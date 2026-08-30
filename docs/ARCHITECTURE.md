# Lupine 3D 0.6.3 architecture

## Design target

Lupine 3D is a CGB-only first-person engine for a 4 MiB MBC5 cartridge with no external RAM. It uses double-speed SM83 execution, two VRAM banks, two BG maps, CGB attributes, GDMA, shadow OAM, VBlank/STAT interrupts, joypad input and audio hardware.

The renderer represents geometry as compact column records and converts those records into reusable or generated 8×8 tiles. The Living World layer projects entities against the same wall-depth certificates and submits them through OAM.

Hard constraints:

- 160×96 world viewport and 48-pixel HUD;
- 80 two-pixel geometry samples and 160 reconstructed physical columns;
- exact wall-cell, side and material selection for the quantized runtime ray;
- no floating point at runtime and no general division in DDA traversal;
- no fixed 3,840-byte framebuffer;
- maximum BG commit of 1,920 bytes / 120 GDMA blocks;
- maximum 40 OAM entries and 10 visible objects per scanline;
- deterministic CGB-only MBC5 image.

## Runtime sequence

1. Atomically consume VBlank-latched input.
2. Apply radius movement, fire or begin a door interaction.
3. Advance the door and low-frequency AI.
4. Cast 41 mandatory anchors and exact fallback rays.
5. Produce 80 wall records with top, style, face, along, depth and segment.
6. Reconstruct 160 physical columns with exact edge recasts.
7. Compose the 20×12 hidden tile page.
8. Transform the Sentinel, wall-clip its strips and write shadow OAM.
9. Wait for a fresh VBlank.
10. GDMA dynamic tiles and the complete hidden map.
11. Publish OAM if the remaining VBlank budget is safe.
12. Flip the BG map only after hidden data is complete.

The VBlank ISR samples controls but never mutates the pose or simulation. A render therefore sees one stable world snapshot.

## Cartridge layout

| Region | Purpose |
|---|---|
| Banks 0–1 | Resident engine, active level, entity assets and lookup metadata |
| Banks 2–145 | 2,359,296-byte exact projection-result table |
| Banks 146–149 | 65,536-byte exact DDA product table |
| Bank 150 | Inactive VRAM profile's atlas and dictionary |
| Bank 151 | Active level's 1,024-byte surface-segment table |
| Remaining banks | Available for levels, art and future content |

Every hot banked lookup restores conventional ROM bank 1 before returning.

## World geometry

Positions are Q8.8; the integer byte selects the map cell. The active grid is 16×16 in WRAM bank 1. Material 0 is empty, 1 and 2 are wall families, and 3 is a door.

The angle is an unsigned byte spanning one turn. Rays use a 1,024-direction table at magnitude 127, 80 camera-plane offsets, 160 physical offsets, and cosine corrections generated on the host.

### Signed-error DDA

Each ray crosses only cell boundaries. The next X/Y boundary is selected from the sign of:

```text
error = nextX × absY − nextY × absX
```

Initial 8×7-bit products are read exactly from the 64 KiB MBC5 product table. The loop then updates only the map coordinate, boundary distance and error high byte. An enclosed map guarantees a hit; a 32-crossing bound provides deterministic fallback for malformed data.

### Projection

Axis distance is rounded to Q5 tiles. The mathematically exact projected top for every live `(component, correction, distance)` tuple is read from the banked projection table. The wall descriptor stores:

- hit cell and crossed axis;
- material and projected top;
- compact face key and along-face cell;
- conservative corrected perpendicular depth in Q5;
- continuous exposed-surface segment ID.

## Descriptor memory

| Address | Bytes | Contents |
|---|---:|---|
| `$D200` | 80 | `RAY_TOPS` |
| `$D250` | 80 | `RAY_STYLES` |
| `$D300` | 80 | `RAY_KEYS` |
| `$D350` | 80 | `RAY_ALONG` |
| `$D400` | 160 | `PIXEL_TOPS` |
| `$D4A0` | 160 | `PIXEL_STYLES` |
| `$D540` | 160 | `PIXEL_KEYS` |
| `$D5E0` | 160 | `PIXEL_ALONG` |
| `$D680` | 80 | `RAY_DEPTH` |
| `$D6D0` | 80 | `RAY_SEGMENT` |
| `$D800` | 160 | `PIXEL_SEGMENT` |

The 80-ray pass always casts even indices plus index 79. An odd midpoint is reconstructed only when both anchors agree on face and segment identity, are adjacent along the face, and differ by no more than two top pixels. Otherwise that ray is cast exactly. The 160-column pass performs additional exact recasts at detected discontinuities and expands segment identity for presentation classification.

## Tile compositor

The permanent BG vocabulary is:

| Tile IDs | Purpose |
|---|---|
| 0–95 | Dynamic boundary tiles for the current hidden page |
| 96–97 | Ceiling and floor |
| 98–118 | Phase-free wall/seam vocabulary |
| 119–198 | 80-pattern entity-heavy exact atlas |
| 199–239 | Entity-profile OBJ art (39 currently used) |
| 240–255 | HUD/weapon assets |

The renderer-heavy profile replaces 119–239 with its 121-pattern exact atlas and exposes no entity art. Both atlases contain 255 exact ten-byte signatures. The build-selected active profile is resident and the inactive profile is banked. A cache miss falls through to the unchanged microstrip compositor.

An 8×8 dynamic tile is built from one- or two-pixel vertical microstrips. Only cells containing a silhouette, height change or style transition are dynamic. The hard buffer is 96 patterns / 1,536 bytes.

### Surface grammar

The base fills remain phase-free: orientation selects light or shadow, while strong detail is attached only to actual geometry. Static material 1 and 2 cells share a physical segment when they continue the same exposed plane. A segment change receives one dark pixel; a material change on the same segment is a soft fill transition; ordinary cell boundaries produce no full-height mark. Door runs derive narrow frames and a wider two-pixel centre spine from their projected extent.

The eye-height machinery rail is disabled. At a half-height camera it necessarily projected to screen row 48 at every distance, so it behaved as a false horizon and forced additional dynamic composition. The entity-heavy profile now retains the same 23-tile static wall vocabulary without either rail variant.

## VRAM pages and publication

| VRAM resource | Bank 0 | Bank 1 |
|---|---|---|
| Tiles 0–95 | Page 0 dynamic pixels | Page 1 dynamic pixels |
| Shared BG tiles | Mirrored | Mirrored |
| `$9800` | Page 0 tile numbers | Page 0 attributes |
| `$9C00` | Page 1 tile numbers | Page 1 attributes |
| Tiles 240–255 | HUD utilities | Weapon OBJ art |

Tile numbers are always uploaded with `VBK=0`. A completed page uses at most 96 dynamic GDMA blocks plus 24 map blocks. LCDC bit 3 changes only after both transfers start in the same VBlank.

The lower 48-pixel HUD uses a warning separator and dark-metal status plate. Two-digit health and `00`/`01` exit-objective fields are written to both BG maps. As with shadow OAM, the eight tile-number writes are deferred when `DYN_COUNT > 72`, preserving the certified worst-case VBlank publication.

## Living World memory and OAM

Gameplay state occupies `$D720–$D779`. It includes the selected VRAM profile, Sentinel transform/state, player health, pickup/exit state, a four-record door table, generic projection coordinates, LOS scratch and radius-collision scratch.

Shadow OAM occupies `$C800–$C89F`. Entries 0–17 are reserved for foreground UI, while 18–39 are available to world entities. A ten-byte OAM-DMA routine lives at `$FFF4–$FFFD`; hot scalar state uses 111 bytes at `$FF80–$FFEE`, leaving the two regions disjoint.

The entity renderer supports an 8×16 far LOD and 16×32 near LOD. Near left/right strips independently compare entity Q5 depth with the corresponding wall-depth samples. Fully hidden actors consume no OAM. The active exit uses the same projection certificate as a pulsing 8×8/16×16 world beacon.

If the wall compositor exceeds 72 dynamic tiles, OAM DMA is deferred to protect the BG commit's worst-case VBlank budget. The shadow image remains coherent while deferred.

## Simulation and interaction

The Sentinel has dormant, patrol, chase, attack, hurt and dead states. AI ticks every fourth VBlank input sample. Cell-space Bresenham traversal tests line of sight against the exact active map. Player hitscan uses the projected, wall-visible Sentinel record.

Player collision is axis-separated with a Q8 radius of `$38`. Up to four doors open independently over eight fraction steps and remain solid until their panels have fully retracted, keeping rays, collision and AI sight consistent. Door flags support a Sentinel-gated exit lock with distinct blocked feedback.

The content compiler reads legacy `lupine-level-v1` renderer fixtures and current `lupine-level-v2` gameplay JSON. Version 2 validates player-radius spawn clearance, minimum enemy separation, door frames and IDs, a reachable completion cell, and one Sentinel-locked exit door. See [Living World architecture](LIVING_WORLD_V6.md) for the content and entity contracts.

## Optional reprojection

When compiled with `LUPINE3D_REPROJECTION=1`, VBlank input can shift the previously completed 3D page by ±4 pixels. Guard map columns hide the exposed edges. Exact page publication resets the shift, and an LYC=96 STAT interrupt restores `SCX=0` for the HUD.

The default remains disabled until independent emulator and original-CGB LCD testing is complete.

## Generated engine footprint

The current resident engine is 31,053 bytes, ending at `$7A9D`, and still fits banks 0/1. Hot HRAM uses 111 bytes. The ROM remains 4 MiB so the arithmetic tables and both scene profiles coexist with substantial capacity for banked content.
