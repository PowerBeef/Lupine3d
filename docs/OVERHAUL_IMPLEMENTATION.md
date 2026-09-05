# v0.7.0-beta.1 — Living Renderer

This implements the software items deferred by the Renderer Foundation alpha. It is a playable beta, not an original-hardware-certified release. The prior alpha artifacts and historical geometry/RGB evidence remain intact.

## Delivered contracts

| Item | Implementation | Acceptance |
|---|---|---|
| Selective high-precision traversal | Cheap coarse crossing-order certificate; uncertain rays restart with Q14 camera-plane directions and 32-bit error | Exhaustive component-error bound, 64 severe historical rays executed in ROM, full 24,384-view host tail scan |
| Physical doors | Finite sliding segment at cell centre; aperture shared by wall rays, exact LOS, hitscan and radius collision | 1,600 ROM/host door probes plus collision/LOS aperture tests |
| Fixed simulation | ~59.73 Hz VBlank timestamp; movement and doors advance on queued ticks, AI every fourth tick | Same movement under different service batching; timestamp wrap and backlog tests |
| Resumable rendering | Cooperative yields at ray and tile-column boundaries; bank 2 live world and bank 1 immutable snapshot | Snapshot bytes unchanged while live state advances |
| Repeated input | 63 usable four-byte records containing a 16-bit timestamp, held state and rising edges | Repeated presses, 16-bit wrap, overflow preservation and long-render input tests |
| Entity rendering | Hardware 8×16 pairs, per-bit strip masks, double-buffered mask patterns | Exact masked tile bytes; hidden strips consume no OAM; total and scanline caps |
| LOD and multiple actors | 16×32, 16×16 and 8×16 cels with hysteresis; four fixed Sentinel slots | Two-actor scene, nearest-first submission/hitscan and aggregate exit lock |
| Surface content | 1,024 independent oriented-face profile bytes; neutral structure, muted-green machinery, cyan/white doors | Compiler rejects door-colour misuse; ROM/host attribute packets agree |
| Coherent publication | Dynamic BG patterns, masked OBJ patterns, attributes, tile map, HUD and OAM form one publication | Forced staged transfers and independent SameBoy write checks |
| Reprojection experiment | Published world OAM X shifts with SCX; foreground UI stays fixed | Clamp, immutable base packet, guard attributes and reset tests; default off |
| Independent execution | Reproducible pinned SameBoy and mGBA adapters plus CI configuration | Exact candidate boots, moves, turns and opens a door in all three model/core lanes |

## Geometry improvement and its limits

The full retained renderer-benchmark corpus contains 24,384 views and 3,901,440 physical columns. Maximum wall-top error is **4.4896 pixels**, with **zero columns at or above eight pixels**. Historical maximum was 41 pixels; its evidence was not overwritten. All 64 retained severe ray probes now choose the floating oracle's hit cell/axis in actual generated code.

This is not perfect continuous geometry: the new scan still has 67 wrong-segment columns and three wrong-material columns. Q14 governs crossing order. Projection intentionally retains the integer Q5 LUT and coarse component/correction domain; interpolated depths remain conservative. Near clipping, quantization and reconstruction still contribute error.

The certificate relies on a generated-direction bound below one coarse component unit (measured maximum 0.851318359375). A coarse order is accepted only when its signed-error magnitude exceeds the sum of the next X/Y boundary distances. Axis-degenerate and ambiguous cases restart. Generic AI LOS uses the actual player-to-enemy vector in the same wide traversal.

## Simulation and capacity semantics

The ISR only samples input and queues packets. A yield saves render HRAM, switches to the live bank, consumes at most four packets, restores bank 1 and resumes. Debt is retained. A 16-bit timestamp wraps safely; movement depends on queued ticks, not render duration.

The queue has 63 usable records (~1.05 seconds). Full-queue handling preserves pending records and OR-latches a missed edge, while a saturating diagnostic records overflow. It cannot preserve arbitrarily many repeated presses after overflow; normal verified routes have no overflow. Muzzle feedback is acknowledged when snapshotted so it does not expire invisibly during a slow render.

Movement uses four Q8 units/tick; turn uses one angle unit/tick. Doors advance eight fraction units/tick and fully open in 32 ticks. Radius collision can remain blocked when a thin ray already fits through an aperture; this is intentional shared geometry with different query thickness.

## Entity and colour semantics

Up to four Sentinel slots reuse one AI/combat implementation. The default map still has one enemy. A two-enemy acceptance scene generates eight world objects, 17 visible objects total and six maximum Y-selected objects on a scanline. The exit unlocks only after every active actor dies.

World admission permits at most 16 OAM entries and four world objects per scanline, leaving room for the ten-entry foreground reservation. Hardware uses two aligned patterns per 8×16 object. Masks come from per-pixel X comparisons against two-pixel wall-depth samples; this remains conservative occlusion, not exact per-pixel depth.

Per-face profiles are independent of physical segment IDs. CGB palettes are tile-granular: a mixed-profile tile deliberately uses neutral colours rather than repainting its neighbour. The wall grammar remains restrained; no broad new texture system or floor/ceiling casting was added.

## Exactness and visual review

The new precision, sliding geometry and palette semantics intentionally change rendered images. Old RGB fixtures are historical, not secretly updated. The nine new captures were visually inspected before accepting `playtests/v070_beta_capture_pixels.json`.

A separate frozen-world folded/unfolded A/B yields identical RGB in all nine views. Fixed simulation is suspended for this representation-only comparison so differences in execution time cannot change the snapshot being compared.

The combat scenario explicitly injects diagnostic camera poses, including aiming at the live Sentinel and relocating to its actual drop. It does not inject health, death or completion. The separate 233-update controller route injects no game RAM at all.

## Reproduce

```sh
make test
make playtest playtest-world
make playthrough variants
make research-tail
make sameboy SAMEBOY_DIR=/absolute/path/to/SameBoy
make mgba MGBA_DIR=/absolute/path/to/mgba
python3 tools/release_check.py
```

Default: Q14 on, fixed simulation on, folding on, 121-pattern atlas, reprojection off. Experimental flags must match between a ROM and its validating host process. Variant tools build in memory and do not overwrite the default ROM.

## Explicitly still outside acceptance

- Original CGB, original LCD and MBC5 flash-cartridge validation of this exact SHA.
- Nintendo boot-ROM validation; SameBoy uses a synthetic bootstrap and mGBA uses built-in skip-BIOS.
- Enabling asynchronous reprojection by default: current guards extend edge tiles, not newly rendered geometry; the HUD uses a STAT split, not the Window layer.
- Arbitrary-scale sprites, a general ECS, additional enemy types, streamed multi-level content, sector heights, textured floors/ceilings and saving.
- A blanket performance gain. Combat diagnostic worst-case visual rate is 4.26 Hz despite fixed-rate input/simulation. Profiling real gameplay is the next performance target.

See [test report](TEST_REPORT.md) for candidate-bound evidence.
