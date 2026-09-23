# Lupine 3D v0.8 performance audit

This audit measures where a full geometry update actually spends its cycles in the
shipped v0.8 ROM, and ranks the remaining optimization opportunities by measured
value. It is an engineering assessment, not a release record; the qualification
evidence for v0.8 itself remains [its test report](archive/TEST_REPORT_V08.md).

The target (`docs/archive/RENDERING_IMPLEMENTATION.md`) is ten sustained full geometry
updates per second. v0.8 reaches 5.5–7.9/s and the gate `Q <= (B + P) / 2` fails
in all eight sustained scenarios by 139k–351k T-cycles. That is an owner-accepted
visual tradeoff, recorded and unchanged. This document asks what it would take to
close the remaining distance.

All figures are CPU T-cycles at 8,388,608 Hz (CGB double speed). One LCD interval
is 140,448 CPU T-cycles.

## 1. The governing constraint: LCD-interval quantization

`upload_hidden_page` publishes by busy-polling `LY` (`tools/build_rom_v1.py`,
`wait_vblank`). A full update therefore ends on an LCD-interval boundary, and the
observed frame times are near-exact multiples of 140,448: walking p50 1,404,456
(10 intervals), turning p50 983,172 (7), and the common 1,123,584 (8) and
1,264,032 (9).

**A saving smaller than one LCD interval buys no frame rate.** This is not a
theoretical caveat. It was measured directly during this audit: removing 9,026
T-cycles per update from `render_view` (§6.1) left the frame mean unchanged at
878,889 on the coherence tour, because `upload_hidden_page` absorbed 8,849 of
them as additional `LY` spinning.

Every proposal below is therefore sized against ~140,448, and the highest-value
item is the one that removes idle spinning rather than work.

## 2. Measured cost model

Shipped v0.8 ROM `a5f3d54eb7d9be446d2d6ca36c010e9be264792c14c73f9691d6027871057ccb`,
walking scenario, 60 s, 373 full updates
(`milestones/v0.8/qualification/evidence/sustained-motion.json.gz`):

| Bucket | Share of all CPU | Per full update |
|---|---:|---:|
| `engine` | 74.4 % | 1,003,270 |
| **`publication_waits`** | **16.0 %** | **215,656** |
| `simulation_service` | 8.7 % | 116,999 |
| `interrupts` | 0.6 % | 8,607 |
| `dma` (all GDMA) | **0.3 %** | 4,600 |

Inside `engine`:

| Phase | Per full update | Share of frame |
|---|---:|---:|
| `cast_all` | 618,324 | 45.9 % |
| ├ `cast_one_v2` | 447,127 | 33.2 % |
| ├ `build_pixel_descriptors` | 123,691 | 9.2 % |
| └ `decorate_pixel_styles` | 41,086 | 3.0 % |
| everything else in `engine` | ~385,000 | 28.6 % |

Per-update counters: 52.4 rays, **2.37 crossings/ray**, 3.45 cell reads/ray,
**949 ROM-bank writes**, 11.85 dynamic tile compositions, 7.6 physical recasts,
6.6 Q14 continuations.

Four of these redirect effort away from the intuitive answers:

1. **The 176-block GDMA ceiling is not a performance constraint.** All GDMA is
   0.3 % of CPU. It is a hardware-safety contract, and holding it is what forces
   192 bytes of 6×-slower CPU copying into the VBlank window.
2. **Crossings per ray are only 2.37**, so the DDA loop is not where a ray's time
   goes. Roughly half of a ~6,500 T ray is fixed prologue and epilogue.
3. **Only ~12 dynamic tiles are composed per update**, so the `or_16` microstrip
   compositor is about 4 % of the frame, not the bottleneck its inner loop
   suggests.
4. **The wall cache is bimodal**: a 0.2–1.2 % hit rate while the camera moves and
   99.9 % while it is still. Its per-frame key work is paid almost entirely on
   frames that will miss.

## 3. Publication spends a whole LCD interval idle

> **Outcome (v0.10).** The dead interval this section describes is gone,
> but not by the interrupt-driven route prototyped in §3.1: the hidden
> patterns and the hidden map now stream by HBlank DMA during composition
> and the tail is one VBlank, which keeps the verification vantage point and
> every packet byte. See [streamed publication](STREAMED_PUBLICATION.md).
> The alignment wait that §3.1 would also remove is still there, and so is
> that decision.

`emitter.py`, `upload_hidden_page`. On slim, publication calls `wait_vblank` two
or three times: once to align (legitimate), once more when
`DYN_COUNT + MASK_TILE_COUNT >= 49`, and once unconditionally before the
attribute/map/HUD/OAM tail. Between the pattern stage and that final wait the
engine performs roughly 5,000 cycles of work — 96 CPU map bytes, a mask GDMA and
a 32-byte attribute prefix — and then spins for the remaining ~135,000 cycles of
the interval.

Measured `publication_waits` is 215,656 per update, about 1.54 intervals. Roughly
half an interval is unavoidable alignment; **a full interval is dead time**.

`docs/archive/PERFORMANCE_V4.md` rejected interrupt-driven publication in v0.4, correctly:
the packet then fit in a single VBlank entered at LCD line 129, so an ISR could
not publish any earlier. The slim viewport made publication a two-or-three stage
operation, and stages 2 and 3 now sit behind whole-interval stalls that did not
exist when that measurement was taken. The rejection is stale for the current
packet shape.

**The opportunity.** `cast_all` writes only the `RAY_*`/`PIXEL_*` descriptor
arrays. It does not touch `VIEW_MAP`, `VIEW_ATTRIBUTES`, `DYNAMIC_TILES`,
`MASK_TILES`, `HUD_PACKET` or `OAM_SHADOW`. The staged packet is therefore stable
throughout the next frame's casting, and the remaining publication stages can be
drained during it instead of in a spin loop. No second staging buffer is needed,
which was v0.4's other objection.

### 3.1 Prototype result: the largest available speedup, and what it costs

This audit built the overlap and measured it. `upload_hidden_page` was split so the
pattern stage hands the packet to the VBlank handler and returns; the handler
commits the tail under a forced `SVBK=1` with `VBK` restored; `update_muzzle_oam`
moved ahead of the first wait so `FLASH` is consumed before the next snapshot; and
a drain barrier sat before `render_view`/`render_entities` and before the cached
publication path.

On the nine-capture coherence tour, against the same build with the flag off:

| | Default | Staged publication | Delta |
|---|---:|---:|---:|
| Mean cycles/update | 878,889 | **623,056** | **−255,833 (−29.1 %)** |
| LCD intervals/update | 6.258 | **4.436** | −1.82 |
| Max cycles/update | 1,268,860 | 1,268,388 | −472 |
| Frozen oracle captures matched | 9 / 9 | **5 / 9** | — |

It is the largest single speedup found anywhere in this audit, and **it is not
output-exact**. Four captures differ — `02_airlock_approach`, `04_corridor_turn`,
`07_combat_partition` and `09_exit_approach` — because deferring the commit adds a
one-frame publication lag: the epoch that is visible at a given presentation count
is one frame behind the pose the scenario injected.

It also moves the vantage point the project verifies from. `validate_frame` builds
its host reference model from the **bank-1 snapshot pose and map**, then compares
the descriptor arrays and VRAM against it. Once publication is deferred past
`begin_frame_snapshot`, that snapshot describes frame N+1 while VRAM still holds
frame N, and fourteen same-snapshot checks fail together — `pair_descriptors_exact`,
`pixel_descriptors_exact`, `view_map_exact`, `published_map_exact` and the rest.
Narrowing the barrier does not help: any overlap window that does not cross
`begin_frame_snapshot` is empty, because the snapshot is the first thing the next
frame does.

So the choice is explicit rather than technical. Roughly 29 % on this route is
available in exchange for one frame of publication latency, a new versioned pixel
oracle, and either a second published-frame identity for the validator to observe
or a change to where it observes. That is an owner decision of the same kind as the
Sable art tradeoff, and the prototype was reverted rather than shipped.

Three constraints make the overlap correct rather than merely faster, and they hold
for any future attempt:

* `update_muzzle_oam` reads and decrements `FLASH`, which lies inside
  `WORLD_COPY_RANGES`. It must run before the next `begin_frame_snapshot`
  overwrites bank 1. `prepare_hud_tiles` has the same dependency and already runs
  in the pre-VBlank prologue.
* The publication tail reads **banked** WRAM — `CURRENT_PAGE` (`$D148`),
  `HUD_PACKET` (`$D3D8`) and `VIEW_ATTRIBUTES` (`$DC00`) — so anything draining
  it asynchronously must force `SVBK=1` and restore the interrupted bank. A
  simulation yield can be in progress with `SVBK=2`.
* A cache-hit frame (`upload_entities_hud`) publishes OAM and HUD on its own and
  must not overtake a packet that is still draining.

This is a change to the publication contract, so it would also require both pinned
cores and `tools/independent_witnesses.py`, not just the host harness.

## 4. The per-ray prologue, not the traversal

At ~6,500 T per ray with 2.37 crossings, the fixed cost dominates:

| Segment | T/ray | Note |
|---|---:|---|
| `load_ray_setup_prepared` | 524 | 15 scattered stores, 8 of them to WRAM |
| next-X/next-Y boundary selection | ~280 | 8 HRAM load/store pairs |
| initial error, 2 × `mul_u8` | 416 | 4 ROM-bank writes |
| `project_hit` + `lookup_segment_id` | ~1,010 | 4 more ROM-bank writes |
| `store_cast_result` | 324 | 7 × `ld hl,nn; add hl,de; ld a,(nn); ld (hl),a` |
| `PLAYER_XH/YH → DDA_MAP_X/Y` | 56 | frame-invariant |

Exact opportunities:

1. **Commute the `mul_u8` operands.** `mul_u8` derives its ROM bank from `C>>5`
   and its 512-byte row from `C&31`. The DDA error setup passes `B = next*`,
   `C = abs*`, but `next*` takes only four values in a frame
   (`FRAME_{X,Y}_{POS,NEG}`). Swapping the operands makes the bank and row base
   frame-invariant, so `prepare_frame_boundaries` can precompute all four.
   Estimated ~190 T/ray, ~10,000/update.
2. **Defer the bank restores.** 949 bank writes per update cost 15,184 T-cycles.
   `mul_u8` restores bank 1 on every call; `project_hit` restores it and
   `lookup_segment_id` immediately switches away again. Roughly a third of the
   traffic is redundant round trips.
3. **Interleave the seven ray descriptor arrays.** They sit `0x50` apart in a
   fixed order, so one `HL` walk replaces seven address computations in
   `store_cast_result`, and removes the fourteen `ADAPTIVE_INDEX` reloads per
   interpolated midpoint in `adaptive_fill_loop`.
4. **Hoist the frame-invariant map initialisation** out of `dda_setup`.

## 5. The DDA loop body

Roughly 810 T per crossing: a `call q14_crossing_uncertain` (24) plus certificate
body (288), axis selection (~92), step prologue (132), `dda_post_step` and
`dda_read_cell` (196) and the tail (96).

1. `DDA_DIST` is written on **every** step but read only by `project_hit` and the
   door path. Confining the 4-byte copy to cells with nonzero material saves
   ~48 T per non-terminal step. Note that `door_ray_hit` overwrites `DDA_DIST`
   with the door plane distance, so the copy must stay ahead of that call.
2. Inlining `dda_post_step` and `dda_read_cell` removes ~48 T/step of call
   overhead for ~120 ROM bytes.
3. `dda_read_cell` rebuilds `swap(DDA_MAP_Y)` on every step although the row base
   changes only on Y steps.
4. **Do not enable `INCREMENTAL_CERTIFICATE`.** It is recorded as slower, and the
   code shows why: ~152 T/ray of setup to save 48 T/step, breaking even at ~3.2
   loop iterations against a shipped ~3.37. It is marginal rather than wrong, and
   would win only at high crossing counts such as `two_actor_corner` (10.22/ray).
5. A **quadrant-specialised, register-resident loop** — four copies selected once
   per ray on the `stepX/stepY` signs, with the map pointer in `HL`, the error in
   `DE` and `absX/absY` in `B/C` — is the largest single engine win, estimated
   ~450 T/step (~80,000/update) for ~600–800 ROM bytes.

## 6. Composition and descriptors

1. **`render_write_tile` rebuilt the folded mirror row every row** —
   `(VIEW_ROWS-1-TILE_ROW)*32 + column_base` via five `add hl,hl`. It is a
   pointer walking backwards by 32 while `MAP_PTR` walks forwards. **Implemented
   in this audit**: measured −9,026 T/update in `render_view` on the coherence
   tour and −4,285 on the living-world route, nine-image oracle exact. `TILE_ROW`
   became dead and was removed from the HRAM ABI.

   Its effect on the 60-second sustained lane is the clearest illustration of §1:

   | Scenario | v0.8 mean | After | Delta | Hz |
   |---|---:|---:|---:|---|
   | walking | 1,348,012.75 | 1,348,012.82 | **+0.07 (0.000 %)** | 6.22 → 6.218 |
   | turning | 1,058,544.78 | 1,037,120.07 | **−21,424.71 (−2.02 %)** | 7.92 → 8.068 |

   Walking sits at 9.598 intervals and did not move at all — the whole saving
   became additional `LY` spinning. Turning sits at 7.537 and had enough frames
   near a boundary to convert part of it. Same change, same ROM, same saving;
   the difference is only where each scenario sits relative to 140,448.
2. `find_atlas_tile` re-tests the frame-constant `VRAM_PROFILE` four times per
   call; the bucket, count and entry pointers and the bank can be resolved once
   per frame.
3. The 8-byte signature compare runs at 56 T/byte; straight-line unrolling gives
   about 32.
4. `classify_row` runs eight times per column, re-deriving `VIEW_HEIGHT − MIN_TOP`
   and `− MAX_TOP` from column-constant inputs that `scan_column` already
   produced. The first and last dynamic folded rows can be computed once per
   column.
5. `build_pixel_descriptors` duplicates five 80-byte streams to 160 bytes
   (~17,960 T/update) and `event_boundary_loop` rebuilds a base address three to
   five times per column (~28,600 T/update). Both are address arithmetic over
   parallel arrays that could be walked with pointers.
6. A quad or octet microstrip fast path is **not** worth it at 11.85 compositions
   per update.

## 7. Snapshot and wall key

`begin_frame_snapshot` copies 457 bytes twice through `WORLD_COPY_BUFFER` — a flat
29,768 T every update. The double copy is unavoidable: `SVBK` exposes one banked
window and GDMA cannot target WRAM.

But 256 of those 457 bytes are `MAP`, and the live map has exactly two writers in
the whole engine: `load_level` and the one byte `update_animated_doors` clears when
a door finishes opening. A generation counter bumped at those two sites would skip
2 × 8,108 T of map copying per update, and would also replace the 256-byte map
range in the wall key with a one-byte comparison.

**It is not, however, a free exact win, and the audit initially misjudged this.**
A counter is exact with respect to *the engine's own writers* only.
`test_every_mutable_key_byte_invalidates_without_hash_collisions` flips every one
of the 290 key bytes, including all 256 map bytes, and requires each flip to
invalidate the cache; a counter cannot see a direct byte mutation. That test is the
byte-for-byte contract `AGENTS.md` says to preserve, and the same reasoning applies
to diagnostic map injection in the snapshot path. Either half is therefore a
contract change requiring acceptance, not an optimization — it belongs with §11,
not with the exact work.

`check_wall_reuse` costs 16,868 T on a hit (290 bytes at 56 T/byte, with no early
exit possible) and ~10,348 T on a miss, where it aborts at the first byte and then
re-captures all 290. The `wall_key_equal` loop is 56 T/byte largely because of an
in-loop `RET NZ`; a shared mismatch exit and a four-way unroll remove 12–16 T/byte
from the residual 34 bytes.

## 8. Entities

Every actor is projected **twice per frame** with identical inputs:
`project_actor_depths` calls `project_sentinel` for depth sorting, and
`render_sentinel_actor` calls it again to draw. `project_sentinel` is four signed
multiplies, two eight-iteration saturating divisions and up to two eight-sample
occlusion strip scans. Caching the depth pass is exact.

Also: `select_nearest_actor` is re-scanned from scratch on each draw pass;
`actor_load`/`actor_save` use `copy_bc(10)` at 444 T for 10 bytes because
`copy_bc`'s prologue is ~128 T (about 16 slot copies per frame); and
`clear_entity_oam_shadow` clears all 144 `WORLD_SCANLINES` counters when only the
lines reserved last frame need it.

## 9. ROM space is the binding constraint

Fixed code ends at `$3910`, leaving 1,776 bytes below `$4000`; resident data ends
at `$73CD` with 3,123 bytes free against a hard 3,000-byte reserve. That reserve
already blocked one accepted optimization (the fully unrolled door division).

With the default `PREPARED_RAYS=1`, the following sit in resident bank 1:

| Table | Bytes | Runtime status |
|---|---:|---|
| `align(RAY_DIRECTION_COUNT)` padding | ≤1,023 | pure padding |
| `ray_vectors_packed` | 4,096 | reachable only through `dda_raw_vector`, i.e. records ≥241 — disabled packet experiments and the raw-probe sentinel |
| `ray_offsets_q10`, `ray_corrections` | 240 | emitted only under `if not PREPARED_RAYS` — runtime-dead |
| `physical_offsets_q10`, `physical_corrections` | 480 | same — runtime-dead |

Moving these to the cold assets bank — the pattern `upload_profile_tiles` already
uses — frees roughly 4.8–5.8 KB without touching the reserve, which is what a
quadrant-specialised DDA loop or any wider strip table would need. Note that only
code that **writes** `$2000` must live below `$4000`; a register-resident DDA loop
can sit in bank 1 and still call `mul_u8` in bank 0.

## 10. Recorded inaccuracies

* The build manifest reports `maximum_publication_vblanks = 2` for the shipped
  slim configuration, but the slim path in `upload_hidden_page` can issue **three**
  `wait_vblank` calls. [The v0.8 test report](archive/TEST_REPORT_V08.md) and
  [the slim display contract](archive/SLIM_HUD.md) already say "two or three".
* [The hardware checklist](HARDWARE_TEST_CHECKLIST.md) Gate D described the legacy
  96/80 two-stage split rather than the shipped slim 96 / 32 / 48 split.

Both are corrected alongside this document.

## 11. Options that change output or contracts

These are owner decisions, recorded here without being implemented.

* **Convert the 192 hidden-map CPU bytes to GDMA.** They cost 5,016 T at 24 T/byte
  versus 768 T as 12 blocks, and every one of those cycles is spent inside the
  9,120 T VBlank window. They are CPU-copied purely to hold the qualified
  176-block ceiling. Raising it to 188 would return ~1,400 T to the final VBlank
  and ~2,830 T to the middle one — possibly enough to raise the 49-pattern
  threshold and drop the third stage on more frames.
* **HBlank DMA (mode 1) for the BG packet.** 144 HBlanks × 16 bytes exceeds a
  whole packet. `docs/archive/PERFORMANCE_V4.md` rejected it because it needed a second
  1,920-byte staging buffer — an objection §3 dissolves. It is the riskiest item
  here: CGB HDMA behaviour at double speed must be proved on both pinned cores.
* **Dirty-flag HUD and OAM publication.** `prepare_hud_tiles` and
  `update_hud_tiles` run unguarded on both paths, `animate_weapon` sets
  `OAM_DIRTY` every frame, and both live paths call the unguarded
  `publish_oam_packet` even though `publish_oam_if_budget` exists and is reachable
  only from tests. The saving is ~1,470 T, but it is in-VBlank time, which is what
  gates the stage count.
* **Rotational ray-result cache.** A cast result is a pure function of (direction
  index, player position, map), so during pure rotation any ray whose 10-bit
  direction index was cast last frame is exactly reusable. A 256-entry
  direct-mapped cache in a free WRAM bank costs ~60 T to probe versus ~6,500 to
  cast. It helps `turning`, not `walking`.
* **Fewer anchors with hierarchical subdivision.** The only lever large enough to
  reach 10 Hz on its own (52.4 → ~35 rays, ≈ −150,000/update), and the only one
  here that is **not output-exact**. It would need a new versioned pixel oracle
  and an explicit acceptance, exactly like the Sable art tradeoff.

## 12. Already settled — do not re-propose

Each of these was measured, not assumed
(`docs/archive/RENDERING_IMPLEMENTATION.md`, `docs/archive/PERFORMANCE_V4.md`):

* Dynamic tile cache, residual signature cache and tile dedup — insufficient hits, net slower; rejected three separate times.
* `ANCHOR_PACKETS` (+7.60 %) and `PACKET_BOUNDS_REUSE` (+6.89 %) — exact but slower.
* `PROJECTION_STORAGE=paged256/hybrid256` (+1.19 %) — compaction adds lookup cost.
* `INCREMENTAL_CERTIFICATE` — exact but slower at the shipped crossing count.
* `PHYSICAL_DEPTH`, `ACTOR_PRECISION`, `SCANLINE_ADMISSION`, `DOOR_IDENTITY`, `NEAR_FIELD` — correct, but over the quality budget; near-field is roughly +76 % mean.
* `FOREGROUND_PUBLICATION` — fails the timing gate by 155 cycles and the latency gate separately.
* A larger exact atlas — non-monotonic; 96 patterns is slower than 80.
* Blanket unrolling — already blocked once by the 3,000-byte resident reserve.

## 13. Estimated headroom

Output-exact, and therefore available without an acceptance decision:

| Item | Gain per update | Status |
|---|---:|---|
| §6.1 folded-mirror pointer | **9,026 measured** | **implemented** |
| §6.5 adaptive-fill single indexing | **11,643–19,810 measured** | **implemented** |
| §9 cold raw-ray tables | 0 cycles, **+5,328 resident bytes** | **implemented** |
| §5.5 quadrant-specialised DDA step | ~3,000–18,000 (revised down) | not implemented |
| §4.1–4.4 ray prologue | ~10,000 (revised down) | not implemented |
| §6.2–6.4 atlas and row-range | ~15,000 | not implemented |
| §8 entity projection dedup | ~2,500–10,000 (revised down) | not implemented |

**Measured outcome of the implemented set**, 60-second sustained lane against the
committed v0.8 evidence:

| Scenario | v0.8 | After | Delta | Hz | Intervals |
|---|---:|---:|---:|---|---:|
| walking | 1,348,013 | 1,304,537 | **−43,475 (−3.23 %)** | 6.22 → **6.418** | 9.598 → 9.288 |
| turning | 1,058,545 | 1,026,714 | **−31,831 (−3.01 %)** | 7.92 → **8.168** | 7.537 → 7.310 |

**Two of this document's earlier estimates were too optimistic and are corrected
above.** They measured the *cost of the current code* and assumed a fix removes
all of it. In practice:

* Hoisting the per-step `DDA_DIST` copy out of the loop has to re-commit the
  distance on the hit path, ahead of `door_ray_hit`'s override. At 3.37 steps per
  ray the added branch and copy claw back most of the 48 cycles per step — about
  2,600–4,700 per update, not 8,500.
* A quadrant-specialised loop only removes the `stepX`/`stepY` load-add-store
  (44 → 28 cycles). The step's real cost is in its callees — 312 cycles of
  crossing certificate and 220 of `dda_post_step`/`dda_read_cell` out of ~810.
  Reaching the original ~80,000 estimate needs those *inlined* and the error and
  map pointer register-resident, which is a full traversal rewrite against the
  documented Q14 crossing-order and tie contract — a much larger and riskier job
  than emitting four copies of the loop.

The remaining exact items are worth roughly 45,000 T-cycles together, not the
169,000 first estimated — individually all of them sit well below the 140,448
quantization step, so each converts only where a scenario already sits near a
boundary. The folded-mirror change showed this at its starkest: on its own it
moved walking by +0.07 cycles (nothing) and turning by −21,425 (−2.02 %), from
the same 9,026-cycle engine saving. Accumulating three changes finally moved
walking, from 9.598 intervals to 9.288.

Not output-exact, and therefore owner decisions:

| Item | Gain per update | Cost |
|---|---:|---|
| §3 staged publication | **−255,833 measured (−29.1 %)** | one frame of publication lag; 4/9 oracle captures; a new verification vantage point |
| §11 fewer anchors | ~150,000 est. | new pixel oracle |
| §7 map generation counter | ~24,000 est. | byte-for-byte wall-key validation and diagnostic map injection |
| §11 192 CPU bytes → GDMA | ~4,250, all in-VBlank | raises the qualified block ceiling to 188 |

**Nothing here reaches 10 Hz on exact output alone.** The exact work is worth about
13 %, and it only converts to frame rate once the stall goes. The stall is worth
29 % by itself and costs a frame of latency. That is the actual shape of the
decision, and it should be recorded rather than engineered around.

## 14. How to qualify any of this

Per change, measured on its own and reverted rather than stacked if it does not
pay (`docs/archive/RESEARCH_AND_DECISIONS.md`):

1. `make build && make test` — unit, allocation/lifetime and linker gates.
2. `tools/profile_rendering.py` on the coherence and living-world routes, to
   attribute the gain to the stage that changed. Expect the frame mean to move
   only when the saving crosses an LCD interval (§1).
3. Exactness: `make playtest playtest-world playtest-art` against the nine-image
   oracle `playtests/archive/oracles/sable_objective_spaced_capture_pixels.json`, plus
   `make variants`. Never adjust a fixture to make a change pass.
4. Budgets: `tools/release_check.py` — resident reserve, `$4000` ceiling,
   publication ceiling, dynamic pattern cap.
5. Sustained timing: `tools/sable_sustained.py` across all eight scenarios, then
   `tools/sable_quality_budget.py` against the unchanged `(B + P) / 2` limit.
6. Anything touching CPU, banks, interrupts, DMA or publication — including §3 —
   additionally requires both pinned cores (`make sameboy`, `make mgba`) and
   `tools/independent_witnesses.py`.

Hardware and boot-ROM testing remain unavailable and are reported false.
