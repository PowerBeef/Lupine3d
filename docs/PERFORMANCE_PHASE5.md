# Performance after textures (Phase 5)

Phase 5 set sustained targets for the textured slim ROM: walking at least
9.0 full geometry updates/s, turning 11.0 and the two-actor corner 7.5. This
page records where an update spends its cycles, what the first round of
exact savings bought, and why the rest needs a decision rather than trims.

Every number is emulated CPU T-cycles (8,388,608/s in double speed) from
`tools/sable_sustained.py`: eight 60-second LCD-indexed controller replays,
zero game-RAM writes after trial start, zero input-queue overflows and zero
unsafe GDMA starts in every trial. Host time never enters a result.

## Results

Full geometry updates per second (mean full update in thousands of T):

| Scenario | Textured before | Textured after | Default v0.11 | Default after |
| --- | ---: | ---: | ---: | ---: |
| walking | 6.47 (1296k) | **6.85** (1223k) | 7.77 | **8.08** (1037k) |
| turning | 8.40 (997k) | **9.08** (922k) | 10.25 | **10.84** (773k) |
| walking turning | 8.20 (1022k) | **8.85** (946k) | 9.80 | **10.25** (817k) |
| moving fire | 8.17 (1026k) | **8.85** (947k) | 9.79 | **10.24** (819k) |
| open door | 7.45 (1123k) | **7.83** (1070k) | 8.38 | **9.02** (929k) |
| closed door | 6.42 (1305k) | **6.83** (1226k) | 8.68 | **9.30** (899k) |
| two actor corner | 6.13 (1363k) | **6.65** (1261k) | 6.62 | **7.20** (1163k) |
| opening door | 0.08 (1180k) | 0.08 (1152k) | 0.10 | 0.10 (937k) |

"Textured before" is the textured ROM of commit 8c8e446 (candidate
`2eebf745…`); "Default v0.11" is `docs/TEST_REPORT.md` (ROM `76b6f974…`),
which predates the conditional map copy of the render snapshot as well. The
targets are **not met**: the textured ROM gained 5-9%, and walking needs
about 330k T less per update to reach 9.0/s.

## Where an update goes

A call-tree profile over the replays (inclusive T per update, textured
build, before this round):

| | walking | turning | two-actor corner |
| --- | ---: | ---: | ---: |
| update | 1,235k | 954k | 1,680k |
| ray casts (`cast_one_v2`) | 485k | 317k | 848k |
| of which door panels (`door_ray_hit`) | 182k | 25k | - |
| of which 16x16 products | 86k | 25k | 131k |
| texture kernel (`tex_*`, exclusive) | 234k | not separated | not separated |
| simulation ticks | 67k | 38k | 173k |
| waiting for VBlank (`wait_vblank`) | 37k | 46k | 41k |

Walking starts at the first sector's spawn facing the airlock door, so
almost every ray tests its panel; the two-actor corner is an open diagnostic
arena where every ray crosses about fourteen cells and two actors run line
of sight each tick.

## What this round changed (all exact)

* **Texture kernel.** Rows whose step is under one texel row cost 76 T
  instead of 104; one-face columns lost their per-tile bookkeeping; the run
  setup keeps its record in a register (`docs/TEXTURED_WALLS.md`, "Phase 5:
  exact savings").
* **16x16 multiply** (`q14_multiply_u16`): the four table products
  accumulate through the stack, each product byte stored once - roughly 870 T
  against 1,500 by instruction count.
* **Door panels** (`door_quotient`): the displacement matters only below
  4096, and `floor(p / d) >= 4096` exactly when `floor(p / 4096) >= d`, so
  the divide starts from the product's top and runs twelve steps instead of
  sixteen; `tests/test_runtime.py` pins it against Python.
* **The crossing certificate** is fused into the DDA loop: a certified
  crossing has a nonzero error whose sign is the step, so the axis choice
  does not reload what the certificate read, and the cell read is inline.

Every frame check, both pinned cores, the CPU conformance lane and every
golden passed; ten living-world captures moved to neighbouring accepted
ticks (a reticle halo, a door panel one step further, a Sentinel frame) and
were accepted with notes after review.

## Why the remainder is structural

Updates are quantized to LCD intervals (140,448 T): a full update ends in
VBlank, where the tail is published, so a saving shows only when it moves an
update across an interval boundary. The textured trials spent 53-78k T per
presentation in publication waits before this round. The candidates, none of which this round took:

1. **Overlap the next update with the wait.** Publish the tail from the
   VBlank interrupt and start casting the next frame while it waits. It
   removes the average half-interval loss but needs a second attribute and
   mask buffer, and the VBlank budget is already nearly spent
   (`AGENTS.md`, "Sound contracts"). It changes which simulation ticks are
   rendered, so it is an owner decision with a snapshot acceptance.
2. **Cheaper door panels.** A door test still costs several thousand T per
   ray that reaches a door cell (4.6k before this round); deciding hit or
   miss from bounds before the product would skip most of it, but must stay
   equal to `door_intersection`.
3. **Rotation reuse** for turning: 26-47 of 80 rays keep their coarse
   direction after a turn step, but the Q14 order depends on the continuous
   angle, so exact reuse needs a margin certificate per ray.
4. **Output-changing options** (fewer anchors, coarser texture columns)
   need an owner decision and snapshot acceptance, as the plan says.

The quality-budget gate (`tools/sable_quality_budget.py`) is unchanged and
still records its original failure; its B/P inputs were measured on the old
first sector, so it is not a like-for-like comparison.
