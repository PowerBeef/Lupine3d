# Your first game

In about thirty minutes you will make a Game Boy Color game of your own from
the starter: give it a title and a night-time palette, add a tougher enemy,
check it the way the engine checks everything, and play it from the title
to the ending. Every command and output below is real; run them from the
repository root.

You need Python 3.10 or later, Make, and a Game Boy Color emulator to play
the result (SameBoy, mGBA and most others work).

## 1. Set up

```sh
python3 tools/dev_setup.py
source .venv/bin/activate
```

`dev_setup.py` creates the virtual environment and installs the two Python
packages the engine needs (Pillow and numpy). Nothing else is required: the
engine writes the console's machine code itself.

## 2. Make a game

```sh
python tools/lupine.py new-game games/night_shift
```

```text
Created games/night_shift: Night Shift (night_shift), copied from games/starter.
Next:
  python tools/lupine.py game check --game games/night_shift
  …
```

`games/night_shift` is a complete game: two levels, two enemy kinds, a
theme, songs, screens and art, copied from the starter, with its own id,
title and cartridge header. Open `games/night_shift/game.json`; the
[game manifest](../reference/game-manifest.md) explains every key.

## 3. Check it

```sh
python tools/lupine.py game check --game games/night_shift
```

```text
Night Shift (night_shift) in games/night_shift: builds into build/games/night_shift/
  episodes: Training (2 levels)
  kinds: 2/4 (drone, carrier); actor palettes 2/3
  weapons: shotgun from level 1, slug rifle from level 1, arc lance from level 2, pulse carbine never
  themes: training; textures: 3 (steel_panel, machinery_grille, door_plate)
  songs: title 64 rows, world 64 rows, victory 32 rows (at most 1322 each)
  playtests: tour; files read by the build: 27
levels/first_steps.json: ok - First Steps: 16x16, 2 doors, 1 actors, 1 drops, 4 fixtures, 32 segments
  certificate: 47 walkable, 0 unreachable, critical path 15 steps/5 turns, sightline 6, room 4x4, door separation 4, seams 3, singleton runs 2
levels/keycard.json: ok - Keycard: 16x16, 3 doors, 2 actors, 2 drops, 4 fixtures, 36 segments
  certificate: 56 walkable, 0 unreachable, critical path 18 steps/5 turns, sightline 6, room 4x4, door separation 4, seams 1, singleton runs 2
ok - 2 of 2 levels compile
```

`game check` loads the manifest and every file it names, checks the
engine's [limits](../reference/limits.md), and compiles every level with its
certificate: the proof that a level can be finished and reads clearly. It
does not build; it is the quick loop while you edit.

## 4. Build it and play it

```sh
python tools/lupine.py build --game games/night_shift
```

```text
Built …/build/games/night_shift/lupine3d.gb (4194304 bytes): Night Shift (night_shift)
```

Open `build/games/night_shift/lupine3d.gb` in your emulator. Press START on
the title, walk up to the airlock with the D-pad, open it with B, and find
the drone; A fires. That is the starter's game with your name on it.

## 5. Give it a title

In `games/night_shift/screens.json`, the title screen's first line:

```json
{"text": "NIGHT SHIFT", "y": 28, "colour": 2, "scale": 3},
```

Screen text is upper-case letters, digits and a little punctuation, drawn in
the engine's font; at scale 3 a line holds twelve characters
([screen format](../reference/screen-format.md)).

## 6. Make it night

In `game.json`, the `training` theme's `colours`:

```json
"ceiling": [1, 1, 4],
"floor": [3, 3, 7],
```

Colours are red, green and blue from 0 to 31, the values the console
stores. The ceiling and floor fill everything above and below the walls, so
this one change turns the whole world to night
([themes and palettes](../how-to/themes-and-palettes.md)).

## 7. Add a tougher enemy

First, the mistake everyone makes. In `levels/first_steps.json`, change the
drone to a kind that does not exist yet:

```json
"entities": [{"kind": "sentry", "x_q8": 2176, "y_q8": 896, "health": 4, "activation_radius_q4": 96}],
```

```sh
python tools/lupine.py game check --game games/night_shift
```

```text
levels/first_steps.json: REFUSED: unknown enemy kinds ['sentry']: night_shift's kinds are drone, carrier (game.json `kinds`)
```

Every refusal says what is wrong and where. Define the kind in `game.json`,
after the carrier:

```json
{"name": "sentry", "contact_damage": 10, "recovery_ticks": 10, "step_q8": 6, "palette": "carrier", "drop": "medkit"}
```

A sentry hits harder and moves slower than a drone, wears the carrier's
colours, and leaves a medkit ([enemies](../how-to/enemies.md)). Check again:

```text
  kinds: 3/4 (drone, carrier, sentry); actor palettes 2/3
levels/first_steps.json: ok - First Steps: 16x16, 2 doors, 1 actors, 1 drops, 4 fixtures, 32 segments
…
ok - 2 of 2 levels compile
```

## 8. Look at every frame

```sh
python tools/lupine.py build --game games/night_shift
python tools/lupine.py run --game games/night_shift --snapshot-mode record
```

`run` plays the game's tour (`playtests/tour.json`) in the engine's host
harness and checks every frame the ROM draws against the engine's own model
of what it must be. Open
`build/games/night_shift/playtest/coherence_tour/contact_sheet.png`: seven
views of the first level, at night.

When they look right, keep them as your **goldens**, the pictures future
builds must reproduce exactly:

```sh
python tools/lupine.py snapshot --game games/night_shift accept --suite tour --note "first look"
```

From now on `python tools/lupine.py run --game games/night_shift` fails if
a picture changes, and names the scene. You accept a change only with a
note saying why ([test your game](../how-to/test-your-game.md)).

## 9. Prove it can be finished

```sh
make playthrough GAME=games/night_shift RESTART=1
```

```text
Sector 1 (First Steps) complete after 328 updates
Sector 2 (Keycard) complete after 804 updates
```

The controller route plays the whole game on controller input alone: it
fights the sentry, takes the medkit, collects the keycard, opens every door,
reaches both exits, crosses the intermission, plays the ending and restarts,
checking every frame on the way. It takes about three minutes. If the route
can finish your game, so can a player.

## Where next

- [Your first level](first-level.md): draw a level from a blank grid.
- The [how-to guides](../how-to/README.md): textures, sprites, weapons,
  music, screens, episodes.
- [The engine and the game](../explanation/engine-and-game.md): what the
  engine does for you, and what a game cannot change yet.
- [Ship a ROM](../how-to/ship-a-rom.md) when it is ready for players.
