# Development and playtesting

## Quick start

Lupine 3D uses a deterministic Python ROM generator instead of RGBDS or GBDK.
Python 3.10+ and Pillow are the only host requirements.

```sh
python3 tools/dev_setup.py
.venv/bin/python tools/build_rom.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/playtest.py
.venv/bin/python tools/playtest.py --scenario playtests/living_world.json \
  --output-dir build/playtest/living_world
```

On an offline machine that already exposes Pillow to the system interpreter:

```sh
python3 tools/dev_setup.py --offline
```

The setup command creates `.venv`, verifies Pillow, builds the 4 MiB CGB-only
MBC5 ROM,
and runs the main engine regression module. The generated environment is local
and is intentionally excluded from release archives.

## Make targets

| Target | Purpose |
|---|---|
| `make setup` | Create and smoke-test `.venv` |
| `make build` | Emit ROM, symbols, listing, and manifest |
| `make test` | Run ROM/host, gameplay, DMA, and v0.1 regression tests |
| `make playtest` | Drive the default gameplay scenario and capture artifacts |
| `make playtest-world` | Drive Sentinel combat, pickup, and level completion |
| `make research-v3` | Compare the current renderer with the retained fidelity baseline |
| `make research-atlas` | Regenerate the v0.4 exact boundary atlas |
| `make research-atlas-entity` | Regenerate the 80-pattern entity-profile atlas |
| `make research-atlas-all` | Regenerate both scene-level VRAM profiles |
| `make research-atlas-pareto` | Build and drive candidate atlas sizes without changing production assets |
| `make research-tail` | Scan and preserve rare geometry-tail failures |
| `make qa` | Build, test, playtest, and run the fidelity research gate |

## Playtest scenario format

`tools/playtest.py` executes the emitted ROM in `tools/sm83emu.py`. Inputs are
sampled at the main-loop boundary and every VBlank. Rising edges are retained
until the next stable simulation step; each scenario update ends only after
the hidden page has been committed and displayed.

```json
{
  "name": "example",
  "world_mode": "living",
  "pixel_oracle": "optional_capture_pixels.json",
  "actions": [
    {"pose": [384, 384, 0], "updates": 1, "capture": "start"},
    {"buttons": ["up"], "updates": 4, "capture": "forward"},
    {"buttons": ["right"], "updates": 3, "capture": "turn"},
    {"buttons": ["a"], "updates": 1, "capture": "fire",
     "expect": {"sentinel_health": 2}}
  ]
}
```

Buttons are `up`, `down`, `left`, `right`, `a`, and `b`. A `pose` is an
optional diagnostic teleport in Q8.8 coordinates followed by an 8-bit angle.
It is useful for deterministic visual coverage; ordinary actions remain driven
through the ROM joypad routine.

Run a custom scenario with:

```sh
.venv/bin/python tools/playtest.py \
  --scenario playtests/my_route.json \
  --output-dir build/playtest/my_route \
  --record-all
```

Every update checks:

- 80-ray adaptive descriptors against the host oracle;
- all 80 corrected-depth and surface-segment certificates;
- all 160 final pixel descriptors, including exact edge recasts;
- material-event and cast counters;
- generated boundary tile bytes and the complete 384-byte view map;
- dynamic-tile capacity and overflow state;
- one-VBlank GDMA commit safety.
- total and per-scanline OAM limits;
- optional authored world-state expectations.

When `pixel_oracle` is present, each named capture is also hashed as raw RGB
pixels and compared with the referenced JSON map. The default coherence tour
uses `playtests/v030_capture_pixels.json`; this makes any visible departure
from the accepted v0.3.0 fidelity fail the playtest independently of PNG
compression metadata.

Outputs include individual PNGs, `playtest.gif`, `contact_sheet.png`, and
`report.json` with per-update cycles, pose, casts, material events, tile count,
commit blocks, and validation results.

The harness models the MBC5 nine-bit ROM-bank register used by the exact
projection/product tables, VBlank/STAT IF generation, interrupt dispatch, EI delay,
RETI, live joypad reads, OAM DMA, and the hardware object budgets. It remains project-scoped evidence, not a replacement for SameBoy/mGBA and
original Game Boy Color testing. Use `docs/HARDWARE_TEST_CHECKLIST.md` before a
hardware-certified release.

## Builder boundaries

`tools/build_rom.py` is the stable compatibility facade and final linker. The
current implementation is split under `tools/lupine3d_v4/`:

- `layout.py`: hardware addresses, HRAM ABI, cartridge and renderer constants;
- `resources.py`: tables, palettes, tiles, and generated resource bytes;
- `reference.py`: host geometry and compositor oracles;
- `emitter.py`: emitted SM83 routines.
- `levels.py`: authored JSON validation, compact headers, and segment IDs;
- `living_world.py`: OAM, entity projection, AI, collision, doors, and reprojection.

The active content lives in `levels/living_world.json`. Override it at build
time with `LUPINE3D_LEVEL=/absolute/path/to/level.json`; the resident slice
supports one to four authored material-3 doors, one Sentinel, one Sentinel
drop, and one empty exit cell. Current `lupine-level-v2` gameplay levels also
require safe-spawn metadata and one Sentinel-locked exit door.

`make playtest` intentionally rebuilds with `levels/renderer_benchmark.json`
before checking the nine frozen pixel oracles. `make playtest-world` rebuilds
the normal Hangar Breach ROM. This isolates renderer regression evidence from
deliberate gameplay-map revisions.

Enable the opt-in reprojection variant with `LUPINE3D_REPROJECTION=1`. The
test suite builds this variant in a fresh subprocess so the environment-backed
compile flag cannot be masked by Python module caching.

Research and tests should continue importing `build_rom`; the facade preserves
the established public API while the implementation modules remain narrow.

## Exceptional-tail workflow

`research/tail_failure_lab.py` scans the full 24,384-view corpus and writes
JSON, CSV, and a comparison sheet. Each retained event includes the pose,
physical column, expected and actual segment identities, top values, material,
cast counters, and local map neighborhood. The regression suite also freezes
one known 41-pixel occlusion-discontinuity case. A full-corpus narrow-boundary
experiment changed only one of 3,901,440 columns, so that heuristic is not in
the runtime; future proposals must beat the retained corpus rather than one
headline maximum.
