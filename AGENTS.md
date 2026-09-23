# Working on Lupine 3D

## Start here

Lupine 3D is a Game Boy Color first-person engine. Python generates SM83 machine
code, lookup tables, levels and native art into a deterministic 4 MiB MBC5 ROM.
Python is the build/test environment, not the console runtime. There is no
framebuffer or cartridge RAM.

Read `README.md`, `docs/DEVELOPMENT.md` and `docs/ARCHITECTURE.md`. `VERSION`
identifies the release; `docs/TEST_REPORT.md` identifies its evidence. Use source,
manifest and CI to resolve stale details in historical milestone documents.
`docs/README.md` separates current guides from retained research.

## Working policy

- Work directly in the existing **main** checkout. Do not create development
  branches/worktrees or switch branches. Temporary source copies for baseline
  comparisons and clean-room builds are allowed.
- The owner has **no physical CGB or flash cartridge**. Validate with the harness
  and pinned SameBoy CGB-0/E and mGBA cores. Do not request hardware testing or
  block an emulator-qualified release on it. Keep hardware-test flags false.
- Preserve user edits and historical evidence. Edit generators/authored assets,
  not ROMs, listings or symbols. Keep changes scoped to the request.
- Builds must never call image generation. Keep selected generated masters,
  prompts, indexed native PNGs, palettes and frame metadata as source assets.

## Commands

Python 3.10+, Pillow and Make are required; CI uses Python 3.12. Reuse `.venv`:

```sh
python3 tools/dev_setup.py       # only if setup is needed
source .venv/bin/activate
make build
make test
```

Run from the repository root. Setup does not activate the environment.
`make PYTHON=.venv/bin/python <target>` also works. The ignored
`build/local-env.sh`, when present, is an optional local emulator-path helper.
RGBDS is not needed. Builds produce `build/lupine3d.gb`, `.sym`, `.lst` and
`build/build_manifest.json`.

`make test` invokes `tools/run_tests.py`: historical tests run under explicit
legacy settings, then Sable/default/display checks run in fresh processes.
Do not run all historical unittests against implicit slim defaults. For a
focused historical suite:

```sh
LUPINE3D_DISPLAY=legacy LUPINE3D_ART=legacy LUPINE3D_ART_ANIMATION=0 \
  .venv/bin/python -m unittest discover -s tests -p 'test_columns.py' -v
```

Flags are read at import time. Use a fresh process for each configuration and
match the validator's configuration to its ROM. Rebuild the default ROM after
experiments that change `build/`. `make clean` removes all of `build/`, including
locally compiled emulator dependencies; do not use it casually.

Independent cores need a C compiler, Make, CMake and the commits in
`docs/DEVELOPMENT.md`. SameBoy's `lib` target builds without `cppp`: only its
generated public headers need it, and the adapter includes `Core/gb.h` from the
core tree. mGBA must use the **Unix Makefiles** generator because its adapter
reads `flags.make` to match the library ABI. Both adapters press START before
they do anything else, because the campaign holds the world behind a title
screen. Installed emulator applications do not replace these pinned lanes.

## Code map

Paths below are relative to `tools/lupine3d_v4/` unless stated otherwise.

| Area | Files |
| --- | --- |
| Build/linker and public compatibility facade | `tools/build_rom.py` |
| Addresses, flags, allocation/lifetime assertions | `layout.py`, `configuration.py`, `allocation.py` |
| MBC5 bank contract over the emitted image | `bank_safety.py` |
| Core emission and host models/tables | `emitter.py`, `reference.py`, `resources.py` |
| Q14 traversal, prepared rays, physical columns | `precision.py`, `ray_setup.py`, `columns.py` |
| Queued simulation, snapshots, wall reuse | `simulation.py`, `wall_cache.py` |
| Doors, combat, actor slots and masking | `living_world.py`, `door_geometry.py`, `actors.py`, `masked_entities.py` |
| Level compilation, surfaces and fixtures | `levels.py`, `surfaces.py`, `world_decor.py` |
| Game modes and full-screen presentation | `screens.py` |
| Songs, the sequencer and sound effects | `music.py` |
| Native art, animation, steel HUD | `artwork.py`, `sprite_assets.py`, `animation.py`, `steel_hud.py` |
| Gated experiments | `tile_cache.py`, `packets.py`, `physical_depth.py`, `actor_precision.py`, `admission.py`, `projection_storage.py`, `near_field.py`, `foreground.py` |
| Assembler and deterministic CGB harness | `tools/sm83.py`, `tools/sm83emu.py` |
| Content, assets, scenarios and tests | `levels/`, `assets/`, `playtests/`, `tests/` |
| Research and retained evidence | `research/`, `milestones/`, `.render-baselines/` |

`lupine3d_v4` remains the active package despite its historical name. Preserve
its import path and the `build_rom` exports used by tests/research. Historical
`build_rom_v1.py`/`build_rom_v2.py` remain references; the frozen v1 hash is a
regression contract.

## Production configuration

- Default `LUPINE3D_DISPLAY=slim`: 160×120 world, horizon 60, 24-pixel HUD,
  15 world tile rows, eight folded composition rows and STAT switch at 120.
  `compact` retains 112/32; `legacy` retains 96/48. Extend vertical visibility;
  do not stretch horizontal FOV or projection scale.
- New Sable art and animation are default except for the legacy profile.
  The owner explicitly accepted their performance cost. Preserve the failed
  original quality-budget evidence; do not ask for that acceptance again or
  silently describe the mathematical gate as passed.
- Accepted exact rendering flags: `COMPACT_STRIPS`, `CAMERA_SETUP`,
  `NARROW_YIELDS`, `ATTRIBUTE_PADDING`. Other experimental kernels stay disabled;
  projection storage is `direct`, reprojection is off. Diagnostic commands may
  adapt implicit defaults; explicit incompatible requests must fail.
- Legacy/compact strips retain 19 logical/nine stored states. Slim uses 21/11:
  states 19/20 represent both boundaries in the self-mirrored centre tile.
  Preserve exact centre coverage. The unfolded diagnostic uses bank 237 and
  fixed 16-byte scratch at `$C8E0–$C8EF`.
- Preserve prepared scalar records 0–240 and raw-query sentinel semantics.
  Packet experiments own records 241–250 only.

## Textured walls (the slim default)

- Textured walls are the slim Sable default (slim + Sable + streaming only):
  the row-window kernel in `textured.py` replaces the microstrip compositor
  and the trained atlas; `texture_reference.compose_kernel` is its
  byte-exact model and `docs/TEXTURED_WALLS.md` the contract, and the
  default goldens live under `snapshots/slim-sable-v2-textured/`.
  `LUPINE3D_TEXTURED_WALLS=0` builds the flat slim profile (`make flat
  playtest-flat sable-check-flat`, goldens under `snapshots/slim-sable-v2/`);
  legacy and compact are always flat, and diagnostics textured walls cannot
  run with (unfolded, physical depth, anchor packets) adapt the implicit
  default to flat. An explicit incompatible request fails.
- Every cast records its along-face coordinate (`RAY_U`, `PIXEL_U`), oriented
  so texture columns never decrease across the view: the console negates the
  east and north faces. Textures are authored 16x8 indexed PNGs under
  `assets/textures/`, mirrored about the horizon by construction; builds
  compile them into row-window blocks (`TEXTURE_WINDOW_BANKS`: 248-255,
  246, 155) and never generate images. Each episode has its own texture set,
  selected by the level's palette set: `load_level` points `TEX_DIRECTORY`
  at the set's slice of `tex_block_directory` (`docs/TEXTURED_WALLS.md`,
  "Texture sets per episode").
- Dynamic patterns are numbered in composition order (ids 0..237: below 128
  at `$9000`, the rest at `$8800`; ceiling 238, floor 239) and composed into
  a 96-slot ring at `$C000` that HBlank DMA drains in chunks that never cross
  the ring wrap or the VRAM half. `DYN_STREAMED`/`DYN_INFLIGHT` are the
  hand-off; a tile waits only when it would lap a slot still in flight. With
  the LCD off the ring flushes into both banks by GDMA as it composes, so
  `enter_world` uploads no patterns separately.
- The kernel's scalars alias the flat compositor's compositor-local HRAM
  (HRAM is full); its run records, window caches and mask tables live for one
  composed column (`TEX_RUNS`, `TEX_WINDOWS`, `TEX_MASKS`). Runs split on
  face key, surface profile and the shade bit. Bank switches stay in the
  resident half (`tex_column_runs`); the row kernel is cold.
- Measured over every code region of the coherence tour, the kernel costs
  about 270k T per full update against the flat compositor's 60k (tour mean
  917k T against 675k) before Phase 5; the owner made it the default after
  that round anyway. The numbers, the missed gate and what each part costs are in `docs/TEXTURED_WALLS.md` and
  `research/results/textured_walls_lab_v2.json`. One-face columns run
  `tex_column_single` with the accumulator, step and slot in registers
  across the column; seam columns run `tex_compose_tile` per tile. A run
  whose row step is under one texel row takes the 76 T rows (`fast_rows`:
  `DE` the cache row, `B` the fraction, `C` the step, `HL` the
  destination, `set 3,e` for the second plane), which relies on a run's
  cache being sixteen-aligned and its texel rows staying below eight.

## Campaign, modes and screens

- `GAME_MODE` in fixed WRAM drives the loop: only `MODE_PLAYING` runs the world
  renderer. The VBlank ISR queues simulation input in that mode alone. A
  full-screen mode owns the whole background with LCDC `$81` and VBlank only,
  so it has no HUD boundary and therefore no STAT split.
- Screens borrow the idle 96-pattern composition window at `$9000` and are
  written with the LCD off. `enter_world` repeats the boot upload, so a screen
  never has to put anything back. Runtime digits are patterns 0–9 and go into a
  screen's reserved map slot **before** the LCD comes back on.
- Screen slot state borrows the bottom of the BG map staging buffer at `$C600`:
  a full-screen mode owns the whole background, so composition is idle for
  exactly as long as that state exists, and `enter_world` refills the buffer.
  Campaign state that must ride the render snapshot goes in the slack at the
  top of the copied world window; it never grows the copy (`WORLD_COPY_BYTES`:
  the map, the camera, the 128-byte world window and the actor slots). Per-level
  constants (`ACTOR_COUNT`, the palette set, weapons owned, the level page) are
  fixed-WRAM campaign scalars written by `load_level` with the LCD off.
- Level selection is runtime, not an assembled immediate. Campaign levels are
  packed five to a ROM bank from `LEVEL_ROM_BANK_BASE` in page-aligned slots
  (`LEVEL_SLOT_PITCH`) at the fixed offsets in `levels.py`; the resident
  `level_directory` gives `select_level` each level's bank and slot page, and
  every reader adds the page with `add_level_page`. `LEVEL_INDEX`,
  `LEVEL_BANK` and `LEVEL_PAGE` live in fixed WRAM outside the snapshot copy
  and only change with the LCD off. The surface table must stay exactly 1,024
  bytes above the segment table: `lookup_segment_id` reads both through one
  pointer. Every level bank read restores ROM bank 1.
- All campaign levels share one `vram_profile`: the resident atlas is still
  chosen at build time and `layout.py` rejects a campaign that disagrees.
  Lifting that needs atlas streaming, not a new flag. `palette_profile` is
  per level (`PALETTE_IDS`: outpost 0, reactor 1, spire 2): `load_level`
  stores header byte 3 in `PALETTE_SET` and `enter_world` uploads that
  128-byte set (BG then OBJ) with the LCD off, clamping an unknown set to 0.
  Sets recolour only the world (BG 0, 2-6; OBJ 1, 6, 7); BG 1 and 7 and the
  weapon, drop, flash, decor and reticle palettes are identical in every set
  because screens never rewrite palettes. Set 0 is byte-identical to the
  original table, so the outpost goldens do not move.
- Episodes are `EPISODE_SECTORS` (six) sectors. The title opens episode one;
  when `LEVEL_INDEX` is one of `EPISODE_STARTS` (6, 12) the episode's opening
  screen shows before its first sector loads (`show_episode_opening`, from
  the title start, so a continue code opens its episode), and the intermission
  that advanced onto it shows the finished episode's closing first
  (`show_episode_closing`, intermission mode only, so a death retry never
  shows one). `SCREEN_EPISODE_CLOSINGS`/`OPENINGS` index `SCREEN_SOURCES`.
- Death retries the current sector; completion advances `LEVEL_INDEX` through an
  intermission, and the last sector's ending restarts the campaign. Host
  geometry oracles must follow the ROM: select the reference level from the
  running machine's `LEVEL_INDEX`, never from the build-time first level.

## Continue codes

- There is no cartridge RAM, so progress is a written-down code. `continue_codes`
  generates one four-digit code per (sector, skill) pair at build time: distinct,
  deterministic and never starting with a zero. The console compares bytes; it
  never decodes a checksum. Regenerating the table changes every code, so treat
  it as content, not an implementation detail.
- A screen may reserve up to `SCREEN_SLOT_CAPACITY` map cells it rewrites at
  runtime. Patterns 0-9 are the digits and pattern 10 is blank, so a number or a
  cleared cell is one map write - done with the LCD off, or at the top of VBlank
  from the screen loop. Keep the code's four cells adjacent.
- SELECT opens code entry from the title only. An unrecognised code is refused
  without changing anything, and SELECT cancels back to the title.
- A screen declares a label and the number of cells the runtime writes after
  it; `compose_screen` places the cells on tile boundaries, the label clear of
  them, and refuses a line whose glyphs straddle a tile row or land on
  authored art. Never place those cells by hand.

## Enemies and skill

- An actor's kind is byte 15 of its slot (`ACTOR_KIND_OFFSET`), so it rides the
  existing per-slot save/load and the bank-1 snapshot. `actor_kind_stats` gives
  each kind contact damage, attack recovery, Q8 step, OBJ palette and what it
  drops; records are `ACTOR_KIND_RECORD_BYTES` wide so `actor_kind_record` can
  still index by shifting, and there are four because the kind byte is masked
  to two bits. The fourth is the **boss** (kind 3): the Sentinel's cels and
  OBJ palette, the heaviest contact damage in the game, slow, with the health
  its level gives it; a corrupt kind byte still reads a playable actor. The
  last sector of an episode fields one.
- Kinds share the Sentinel's cels, so variety costs ROM, not VRAM patterns —
  but a distinct look costs an **OBJ palette**, and all eight are spoken for:
  0 weapon, 1 Sentinel, 2 drops, 3 muzzle/decor, 4 decor and the reticle,
  5 the weapon's second palette, 6 warden, 7 skirmisher. A fourth visible kind
  means re-planning those, not editing the table; palette 6 came free only
  because the reticle is a single-colour crosshair that could share palette 4,
  and that still moved shipped pixels. Resolve the palette once per actor in
  `render_sentinel_actor`: every submission needs D for the cel.
- A drop carries no kind byte: it is whatever the actor that left it was.
  `KIND_DROPS` in `levels.py` and the table's drop column must agree, a level
  declares the drops it fields, and the compiler refuses one whose keycard sits
  behind the door it opens.
- `DIFFICULTY` (0..2, chosen with left/right on the title) scales contact
  damage only — half, authored, or one and a half. Selection follows rising
  edges, so holding the pad is one step.
- `sentinel_patrol_step` and `sentinel_chase_step` share four named stepping
  bodies at the kind's own speed; each returns Z when the step was taken.
  Patrol walks a heading from `ACTOR_PATROL`, a parallel per-actor array in the
  snapshot slack, and turns a quarter turn when a step is refused. The actor
  slot is exactly full: new per-actor state goes beside it, not in it.
- A dormant actor wakes inside the level's authored `activation_radius_q4`,
  folded to whole cells once at load. It is not a phase count.
- Contact is cell adjacency with line of sight, and across a diagonal only
  when the corner is clean (both cells the two share a side with are open):
  a wall corner that blocks the player's shot blocks the actor's reach too,
  so it keeps chasing and swings from beside the player instead.
  `tests/test_campaign.py` pins it; the eighteen-sector route found it.

## Weapons

- Four weapons (`WEAPON_COUNT`, a power of two: the index is masked) share
  one eighty-pattern window at `$8200` in VRAM bank 1, so only one is
  resident. Their cel sheets live in `WEAPON_ROM_BANK` (245) in weapon order
  and `weapon_source` reads a resident pointer table; `init_vram` and
  `service_weapon_swap` map that bank only for the copy and put the boot
  bank or bank 1 back. SELECT walks to the next **owned** weapon
  (`swap_weapon` tries the other three and gives up without a swap when
  none is owned) and `service_weapon_swap` streams its cels in as a single
  GDMA **with the LCD off**, from the main loop once the frame is
  published. A transfer with the LCD on is part of a frame's publication to
  the console and to the harness; this is a VRAM re-upload, and the
  controller route refuses the frame if it is done the other way.
- `WEAPONS_OWNED` is a bit per weapon that `load_level` derives from
  `LEVEL_INDEX` and `WEAPON_UNLOCK_SECTORS` (0, 0, 6, 12), so a continue
  code restores the arsenal for free and one that moves backwards takes a
  weapon away; a weapon in hand that is no longer owned drops to the first.
- Pattern IDs never change, only their contents, so no OAM is rewritten and the
  animation code is weapon-agnostic. Every weapon must compile to exactly
  `WEAPON_TILE_BYTES`; the sheets are rendered from 3D models by
  `tools/render_weapons.py` (`docs/ART_PIPELINE.md`, "Weapons are rendered
  from models") into a 40x32 window right of centre: ten objects
  (`WEAPON_OBJECTS`, OAM 0-9, then the reticle and muzzle), four cels of
  twenty patterns, and a per-weapon OBJ palette per object that
  `animate_weapon` writes from `weapon_object_attributes` (all palette 0
  today: a second colour could only fill whole sprites, and on a diagonal,
  sliding gun that shows as rectangles). The scanline
  admission counts those objects before admitting world objects.
- `weapon_stats` gives each weapon damage and recovery in simulation ticks. The
  shotgun's record is the engine's original behaviour exactly — one damage, no
  recovery — so a change there is a change to every existing measurement.
- A shot lands on the nearest actor inside the aim window whose Q5 depth is
  below the centre ray's wall depth plus `HITSCAN_DEPTH_SLACK` (a quarter
  cell): a chaser pressed flush against a wall has its centre on that wall's
  plane and must still be hittable, while an actor behind a wall or a closed
  panel is at least half a cell further. `tests/test_hitscan.py` pins both.

## Sound contracts

- CH1 belongs to sound effects alone; the sequencer owns CH2, CH3 and CH4, so
  firing can never cut the music. Effects are one-shot register presets with no
  per-frame service.
- The sequencer **never ticks in VBlank**. A staged publication finishes its
  GDMA roughly one scanline before 153 (measured line 152, dot 432 of 456), so
  VBlank has no room for anything else: adding a single conditional call there
  pushes the legacy profile past the deadline. The world ticks it from the
  viewport STAT boundary; a full-screen mode ticks it from its wait loop.
- The tick **never switches the ROM bank**: an interrupt can land between a
  banked lookup's switch and its read. Songs are copied into WRAM bank 5 and
  the tick saves/restores SVBK. Keep the test that scans for a bank-register
  write in every routine the tick reaches.

## Runtime and memory contracts

- Implement SM83 routines in the relevant emission module. Document register/
  flag clobbers, stack use, bank ownership and overflow where correctness relies
  on them. New opcode forms require assembler and harness support.
- Preserve Q8.8 positions, Q14 crossing-order/tie semantics, Q5 projection and
  conservative interpolation. Segment identity is separate from material.
  Rays, hitscan, LOS and collision share finite-door geometry.
- VBlank samples/queues input. Simulation runs at cooperative yields in WRAM
  bank 2; rendering uses an immutable bank-1 snapshot. Preserve queue debt,
  edges, accepted animation ticks and wraparound. Restore bank 1 on return.
- `bank_safety.py` checks the MBC5 rule against the emitted image, so code
  placement is a build decision: every bank-register write and everything an
  interrupt reaches stays below `$4000`, nothing runs above it with a foreign
  bank mapped, and no section falls through into the next. Banked lookups
  restore ROM bank 1 — unconditionally, where a conditional restore would leave
  a window no static reading can prove closes. Bank-neutral sections go in
  `cold_sections` and land above `$4000` in bank 1. Preserve **3,000 resident
  bytes** and the 512-byte stack. Check linker, allocation/lifetime assertions
  and manifest before changing any memory range.
- Full publication owns matching BG patterns/maps/attributes, masks, HUD and
  OAM. Commit coherently. BG/OBJ bank owners may differ after cached updates.
  Preserve exact wall-key validation and reload-generation handling.
- Limits: 96 dynamic BG patterns, 32 masked OBJ patterns, six simulated actor
  slots (`MAX_ACTORS`) of which the OBJ budget admits four per frame,
  16 world objects/four per scanline, 40 total objects/ten per scanline.
  Do not partially admit an actor or overwrite published patterns.
- Compact/slim full packets are **HBlank-streamed** (`HDMA_STREAMING`, see
  `docs/STREAMED_PUBLICATION.md`): dynamic patterns and the whole hidden map
  go by HBlank DMA during composition, from **fixed-WRAM sources only** (a
  block reads through SVBK and a yield may have bank 2 mapped); the tail is
  one VBlank of at most 62 banked GDMA blocks (masks + attributes) plus
  HUD/OAM/flip. Start a transfer only while `HDMA5` reads idle and the LCD is
  on, never terminate one, never write VBK while one is active, and keep
  `DYN_STREAMED` in step with the hand-offs. Finish the tail before line 153.
  The legacy profile keeps the staged packet: at most **176 GDMA blocks** over
  two VBlanks, 96-block first stage, 192 CPU-copied hidden-map bytes on the
  compact profiles only when streaming is off. Slim map/attribute buffers are
  480 bytes.
- Overlapped publication is the slim default (`LUPINE3D_OVERLAP_PUBLICATION=0`
  builds the synchronous tail, `make sync playtest-sync`; compact keeps it
  unless asked; physical depth and anchor packets exclude it): the VBlank
  interrupt publishes the tail (`vblank_tail`, fixed half, saves SVBK/VBK,
  never switches the ROM bank) after `publication_handoff` sets
  `TAIL_PENDING`; the main loop settles anything the tail would read from the
  snapshot before the hand-off and calls `wait_tail` before it touches a
  publication buffer or turns the LCD off. `wait_tail` publishes the packet
  itself at the next VBlank's entry if the interrupt did not (interrupts
  off), and boot clears `TAIL_PENDING`. In the harness a presented frame is
  read as the state it was handed off with, and host writes to a running
  machine must pass `diagnostic_barrier` (`docs/VERIFICATION.md`).
- Physical depth validity means an actual query at that column and wall key.
  Same-key appearance refinement must promote a coherent full wall packet.
  Never relabel duplicated or height-class depths as physical measurements.
- Foreground events originate only at simulation acceptance. Preserve sequence,
  generation, pending events and published world-OAM ownership. This disabled
  experiment has separate occupancy and VBlank gates; count its publications
  separately from full geometry updates.

## HUD and animation contracts

Read `docs/SABLE_OUTPOST.md` and `docs/STEEL_HUD.md` before changing art.
Keep the approved **armoured helmet and respirator**; do not substitute an
uncovered human face. The skull counts living enemies remaining. Slim reads
GOAL/HUNT until enemies are defeated, then GOAL/EXIT; DEAD/DONE clear GOAL.
Internal LOCK/OPEN keys remain for the packet ABI. No controls footer/hint tiles.

The 16-byte HUD packet at `$D3D8` owns health 4, count 1, caption 2, status 3 and
portrait 6 bytes. HUD source uses **94/96 patterns**. Objective text starts at
HUD y=4/y=10; status IDs reference vertical tile pairs and publication writes
ID+1 into the third HUD row on both maps. Preserve all chassis/framing pixels.
Slim helmet blink uses accepted snapshot ticks 62–63 modulo 64.

Weapon/UI occupies 86 preloaded bank-1 OBJ patterns, separate from the 32 masked
patterns; eighty of them are one weapon's cels and are streamed, not resident
per weapon (see **Weapons**). The enemy/fixture ROM source dictionary has 242 patterns; source IDs
are not resident VRAM IDs. Preserve cold-bank capacity. Animation follows
accepted snapshot ticks; pending flashes cannot expire unseen. Cosmetic death
must never delay gameplay death, pickups or exit activation; living actors and
pickups take precedence over cosmetic corpses.

## Verification and evidence

For runtime/content changes run `make test playtest playtest-world`; add:

| Affected behavior | Additional checks |
| --- | --- |
| Art/HUD/palettes/fixtures | `make playtest-art`; `tools/check_sable.py`; inspect emitted-ROM stills and motion |
| Display dimensions/folding | `tools/check_display.py`; variants; boundary/publication checks |
| Movement/doors/combat/progression | `make playthrough variants`; `tools/playthrough.py --restart`; `--sectors A-B` replays one sector through its continue code |
| Geometry/composition/cache/timing | `make variants wall-reuse motion`; `make research-tail` for traversal/projection |
| CPU/banks/interrupts/DMA/publication | Both pinned `make sameboy` and `make mgba`; `tools/independent_witnesses.py` |
| Assembler or harness opcode/flag semantics | `make conformance SAMEBOY_DIR=…` (`tools/harness_conformance.py`): every emitted form, harness vs SameBoy |

Visual verification is **golden-image snapshots** (`tools/snapshot.py`,
`docs/VERIFICATION.md`): goldens under `snapshots/<profile>/<suite>/` with a
manifest binding each scene to the ROM, configuration, author, date and a
note. Every producer (`playtest`, `check_sable`, `independent_witnesses`)
checks its captures against them and fails naming the scene; the route only
records. The evidence (`actual`, `expected`, `diff`, `report.html`) lands in
`build/snapshots/` and is CI's `visual-diff` artifact. An intentional image
change is accepted with `python tools/snapshot.py accept --suite … --scene …
--note "why"` and committed with its PNG so the PR shows the diff; nothing
in CI accepts, and an empty note is refused. The retired hash oracles live in
`playtests/archive/oracles/` as evidence only. Engine invariants (model
equality, publication safety, the bank contract, reserves, A/B equality,
core agreement, the v1 hash) are hard gates, never snapshots: **never weaken
a check to pass.**

`playtest`/frozen witnesses may inject diagnostic poses. `playthrough` uses
controller input without game-RAM writes. Sustained motion uses LCD-indexed
controller replays and host observation; no diagnostic writes after setup.
CPU **T-cycles** are the timing unit; LCD timing does not double with CPU speed.
Report full geometry and cached/foreground presentations separately.

Use `tools/sable_sustained.py` for all eight 60-second current scenarios.
Keep sustained work in manual/release qualification, not short CI. Preserve
immutable pre-viewport B/P data in `milestones/sable-v2/performance-inputs.json`.
`tools/sable_quality_budget.py` retains the original mean/p95 gate
`Q <= (B + P) / 2`; its expected failure records the owner's visual tradeoff.
Other experiments still require their acceptance gates. Same-snapshot exactness
and live-controller performance are different comparisons.

Follow `.github/workflows/ci.yml` for complete short CI. `make qa`/`verify` do not
cover every lane. Reports must identify ROM/configuration and actual checks run.
Documentation-only edits need link/command/diff checks, not a ROM test rerun:
`make docs-check` (`tools/check_docs.py`) verifies every link and command and
that `docs/guide/MEMORY_MAP.md` matches the manifest (regenerate it with
`make memory-map`, never by hand). Historical documents live in
`docs/archive/` with an index; `python tools/lupine.py` is the one entry
point for build, run, snapshot, level, profile and verification commands.

## Documentation and release hygiene

Author gameplay in the campaign levels `levels.py:CAMPAIGN_ORDER` names:
three episodes of six sectors (`docs/CAMPAIGN.md`, "Three episodes"). The
full controller route plays every sector, so it is run by episode: CI's slow
lane plays `SECTORS=1-6` and the `campaign` matrix plays 7-18 in three-sector
chunks from their continue codes (`make playthrough SECTORS=A-B ROUTE_DIR=…`,
`RESTART=1` for the last); `release_check.py` unions every report for the
current ROM.
Budget minutes, not seconds. Retain the
two-sentinel acceptance and renderer-benchmark levels. Preserve compiler checks
for clearance, reachability, door gates, sightlines and room sizes: every
campaign level carries the same certificate, and `release_check.py` gates all of
them, not just the first. Document changed contracts
alongside source. Historical experiments write new results under `build/` unless
intentionally adding versioned evidence.

Keep `.venv/`, `build/`, `dist/`, cores, ROMs and release archives out of commits.
Use `make preview` for actual emulator images. Follow `docs/DEVELOPMENT.md` and
`tools/package_release.py` for release qualification and clean-room packaging.
The package uses explicit allowlists: include every required source input.
Retained qualification evidence is reusable only for the identical ROM SHA;
clean-room builds and extracted-source tests must still run. Tag `v$(cat VERSION)`
from main. Report emulator qualification honestly; hardware/boot-ROM testing
remains unavailable and false.
