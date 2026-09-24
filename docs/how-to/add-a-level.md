# Add a level

A level is a JSON file in your game's `levels/` directory, listed in an
episode. The [level format](../reference/level-format.md) is the full
reference; this page is the path from an idea to a level in the campaign.

## 1. Start from a level that works

Copy one of your game's levels (the starter's `first_steps.json` is the
smallest) to a new name:

```sh
cp games/my_game/levels/first_steps.json games/my_game/levels/pump_room.json
```

Change its `name`. Keep `format` at `lupine-level-v2`.

## 2. Draw the map

`rows` is sixteen strings of sixteen digits, `rows[y][x]`: `0` floor, `1`
structure wall, `2` machinery wall, `3` a door cell. The outer ring must be
solid. Every `3` needs a record in `doors` with the same `x` and `y`, and a
door sits in a wall: a `horizontal` door has walls west and east, a
`vertical` door walls north and south.

Design to the certificate's defaults: no straight run of floor longer than
**6** cells (a door cell counts), rooms no bigger than **4×4**, at least
**4** cells behind every ordinary door, and a path of at least **12** steps
with **2** turns from the spawn to the first enemy. Put a turn right after a
door rather than lining a corridor up with a room.

Or draw it in Tiled ([use Tiled](use-tiled.md)).

## 3. Place the player, enemies and the exit

- `player_spawn`: `x_q8` and `y_q8` are cells × 256 (the middle of cell 2 is
  640), `angle` 0 east, 64 south, 128 west, 192 north. The first enemy must
  be at least `safe_radius_cells` walking steps away.
- `entities`: one to six enemies, each a `kind` from your `game.json`, on a
  floor cell the spawn can reach. The first is the level's headline enemy.
- `exit`: the exit cell, behind exactly one door of `"kind": "exit"` with
  `"unlock": "enemies_cleared"`.
- `pickups`: one record per kind of drop your enemies leave (`medkit` with
  the health it restores, `keycard` with value 1), `"source": "drop"`.
- `palette_profile`: one of your themes.

List the door nearest the spawn first: the pinned-core smoke test
([test your game](test-your-game.md)) walks forward from the spawn and
opens the first door.

## 4. Check it until the compiler agrees

```sh
python tools/lupine.py level check --game games/my_game games/my_game/levels/pump_room.json
```

It prints the certificate, or exactly why it refuses the level:

```text
games/my_game/levels/pump_room.json: REFUSED: readability: sightline is too long (7 > 6)
```

Fix the level, never the limit. The
[certificate](../reference/level-certificate.md) page explains each rule.

## 5. Put it in the campaign

Add the file to an episode's `levels` in `game.json`, in the order it is
played, then check the whole game and build:

```sh
python tools/lupine.py game check --game games/my_game
python tools/lupine.py build --game games/my_game
```

A game holds at most 20 levels ([limits](../reference/limits.md)). The
intermission after each level shows its continue code.

## 6. Prove it can be finished

```sh
make playthrough GAME=games/my_game RESTART=1
```

The controller route plays every level on controller input alone: it
clears the enemies, collects the drops, opens the doors and reaches the
exit, checking every frame. `SECTORS=3-3` plays one level from its
continue code. If the route cannot finish your level, a player may not
either.
