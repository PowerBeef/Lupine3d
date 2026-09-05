<div align="center">

# Lupine 3D

### A tile-native first-person world for Game Boy Color

[![CI](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml/badge.svg)](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-8ac926.svg)](LICENSE)

[Download beta.6](https://github.com/PowerBeef/Lupine3d/releases/tag/v0.7.0-beta.6) · [Build](#quick-start) · [Controls](#controls) · [Architecture](docs/ARCHITECTURE.md) · [Verification](docs/TEST_REPORT.md)

<img src="docs/images/lupine3d_preview_4x.png" width="640" alt="Lupine 3D Sentinel, steel-walled environment and industrial HUD">

<sub>160×96 viewport · 4 MiB MBC5 cartridge · no framebuffer</sub>

</div>

## Current implementation

**0.7.0-beta.6 — Rendering qualification** improves the Sable Outpost renderer while preserving its reviewed images and gameplay. The playable industrial outpost includes a protected start, animated sliding doors, a Sentinel encounter, hitscan combat, a dropped medkit and a marked exit. The bounded entity system supports up to four Sentinels; the main level uses one, with a separate two-enemy acceptance scene.

The release enables compact folded strips, camera setup computed once per snapshot, smaller save/restore contexts at documented yield boundaries, and exact attribute-padding initialization. Mean full-frame time improves **3.7–7.5%** across the six primary sustained scenarios. Resident free space increases from **3,123 to 5,939 bytes**, preserving the 3,000-byte reserve.

Release packaging preserves the qualified atlas assets. `make atlas-check` verifies both stored profiles against their recorded hashes and exact compositor output before measuring complete diagnostic frames.

Gunmetal structure, muted green machinery and illuminated teal doors give the environment a consistent colour language. Sixteen authored wall fixtures add vents, caged lights, access markers and sector signs. Red-armoured Sentinels, green medkits, a steel shotgun and a clear reticle sit above a dedicated instrument-panel HUD with large health and hostile counts and a literal exit status.

[View the native-resolution art tour](docs/images/sable_outpost.png).

The engine emits SM83 machine code directly from Python. Cartridge tables replace expensive arithmetic, precision rays continue from certified crossings, and door division keeps its working values in CPU registers. Sequential column/event scans keep working values in registers; aligned cartridge records provide coarse and Q14 directions plus exact projection pointers. Native tiles, palettes and objects carry the final image.

| Rendering | World and platform |
|---|---|
| Certified selective Q14 crossing order | Fixed VBlank-rate simulation |
| 80 adaptive samples → 160 physical columns | Timestamped held-state and button-edge queue |
| Corrected Q5 depth and physical segment IDs | Immutable render snapshots in a separate WRAM bank |
| Folded six-row composition, nine stored strip states and full 121-pattern atlas | Shared sliding-door geometry for rays, collision and LOS |
| Masked hardware 8×16 sprites, three size LODs | Four bounded actor slots, depth sorting and OAM admission |
| Per-face palettes and wall-mounted fixture masks | Atomic BG, attributes, HUD and entity publication |
| Exact reuse of unchanged wall views | Independent sprite/HUD updates with retained wall depth |
| Dedicated 78-pattern HUD with a scanline split | Native pixel art; no imported game assets |

### Hangar Breach

A protected airlock leads through a turning corridor into a partitioned combat chamber and an exit wing. Defeat the Sentinel, collect its medkit, open the unlocked exit door and reach the beacon. An optional service branch provides a detour.

**Cyan and white identify working doors.** Neutral steel marks structure; muted green marks machinery. The ceiling and floor stay distinct, and there is no eye-height decorative rail.

The level compiler checks safe spawn clearance, reachability, meaningful door gates, short sightlines and room sizes. Content lives in [living_world.json](levels/living_world.json); [two_sentinels.json](levels/two_sentinels.json) exercises multiple actors.

## How it fits

Upper wall tiles are composed once. Lower rows reuse their patterns with CGB Y-flip and paired floor palettes. Signed BG addressing places world patterns at **$8800–$97FF**. A line-96 STAT interrupt switches to unsigned addressing for the HUD, which occupies otherwise unused bank-0 patterns alongside the separate masked-object pool. See the [visual design and graphics budget](docs/SABLE_OUTPOST.md).

The renderer yields at ray and tile-column boundaries to service queued simulation ticks. It then resumes the same untouched camera/world snapshot. An exact camera/map/door check lets unchanged walls stay in VRAM while new entities and HUD publish independently. Full renders publish all matching data together; larger packets prepare hidden patterns in one VBlank and finish publication in the next.

Wall depth remains Q5; interpolated samples use conservative bounds. Sprite masks operate on individual pixel bits but obtain occlusion from those two-pixel depth samples. This is not arbitrary-precision geometry or unrestricted sprite scaling.

### Measured routes

Each sustained scenario runs for 3,584 LCD intervals, approximately 60 emulated
seconds, with identical controller replays on baseline and candidate ROMs.
CPU T-cycles include engine work, simulation, interrupts, publication waits and
DMA. Every five-second movement window must contain real movement or turning.

| Scenario | Full geometry updates/s | Mean T-cycles/full frame | p95 T-cycles/full frame |
|---|---:|---:|---:|
| Walking | 7.25 | 1,151,487 | 1,264,268 |
| Turning | 9.67 | 866,184 | 983,424 |
| Walking and turning | 9.23 | 906,582 | 1,123,992 |
| Moving fire | 9.23 | 906,582 | 1,123,916 |
| Open door | 6.83 | 1,225,335 | 1,264,160 |
| Closed door | 8.68 | 963,202 | 1,124,568 |
| Two-actor corner arena | 6.52 | 1,283,440 | 1,685,396 |

The **10 sustained full geometry updates/s target remains unmet**. Cached
sprite/HUD updates and experimental foreground publications are counted
separately and never inflate that rate. Trials record zero post-setup game-RAM
writes, input overflow and unsafe GDMA starts. The door-interaction trial and
controller-only completion/restart provide separate functional coverage.

See the [rendering implementation and acceptance evidence](docs/RENDERING_IMPLEMENTATION.md)
for baseline comparisons, memory allocations, replay identities and timing
definitions. Exact output is checked on identical frozen snapshots; faster
rendering can change when live actor poses are sampled.

### Gated experiments

Persistent dynamic-tile caching, four-anchor packets, physical-depth refinement,
Q8.8 actor projection, atomic scanline admission, door-run identity, projection
page compression, near-field precision and foreground feedback are implemented
as individually selectable build paths. They remain disabled where performance
or quality gates failed. Intentional quality changes must retain at least half
the accepted performance gain for both mean and p95 frame time. The default
keeps the current Q5 depth model and reviewed visual oracle; reprojection also
remains disabled.

## Quick start

Requirements: Python 3.10+, Pillow and `make`.

```sh
python3 tools/dev_setup.py
source .venv/bin/activate
make build
make test
make playtest playtest-world
make playthrough variants
make wall-reuse motion
```

Open **`build/lupine3d.gb`** in a Game Boy Color emulator with MBC5 support.

```sh
# External cores must first be built at the documented pinned revisions.
make sameboy SAMEBOY_DIR=/absolute/path/to/SameBoy
make mgba MGBA_DIR=/absolute/path/to/mgba
```

See [Development](docs/DEVELOPMENT.md) for core build commands, content tooling and diagnostic switches.

Development takes place directly on **`main`**, without development branches or
Git worktrees. Optional sustained comparisons run with `make sustained`; they
also have a separate manual CI job.

## Controls

| Button | Action |
|---|---|
| D-pad Up / Down | Move forward / backward |
| D-pad Left / Right | Turn |
| A | Fire |
| B | Interact with the door ahead |
| Start | Restart after death or level completion |

## Verification and limits

**137 automated tests**, nine unchanged reviewed RGB fixtures, 53 frozen-scene comparisons, a six-view art tour and a 24,384-view geometry-tail scan protect the implementation. Fifty-one additional complete-world witnesses cover occlusion, corners, doors, actor motion and admission. Controller-only completion and restart pass without teleporting or changing game RAM; the controller reads state to steer, so this is functional verification rather than a blind human-navigation study.

Validation checks the actual published sprite patterns, OAM banks and viewport VRAM, alongside host geometry and staging buffers. All 290 wall-key bytes are tested for invalidation; cached updates preserve the displayed background exactly.

The exact candidate passes independent SameBoy CGB-0/CGB-E and mGBA startup/controller lanes. All 51 frozen worlds agree with the project harness on those lanes for the production, quality and near-field configurations. Releases include checksums and a source bundle that is rebuilt and tested after extraction. Check the CI badge for remote run status.

**No physical CGB or flash cartridge is available.** Development and releases
use emulator qualification, with hardware status explicitly untested. Neither
emulator lane uses the Nintendo boot ROM. Physical testing is optional future
work and does not block releases. Optional ±4-pixel turning reprojection remains
disabled; its visual benefit has not been accepted.

| Document | Purpose |
|---|---|
| [Rendering implementation](docs/RENDERING_IMPLEMENTATION.md) | Current defaults, gated experiments, sustained measurements and qualification |
| [Agent guidance](AGENTS.md) | Main-only development, architecture contracts and verification commands |
| [Implementation status](docs/OVERHAUL_IMPLEMENTATION.md) | Delivered overhaul items and exactness boundaries |
| [Sable Outpost](docs/SABLE_OUTPOST.md) | Current art direction, wall fixtures and HUD |
| [Gameplay performance](docs/RUNTIME_PERFORMANCE.md) | Implementation steps, exactness proof and measured results |
| [Streaming columns and prepared rays](docs/COLUMN_PERFORMANCE.md) | Historical beta.5 rendering and motion evidence |
| [Wall reuse and combat latency](docs/WALL_REUSE.md) | Exact caching, independent sprite publication and timing |
| [Architecture](docs/ARCHITECTURE.md) | Cartridge, memory, simulation and publication |
| [Test report](docs/TEST_REPORT.md) | Candidate hash, measured evidence and limitations |
| [Hardware checklist](docs/HARDWARE_TEST_CHECKLIST.md) | Optional procedure for future physical hardware access |

Code and original assets use the [MIT License](LICENSE). See [NOTICE.md](NOTICE.md) for naming and asset details.
