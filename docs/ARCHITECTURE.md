# Lupine 3D 0.7.0-beta.4 architecture

Lupine is a CGB-only 4 MiB MBC5 engine with no cartridge RAM. Python generates SM83 code, tables and original graphics. Runtime uses double-speed execution, native tiles, two VRAM banks, two BG maps and hardware 8×16 objects.

## Frame and simulation ownership

VBlank interrupts sample controls into a timestamped ring queue; they never simulate. The renderer cooperatively yields at ray and tile-column boundaries. Each yield saves render HRAM, selects WRAM bank 2, consumes at most four simulation packets, restores bank 1 and resumes. Queue debt is retained.

At frame start, live map/player/world/actor records are copied through a 457-byte fixed-WRAM staging buffer into bank 1. All rendering, depth tests, animation selection and publication use that immutable snapshot. Bank 2 continues moving actors and doors while the snapshot renders.

A full frame proceeds through 80 adaptive descriptors, 160 physical columns, six folded tile rows, palette attributes, masked entity patterns and shadow OAM. Before casting, a 290-byte exact comparison checks camera, map, door records, configuration and reload generation. A hit retains the matching wall view/depth and renders only entities, fixtures and HUD. Publication occurs only when its complete packet is ready. See [wall reuse](WALL_REUSE.md).

## Cartridge banks

| Banks | Contents |
|---|---|
| 0–1 | Resident engine, level records and hot metadata |
| 2–145 | Paired projection top/depth LUT: 2,359,296 bytes |
| 146–153 | Complete 8×8 product LUT: 131,072 bytes |
| 154 | Alternate atlas/dictionary |
| 155 | Physical segments: 1,024 bytes; oriented-face profiles: 1,024 bytes |
| 156 | Cold boot assets and startup map: 9,514 bytes |
| 157–172 | Q14 camera directions: 262,144 bytes |
| 173–255 | Unallocated cartridge capacity |

Banked lookups restore ROM bank 1. Executing hot lookup routines stay below $4000; the builder asserts the boundary. Resident image ends at $73CD (29,309 emitted bytes), leaving 3,123 bytes below $8000. Full 16×16 multiplication uses four table partial products, skipping zero terms. Product-bank selection uses three rotates and a mask. Unaligned fixture records follow the hot tables; the startup map lives in cold bank 156. The loader restores bank 1 after copying it.

## Geometry and projection

Positions are Q8.8 on a 16×16 map; angles are 256 units/turn. Static walls use material 1/2, doors 3 and empty cells 0.

The coarse signed-error DDA maintains next-boundary distances and the sign of `nextX*absY - nextY*absX`. For supported camera records, an error certificate determines whether coarse and Q14 traversal must choose the same crossing. At the first uncertain crossing, compute the fine 32-bit error at the current cell and continue in Q14. Earlier certified cells need no retraversal. Degenerate coarse components and casts beginning inside a door still initialize from the player. See the [continuation proof and performance contract](RUNTIME_PERFORMANCE.md).

A 1,024-byte direction page per camera angle contains 80 pair-centre vectors, 160 physical-centre vectors and one centre hitscan vector. The 64 retained severe tail rays choose their floating-oracle cell/axis in generated code. This does not eliminate every continuous-camera error.

Projection still uses the paired integer Q5 LUT. Cast depth is corrected perpendicular Q5 distance, saturated to 255. Adaptive interpolation uses conservative height-class depth bounds. Wall geometry is not a floating-point continuous oracle.

### Sliding doors

A door is a finite segment at the centre of its cell, with an authored normal axis. Fraction F exposes the along-panel interval [0,F); the remaining [F,256) is solid and translates into the positive-axis jamb. Fully open state removes the cell.

Wall rays, current-pose hitscan and exact player-to-enemy LOS share this plane intersection. Axis-separated player/actor collision expands the same panel by radius 56/256 tile. Door intersection alone uses bounded integer division; ordinary grid crossing does not. The sixteen quotient bits are processed in four groups. BC holds the quotient, HL the remainder, DE the divisor, and a two-byte stack entry holds the group count. Overflow leaves the original numerator for the existing rejection path.

Each opening takes 32 simulation ticks (eight fraction units/tick). Rays may pass before a radius-sized player fits. There are four independent door records and an all-enemies-dead exit lock. Closing/reversing/crushing doors are not implemented.

### Reconstruction and physical identity

41 mandatory anchor rays are cast. Odd samples interpolate only when plane/material, physical segment, surface profile, adjacency and a two-pixel slope bound agree. Other samples recast. The physical-column pass selectively recasts discontinuities.

Static materials can share one physical segment on a continuous exposed plane. Doors split segments; latent jamb faces receive IDs before opening. Surface colour metadata never defines physical continuity.

| Address | Bytes | Snapshot descriptors |
|---|---:|---|
| $D200 / $D250 | 80 each | Ray top / style |
| $D300 / $D350 | 80 each | Ray face key / along-face cell |
| $D400 / $D4A0 | 160 each | Physical top / style |
| $D540 / $D5E0 | 160 each | Physical face key / along |
| $D680 / $D6D0 | 80 each | Ray depth / segment |
| $D800 | 160 | Physical segment |
| $DE00 | 80 | Ray surface profile |
| $DE80 | 160 | Physical surface profile |

## Tile and palette composition

| BG IDs | Purpose |
|---|---|
| 0–95 | Dynamic boundaries, 96-pattern capacity |
| 96–97 | Ceiling/floor |
| 98–118 | Phase-free static wall/edge vocabulary |
| 119–239 | Full 121-pattern exact atlas |
| 240–255 | Retained legacy art; unused by the active HUD |

Signed BG addressing maps IDs 0–127 to $9000–$97FF and 128–255 to $8800–$8FFF. Atlas upload splits at ID 128. Unsigned OBJ patterns occupy the non-overlapping $8000–$87FF region in both banks.

The active HUD uses 78 bank-0 patterns at $8200–$86DF. A line-96 STAT interrupt switches LCDC.4 to unsigned addressing for its six rows; VBlank restores signed addressing. Masked world OBJ pages occupy only $8000–$81FF. Weapon/UI OBJ art resides at $8400–$853F in bank 1. See [the complete art allocation](SABLE_OUTPOST.md).

Only six upper rows are composed. Lower rows reuse IDs with Y-flip and a matching floor palette; `LUPINE3D_FOLDED=0` retains the unfolded oracle. This relies on symmetric full-height walls and does not support pitch or arbitrary sector heights.

Per-face content selects structure, machinery or functional-door profiles. A uniform eight-pixel group selects its profile's palette; a mixed group falls back to neutral to avoid inventing a material edge. Upper/lower palette pairs are 0/2, 5/6 and 3/4 respectively; HUD uses 1. All share consistent ceiling/floor colours.

No eye-height rail or full-height decorative cell ribs are emitted. True corners receive narrow dark edges; doors have run-derived frames and a brighter centre signal.

## Entities and OAM

Hardware 8×16 mode uses aligned even/odd pattern pairs. Four fixed 16-byte slots reuse Sentinel AI, health, hurt/death animation and dropped pickups. The compiler accepts one to four spawns; the production level uses one.

Three pre-scaled sizes—16×32, 16×16, 8×16—share the wall camera focal length and project feet from forward depth. Hysteresis prevents threshold chatter. Candidate actors are depth-sorted nearest first. Hitscan selects the nearest aimed candidate and then performs a fresh wall query, never trusting stale render visibility.

Every eight-pixel strip computes a visibility bitmask against the 80-sample conservative depth buffer. Both bitplanes of its ROM-source cel are ANDed with that mask into staging. Mask patterns alternate banks using an independent OBJ owner; fully occluded strips allocate nothing. BG and OBJ owners may differ after a cached presentation.

OAM entries 0–9 reserve weapon, crosshair and muzzle flash. World entries 10–25 admit at most 16 objects, and at most four world objects per scanline. The Y-selected scanline budget includes X-offscreen hardware objects. Unused entries are hidden. The bounded world limit leaves room for UI without exceeding 40 total / ten per scanline.

Sixteen authored wall fixtures share that pool after actors and the exit. At most four fixture objects are submitted. Their masks require physical segment and along-face cell agreement. Pre-scaled cels sit at the upper wall quarter; door access marks translate with the sliding panel. The completed world-copy staging buffer temporarily holds fixture visibility, preserving wall attributes across cached updates.

## Fixed and banked WRAM

| Range | Purpose |
|---|---|
| $C000–$C5FF | Dynamic BG patterns |
| $C600–$C77F | Hidden tile map |
| $C800–$C89F | Shadow OAM |
| $C8A0–$C8B2 | Fixed render/AI scratch, published entity X and bulk-copy remainder |
| $C8B3–$C8B9 | OBJ owner, cache flags, presentation serial and reload generation |
| $C8D0–$C8DD | 16-bit clocks, queue cursors, budget and diagnostics |
| $C900–$CAC8 | World-copy staging, 457 bytes; first 256 reused for fixture visibility after copy |
| $CB00–$CB6E | HRAM save area |
| $CC00–$CCFF | 64×4 input ring; 63 usable records |
| $CD00–$CDFF | Exact cached map key |
| $CE00–$CFFF | Reserved stack, top $CFFF |
| $D000–$D7FF | Banked map/player/descriptors/world/scratch |
| $D8A0–$D8FF | Wide ray/door/mask/profile scratch |
| $D900–$D98F | 144 scanline admission counters |
| $D990–$D9CF | Four actor slots |
| $D9D0–$D9D7 | Actor count and sorting scratch |
| $D9E0–$D9F4 | Wall-fixture scratch and saved projection |
| $D9F5–$D9FF | Eleven prepared HUD tile IDs |
| $DA00–$DBFF | 32 masked patterns |
| $DC00–$DD7F | Hidden attribute packet |
| $DE00–$DF1F | Ray and physical surface buffers, including alignment gap |
| $DF20–$DF41 | Exact camera/configuration/door/generation key |

HRAM uses $FF80–$FFEE (111 bytes). The ten-byte OAM DMA stub uses $FFF4–$FFFD. ISR-owned input bytes are excluded from render-save restoration.

Queue entries contain a 16-bit tick, held state and rising edges. Overflow never overwrites pending entries: it increments a saturating diagnostic and preserves an OR-latched edge. It is finite capacity, not an unlimited event log.

## Publication

Maximum packet: 96 dynamic BG blocks + 32 masked OBJ blocks + 24 attribute blocks + 24 map blocks = 176 GDMA blocks / 2,816 bytes, plus HUD writes and OAM DMA.

When dynamic-plus-mask patterns exceed 24, hidden dynamic patterns upload in one VBlank; masked patterns, attributes, map, HUD and OAM finish together in the next. The first stage is at most 96 blocks; final stage at most 80. Small packets fit one VBlank. The old complete frame stays visible until publication. HUD values are computed before waiting; only the eleven prepared IDs are written during publication. OAM DMA waits 160 M-cycles in HRAM. Boundary tests require completion before line 153.

With optional reprojection enabled, more than 24 masked patterns trigger an additional wait after their upload. That stress case can use three VBlanks to preserve headroom for the published-X copy; the default build uses at most two.

Tile numbers upload with VBK=0; attributes with VBK=1; BG pattern bank follows the hidden BG page. Mask patterns target the hidden OBJ bank independently. LCDC map selection changes only after the matching complete full packet. A cached update uploads only 0–32 mask patterns plus HUD/OAM in one VBlank and leaves the viewport maps and BG owner untouched. `PRESENT_SERIAL` advances after either path; physical BG flips are counted separately. SameBoy checks GDMA/OAM starts, final publication and writes against the published mask bank.

## Optional reprojection

`LUPINE3D_REPROJECTION=1` enables a ±4-pixel SCX shift at VBlank. Only published world OAM X moves with the BG; foreground UI remains fixed. The ISR reads immutable published X, not the next shadow packet. Exact commits reset the offset.

Guard columns extend the nearest edge tile/attribute; they are not extra rendered rays. A line-96 STAT split resets SCX for the HUD, not a Window-layer conversion. The experiment remains off by default pending perceptual and physical LCD testing.

## Content and modules

`levels.py` compiles JSON legality/readability, physical segments, oriented-face profiles and fixtures. `precision.py` owns Q14 tables/traversal; `door_geometry.py` shared panel queries; `simulation.py` queues/bank snapshots; `actors.py` bounded actor reuse; `masked_entities.py` LOD/masks/admission; `surfaces.py` palette packets; `artwork.py` native graphics; `world_decor.py` mounted fixtures. The legacy-named `lupine3d_v4` package remains a stable import path, not a version claim.

The active map is compiled into the cartridge and loaded into live WRAM. Multiple spawns and per-face profiles are supported; streamed multi-level asset loading is not yet a runtime feature.
