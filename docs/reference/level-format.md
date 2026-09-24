# Level format (`lupine-level-v2`)

A level is one JSON file in a game's directory (the showcase's are under `games/sable_outpost/levels/`). `tools/lupine3d_v4/levels.py`
(`compile_level`) is the validator of record: this page documents what it
accepts and why, and `docs/schema/level-v2.schema.json` describes the same
shape for editors. When the two disagree, the compiler wins and the
documentation is wrong. `python tools/lupine.py level check games/sable_outpost/levels/*.json`
compiles a level and prints its certificate (`docs/reference/level-certificate.md`).

Authoring in [Tiled](https://www.mapeditor.org/) is supported through
`tools/lupine3d_v4/tmx_import.py` (`lupine level export-tmx` and
`lupine level import-tmx`); the TMX mapping is at the end of this page.

## Coordinates and units

- The map is a **16×16 cell grid**, `rows[y][x]`, y down, x right. Every row is
  a string of sixteen material digits. The loader currently requires exactly
  16×16 (`width` and `height` are both 16).
- **Q8** positions (`x_q8`, `y_q8`) are cell coordinates × 256: cell `(4, 13)`
  centre is `(4 × 256 + 128, 13 × 256 + 128) = (1152, 3456)`. The runtime
  keeps Q8.8 positions, so an authored position is exact.
- The player's **angle** is a byte, 0..255, one turn. 0 faces +x (east),
  64 faces +y (south, down the map), 128 west, 192 north.
- `activation_radius_q4` is a **Q4** radius (units of a sixteenth of a cell);
  the loader folds it to whole cells once. It is a distance, not a phase count.
- Door and fixture cells use whole-cell `x`, `y`.

## Materials

| Code | Meaning | Presentation profile by default |
|---|---|---|
| `0` | walkable | - |
| `1` | wall, structure | `structure` (neutral steel) |
| `2` | wall, machinery | `machinery` (cool green) |
| `3` | door cell | `door` (cyan/white, reserved for functioning doors) |

Materials 1 and 2 share physical continuity: a paint change is not geometry,
so a run of `1`s and `2`s is one physical segment. Doors always split a run.
The outer ring of the map must be solid (any of `1`, `2`, `3` is solid; a door
on the boundary is refused separately).

`surfaces` overrides the presentation profile of one oriented face:

```json
{"x": 5, "y": 6, "side": "south", "profile": "machinery"}
```

`side` is the face of the solid cell (`west`, `east`, `north`, `south`), the
cell must be solid, a face may be overridden once, and the `door` profile is
allowed only on material-3 cells (and a door cell may not be painted as
anything else). On slim builds (textured walls) the surface profile selects the
texture (`docs/explanation/textured-walls.md`).

## Top-level keys

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | `lupine-level-v2` for gameplay levels; `lupine-level-v1` keeps the older, laxer checks for benchmark levels |
| `name` | yes | Display name, used in reports and the manifest |
| `width`, `height` | yes | 16 and 16 |
| `rows` | yes | sixteen strings of sixteen material digits |
| `player_spawn` | yes | `x_q8`, `y_q8`, `angle`, optional `safe_radius_cells` (0..15) |
| `doors` | yes | one to six door records (see below) |
| `entities` | yes | one to six actors (see below) |
| `pickups` | yes | the drops the level fields (see below) |
| `exit` | yes | `x`, `y` of the exit cell (walkable); `marker` is retained but not read |
| `palette_profile` | yes | one of the game's themes (`game.json` `themes`; the showcase's are `outpost`, `reactor` and `spire`): its palettes and textures are what every entry into this level uses ([palettes](palettes.md)); levels of one campaign may differ |
| `vram_profile` | yes | `renderer-heavy` or `entity-heavy` (the resident atlas; every campaign level must agree) |
| `readability` | no (v2) | per-level certificate limits; defaults below |
| `fixtures` | no | up to sixteen wall-mounted landmarks |
| `surfaces` | no | per-face presentation overrides |
| `triggers` | no | retained for authoring intent; the v2 rule (one exit door that opens when the enemies are cleared) is what the compiler enforces |

Unknown keys are ignored by the compiler and preserved by the TMX round trip.

### Doors

```json
{"id": "exit_lock", "x": 9, "y": 11, "orientation": "horizontal",
 "kind": "exit", "unlock": "enemies_cleared"}
```

- Every material-3 cell has exactly one door record and every door sits on a
  material-3 cell, off the boundary, with a unique `id` and a unique cell.
- `orientation` is the direction the panel slides across: `horizontal` doors
  sit in an east-west wall (solid west and east, open north and south);
  `vertical` doors the other way round. A v2 level is refused when the frame
  does not match.
- `kind` is `standard` or `exit`. `unlock` is `none`, `enemies_cleared`
  (opens once every actor is dead; the showcase writes `sentinel_dead`, the
  same thing) or `keycard` (opens once the player holds the card). A v2
  level has exactly one `exit` door, and it is `enemies_cleared`.
- The record compiles to six bytes: x, y, orientation, flags (`0x01` exit,
  `0x02` locked until the actors are dead, `0x04` keycard), state, fraction.
  Up to six doors ride the wall key and the snapshot copy, so the limit is an
  engine contract, not a style choice (`docs/explanation/architecture.md`).

### Entities

```json
{"kind": "drone", "x_q8": 2688, "y_q8": 2176, "health": 3, "activation_radius_q4": 96}
```

- One to six actors, each of a kind the game defines (`game.json` `kinds`;
  [enemies](../how-to/enemies.md)). Each stands on a walkable cell the spawn
  can reach with the enemies-cleared doors shut; an actor in a wall or in the
  exit room is refused. Every kind uses the game's actor frames and differs
  by stats and OBJ palette. Six are simulated, but the renderer
  admits at most four per frame (sixteen world objects, four per scanline,
  32 masked patterns), so keep at most four actors on any one sightline; the
  fifth and sixth belong elsewhere in the sector.
- `health` is 1..255 hit points before difficulty scaling, which changes
  contact damage only.
- `activation_radius_q4` is how near the player must come before the actor
  wakes, in sixteenths of a cell (1..127). Today the level header carries the
  first actor's radius, folded to whole cells, for every actor.
- The first entity is the level's headline actor: its cell is the critical
  path's target in the certificate and its position rides the level header.
- The spawn must keep every actor at least `safe_radius_cells` walking steps
  away with doors closed (or unreachable), and the player's `0x38` Q8
  collision radius must clear the walls at all four corners.

### Pickups (drops)

```json
{"kind": "medkit", "source": "drop", "value": 25}
```

Nothing is placed on the map: a pickup is what a dead actor leaves, selected
by the actor's kind (its `drop` in `game.json`: a `medkit` or a `keycard`).
A level declares which drops it fields, one record per kind, `source` is
always `drop` (the showcase writes `sentinel_drop`, the same thing), and the
medkit's `value` (1..255,
health restored) is the only per-level number. The compiler refuses a declared
drop no actor leaves, a keycard drop that opens nothing, a keycard door with no
declared card, and a keycard door whose only card-carrying actor is behind it.

### Fixtures

```json
{"x": 4, "y": 11, "side": "south", "kind": "access"}
```

Up to sixteen wall-mounted landmarks, each of one of the game's four
`fixture_kinds` (the showcase's and the starter's are `vent`, `light`,
`access` and `sector`), drawn from its fixture sheet,
each on an interior wall face that is exposed to a walkable or door cell. A
fixture on a door cell must face the moving panel. Duplicates are refused.
Fixtures are rendered as masked objects, so they share the world OBJ budget
(`docs/explanation/architecture.md`, "Publication and timing").

### Readability limits

The v2 certificate gates spatial legibility (`docs/reference/level-certificate.md`). A
level may tighten the defaults; it cannot loosen the fixed 4×4 room envelope
or the reachability rule.

| Key | Default | Rule |
|---|---|---|
| `maximum_sightline` | 6 | longest straight walkable run, in cells |
| `minimum_door_separation` | 4 | walkable cells an ordinary door cuts off |
| `minimum_critical_path_steps` | 12 | spawn to first entity, doors open |
| `minimum_critical_path_turns` | 2 | fewest turns among the shortest paths |
| `maximum_material_singletons` | 16 | one-cell paint islands on exposed faces |

## Compiled payload

Campaign levels are packed five to a 16 KiB ROM bank from
`LEVEL_ROM_BANK_BASE` (241), in page-aligned slots of `LEVEL_SLOT_PITCH`
(2,816) bytes, at fixed offsets inside the slot. A resident directory gives
the loader each level's bank and slot page (`level_location(index)`), and
every reader adds the page to the high byte of its offset, so the offsets
below are the first slot's:

| Offset | Bytes | Contents |
|---|---|---|
| `$4000` | 1024 | segment IDs, `(cell × 4 + side)`, one ID per contiguous exposed face run |
| `$4400` | 1024 | surface profiles, same index (must stay exactly 1024 above the segments: one pointer reads both) |
| `$4800` | 256 | the 16×16 material grid |
| `$4900` | 24 | header: size, profiles, spawn, first actor, exit, counts, medkit value |
| `$4920` | 36 | six six-byte door records |
| `$4950` | 96 | six sixteen-byte actor slots |
| `$49B0` | 256 | sixteen sixteen-byte fixture records |

`levels.py` names these offsets; `docs/explanation/architecture.md` explains how
`LEVEL_INDEX`, `LEVEL_BANK` and `LEVEL_PAGE` select a level at runtime.

## Tiled (TMX) mapping

`tmx_import.py` maps a level to an orthogonal TMX map of 16×16 tiles of
**32 pixels**, so a Q8 coordinate is exactly a pixel coordinate divided by
eight and the round trip JSON → TMX → JSON is lossless:

| JSON | TMX |
|---|---|
| `rows` | tile layer `materials`, CSV, tileset `materials` (firstgid 1, tile id = material) |
| `player_spawn` | point object `spawn` in object layer `spawn`, at `(x_q8/8, y_q8/8)`, properties `angle`, `safe_radius_cells` |
| `doors[]` | rectangle objects (one cell) in layer `doors`, `name` = id, properties `orientation`, `kind`, `unlock` |
| `entities[]` | point objects in layer `entities`, `type` = kind, properties `health`, `activation_radius_q4` |
| `fixtures[]` | rectangle objects in layer `fixtures`, `type` = kind, property `side` |
| `surfaces[]` | rectangle objects in layer `surfaces`, `type` = profile, property `side` |
| `exit` | rectangle object `exit` in layer `exit`, property `marker` |
| `pickups`, `triggers`, `readability` and any other key | map properties holding JSON text, named `json:<key>` |
| `format`, `name`, `palette_profile`, `vram_profile` | map properties of the same name |

The tileset references `materials.png`, a 128×32 strip of four 32×32
swatches in material order; `lupine level export-tmx --swatch` writes one
beside the map so Tiled can draw the layer. The importer never reads it.
