# Art pipeline

Everything the console draws in the world is compiled from a game's
checked-in, indexed PNGs at build time; the full-screen modes are the
game's text drawn in the engine's font. **Builds never generate
images**: `games/sable_outpost/art/tools/adapt_sable_art.py` is an offline authoring step whose
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
index, palette or SHA-256 disagree with `games/sable_outpost/art/sprites.json`, so a
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
| Enemy, near | `games/sable_outpost/art/native/sentinel_near.png` | 16×32 | 12 | ROM cel dictionary (242 source patterns); masked into 32 OBJ patterns per bank at runtime |
| Enemy, mid | `sentinel_mid.png` | 16×16 | 12 | same |
| Enemy, far | `sentinel_far.png` | 8×16 | 12 | same |
| Weapons | `shotgun.png`, `slug_rifle.png`, `arc_lance.png`, `pulse_carbine.png`, rendered by `games/sable_outpost/art/tools/render_weapons.py` from 3D models | 40×32 | 4 | eighty streamed OBJ patterns at `$8200`, VRAM bank 1; one weapon resident, SELECT swaps with the LCD off |
| Muzzle flash | `flash.png` | 8×16 | 2 | preloaded OBJ patterns |
| Reticle | `reticle.png` | 8×16 | 1 | preloaded OBJ pattern, palette 4 |
| Helmet portrait | `helmet_steel.png` | 16×16 | 4 (normal, blink, hurt, dead) | HUD packet portrait, six tile IDs |
| HUD chassis | `hud_steel.png` | 160×24 | 1 | 94 of 96 HUD patterns, bank 0 `$8200-$87DF` |
| Drops | `drops.png` (medkit, keycard) | 8×8 | 2 | OBJ patterns, palette 2 |
| Hit effect, exit beacon | `hit_effect.png`, `exit_beacon.png` | 8×8 | 2 each | OBJ patterns |
| Wall fixtures | `fixtures.png`: per family (`game.json` `fixture_kinds`) a 16×16 cel at 16, 8 and 4 pixels across; the engine derives the half-width copy | 16×16 | 12 | masked OBJ patterns |
| Wall textures | `games/<id>/textures/*.png` (named in `game.json` `textures`) (a structure and a machinery texture per episode, one shared door plate; design rules in `docs/TEXTURED_WALLS.md`, "Texture design") | 16×8 (upper half) | 1 | row-window tables in `TEXTURE_WINDOW_BANKS` on every slim build; a level's palette set picks its texture set |
| Screens | `screens.json`: text in the engine's 3×5 font | 160×144 | 1 per mode | the idle 96-pattern window at `$9000` |

The twelve enemy cels are, in order: `idle_a`, `idle_b`, `walk_left`,
`walk_pass_a`, `walk_right`, `walk_pass_b`, `attack_raise`, `attack_fire`,
`hurt`, `death_kneel`, `death_fall`, `death_down`, with per-cel tick counts in
the manifest. All three size levels carry the same twelve cels; the runtime
chooses a level from projected height. Kinds (Sentinel, skirmisher, warden and the boss)
share these cels and differ by OBJ palette and stats.

Every weapon must compile to exactly `WEAPON_TILE_BYTES` (1,280 bytes, eighty
patterns) in the 8×16 pair order the weapon window expects; pattern IDs never
change between weapons, only their contents.

## Weapons are rendered from models

A first-person weapon has to read as a solid object held by the player, and
neither pixels placed by hand nor flat illustrations reduced to 32×32 did.
Each weapon is therefore a small 3D model in `games/sable_outpost/art/tools/render_weapons.py`,
rendered straight at the console's resolution: the technique 3D-to-pixel-art
pipelines use, fitted to the OBJ hardware.

- **Model.** A handful of signed-distance primitives in gun space (+z along
  the barrel, +y up): tubes, rounded boxes, and ellipsoids for the gloved
  hands. Each part has a material (steel, polymer, wood, glove, sleeve, ink,
  glow) and a name; parts of the action (the shotgun's pump, the rifle's
  bolt, the lance's capacitor rings, the carbine's shutter) move with the
  animation, so all four cels are posed from one model.
- **Camera.** The view's own eye with a viewmodel field of view: a long
  focal length and a distant gun, as first-person games draw their held
  weapon, so it keeps its shape instead of ballooning near the eye. The pose
  is solved from where the receiver's rear and the muzzle land on screen,
  a three-quarter view from the right with the muzzle under the flash. The
  gun sits right of the eye pointing at the centre, so the camera sees its
  **left** flank: details that must show go on −x.
- **Pixels.** Every pixel is decided at the target resolution from 4×4
  samples (majority part, its mean normal, nearest depth), never shrunk from
  a large image. Shading is three bands per material from one key light,
  with a specular glint on metal.
- **Ink.** A dark line on the silhouette's own edge and on the far side of
  every boundary between differently named parts: that is what makes a pump
  read as a pump at forty pixels.
- **One palette.** Every object uses OBJ palette 0 (ink, steel, highlight).
  A sprite takes one palette, so a second colour, wood on a pump, could
  only show in whole 8×16 blocks; the gun is diagonal and the action
  slides, so those blocks sat over the gun as rectangles that did not
  follow the part. Wood therefore reads as the mid tone without the crest
  highlight, cut by ink grooves. The fit still records a palette per object
  (`object_palettes` in `sprites.json`, written by `animate_weapon` from the
  ROM's `weapon_object_attributes` table), so a later weapon whose second
  material fills whole objects can use OBJ palette 5.

The window is 40×32 pixels at world x 68..107 on the slim display: five
8×16 objects across and two down, ten objects and four cels of twenty
patterns (idle, the kick, the action back, the action returning; recovery
shows the idle cel). The scanline admission counts the weapon's objects
before any world object, so a line never exceeds ten objects with the flash
on the top row. The legacy art profile keeps its eight-object 32×32 window
and takes the centre 32 columns of each idle cel.

The tool is offline authoring: `python games/sable_outpost/art/tools/render_weapons.py` writes
previews to `build/weapon-art/`, `--write` renders the four sheets into
`games/sable_outpost/art/native/` and updates their manifest records, and `--check`
fails when a committed sheet is not a fresh render. `tests/test_weapon_art.py`
does the same check, so a weapon is changed in its model and re-rendered,
never touched up by hand. numpy is pinned in `requirements.txt` so the
render is byte-identical everywhere.

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
weapon, drops and HUD must not change colour between sectors. Sets are the
game's `themes` in `game.json` (the shared rows are its `shared_palettes`),
assembled by `tools/lupine3d_v4/palettes.py`; `--set N` selects the set for
`--swatches` and `--propose`.

| BG | Owner |
|---|---|
| 0 | structure walls, upper half (ceiling colour 0, wall light and dark), *per set* |
| 1 | HUD (the steel palette in `steel_hud.py`); the full-screen modes draw in it too (`SCREEN_PALETTE`) |
| 2 | structure walls, lower half: colour 0 is the floor, so the Y-flipped upper patterns need no recolouring, *per set* |
| 3, 4 | door faces, upper and lower (cyan/white in the outpost, amber in the reactor, violet on the spire; reserved for functioning doors), *per set* |
| 5, 6 | machinery faces, upper and lower (cool green, coolant teal, signal amber), *per set* |
| 7 | reserved (`shared_palettes.reserved_bg`) |

| OBJ | Owner |
|---|---|
| 0 | weapon |
| 1 | Sentinel (red armour; rust in the reactor, pale blue on the spire), *per set* |
| 2 | drops (medkit, keycard) |
| 3 | muzzle flash and decor |
| 4 | decor and the reticle |
| 5 | the weapon's second palette (unused by the current weapons; see "Weapons are rendered from models") |
| 6 | warden (brass; acid green, crimson), *per set* |
| 7 | skirmisher (cold blue; violet, teal), *per set* |

A fourth visible enemy kind or a new drop colour means re-planning this
table, not adding to it (`AGENTS.md`, "Enemies and skill"). Depth shading on
slim builds darkens the texture, not the palette, so it costs no
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
2. Update `games/sable_outpost/art/sprites.json`: file, size, frame names, ticks,
   anchor, palette and the new SHA-256.
3. `make build` and `python tools/check_sable.py`: the cel compiler contract,
   the VRAM window against the compiled sheet, the HUD fixture and the
   publication windows are hard gates.
4. `make playtest-art` and review the snapshot diff (`docs/VERIFICATION.md`);
   an intentional change is accepted with a note and committed with its PNG.
5. Preview on the emitted ROM with `make preview`; concept images are not
   evidence.

Screens are text in the game's `screens.json`, drawn in the engine's font;
the same checks apply and their goldens live in the same suites.
