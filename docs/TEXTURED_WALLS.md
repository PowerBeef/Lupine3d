# Textured walls: design, contract and prototype gate

Lupine 3D's walls have been flat two-tone surfaces with composed edge
strips since v0.2. This document is the design for texture-mapped walls
with depth shading on the same renderer, the exact host reference that
defines what every textured tile byte must be, and the host-side prototype
that decided whether the console kernel is worth emitting. It is written
before any SM83 exists for it; the emission is Phase 2b of the roadmap.

## What the folded compositor allows

The slim viewport composes eight tile rows and displays the lower seven as
the Y-flip mirror of the upper ones (palette 2 turns colour 0 into floor).
A texture therefore **cannot be vertically asymmetric**: the rows below the
horizon are the rows above it, reflected. Textures are authored **16 texels
wide by 8 rows** and mirrored about the horizon by construction; a texture
that is not is refused at compile time. Rivet rows, rails and panel seams
read naturally under that rule; a texture with a "top" and a "bottom" does
not exist here.

Wall tones are the three non-zero colours of the face's palette: 2 (lit),
3 (shaded) and 1 (the deep tone the upper palettes share with the floor).
Colour 0 is the outside. Per-face palette selection (structure, machinery,
door) is unchanged, so material colour stays a property of the face and the
texture gives shape and tone within it.

## The reference (`tools/lupine3d_v4/texture_reference.py`)

**Along-face coordinate.** Every cast now records `along_q8`: the hit's
position along the face it struck, Q8 within the cell, measured along the
axis the face is parallel to (`reference.py`, `ReferenceRayHit.along_q8`).
It is the exact rational hit point floored, for regular faces and door
panels alike. Physical pixels take it by the same reconstruction the tops
use (`expand_pixel_u`): each pair ray's two pixels are pulled a quarter of
the way towards the neighbouring ray when both lie on the same face and the
coordinates do not wrap; the pixels an edge recast replaced take the
recast's own coordinate. Faces are oriented (`face_texel_column`) so the
texture column never decreases from the viewer's left to right on any side
of a cell, which the tests assert over the corpus.

**Height classes and rows.** A tile column's eight pixels share one height
class: the tallest top within two rows of the first pixel's. `texel_row`
maps a screen row of the upper half to one of the eight texture rows; the
lower half mirrors. Silhouettes stay per-pixel exact; only texture sampling
shares the class.

**Shade.** The dark side of a cell (style bit 0) uses shade set 3; the lit
side uses near, mid or far by half height (≥ 24, ≥ 10, else). A shade set
is a tone remap applied to texels, so depth shading costs no CPU and no
palette, and its banding follows wall geometry column by column rather than
screen rows (the screen-space palette ladder v0.8 rejected).

**Two compositions, one result.** `compose_pixels` is the semantics: for
every wall pixel, which texel, which shade. `compose_windows` is what the
console will run: inside one tile column the texture columns are affine,
`u_i = u0 + i·Δ` with Δ ∈ {1/8, 1/4, 1/2, 1, 2} texels per pixel and `u0`
quantised to a quarter texel, so a tile row is one lookup in a **row
window** table `W[texture][shade][Δ][phase][v]` (eight texels, two plane
bytes) masked by the silhouette. A face seam inside a tile column splits it
into runs, one lookup each. `affine_columns` states the approximation
exactly, and the two compositions must be byte-identical on every scene;
the emitted kernel will be checked against this the way `render_view` is
checked against `reference_compose_view` today.

**Costs.** A window table is 20 KiB per texture (4 shades × 5 strides × 64
phases × 8 rows × 2 bytes); the V lookup is 3.9 KiB; a 128×128 quotient
table for the console's along-face division is 16 KiB.

## The prototype gate (`research/textured_walls_lab.py`)

The lab composes 700 poses — the frozen witness scenes, the 53 wall-reuse
scenes, the tour and living-world captures, and every eighth update of the
six-sector controller route — with three procedurally authored textures
(a riveted steel panel, a machinery grille, a door plate), proves the two
compositions equal, counts patterns, and models the kernel's T-cycle cost
against the flat compositor's on each pose's measured per-update cycles.

| Criterion | Target | Measured |
| --- | --- | --- |
| Row windows equal pixel-level composition | every scene | 700 of 700 |
| Modelled Δ per full update, mean | ≤ +70k T | **+2.0k T** |
| Modelled Δ, p95 | ≤ one interval (140,448 T) | 105k T (max 135k) |
| Modelled LCD intervals, net over the corpus | ≤ +2% | **+0.34%** (4,114 → 4,128) |
| Unique patterns per update, p95 / max | ≤ 114 / ≤ 224 | **63 / 85** (160 wall tiles composed at most; identical tiles share a pattern) |
| ROM for tables | ≤ 160 KiB | 82 KiB for three textures |
| Overflow | none | none |

Where the cycles come from: a textured frame composes every wall tile
(79.7 on average, 21.9 of them silhouette boundaries, 5.7 with a face seam)
at a modelled 700 T for an interior tile and 1,300 T for a boundary tile,
plus about 9.4k T to derive the coordinates; the flat compositor it replaces
composes 11.6 dynamic tiles at 6.7k T and looks up 8.2 atlas tiles. Simple
frames get cheaper; wall-filling frames pay up to one LCD interval. The
projection for the sustained scenarios, from the mean, is unchanged rates;
the honest expectation is a small loss on wall-heavy motion and none
elsewhere, to be measured on the emitted ROM.

The kernel model is an estimate from the instruction timings of an SM83
sketch, not a measurement; the emission phase measures it with
`runtime_observer` and the go criteria are re-evaluated on the real ROM.

The contact sheet (`docs/images/textured_walls_prototype_2x.png`; the full
set with 4× exact-coordinate renders lands in `build/textured-lab/`) shows
each accepted flat golden beside the textured prototype of the same pose.
The summary is `research/results/textured_walls_lab_v1.json`.

**Decision: go.** Phase 2b emits the kernel under a `walls=textured`
profile flag, keeps the legacy and compact profiles byte-identical, and
re-runs this gate on the emitted ROM.

## What Phase 2b must emit

1. `RAY_U` (80 bytes) after `project_hit`, from `DDA_ERR` and the axis
   component through the quotient table, equal to `along_q8`; `PIXEL_U`
   (160 bytes) by the pair expansion and edge recasts, equal to
   `expand_pixel_u`.
2. The row-window kernel in the fixed half: per tile column, the height
   class, the shade, the runs; per row, the coverage, edge and floor masks
   and one window lookup per run; every wall tile composed into a 96-slot
   WRAM ring that HBlank streaming drains into up to 254 VRAM patterns.
3. `validate_frame` gains `ray_u_exact`, `pixel_u_exact`, and reads the
   dynamic tiles from the hidden VRAM bank after publication; the atlas
   and seam tiles retire under the textured profile.
4. Texture assets as indexed 16×8 PNGs under `assets/textures/`, compiled
   to window tables by `texture_assets.py`; a level names its texture set.
