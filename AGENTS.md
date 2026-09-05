# Working on Lupine 3D

## Project

Lupine 3D is a Game Boy Color first-person engine. Python emits SM83 machine
code, lookup tables, levels, and native pixel art into a deterministic 4 MiB
MBC5 ROM. The game uses tiles and hardware sprites, with no framebuffer or
cartridge RAM. Python is the build and verification environment, not the
runtime language on the console.

Start with `README.md`, `docs/DEVELOPMENT.md`, and `docs/ARCHITECTURE.md`.
`VERSION` identifies the release. Use the current implementation, tests, and
`.github/workflows/ci.yml` to resolve stale details in older documents;
`CONTRIBUTING.md` still contains historical test counts and DMA limits.

## Development policy

Develop directly in the existing `main` checkout. Do not create development
branches or Git worktrees, or switch away from `main` for project work.
Temporary source copies for baseline comparisons and clean-room verification
are allowed; they do not change this development policy.

The owner has no physical Game Boy Color or flash cartridge available.
Use the project harness and pinned SameBoy CGB-0/E and mGBA lanes for validation.
Physical testing is unavailable, not a prerequisite for development or
emulator-qualified releases. Do not ask the owner to run hardware tests.
Keep hardware-test flags false and describe results as emulator-qualified;
the physical checklist is retained only for possible future hardware access.

## Code map

| Location | Responsibility |
| --- | --- |
| `tools/build_rom.py` | Build entry point, ROM linker, and compatibility exports used by tests and research. |
| `tools/lupine3d_v4/layout.py` | Hardware addresses, memory allocation, constants, and build configuration. |
| `tools/lupine3d_v4/emitter.py` | Core SM83 emission: arithmetic, raycasting, tile composition, input, and publication. |
| `tools/lupine3d_v4/reference.py`, `resources.py` | Host reference models, graphics resources, and lookup tables. |
| `tools/lupine3d_v4/precision.py`, `ray_setup.py`, `columns.py` | Q14 traversal, prepared ray records, and physical-column reconstruction. |
| `tools/lupine3d_v4/simulation.py`, `wall_cache.py` | Queued simulation, immutable render snapshots, and exact wall reuse. |
| `tools/lupine3d_v4/configuration.py`, `allocation.py` | Resolved experiment flags, configuration identity, memory and lifetime assertions. |
| `tools/lupine3d_v4/tile_cache.py`, `packets.py`, `physical_depth.py`, `actor_precision.py` | Gated cache/traversal/depth/projection kernels. |
| `tools/lupine3d_v4/admission.py`, `projection_storage.py`, `near_field.py`, `foreground.py` | Gated actor transactions, table storage, plane precision and feedback publication. |
| `tools/lupine3d_v4/living_world.py`, `door_geometry.py`, `actors.py`, `masked_entities.py` | Movement, shared door geometry, combat, actor slots, and sprite masks/admission. |
| `tools/lupine3d_v4/levels.py`, `surfaces.py`, `artwork.py`, `world_decor.py` | Level compilation, surface palettes, current pixel art/HUD, and wall fixtures. |
| `tools/sm83.py`, `tools/sm83emu.py` | Purpose-built assembler and deterministic CGB test harness. |
| `levels/`, `assets/`, `playtests/`, `tests/` | Authored content, atlas data, driven scenarios/RGB fixtures, and unittest coverage. |
| `research/`, `docs/`, `milestones/` | Geometry/performance experiments, design contracts, and retained evidence. |

Module names after the first path in a table row are in that same directory.
`lupine3d_v4` is the active package despite its historical name. Preserve its
import path and the `build_rom` facade. `tools/build_rom_v1.py` and
`tools/build_rom_v2.py` are historical implementations; the v1 ROM hash is a
frozen regression contract, and active code still reuses some v1 helpers.

## Environment and commands

Requirements are Python 3.10+, Pillow from `requirements.txt`, and Make.
CI uses Python 3.12. Reuse a working `.venv`; for initial setup:

```sh
python3 tools/dev_setup.py
source .venv/bin/activate
make build
make test
```

Run commands from the repository root. Setup creates the environment but does
not activate it. Alternatively, use `make PYTHON=.venv/bin/python <target>`.
If present, the local `build/local-env.sh` also sets emulator paths; it is an
optional ignored helper, not a repository prerequisite.

The build produces `build/lupine3d.gb`, `.sym`, `.lst`, and
`build/build_manifest.json`. RGBDS is not required for the Python ROM builder.
Independent verification needs a C compiler, Make, CMake, and the pinned
SameBoy/mGBA sources described in `docs/DEVELOPMENT.md` and CI:

```sh
make sameboy SAMEBOY_DIR=/absolute/path/to/SameBoy
make mgba MGBA_DIR=/absolute/path/to/mgba
```

Use mGBA's Unix Makefiles generator: its adapter reads `flags.make` to match
the compiled library ABI. SameBoy's public-header generation needs `cppp`.
Installed emulator apps are useful for playtesting but do not replace these
pinned verification cores.

## Implementation contracts

- Keep ROM output deterministic and preserve the frozen v1 hash. Edit source
  generators and authored content, not generated ROMs, listings, or symbols.
- Implement SM83 routines in the relevant emission module. Follow surrounding
  Python style; explain register/flag clobbers, stack use, bank ownership, and
  integer overflow where correctness depends on them. If adding an opcode
  form, check both the assembler and the harness support it correctly.
- Preserve Q8.8 positions, Q14 crossing-order semantics, Q5 depth/projection,
  and conservative interpolation. Physical segment identity is independent
  of material colour. Rays, hitscan, LOS, and collision share door geometry.
- VBlank samples and queues input; simulation runs at cooperative yields.
  Render from the immutable bank-1 snapshot while bank 2 owns live state.
  Preserve queue debt and edges, restore render state, and test wraparound.
- Keep bank-switching code in fixed ROM below `$4000`; banked lookups restore
  ROM bank 1. Check `layout.py`, linker assertions, and the build manifest
  before changing ROM/WRAM/HRAM/VRAM allocation or scratch lifetimes.
- Publish matching BG patterns/maps/attributes, masks, HUD, and OAM atomically.
  BG and OBJ bank owners can differ after cached updates. Preserve exact wall
  cache invalidation, retained depth, and reload-generation handling.
- Respect 96 dynamic BG patterns, 32 masked OBJ patterns, four actor slots,
  40 hardware objects, and ten objects per scanline. World admission is further
  bounded to 16 objects and four per scanline. Maximum full packets are 176
  GDMA blocks staged across VBlanks; do not treat that as a single-VBlank
  allowance. Keep GDMA/OAM/publication timing safe and published banks intact.
- Build flags are read at import time. Scope `LUPINE3D_*` overrides to a fresh
  process and use identical configuration for the ROM and host validator.
  Keep experimental reprojection off by default. Rebuild the default ROM
  after experiments that change the on-disk build.
- The accepted rendering defaults are `COMPACT_STRIPS`, `CAMERA_SETUP`,
  `NARROW_YIELDS`, and `ATTRIBUTE_PADDING`. Other new kernels remain disabled;
  projection storage defaults to `direct`. Historical folded/prepared/reprojection
  diagnostic commands adapt implicit defaults, but explicit incompatible
  requests must fail. See `docs/RENDERING_IMPLEMENTATION.md` for evidence.
- Preserve the general 19-state strip oracle and nine stored folded states.
  The unfolded diagnostic uses bank 237 and fixed 16-byte scratch. Keep
  prepared records 0–240 intact; packets own only records 241–250.
- Physical depth validity means a real query at that physical column and wall
  key. Same-key appearance refinement must promote a coherent full wall packet.
  Never relabel duplicated/height-class depths as physical measurements.
- Foreground events originate only at simulation acceptance. Preserve sequence,
  generation and world-OAM ownership; count foreground commits separately.
  This disabled experiment reserves maximum possible foreground occupancy and
  needs three VBlanks at maximal load. Its 176-block total is unchanged.

## Verification

For engine, content, or runtime changes, run `make test` and the driven
`make playtest playtest-world` checks. Add focused regression coverage for
changed behavior; exercise emitted machine code and actual published VRAM/OAM,
not only host functions. During iteration, a focused suite can be run with:

```sh
python -m unittest discover -s tests -p 'test_columns.py' -v
```

Choose additional checks by the affected behavior:

| Change | Checks |
| --- | --- |
| Art, palettes, HUD, fixtures, or visual composition | `make playtest-art`; inspect actual captures/contact sheets. |
| Movement, doors, combat, actors, or level progression | `make playthrough variants`. |
| Geometry, ray setup, composition, cache, or timing | `make variants wall-reuse motion`; add `make research-tail` for traversal/projection changes. |
| CPU instructions, banking, interrupts, DMA, or publication | Both pinned `make sameboy` and `make mgba` lanes. |

The active coherence oracle is `playtests/v070_sable_capture_pixels.json`.
Preserve its nine exact RGB captures for behavior-preserving changes. Deliberate
visual changes need reviewed before/after captures and an explained oracle
update; retain historical fixtures. Never change expected hashes or weaken
validators merely to make a failing implementation pass.

`playtest` scenarios may inject diagnostic poses. `playthrough` completes the
level through controller input without game-RAM writes. Distinguish these
forms of evidence. Performance claims need reproducible measurements and must
separate full geometry renders from cached sprite/HUD presentations.

`tools/benchmark_motion.py --duration 60` observes CPU T-cycles without patching
ROM code. `make sustained` adds explicit movement assertions and controller-only
completion/restart is available with `tools/playthrough.py --restart`.
Keep the short CI lane; sustained comparisons belong to the manual job.
Preserve immutable baseline/performance evidence in `.render-baselines/`, which
is excluded from `make clean`. Same-snapshot exactness and live controller
performance are separate comparisons. Quality promotion requires
`Q <= (B + P) / 2` for both mean and p95 in every affected scenario, plus
independent expected geometry and reviewed visual changes. Failed experiments
stay disabled with their ROM-bound results; do not relax the gate.

Follow `.github/workflows/ci.yml` for the complete CI sequence; `make qa` and
`make verify` do not cover every lane. Reports must match the current ROM SHA
and configuration. Do not reuse stale evidence or claim CI/hardware checks
that were not run. Documentation-only edits need path/command and diff checks,
not a ROM test rerun.

## Content, documentation, and releases

Author gameplay in `levels/living_world.json`; `levels/two_sentinels.json` is
the multi-actor acceptance scene and `levels/renderer_benchmark.json` is for
research. Preserve compiler validation of spawn clearance, reachability,
door gates, sightlines, and room sizes. Door colour belongs to functional
doors. Follow `docs/SABLE_OUTPOST.md` for art direction and graphics budgets.

Keep changes scoped and preserve existing user edits. Document changes to
memory layout, timing, rendering contracts, and content semantics alongside
the implementation. Preserve versioned research evidence; write new
experiments to `build/` unless intentionally updating a documented dataset.

Keep `.venv/`, `build/`, `dist/`, downloaded cores, ROMs, and release archives
out of commits. `make clean` removes all of `build/`, including locally built
emulator dependencies and setup notes. Use `make preview` for real emulator
captures when updating presentation assets.

For release work, follow `docs/DEVELOPMENT.md` and `tools/package_release.py`.
The packager uses explicit file allowlists and clean-room rebuild/extraction
checks; update those lists when adding required release inputs. Original CGB,
flash-cartridge, and Nintendo boot-ROM validation remain separate from the
project harness and independent emulator checks.
