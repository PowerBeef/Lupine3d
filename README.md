<div align="center">

# Lupine 3D

### Sable Outpost · A first-person game for Game Boy Color

[![CI](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml/badge.svg)](https://github.com/PowerBeef/Lupine3d/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-8ac926.svg)](LICENSE)

[**Download v0.9**](https://github.com/PowerBeef/Lupine3d/releases/tag/v0.9) · [Build](#build-from-source) · [Controls](#how-to-play) · [Release notes](RELEASE_NOTES.md)

<img src="docs/images/lupine3d_preview_4x.png" width="640" alt="Sable Outpost running in the emulator: industrial walls, a Sentinel, shotgun and compact steel HUD">

<sub>160×120 world view · Animated native sprites · 4 MiB MBC5 ROM · CGB only</sub>

</div>

Fight through six sectors of an industrial outpost: clear each one, take what the dead leave, and reach the exit. Lupine 3D renders its first-person world with Game Boy Color tiles and hardware sprites, without a framebuffer or cartridge RAM.

**v0.10 makes the renderer stream:** a full geometry update publishes in one VBlank instead of two or three, because hidden patterns and the hidden map now travel by HBlank DMA while the CPU is still composing, and a sixth sector joins the campaign. v0.9 turned the tech demo into a campaign: five levels behind a title screen, three enemy kinds, two weapons, keycard doors, music, skill settings and written-down continue codes. The release includes the playable ROM, native art sources, generated concept masters, previews and reproducible verification evidence.

## What's new in v0.10

- **HBlank-streamed publication.** The dynamic patterns and the whole hidden tile-number map stream into the hidden bank by HBlank DMA as each column is composed, so the VBlank tail is only the banked masks, attributes, HUD and OAM. A full update no longer spends an LCD interval idle between its pattern stage and its map stage. Every descriptor, packet and VRAM byte is unchanged; see [streamed publication](docs/STREAMED_PUBLICATION.md).
- **Exact engine savings.** The folded compositor writes each column's fifteen map cells from one pointer instead of walking two per row; the column scan keeps its extremes in registers; the depth pass keeps each actor's projection for the draw pass; the wall-key compare and the snapshot copies run eight bytes per counter step. No pixel, packet or allocation order moves.
- **A sixth sector.** Cryo Vault: a warden and a skirmisher above, a keycard hatch, and a sump with a Sentinel and a second skirmisher below, carrying the same compiler certificate as the other five.
- **Measured.** The nine-image tour falls from 866,119 to 674,644 CPU T-cycles per update (−22.1%) and the living-world route from 719,567 to 632,973 (−12.0%) on the host harness; the sustained sixty-second results are in [the test report](docs/TEST_REPORT.md).

## What's new in v0.9

- **A campaign.** Five sectors — Sable Outpost, Coolant Spine, Reactor Gate, Vent Stacks and Signal Deck — each in its own ROM bank and chosen at runtime, rising from one enemy to four. Clearing one shows an intermission with its continue code, kills and time; dying retries the sector you lost; clearing the last one ends the campaign.
- **Continue codes.** The cartridge has no save hardware, so progress is a four-digit code you write down. Select on the title opens code entry.
- **Three enemy kinds and two weapons.** The Sentinel, the quick skirmisher that carries a keycard, and the heavy warden. Select swaps the shotgun for a slug rifle — twice the damage for a long recovery — by streaming its cels into the one pattern window they share.
- **Music.** A title theme, an in-game loop and a victory sting on three channels, with the fourth kept free so gunfire never cuts a bar.
- **Preserved engine contracts.** Deterministic builds, immutable render snapshots, exact wall reuse and bounded graphics publication. The MBC5 bank rule is now checked against the emitted image rather than approximated. Legacy artwork and historical image fixtures remain available.

<img src="docs/images/sable_objective_spaced_states_4x.png" width="640" alt="HUD states: hunt with one enemy remaining, exit with zero enemies, dead and done">

## How to play

Open `Lupine3D_v0.9.gb` in a Game Boy Color emulator with MBC5 support. The monochrome Game Boy is not supported. There is no save system: progress is a continue code you write down.

| Game Boy button | Action |
|---|---|
| D-pad Up / Down | Move forward / backward |
| D-pad Left / Right | Turn |
| A | Fire |
| B | Use a nearby door |
| Select | Swap weapons; on the title, enter a continue code |
| Start | Begin, and continue past a results screen |

The **skull counts living enemies remaining**, not kills. **GOAL / HUNT** means clear the sector; **GOAL / EXIT** means the exit is available. Reach it to finish. Green medical pickups restore health, and a keycard opens the door that wants one — in the sector you found it in. **Left and right on the title** choose one of three skill settings before you press Start.

## Performance and qualification

Active 60-second scenarios measure **6.80–10.27 full geometry updates/s** (v0.9: 5.53–8.15 on the same replays), and the slowest image of the nine-image tour **7.45/s** (v0.9: 6.611/s). Full geometry updates and cached sprite/HUD presentations run at different rates. The target of ten sustained full geometry updates per second is met while turning and missed by less than 0.15/s in two more scenarios; it remains unmet in the other five.

v0.8 deliberately traded some geometry throughput for the larger viewport and animated art. The original half-gains performance criterion was not met; that visual tradeoff was explicitly accepted, and v0.9 inherits it unchanged. Memory, graphics capacity and publication safety limits remain enforced.

Qualification uses the project harness and pinned **SameBoy CGB-0/CGB-E and mGBA** cores, all passing on the released ROM along with 87 frozen independent-witness scenes. It is **emulator-qualified**; physical hardware and an original Nintendo boot ROM have not been tested. Reprojection and the experimental foreground feedback lane remain disabled.

## Build from source

Requires Python 3.10+, Pillow and Make. RGBDS is not required: Python emits the console's SM83 machine code, tables, level data and 2bpp graphics.

```sh
python3 tools/dev_setup.py
source .venv/bin/activate
make build
make test
```

The build writes `build/lupine3d.gb`, symbols, a listing and `build/build_manifest.json`. Builds consume checked-in indexed PNGs and never call image generation or require an image API key.

```sh
make playtest playtest-world playtest-art
make playthrough variants wall-reuse motion
```

| Display profile | World / HUD | Default art |
|---|---|---|
| `slim` — default | 160×120 / 160×24 | Sable, animated |
| `compact` | 160×112 / 160×32 | Sable, animated |
| `legacy` | 160×96 / 160×48 | Historical, static |

For example, `LUPINE3D_DISPLAY=legacy make build` reproduces the beta.6 visual configuration. Rebuild without overrides to restore the current ROM. Project development takes place directly on `main`.

## Explore the project

| Guide | Contents |
|---|---|
| [Documentation index](docs/README.md) | Current guides and historical evidence |
| [Development](docs/DEVELOPMENT.md) | Setup, emulator cores, diagnostics and releases |
| [Architecture](docs/ARCHITECTURE.md) | Rendering, memory, simulation and publication |
| [Campaign](docs/CAMPAIGN.md) | From demo to game: decisions, measured cost and evidence |
| [Sable Outpost art](docs/SABLE_OUTPOST.md) | Visual language, animation sources and budgets |
| [Steel HUD](docs/STEEL_HUD.md) | Layout, objective text and native tile contracts |
| [Verification](docs/TEST_REPORT.md) | Current ROM hash, executed checks and performance |
| [Contributing](CONTRIBUTING.md) | Change requirements and development policy |
| [Agent guidance](AGENTS.md) | Code map and implementation invariants |

Original code and assets use the [MIT License](LICENSE). See [NOTICE.md](NOTICE.md) for attribution and asset provenance.
