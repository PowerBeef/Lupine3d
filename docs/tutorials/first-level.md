# Your first level

You will draw a level from a blank grid, let the level compiler refuse it
twice, fix it into a level that reads well, add it to your game and watch
the controller route finish it. It continues [your first game](first-game.md)
(`games/night_shift`); any game works.

## 1. A first draft

A level is a 16×16 grid, `rows[y][x]`: `0` floor, `1` structure wall, `2`
machinery wall, `3` a door. Create `games/night_shift/levels/cellar.json`:

```json
{
  "format": "lupine-level-v2",
  "name": "Cellar",
  "width": 16,
  "height": 16,
  "rows": [
    "1111111111111111",
    "1111111111111111",
    "1100001111111111",
    "1100001111111111",
    "1100003000011111",
    "1100001111111111",
    "1111011111111111",
    "1111011111111111",
    "1111011111111111",
    "1111011111111111",
    "1111311111111111",
    "1100001111111111",
    "1100001111111111",
    "1100001111111111",
    "1100001111111111",
    "1111111111111111"
  ],
  "player_spawn": {"x_q8": 1152, "y_q8": 3200, "angle": 192, "safe_radius_cells": 5},
  "doors": [
    {"id": "hatch", "x": 4, "y": 10, "orientation": "horizontal", "kind": "standard", "unlock": "none"},
    {"id": "exit_door", "x": 6, "y": 4, "orientation": "vertical", "kind": "exit", "unlock": "enemies_cleared"}
  ],
  "entities": [{"kind": "sentry", "x_q8": 896, "y_q8": 896, "health": 4, "activation_radius_q4": 96}],
  "pickups": [{"kind": "medkit", "source": "drop", "value": 25}],
  "exit": {"x": 10, "y": 4, "marker": "beacon"},
  "palette_profile": "training",
  "vram_profile": "entity-heavy"
}
```

A spawn room at the bottom, a hatch, a straight corridor north to a room
with a sentry, and an exit door east of it. Positions are in cells × 256
(`x_q8` 1152 is the middle of column 4); the angle 192 faces north.

## 2. Let the compiler read it

```sh
python tools/lupine.py level check --game games/night_shift games/night_shift/levels/cellar.json
```

```text
games/night_shift/levels/cellar.json: REFUSED: readability: critical path is too short (10 < 12)
```

The compiler does more than parse: it certifies that a level is legible and
fair ([level certificate](../reference/level-certificate.md)). Here the
sentry is only ten steps from the spawn; the player should have a moment to
look around first. Move the spawn to the room's far corner and the sentry to
the far corner of its room:

```json
"player_spawn": {"x_q8": 640, "y_q8": 3456, "angle": 192, "safe_radius_cells": 5},
"entities": [{"kind": "sentry", "x_q8": 640, "y_q8": 640, "health": 4, "activation_radius_q4": 96}],
```

```text
games/night_shift/levels/cellar.json: REFUSED: readability: sightline is too long (13 > 6)
```

Column 4 runs straight from the sentry's room, down the corridor, through
the hatch and across the spawn room: thirteen cells a player would see down
at once. The certificate keeps straight runs of floor to six cells (door
cells count), so a level reads as rooms and turns rather than a shooting
gallery, and so its views stay within the renderer's budget.

## 3. Turn the corners

Put a turn after every door, enter the rooms from the side, and move the
exit to the room's north wall:

```json
"rows": [
  "1111111111111111",
  "1000011111111111",
  "1111311111111111",
  "1100001111111111",
  "1100001111111111",
  "1100001111111111",
  "1100000011111111",
  "1111111011111111",
  "1111111011111111",
  "1111000011111111",
  "1111311111111111",
  "1100001111111111",
  "1100001111111111",
  "1100001111111111",
  "1100001111111111",
  "1111111111111111"
],
"player_spawn": {"x_q8": 896, "y_q8": 3456, "angle": 192, "safe_radius_cells": 5},
"doors": [
  {"id": "hatch", "x": 4, "y": 10, "orientation": "horizontal", "kind": "standard", "unlock": "none"},
  {"id": "exit_door", "x": 4, "y": 2, "orientation": "horizontal", "kind": "exit", "unlock": "enemies_cleared"}
],
"entities": [{"kind": "sentry", "x_q8": 640, "y_q8": 896, "health": 4, "activation_radius_q4": 96}],
"exit": {"x": 1, "y": 1, "marker": "beacon"},
```

```text
games/night_shift/levels/cellar.json: ok - Cellar: 16x16, 2 doors, 1 actors, 1 drops, 0 fixtures, 26 segments
  certificate: 46 walkable, 0 unreachable, critical path 19 steps/5 turns, sightline 6, room 4x4, door separation 4, seams 0, singleton runs 0
```

The certificate says the level is reachable everywhere, the sentry is
nineteen steps and five turns away, no view is longer than six cells, no
room is bigger than 4×4, and each door closes off at least four cells. The
exit door opens when every enemy is dead.

## 4. Put it in the game

Add it to the episode in `game.json`:

```json
"episodes": [{"name": "Training", "levels": ["levels/first_steps.json", "levels/keycard.json", "levels/cellar.json"]}],
```

```sh
python tools/lupine.py game check --game games/night_shift
```

```text
  episodes: Training (3 levels)
…
ok - 3 of 3 levels compile
```

## 5. Edit it in Tiled

[Tiled](https://www.mapeditor.org/) is easier than typing digits:

```sh
python tools/lupine.py level export-tmx games/night_shift/levels/cellar.json build/cellar.tmx --swatch
```

Open `build/cellar.tmx` in Tiled: the walls are a tile layer, the spawn,
doors, enemies and exit are objects you can drag. Save, then bring it back:

```sh
python tools/lupine.py level import-tmx --game games/night_shift build/cellar.tmx games/night_shift/levels/cellar.json
```

The round trip is lossless, and the import compiles what it writes, so a
map the compiler refuses is reported at once ([use Tiled](../how-to/use-tiled.md)).

## 6. Watch it being played

```sh
make playthrough GAME=games/night_shift SECTORS=3-3 RESTART=1
```

```text
Sector 3 (Cellar) complete after 364 updates
```

The route builds the game, types the level's continue code on the title,
walks to the sentry, fights it, takes the medkit, opens the exit and walks
out, then plays the ending and restarts, checking every frame. Its contact
sheet is in `build/games/night_shift/playthrough/`.

## Where next

- [Add a level](../how-to/add-a-level.md): the same steps, as a checklist.
- [Level format](../reference/level-format.md): fixtures, surfaces, keycard
  doors and every key.
- [Troubleshooting](../how-to/troubleshooting.md): every refusal and its fix.
