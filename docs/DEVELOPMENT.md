# Development and playtesting

## Quick start

Lupine 3D uses a deterministic Python ROM generator instead of RGBDS or GBDK.
Python 3.10+ and Pillow are the only host requirements.

```sh
python3 tools/dev_setup.py
.venv/bin/python tools/build_rom.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/playtest.py
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
| `make research-v3` | Run the retained v0.2.2/v0.3.0 fidelity corpus |
| `make research-atlas` | Regenerate the v0.4 exact boundary atlas |
| `make qa` | Build, test, playtest, and run the fidelity research gate |

## Playtest scenario format

`tools/playtest.py` executes the emitted ROM in `tools/sm83emu.py`. Inputs are
sampled at the ROM's real `main_loop` boundary; each scenario update ends only
after the hidden page has been committed and displayed.

```json
{
  "name": "example",
  "pixel_oracle": "optional_capture_pixels.json",
  "actions": [
    {"pose": [384, 384, 0], "updates": 1, "capture": "start"},
    {"buttons": ["up"], "updates": 4, "capture": "forward"},
    {"buttons": ["right"], "updates": 3, "capture": "turn"},
    {"buttons": ["a"], "updates": 1, "capture": "fire"}
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
- all 160 final pixel descriptors, including exact edge recasts;
- material-event and cast counters;
- generated boundary tile bytes and the complete 384-byte view map;
- dynamic-tile capacity and overflow state;
- one-VBlank GDMA commit safety.

When `pixel_oracle` is present, each named capture is also hashed as raw RGB
pixels and compared with the referenced JSON map. The default coherence tour
uses `playtests/v030_capture_pixels.json`; this makes any visible departure
from the accepted v0.3.0 fidelity fail the playtest independently of PNG
compression metadata.

Outputs include individual PNGs, `playtest.gif`, `contact_sheet.png`, and
`report.json` with per-update cycles, pose, casts, material events, tile count,
commit blocks, and validation results.

The harness models the MBC5 nine-bit ROM-bank register used by the exact
projection/product tables. It remains project-scoped evidence, not a replacement for SameBoy/mGBA and
original Game Boy Color testing. Use `docs/HARDWARE_TEST_CHECKLIST.md` before a
hardware-certified release.
