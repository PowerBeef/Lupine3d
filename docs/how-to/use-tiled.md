# Use Tiled

[Tiled](https://www.mapeditor.org/) is a free map editor. A level converts
to a Tiled map and back without loss, so you can draw walls and move the
spawn, enemies, doors and fixtures with a mouse, and keep the JSON as the
file of record.

## Export a level

```sh
python tools/lupine.py level export-tmx games/my_game/levels/first_steps.json build/first_steps.tmx --swatch
```

`--swatch` writes `materials.png` beside the map: four 32×32 swatches (floor,
structure, machinery, door) so Tiled can draw the `materials` layer. Open
the `.tmx` in Tiled.

## Edit it

| Layer | Holds |
|---|---|
| `materials` | the 16×16 map: paint with the four swatches (floor, structure, machinery, door) |
| `spawn` | a point object `spawn`; its properties `angle` and `safe_radius_cells` |
| `doors` | one one-cell rectangle per door, named by its id; properties `orientation`, `kind`, `unlock` |
| `entities` | point objects, their type the enemy kind; properties `health`, `activation_radius_q4` |
| `fixtures` | one-cell rectangles, their type the fixture family; property `side` |
| `surfaces` | one-cell rectangles, their type a wall profile; property `side` |
| `exit` | a one-cell rectangle `exit` |

A tile is 32 pixels, so a position in pixels is the Q8 coordinate divided by
eight: the middle of cell 2 is at 80 pixels. Keys Tiled has no layer for
(`pickups`, `readability`, `triggers`) ride as map properties named
`json:<key>`; edit them there or in the JSON afterwards.

## Import it

```sh
python tools/lupine.py level import-tmx build/first_steps.tmx games/my_game/levels/first_steps.json
```

The importer writes the JSON and compiles it at once, so a map the compiler
refuses is reported with the reason ([troubleshooting](troubleshooting.md)).
Then build and check the game as usual. The
[level format](../reference/level-format.md), "Tiled (TMX) mapping", gives
the mapping in full.
