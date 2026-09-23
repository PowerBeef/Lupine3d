# From tech demo to game

Lupine 3D shipped v0.8 as one hand-authored level with one enemy, no framing
screens and no way to stop playing except turning the console off. This
document records what turned it into a game and what each decision cost.
Contracts live beside their source; this is the summary and the evidence.

## What the game is now

| | v0.8 | main |
| --- | --- | --- |
| | v0.8 | v0.9 |
| --- | --- | --- |
| Levels | 1, chosen at build time | **5**, chosen at runtime from their own ROM banks |
| Enemies | 1 Sentinel | 1–4 actors, **three kinds**, patrolling and waking on proximity |
| Weapons | 1 | **2**, streamed through one 80-pattern window |
| Doors | open or wait on the Sentinels | also **keycard**, carried by the kind that drops one |
| Framing | none | title, intermission, results and ending screens, with **kills and time** |
| Difficulty | fixed | **three skill settings**, chosen on the title |
| Persistence | none | **four-digit continue codes** |
| Audio | three effects on CH1 | a **sequencer on CH2/CH3/CH4** plus nine effects on CH1 |

A run starts at the title, where left and right choose a skill and Select opens
code entry. Each sector is cleared by killing every actor and reaching the exit;
clearing one shows the code for the next along with what the sector cost, dying
retries the sector that was lost, and clearing the last one ends the campaign
with the run's totals.

## The decisions that shaped it

**Levels became data, not opcodes.** Selection used to be assembled into
immediate operands — entity counts, fixture counts, the pickup value, the
segment-table bank. Each campaign level now owns a page-aligned slot in a ROM
bank from 241 (five levels per bank) at fixed offsets inside the slot, and the
loader reads the bank and slot page from a resident directory by `LEVEL_INDEX`.
The hot geometry path pays two fixed-WRAM loads per wall hit for it. The resident wall
atlas is still chosen at build time, so every campaign level must declare the
same VRAM profile; `layout.py` rejects a campaign that disagrees. The palette
set is per level: the header byte the loader keeps in `PALETTE_SET` picks one
of the three 128-byte sets that `enter_world` uploads with the LCD off.

**Screens borrow the renderer's own scratch.** A full-screen mode owns the
whole background with LCDC `$81` and VBlank only, and its patterns go into the
96-pattern composition window at `$9000`, which is meaningless while the world
is not rendering. `enter_world` repeats the boot upload, so a screen never has
to put anything back.

**The music driver stays out of VBlank.** A staged publication finishes its
GDMA at line 152, dot 432 of 456 — about forty T-cycles of margin. Adding a
single conditional call to the VBlank interrupt pushed the legacy profile past
line 153 and broke the publication budget test. The sequencer rides the
viewport-boundary STAT interrupt instead, forty lines earlier, and a
full-screen mode ticks it from its own wait loop. It never switches the ROM
bank either: songs are copied into WRAM bank 5, because an interrupt can land
between a banked lookup's bank switch and its read.

**Enemy variety is bounded by OBJ palettes, not by VRAM.** Kinds share the
Sentinel's cels, so stats cost ROM bytes. A distinct *look* costs an OBJ
palette, and the first attempt at three kinds repainted palettes 5 and 6 —
which are the weapon's lit corners and the reticle — and broke nine of nine
oracle captures.

The third kind came from asking what palette 6 was actually *for*. It held the
reticle alone, and the reticle's art uses one colour: index 3, `(13,28,26)`.
Palette 4's index 3 was already `(16,29,27)` — three parts in thirty-one apart
on red, one on green and blue. Moving the crosshair onto palette 4 is one
attribute byte, it frees palette 6 entirely, and it changes eight pixels a
frame and nothing else, which before-and-after ROM captures show exactly. That
is a deliberate change to shipped pixels, so v0.9 carries its own nine-image
oracle rather than editing the v0.8 one.

**Progress is a written-down code, not a battery.** The cartridge has no RAM
(`$0147` is `$19`, `$0149` is `$00`) and every release check depends on that. A
build-time table holds one four-digit code per sector and skill; the console
only ever compares bytes.

## Measured cost

| | Figure |
| --- | --- |
| Full geometry updates | **6.611/s** on the nine-image tour, unchanged from before this work |
| Weapon stream | one GDMA of 80 blocks with the LCD off, once per swap |
| Music sequencer | 84 T-cycles counting down, 1,048 on a row boundary, **149 mean** — 0.106% of an LCD interval |
| Segment lookup | one extra fixed-WRAM load per wall hit |
| Resident ROM free | **6,475 bytes** below `$8000` (floor 3,000) |
| Fixed code | ends at `$3240` — **3,520 bytes** below the `$4000` bank-switching ceiling |

That last row used to read `$3F60`, 160 bytes, and it was the next wall. The
ceiling was a proxy: the hardware rule is that code writing the bank register
must live in bank 0, not that all code must. `bank_safety.py` checks the rule
itself against the emitted image, so sections that never switch a bank, never
run inside another section's window and are unreachable from an interrupt are
emitted after the data and land above `$4000` in bank 1. Of 16.5 KB of
instructions, 1.6 KB are genuinely pinned below the boundary.

## The sixth sector

v0.10 adds **Cryo Vault**, sector six, in ROM bank 246: a vault of four
rooms above a keycard hatch, with a warden and a card-carrying skirmisher
upstairs and a Sentinel and a second skirmisher in the sump below, and the
exit behind the Sentinel-locked door of a fourth room. It carries the same
compiler certificate as the other five (no unreachable cell, sightlines of at
most six cells, doors that each separate at least eight walkable cells, a
critical path of twenty steps and seven turns, no open room beyond the 4×4
envelope, and a card that can be reached with the hatch shut), and the
controller route plays it like the others. The continue-code table grew from
fifteen codes to eighteen, which changes every code: they are content.

## What the last five cost

The first pass left five things out, each for a stated reason. Each turned out
to be blocked by a claim that was true of the code but not of the hardware.

**Patrol routes** were blocked on the actor slot, which is exactly sixteen
bytes full. Per-actor state does not have to live in the slot: a parallel
four-byte array in the snapshot slack, indexed like `ACTOR_DEPTHS`, holds a
heading, and patrol walks it through the same stepping bodies and collision
test the chase uses. A refused step turns the actor a quarter turn. The
authored `activation_radius_q4`, parsed and stepped over since it was written,
now wakes an actor when the player comes inside it.

**Keyed doors** were blocked on nothing, it turned out. `DoorSpec.flags` had
free bits and the record needed no growth. What was actually missing was the
drop: a card has to come from somewhere. It does not need a byte of its own
either - a drop is whatever the actor that left it was, and the kind is
already in the slot and already snapshotted. The Sentinel leaves a medkit, the
skirmisher a card, and the compiler refuses a level whose card is behind the
door it opens.

**A third enemy kind** was blocked on OBJ palettes, all eight claimed. Palette
6 held the reticle alone, and the reticle's art is one colour - within three
parts in thirty-one of palette 4's, which is why moving it there changes eight
pixels a frame and nothing else. That is still a change to shipped pixels, so
v0.9 carries its own capture oracle beside the retained v0.8 one.

**Sector statistics** were blocked on fixed WRAM: one free byte in the `$C7E0`
window against three per digit slot. Screen slot state does not belong in
fixed WRAM at all. A full-screen mode owns the whole background, so
composition is idle for exactly as long as that state exists, and
`enter_world` refills the map buffer anyway - the same argument that lets
screens borrow the `$9000` pattern window. Capturing the result found that no
runtime digit below row eight had ever been visible: the row offset passes 255
and the carry was being dropped, which put the continue code and the skill
indicator where nobody could read them.

**A second weapon** was the one whose stated reason held exactly. The window
is eighty patterns and that is one weapon's cels, so the patterns stream. The
pattern IDs never change, only their contents, so no OAM is rewritten. The
transfer runs with the LCD off, the way `init_vram` uploads that same window:
with the LCD on the harness counted it as part of a frame's publication and
refused the frame, which is the correct answer - a weapon swap is a VRAM
re-upload, not a publication.

## Evidence

ROM `e59f722b698b545e75e5dbb2cdfe3810c5cc6a3ec96e38e868c09d286e2a9b89`, default
slim/Sable configuration.

- **229 automated tests** (`make test`), including the campaign's bank layout,
  the sequencer's placement and bank contract, enemy kinds and skill scaling, a
  continue-code round trip with a refused code, the MBC5 bank contract against
  images built to break each of its clauses, patrol collision and waking, the
  keycard gate and the compiler's refusal of an unsolvable level, the map cell
  every reserved digit resolves to, and the weapon stream.
- **Two pixel oracles byte-identical** (`make playtest`, `make playtest-world`).
  Every commit but the palette re-plan was required to move no pixel at all;
  that one moved eight per frame and was captured before and after.
- **89 release checks** (`tools/release_check.py`), including a per-level
  readability certificate for all five sectors rather than only the first.
- **2,961-update controller route** (`tools/playthrough.py --restart`): every
  sector cleared, every drop collected, one sector cleared with the second
  weapon, every intermission crossed and the ending restarting the campaign, on
  controller input alone, with **zero game RAM writes** and **zero unsafe GDMA
  starts**. Every frame is checked against the host geometry and compositor
  models.
- **Variant pixel equality** (`make variants`): folded/unfolded,
  reuse-disabled, prepared-rays-disabled and the two-actor level.
- `make wall-reuse`, `make motion`, `tools/check_sable.py`,
  `tools/check_display.py` — all passing.

- **Pinned SameBoy CGB-0/CGB-E and mGBA**, and 87 frozen independent-witness
  scenes, all matching the harness on this ROM. Both adapters predate the title
  screen and had to learn to press START; with that fixed, SameBoy immediately
  reported 192 CPU writes to the *displayed* background map. The weapon swap
  was restoring a constant `LCDC` after its LCD-off transfer, clearing the bit
  that says which page is displayed while `CURRENT_PAGE` still said the other
  one — so the next frame's hidden-page copy wrote the visible map. It restores
  the `LCDC` it found now, and the swap no longer fires on the first frame of a
  real power-on, because the weapon state it reads is initialised at boot
  rather than inherited from whatever was in WRAM.

Neither fault was reachable in the host harness, which zeroes WRAM and models
the page flip from the same state the ROM does. That is what those lanes are
for, and it is the first time in this work they have caught something the
project's own model could not.

## Three episodes

The campaign is three episodes of six sectors, each with its own palette set
(`docs/ART_PIPELINE.md`) and its own opening and closing screens
(`AGENTS.md`, "Campaign, modes and screens"). Levels are packed five to a
ROM bank from 241; the arsenal grows by episode (`WEAPON_UNLOCK_SECTORS`:
the arc lance from sector 7, the pulse carbine from sector 13) and the
continue codes carry it. The episode-closing sectors of Reactor Deep and
Signal Spire field the boss kind.

| Episode | Palette set | Sectors |
|---|---|---|
| 1 Sable Outpost | `outpost` | Sable Outpost, Coolant Spine, Reactor Gate, Vent Stacks, Signal Deck, Cryo Vault |
| 2 Reactor Deep | `reactor` | Coolant Intake, Pump Gallery, Turbine Hall (keycard), Coolant Dark, Control Gallery, Reactor Heart (boss) |
| 3 Signal Spire | `spire` | Antenna Base, Relay Deck (keycard), Hull Walk, Signal Vault (keycard), Transmitter Ring, Spire Crown (boss) |

Every sector carries the same compiler certificate as the first six
(`docs/LEVEL_CERTIFICATE.md`; `tests/test_campaign.py` pins it for all
eighteen), and the controller route plays all of them: CI's slow lane plays
episode one and a `campaign` matrix plays episodes two and three from their
continue codes in three-sector chunks (`make playthrough SECTORS=7-9
ROUTE_DIR=build/playthrough-ep2a`), the last chunk restarting the campaign
from the ending. `release_check.py`
unions the reports for the current ROM. Regenerating the continue-code table
for eighteen sectors changed every code.

### Named places

Every sector is laid out as one place with a purpose, so the way through it
follows how the place would be used rather than a grid of rooms:

| Sector | Place |
|---|---|
| 2 Coolant Spine | a pump house, then a pipe-lined spine climbing to the valve head and the lift, with the coolant shaft off to one side |
| 3 Reactor Gate | a security checkpoint: a lobby, a ring corridor round the guard block, the cell block and turbine stair off it, the Warden at the reactor gate |
| 4 Vent Stacks | two shafts from the stack base: west to the fan room and the card, east to the carded upper walk and the exhaust hall |
| 5 Signal Deck | a ring walk round the antenna mast, with the mast shaft, radio room and deck gate off it and the carded throat down to the lower deck |
| 6 Cryo Vault | the cold throat up to the pod hall, the control room with the card, the carded sump below the pods |
| 7 Coolant Intake | a pump stair into a cistern held up by four pump columns, with the settling tank, intake valve and grate gallery off it |
| 8 Pump Gallery | a U of pump bays wrapped round the pump room, the valve room at the head of the U |
| 9 Turbine Hall | two turbine rooms, each walked round its turbine, with the stair and condenser below and the carded control room above |
| 10 Coolant Dark | unlit tunnels threading a staggered lattice of pipe blocks; the tunnels loop, so anything in them can come from two sides |
| 11 Control Gallery | an observation gallery opening by two arches onto a field of console pedestals, the offices and lock behind it |
| 12 Reactor Heart | a two-wide ring walk round the core, where the boss circles, with the coolant loops either side |
| 13 Antenna Base | a four-flight switchback stair up the base, the relay room at its head, the base hall and lift below |
| 14 Relay Deck | a deck of relay racks in staggered pairs, the operations room and the lock behind the carded door |
| 15 Hull Walk | a walk that circles the whole hull, jogging along the plating, with the four hull rooms off it |
| 16 Signal Vault | archive stacks either side of the vault; the west stacks hold the card, the vault holds two Wardens and the data core |
| 17 Transmitter Ring | a diamond ring round the transmitter, with a door at each point: arrival, two emitter rooms, the lock |
| 18 Spire Crown | the crown chamber, eight pillars round the boss, with bays either side and the uplink lock above |

The certificate shapes every plan (`docs/LEVEL_CERTIFICATE.md`): a door
counts as open floor in the six-cell sightline, so a door sits where the
corridor turns, and every door must cut off at least eight cells, so doors
lead into wings and never sit on a loop; the loops are open corridors.
The controller route added three rules of its own. A boss fight needs room to
back away: a one-wide ring corner trapped the route against the boss, so
Reactor Heart's ring is two cells wide. A door should not open between two
enemies that wake together. And a lone pillar in a small room can hide an
actor from every firing position; Relay Deck's Warden walks the deck instead
of the operations room.
