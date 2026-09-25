# Sable Outpost

<img src="../../docs/images/lupine3d_preview_4x.png" width="480" alt="Sable Outpost: textured vent walls near and far, a Sentinel, the shotgun and the steel HUD">

*Something answered.*

The Line is the chain of relay stations that carries every voice between
the frontier colonies and home. Sable Outpost, sunk into the ice of the
black moon Sable, is its last and deepest ear. Nine days ago the deep bore
under its reactor broke into a hollow, and something down there was
already transmitting on the station's command band. The security frames
stopped taking orders. The crew went down. You are a Linewalker, the
Line's lone repair marshal, in an armoured helmet too old to hear the call:
go in, find what the station heard, and cut the uplink before the Spire
sends it down the Line.

Sable Outpost is the showcase game of the [Lupine 3D](../../README.md)
engine: eighteen sectors in three episodes, from the outpost's decks down
into the reactor and up the signal spire. Every room holds something: a
fight, a card, ammunition, armour, a trap. It is the game the engine's
evidence (the regression suite, the controller route, the pinned emulator
cores, the performance measurements) is recorded on, and it uses every
feature a game can use.

**Download:** `SableOutpost_v0.13.gb` from the
[v0.13 release](https://github.com/PowerBeef/Lupine3d/releases/tag/v0.13)
(its cartridge header reads `SABLE OUTPOST`). To build it:
`python tools/lupine.py build` writes `build/lupine3d.gb` (the showcase is
the engine's default game).

## How to play

Open the ROM in a Game Boy Color emulator with MBC5 support (the original
Game Boy is not supported). There is no save: after every sector the debrief
gives a continue code to write down, and Select on the title enters one.

| Button | Action |
|---|---|
| D-pad up / down | move forward / back |
| D-pad left / right | turn |
| B + left / right | strafe |
| A | fire |
| B | open a door in front of you |
| Select | switch to the next weapon you own; on the title, enter a continue code |
| Start | begin, and continue past a screen (hold it to page through the story) |

Clear every enemy in a sector and reach the exit. The **skull** counts the
enemies still alive; **GOAL / HUNT** means clear the sector and **GOAL /
EXIT** means the exit is open. Beside the health, a **shield** shows while
you have armour, two small digits count the **ammunition** of the weapon in
hand, and a **card** shows for each key you hold. Left and right on the
title choose one of three skills.

Whatever you carry at the end of a sector - health (at least 50), armour,
ammunition and any weapon you found - comes with you into the next. The
debrief shows the code, your kills, the time and the share of the sector's
items you took.

### What you will find

| Item | What it does |
|---|---|
| Stim, medkit | +10 and +25 health; they stay on the floor while you are at full health |
| Armour | +50; it takes half of every hit while it lasts |
| Slugs | six rounds for the slug rifle |
| Cells | twenty cells for the arc lance and the pulse carbine |
| Amber card, teal card | open the doors of their colour in the sector you found them |
| Weapon case | the arc lance or pulse carbine, before the episode that issues it |

Some doors open only from somewhere else: step on the right spot (often
where a card lies) and a door behind you opens. Expect company.

### What you will fight

| Enemy | |
|---|---|
| **Sentinel** | the station's security frame: steady, and it hits hard up close |
| **Hound** | fast and weak; some carry a card |
| **Warden** | heavy, and it shoots: a whine as it raises its arm is your warning to break its line of sight |
| **Overseer** | the command frame that holds the last sector of each episode |

### What you carry

| Weapon | |
|---|---|
| Shotgun | never runs dry |
| Slug rifle | twice the damage, slower, uses slugs |
| Arc lance | four times the damage, very slow, four cells a shot (issued from sector 7) |
| Pulse carbine | twice the damage, fast, a cell a shot (issued from sector 13) |

A dry weapon clicks and hands you back the shotgun.

## The campaign

| Episode | Sectors | Theme |
|---|---|---|
| Sable Outpost | Landing Deck, Coolant Spine, Reactor Gate, Vent Stacks, Signal Deck, Cryo Vault (a boss) | `outpost`: cool steel, cyan doors |
| Reactor Deep | Coolant Intake, Pump Gallery, Turbine Hall, Coolant Dark, Control Gallery, Reactor Heart (a boss) | `reactor`: rust and amber |
| Signal Spire | Antenna Base, Relay Deck, Hull Walk, Signal Vault, Transmitter Ring, Spire Crown (a boss) | `spire`: pale blue and violet |

A prologue and a page at each turn of the episodes tell the story, each
sector ends with a page of Chief Engineer Oda's log, the ending closes it,
and eight songs share one leitmotif. [The campaign document](docs/campaign.md) says what each sector
asks of you.

## What it shows of the engine

Each feature is data in this folder, read by the engine:

| In `games/sable_outpost/` | The engine feature | Handbook |
|---|---|---|
| `game.json` `episodes`, `levels/` | 18 levels in three episodes, continue codes, carry-over, episode screens | [episodes](../../docs/how-to/episodes-and-progression.md), [levels](../../docs/how-to/add-a-level.md) |
| `items`, `ammo`, `keys`, level `items` and `triggers` | nine item types, two ammunition pools, two card colours, remote doors and their triggers | [level format](../../docs/reference/level-format.md), [game manifest](../../docs/reference/game-manifest.md) |
| `kinds` | four enemy kinds in three palettes, a ranged Warden and a boss, each actor with its own wake rule and drop | [enemies](../../docs/how-to/enemies.md) |
| `weapons` | four weapons owned by episode or found, three drawing on ammunition | [weapons](../../docs/how-to/weapons.md) |
| `themes`, `textures/` | three themes over seven wall textures, the most the engine holds | [themes](../../docs/how-to/themes-and-palettes.md), [textures](../../docs/how-to/wall-textures.md) |
| `art/` | the Sentinel's twelve animated frames at three distances, the steel HUD and helmet, items, fixtures, the title's wordmark and emblem | [sprites and HUD](../../docs/how-to/sprites-and-hud.md) |
| `screens.json` | 27 screens: the title, code entry, a prologue, the episode pages, 17 debriefs, game over and the ending | [screens](../../docs/how-to/screens.md) |
| `audio/` | eight songs and ten effects | [music and sound](../../docs/how-to/music-and-sound.md) |
| `playtests/`, `snapshots/` | three driven tours and six golden suites | [test your game](../../docs/how-to/test-your-game.md) |

It is also the only game that builds the engine's historical `compact` and
`legacy` display profiles, which the engine keeps as regression contracts.

## Its own documents

- [Campaign](docs/campaign.md): from tech demo to game, what each decision cost, and what every sector holds.
- [Art direction](docs/art.md) and the [steel HUD](docs/steel-hud.md): the look, the sources and the budgets.
- [Weapons](docs/weapons.md): how the four weapons are rendered from 3D models.
- `art/tools/`: the offline tools that made the weapon sheets, the item cels, the title art and the HUD. They make PNGs; no build runs them.
