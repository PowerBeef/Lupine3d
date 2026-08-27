# Lupine 3D v0.4.0 Architecture

## 1. Design target

Lupine 3D v0.4.0 is a CGB-only first-person grid renderer for a 4 MiB MBC5 cartridge with no external RAM. It is designed around the actual SM83, CGB double-speed mode, two 8 KiB VRAM banks, two background maps, CGB tile attributes, GDMA, OAM, and four-channel audio hardware.

The visible renderer remains the v0.3.0 160-column, Q5, selective-recast,
hybrid-microstrip design. v0.4.0 adds a stable HRAM hot-state ABI, packed DDA
records, an exact static boundary atlas, and exhaustive MBC5 arithmetic tables.
See `RENDERER_V3.md` for the fidelity pipeline, `PERFORMANCE_V4.md` for the
optimization architecture, and `DEVELOPMENT.md` for executable validation.

The renderer’s primary goal is not to imitate a modern framebuffer on the Game Boy Color. It deliberately converts visible wall geometry into the smallest useful set of reusable and generated 8×8 tiles.

Release constraints:

- 160×96 3D viewport above a 48-pixel HUD region;
- exact wall-cell and wall-side selection;
- 80 two-pixel geometry columns;
- no floating point at runtime;
- no general multiply or divide inside the DDA traversal loop;
- no fixed 3,840-byte framebuffer;
- maximum hidden-page payload of 1,920 bytes / 120 GDMA blocks;
- page publication only after all hidden data is complete;
- deterministic 4 MiB CGB-only MBC5 ROM with no external RAM.

## 2. Frame pipeline

```text
read input / update gameplay
  ↓
cast 41 mandatory anchor rays
  ↓
validate each missing odd column
  ├─ safe span: affine integer midpoint
  └─ unsafe span: exact DDA cast
  ↓
80 compact wall descriptors
  ↓
classify each of 20×12 viewport tile cells
  ├─ ceiling: static tile
  ├─ floor: static tile
  ├─ uniform wall interior: static style tile
  └─ edge/material transition: generated boundary tile
  ↓
dynamic tile bytes + 12×32 hidden tile map
  ↓
wait for a fresh VBlank
  ↓
GDMA dynamic tiles to hidden tile-data bank
  ↓
GDMA 384-byte tile-number map to hidden BG map in VRAM bank 0
  ↓
flip LCDC background-map bit
```

The geometry stage and raster stage are separated. The raycaster produces no pixels; it produces descriptors that the tile compositor later converts into static tile references or generated boundary tiles.

## 3. Coordinate systems and camera sampling

### 3.1 World coordinates

Player coordinates are Q8.8 values:

```text
integer byte   = map cell
fraction byte  = position inside the cell
```

The map is a 16×16 array in WRAM bank 1. A nonzero byte is solid:

- `1`: ordinary wall;
- `2`: technology/stone wall;
- `3`: door.

### 3.2 Player angle

The player angle is an unsigned byte spanning one full turn. Gameplay turns in four-unit increments, while the renderer supports all byte values for deterministic probes.

### 3.3 Camera-plane-derived ray offsets

The viewport has 80 geometry samples. Each sample represents two physical pixels. Host-side generation computes the center of each sample on a camera plane with a 60.5-degree horizontal field of view, converts its angular offset to a signed 1/1024-turn value, and stores:

- 80 signed 16-bit offsets;
- 80 cosine correction values;
- 1,024 signed X vectors;
- 1,024 signed Y vectors.

Render vectors use magnitude 127. This improves angular precision while preserving the signed 16-bit bounds needed by the initial DDA cross-products.

## 4. Signed-error exact grid DDA

### 4.1 Why cell-boundary traversal

The v0.1.0 renderer advanced every ray by one quarter tile and inspected the resulting map cell. That oversampled empty space and learned the hit only after stepping into a wall.

v0.2.0 traverses only grid boundaries. For each ray it stores:

- current map X/Y;
- absolute X/Y vector components;
- signed X/Y step;
- Q8.8 distance to the next X/Y boundary;
- signed 16-bit ordering error;
- crossed axis;
- hit material and crossing count.

### 4.2 Ordering invariant

Let:

```text
nextX = axis distance to the next vertical boundary
nextY = axis distance to the next horizontal boundary
absX  = absolute ray X component
absY  = absolute ray Y component
```

The next boundary is selected by the sign of:

```text
error = nextX × absY − nextY × absX
```

- `error <= 0`: cross X;
- `error > 0`: cross Y.

After an empty X crossing:

```text
nextX += 256
error += 256 × absY
```

After an empty Y crossing:

```text
nextY += 256
error -= 256 × absX
```

The products are calculated only during setup. v0.4.0 reads those exact 8×7-bit
products from a 64 KiB MBC5 table. The loop itself uses byte map access,
signed-error tests, one cell step, and a high-byte error increment/decrement.
Axial rays use explicit sentinel error states.

### 4.3 Safety bound

The enclosed 16×16 map guarantees a hit, but the ROM still caps traversal at 32 crossings. A deterministic ordinary-wall fallback prevents unbounded execution if malformed map data is introduced.

### 4.4 Returned hit contract

Every exact cast returns:

- hit map cell;
- crossed axis (`0 = X`, `1 = Y`);
- axis distance in Q8.8;
- wall material;
- crossing count;
- projected top edge;
- visual style;
- compact face key;
- cell coordinate along the wall plane.

The compact face key packs:

```text
bit 7      crossed axis
bits 5–6   material
bits 0–4   wall-plane coordinate
```

The along-plane cell is stored separately. Together they identify a continuous visible wall face well enough for adaptive validation.

## 5. Projection and wall descriptors

### 5.1 Perpendicular distance

The axis distance is rounded to thirty-second-tile units (`D32`, 0–511). The
mathematical result remains rounded `(D32 × correction) / component`, saturated
to 511, then mapped to projected half-height. v0.4.0 precomputes the final top
edge for all 256 components, 18 live correction values, and 512 distances in a
2,359,296-byte MBC5 table. Runtime projection therefore needs address
construction and two bank-register writes, but no multiply or divide.

The stored descriptor is the top edge:

```text
top = 48 − halfHeight
bottom = 96 − top
```

Top values are constrained so walls remain at least four pixels high and at most the full viewport height.

### 5.2 Descriptor arrays

Four 80-byte arrays in WRAM bank 1 hold:

- `RAY_TOPS`: projected top edge;
- `RAY_STYLES`: material/orientation style;
- `RAY_KEYS`: wall face key;
- `RAY_ALONG`: along-plane cell.

This 320-byte geometry representation replaces the old 3,840-byte encoded framebuffer as the renderer’s intermediate product.

## 6. Validated adaptive spans

Casting all 80 rays is unnecessary on long planar walls. v0.2.0 first casts:

- every even index `0, 2, …, 78`;
- the final index `79`.

That is 41 mandatory anchors.

For each missing odd index, interpolation is allowed only when the two anchors satisfy all conditions:

1. identical face key: same axis, material, and wall plane;
2. along-plane cells are identical or adjacent;
3. anchor top edges differ by no more than two pixels.

A safe odd top is the rounded integer midpoint. Style, face key, and along value are copied from the left anchor. Any failed condition causes an exact DDA cast for that odd column.

The slope condition is intentionally conservative. Ideal camera-plane wall height is affine across one wall plane, but quantized direction vectors, distance rounding, clipping, and the projection table can create small nonlinear steps. The two-pixel guard prevents large near-wall interpolation errors.

Research-corpus result:

- mean actual casts: 44.494 of 80;
- maximum: 60;
- face-key mismatches against full casting: 0;
- style mismatches: 0;
- top difference: mean 0.056 px, p99 1 px, maximum 1 px.

## 7. Wall styles and directional lighting

The actual crossed axis determines the wall orientation. The renderer does not infer lighting from an angle bit.

Style IDs:

| Style | Meaning |
|---:|---|
| 0 | ordinary wall, X face |
| 1 | ordinary wall, Y face |
| 2 | technology wall, X face |
| 3 | technology wall, Y face |
| 4 | door |

Each style uses a deterministic **8-row × 4 two-pixel-pair** 2bpp material matrix. Static interiors and generated edge microstrips read from the same matrix, so a wall keeps identical material bytes at its centre and silhouette.

The active families are:

- **warm plaster** (`0/1`): deliberately flat light and shadow faces, allowing silhouette and exact side lighting to define the plane;
- **vertical service panel** (`2/3`): a narrow structural frame plus sparse rivets, with no continuous horizontal rail;
- **reinforced door** (`4`): a bright plate, dark vertical spine, and asymmetric fasteners.

The builder rejects any row that changes an entire 8-pixel wall row to the contrasting wall colour. This prevents the old screen-wide bands from reappearing while retaining exact X/Y orientation shading at no runtime cost.

## 8. Boundary-only tile compositor

### 8.1 Static tile vocabulary

The permanent viewport vocabulary is mirrored in both VRAM banks:

- tile 96: ceiling;
- tile 97: floor;
- tiles 98–118: phase-free light/dark seam masks;
- tiles 119–239: 121 exact boundary-atlas patterns.

A viewport cell first uses the ceiling, floor, or seam vocabulary when its
classification permits. Remaining boundary cells are looked up by the exact
ten-byte signature described in `PERFORMANCE_V4.md`; a miss falls through to
dynamic composition.

### 8.2 Dynamic cells

A cell becomes dynamic when it contains:

- a wall top edge;
- a wall bottom edge;
- different wall heights inside the cell;
- a material/style transition.

Dynamic tiles are allocated sequentially from IDs `0–95`.

### 8.3 Two-pixel microstrip library

Each 8×8 dynamic tile is composed from four two-pixel vertical strips. A strip has:

- one of five styles;
- one of nineteen vertical states;
- one of four horizontal pair positions.

States encode:

- all ceiling;
- all floor;
- all wall;
- eight possible top-edge entries;
- eight possible bottom-edge exits.

The ROM library contains:

```text
5 styles × 19 states × 4 pair positions × 16 bytes
= 6,080 bytes
```

The first strip is copied into the destination tile. The remaining three are OR-composed. Fixed 16-byte copy/OR kernels are fully unrolled; this removes loop-control overhead from the compositor’s hottest path and restores v0.1-level frame cadence.

### 8.4 Map staging

The hidden tile map is staged as twelve complete 32-byte rows: 384 bytes. Visible columns 0–19 are written every frame. Padding columns 20–31 are initialized once to the ceiling tile, so the complete DMA source is deterministic and does not depend on WRAM power-on values.

### 8.5 Capacity

The dynamic tile buffer contains 96×16 = 1,536 bytes. The deterministic research corpus reached a maximum of 58 tiles and produced zero overflows. The ROM records current count, high-water mark, and an overflow flag. If capacity is ever exceeded, the affected cell falls back to a static wall tile and sets the flag instead of corrupting memory.

## 9. VRAM page architecture

### 9.1 Tile data

| VRAM region | Bank 0 | Bank 1 |
|---|---|---|
| tiles 0–95 | page 0 dynamic tiles | page 1 dynamic tiles |
| tiles 96–102 | shared static viewport tiles | mirrored static viewport tiles |
| tiles 240–255 | HUD/utility tiles | weapon OBJ tiles |

### 9.2 Tile maps and attributes

- tile-number page 0: `$9800`, VRAM bank 0;
- tile-number page 1: `$9C00`, VRAM bank 0;
- page 0 attributes: `$9800`, VRAM bank 1, selecting tile-data bank 0;
- page 1 attributes: `$9C00`, VRAM bank 1, selecting tile-data bank 1.

A crucial invariant is that tile numbers are always uploaded with `VBK = 0`. Uploading them with `VBK = 1` would overwrite the CGB attribute maps rather than update the visual tile IDs.

## 10. One-VBlank hidden-page commit

For each completed frame:

1. wait until a fresh VBlank;
2. select the hidden page’s tile-data VRAM bank;
3. GDMA `DYN_COUNT × 16` bytes to `$8000`;
4. set `VBK = 0`;
5. GDMA the 384-byte staging map to hidden `$9800` or `$9C00`;
6. update muzzle OAM;
7. flip LCDC bit 3;
8. return `VBK` to zero.

Hard maximum:

```text
96 dynamic blocks + 24 map blocks = 120 blocks
120 × 16 bytes = 1,920 bytes
```

Using the documented rough figure of eight microseconds per 16-byte block, the maximum is approximately 960 microseconds. A CGB VBlank is approximately 1,087 microseconds. The harness includes a forced 120-block test and verifies that both transfers begin in the same VBlank before the map flip.

The final driven-tour maximum is smaller:

```text
54 tiles × 16 + 384 = 1,248 bytes / 78 blocks
```

## 11. Main loop

```text
read joypad
update pressed/held state, movement, door, fire, flash
cast adaptive geometry
compose hidden tiles/map
wait for VBlank and commit
repeat
```

Input is sampled once per visual update. Player collision and door reach continue to use the stable v0.1.0 gameplay helpers, while wall visibility uses the exact v0.2.0 DDA.

## 12. Memory map

### WRAM0

| Address | Size | Purpose |
|---|---:|---|
| `$C000-$C5FF` | 1,536 B | generated dynamic tiles |
| `$C600-$C77F` | 384 B | hidden 12×32 tile map |

### WRAM bank 1

| Address | Size | Purpose |
|---|---:|---|
| `$D000-$D0FF` | 256 B | mutable 16×16 world map |
| `$D140-$D16F` | 48 B | stable gameplay/input state inherited from v0.1 |
| `$D200-$D24F` | 80 B | projected tops |
| `$D250-$D29F` | 80 B | wall styles |
| `$D300-$D34F` | 80 B | face keys |
| `$D350-$D39F` | 80 B | along-plane cells |
| `$D400-$D49F` | 160 B | physical-pixel projected tops |
| `$D4A0-$D53F` | 160 B | physical-pixel render styles |
| `$D540-$D5DF` | 160 B | physical-pixel face keys |
| `$D5E0-$D67F` | 160 B | physical-pixel along-plane cells |

### HRAM

`$FF80-$FFE7` is a generated 104-byte ABI for hot DDA, projection, adaptive,
atlas, and compositor scalars. The builder rejects any allocation beyond
`$FFFE`, and the test suite verifies the emitted range. The stack begins at
`$DFFF` and grows downward. The renderer does not use SRAM.

## 13. ROM layout and generated data

The deterministic Python builder emits a 4 MiB, 256-bank MBC5 image:

| Bank range | Purpose |
|---|---|
| 0 | fixed executable code, header, and startup vectors |
| 1 | ordinary engine tables, assets, atlas index, and microstrip library |
| 2–145 | exact projection-top LUT (144 banks) |
| 146–149 | exact DDA product LUT (4 banks) |
| 150–255 | reserved / `$FF` padding |

All runtime routines remain below `$4000`, so changing the MBC5 switchable
bank never removes executing code. Every arithmetic lookup restores bank 1
before the engine reads normal switchable-bank data. Major generated resources
also include packed 1,024-direction records, 80/160 camera corrections, 121
exact atlas tiles, UI/weapon data, maps, palettes, and one-/two-pixel
microstrip libraries.

The header declares CGB-only, MBC5 without RAM, and 4 MiB ROM. The ROM's unused
banks are deterministic `$FF` padding and provide room for later content.

## 14. Verification architecture

The repository contains four complementary evidence layers:

1. **Frozen v0.1.0 generator and tests** for gameplay regression.
2. **Host mathematical references** for exact cross-product DDA, adaptive spans, and byte-exact microstrip composition.
3. **Project SM83/CGB harness** for ROM instruction execution, timing, memory, GDMA, maps, attributes, OAM, joypad, audio-register effects, and rendered images.
4. **External checklist** for independent emulators and original hardware.

The first three are automated. The fourth remains pending and is intentionally not claimed by the software report.

## 15. Extension seams

The geometry-first representation is intended to support later work:

- a compact wall depth buffer for billboard sprites;
- hit detection and damage;
- animated doors;
- dynamic tile deduplication;
- certified wider affine spans;
- wall-continuation prediction;
- multiple banked levels;
- richer static microtile vocabularies;
- stable per-face material phase, distance LOD, and certified palette bevels;
- floor/ceiling effects where budgets permit.

Any extension should preserve face identity, dynamic-tile bounds, one-VBlank publication, and the frozen regression oracle.
