# Palettes

The Game Boy Color has eight background (BG) palettes and eight object (OBJ)
palettes of four colours each, and all sixteen are spoken for. A game gives
the colours; the engine decides which slot each one fills. This page is that
assignment, from `tools/lupine3d_v4/palettes.py`.

Colours are RGB555 triples in `game.json`, `[red, green, blue]` with each
channel 0..31.

## Themes and shared palettes

A game's **themes** (`game.json` `themes`, at most four) each become one
128-byte palette set, BG then OBJ. A level names its theme
(`palette_profile`), and every entry into the level uploads that set with the
LCD off, so a theme recolours the world without touching a pattern. Rows
marked *theme* below come from the level's theme; the others come from
`shared_palettes` and are the same bytes in every set, because the screens
never rewrite palettes and the weapon, drops and HUD must not change colour
between levels.

## Background palettes

| BG | Colours 0-3 | Draws | Source |
|---|---|---|---|
| 0 | ceiling, floor, structure light, structure dark | structure walls, upper half | *theme* |
| 1 | `hud` | the HUD, and every full-screen mode | shared |
| 2 | floor, floor, structure light, structure dark | structure walls, lower half | *theme* |
| 3 | ceiling, floor, door light, door dark | door faces, upper half | *theme* |
| 4 | floor, floor, door light, door dark | door faces, lower half | *theme* |
| 5 | ceiling, floor, machinery light, machinery dark | machinery walls, upper half | *theme* |
| 6 | floor, floor, machinery light, machinery dark | machinery walls, lower half | *theme* |
| 7 | `reserved_bg` | reserved | shared |

The lower half of the view is the upper half's patterns flipped vertically,
and colour 0 of a wall pattern is the space beside the wall: the upper
palettes put the ceiling there and the lower ones the floor, so no pixel is
recoloured. Depth shading darkens the texture, not the palette, so it costs
no slot.

## Object palettes

| OBJ | Draws | Source |
|---|---|---|
| 0 | the weapon | shared `weapon` |
| 1 | the first enemy palette (`actor_palettes[0]`) | *theme* `actors` |
| 2 | drops: the medkit and keycard | shared `drops` |
| 3 | the muzzle flash and decor | shared `effects` |
| 4 | decor and the reticle | shared `decor` |
| 5 | a weapon's second palette | shared `weapon_alt` |
| 6 | the second enemy palette (`actor_palettes[1]`) | *theme* `actors` |
| 7 | the third enemy palette (`actor_palettes[2]`) | *theme* `actors` |

Colour 0 of every OBJ palette is transparent. An enemy palette a game does
not name is filled with black and never drawn.

## What this means for a game

- A new enemy *look* needs one of the three enemy palettes; a fourth visible
  look means re-planning this table, not adding a row.
- A new drop colour, or a second weapon colour that is not a whole 8×16
  object, has no slot.
- Everything that is not the world (HUD, screens, weapon) is in the shared
  palettes: change it once, for every theme.

`python tools/palette_plan.py` prints the owners and RGB555 values of a
fresh build, and `--propose asset.png` reports the nearest existing palette
to an indexed PNG's colours; `--set N` picks the theme.
