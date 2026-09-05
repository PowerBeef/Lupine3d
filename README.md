<div align="center">

# Lupine 3D

### A tile-native first-person world for Game Boy Color

[![CI](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml/badge.svg)](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-8ac926.svg)](LICENSE)

[Build](#quick-start) · [Controls](#controls) · [Architecture](docs/ARCHITECTURE.md) · [Verification](docs/TEST_REPORT.md)

<img src="docs/images/lupine3d_preview_4x.png" width="640" alt="Lupine 3D Sentinel, steel-walled environment and industrial HUD">

<sub>160×96 viewport · 4 MiB MBC5 cartridge · no framebuffer</sub>

</div>

## Current implementation

**0.7.0-beta.2 — Sable Outpost** is a playable industrial outpost with a protected start, animated sliding doors, a Sentinel encounter, hitscan combat, a dropped medkit and a marked exit. The bounded entity system supports up to four Sentinels; the main level uses one, with a separate two-enemy acceptance scene.

Gunmetal structure, muted green machinery and illuminated teal doors give the environment a consistent colour language. Sixteen authored wall fixtures add vents, caged lights, access markers and sector signs. Red-armoured Sentinels, green medkits, a steel shotgun and a clear reticle sit above a dedicated instrument-panel HUD with large health and hostile counts and a literal exit status.

[View the native-resolution art tour](docs/images/sable_outpost.png).

The engine emits SM83 machine code directly from Python. Cartridge tables replace expensive arithmetic, while native tiles, palettes and objects carry the final image.

| Rendering | World and platform |
|---|---|
| Certified selective Q14 crossing order | Fixed VBlank-rate simulation |
| 80 adaptive samples → 160 physical columns | Timestamped held-state and button-edge queue |
| Corrected Q5 depth and physical segment IDs | Immutable render snapshots in a separate WRAM bank |
| Folded six-row composition and full 121-pattern atlas | Shared sliding-door geometry for rays, collision and LOS |
| Masked hardware 8×16 sprites, three size LODs | Four bounded actor slots, depth sorting and OAM admission |
| Per-face palettes and wall-mounted fixture masks | Atomic BG, attributes, HUD and entity publication |
| Dedicated 78-pattern HUD with a scanline split | Native pixel art; no imported game assets |

### Hangar Breach

A protected airlock leads through a turning corridor into a partitioned combat chamber and an exit wing. Defeat the Sentinel, collect its medkit, open the unlocked exit door and reach the beacon. An optional service branch provides a detour.

**Cyan and white identify working doors.** Neutral steel marks structure; muted green marks machinery. The ceiling and floor stay distinct, and there is no eye-height decorative rail.

The level compiler checks safe spawn clearance, reachability, meaningful door gates, short sightlines and room sizes. Content lives in [living_world.json](levels/living_world.json); [two_sentinels.json](levels/two_sentinels.json) exercises multiple actors.

## How it fits

Upper wall tiles are composed once. Lower rows reuse their patterns with CGB Y-flip and paired floor palettes. Signed BG addressing places world patterns at **$8800–$97FF**. A line-96 STAT interrupt switches to unsigned addressing for the HUD, which occupies otherwise unused bank-0 patterns alongside the separate masked-object pool. See the [visual design and graphics budget](docs/SABLE_OUTPOST.md).

The renderer yields at ray and tile-column boundaries to service queued simulation ticks. It then resumes the same untouched camera/world snapshot. Completed frames publish all matching data together; larger packets prepare hidden patterns in one VBlank and finish publication in the next.

Wall depth remains Q5; interpolated samples use conservative bounds. Sprite masks operate on individual pixel bits but obtain occlusion from those two-pixel depth samples. This is not arbitrary-precision geometry or unrestricted sprite scaling.

### Measured routes

Project-harness CPU cycles include publication waits.

| Result | Coherence tour | Combat diagnostic |
|---|---:|---:|
| Mean cycles/update | 919,079 | 1,243,063 |
| Maximum cycles/update | 1,265,284 | 1,967,352 |
| Minimum visual updates/s | 6.63 | 4.26 |
| Peak dynamic tiles | 18 / 96 | 24 / 96 |
| Peak objects per scanline | 4 / 10 | 7 / 10 |
| Unsafe GDMA starts | 0 | 0 |

Simulation cadence and displayed frame rate are different: controls are sampled each VBlank, but new geometry appears only when a complete render is ready. This beta prioritizes correctness, physical interaction and entity support; combat rendering still needs more timing headroom.

## Quick start

Requirements: Python 3.10+, Pillow and `make`.

```sh
python3 tools/dev_setup.py
make build
make test
make playtest playtest-world
make playthrough variants
```

Open **`build/lupine3d.gb`** in a Game Boy Color emulator with MBC5 support.

```sh
# External cores must first be built at the documented pinned revisions.
make sameboy SAMEBOY_DIR=/absolute/path/to/SameBoy
make mgba MGBA_DIR=/absolute/path/to/mgba
```

See [Development](docs/DEVELOPMENT.md) for core build commands, content tooling and diagnostic switches.

## Controls

| Button | Action |
|---|---|
| D-pad Up / Down | Move forward / backward |
| D-pad Left / Right | Turn |
| A | Fire |
| B | Interact with the door ahead |
| Start | Restart after death or level completion |

## Verification and limits

**72 automated tests**, nine reviewed RGB fixtures, a six-view art tour, a 24,384-view geometry-tail scan, two-actor admission checks and a controller-only level completion protect the implementation. The latter completes in 226 verified updates without teleporting or changing game RAM; it reads state to steer, so it is not a blind human-navigation study.

The combat diagnostic averages 1.287 million CPU cycles per update, with its slowest view at approximately 3.98 visual updates/s. The added artwork has a measured cost; controls and simulation continue at VBlank cadence.

The exact candidate passes independent SameBoy CGB-0/CGB-E and mGBA startup/controller lanes. CI is configured to repeat them; local results are not a claim that a new GitHub CI run has executed.

**Original CGB and flash-cartridge testing remains pending.** Neither emulator lane uses the Nintendo boot ROM. Optional ±4-pixel turning reprojection remains disabled: it shifts published world sprites with the BG, but extends edge tiles rather than rendering new guard geometry. Its LCD behavior and perceptual benefit need hardware/user evaluation.

| Document | Purpose |
|---|---|
| [Implementation status](docs/OVERHAUL_IMPLEMENTATION.md) | Delivered overhaul items and exactness boundaries |
| [Sable Outpost](docs/SABLE_OUTPOST.md) | Current art direction, wall fixtures and HUD |
| [Architecture](docs/ARCHITECTURE.md) | Cartridge, memory, simulation and publication |
| [Test report](docs/TEST_REPORT.md) | Candidate hash, measured evidence and limitations |
| [Hardware checklist](docs/HARDWARE_TEST_CHECKLIST.md) | Physical acceptance procedure |

Code and original assets use the [MIT License](LICENSE). See [NOTICE.md](NOTICE.md) for naming and asset details.
