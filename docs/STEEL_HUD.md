# Native steel-console HUD

The default development ROM implements the approved whole-HUD direction at
160×24 pixels, below the existing 160×120 world. A connected steel chassis,
dark readouts, bold 6×10 health digits, a small ivory skull and compact
objective text replace the flat strip. The portrait follows the approved armoured helmet concept: a recessed brow,
narrow visor, cheek plates and central respirator. Keep the face covered;
the intervening uncovered human portrait was rejected.

## Art and animation

`tools/lupine3d_v4/steel_hud.py` contains deliberately authored native pixels
and glyphs based on the [concept study](design/hud-steel/README.md). The concept
was not automatically shrunk into the game. `tools/adapt_sable_art.py` compiles
the indexed `hud_steel` and `helmet_steel` sibling assets; the original native
assets and historical image fixtures remain intact. Builds only read these
validated PNGs and never call image generation.

The four flat HUD colours are near-black, steel, ivory and muted teal. Visor
and helmet highlights remain readable in normal, blink, hurt and dead cels.
The 16×16 portrait keeps four pixels of vertical space. Slim-mode blink
selection uses snapshot ticks 62–63 modulo 64, so startup shows an alert face.
Visible duration still follows coherent presentation cadence. Compact and
legacy profiles keep their historical artwork/timing.

Dynamic glyphs and portrait cels are composed over their chassis background
before 2bpp compilation. This preserves the divider, upper bevel and lower rail
when health, portrait or status tiles change on either map.

## Skull and objective

The skull counts living Sentinels remaining, not kills already made. The
right readout states the next objective: `GOAL / HUNT` while enemies remain,
then `GOAL / EXIT` when all are defeated. Reach the exit to finish; ordinary
doors still use B. This replaces the ambiguous EXIT LOCK/OPEN wording and does
not describe a nearby sliding door's position. DEAD and DONE take priority
and clear the GOAL caption.

Only the slim production profile uses this wording. Internal LOCK/OPEN table
keys stay intact to preserve the runtime packet ABI; compact and legacy
profiles retain their historical text.

The caption begins at HUD y=4 and main text at y=10, one pixel lower than
the first objective revision. A blank row separates the caption from the
upper bevel and from the main text. Main glyphs cross into the third tile
row, so preloaded vertical tile pairs preserve their bottom pixels and the
chassis rail. The existing packet carries only each pair's first ID.

## Resources and checks

HUD usage is 94 of 96 patterns, up 25 patterns (400 bytes) from the initial
24-pixel HUD. Bank 0 occupies $8200–$87DF within its existing reservation.
The HUD packet remains 16 bytes, with no new per-frame pattern uploads, OAM
objects or DMA blocks. Fixed-ROM free space is 1,776 bytes and the resident
reserve 3,123 bytes. Weapon/enemy/fixture source artwork is unchanged.

The new oracle is `playtests/sable_objective_spaced_capture_pixels.json`. Checks exercise
all health digits, four portrait states, both maps, chassis rails, persistent
highlights, immutable packets, and the maximal 176-block publication. A/B
subroutine measurement and six frozen-world comparisons are provided by:

```sh
python tools/compare_hud.py \
  --baseline-rom .render-baselines/skull-hud-before/lupine3d.gb \
  --baseline-symbols .render-baselines/skull-hud-before/lupine3d.sym \
  --expected-publication-delta-cycles 108 \
  --output-dir build/hud-spacing/comparison
```

HUD preparation timing is unchanged. Publication adds 108 CPU T-cycles
(about 12.9 microseconds at double speed) for six bottom-row tilemap writes.
World and foreground RGB also match in all six frozen comparisons. Only the skull and objective pixels change; the helmet and panel layout stay
intact. Tests exercise the living-to-cleared objective transition, terminal
priority and immutable publication on both maps.
The four existing portrait animation slots and clocks are unchanged.

The previous whole-HUD revision also had identical mean and p95 frame times in
four ten-second live controller comparisons. Those results remain bound to that
previous ROM in `milestones/steel-hud/`; they are not new measurements of this
icon/text revision. The original rendering B/P budget and owner-approved
visual/performance tradeoff remain unchanged.

Current checks and comparison evidence are retained under
`milestones/hud-spacing/`; full transient output is under `build/hud-spacing/`.
The previous steel and slim oracles remain intact. Qualification is emulator-only.
No release is published by this change.
