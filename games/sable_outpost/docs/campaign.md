# From tech demo to game

Lupine 3D shipped v0.8 as one hand-authored level with one enemy, no framing
screens and no way to stop playing except turning the console off. This
document records what turned it into a game and what each decision cost.
Contracts live beside their source; this is the summary and the evidence.

## What the game is now

| | v0.8 | v0.9 | main |
| --- | --- | --- | --- |
| Levels | 1, chosen at build time | **5**, chosen at runtime from their own ROM banks | **18** in three episodes, five to a ROM bank behind a resident directory |
| Enemies | 1 Sentinel | 1–4 actors, **three kinds**, patrolling and waking on proximity | **six in every sector**, four kinds: Wardens that **shoot** after a telegraphed wind-up, and an Overseer closing each episode; each actor wakes by its own radius or on sight, and drops what its level says |
| Weapons | 1 | **2**, streamed through one 80-pattern window | **4**, owned by episode and restored by a continue code |
| Doors | open or wait on the Sentinels | also **keycard**, carried by the kind that drops one | up to six per level: **amber and teal** card doors, and **remote** doors a trigger opens |
| Items | none | a medkit or card dropped by a kill | up to sixteen **placed** per sector: stims, medkits, armour, slugs, cells, cards and weapon cases |
| Resources | health | health | health, **armour** (half of every hit), two **ammunition** pools, keys, all **carried** from sector to sector |
| Framing | none | title, intermission, results and ending screens, with **kills and time** | a title with a wordmark, a prologue, a debrief with the story after every sector, episode pages, and the ending returning to the title |
| Difficulty | fixed | **three skill settings**, chosen on the title | unchanged |
| Persistence | none | **four-digit continue codes** | one per sector and skill |
| Audio | three effects on CH1 | a **sequencer on CH2/CH3/CH4** plus nine effects on CH1 | **eight songs**: per episode and per guarded sector, and for the game over and the ending |

A run starts at the title, where left and right choose a skill and Select opens
code entry. Each sector is cleared by killing every actor and reaching the exit;
clearing one shows the code for the next along with what the sector cost, dying
retries the sector that was lost, and clearing the last one ends the campaign
with the run's totals.

## The story

The Line is the chain of relay stations that carries every voice between the
frontier colonies and home. Sable Outpost, sunk into the ice of the black
moon Sable, is its last and deepest ear: a listening post with a reactor
below it and the Signal Spire above. Its security is automated: Sentinel
frames hold the corridors, fast Skirmishers carry access cards between the
sealed decks, heavy Wardens guard the gates, and a guard frame holds the way
out of each section. All of them take orders over the station's command band.

Nine days ago the deep bore under the reactor broke into a hollow, and
something down there was already transmitting on that band. Chief Engineer
Oda's log counts the days: the hum, the frames refusing orders, a voice in
the helmets, then a single order, COME DOWN. The crew went down; the frames
stayed. The player is a Linewalker, the Line's lone repair marshal, sent in
the old Mark I armoured helmet and respirator the HUD shows. It has no
command receiver, so the call cannot reach them, and that is why they were
sent.

The title and a dispatch page set this up; after every sector a debrief
gives a page of Oda's log and names the next sector. Episode one retakes the
outpost down to the empty cryo pods. Episode two follows the crew into the
reactor and starves the hollow by killing the core. Episode three climbs the
Spire, which kept a copy of the call and sends it down the Line, and cuts the
uplink. The ending says the Line is safe, but the call ran for nine days and
something heard it. The words are in `screens.json`; the title's wordmark
and emblem are derived by `art/tools/make_title_art.py`, the emblem from the
approved helmet itself. Eight songs play the story: the title's leitmotif
(E, B, A sharp, E an octave up), a world song for each episode, a song for
each episode's guarded last sector, the debrief, the game over and the
ending, which resolves the leitmotif.

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

## Measured cost (v0.9)

These figures were taken on the v0.9 ROM; the engine has grown since (the
generated [memory map](../../../docs/reference/memory-map.md) and the manifest hold the current
budgets).

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

v0.10 added **Cryo Vault**, sector six, then in ROM bank 246 (levels are now packed five to a bank, and it sits in bank 242): a vault of four
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
per-actor array in the snapshot slack (four bytes then, `MAX_ACTORS` now), indexed like `ACTOR_DEPTHS`, holds a
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
(`docs/reference/asset-formats.md`) and its own opening and closing screens
(`AGENTS.md`, "Campaign, modes and screens"). Levels are packed five to a
ROM bank from 241; the arsenal grows by episode (`WEAPON_UNLOCK_SECTORS`:
the arc lance from sector 7, the pulse carbine from sector 13, and
earlier from a weapon case) and the continue codes carry it. The last
sector of every episode fields the boss.

| Episode | Palette set | Sectors |
|---|---|---|
| 1 Sable Outpost | `outpost` | Landing Deck, Coolant Spine, Reactor Gate, Vent Stacks, Signal Deck, Cryo Vault (boss) |
| 2 Reactor Deep | `reactor` | Coolant Intake, Pump Gallery, Turbine Hall, Coolant Dark, Control Gallery, Reactor Heart (boss) |
| 3 Signal Spire | `spire` | Antenna Base, Relay Deck, Hull Walk, Signal Vault, Transmitter Ring, Spire Crown (boss) |

Every sector carries the same compiler certificate as the first six
(`docs/reference/level-certificate.md`; `tests/test_campaign.py` pins it for all
eighteen), and the controller route plays all of them in CI's `route` matrix:
eight chunks sized by route updates (`tools/ci_lanes.py`), each on its own
runner and entered by continue code (`make playthrough SECTORS=7-9
ROUTE_DIR=build/playthrough-7-9`), the first from the title and the last
restarting the campaign from the ending. `release_check.py`
unions the reports for the current ROM. Regenerating the continue-code table
for eighteen sectors changed every code.

### Named places

Every sector is laid out as one place with a purpose, so the way through it
follows how the place would be used rather than a grid of rooms:

| Sector | Place |
|---|---|
| 1 Landing Deck | the landing airlock, a U-shaped decon passage, the bunk room and the mess hall off it, the comms room where the Sentinel guards the lift |
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

The certificate shapes every plan (`docs/reference/level-certificate.md`): a door
counts as open floor in the six-cell sightline, so a door sits where the
corridor turns, and every door must cut off at least eight cells, so doors
lead into wings and never sit on a loop; the loops are open corridors.
The controller route added three rules of its own. A boss fight needs room to
back away: a one-wide ring corner trapped the route against the boss, so
Reactor Heart's ring is two cells wide. A door should not open between two
enemies that wake together. And a lone pillar in a small room can hide an
actor from every firing position; Relay Deck's Warden walks the deck instead
of the operations room.

## Every room means something

The first eighteen sectors were places with almost nothing in them: most
fielded two to five enemies and nothing lay on the floor, so the first
sector had eight rooms to walk and one Sentinel to shoot. The overhaul
gave the engine what a Doom level is built from and then rebuilt every
sector around it:

- **Placed items** (`game.json` `items`): stims (+10) and medkits (+25),
  armour (+50, which takes half of every hit while it lasts), slugs for the
  slug rifle and cells for the arc lance and pulse carbine, amber and teal
  cards, and the two weapon cases. An item with nothing to give stays on
  the floor: a medkit at full health waits for you.
- **Coloured card doors and remote doors.** A card door wants its colour;
  a remote door refuses B and opens only when its trigger cell is stepped
  on, once. A trigger under a card is a trap: take the card and the closet
  behind you opens.
- **Encounters by wake rule.** Every actor has its own wake radius, and a
  sentry that also needs **sight** holds its post until it sees you. A
  closet's occupants stand in their door's line, so they come out the
  moment it opens.
- **Wardens shoot.** Inside five cells and in sight, a Warden holds its
  ground, raises its arm with a whine for most of a second, and fires if it
  still sees you. Every Warden is placed with cover (a door frame, a
  corner, a pillar) within two steps of where you meet it.
- **Carry-over.** Health (at least 50), armour, ammunition and weapons
  found ride from one sector to the next; a continue code starts from the
  sector's own loadout.

Every sector now fields six actors, eight to thirteen items and at least
one card door, and every room holds an encounter, health, ammunition,
armour, a card, a weapon case or a trigger. Each episode's first sector
teaches its idea and its last is a boss arena: 30 health for Cryo Vault's
Overseer, 40 for Reactor Heart's and 60 for Spire Crown's. The level
files hold the details; this is what each sector asks of the player:

| Sector | What happens there |
|---|---|
| 1 Landing Deck | the first card: a locked bunk room seen early, the amber card on the mess table, the first Warden in comms, and the trip back for the bunk room's armour |
| 2 Coolant Spine | the teal card under the shaft hatch: taking it drops two Hounds down the column; the Warden holds the spine behind the teal valve |
| 3 Reactor Gate | a key carried by an enemy: the stair room's threshold springs a closet, and its Hound runs out with the amber card for the cell block's prisoner Warden |
| 4 Vent Stacks | the arc lance's case in the fan room; bait slugs in the exhaust hall open a closet of Hounds behind the Warden |
| 5 Signal Deck | two keys in sequence round a patrolled ring: teal from the mast top (and its closet), amber from the radio room, down to the lower deck's Warden |
| 6 Cryo Vault | the Vault Overseer (30) behind the teal sump lock; the control room's card opens the hatch behind you |
| 7 Coolant Intake | cells and Wardens: a crossfire in the four-column cistern, the amber card's closet in the settling tank |
| 8 Pump Gallery | drains that open under your feet as you pass, a Hound climbing after you each time; the teal card in the pump room |
| 9 Turbine Hall | two Wardens, one by each turbine; a courier with the teal card in the condenser, a secret drain with armour |
| 10 Coolant Dark | the pulse carbine's case in a hidden gallery; tunnels that loop, a courier by the stair |
| 11 Control Gallery | Wardens at both ends of a console field; the teal card in the offices opens the records closet |
| 12 Reactor Heart | the Core Overseer (40) on a two-wide ring; each loop's card springs its sump |
| 13 Antenna Base | Wardens firing down a switchback stair: break the line at the landings; a landing opens a closet |
| 14 Relay Deck | a crossfire among relay racks; the teal card at the top of the west aisle brings two Hounds down it |
| 15 Hull Walk | a walk round the hull with a Hound on each side; the amber card on a trap threshold, two Sentinels behind it |
| 16 Signal Vault | the courier's amber card opens the vault's two Wardens; the teal card inside opens the data core |
| 17 Transmitter Ring | three arcs, three phases; the teal card brings a Sentinel and a Hound down the west arc; a cache to carry into the last sector |
| 18 Spire Crown | the Overseer (60) among eight pillars, a Warden in each bay; the heavy armour's closet in the west bay |

The level compiler gates every one of them as before, and more: every item,
card door, remote door and enemy must be reachable in play (cards before
their doors, triggers before theirs), and sector 1 keeps the grid, spawn,
exit, doors and fixtures the engine's evidence is recorded on (its v0.12
population is kept as `tests/levels/living_world_v012.json`).
