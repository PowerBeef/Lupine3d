# Art pipeline

Everything the console draws is compiled from checked-in, indexed PNGs (or
from authored pixel tables in Python) at build time. **Builds never generate
images**: `tools/adapt_sable_art.py` is an offline authoring step whose
outputs are versioned, and a build that needed a generated file would be a
bug. This page lists the asset kinds, their formats and the checks a new
asset must pass. `docs/SABLE_OUTPOST.md` and `docs/STEEL_HUD.md` describe the
art direction those assets implement; keep the armoured helmet and
respirator, and do not substitute an uncovered face.

## Indexed PNG conventions

Every native asset is a mode-`P` PNG with four palette entries:

| Index | Sprites and HUD | Wall textures |
|---|---|---|
| 0 | transparent (the PNG's `transparency` chunk names index 0) | never used: the outside of a wall |
| 1 | darkest | deep |
| 2 | mid | shaded |
| 3 | lightest | lit |

`sprite_assets.frames` refuses an asset whose mode, dimensions, transparency
index, palette or SHA-256 disagree with `assets/sable_v2/assets.json`, so a
change to a PNG is always accompanied by a manifest change and shows up in
review. Palette RGB values are authored as 8-bit and converted to RGB555 by
`round(c × 31 / 255)`; author with that quantisation in mind.

Pixels compile to 2bpp CGB tiles: each 8×8 tile is sixteen bytes, two
bit-planes per row, most significant bit on the left. Objects are 8×16 pairs
(`compile_frame(..., paired=True)`) and the HUD strip is column-major
(`column_major=True`).

## Asset kinds

| Kind | Source | Size | Cels | Where it lives at runtime |
|---|---|---|---|---|
| Enemy, near | `assets/sable_v2/native/sentinel_near.png` | 16×32 | 12 | ROM cel dictionary (242 source patterns); masked into 32 OBJ patterns per bank at runtime |
| Enemy, mid | `sentinel_mid.png` | 16×16 | 12 | same |
| Enemy, far | `sentinel_far.png` | 8×16 | 12 | same |
| Weapon (shotgun) | `shotgun.png` | 32×32 | 5 | eighty streamed OBJ patterns at `$8200`, VRAM bank 1 |
| Weapon (slug rifle) | authored pixel code, `resources.py:make_slug_tiles` | 32×32 | 5 | the same window; SELECT swaps them with the LCD off |
| Muzzle flash | `flash.png` | 8×16 | 2 | preloaded OBJ patterns |
| Reticle | `reticle.png` | 8×16 | 1 | preloaded OBJ pattern, palette 4 |
| Helmet portrait | `helmet_steel.png` | 16×16 | 4 (normal, blink, hurt, dead) | HUD packet portrait, six tile IDs |
| HUD chassis | `hud_steel.png` | 160×24 | 1 | 94 of 96 HUD patterns, bank 0 `$8200-$87DF` |
| Wall fixtures | authored in `world_decor.py` | 8×16 | per kind and size level | masked OBJ patterns |
| Wall textures | `assets/textures/*.png` | 16×8 (upper half) | 1 | row-window tables from ROM bank 248 under the textured profile |
| Screens | authored in `screens.py` | 160×144 | 1 per mode | the idle 96-pattern window at `$9000` |

The twelve enemy cels are, in order: `idle_a`, `idle_b`, `walk_left`,
`walk_pass_a`, `walk_right`, `walk_pass_b`, `attack_raise`, `attack_fire`,
`hurt`, `death_kneel`, `death_fall`, `death_down`, with per-cel tick counts in
the manifest. All three size levels carry the same twelve cels; the runtime
chooses a level from projected height. Kinds (Sentinel, skirmisher, warden)
share these cels and differ by OBJ palette and stats.

Both weapons must compile to exactly `WEAPON_TILE_BYTES` (1,280 bytes, eighty
patterns) in the 8×16 pair order the weapon window expects; pattern IDs never
change between weapons, only their contents.

## Palettes

There are eight BG and eight OBJ palettes and all sixteen are spoken for.
`python tools/palette_plan.py` prints their owners and RGB555 values from a
fresh build, and `--propose asset.png` reports the nearest existing palette to
an indexed PNG's colours, so a new asset is designed for a slot that exists.

| BG | Owner |
|---|---|
| 0 | structure walls, upper half (ceiling colour 0, wall light and dark) |
| 1 | HUD (the steel palette in `steel_hud.py`) |
| 2 | structure walls, lower half: colour 0 is the floor, so the Y-flipped upper patterns need no recolouring |
| 3, 4 | door faces, upper and lower (cyan/white, reserved for functioning doors) |
| 5, 6 | machinery faces, upper and lower (cool green) |
| 7 | screens |

| OBJ | Owner |
|---|---|
| 0 | weapon |
| 1 | Sentinel (red armour) |
| 2 | drops (medkit, keycard) |
| 3 | muzzle flash and decor |
| 4 | decor and the reticle |
| 5 | the weapon's lit corners |
| 6 | warden (brass) |
| 7 | skirmisher (cold blue) |

A fourth visible enemy kind or a new drop colour means re-planning this
table, not adding to it (`AGENTS.md`, "Enemies and skill"). Depth shading in
the textured profile darkens the texture, not the palette, so it costs no
palette slot.

## Wall textures

A texture is a 16×8 indexed PNG of the **upper half** of a 16×16 texel face;
the compiler mirrors it about the horizon, because the folded compositor
draws the lower half of every wall by Y-flipping the upper patterns. Index 0
never appears. The build compiles four shade sets per texture (near, mid,
far, dark face) into 5 KiB row-window blocks and refuses a PNG of the wrong
size or mode. `docs/TEXTURED_WALLS.md` explains the kernel and its budget; a
texture costs 20 KiB of ROM and no VRAM until it is on screen.

## Adding or changing an asset

1. Author the PNG at the native size with the four-index palette above (for a
   sprite, the palette of the slot it will use).
2. Update `assets/sable_v2/assets.json`: file, size, frame names, ticks,
   anchor, palette and the new SHA-256.
3. `make build` and `python tools/check_sable.py`: the cel compiler contract,
   the VRAM window against the compiled sheet, the HUD fixture and the
   publication windows are hard gates.
4. `make playtest-art` and review the snapshot diff (`docs/VERIFICATION.md`);
   an intentional change is accepted with a note and committed with its PNG.
5. Preview on the emitted ROM with `make preview`; concept images are not
   evidence.

Fixtures, screens and the slug rifle are authored as pixel tables in Python;
the same checks apply and their goldens live in the same suites.
