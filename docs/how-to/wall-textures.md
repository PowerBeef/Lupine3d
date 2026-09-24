# Wall textures

A wall texture is a 16×8 indexed PNG: the **upper half** of a 16×16 face.
The engine mirrors it about the horizon, because it draws the lower half of
every wall by flipping the upper half. A theme gives each wall role
(`structure`, `machinery`, `door`) a texture.

## Make one

1. Draw 16×8 pixels in an indexed PNG with four palette entries, using
   indices 1 (deep), 2 (shaded) and 3 (lit) only; index 0 is never used.
   The PNG's own colours are only for you: on the console the texture takes
   the theme's colours for its role.
2. Save it under your game's `textures/`.
3. Name it in `game.json`:

   ```json
   "textures": {"brick": "textures/brick.png", "…": "…"}
   ```

4. Use it in a theme's `textures` (every texture must be used by a theme, and
   a door texture only on doors).

The build compiles four shade sets per texture (near, middle, far, and the
darker side face) and refuses a PNG of the wrong size or mode.

## What reads well at 16×8

The view samples a texture at 1/8 to 2 texels per pixel, so what reads is
large: panels, seams and bands at least two texels across, never single
dots alone. The showcase's textures share one grammar: a dark trim along the
top of every face (the mirror repeats it at the bottom), panel seams that
meet the neighbouring face's to make a two-texel joint, and a centre feature
the mirror doubles at eye height. [Textured walls](../explanation/textured-walls.md),
"Texture design", explains why.

## Check it

```sh
python tools/lupine.py build --game games/my_game
python tools/lupine.py run --game games/my_game --snapshot-mode record
```

Every frame the tour draws is checked against the texture kernel's host
model, byte for byte: a mismatch is a bug in the engine, never something to
accept. Look at the contact sheet, then accept the changed goldens with a
note ([test your game](test-your-game.md)).
