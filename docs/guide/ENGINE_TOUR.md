# Engine tour

How a frame is made, from a button press to a published VRAM page, with the
module that owns each step. `docs/ARCHITECTURE.md` states the contracts;
this page is the reading order.

## The toolchain

Python does not run on the console: it **emits** the console. `tools/sm83.py`
is an assembler with the exact instruction forms and timings the engine uses,
`tools/build_rom.py` links the resident sections, the cold sections and the
banked tables into a deterministic 4 MiB ROM, and `tools/sm83emu.py` is a
host CGB harness that runs it with DMA, interrupt and mode accounting. The
build writes `build/lupine3d.gb`, a listing, RGBDS-form symbols
(`lupine3d.sym`), a section map and a manifest that records every format
version, budget and hash (`docs/DEVELOPMENT.md`, "Debugger exports").

Every build flag is read at import time, so one process builds one
configuration. `python tools/lupine.py build --flat` and the other CLI
subcommands spawn the right process for you.

## One frame

1. **Input** (`emitter.py`, the VBlank ISR). VBlank samples the pad into a
   timestamped queue in fixed WRAM. Only `MODE_PLAYING` queues simulation
   input; a full-screen mode reads the pad from its own loop.
2. **Simulation** (`simulation.py`, `living_world.py`, `actors.py`). Runs in
   WRAM bank 2 at cooperative yields inside the renderer, consuming up to four
   queued packets per service. Movement, doors, combat, actor AI and pickups
   live here; positions are Q8.8 and doors, rays, hitscan and line of sight
   share one finite door geometry (`door_geometry.py`).
3. **Snapshot**. 456 bytes of world state are copied into bank 1. Rendering,
   animation and the HUD read only the snapshot, so simulation can keep going
   while a frame is composed.
4. **Wall key** (`wall_cache.py`). A 290-byte key (camera, map, door state,
   configuration, reload generation) decides whether the walls can be reused.
   A hit refreshes entities and HUD only; a miss renders the world.
5. **Casting** (`ray_setup.py`, `precision.py`, `columns.py`). Forty-one
   prepared anchor rays traverse the grid in Q14; adaptive pairs, edge recasts
   and conservative interpolation reconstruct 160 physical columns, each with
   a top, a style, a segment key, a surface profile and (textured) an
   along-face coordinate.
6. **Composition** (`emitter.py`, `resources.py`; `textured.py` under the
   textured profile). Each column becomes eight folded tile rows: static
   ceiling/floor and seam tiles, exact-atlas tiles, or dynamic patterns
   composed into the 96-slot ring in fixed WRAM. The textured kernel composes
   from row-window tables instead of microstrips (`docs/TEXTURED_WALLS.md`).
7. **Entities** (`actors.py`, `masked_entities.py`, `animation.py`,
   `world_decor.py`). Actors, drops and fixtures are projected, admitted
   under the sixteen-object/four-per-line budget, masked against the wall
   depth into 32 OBJ patterns, and animated by accepted simulation ticks.
8. **Publication** (`emitter.py` `upload_hidden_page`, `steel_hud.py`). On
   slim, dynamic patterns and the hidden map stream by HBlank DMA during
   composition; one VBlank then moves the masks and attributes by GDMA,
   writes the HUD cells, runs OAM DMA and flips the page. Legacy keeps the
   staged two-VBlank packet. `docs/STREAMED_PUBLICATION.md` has the timing.
9. **HUD** (`steel_hud.py`). A 16-byte packet (health digits, enemy count,
   caption, status, portrait) updates the 24-pixel strip below the STAT
   split; the portrait blinks on snapshot ticks.

## Modes and content

- `screens.py` owns the title, code entry, intermission, death and ending
  modes: full-screen backgrounds composed with the LCD off into the idle
  pattern window, with runtime digit cells for scores and continue codes.
- `levels.py` compiles JSON levels into page-aligned ROM slots, five to a bank, and issues the
  certificate (`docs/LEVEL_FORMAT.md`, `docs/LEVEL_CERTIFICATE.md`).
- `music.py` holds the songs and the sequencer; `artwork.py`,
  `sprite_assets.py` and `texture_assets.py` compile the native art
  (`docs/ART_PIPELINE.md`).
- `layout.py`, `configuration.py` and `allocation.py` are the single source
  of addresses, flags and the machine-checked ledger behind
  [the memory map](MEMORY_MAP.md).

## Where the cycles go

On the coherence tour a full update costs about 675k T-cycles on the flat
compositor: casting is about half, entity work and publication most of the
rest, and composition a few percent. `python tools/lupine.py profile` prints
the split for the current build; `docs/PERFORMANCE_AUDIT_V08.md` ranks the
remaining headroom and `docs/TEST_REPORT.md` has the sustained rates. The
textured kernel's cost and its unmet gate are in `docs/TEXTURED_WALLS.md`.

## What is proven, and how

The engine's invariants are hard gates, not pictures: byte-exact host models
of the geometry, the compositor and the textured kernel; publication safety
in the harness; the MBC5 rule against the emitted image; the resident and
stack reserves; A/B equality of exact-output variants; SameBoy and mGBA
agreement with the host; and the frozen v1 hash. Pictures are golden-image
snapshots with an explicit acceptance path. `docs/VERIFICATION.md` explains
both and `docs/guide/DEBUGGING.md` how to look inside a running ROM.
