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

*Re-evaluated after emission:* the table above is the pre-emission
estimate (`textured_walls_lab_v1.json`). The kernel model now carries the
costs measured on the emitted ROM, and the same lab and corpus give
`textured_walls_lab_v2.json`: +96k T mean, +215k T p95, +10.6% intervals -
the gate is not met. The measured numbers and their consequences are in
"Cost, measured on the emitted ROM" below.

## What was emitted (Phase 2b)

The textured profile is built with `LUPINE3D_TEXTURED_WALLS=1` (slim, Sable
art and HBlank streaming only; `make textured`). It is opt-in: the default
ROM is byte-identical. The contact sheet below is the coherence tour captured
from the emitted ROM by the harness, not a host rendering.

![The coherence tour on the textured ROM](images/textured_walls_rom_tour.png)

### The cast: `RAY_U` and `PIXEL_U`

`compute_along` (resident, one bank switch) evaluates the reference's
`rom_along` after `project_hit`: the player's other coordinate advanced by
the axis distance times the direction's Q8 slope, taken modulo 65536
through three product-table lookups, then negated for the east face (x step
negative) and the north face (y step positive) so that texture columns never
decrease across the view. Anchors store it, midpoints take the circular mean
(`midpoint_u`), edge recasts store their own, and `expand_pixel_u` pulls each
pixel a quarter of the way towards its neighbour's ray with a wrap test.
`validate_frame` requires `ray_u_exact` and `pixel_u_exact` on every update.

### The kernel: `tools/lupine3d_v4/textured.py`

Per tile column (`tex_column_runs`, resident because it switches banks):

1. change bits between neighbouring pixels over the face key, the surface
   profile and the shade bit (style bit 0: decoration darkens single pixels
   of a face, so it splits a run); one face across the column is the common
   case and takes an immediate record;
2. per run: the height class (its tallest pixel), the shade set (dark side,
   or near/mid/far by height), the stride class from the stride table
   (run length, Q8 difference of its last and first coordinates), the phase
   from the coordinate extrapolated back to the tile's first pixel (so the
   window's texel *i* is the tile's pixel *i* and a run needs only a pixel
   mask), the Q8 row step from the step table, and one sixteen-byte copy of
   the row window from its bank into the run's cache (`TEX_WINDOWS`).

Per tile (`tex_compose_tile`, cold): the ring wait; the boundary masks
(`tex_mask_tables`: per row the covered pixels not on the outline and the
outline pixels, built in one pass over the eight tops); then for each run
the eight-row kernel (`tex_compose_run`). The window cache is split by
plane - eight plane-0 rows then eight plane-1 rows - so the run's row
accumulator, `H` = the cache row's address and `L` = the fraction, addresses
a row without arithmetic: a row is `push hl; ld l,h; ld h,$D1; ld a,(hl);
ld (bc),a; inc c; ld a,l; add 8; ld l,a; ld a,(hl); ld (bc),a; inc c;
pop hl; add hl,de` - 96 T. A run that starts inside the tile begins at
`cache - (top - y0) * step` so its rows above the top read garbage the
coverage mask removes and row `top` reads texture row 0 exactly; a run
below the tile is skipped. The first run of a seam tile composes into the
slot and keeps its own pixels; later runs compose into the scratch tile and
merge under their masks. Boundary tiles then apply `(plane & keep) | edge`
per row, and the centre tile mirrors its four upper rows with the floor tone
under the wall. `texture_reference.compose_kernel` is the byte-exact model
of all of this, proven equal to the pixel-level composition over the 700-pose
corpus and checked against the console on every driven update.

### The ring and its transfers

Patterns are numbered in composition order, ids 0..237 (below 128 at `$9000`,
the rest at `$8800`; ceiling 238, floor 239), and composed into the 96-slot
ring at `$C000`. `tex_stream_hblank` hands the next chunk to HBlank DMA into
the hidden bank; a chunk stops at the ring wrap and at the VRAM half so both
ends stay contiguous, and `DYN_INFLIGHT`/`DYN_STREAMED` record what is in
flight and what has been handed over. `tex_ring_wait` lets a tile reuse a
slot only once the pattern that used it 96 ago has landed: below the transfer
in flight, or handed over while idle; otherwise it starts the next chunk and
spins. With the LCD off, `tex_flush_gdma` moves every pending chunk into
both banks synchronously, so `enter_world` needs no separate pattern upload
and `upload_hidden_page` drains whatever the last column left before the map.

### Verification

* `validate_frame`: `dynamic_tiles_exact` reads the displayed page's bank at
  the ids' addresses (the ring has been reused by then), plus the map, the
  published map, `ray_u_exact`, `pixel_u_exact` and the mode-3 counters. The
  coherence, living-world and art tours pass on every update.
* `tools/check_sable.py` under the flag: the window blocks and directory in
  the ROM equal the reference tables; the kernel composed blind (LCD off)
  for far walls in the centre tile, a seam with a decorated pixel and a
  full-height wall whose 160 patterns lap the ring and cross the VRAM half
  lands in both banks exactly; publication windows up to 160 patterns; the
  chunked hand-off under a foreign WRAM bank; six validated poses.
* Pinned SameBoy (CGB-0 and CGB-E) and mGBA run the textured ROM with no
  unsafe transfer, no visible-map write and no mode-3 VRAM or palette write.
* `tests/test_textured_walls.py` runs the Sable checks under the flag in a
  fresh process; the CI slow lane runs the tours and checks.

### Cost, measured on the emitted ROM

Cycles by code region on the coherence tour, mean per update (T-cycles):

| Region | Textured | Flat |
| --- | --- | --- |
| row kernel (`tex_compose_run`, eight rows) | 93k | - |
| column setup (change bits, records, shade, tables, window copy) | 50k | - |
| boundary masks (tables and application) | 29k | - |
| seam tiles (scratch and merge) | 10k | - |
| tile bookkeeping, ring wait, map writes | 30k | 9k |
| flat compositor (microstrips, atlas lookup) | - | 51k |
| `compute_along` (Stage A) | 21k | - |

About 200k T of kernel against 60k of flat compositor: roughly +140k T per
full update, one LCD interval. `research/textured_walls_lab.py` now carries
these per-tile and per-column constants and, over the 700-pose corpus,
models +96k T mean, +215k p95 and +10.6% LCD intervals, projecting the
sustained rates at turning 8.8/s, walking 6.9/s and two-actor corner 6.1/s
against v0.10's 10.27, 7.77 and 6.80 (`research/results/textured_walls_lab_v2.json`).
The prototype gate's estimates (700/1,300 T per tile, no column cost) were
optimistic by about 2x; the gate as written - +70k T mean, rates within 10% -
is **not met** by this first emission, and the profile therefore stays
opt-in. Exactness, publication safety and the pinned cores are all green,
so the remaining work is performance, which Phase 5 takes up on this code
with the profile above as its baseline: the column setup and the boundary
masks are the largest reducible items, and per-frame pattern sharing
(p95 63 unique of 160 raw) the largest structural one.

### Not done in this phase

A level does not yet name its texture set: the surface profile selects the
texture (structure, machinery, door). The V-row lookup table in bank 247 is
still written but unused by the kernel, which accumulates rows instead.
