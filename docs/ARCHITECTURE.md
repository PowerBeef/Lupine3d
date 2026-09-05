# Lupine 3D v0.8 architecture

Lupine generates a CGB-only, 4 MiB MBC5 cartridge with no cartridge RAM.
Python emits SM83 machine code, fixed-point tables and native 2bpp assets.
The console runs in double-speed mode using tiles and 8×16 hardware sprites;
there is no framebuffer. This document describes the default slim/Sable build.
Historical beta.6 measurements are retained in [its test report](TEST_REPORT_BETA6.md).

## Frame, input and simulation ownership

VBlank samples controls into a timestamped ring queue. Simulation runs at
cooperative ray/column yields, consuming at most four queued packets per service.
It owns WRAM bank 2. Queue debt and button edges survive slow rendering.
The narrow production yield contexts preserve live registers/state; the generic
full-HRAM ABI remains a diagnostic reference.

At snapshot creation, 457 bytes of map/player/world/actor state pass through
fixed WRAM into bank 1. Geometry, animation, HUD and OAM all use that immutable
snapshot while simulation continues in bank 2. Animation uses accepted ticks,
not host time or the number of rendered frames.

An exact 290-byte wall-key comparison covers camera, map, door state,
configuration and reload generation. A miss casts/reconstructs the view,
composes tiles, prepares masks/entities and builds a complete publication packet.
A hit retains matching walls/depth and refreshes entities/HUD only. Bank ownership
for the published BG and OBJ patterns can consequently differ. See
[wall reuse](WALL_REUSE.md).

## Display and geometry

| Profile | World | Horizon | HUD | World rows | Folded rows | STAT switch |
| --- | --- | --- | --- | --- | --- | --- |
| `slim` (default) | 160×120 | 60 | 24 px | 15 | 8 | 120 |
| `compact` | 160×112 | 56 | 32 px | 14 | 7 | 112 |
| `legacy` | 160×96 | 48 | 48 px | 12 | 6 | 96 |

Horizontal FOV and projection scale are unchanged. Taller profiles reveal more
vertically; they do not stretch the old image. The weapon is anchored to the
world's lower edge. The STAT handler changes BG tile addressing at the HUD
boundary. Legacy plus legacy art/animation-off reproduces the beta.6 ROM.

Positions use Q8.8. Prepared directions and crossing certificates use Q14 and
the existing tie convention; terminal distance/projection use Q5. Forty even
anchors plus anchor 79 feed adaptive pair reconstruction, physical edge recasts
and conservative interpolation over 160 columns. Surface identity is independent
of material colour. Collision, wall rays, LOS and hitscan share finite door
geometry. Physical-depth and higher-precision actor experiments remain disabled;
production height-derived mask depth is not labelled a continuous geometric query.

The signed-BG compositor folds upper/lower wall tiles using vertical attributes.
Legacy/compact use 19 logical strip states and nine stored states; slim needs
21/11 because the centre tile can contain both boundaries (states 19/20).
The fixed reference retains all logical states. The unfolded diagnostic reads
bank 237 through a fixed 16-byte scratch, then restores bank 1.

Static classification precedes exact atlas lookup. The checked-in atlas was
trained in the legacy domain; eligible keys are translated for larger horizons,
and misses use the exact compositor. `make atlas-check` verifies legacy training
assets; Sable validation checks production lookups. This release does not retrain
or replace the atlas. Dynamic allocation is bounded to 96 patterns.

## ROM allocation

| Banks | Ownership |
| --- | --- |
| 0–1 | Resident engine, level records and hot metadata |
| 2–145 | Direct paired projection top/depth tables: 2,359,296 bytes |
| 146–153 | 8×8 multiplication tables: 131,072 bytes |
| 154 | Alternate atlas/dictionary |
| 155 | Physical segments and oriented-face profiles |
| 156 | Cold startup/map/art assets: 12,810 bytes |
| 157–172 | Q14 camera directions: 262,144 bytes |
| 173–236 | Prepared ray metadata: 1,048,576 bytes |
| 237 | Unfolded diagnostic strip allocation: 8,064 bytes |
| 238–255 | Unallocated cartridge capacity |

For the qualified v0.8 ROM, fixed code ends at `$3910` (1,776 bytes below
`$4000`); resident data ends at `$73CD`, leaving **3,123 bytes** below `$8000`.
The required reserve remains 3,000 bytes. Saving resident table data does not
increase the fixed-code ceiling. Code that changes ROM banks stays below `$4000`
and restores bank 1 before returning. Prepared scalar records 0–240 and the
raw-query sentinel are unchanged; disabled packets own only records 241–250.

## RAM and video allocation

`allocation.py` checks ranges and lifetimes; the build manifest records resolved
allocations. Important owners are:

| Resource | Ownership |
| --- | --- |
| Fixed WRAM `$C600–$C7DF` | 480-byte world map staging |
| Fixed WRAM `$C8E0–$C8EF` | Unfolded strip scratch, outside the enlarged map |
| Fixed WRAM `$CE00–$CFFF` | 512-byte reserved stack |
| WRAM bank 1 | Immutable render snapshot, descriptors, masks and staging |
| Bank 1 `$D3D8–$D3E7` | 16-byte HUD publication packet |
| Bank 1 `$DC00–$DDDF` | 480-byte attribute staging |
| WRAM bank 2 | Authoritative live simulation state |
| WRAM bank 3 | Reserved 128×32-byte dynamic-cache experiment |
| WRAM bank 4 | Reserved foreground buffers/event queue experiment |
| WRAM banks 5–7 | Available |
| HRAM | 111 state bytes and a separate 10-byte DMA stub |
| BG patterns | Static/atlas tiles plus at most 96 dynamic patterns |
| Bank-0 HUD patterns | 94 of 96, `$8200–$87DF` |
| Bank-1 OBJ patterns | 86 preloaded weapon/UI plus 32 masked world patterns |
| OAM | 40 hardware objects; world pool 16, at most four per scanline |

The 242-pattern enemy/fixture **ROM source dictionary** is distinct from resident
VRAM tile IDs. Masked strips are composed into the bounded pool. Hardware selects
at most ten objects per scanline, including Y-overlapping objects hidden in X.
Living actors and gameplay pickups have priority over cosmetic death sprites.

## Publication and timing

A full packet contains at most 176 GDMA blocks: 96 BG, 32 OBJ, 24 map and 24
attribute blocks. The retained bulk map transfers cover twelve rows. Slim's
three additional rows require **192 bounded CPU-copy bytes** into hidden maps:
96 map + 32 attribute bytes during the pattern stage, then 64 attribute bytes
in the final commit. HUD and OAM are committed with matching bank/map state.

The first stage remains bounded to 96 blocks. Above 48 dynamic+mask patterns,
an additional VBlank precedes the pattern stage. Full packets therefore use
two or three VBlanks; cached packets use one. Writes must finish before line
153. No partially prepared row or mask bank becomes visible. GDMA and OAM DMA
halt CPU execution and are counted as work, not background transfers.

The steel HUD retains a 16-byte packet: four health IDs, one enemy count,
two caption IDs, three status IDs and six portrait IDs. Text starts at HUD y=4
and y=10. Each main status ID names a vertical tile pair; its lower ID is written
into the third HUD row on both maps. The final one-pixel spacing fix adds six
map writes, **108 CPU T-cycles** (about 12.9 µs), without extra pattern DMA.
See [HUD layout and captures](STEEL_HUD.md).

CPU T-cycles are canonical: double-speed CPU frequency is 8,388,608 Hz. One LCD
interval remains 70,224 base-speed clocks, about 16.74 ms (140,448 double-speed
CPU T-cycles). Full geometry updates, cached presentations and experimental
foreground publications are separate counters. [Current evidence](TEST_REPORT.md)
documents the accepted visual/performance tradeoff; ten sustained full updates/s
is a target, not an achieved guarantee.

## Art and animation

Original generated concepts are adapted into indexed PNGs and deterministically
compiled into 2bpp data. Builds do not generate images or download assets.
The shotgun has five preloaded cels; flashes have two. Sentinels have twelve
frames at each of three deliberately authored sizes. The HUD uses the approved
armoured helmet with normal/blink/hurt/dead states. Snapshot timing selects cels;
OAM references animate the weapon without runtime pattern uploads.

Accepted fire restarts recoil and preserves pending flash feedback until it is
published. Gameplay death happens immediately; a short three-pose death visual
is cosmetic and can be omitted under capacity pressure. Scene generation,
restart and tick wraparound preserve coherent state. Details and source locations
are in [Sable Outpost](SABLE_OUTPOST.md).

## Feature gates and references

Compact strips, invariant camera setup, narrow yields and CPU attribute padding
are the accepted exact-output improvements. Sable art/animation and slim display
are enabled by the owner's explicit acceptance of their measured cost. The
original mean/p95 half-gains budget remains recorded as failed.

Dynamic caching, packet traversal, physical depth, actor precision, scanline
admission, paged projection, near-field precision and foreground publication
remain experiments. Reprojection is disabled. Build flags and format versions
are recorded in the manifest; unsupported explicit combinations fail.
[Rendering milestone evidence](RENDERING_IMPLEMENTATION.md) describes the earlier
performance work, while [development guidance](DEVELOPMENT.md) explains how to
build references and qualify changes without overwriting historical evidence.
