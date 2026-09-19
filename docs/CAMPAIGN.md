# From tech demo to game

Lupine 3D shipped v0.8 as one hand-authored level with one enemy, no framing
screens and no way to stop playing except turning the console off. This
document records what turned it into a game, what each decision cost, and what
is still missing. Contracts live beside their source; this is the summary and
the evidence.

## What the game is now

| | v0.8 | main |
| --- | --- | --- |
| Levels | 1, chosen at build time | **5**, chosen at runtime from their own ROM banks |
| Enemies | 1 Sentinel | 1–4 actors, **two kinds** |
| Framing | none | title, intermission, results and ending screens |
| Difficulty | fixed | **three skill settings**, chosen on the title |
| Persistence | none | **four-digit continue codes** |
| Audio | three effects on CH1 | a **sequencer on CH2/CH3/CH4** plus seven effects on CH1 |

A run starts at the title, where left and right choose a skill and Select opens
code entry. Each sector is cleared by killing every actor and reaching the exit;
clearing one shows the code for the next, dying retries the sector that was
lost, and clearing the last one ends the campaign.

## The five decisions that shaped it

**Levels became data, not opcodes.** Selection used to be assembled into
immediate operands — entity counts, fixture counts, the pickup value, the
segment-table bank. Each campaign level now owns one ROM bank from 241 at fixed
offsets, and the loader derives that bank from `LEVEL_INDEX` alone. The hot
geometry path pays one fixed-WRAM load per wall hit for it. The resident wall
atlas is still chosen at build time, so every campaign level must declare the
same VRAM and palette profile; `layout.py` rejects a campaign that disagrees.

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
| Music sequencer | 84 T-cycles counting down, 1,048 on a row boundary, **149 mean** — 0.106% of an LCD interval |
| Segment lookup | one extra fixed-WRAM load per wall hit |
| Resident ROM free | **7,166 bytes** below `$8000` (floor 3,000) |
| Fixed code | ends at `$3050` — **4,016 bytes** below the `$4000` bank-switching ceiling |

That last row used to read `$3F60`, 160 bytes, and it was the next wall. The
ceiling was a proxy: the hardware rule is that code writing the bank register
must live in bank 0, not that all code must. `bank_safety.py` checks the rule
itself against the emitted image, so sections that never switch a bank, never
run inside another section's window and are unreachable from an interrupt are
emitted after the data and land above `$4000` in bank 1. Of 15.8 KB of
instructions, 1.6 KB are genuinely pinned below the boundary.

## Evidence

ROM `275adaca71f8308b799e6d5745fb46fcb80a969e45360614ee912bc945d6e106`, default
slim/Sable configuration.

- **169 automated tests** (`make test`), including the campaign's bank layout,
  the sequencer's placement and bank contract, enemy kinds and skill scaling,
  and a continue-code round trip with a refused code.
- **Nine-image pixel oracle byte-identical** (`make playtest`) across every
  change in this work. Nothing here was allowed to move a pixel of the shipped
  scenes.
- **89 release checks** (`tools/release_check.py`), including a per-level
  readability certificate for all five sectors rather than only the first.
- **3,356-update controller route** (`tools/playthrough.py --restart`): every
  sector cleared, every drop collected, every intermission crossed and the
  ending restarting the campaign, on controller input alone, with **zero game
  RAM writes** and **zero unsafe GDMA starts**. Every frame is checked against
  the host geometry and compositor models.
- **Variant pixel equality** (`make variants`): folded/unfolded,
  reuse-disabled, prepared-rays-disabled and the two-actor level.
- `make wall-reuse`, `make motion`, `tools/check_sable.py`,
  `tools/check_display.py` — all passing.

**Not run here:** the pinned SameBoy and mGBA lanes and
`tools/independent_witnesses.py`. SameBoy's build needs `cppp`, which is not
available in this container. Work touching interrupts, banks or publication —
the sequencer's STAT placement especially — has not been confirmed on those
cores and must be before a release.

The `sustained` CI job compares against a baseline pinned at commit
`466bd09`, which predates the v0.8 display change. The current host oracle
cannot validate that ROM, and could not at the v0.8 tag either; that job is
manual-only, so it does not gate anything, but the pin needs refreshing.

## Still missing

- **Sector statistics** on the intermission and ending. Blocked on fixed-WRAM
  capacity: the four runtime digit slots are spent on the continue code, and
  raising the capacity needs twelve bytes the `$C7E0` window does not have.
- **A second weapon.** The 80-pattern shotgun window leaves ten free OBJ
  patterns, so this means streaming the active weapon's patterns on switch.
- **Keyed doors and pickup kinds.** `DOOR_FLAG_EXIT` is compiled and never
  read, and `PickupSpec.kind`/`source` are parsed and ignored.
- **A third visible enemy kind**, which needs the weapon and reticle palettes
  re-planned.
- **Patrol routes.** `sentinel_patrol_step` now carries and collides correctly,
  but it is still a bob in place.
