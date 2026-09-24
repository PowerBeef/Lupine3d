# Test your game

The engine proves every frame it draws against a host model, so testing a
game is mostly running what already exists and looking at the pictures.

| Check | Command | Proves |
|---|---|---|
| content | `python tools/lupine.py game check --game games/my_game` | the manifest loads, every file exists, every limit holds, every level certifies |
| build | `python tools/lupine.py build --game games/my_game` | the ROM links: art matches its records, every bank fits, the resident engine fits bank 0 |
| tour | `python tools/lupine.py run --game games/my_game` | every frame of the tour matches the engine's model, and every capture matches its golden |
| route | `make playthrough GAME=games/my_game RESTART=1` | the whole game can be finished on controller input alone, through every screen, and restarted |
| cores | `make sameboy GAME=games/my_game SAMEBOY_DIR=build/deps/SameBoy` and `make mgba …` | the ROM runs in two independent emulators with no unsafe VRAM access |

## Goldens: pictures you approve

A golden is a picture a playtest must reproduce exactly. The first time,
record the tour and look at it:

```sh
python tools/lupine.py run --game games/my_game --snapshot-mode record
```

The captures and a contact sheet are in
`build/games/my_game/playtest/coherence_tour/`. When they show what you meant,
accept them:

```sh
python tools/lupine.py snapshot --game games/my_game accept --suite tour --note "first look"
```

The goldens go to `games/my_game/snapshots/`, each with the note, who
accepted it, when, and the ROM. Commit them with the change. From then on
`run` fails when a picture changes, naming the scene, and
`snapshot … diff --suite tour` writes a `report.html` with the changed pixels
in red. Accept a change only when you can say in the note why it is right.

## The tour

`game.json` `playtests.tour` names the scenario; the starter's
(`games/starter/playtests/tour.json`) poses the player at points worth
looking at and presses B at a door. Add a pose wherever a level has
something to see ([scenario format](../reference/scenario-format.md)).

## The route

The controller route (`tools/playthrough.py`) plays the whole game as a
player would, with no writes to game RAM: it walks to the enemies it can
reach, fights them with the weapons the player owns, collects every drop,
opens doors, reaches each exit, crosses every intermission and episode
screen, and with `RESTART=1` plays the ending and restarts. Every frame on
the way is checked. `SECTORS=A-B` plays a range from its continue code.

## The pinned cores

The core smoke tests walk forward from the first level's spawn, press B
twice, turn and fire, then require the level's **first door record** to be
open: list the door nearest the spawn first in your first level, within a
short walk. The cores are built once under `build/deps`
([development](../engine/development.md), "Pinned independent cores").

## Before you publish

All of the above, plus `make limits` if you changed the engine. CI runs the
same lanes for the showcase and the starter: `python tools/lupine.py ci`
runs them locally.
