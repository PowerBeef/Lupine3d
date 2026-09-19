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
`docs/DEVELOPMENT.md`. SameBoy requires `cppp`; mGBA must use the **Unix Makefiles**
generator because its adapter reads `flags.make` to match the library ABI.
Installed emulator applications do not replace these pinned verification lanes.

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

## Campaign, modes and screens

- `GAME_MODE` in fixed WRAM drives the loop: only `MODE_PLAYING` runs the world
  renderer. The VBlank ISR queues simulation input in that mode alone. A
  full-screen mode owns the whole background with LCDC `$81` and VBlank only,
  so it has no HUD boundary and therefore no STAT split.
- Screens borrow the idle 96-pattern composition window at `$9000` and are
  written with the LCD off. `enter_world` repeats the boot upload, so a screen
  never has to put anything back. Runtime digits are patterns 0–9 and go into a
  screen's reserved map slot **before** the LCD comes back on.
- Level selection is runtime, not an assembled immediate. Each campaign level
  owns one ROM bank from `LEVEL_ROM_BANK_BASE` at the fixed offsets in
  `levels.py`; `LEVEL_INDEX`/`LEVEL_BANK` live in fixed WRAM outside the
  snapshot copy and only change with the LCD off. The surface table must stay
  exactly 1,024 bytes above the segment table: `lookup_segment_id` reads both
  through one pointer. Every level bank read restores ROM bank 1.
- All campaign levels share one `vram_profile` and `palette_profile`: the
  resident atlas is still chosen at build time and `layout.py` rejects a
  campaign that disagrees. Lifting that needs atlas streaming, not a new flag.
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

## Enemies and skill

- An actor's kind is byte 15 of its slot (`ACTOR_KIND_OFFSET`), so it rides the
  existing per-slot save/load and the bank-1 snapshot. `actor_kind_stats` gives
  each kind contact damage, attack recovery, Q8 step and OBJ palette; the table
  has four records because the kind byte is masked to two bits, and the spares
  repeat the Sentinel so a corrupt byte still reads a playable actor.
- Kinds share the Sentinel's cels, so variety costs ROM, not VRAM patterns —
  but a distinct look costs an **OBJ palette**, and only palette 7 was free
  (0 weapon, 1 Sentinel, 2 pickup, 3 muzzle/decor, 4 decor, 5 the weapon's lit
  corners, 6 the reticle). A third visible kind means re-planning those, not
  editing the table. Resolve the palette once per actor in
  `render_sentinel_actor`: every submission needs D for the cel.
- `DIFFICULTY` (0..2, chosen with left/right on the title) scales contact
  damage only — half, authored, or one and a half. Selection follows rising
  edges, so holding the pad is one step.
- `sentinel_patrol_step` and `sentinel_chase_step` share one stepping body at
  the kind's own speed, with the carry and collision test the old patrol
  lacked. Patrol is still a bob in place, not a route.

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
- Limits: 96 dynamic BG patterns, 32 masked OBJ patterns, four actor slots,
  16 world objects/four per scanline, 40 total objects/ten per scanline.
  Do not partially admit an actor or overwrite published patterns.
- Full packets remain at most **176 GDMA blocks**, staged across VBlanks.
  This is not a single-VBlank allowance. Slim map/attribute buffers are 480 bytes.
  Extra hidden-map CPU copies total 96 map + 96 attribute bytes: 96 map and
  32 attribute bytes in the pattern stage, 64 attributes in the final commit.
  Above 48 dynamic+mask patterns, insert another VBlank before the pattern stage.
  Preserve the 96-block first-stage limit and finish writes before line 153.
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
patterns. The enemy/fixture ROM source dictionary has 242 patterns; source IDs
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
| Movement/doors/combat/progression | `make playthrough variants`; `tools/playthrough.py --restart` |
| Geometry/composition/cache/timing | `make variants wall-reuse motion`; `make research-tail` for traversal/projection |
| CPU/banks/interrupts/DMA/publication | Both pinned `make sameboy` and `make mgba`; `tools/independent_witnesses.py` |

Current nine-image oracle: `playtests/sable_v09_capture_pixels.json`. It differs
from the v0.8 oracle in eight pixels a frame: the reticle moved to OBJ palette 4
so palette 6 could carry a third enemy kind. Preserve the prior objective,
helmet, steel, slim, initial Sable and beta.6 fixtures.
Intentional image changes need explained before/after ROM captures and a new
versioned oracle. Never weaken checks or change hashes just to pass.

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
Documentation-only edits need link/command/diff checks, not a ROM test rerun.

## Documentation and release hygiene

Author gameplay in the campaign levels `levels.py:CAMPAIGN_ORDER` names. The
full controller route plays every sector, so it grows with the campaign -
budget minutes, not seconds, and keep it out of the short lanes if it stops
fitting. retain
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
