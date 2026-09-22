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
| Weapons | `shotgun.png`, `slug_rifle.png`, `arc_lance.png`, `pulse_carbine.png`, reduced by `tools/draw_weapons.py` from the SVGs in `vector/` | 32×32 | 5 | eighty streamed OBJ patterns at `$8200`, VRAM bank 1; one weapon resident, SELECT swaps with the LCD off |
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

Every weapon must compile to exactly `WEAPON_TILE_BYTES` (1,280 bytes, eighty
patterns) in the 8×16 pair order the weapon window expects; pattern IDs never
change between weapons, only their contents.

## Weapons are vector illustrations, reduced

A first-person weapon has to read as a solid object seen from the shooter's
eye, and pixels placed by hand at 32×32 did not. Each weapon is therefore
an SVG illustration under `assets/sable_v2/vector/`, drawn in cel units
(`viewBox="0 0 32 32"`, one unit per pixel) with as much detail as the
drawing wants, using only the weapon palette's three tones as fills
(`#1e2328` dark, `#6f8489` mid, `#eee5c5` light) so every shape already
says which tone it is: lit tops and bevels, mid bodies, dark flanks,
grooves, undersides and a contour. The perspective is drawn, not
computed: the eye is above and behind the gun, the barrel converges on the
reticle thirty units above the frame, the forend or housing is the nearest
thing in view and the receiver sits under it, mostly out of frame.

`tools/draw_weapons.py` rasterises each cel at sixteen times the cel size
with cairosvg and reduces it block by block: a pixel is opaque when half
its block is covered, dark when dark ink reaches a quarter of it, mid when
mid ink reaches a third, otherwise the majority tone. So a line drawn 0.5
units wide survives as a one-pixel line and a highlight has to be at least
half a unit wide to show; draw with that in mind and check the reduction,
not only the illustration. The cels are posed from named groups: `action`
(the pump, charging handle, capacitor ring or vent shutter, translated by
`data-travel` units), `flare` (shown in the kick cel only) and `gun`
(everything, kicked down and toward the eye on recoil).

The tool is offline authoring: `--write` reduces the four sheets into
`assets/sable_v2/native/` and updates their hashes in `assets.json`, and
`tests/test_weapon_art.py` refuses a committed sheet that is not the
reduction of its SVG, so a weapon is changed in the drawing and
regenerated, never touched up by hand. The bottom corner objects of the
weapon grid use OBJ palette 5 (leather), so the gloves are drawn there and
everything steel stays in the middle columns; the muzzle sits under the
flash object at the top centre. The legacy art profile keeps its original
drawn cels.

## Palettes

There are eight BG and eight OBJ palettes and all sixteen are spoken for.
`python tools/palette_plan.py` prints their owners and RGB555 values from a
fresh build, and `--propose asset.png` reports the nearest existing palette to
an indexed PNG's colours, so a new asset is designed for a slot that exists.

A build ships one **palette set** per episode (`outpost`, `reactor`, `spire`;
a level's `palette_profile` names its set) as 128 bytes each in the
`bg_palettes` table, BG then OBJ. `enter_world` uploads the level's set with
the LCD off, so an episode recolours the world without touching a pattern.
A set may change only the rows marked *per set* below; the others are the
same bytes in every set, because screens never rewrite palettes and the
weapon, drops and HUD must not change colour between sectors. Sets are
authored in `make_palette_sets` (`tools/build_rom.py`) from the outpost set;
`--set N` selects the set for `--swatches` and `--propose`.

| BG | Owner |
|---|---|
| 0 | structure walls, upper half (ceiling colour 0, wall light and dark), *per set* |
| 1 | HUD (the steel palette in `steel_hud.py`) |
| 2 | structure walls, lower half: colour 0 is the floor, so the Y-flipped upper patterns need no recolouring, *per set* |
| 3, 4 | door faces, upper and lower (cyan/white in the outpost, amber in the reactor, violet on the spire; reserved for functioning doors), *per set* |
| 5, 6 | machinery faces, upper and lower (cool green, coolant teal, signal amber), *per set* |
| 7 | screens |

| OBJ | Owner |
|---|---|
| 0 | weapon |
| 1 | Sentinel (red armour; rust in the reactor, pale blue on the spire), *per set* |
| 2 | drops (medkit, keycard) |
| 3 | muzzle flash and decor |
| 4 | decor and the reticle |
| 5 | the weapon's lit corners |
| 6 | warden (brass; acid green, crimson), *per set* |
| 7 | skirmisher (cold blue; violet, teal), *per set* |

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
