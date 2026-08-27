# Lupine 3D

[![CI](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml/badge.svg)](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/PowerBeef/Lupine3d?display_name=tag)](https://github.com/PowerBeef/Lupine3d/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Lupine 3D** is an original first-person raycasting engine built for the real **Game Boy Color** CPU, memory map, tile renderer, VRAM banks, DMA controller, OAM, joypad, and audio hardware. It takes inspiration from the broad early-1990s corridor-shooter format, but contains no Wolfenstein 3D source, artwork, maps, sounds, names, or other game assets.

Version **0.4.0** preserves the v0.3.0 hybrid 160-column image byte-for-byte while using HRAM, an exact boundary-tile atlas, and banked MBC5 arithmetic tables to reduce the driven renderer cost by 18.61%.

![Lupine 3D preview](docs/images/lupine3d_preview_4x.png)

## Status

The repository builds a deterministic 4 MiB CGB-only MBC5 ROM and passes **25 automated tests**, including the frozen v0.1.0 regression suite. A scenario-driven playtest harness executes the emitted SM83 program, models MBC5 bank switches and GDMA, drives joypad input, renders BG/OBJ output, and checks descriptors, generated tiles, and nine complete captures against independent/frozen oracles.

The ROM has **not yet been physically tested on an original Game Boy Color** in this environment. Independent emulator checks and a flash-cartridge run remain required before calling it hardware-certified. Follow `docs/HARDWARE_TEST_CHECKLIST.md`.

## What v0.4.0 implements

- 160×96 first-person viewport
- **80 adaptive geometry samples reconstructed into 160 physical columns**
- Exact signed-error grid DDA with no general division in the traversal loop
- 1,024-direction quantized render-vector table
- Camera-plane-correct field-of-view offsets and fish-eye correction
- Q5 distance projection through an exhaustive, exact banked-ROM result table
- Correct X/Y wall-side identity and directional light/shadow styles
- Quarter-interval subcolumn synthesis with exact recasts at face discontinuities
- World-anchored face creases and along-cell seams
- Projected-run door frames and centre spine with material LOD
- Phase-free base materials with exact X/Y side lighting
- One-row top lip and floor-contact shadow on generated silhouette tiles
- Automated prohibition of full-width contrasting wall bands
- 41 mandatory adaptive anchors with exact midpoint fallback at unsafe spans
- 80 compact per-column descriptors: top edge, style, face identity, and along-face cell
- Hybrid one-/two-pixel boundary microstrips: identical pairs retain the fast path
- Static dark-mask seam atlas for full-interior rows
- Corpus-trained exact boundary atlas with 255 signatures and 121 mirrored VRAM tiles
- HRAM hot-state ABI and sequential packed DDA direction records
- Shared player-fraction boundary setup across every cast in an update
- Exact 64 KiB DDA product table in banked cartridge ROM
- Maximum 96 generated boundary tiles per frame
- One-fresh-VBlank hidden-page commit
- Player movement, turning, backward movement, point collision, doors, firing, HUD, weapon, crosshair, muzzle flash, and pulse-channel sound
- CGB double-speed mode
- 4 MiB MBC5 cartridge layout with no external RAM or coprocessor

## Controls

| Control | Action |
|---|---|
| D-pad Up | Move forward |
| D-pad Down | Move backward |
| D-pad Left / Right | Turn |
| A | Fire; sound and muzzle flash |
| B | Open the door directly ahead |

## Measured renderer results

The v0.3 stress corpus contains **24,384 views** and **3,901,440 physical-column comparisons**. Both versions below were remeasured against the same floating camera-plane oracle.

| Measurement | v0.2.2 | v0.3.0 |
|---|---:|---:|
| Mean physical wall-top error | 0.334 px | **0.243 px** |
| P95 wall-top error | 1.256 px | **0.794 px** |
| P99 wall-top error | 1.953 px | **1.136 px** |
| Wrong visible wall segment | 0.384% | **0.256%** |
| Wrong material | 0.0322% | **0.0209%** |
| Mean casts per view | 44.944 | **45.835** |
| Mean dynamic tiles | — | **29.706** |
| Maximum dynamic tiles | — | **64 / 96** |
| Overflow views | — | **0** |

v0.4.0 intentionally leaves those fidelity numbers unchanged. Its performance
comparison uses the same 27-update driven route and frozen capture poses:

| Measurement | v0.3.0 | v0.4.0 | Change |
|---|---:|---:|---:|
| Mean cycles/update | 1,118,243 | **910,143** | **-18.61%** |
| Maximum cycles/update | 1,264,820 | **1,124,736** | **-11.08%** |
| Minimum updates/s | 6.632 | **7.458** | **+12.45%** |
| Exact capture pixels | reference | **9 / 9** | unchanged |

The 27-update driven coherence tour now averages **910,143 cycles/update**, down from 1,118,243 in v0.3.0. It never falls below **7.458 updates/s** (up from 6.632), uses at most 54 dynamic tiles and 59 total casts, matches all nine v0.3.0 capture hashes, and records zero unsafe GDMA starts. The renderer remains framebuffer-free and keeps the 120-block single-VBlank hard cap.

These numbers are mathematical and project-harness evidence, not original-hardware certification.

## Rendering pipeline

```text
player pose
  → 41 mandatory signed-error DDA anchors
  → validate each odd-column span
  → interpolate safe midpoint or cast exact fallback
  → 80 {top, style, face, along} descriptors
  → Q5 projection + quarter-interval physical synthesis
  → exact recasts beside detected face discontinuities
  → 160 {top, style, face, along} pixel descriptors
  → world-face seams, door runs, and projected-height LOD
  → classify 20×12 viewport tile cells
  → reuse static ceiling/floor/seam and exact boundary-atlas tiles
  → compose remaining cells with hybrid one-/two-pixel microstrips
  → dynamic tile dictionary + 384-byte hidden tile map
  → one fresh-VBlank GDMA commit
  → flip the visible BG map after both transfers
```

The two visible pages use separate CGB tile-data banks. Tile-number maps always live in VRAM bank 0, while the corresponding CGB attribute maps live in bank 1 and select the correct tile-data bank for each page.

See `docs/PERFORMANCE_V4.md` for the optimization plan, rejected experiments, and checkpoint measurements; `docs/RENDERER_V3.md` for the geometry/material pipeline; and `docs/DEVELOPMENT.md` for the driven harness.

## Build and verify

The deterministic ROM builder itself uses Python 3.10 or newer and the standard library. The harness previews and comparison images also use Pillow.

```sh
git clone https://github.com/PowerBeef/Lupine3d.git
cd Lupine3d
```

```sh
python3 tools/dev_setup.py
make qa
make preview
make package
```

Or run the stages directly:

```sh
.venv/bin/python tools/build_rom.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/playtest.py
.venv/bin/python research/rendering_v3_lab.py
.venv/bin/python tools/release_check.py
```

Primary outputs:

- `build/lupine3d.gb` — ready-to-run CGB ROM
- `build/lupine3d.sym` — emitted symbols
- `build/lupine3d.lst` — generated listing
- `build/build_manifest.json` — layout, checksums, and renderer metadata
- `build/verification_report.json` — structural, harness, research, and baseline comparison
- `build/lupine3d_preview_4x.png` — enlarged still preview
- `build/lupine3d_preview.gif` — scripted gameplay preview
- `build/playtest/coherence_tour/` — driven screenshots, GIF, contact sheet, and telemetry
- `research/results/tile_atlas_v4.json` — exact-atlas corpus coverage and asset hashes
- `research/results/rendering_v3_results.json` — v0.2.2/v0.3.0 fidelity study retained by v0.4.0
- `research/results/rendering_v3_before_after.png` — ROM-executed comparison sheet
- `research/results/geometry_v2_results.json` — geometry and bandwidth measurements
- `research/results/geometry_v2_accuracy.csv` — compact accuracy table
- `research/results/geometry_v2_comparison.png` — v0.1/v0.2/reference comparison
- `build/clean_room_verification.json` — extracted-archive rebuild evidence
- `dist/Lupine3D_v0.4.0_*` files — named release bundle, clean-room evidence, reports, previews, and SHA-256 manifest

Every push and pull request runs the ROM regression suite and driven pixel
oracle in GitHub Actions. Pushing a version tag such as `v0.4.0` regenerates
the research assets, performs both clean-room rebuilds, and publishes the
verified ROM and source bundle on the
[Releases page](https://github.com/PowerBeef/Lupine3d/releases).

The exact v0.1.0 generator remains in `tools/build_rom_v1.py`. Its regression-oracle ROM SHA-256 is:

```text
0b5794c93b43b38a0dd2a76cf4e289f0317dd9b10314632ff366402ecd37fa00
```

## Running the ROM

### Independent emulator

Load `build/lupine3d.gb` in a CGB-capable emulator. Cross-check it in at least two maintained emulators, with one configured for strict timing or diagnostics where available. The included harness is intentionally project-scoped and is not independent validation.

### Original Game Boy Color

Copy the ROM to a flash cartridge that supports **4 MiB MBC5** images, then boot it on an original Game Boy Color. The header is CGB-only (`$0143 = $C0`), MBC5 (`$0147 = $19`), with no cartridge RAM; monochrome Game Boy models are not supported.

## Editing the map

The demo map comes from `make_map()` in `tools/build_rom_v1.py` and is re-exported by the v0.4 builder. The 16×16 world must remain enclosed.

- `0` — empty space
- `1` — ordinary wall
- `2` — technology/stone wall
- `3` — openable door

The player begins at Q8.8 coordinate `(1.5, 1.5)`, facing east.

## Known limitations

- No enemy/entity renderer, AI, damage, pickups, or level progression
- Face/cell material grammar rather than arbitrary sampled wall textures
- One-level adaptive reconstruction; unsafe odd columns fall back to exact casting
- Point collision rather than a player-radius model
- Doors disappear immediately instead of animating
- No floor or ceiling texture casting
- No save system
- Project harness is not an independent emulator
- Original-hardware validation remains pending

## Technical references

- Pan Docs: <https://gbdev.io/pandocs/>
- CGB VRAM DMA: <https://gbdev.io/pandocs/CGB_Registers.html#ff51ff55--hdma1hdma5-cgb-mode-only-vram-dma-registers>
- Tile data and tile maps: <https://gbdev.io/pandocs/Tile_Data.html>
- OAM and sprites: <https://gbdev.io/pandocs/OAM.html>
- CGB speed switching: <https://gbdev.io/pandocs/CGB_Registers.html#ff4d--key1-cgb-mode-only-prepare-speed-switch>
- SM83 instruction table: <https://gbdev.io/gb-opcodes/optables/>

## License and naming

Code and original assets are released under the MIT License. “Lupine 3D” is an independent project name. See `NOTICE.md` and `LICENSE`.
