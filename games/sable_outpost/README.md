# Sable Outpost

<img src="../../docs/images/lupine3d_preview_4x.png" width="480" alt="Sable Outpost: textured vent walls near and far, a Sentinel, the shotgun and the steel HUD">

The showcase game of the [Lupine 3D](../../README.md) engine: three episodes
of six sectors, from a surface outpost down into the reactor and up the
signal spire. Clear each sector, take what the dead leave, and reach the
exit. It is the game the engine's evidence (the regression suite, the
controller route, the pinned emulator cores, the performance measurements)
is recorded on, and it uses every feature a game can use.

**Download:** `SableOutpost_v0.12.gb` from the
[v0.12 release](https://github.com/PowerBeef/Lupine3d/releases/tag/v0.12)
(its cartridge header reads `SABLE OUTPOST`). To build it: `python tools/lupine.py build` writes `build/lupine3d.gb` (the showcase
is the engine's default game).

## How to play

Open the ROM in a Game Boy Color emulator with MBC5 support (the original
Game Boy is not supported). There is no save: progress is a continue code
you write down.

| Button | Action |
|---|---|
| D-pad up / down | move forward / back |
| D-pad left / right | turn |
| A | fire |
| B | open a nearby door |
| Select | switch to the next weapon you own; on the title, enter a continue code |
| Start | begin, and continue past a screen |

The **skull counts the enemies still alive**. **GOAL / HUNT** means clear
the sector; **GOAL / EXIT** means the exit is open: reach it. Medkits restore
health, and a keycard opens the doors that want one, in the sector you found
it. **Left and right on the title** choose one of three skills.

## The campaign

| Episode | Sectors | Theme |
|---|---|---|
| Sable Outpost | Sable Outpost, Coolant Spine, Reactor Gate, Vent Stacks, Signal Deck, Cryo Vault | `outpost`: cool steel, cyan doors |
| Reactor Deep | Coolant Intake, Pump Gallery, Turbine Hall, Coolant Dark, Control Gallery, Reactor Heart (a boss) | `reactor`: rust and amber |
| Signal Spire | Antenna Base, Relay Deck, Hull Walk, Signal Vault, Transmitter Ring, Spire Crown (a boss) | `spire`: pale blue and violet |

Four enemy kinds (the Sentinel, the fast skirmisher that carries keycards,
the heavy warden, and a boss), four weapons that arrive by episode (the
shotgun and slug rifle, the arc lance, the pulse carbine), and a screen at
each episode's opening and close.

## What it shows of the engine

Each feature is data in this folder, read by the engine:

| In `games/sable_outpost/` | The engine feature | Handbook |
|---|---|---|
| `game.json` `episodes`, `levels/` | 18 levels in three episodes, continue codes, episode screens | [episodes](../../docs/how-to/episodes-and-progression.md), [levels](../../docs/how-to/add-a-level.md) |
| `kinds` | four enemy kinds in three palettes, a boss that reuses the Sentinel's | [enemies](../../docs/how-to/enemies.md) |
| `weapons` | four weapons owned by episode | [weapons](../../docs/how-to/weapons.md) |
| `themes`, `textures/` | three themes over seven wall textures, the most the engine holds | [themes](../../docs/how-to/themes-and-palettes.md), [textures](../../docs/how-to/wall-textures.md) |
| `art/` | the Sentinel's twelve animated frames at three distances, the steel HUD and helmet, drops, fixtures | [sprites and HUD](../../docs/how-to/sprites-and-hud.md) |
| `screens.json` | nine screens, the episodes' among them | [screens](../../docs/how-to/screens.md) |
| `audio/` | three songs and nine effects | [music and sound](../../docs/how-to/music-and-sound.md) |
| `playtests/`, `snapshots/` | three driven tours and five golden suites | [test your game](../../docs/how-to/test-your-game.md) |

It is also the only game that builds the engine's historical `compact` and
`legacy` display profiles, which the engine keeps as regression contracts.

## Its own documents

- [Campaign](docs/campaign.md): from tech demo to game, and what each decision cost.
- [Art direction](docs/art.md) and the [steel HUD](docs/steel-hud.md): the look, the sources and the budgets.
- [Weapons](docs/weapons.md): how the four weapons are rendered from 3D models.
- `art/tools/`: the offline tools that made the weapon sheets and adapted the HUD art. They make PNGs; no build runs them.
