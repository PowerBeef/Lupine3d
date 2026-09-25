# Unreleased — after v0.12

- **Items, ammunition, coloured keys and triggers.** A game defines item
  types (`game.json` `items`: health, armour, ammunition, a key or a weapon,
  each drawn from a new `items` sprite sheet in one of the shared palettes)
  and up to two ammunition pools and two key colours; a level places up to
  sixteen items, gives a `loadout`, colours its card doors (`key`), makes a
  door `remote` and opens it from up to eight `open_door` triggers. Walking
  onto an item takes it unless it has nothing to give. Weapons may draw on a
  pool (`ammo`, `cost`): a dry weapon clicks and falls back to the first.
  The slim HUD shows the pool of the weapon in hand (two small digits after
  health; the packet is 18 bytes) and each key held (OAM 28-29). A level
  without a loadout has infinite pools, and one without items or triggers
  costs two compares a tick, so the evidence population and the starter
  play as before. The compiler walks each level as a player can and refuses
  an item, enemy, card door or remote door it cannot reach. Sable Outpost
  defines nine item types (`art/tools/make_item_art.py` draws the cels);
  its levels place none yet. `make limits` now also proves sixteen item
  types and a level with sixteen items and eight triggers.
- **Sable Outpost has a story, a title and a soundtrack.** The title is a
  SABLE wordmark over the approved helmet (both derived by
  `art/tools/make_title_art.py`) with a tagline, "SOMETHING ANSWERED.".
  START leads to a dispatch page, the first episode's new prologue.
  After every sector a debrief replaces the intermission: the cleared
  sector's name, a page of Chief Engineer Oda's nine-day log, the continue
  code, kills and time, and the next sector's name. The episode pages, game
  over and ending carry the story to an open end, and the ending now
  returns to the title instead of starting a new run. Sector 1 is named
  Landing Deck. Eight new songs share one leitmotif. Each episode has its own
  song, the guarded last sector of each has another, and the debrief,
  game over (no longer silent) and ending have theirs.
- **Screens for stories.** Screens gain the reading face (one 8×8 tile a
  character, readable at the console's size), images (indexed PNGs on the
  tile grid), an unframed option, a prologue for the first episode, and
  per-level debriefs whose `{sector}` and `{next}` become level names. Text
  screens share pattern pools, and records name their payload's bank, so 27
  screens fit where nine used to (bank 239, with room above the raw rays in
  238). Every screen but the title also passes when START is held for a
  second, which is how the harness and both adapters reach the world. A level
  may name its song (`music`, header byte 21), and a game may add game over,
  ending and level songs (at most sixteen). The run's time on the ending is
  whole seconds now: the old count of VBlanks wrapped after eighteen
  minutes. It stops at 9,999, as kills stop at 255. The screens are a new
  `screens` golden suite (`tools/check_screens.py`, `make screens`, CI's fast
  lane). The starter game's content is unchanged.
- **Room below $4000, and cheaper enemies.** The showcase overhaul needs
  code in the fixed half of bank 0, which had 64 bytes left. Actor admission
  and animation never switch banks and no interrupt reaches them, so they
  now sit above $4000 in bank 1 (bank_safety proves it): the fixed half has
  1,344 bytes free. Two pieces of unreachable code are gone: the cell-walk
  line of sight that the exact query replaced long ago, and the UI scanline
  seeding that only per-scanline admission calls (581 bytes). An actor's
  admission check now reads only the scanlines its strips cover instead of
  all 144, which makes the same decision (every other line already holds
  four objects or fewer; `tests/test_admission.py` checks 1,500 random
  cases against the full scan) and saves 30-60k T per drawn enemy. A dormant
  actor outside its wake radius no longer casts a line of sight nothing
  reads. The world playtest captures five scenes a few LCD frames earlier
  as a result; every capture taken on the same frame as before is
  pixel-identical.
- **A dropped medkit no longer wears the keycard.** A drop is an 8×8 cel
  drawn as the top of an 8×16 object, and the cels were packed, so a medkit
  showed the keycard beneath it and a keycard the hit effect. Each drop now
  keeps an empty pattern after it (the dictionary is 220 patterns); the
  legacy profile keeps its bytes for this.
- **The engine's evidence keeps its scene when the showcase changes.** The
  goldens, witnesses, cycle gates and sustained tapes were all recorded on
  the showcase's first sector as v0.12 populated it. That sector keeps its
  geometry, but its enemies and items are about to change. With
  `LUPINE3D_POPULATION=evidence` a process swaps the v0.12 population back
  in (`tests/levels/living_world_v012.json`, refused if the frozen geometry
  ever differs) and boots the built ROM with that one level slot rewritten.
  Evidence tools default to it, `run_tests.py` sets it, playtest scenarios
  declare it, and release checks bind those reports to that image; the
  route and the build refuse it. A canary run with two extra Sentinels in
  the shipped sector reproduced every golden, cycle count and test on the
  evidence image, which was byte-identical to the unmodified ROM. The
  numbers the overhaul's shipped-content gates are held against are in
  `milestones/overhaul/baseline-7dd300d7.json`. No ROM byte changes.
- **Enemies grow as they come closer.** The middle and far cels were both
  16 pixels tall, so from about 1¾ cells out an enemy stayed one size while
  the walls around it grew: it looked twice a wall's height at six cells and
  seemed to shrink as the player approached. The three sizes now halve: the
  near 16×32, the 8×16 far art (its half-scale) for the middle distance, and
  a quarter-scale 4×8 figure derived from it
  (`art/tools/derive_distant_sentinel.py`) for the far one. The engine
  measures the drawn figures and switches where neighbouring sizes are
  equally wrong (near below 1.3 cells, far from 3 cells), with the near
  figure true one cell away. The middle cel may now be one column (8×16) or
  two; one column frees 24 dictionary patterns (218 of 256) and one object
  per enemy. The squat 16×16 middle cel stays in the art folder, unused.
  The starter game uses the same ladder. The legacy profile is unchanged.
- **The route stops a reposition that is costing it.** Moving away from
  an awake actor that follows now ends once the walk has cost two contacts
  and turns to fight, as the walk to a firing position already did: with
  the ladder's cheaper middle-distance cels shifting the timing, the first
  sector's Sentinel took seven contacts off a 130-update reposition and
  killed the route.
- **Enemies no longer show through near walls.** A reconstructed sample
  between two cast rays takes its occlusion depth from its projected top,
  and close to a wall some tops belong to no depth: they read 255, as if
  the wall were infinitely far, and an enemy behind it was drawn through it.
  In 150 random poses in the first sector, 63 had such a sample; now none
  do. Each empty top takes the nearest class on the near side
  (`tests/test_top_depth_lut.py`). No golden moves: none showed an enemy
  behind such a wall. The legacy profile keeps its bytes.
- **Wall signs stay on their walls.** A fixture was centred at `64 - B/2`
  (B the wall's projected half-height): 64 is the legacy horizon plus the
  OBJ offset, fixed in. On the slim horizon (60) every sign drew 12 pixels
  high, so walking back from one it climbed off its wall into the ceiling
  (8 pixels on compact). It now uses the profile's horizon and sits three
  quarters up its wall at every distance. Only fixture pixels move: the
  tour, world, art and sable goldens that show a sign are re-accepted with a
  note, and the legacy ROM is byte-identical.
- **The conformance adapter waits for the program.** `tools/sameboy_dump.c`
  took a micro-program as finished when `$C0FF` read `$A5`, which SameBoy's
  random power-on RAM already holds about one time in 250: CI #86 compared
  twelve programs against random memory. It now waits for the ROM's own
  write, as the smoke adapters wait for world entry, and takes
  `LUPINE3D_SAMEBOY_SEED`.

---

# Sable Outpost v0.12 — The engine and its game

Sable Outpost, the showcase game of the Lupine 3D engine, is released under
its own name: the cartridge header reads `SABLE OUTPOST` (mask ROM version
7, from 6) and the download is `SableOutpost_v0.12.gb`. Lupine 3D is the
engine that builds it, and this release separates the two. It is the first
release published on GitHub since v0.9, so it also carries v0.10's streamed
renderer and v0.11's three episodes (their sections follow in
`RELEASE_NOTES.md`).

**ROM SHA-256:** `9707e90eea9c51fe73dcf1a6517b639d785ab914a82f66fac763c984941b0fa4`.
Emulator-qualified ([test report](docs/evidence/TEST_REPORT.md)): 322 tests
and 90 release checks pass; the controller route clears all eighteen sectors
in 24,198 verified updates and restarts the campaign; pinned SameBoy (CGB-0,
CGB-E) and mGBA pass, with 87 frozen scenes byte-identical across the host
and every core. Full geometry updates run at 7.1 to 9.9 a second over
sixty-second replays. Not tested on physical hardware or with an original
boot ROM.

- **The release is the game's.** The packager names every asset after the
  showcase (`SableOutpost_v0.12_*`), its manifests name the game and the
  engine, and the release workflow titles the release with the game's name.
  The header title and version are the game's own (`games/sable_outpost/game.json`
  `rom`), so no engine code changed for it.
- **Release tooling.** The release job had an hour, which v0.9's five
  sectors fitted and the eighteen-sector route on one runner does not; it
  has five and a half. `release_check.py` still held the slim capture equal
  to the compact unfolded oracle, a comparison textured walls ended; it now
  checks the fold identity on compact, as `make variants` does, and keeps
  the slim capture as the reference the other slim variants must equal.
  The stale-path test asked Git for the files to read, and the release
  archive's extracted tree has no Git; it walks the tree when there is none,
  so the clean-room suite runs it too.
- **Lupine 3D is an engine; games are data.** A game is a folder with a
  `game.json` (`docs/reference/game-manifest.md`): its levels in episodes,
  enemy kinds, weapons and unlocks, themes and textures, sprite sheets and
  HUD words, screens, songs and sound effects, and the cartridge header.
  Sable Outpost moved into `games/sable_outpost` and is the showcase; every
  ROM it builds, in all ten configurations, stayed byte for byte identical
  through the separation. `--game` (`make … GAME=`, `LUPINE3D_GAME`) builds
  any game, into `build/games/<id>/`.
- **A starter game** (`games/starter`): two levels, two kinds, one theme,
  songs and screens of its own. `lupine new-game DIR` copies it into a new
  game; `lupine game check` loads a game and certifies every level. CI's new
  `starter` job builds it, tours it against its goldens, plays it to its
  ending and restarts it, runs it in SameBoy, builds a game at every content
  limit, and scaffolds a new game from it.
- **Limits a creator can read.** `tools/lupine3d_v4/limits.py` states every
  content limit with the engine fact behind it (20 levels, 3 episodes, 4
  kinds, 4 themes, 7 textures, 128 patterns a screen, …), the loader refuses
  a game past one in those words, and `make limits` proves them together.
  JSON Schemas for every game file are in `docs/schema/`.
- **Fixes found on the way.** A screen held 128 patterns, not the world's
  238 (`show_screen` copies to the map at `$9800`); episode screen indices
  assumed three episodes, so a two-episode game showed the wrong screen; a
  screen character the font lacked drew nothing instead of being refused.
  The fonts gain punctuation and the whole HUD alphabet.
- **The handbook.** The README leads with the engine, and `docs/` is a
  handbook: tutorials (your first game, level and engine change, run
  literally), how-to guides, reference pages checked against the code by
  `make docs-check`, explanation, and a contributor's guide. Pages moved:
  `docs/guide/` and the top-level engine pages to `docs/reference/`,
  `docs/explanation/`, `docs/how-to/` and `docs/engine/`; the test report
  and Phase 5 measurements to `docs/evidence/`; the v0.8 performance audit
  to `docs/archive/`; the campaign, art and steel HUD pages, with the HUD
  design references, to `games/sable_outpost/docs/`.
- **Overlapped publication is the slim default.** The VBlank interrupt
  publishes the streamed tail while the next update casts, so an update is
  bound by its own work instead of waiting for VBlank: textured walking
  6.85 to 7.45/s, turning 9.08 to 9.89/s, two-actor 6.65 to 7.12/s
  (`docs/evidence/PERFORMANCE_PHASE5.md`). `LUPINE3D_OVERLAP_PUBLICATION=0` (`make
  sync`) builds the synchronous tail. The harness validates a presented
  frame against the state it was handed off with (`docs/explanation/verification.md`).
- **The engine is textured.** Every slim Sable build composes every wall
  from its episode's textures; the flat slim profile, its goldens, make
  targets and CLI flag were removed. The flat compositor remains only as the
  renderer of the historical legacy and compact profiles, and the fold
  identity in `make variants` now runs on compact.
- **Exact performance round** (`docs/evidence/PERFORMANCE_PHASE5.md`). The textured
  kernel composes rows under one texel row in 76 T instead of 104 and drops
  its per-tile bookkeeping on one-face columns; every profile gets a leaner
  16x16 multiply, a twelve-step door-panel divide and the crossing
  certificate fused into the DDA loop. Textured walking 6.47 to 6.85/s,
  turning 8.40 to 9.08/s; the flat default of the time (since removed)
  walking 7.77 to 8.08/s, turning 10.25 to 10.84/s. The Phase 5 targets are
  not met.
- **Gameplay fixes** (from the v0.9 correctness audit). A weapon swap no
  longer clears the recovery the last shot started, so a slow weapon cannot
  shed its cost by swapping away; each sector's time is measured from the
  clock `init_simulation` has just reset rather than the previous sector's;
  and moving the continue-code cursor restores a digit the blink had hidden.
  The medkit's cap at 99 health was already in.
- **CI in parallel chunks.** The route runs as a matrix of eight chunks
  sized by measured route updates (`tools/ci_lanes.py`, none above about
  3,700 updates), so the slow job no longer plays it (it took 38.7 of its 40
  minutes with the route); a push to `main` runs to completion instead of
  being cancelled by the next one.
  `python tools/ci_local.py` (`make ci-local`, `lupine ci`) runs every CI
  lane locally in parallel, each in its own copy of the working tree.
- **Textured texture coordinates.** A neighbour difference of 126 or 127
  pulled a pixel's U the wrong way; `check_sable.py` now runs the expansion
  over every difference.
- **The render snapshot copies its map** only when a door or a load changed
  it.
- **The route** stops a close-in walk that is costing health once a step has
  put it beside the actor with a line, instead of walking on past it, and
  counts an exchange's contacts from its first shot, so hits taken turning
  to face a chaser no longer send it away to a firing position. It gives up
  a walk to a firing position after two contacts, steers by the live world
  rather than the presented frame, and shoots a target all but on its own
  row or column straight down the axis while that keeps it near the
  crosshair, so a one-step-off heading no longer grazes the next row's wall.

---

# Lupine 3D v0.11 — Three episodes

v0.10 streamed the renderer; v0.11 turns the six-sector demo into a
campaign of three episodes and eighteen sectors, each a named place, and
gives the engine what a campaign and other developers need: golden-image
verification, an opt-in textured-wall profile, and an SDK.

- **Golden-image verification.** Visual evidence is reviewable snapshots
  (`tools/snapshot.py`, `docs/VERIFICATION.md`): goldens per profile and
  suite, a diff report as a CI artifact, and an explicit `accept --note`
  as the only way to change one. Engine invariants stay hard gates. CI is
  split into fast, slow and campaign lanes, and a CPU conformance lane runs
  every emitted instruction form in the harness and in pinned SameBoy.
- **Textured walls** (opt-in, `LUPINE3D_TEXTURED_WALLS=1`). A row-window
  kernel textures every wall from authored 16×8 PNGs with depth shading,
  byte-exact against its host model (`docs/TEXTURED_WALLS.md`). It costs
  more than the flat compositor and misses its performance gate, so the
  default ROM is unchanged.
- **An SDK for other games.** RGBDS-form `.sym` and `.map` exports, one
  `tools/lupine.py` command line, the level format with a JSON schema and a
  certificate reference, a lossless Tiled (TMX) round trip, an art pipeline
  guide with a palette planner, and a developer guide with a generated
  memory map (`docs/guide/`).
- **Engine limits lifted for the campaign.** Levels are packed five to a
  ROM bank behind a resident directory; a level holds six doors and six
  actors; each episode has its own palette set; four weapons are owned by
  episode; a boss kind closes an episode; and episodes open and close with
  their own screens.
- **Three episodes of six sectors.** Reactor Deep (sectors 7-12) and Signal
  Spire (13-18) join Sable Outpost, each with its own palette set, opening and
  closing screens, and a boss in its last sector; the arsenal grows to four
  weapons by episode. The continue-code table now holds fifty-four codes,
  which changes every code (`docs/CAMPAIGN.md`, "Three episodes").
- **Every sector is a named place.** All eighteen sectors are redrawn as places with
  a purpose (a pump house and spine, a security checkpoint, a turbine hall, a
  flooded tunnel lattice, a hull walk round the whole map, a diamond ring
  round the transmitter), each with the same certificate and enemy mix, and
  each played through by the controller route (`docs/CAMPAIGN.md`, "Named
  places"). Sable Outpost keeps the cells the engine's evidence stands on (the
  spawn, the airlock door ahead of it, the Sentinel, the exit door and lift),
  so its tours and tests move only where a room changed, and every golden
  image of the first sector is re-accepted.
- **Weapons rendered from 3D models.** Each weapon is a small 3D model
  rendered straight at the console's resolution with banded shading, part
  outlines, in a larger 40×32 window right of centre with four animation
  cels (`tools/render_weapons.py`, `docs/ART_PIPELINE.md`).
- **Texture sets per episode** (textured profile). Reactor Deep and Signal
  Spire wall their sectors in their own structure and machinery textures;
  the level's palette set selects the set (`docs/TEXTURED_WALLS.md`). All
  seven wall and door textures were redesigned as one set (bolted steel
  panels, louvred vents, sliding doors with a hazard band, riveted reactor
  plates, coolant pipes, recessed hull panels, relay racks), and doors now
  darken along their own palette order instead of turning bright at a
  distance.
- **Engine fixes the eighteen-sector route found.** The projection table's
  component-zero slice now saturates to the far clamp like the host model:
  an exactly axial ray that the Q14 crossing order carried across the
  perpendicular plane used to project a full-height column in the middle of
  a far wall (every profile's ROM changes in banks 2-3; no accepted golden
  shows the case). A medkit tops health up to 99 and no further (it
  saturated at 255 and the HUD showed 141 as "41"). An actor strikes across
  a diagonal only when the corner is clean, the same rule the player's shot
  obeys. The compiler refuses an actor inside a wall or behind a
  Sentinel-locked door, whether or not the level has a card door.
  `init_vram` read the weapon pointer table with the weapon bank already
  mapped; the table is resident data that the textured build places above
  `$4000`, so the first weapon loaded as blank patterns there. It is now read
  with bank 1 mapped, as the swap already did.

---

# Lupine 3D v0.10 — The renderer streams

v0.9 spent a whole LCD interval idle inside every full geometry update: the
hidden patterns went up in one VBlank, and the CPU then spun until the next
one to send the map, the attributes, the HUD and OAM. v0.10 removes that
interval without moving a pixel.

- **HBlank-streamed publication.** The hidden dynamic patterns and the whole
  hidden tile-number map now travel by HBlank DMA while `render_view` is
  still composing, one block per visible line into the bank and map the
  displayed page never reads. `render_view` hands each column's patterns
  over as it finishes them; the tail is one VBlank of banked GDMA (masks and
  attributes, at most 62 blocks) plus the HUD, OAM and the flip. The 192
  bytes of CPU map/attribute copying are gone. Every descriptor, packet and
  VRAM byte is unchanged; only the presentation time moves. The legacy
  profile keeps the staged packet byte for byte, and `LUPINE3D_HDMA_STREAMING=0`
  builds it on any profile. See `docs/STREAMED_PUBLICATION.md`.
- **Exact engine savings.** The folded compositor's rows are unrolled and
  each column writes its fifteen map cells from one pointer; the column scan
  keeps its extremes in registers and the row classification folds the row
  origin into immediates; the depth pass keeps every actor's projection so
  the draw pass restores it instead of projecting the same inputs again; the
  wall-key compare, the snapshot copies and the actor slot copies run eight
  or ten bytes per counter step; the midpoint descriptors and cast results
  are stored without a result-byte round trip. No pixel, packet or dynamic
  allocation order moves.
- **A sixth sector.** Cryo Vault, in ROM bank 246, with the same compiler
  certificate as the other five. The continue-code table grew to eighteen
  codes, which changes every code.
- **The harness models HBlank DMA** (`tools/sm83emu.py`): a block per visible
  line, read through SVBK and written to the bank VBK selects, with the CPU
  stall charged where it lands; a commit reports HBlank and VBlank blocks
  separately and is safe only if no transfer is still active at the flip.

**Measured** on the host harness against the v0.9 ROM: the nine-image tour
falls from 866,119 to 674,644 T-cycles per full update (−22.1%) and the
living-world route from 719,567 to 632,973 (−12.0%). Sustained sixty-second
trials deliver 6.80–10.27 full geometry updates/s against v0.9's 5.53–8.15 on
the same replays; turning reaches the ten-updates/s target for the first
time. The table is in `docs/TEST_REPORT.md`.

**Changed pixels:** six, in one capture of the nine-image tour — the helmet
portrait's blink in `09_exit_approach`, because that update now completes one
LCD interval earlier and the accepted tick lands differently on the 62–63
blink window. v0.10 carries its own oracle, `playtests/sable_v10_capture_pixels.json`,
with the other eight hashes identical to v0.9's, which is retained.

**Route:** the controller route died once on the faster ROM, standing in a
doorway firing at a Sentinel pressed against a wall corner that its sampled
sight test cleared and the ROM's exact centre ray did not. It now kites from
contact range and moves one cell when an exchange settles nothing; the
gameplay it exercises is unchanged.

---

# Lupine 3D v0.9 — The campaign

v0.8 was one level, one enemy and no way to stop playing but turning the
console off. v0.9 is a game.

- **Five sectors**, chosen at runtime from their own ROM banks, behind a title
  screen. Clearing one shows an intermission, dying retries the sector you
  lost, and clearing the last one ends the campaign and restarts it.
- **Four-digit continue codes.** The cartridge has no RAM, so progress is
  written down: clearing a sector shows its code, and SELECT on the title opens
  code entry. Generated at build time, one per sector and skill, compared byte
  by byte on the console.
- **Three enemy kinds**: the armoured Sentinel, the quick skirmisher that
  carries a keycard, and the heavy warden. They patrol a heading and turn at
  walls rather than bobbing in place, and they stay dormant until you come
  inside the radius their level authors.
- **Two weapons.** SELECT swaps the shotgun for a slug rifle — two damage for a
  long recovery. The pattern window fits one weapon's cels, so the other one's
  stream in on the swap.
- **Keycard doors.** A drop is whatever the actor that left it was; two sectors
  lock a door on the way to the exit, and the compiler refuses a level whose
  card sits behind the door it opens.
- **Three skill settings**, chosen with left and right on the title, scaling
  contact damage only.
- **Music**: a title theme, an in-game loop and a victory sting on CH2/CH3/CH4,
  with CH1 left to nine sound effects so gunfire never cuts a bar. The
  sequencer never ticks in VBlank and never switches a ROM bank.
- **Results that report something**: the intermission carries kills and time
  beside the code, the ending the whole run.

**Fixed:** no runtime digit below row eight had ever been visible. The map row
offset passes 255 and the carry was dropped, so every continue code and the
skill indicator were written where nobody could read them.

**Changed pixels:** the reticle moved to OBJ palette 4 so palette 6 could carry
a third enemy kind. That is eight pixels a frame, the crosshair's own, and
v0.9 therefore carries its own nine-image capture oracle beside the retained
v0.8 one. No hash was edited.

**Contracts:** the `$4000` ceiling was a proxy for the MBC5 rule, and it had
160 bytes left. `bank_safety.py` checks the rule itself against the emitted
image in six clauses, with entry points read out of the cartridge's own reset
and interrupt vectors; bank-neutral sections now live above `$4000` in bank 1.
Publication budgets, object and mask limits and the 3,000-byte resident reserve
are unchanged and still enforced.

**Performance:** the nine-image tour measures **6.611 full geometry updates/s**,
unchanged across all of this work. The ten-updates/s target remains unmet, and
the original mean/p95 quality gate `Q <= (B + P) / 2` still fails on the
v0.8 visual tradeoff, which was explicitly accepted and is inherited here.

**Caught by the pinned cores:** the weapon swap turns the LCD off to stream
patterns, and it was putting back a constant `LCDC` — clearing the bit that
says which background page is displayed, while the compositor still believed
the other one. The next frame's hidden-page copy then wrote the visible map.
It restores the `LCDC` it found now. The swap also fired on the first frame of
a real power-on, because the weapon state lives in fixed WRAM the console does
not clear; boot initialises it. Neither fault was reachable in the project's
own harness. Both independent adapters also predate the title screen and now
press START before they drive their route.

**Qualification:** 229 tests, 89 release checks, two byte-identical pixel
oracles, 53 frozen wall-reuse comparisons, variant pixel equality, a
2,961-update controller-only route that clears all five sectors with zero
game-RAM writes and zero unsafe GDMA starts, and the pinned **SameBoy CGB-0 and
CGB-E** and **mGBA** lanes plus 87 frozen independent-witness scenes, all
matching the harness on this ROM. Physical hardware and an original Nintendo
boot ROM remain untested and unavailable.

**ROM SHA-256:** `e59f722b698b545e75e5dbb2cdfe3810c5cc6a3ec96e38e868c09d286e2a9b89`.

See [the campaign write-up](games/sable_outpost/docs/campaign.md), [architecture](docs/explanation/architecture.md)
and the [development guide](docs/engine/development.md).

---

# Lupine 3D v0.8 — Sable Outpost

A visual overhaul with native animated sprites, a larger world view and a cleaner steel HUD.

- Expand the world from 160×96 to **160×120** while cutting the HUD from 48 to **24 pixels**. Preserve horizontal FOV and projection scale.
- Make the original Sable art and animation the default: five shotgun cels, two flashes, twelve Sentinel frames at three sizes and four helmet states. Include generated masters, native indexed sources, metadata and deterministic compilation.
- Replace the cluttered panel with readable health, the approved armoured helmet, an enemies-remaining skull and **GOAL / HUNT → GOAL / EXIT**. Keep the upper/lower rails intact and space objective text below the top border.
- Preserve coherent snapshots, pending fire feedback, immediate gameplay death and bounded cosmetic death animation. Preload weapon cels and animate through OAM references.
- Qualify the taller display with 480-byte staging and bounded hidden-map CPU copies. Keep the 176-block staged GDMA ceiling, object/mask limits and 3,000-byte resident reserve.
- Retain legacy artwork, the exact beta.6 ROM path, historical oracles and disabled rendering experiments. Reprojection and foreground-only feedback remain off.
- Overhaul the README, development/art/architecture guides, test report and AGENTS.md. Correct research tooling to use explicit viewport domains and preserve archived results.

**Performance:** active sustained scenes measure **5.50–7.92 full geometry updates/s**. The larger view and animation miss the original mean/p95 half-gains budget; the owner explicitly accepted that visual tradeoff. The ten-full-updates/s target remains unmet. Cached presentations are counted separately.

**Qualification:** 140 tests, 86 release checks, nine current RGB fixtures, 53 frozen wall-reuse comparisons, controller-only completion/restart, eight sustained scenarios and 87 frozen scenes matching pinned SameBoy CGB-0/E and mGBA. Source archives rebuild byte-for-byte and run the suite after extraction. Emulator-qualified only; physical hardware and original boot-ROM testing are unavailable.

**ROM SHA-256:** `a5f3d54eb7d9be446d2d6ca36c010e9be264792c14c73f9691d6027871057ccb`.

Download `Lupine3D_v0.8.gb` to play or the `_complete.zip` for source, assets and evidence. See [the v0.8 test report](docs/evidence/TEST_REPORT.md), [architecture](docs/explanation/architecture.md) and [development guide](docs/engine/development.md).

---

# Lupine 3D 0.7.0-beta.6 — Rendering qualification

- Enable compact folded strips, invariant camera setup, narrow cooperative-yield contexts and exact attribute padding. The existing nine-image visual oracle and 53 frozen comparisons remain exact.
- Reduce mean full-frame time by 3.7–7.5% across six approximately 60-second motion scenarios. Moving geometry rates range from 6.52/s in the two-actor arena to 9.67/s while turning; the 10/s target remains unmet.
- Save 3,840 microstrip table bytes and 2,816 net linked bytes. Resident free space is 5,939 bytes; fixed-ROM execution limits, the 3,000-byte reserve and publication budgets remain enforced.
- Implement complete-key tile caching, certified four-anchor packets, physical-depth refinement, Q8.8 actor transforms, atomic admission, physical door identity, paged projection storage, near-field arithmetic and foreground events as gated experiments. Candidates that fail measured gates remain disabled.
- Add reconciled host timing, LCD-indexed controller replays, 51 geometric witnesses, independent-core scene adapters, current-ROM quality budgets and immutable comparison archives.
- Validate both committed atlas profiles at release time, including all signature/pattern bytes and full-composition diagnostic routes. Retraining remains an explicit research operation so packaging preserves the qualified ROM. Repair diagnostic snapshot updates and select the actual compact entity atlas during its measurements.
- Preserve archived research during packaging. Fresh static-geometry checks compare matching solid-cell geometry; finite-door tests remain separate, and existing error thresholds are unchanged.
- Pass 137 tests, controller-only completion/restart, SameBoy CGB-0/CGB-E and mGBA checks, and deterministic clean-room source rebuilds. Preserve the original v1 ROM hash and historical fixtures.
- Document development directly on `main`. Physical CGB and flash-cartridge access are unavailable; this is an emulator-qualified prerelease.

Production ROM SHA-256: `48c80fcd588365a38eb08c7ce1cc4ce2439c432127e4f389651b8e0bdafe2e99`.
See [implementation and evidence](docs/archive/RENDERING_IMPLEMENTATION.md) and the
[beta.6 test report](docs/archive/TEST_REPORT_BETA6.md). The version update changes release
metadata; the production ROM is byte-identical to the qualified performance
milestone.

---

# Lupine 3D 0.7.0-beta.5 — Streaming columns and prepared rays

- Sequential 80-to-160 column expansion and register-resident surface/door scans preserve rounding, edge recasts, event counts and stencil precedence.
- Aligned cartridge records provide coarse directions, correction, projection addresses and Q14 components. Raw probes and generic LOS retain their original paths; a flag-off build preserves the arithmetic implementation.
- All 53 frozen scenes remain exact. Mean complete-update cost falls 9.66%; column expansion is 65.67% cheaper and surface scans 51.69% cheaper.
- Short live trials measure 6.68 full geometry updates/s walking, 9.19 turning and 8.77 walking while turning. A one-LCD-frame B tap opens the door, with multiple apertures validated. Counts distinguish full geometry from cached presentations.
- 84 tests, nine unchanged reviewed RGB captures, arithmetic/prepared variants, 252-presentation controller-only completion and independent SameBoy CGB-0/CGB-E plus mGBA checks pass.
- Uses 1 MiB of formerly unused cartridge capacity and four banked WRAM bytes; leaves 304 KiB of cartridge capacity and 3,123 resident bytes free. No additional HRAM or VRAM; publication budgets unchanged.

All four planned steps are complete. These are emulator measurements; original CGB and flash-cartridge acceptance remains pending. See [implementation and evidence](docs/archive/COLUMN_PERFORMANCE.md).

---

# Lupine 3D 0.7.0-beta.4 — Wall reuse and combat presentation

- Exact 290-byte camera/map/door/configuration comparison retains unchanged wall geometry, depth, tiles and attributes. Reload generations invalidate in-flight views safely.
- Entities, fixtures, firing feedback and HUD update independently against retained depth. Separate OBJ ownership keeps masked patterns hidden until OAM publication, without flipping the BG page.
- Completed presentations are counted separately from genuine geometry renders. Existing full-packet timing bounds remain unchanged; cached packets transfer at most 32 OBJ blocks in one VBlank.
- Stationary combat measures 40.37 presentations/s, with three brief fire taps reaching the next muzzle scanline at about 56 ms. Safe-start idle measures 59.71 presentations/s. These are emulator trials, not original-LCD measurements.
- The mixed combat route averages 692,666 cycles, with 25 cached updates out of 47. Full first-frame work costs 1.31% more on the 53-scene corpus; changing cameras/doors still require wall rendering.
- 80 tests, 53 exact cached/full scenes, nine unchanged reviewed captures, reuse on/off and folding variants, 233-update controller-only completion, and SameBoy CGB-0/CGB-E plus mGBA checks pass.
- Adds 297 WRAM bytes; no new HRAM or VRAM. Cold-map relocation preserves 3,123 free resident bytes and the full stack reservation.

All four planned steps are complete. Original CGB/flash-cartridge validation remains pending. See [implementation and evidence](docs/archive/WALL_REUSE.md).

---

# Lupine 3D 0.7.0-beta.3 — Gameplay performance

- Precision rays continue from the last certified crossing instead of retracing the same cells. Axial rays and origin-door casts retain full initialization.
- Sliding-door division keeps quotient/remainder in registers and processes four bits per loop. Product-table bank selection uses a shorter exact rotate/mask sequence.
- The startup map follows the aligned hot tables. Resident code/data retain 3,123 free bytes; HRAM, VRAM, cartridge capacity and gameplay rules are unchanged.
- All 53 frozen scenes retain exact descriptors, depths, surfaces, tiles, maps, objects, HUD and RGB. Their mean update cost falls 8.73%, and wall-casting cost falls 10.56%.
- The live combat diagnostic averages 1,218,677 cycles; its slowest update costs 1,685,836 cycles (4.98 visual updates/s). Fixed-tick simulation means live actor poses vary with rendering speed.
- 75 automated tests, nine unchanged reviewed captures, controller-only completion in 236 updates, and independent SameBoy CGB-0/CGB-E and mGBA checks pass.

The Sable artwork and level remain intact. Original CGB/flash-cartridge acceptance is still pending. See the [step-by-step implementation and evidence](docs/archive/RUNTIME_PERFORMANCE.md).

---

# Lupine 3D 0.7.0-beta.2 — Sable Outpost

- Original gunmetal/green environment, illuminated teal doors, amber utility lighting and coherent functional colours.
- Sixteen map-authored wall fixtures: vents, caged lights, sector signs and moving door access emblems. Physical segment/cell masks prevent decoration leaking across corners or openings; at most four fixture objects share the existing bounded world pool after actors.
- New shotgun and gloved hands, red-armoured Sentinel animation, medical crate, exit beacon palette, clear reticle and muzzle flash.
- A 78-pattern instrument-panel HUD with large health/hostile counts, visor portrait, controls and LOCK/OPEN/DEAD/DONE text. A verified line-96 addressing switch uses spare bank-0 VRAM without reducing the wall atlas.
- HUD preparation runs before VBlank. Publication uses a measured 24-pattern single-window budget and the documented 160-M-cycle OAM wait. Default large packets remain atomic over two VBlanks; the optional reprojection stress case can use three.
- 72 tests, reviewed RGB fixtures, close-up art tour, controller-only completion and independent SameBoy CGB-0/CGB-E plus mGBA checks.

The protected room/corridor topology and wall mathematics remain intact. This visual pass adds measurable rendering work; original CGB/flash-cartridge validation remains pending. See [visual implementation](games/sable_outpost/docs/art.md) and [test report](docs/evidence/TEST_REPORT.md).

---

# Lupine 3D 0.7.0-beta.1 — Living Renderer

Implements the software items deferred by the foundation alpha:

- Certified selective Q14 crossing order removes all ≥8-pixel top errors in the full retained 24,384-view corpus; maximum is 4.489522 pixels. Historical evidence remains unchanged.
- True sliding centre-plane doors share geometry across rendering, LOS, hitscan and radius collision.
- A 16-bit timestamped input queue drives fixed-tick simulation. Rendering yields cooperatively while preserving a separate immutable WRAM snapshot.
- Masked hardware 8×16 billboards, three size LODs with hysteresis, four bounded actor slots, nearest-first submission and scanline admission.
- Per-face colour metadata separates neutral steel, muted-green machinery and recognizable cyan/white doors. No eye-height rail returns.
- Matched dynamic patterns, masked sprites, attributes, map, HUD and OAM publish atomically, with bounded two-VBlank staging for large packets.
- Optional turning reprojection shifts published world objects with the BG while retaining fixed UI; remains disabled by default.
- Pinned SameBoy CGB-0/CGB-E and mGBA lanes, two-Sentinel acceptance scene, folded/unfolded RGB equivalence and controller-only level completion.

This is a playable beta, not a blanket speedup or original-hardware certification. The combat diagnostic reaches 4.26 visual updates/s in its slowest view even though controls/simulation use fixed ticks. Pixel masks retain two-pixel conservative wall-depth precision. See [implementation status](docs/archive/OVERHAUL_IMPLEMENTATION.md) and [test report](docs/evidence/TEST_REPORT.md).

---

# Lupine 3D 0.7.0-alpha.1 — Renderer Foundation

First implemented milestone of the overhaul, not completion of the full roadmap.

- Paired projection records retain actual cast depth in the same 2.25 MiB ROM budget.
- Latent door-jamb faces have physical IDs in all 16 door-state combinations.
- Current-pose hitscan ignores cached visibility; entities share the wall camera focal length and project their feet from depth.
- Signed BG addressing separates OBJ art from world patterns; the full 121-pattern atlas coexists with entities.
- Folded composition reuses upper patterns through CGB Y-flip and a paired palette; unfolded A/B remains available.
- Cold boot assets move to bank 152; the stack moves to fixed WRAM; generated memory budgets enforce fixed-bank hot code.
- Large packets stage hidden patterns, then publish BG/HUD/OAM together.
- Joypad polling no longer advances the VBlank clock; bounded AI catch-up retains tick remainder.
- 47 tests, controller-only level completion, and pinned SameBoy CGB-0/CGB-E smoke lanes.

The opened-airlock RGB fixture intentionally removes 50 false-crease pixels after inspection. The other eight legacy captures are unchanged; all nine folded/unfolded captures match each other.

High-precision tail fallback, fully fixed-rate simulation, masked multi-entity rendering, real sliding apertures and original-hardware validation remain unfinished. See [implementation status](docs/archive/OVERHAUL_IMPLEMENTATION.md).

---

# Lupine 3D 0.6.3 — Spatial Clarity

This revision makes the authored world read as geometry rather than a collection of decorative screen marks.

### Rendering grammar

- Removed the eye-height machinery rail and its horizon-locked row-48 presentation path.
- Decoupled physical surface segments from material paint; adjacent static materials now share one segment across a continuous exposed plane.
- Added `PIXEL_SEGMENT[160]` so the emitted ROM and host oracle classify physical breaks from the same authoritative certificate.
- Reduced true corners to a one-pixel dark crease, removed full-height cell ribs, and retained a wider run-centred door signal.

### Level and tooling

- Rebuilt Hangar Breach as a tighter room-and-corridor graph with meaningful door cuts, staged turns and a partitioned combat room.
- Added compiler gates for unreachable walkable cells, weak doors, critical-path length/turns, sightline length, open-room span and material fragmentation.
- Added a nine-frame spatial-coherence tour and refreshed the exact RGB oracle only after inspecting the generated contact sheet.
- Expanded the suite to 37 tests and added exact 160-column segment checks to both the ROM differential tests and driven harness.

The accepted map certificate is: 70 walkable cells, zero unreachable cells, 15 steps/five turns to the Sentinel, six-cell maximum sightline, 4×3 maximum open rectangle, an 11-cell minimum door cut, and zero paint seams/singleton runs on continuous surfaces.

Original Game Boy Color and independent-emulator certification remain pending.

---

# Lupine 3D 0.6.2 — Iron & Ash

This release gives Hangar Breach an original industrial-horror presentation pass while keeping the renderer-heavy timing contract intact.

### Original art and interface

- Rebuilt the CGB palettes around soot, concrete, oxidized metal, bone highlights and warning red.
- Replaced the foreground art with an original twin-bore weapon, visible gloves, asymmetric muzzle bloom and corner reticle.
- Redrew every Sentinel LOD/frame with a horned sensor crown, skull mask, layered armour, reactor core and clearer attack/hurt silhouettes.
- Reworked the medkit into a medical crate and refined the pulsing world-space exit beacon.
- Added a dark-metal status plate with original health/objective icons, Lupine badge and live two-digit fields mirrored across both BG pages.

### Surface grammar and performance

- Authored machinery-panel cells throughout Hangar Breach without changing its collision or progression topology.
- Added world-cell double ribs and a world-height machinery rail that never repeats in screen-tile space.
- Made the rail an entity-heavy profile feature: two rare seam IDs become light/shadow rail tiles, while renderer-heavy scenes retain those seams and omit all rail hot-path work.
- Conservatively remove the rail from mixed material/rib boundary tiles, preventing visual leakage and retaining exact-atlas hits.
- Deferred live-HUD VRAM writes beside publications above the established 72-block threshold, preserving the forced 120-block VBlank guarantee.
- Relocated cold palette data after the aligned hot tables, avoiding a wasted 1 KiB alignment page.

### Verification

- Added a 0.6.2 nine-capture RGB oracle for the intentional presentation change.
- Expanded the suite to 36 tests with exact surface-rail tiles, UI payload, status-map and emitted HUD-routine checks.
- Renderer-heavy route: 972,658.815 mean cycles, 1,124,756 maximum, 54 dynamic tiles, and nine of nine RGB captures exact.
- Living World route: 831,711.077 mean cycles, 1,125,776 maximum, 42 dynamic tiles, zero unsafe GDMA starts, and all combat/door/exit state assertions passing.

All art and interface assets in this release are original to Lupine 3D; no artwork or game data was imported from another title.

Original Game Boy Color and independent-emulator certification remain pending.

---

## 0.6.1 — Hangar Breach

This revision replaces the research maze with a compact E1M1-inspired level and promotes doors, spawning and exiting into explicit engine systems.

### Level and progression

- Added the original 16×16 Hangar Breach layout: protected southern start, staged approach, central zig-zag tech hall, optional courtyard branch and separate exit wing.
- Moved the Sentinel onto the mandatory route so the first enemy encounter cannot be bypassed accidentally.
- Added compiler-enforced player-radius clearance, minimum actor separation and open-door reachability for the authored start/exit contract.
- Added a two-phase projected exit beacon that is 8×8 at distance and mirrors into a 16×16 near panel.

### Door system

- Replaced the single global door with four independently stateful six-byte WRAM records.
- Added named authored doors, validated frame orientation, exact interaction selection and independent eight-step animation.
- Added a Sentinel-locked exit door with distinct blocked audio. Sentinel death unlocks the interaction but does not open the door automatically.
- Extended the host oracle and driven harness to validate partially retracted door geometry and per-door state/fraction telemetry.

### Verification

- Isolated the frozen renderer benchmark from the active gameplay level so deliberate map revisions cannot weaken the nine-capture pixel contract.
- Expanded the suite to 35 tests, including unsafe-spawn, malformed-door and missing-exit-lock rejection.
- Expanded the Living World route to cover safe spawn, normal opening, locked rejection, combat, pickup, exit unlocking, beacon visibility and completion.

Original Game Boy Color and independent-emulator certification remain pending.

---

## 0.6.0 — Living World

This release turns the renderer core into a playable vertical slice while preserving the accepted empty-world pixels exactly.

### Geometry and rendering

- Added corrected-perpendicular `RAY_DEPTH[80]` and build-time `RAY_SEGMENT[80]` certificates.
- Made adaptive interpolation segment-aware and added exact physical recasts at ambiguous surface boundaries.
- Added renderer-heavy (121 patterns) and entity-heavy (80 patterns) level-selectable VRAM profiles. The entity profile frees 41 tile IDs and remains overflow-free across 24,384 corpus views.
- Added a hybrid OAM billboard path with 8×16 far and 16×32 near LODs plus per-strip wall-depth clipping.
- Added atomic 160-byte shadow-OAM publication, permanent weapon/UI reservations, and budget-aware deferral beside worst-case GDMA.
- Added an optional compile-time ±4-pixel VBlank turn-reprojection experiment with guard tiles and a scanline-96 HUD reset.

### Living World slice

- Added an authored JSON level pipeline with map materials, spawn points, doors, pickups, triggers, exit, palette and VRAM profiles.
- Added one original Sentinel with dormant, patrol, chase, attack, hurt and dead states.
- Added exact-grid line of sight, low-frequency AI, hitscan damage, player damage, death, medkit drop, exit activation and level completion.
- Added axis-separated radius collision and an eight-step door that remains solid until its projected panel fully retracts.

### Verification and tooling

- Expanded the suite to 34 tests, including both VRAM profiles, depth/segment identity, OAM limits, clipping, AI/combat, door timing and the reprojection build.
- Added a second driven playtest that completes the Sentinel combat/drop/pickup/exit loop.
- Preserved all nine frozen empty-world RGB captures byte-for-byte.
- Retained the 41-pixel exceptional-tail certificate after a full 3.9-million-column correction experiment improved only one column and did not justify runtime complexity.
- Updated clean-room packaging, CI evidence, preview generation and documentation for the current implementation.

Original Game Boy Color and independent-emulator certification remain pending.

## 0.5.0 — Responsive, inspectable engine core

v0.5.0 preserves every accepted v0.3 RGB capture and the v0.4 rendering
architecture while making input, research, and maintenance safer.

### Engine changes

- Added a minimal VBlank interrupt sampler. It records the latest held state
  and OR-latches rising edges, while all movement and pose mutation remain in
  the main loop.
- Main-loop input consumption is atomic and uses a stable held-state snapshot.
  A short press that begins and ends during a long render is therefore acted
  on at the next simulation boundary instead of being lost.
- Extended the project emulator with VBlank IF generation, interrupt dispatch,
  EI delay, RETI behavior, and live joypad sampling.
- Split the 90 KB ROM builder into layout, resources, reference-model, emitter,
  and linker modules while preserving the public `build_rom` API.

### Research and verification changes

- Added a full tail-failure corpus with pose, physical column, expected/actual
  face, top error, map neighborhood, CSV/JSON evidence, and a visual sheet.
- Added an emitted-ROM exact-atlas Pareto study. The full 121-pattern cache is
  retained because it remains fastest; the 80-pattern option frees 41 tile IDs
  at a measured 2.28% mean-cycle cost.
- Added regression certificates for the known 41-pixel tail case and for a
  one-frame A-button pulse captured during rendering.
- Expanded the suite from 25 to 27 tests. All nine RGB captures remain exact;
  the driven mean is 910,156 cycles/update with zero unsafe GDMA starts.

## v0.4.0 exact-fidelity performance architecture

## Exact-fidelity performance architecture

v0.4.0 preserves the v0.3.0 hybrid 160-column image byte-for-byte while
reducing the driven tour's mean update cost by 18.61%.

### Engine changes

- Moved hot scalar DDA, projection, and compositor state into a stable HRAM
  ABI so the v0.4 assembler emits shorter/faster `LDH` accesses.
- Packed 1,024 ray directions as sequential `{absX, absY, stepX, stepY}`
  records and shared player-fraction boundary preparation across each cast.
- Added a corpus-trained exact boundary atlas: 255 signatures, 121 VRAM tile
  patterns, and 41.377% corpus coverage. Hash collisions are resolved by a
  full ten-byte comparison.
- Converted the ROM from 32 KiB ROM-only to 4 MiB MBC5, with no cartridge RAM.
- Added a 2,359,296-byte exhaustive projection-result LUT and a 65,536-byte
  exact DDA product LUT. The executable remains in fixed bank 0 and restores
  ordinary data bank 1 after each lookup.
- Removed the now-unused runtime projection divider and resident height table.

### Validation changes

- Expanded the project harness with MBC5 ROM-bank behavior.
- Added atlas reconstruction and banked-LUT layout tests.
- Tightened hot-path and full-update cycle ceilings.
- Added a frozen nine-capture RGB-pixel oracle from v0.3.0 to the driven
  playtest; any visible change now fails the run.
- Preserved the frozen v0.1.0 ROM SHA-256 oracle.

### Measured results

- driven mean: 1,118,243 → **910,143 cycles/update** (-18.61%);
- driven maximum: 1,264,820 → **1,124,736 cycles** (-11.08%);
- minimum driven rate: 6.632 → **7.458 updates/s** (+12.45%);
- isolated six-pose cast+render mean: 1,008,489 → **899,372 cycles** (-10.82%);
- exact capture pixels: **9/9**;
- unsafe GDMA starts and dynamic-tile overflows: **0**.

The VBlank ISR/staging and residual signature-cache ideas were investigated
but not retained because the measured workload did not benefit. Details and
checkpoint data are in `docs/archive/PERFORMANCE_V4.md`.

Original Game Boy Color and independent-emulator certification remain pending.
