# Themes and palettes

A theme is a level's look: the textures on its walls and the world's colours.
A game has one to four; each level names one in its `palette_profile`.
[Palettes](../reference/palettes.md) lists every colour slot.

## Change the colours of a theme

In `game.json` `themes`, every colour is `[red, green, blue]`, each 0..31:

```json
{
  "name": "training",
  "textures": {"structure": "steel_panel", "machinery": "machinery_grille", "door": "door_plate"},
  "colours": {
    "ceiling": [2, 2, 1], "floor": [6, 5, 3],
    "structure": [[17, 15, 11], [8, 7, 5]],
    "door": [[4, 12, 18], [18, 26, 29]],
    "machinery": [[14, 11, 6], [6, 5, 3]]
  },
  "actors": {
    "drone": [[0, 0, 0], [4, 4, 6], [16, 18, 22], [28, 29, 30]],
    "carrier": [[0, 0, 0], [6, 3, 1], [26, 14, 3], [31, 26, 12]]
  }
}
```

- `ceiling` and `floor` fill the space above and below the walls.
- `structure`, `door` and `machinery` are each a wall's light and dark tone;
  the texture's three indices draw in them, darkened with distance.
- `actors` gives each enemy palette four colours; colour 0 is transparent.

Keep doors distinct from walls: players read a door by its colour first.

## Add a theme

Add an object to `themes` with a new `name`, and set a level's
`palette_profile` to it. A theme may reuse the textures of another; each
distinct texture costs 20 KiB of ROM, and a game has room for seven. Four
themes is the limit: each theme's texture directory lives in bank 0 beside
the resident engine ([limits](../reference/limits.md)).

## Change what every theme shares

`shared_palettes` holds the HUD (which the full-screen modes also use), the
weapon, the drops, the effects and decor: the same in every theme, so the
HUD and weapon never change colour between levels.

## Look at it

```sh
python tools/lupine.py build --game games/my_game
python tools/lupine.py run --game games/my_game --snapshot-mode record
python tools/palette_plan.py --swatches build/swatches.png
```

`palette_plan.py` (run with `LUPINE3D_GAME=games/my_game`) prints each slot's
owner and value from a fresh build, `--set N` for another theme.
