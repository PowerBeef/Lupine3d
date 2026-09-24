# Weapons

Sable Outpost's four weapons (the shotgun, the slug rifle, the arc lance and
the pulse carbine) are 40×32 sheets of four cels each, the format any game's
weapons take ([asset formats](../../../docs/reference/asset-formats.md)).
This page is how the showcase made its sheets: they are rendered from small
3D models, and the renderer is the showcase's own offline tool, not part of
the engine or the build.

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
  (`object_palettes` in `art/sprites.json`, written by `animate_weapon` from the
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
