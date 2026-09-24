# Lupine 3D architecture

Lupine generates a CGB-only, 4 MiB MBC5 cartridge with no cartridge RAM.
Python emits SM83 machine code, fixed-point tables and native 2bpp assets.
The console runs in double-speed mode using tiles and 8×16 hardware sprites;
there is no framebuffer. This document describes the default slim/Sable build.
Historical beta.6 measurements are retained in [its test report](../archive/TEST_REPORT_BETA6.md).

## Frame, input and simulation ownership

VBlank samples controls into a timestamped ring queue. Simulation runs at
cooperative ray/column yields, consuming at most four queued packets per service.
It owns WRAM bank 2. Queue debt and button edges survive slow rendering.
The narrow production yield contexts preserve live registers/state; the generic
full-HRAM ABI remains a diagnostic reference.

At snapshot creation, 496 bytes of map/player/world/actor state pass through
fixed WRAM into bank 1 (`WORLD_COPY_BYTES`). The 256-byte map among them is
copied only when it changed: every live map writer (a door finishing its
opening, the empty world's instant door, `load_level`) increments
`LIVE_MAP_GEN`, and `begin_frame_snapshot` skips the map while the generation
it last copied, `SNAP_MAP_GEN`, still matches (`tests/test_snapshot_map.py`). Geometry, animation, HUD and OAM all use that immutable
snapshot while simulation continues in bank 2. Animation uses accepted ticks,
not host time or the number of rendered frames.

An exact 302-byte wall-key comparison covers camera, map, six door records,
configuration and reload generation. A miss casts/reconstructs the view,
composes tiles, prepares masks/entities and builds a complete publication packet.
A hit retains matching walls/depth and refreshes entities/HUD only. Bank ownership
for the published BG and OBJ patterns can consequently differ. See
[wall reuse](../archive/WALL_REUSE.md).

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
the existing tie convention; terminal distance/projection use Q5. A ray whose
Q8 direction is exactly axial can still cross the plane its zero component is
perpendicular to, because the traversal follows the finer Q14 order; the
projection table's component-zero slice saturates to the far clamp for it, as
the host model does. Forty even
anchors plus anchor 79 feed adaptive pair reconstruction, physical edge recasts
and conservative interpolation over 160 columns. Surface identity is independent
of material colour. A shot lands when the actor's Q5 depth is below the centre
ray's wall depth plus a quarter-cell slack (`HITSCAN_DEPTH_SLACK`), so an actor
pressed flush against a wall stays hittable while one behind a wall or a closed
panel, at least half a cell further, is not. Collision, wall rays, LOS and hitscan share finite door
geometry. Physical-depth and higher-precision actor experiments remain disabled;
production height-derived mask depth is not labelled a continuous geometric query.

A reconstructed midpoint's mask depth comes from its projected top through
`top_depth_lut`: the nearest depth that projects to that top. Near a wall the
half-height jumps several pixels a Q5 step, so some tops have no depth; on
the compact and slim profiles such a top takes the depth of the nearest
class on the near side, which is never farther than the wall
(`tests/test_top_depth_lut.py`). Before that, an empty top read 255 and an
enemy behind a wall within about a cell and a half showed through it at
that sample. The legacy profile keeps its table byte for byte, gaps included,
as the contract it is.

Slim builds compose every wall with the textured row-window kernel
(`textured.py`, [textured walls](textured-walls.md)): textures are mirrored
about the horizon, so the lower half is the upper half's Y-flipped patterns,
and up to 238 dynamic pattern ids (below 128 at `$9000`, the rest at `$8800`)
are composed through a 96-slot ring in fixed WRAM that HBlank DMA drains.
`texture_reference.compose_kernel` is its byte-exact host model. The rest of
this section describes the flat microstrip compositor that the historical
legacy and compact profiles keep.

The signed-BG compositor folds upper/lower wall tiles using vertical attributes.
Legacy/compact use 19 logical strip states and nine stored states; slim needs
21/11 because the centre tile can contain both boundaries (states 19/20).
The fixed reference retains all logical states. The unfolded diagnostic reads
bank 237 through a fixed 16-byte scratch, then restores bank 1.

Static classification precedes exact atlas lookup. The checked-in atlas was
trained in the legacy domain; eligible keys are translated for larger horizons,
and misses use the exact compositor. `make atlas-check` verifies legacy training
assets; Sable validation checks production lookups. This release does not retrain
or replace the atlas. Flat dynamic allocation is bounded to 96 patterns.

## ROM allocation

| Banks | Ownership |
| --- | --- |
| 0–1 | Resident engine, level records and hot metadata |
| 2–145 | Direct paired projection top/depth tables: 2,359,296 bytes |
| 146–153 | 8×8 multiplication tables: 131,072 bytes |
| 154 | Alternate atlas/dictionary (inactive on slim) |
| 155 | Texture row windows (three blocks per bank) |
| 156 | Cold startup/art assets |
| 157–172 | Q14 camera directions: 262,144 bytes |
| 173–236 | Prepared ray metadata: 1,048,576 bytes |
| 237 | Unfolded diagnostic strip allocation: 8,064 bytes |
| 238 | Cold raw ray vectors and camera-plane offset/correction tables |
| 239 | Authored full-screen presentation (title, results, intermission, episode openings and closings) |
| 240 | Songs and the sequencer's note periods |
| 241–244 | Campaign levels, five per bank in page-aligned slots |
| 245 | Weapon cel sheets, streamed into the OBJ window one at a time |
| 246, 248–255 | Texture row windows (three blocks per bank) |
| 247 | Texture slopes, height-class rows and stride classes |

No bank is free on the slim build; `docs/reference/memory-map.md` is generated
from the manifest and gives every range.

### Campaign levels

Level selection is a runtime value, not an assembled immediate. Compiled
levels are packed five to a bank from `LEVEL_ROM_BANK_BASE` (241) in
page-aligned slots of `LEVEL_SLOT_PITCH` (2,816) bytes, at fixed offsets
inside the slot; the resident `level_directory` gives `select_level` each
level's bank and slot page, and every reader adds the page to the high byte of
its offset (`add_level_page`). The first slot's offsets are:

| Offset | Contents |
| --- | --- |
| `$4000` | Physical segment ids, 1,024 bytes, indexed `cell * 4 + side` |
| `$4400` | Oriented-face surface profiles, same index |
| `$4800` | The 16×16 world map |
| `$4900` | 24-byte header: dimensions, profiles, spawn, primary actor, exit, and the door/actor/fixture counts and pickup value the loader reads |
| `$4920` | Six fixed-capacity door records |
| `$4950` | Six bounded actor slots |
| `$49B0` | Up to sixteen wall-mounted fixture records |

`lookup_segment_id` reads the segment and its surface profile through one
pointer, so the surface table must stay exactly 1,024 bytes above the segment
table. `LEVEL_INDEX` and the derived `LEVEL_BANK` and `LEVEL_PAGE` live in
fixed WRAM: they are written with the LCD off during a transition and read by
the renderer under the bank-1 snapshot, and they are deliberately outside the
snapshot copy because they cannot change while a frame is in flight. The hot
geometry path pays two fixed-WRAM loads per wall hit for this.

The resident wall atlas is still chosen once, at build time, from the first
level's `vram_profile`; `layout.py` rejects a campaign whose levels disagree.
The palette set is not resident: `load_level` keeps header byte 3 in the
fixed-WRAM `PALETTE_SET`, and `enter_world` calls `init_palettes` with the LCD
off, which uploads that set's 128 bytes (eight BG then eight OBJ palettes)
from the `bg_palettes` table; a set past the table reads set 0. Sets differ
only in what the world owns (ceiling, floor, structure, door and machinery
tones, the three enemy kinds); BG palette 1 (the HUD, which the screens use),
BG 7, the weapon, drops, muzzle flash, decor and reticle are the same bytes in
every set, so a screen never has to restore anything.

For the qualified v0.8 ROM, fixed code ended at `$3910` (1,776 bytes below
`$4000`); resident data ended at `$73CD`, leaving **3,123 bytes** below `$8000`.
Moving the cold ray tables and the level records out of banks 0/1 since then
leaves the current build over 7,500 bytes free (`memory_budget.resident_free_bytes`
in the manifest has the exact figure). The required reserve remains
3,000 bytes, and saving resident table data still does not buy fixed-code room.

### The bank boundary

MBC5 maps bank 0 at `$0000–$3FFF` and a switchable bank at `$4000–$7FFF`, so
the hardware rule is narrow: code that writes the bank register must sit in the
fixed half, and code in the switchable half must not run while another bank is
mapped there. Until v0.9 the build enforced a proxy for that — every byte of
engine code below `$4000` — which is far stronger than the rule and had run out
of room at 160 bytes.

`bank_safety.py` now checks the rule itself against the emitted image, in six
clauses: every bank-register write is in the fixed half; nothing that can run
with a foreign bank mapped is in the switchable half; the interrupt handlers
and everything they reach are in the fixed half and never switch a bank; the
image contains no `jp (hl)` or `rst`, so no edge goes unfollowed; no transfer
leaves the image into the switchable half; and no placement section falls
through into the next, which is what makes a section's address a placement
decision. Clause two is a context-sensitive taint analysis: calls are matched
to their returns per call site, so a routine that switches a bank and restores
it does not contaminate its callers, and one that returns with a foreign bank
still mapped does contaminate the right ones. Entry points are read out of the
cartridge's own reset and interrupt vectors rather than declared.

Sections that neither switch a bank, nor can run inside another section's bank
window, nor are reachable from an interrupt vector are emitted after the data
and land above `$4000` in ROM bank 1, the engine's resting bank. Of about
22 KB of instructions, about **2.0 KB** are pinned to the fixed half, and the
overlapped publication tail and the textured kernel's banked helpers have
filled it: fixed code ends at `$3FC0`, **64 bytes** below the boundary
(`bank_safety` and `memory_budget.fixed_code_end` in the manifest). New
resident code has to be cold or move something cold first. Prepared scalar records 0–240 and
the raw-query sentinel are unchanged; disabled packets own only records
241–250.

## RAM and video allocation

`allocation.py` checks ranges and lifetimes; the build manifest records resolved
allocations. Important owners are:

| Resource | Ownership |
| --- | --- |
| Fixed WRAM `$C600–$C7DF` | 480-byte world map staging |
| Fixed WRAM `$C7E0–$C7EB` | Music sequencer state, above the map in every profile |
| Fixed WRAM `$C8E0–$C8EF` | Unfolded strip scratch, outside the enlarged map |
| Fixed WRAM `$CE00–$CFFF` | 512-byte reserved stack |
| WRAM bank 1 | Immutable render snapshot, descriptors, masks and staging |
| Bank 1 `$D3D8–$D3E7` | 16-byte HUD publication packet |
| Bank 1 `$DC00–$DDDF` | 480-byte attribute staging |
| WRAM bank 2 | Authoritative live simulation state |
| WRAM bank 3 | Reserved 128×32-byte dynamic-cache experiment |
| WRAM bank 4 | Reserved foreground buffers/event queue experiment |
| WRAM bank 5 | Note periods and the selected song's rows |
| WRAM banks 6–7 | Available |
| HRAM | 112 state bytes and a separate 10-byte DMA stub |
| BG patterns | Slim: ceiling, floor and up to 238 dynamic pattern ids through a 96-slot ring; legacy/compact: static/atlas tiles plus at most 96 dynamic patterns |
| Bank-0 HUD patterns | 94 of 96, `$8200–$87DF` |
| Bank-1 OBJ patterns | 86 preloaded weapon/UI plus 32 masked world patterns; 80 of the 86 are the streamed weapon window |
| OAM | 40 hardware objects; world pool 16, at most four per scanline |

The 218-pattern enemy/fixture **ROM source dictionary** is distinct from resident
VRAM tile IDs. Masked strips are composed into the bounded pool. Hardware selects
at most ten objects per scanline, including Y-overlapping objects hidden in X.
Living actors and gameplay pickups have priority over cosmetic death sprites.

### Screens and their runtime digits

A full-screen mode owns the whole background with LCDC `$81` and VBlank only,
so composition is idle for as long as one is up. Its slot state — the digits it
will write and the map cells they go in — therefore borrows the bottom of the
BG map staging buffer at `$C600` rather than fixed WRAM, which had one byte
free against three per slot. `enter_world` repeats `init_vram`, whose loop
refills every byte of that buffer, so a screen never has to put anything back.

A screen declares a label and how many cells follow it; the composer places
those cells on tile boundaries, the label clear of them, and refuses a line
whose glyphs straddle a tile row or land on authored art. Placing them by hand
is how the continue code and the skill indicator came to be written eight rows
above where they belonged: the map row offset passes 255 at row eight and the
address arithmetic was dropping the carry, so neither had ever been visible.

### Continue codes

There is no cartridge RAM — `$0147` is `$19` and `$0149` is `$00` — so progress
travels as a code the player writes down. A build-time table holds one
four-digit code per (sector, skill) pair, generated deterministically, never
repeated and never starting with a zero, so a code read off the intermission
types back in exactly as it appears. The console only ever compares bytes: no
modular arithmetic, no checksum decode.

The intermission writes the code for the sector just unlocked into four
adjacent runtime digit slots. SELECT on the title opens a code-entry screen
using the same slots: left and right move a blinking cursor, up and down roll
the digit under it, START looks the code up and, on a match, sets the level and
the skill. An unknown code is simply not taken, and SELECT returns to the title.

Screens carry up to `SCREEN_SLOT_CAPACITY` (ten) rewritable map cells. Patterns 0–9 are the decimal
digits and pattern 10 is blank, so showing a number or clearing a cell is a
single map write with the LCD off, or at the top of VBlank.

## Enemies

An actor slot's byte 15 holds its kind, so the kind rides the per-slot save and
load and the bank-1 snapshot like every other actor field. A four-record table
gives each kind contact damage, attack recovery in AI ticks, Q8 move per tick,
an OBJ palette and what it drops when it dies; records are a power of two wide
so the lookup still indexes by shifting. The kind byte is masked to two bits;
the fourth record is the boss, the Sentinel's cels and palette with the
heaviest contact damage in the game, so a corrupt byte still reads a playable
actor, only a dangerous one.

Kinds share the Sentinel's cels, so variety costs ROM bytes rather than VRAM
patterns. A distinct *look*, though, costs an OBJ palette, and all eight are
now spoken for: 0 the weapon, 1 the Sentinel, 2 drops, 3 the muzzle and decor,
4 decor and the reticle, 5 the weapon's second palette, 6 the warden and 7 the
skirmisher. Palette 6 came free only because the reticle is a single-colour
crosshair whose colour was already within three parts in thirty-one of
palette 4's, and moving it still changed eight shipped pixels a frame. A
fourth visible kind means re-planning those, not editing the table.

A dead actor's drop needs no byte of its own: it is whatever the actor was.
The Sentinel and the warden leave a medkit, the skirmisher a keycard, and the
level compiler refuses a level whose card is behind the door it opens, or one
that declares a drop no actor leaves.

An actor patrols a heading held in a parallel per-actor array in the snapshot
slack — the sixteen-byte slot is exactly full — walking it through the same
stepping bodies and collision test the chase uses, and turning a quarter turn
when a step is refused. It stays dormant until the player comes inside the
level's authored activation radius, folded to whole cells once at load.

Skill (0–2, chosen with left and right on the title screen) scales contact
damage only: half, as authored, or one and a half.

## Weapons

The weapon window is eighty OBJ patterns at `$8200` in VRAM bank 1, and that is
one weapon's four 40×32 cels exactly (ten objects, twenty patterns a cel;
`docs/reference/asset-formats.md`) — the reticle and muzzle take the next four and
the masked pool owns the thirty-two below. Two weapons cannot both be resident,
so SELECT streams the next owned one's cels in as a single GDMA of eighty
blocks. The four cel sheets share ROM bank `WEAPON_ROM_BANK` in weapon order
and `weapon_source` reads a resident pointer table; ownership is a bit per
weapon that `load_level` derives from the sector (`WEAPON_UNLOCK_SECTORS`),
so a continue code carries the arsenal and a weapon no longer owned is put
down on load.

The pattern IDs never change, only their contents, so no OAM is rewritten and
the animation code is weapon-agnostic. The transfer runs from the main loop
once the frame is published, with the LCD off, the way `init_vram` uploads this
same window at `enter_world`: a transfer with the LCD on is part of a frame's
publication to the console and to the harness, and this is a VRAM re-upload
rather than a publication. The cost is the frame each swap blanks.

A four-record table (`weapon_stats`) gives each weapon the damage a hit takes
off and its recovery in simulation ticks. The shotgun's record is the engine's
original behaviour exactly — one damage, no recovery — and the other three
weapons trade damage against recovery. Recovery belongs to the shot: a swap
keeps it, so a slow weapon cannot shed its cost by swapping away.

## Sound

CH1 is reserved for effects — the shot, a weapon swap, a locked door, a door
opening, the player being hit, an enemy dying, a pickup, a keycard and a
cleared sector — so nothing
the player does can cut a bar of music. The sequencer owns CH2 (pulse lead),
CH3 (wave bass) and CH4 (noise percussion).

Songs are rows of three bytes, one per sequencer channel: hold, release, or a
note index into a 64-entry equal-tempered period table. A song header carries
its speed in frames per row, its length and its loop row.

Two placement constraints shape the driver:

* **It never runs in VBlank.** A staged publication finishes its GDMA about one
  scanline before line 153 — measured at line 152, dot 432 of 456 — so anything
  else in VBlank costs frames outright. While the world renders, the sequencer
  ticks from the viewport-boundary STAT interrupt instead, forty-odd lines
  earlier. A full-screen mode enables VBlank only and has no such boundary, so
  its wait loop ticks the sequencer directly.
* **It never switches the ROM bank.** An interrupt can land between a banked
  lookup's bank switch and its read. The selected song is copied into WRAM bank
  5 at `music_start`, and the tick saves and restores SVBK around the rows it
  reads. A test scans the emitted bytes of every routine the tick reaches and
  rejects any write to the MBC5 bank register.

Measured cost: 84 T-cycles on a frame that only counts down, 1,048 on a row
boundary, **149 T-cycles mean** — 0.106% of a 140,448-cycle LCD interval, and
the same share of a full geometry update.

## Publication and timing

On the compact and slim profiles a full packet is **streamed**: the hidden
dynamic patterns (at most 96 blocks on compact; up to 238 on slim, 268 HBlank
blocks with the map) and the complete hidden tile-number map
(30 blocks on slim) travel by HBlank DMA while `render_view` is still
composing, one block at the HBlank of each visible line, into the bank and
map the displayed page never reads. `render_view` hands each column's
patterns over as it finishes them; `upload_hidden_page` streams the remainder
and the map, builds the attribute packet underneath the transfer, then uses
**one VBlank** for the banked tail: masked OBJ patterns and the attribute
packet by GDMA (at most 62 blocks), the HUD map cells, OAM DMA and the flip.
On slim that tail is run by the VBlank interrupt (**overlapped
publication**): the main loop hands the packet over at `publication_handoff`
and goes straight on to the next snapshot and its casts, and waits for the
tail (`wait_tail`) only before it touches a publication buffer again
([performance after textures](../evidence/PERFORMANCE_PHASE5.md)).
HBlank sources are fixed WRAM because a block reads through SVBK and a
simulation yield may have bank 2 mapped; VBK belongs to the transfer for its
whole life; nothing streams with the LCD off. See
[streamed publication](streamed-publication.md).

The legacy profile keeps the staged packet: at most 176 GDMA blocks (96 BG,
32 OBJ, 24 map, 24 attribute) over two VBlanks, the pattern stage bounded to
96 blocks, with the experimental foreground/reprojection lanes built on it.
Cached packets use one VBlank on every profile. Writes must finish before line
153. No partially prepared row or mask bank becomes visible. GDMA, HBlank
blocks and OAM DMA halt CPU execution and are counted as work, not background
transfers.

The steel HUD retains a 16-byte packet: four health IDs, one enemy count,
two caption IDs, three status IDs and six portrait IDs. Text starts at HUD y=4
and y=10. Each main status ID names a vertical tile pair; its lower ID is written
into the third HUD row on both maps. The final one-pixel spacing fix adds six
map writes, **108 CPU T-cycles** (about 12.9 µs), without extra pattern DMA.
See [HUD layout and captures](../../games/sable_outpost/docs/steel-hud.md).

CPU T-cycles are canonical: double-speed CPU frequency is 8,388,608 Hz. One LCD
interval remains 70,224 base-speed clocks, about 16.74 ms (140,448 double-speed
CPU T-cycles). Full geometry updates, cached presentations and experimental
foreground publications are separate counters. [Current evidence](../evidence/TEST_REPORT.md)
documents the accepted visual/performance tradeoff; ten sustained full updates/s
is a target, not an achieved guarantee.

## Art and animation

Original generated concepts are adapted into indexed PNGs and deterministically
compiled into 2bpp data. Builds do not generate images or download assets.
Each weapon has four 40×32 cels of twenty patterns, streamed into the
80-pattern OBJ window with the LCD off when it is swapped in; flashes have two. Sentinels have twelve
frames at each of three deliberately authored sizes. The HUD uses the approved
armoured helmet with normal/blink/hurt/dead states. Snapshot timing selects cels;
OAM references animate the weapon without per-frame pattern uploads.

Accepted fire restarts recoil and preserves pending flash feedback until it is
published. Gameplay death happens immediately; a short three-pose death visual
is cosmetic and can be omitted under capacity pressure. Scene generation,
restart and tick wraparound preserve coherent state. Details and source locations
are in [Sable Outpost](../../games/sable_outpost/docs/art.md).

## Feature gates and references

Compact strips, invariant camera setup, narrow yields and CPU attribute padding
are the accepted exact-output improvements. Sable art/animation and slim display
are enabled by the owner's explicit acceptance of their measured cost. The
original mean/p95 half-gains budget remains recorded as failed.

Dynamic caching, packet traversal, physical depth, actor precision, scanline
admission, paged projection, near-field precision and foreground publication
remain experiments. Reprojection is disabled. Build flags and format versions
are recorded in the manifest; unsupported explicit combinations fail.
[Rendering milestone evidence](../archive/RENDERING_IMPLEMENTATION.md) describes the earlier
performance work, while [development guidance](../engine/development.md) explains how to
build references and qualify changes without overwriting historical evidence.
