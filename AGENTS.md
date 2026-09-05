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
| Core emission and host models/tables | `emitter.py`, `reference.py`, `resources.py` |
| Q14 traversal, prepared rays, physical columns | `precision.py`, `ray_setup.py`, `columns.py` |
| Queued simulation, snapshots, wall reuse | `simulation.py`, `wall_cache.py` |
| Doors, combat, actor slots and masking | `living_world.py`, `door_geometry.py`, `actors.py`, `masked_entities.py` |
| Level compilation, surfaces and fixtures | `levels.py`, `surfaces.py`, `world_decor.py` |
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
- Keep bank-switching execution below `$4000`; banked ROM lookups restore ROM
  bank 1. Preserve **3,000 resident bytes** and the 512-byte stack. Check linker,
  allocation/lifetime assertions and manifest before changing any memory range.
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

Current nine-image oracle: `playtests/sable_objective_spaced_capture_pixels.json`.
Preserve prior objective, helmet, steel, slim, initial Sable and beta.6 fixtures.
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

Author gameplay in `levels/living_world.json`; retain two-sentinel acceptance
and renderer-benchmark levels. Preserve compiler checks for clearance,
reachability, door gates, sightlines and room sizes. Document changed contracts
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
