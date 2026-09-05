# Whole-HUD steel-console direction

This direction is now implemented in the [native steel HUD](../../STEEL_HUD.md).
The generated boards below remain concept references, not ROM captures.
The final portrait keeps the approved armoured helmet, recessed visor and
respirator. An uncovered human-face revision was rejected. The owner clarified that the entire UI bar needs
more character, rather than only the helmet portrait.

## Direction

Use the original Doom status bar's clear information hierarchy, expressive
player portrait and tangible panel surface as inspiration. Keep Sable's own
art, restrained teal accents, 24-pixel height and 160×120 world view.
The [Doom II manual](https://cdn.akamai.steamstatic.com/steam/apps/2300/manuals/DOOM%20II%20Manual.pdf)
describes the portrait's health/event feedback;
[id Software's status-bar implementation](https://github.com/id-Software/DOOM/blob/master/linuxdoom-1.10/st_stuff.c)
provides the original expression priorities.

- Panel: one connected steel surface, a continuous top divider and shallow
  recessed readouts. Use a one-pixel edge treatment and sparse material marks.
- Health: a crisp cross and bold ivory numerals, the strongest numeric readout.
- Portrait: readable eyes beneath an angular helmet brow, a dark visor recess,
  ivory structural highlights and a small respirator. Preserve highlights
  during blinking; the original washed-out blink cel lacked highlights.
- Hostiles: the production refinement uses an ivory skull and a subordinate
  single digit for enemies remaining.
- Objective: the production refinement uses GOAL over HUNT/EXIT, replacing
  the confusing EXIT LOCK/OPEN concept text. Clear GOAL for DEAD/DONE.

## Native implementation constraints

The generated board illustrates material and hierarchy. It is not a verified
160×24 raster or a four-colour production sheet: its shading and extra details
must be redrawn deliberately at native resolution. Simplify the heavy borders
and vents rather than trying to shrink every generated detail.

Preserve the present layout: 16×16 portrait with four pixels of vertical
padding, 6×10 health digits and smaller 5×7 hostile/status glyphs. Keep the
continuous divider in every dynamic tile touching the top row. Do not add
controls, armour, ammunition, meters or unsupported gameplay indicators.

Use at most four colours per tile palette and 96 HUD patterns; current usage
is 94. Retain the 16-byte immutable HUD packet and preloaded patterns. First
replace the existing four portrait cels; additional reaction/health states
are a separate change requiring animation selection and resource measurement.

Most of the redesign can be preloaded tile artwork and static attributes.
That should avoid additional per-frame transfers, but timing and pattern
counts must be verified in the emitted ROM before claiming an exact cost.
Validate native stills, normal/blink/hurt/dead states, every health digit,
every status, both maps, the divider, publication safety and independent cores.
Preserve the qualified baseline and version the intentional image changes.

## Concept assets

Generated with the built-in image-generation tool:

- [Whole HUD concept](concept.png)
- [Initial portrait comparison](portrait-study.png)
- [Whole-HUD generation prompt](prompt.txt)

The whole-HUD direction supersedes the narrower portrait-only framing.
