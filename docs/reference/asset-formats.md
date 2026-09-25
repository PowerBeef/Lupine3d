# Asset formats

Everything the console draws in the world is compiled at build time from a
game's checked-in, indexed PNGs; the full-screen modes are the game's text
drawn in the engine's font. **Builds never generate images.** A tool that
makes art (the showcase's weapon renderer, for instance) is an offline
authoring step whose outputs are committed, and a build that needed a
generated file would be a bug.

This page gives every kind of asset, its format and the checks it must
pass. [Palettes](palettes.md) gives the colour slots they draw in, and
[sprites and HUD](../how-to/sprites-and-hud.md) walks through changing one.

## Indexed PNG conventions

Every asset is a mode-`P` PNG with four palette entries:

| Index | Sprites and HUD | Wall textures |
|---|---|---|
| 0 | transparent (the PNG's `transparency` chunk names index 0) | never used: the outside of a wall |
| 1 | darkest | deep |
| 2 | mid | shaded |
| 3 | lightest | lit |

The PNG's palette is only for viewing it: on the console a sprite takes the
colours of the OBJ palette its role draws in, and a texture the colours of
the level's theme. Palette RGB values are authored as 8-bit and converted
to RGB555 by `round(c × 31 / 255)`.

Pixels compile to 2bpp CGB tiles: each 8×8 tile is sixteen bytes, two
bit-planes per row, most significant bit on the left. Objects are 8×16
pairs and the HUD strip is column-major.

## The sprite manifest

A game's sprite sheets are records of its sprite manifest (`art/sprites.json`
by convention; `docs/schema/sprites-v1.schema.json`):

```json
{
  "schema": "lupine-sprites-v1",
  "assets": {
    "sentinel_near": {
      "file": "native/sentinel_near.png", "size": [16, 32],
      "frames": ["idle_a", "idle_b", "walk_left", "walk_pass_a", "walk_right", "walk_pass_b",
                 "attack_raise", "attack_fire", "hurt", "death_kneel", "death_fall", "death_down"],
      "ticks": [32, 32, 8, 8, 8, 8, 4, 4, 8, 12, 12, 12],
      "anchor": [8, 32],
      "palette": [[0, 0, 0], [39, 28, 32], [170, 53, 50], [238, 218, 175]],
      "sha256": "4b79b749…"
    }
  }
}
```

A sheet is its frames side by side, each `size` wide. `sprite_assets.frames`
refuses a sheet whose mode, dimensions, transparency index, palette or
SHA-256 disagree with its record, so a changed PNG always comes with a
changed record and shows up in review. `game.json` `sprites` says which
record plays which role.

## Asset kinds

| Role (`game.json`) | Size | Frames | Where it lives at runtime |
|---|---|---|---|
| `actor_near` | 16×32 | 12 | a 220-pattern ROM cel dictionary shared by the three distances; masked into 32 OBJ patterns per bank at runtime |
| `actor_mid` | 8×16 or 16×16 (one or two columns) | 12 | same |
| `actor_far` | 8×16 | 12 | same |
| weapons (`weapons[].sprite`) | 40×32 | 4 | eighty streamed OBJ patterns at `$8200`, VRAM bank 1; one weapon resident, SELECT swaps with the LCD off |
| `muzzle_flash` | 8×16 | 2 | preloaded OBJ patterns, OBJ palette 3 |
| `reticle` | 8×16 | 1 | a preloaded OBJ pattern, OBJ palette 4 |
| `portrait` | 16×16 | 4: normal, blink, hurt, dead | the HUD packet's portrait, six tile IDs |
| `hud` | 160×24 | 1 | 94 of 96 HUD patterns, bank 0 `$8200-$87DF`, BG palette 1 |
| `drops` | 8×8 | 2: medkit, keycard | OBJ patterns, OBJ palette 2; each is the top of an 8×16 object over an empty pattern |
| `items` | 8×8 | one per item `sprite` (Sable: medkit, stim, slugs, cells, armour, card, case; `art/tools/make_item_art.py`) | OBJ patterns after the fixtures, each over an empty pattern; drawn in the item type's palette (drops, effects or decor), so one card cel is both key colours; optional, required when the game has `items` |
| `hit_effect`, `exit_beacon` | 8×8 | 2 each | OBJ patterns |
| `fixtures` | 16×16 | 3 per family: 16, 8 and 4 pixels across (the engine derives a half-width copy) | masked OBJ patterns |
| wall textures (`textures`) | 16×8, the upper half of a face | 1 | row-window tables in the texture banks; a level's theme picks its set |
| screens (`screens.json`) | 160×144 | one per mode | text in the engine's 3×5 font, at most 128 patterns a screen, copied to `$9000` while a screen is up |

The twelve enemy frames are, in order: `idle_a`, `idle_b`, `walk_left`,
`walk_pass_a`, `walk_right`, `walk_pass_b`, `attack_raise`, `attack_fire`,
`hurt`, `death_kneel`, `death_fall`, `death_down`, with a tick count each.
All three distances carry the same twelve. The runtime chooses a distance
from the enemy's forward distance: the engine measures each distance's
tallest drawn figure (its inked rows) and switches where the neighbouring
sizes are equally wrong, taking the near figure as true one cell away, with
a tenth of hysteresis either side. Every enemy kind uses these frames in its
own palette.

A fixture is centred on its face three quarters of the way up the wall, a
fixed world height, so it stays put on the wall as the player moves. It is
drawn from its three sizes, never scaled: 16 pixels tall where the wall's
projected half-height is at least 24, 8 from 12, 4 from 6, and not at all
below that. Each step keeps it between a sixth and a third of the wall's
height, except close up: once the wall is taller than 96 pixels the
16-pixel size, the largest there is, falls below a sixth.

A weapon sheet must compile to exactly `WEAPON_TILE_BYTES` (1,280 bytes,
eighty patterns) in the 8×16 pair order the weapon window expects: ten
objects, five across and two down, in four cels (idle, the kick, the action
back, the action returning). Pattern IDs never change between weapons, only
their contents, so a record may carry `object_palettes`, one OBJ palette per
object (0 or 5). The showcase renders its weapons from 3D models
([weapons](../../games/sable_outpost/docs/weapons.md)).

## Wall textures

A texture is a 16×8 indexed PNG of the **upper half** of a 16×16 texel face;
the compiler mirrors it about the horizon, because the folded compositor
draws the lower half of every wall by Y-flipping the upper patterns. Index 0
never appears. The build compiles four shade sets per texture (near, mid,
far, dark face) into 5 KiB row-window blocks and refuses a PNG of the wrong
size or mode. A texture costs 20 KiB of ROM and no VRAM until it is on
screen; a game has room for seven ([limits](limits.md)).
[Textured walls](../explanation/textured-walls.md) explains the kernel,
and its "Texture design" section what reads well at this size.

## Checks a changed asset must pass

1. `python tools/lupine.py game check`: the manifest names records that
   exist, and each record's file is inside the game.
2. `python tools/lupine.py build`: the sheet matches its record, compiles to
   the size its role needs, and fits its window.
3. `python tools/lupine.py run` and the snapshot diff: an intentional change
   is accepted with a note and committed with its PNG
   ([test your game](../how-to/test-your-game.md)).

For the showcase, `python tools/check_sable.py` also pins its HUD pixel by
pixel, the VRAM windows against the compiled sheets, and the publication
windows.
