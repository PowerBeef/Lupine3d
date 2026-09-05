# v0.7.0-beta.5 — Streaming columns and prepared rays

All four implementation steps are complete. The 53-scene frozen comparison preserves pair and physical descriptors, depths, segments, surface profiles, background patterns/maps/attributes, entity masks/OAM, HUD and RGB. Mean complete-presentation cost falls **9.66%**, including publication waits. The nine reviewed Sable RGB fixtures remain unchanged.

## 1. Stream the physical-column expansion

`columns.py` walks the 80 top samples in order using HL for reads, DE for writes and B/C for neighbouring heights. It emits each left/right physical top with the existing rounding, byte arithmetic and endpoint clamping. Five other descriptor arrays use an unrolled sequential duplication kernel. The selective exact physical-ray recast pass still follows expansion.

This removes repeated index/address reconstruction without changing the interpolation contract. Tests execute the kernel against 32 synthetic arrays, including unsigned-byte overflow cases, endpoint boundaries and a destination guard.

## 2. Stream surface events and door runs

The event scan retains the previous segment, face key and along-face cell in registers. Every branch refreshes that state. Segment changes still receive narrow physical creases; material and cell changes keep their existing count-only semantics. Array addressing explicitly handles page crossings.

Door runs are scanned sequentially and receive the existing frame/spine stencil after physical creases. First/last-column runs, LOD thresholds, adjacent door keys and precedence are unchanged. Two hundred differential cases exercise those boundaries. Saving the scan registers around a door stencil temporarily uses four additional stack bytes inside the existing 512-byte reserve.

## 3. Prepare ray records in ROM

Each camera angle owns a 4 KiB page containing 256 aligned 16-byte records: 80 adaptive rays, 160 physical rays, one centre hitscan record and 15 unused records. Four camera pages fit one MBC5 bank. A record contains coarse absolute components and steps, coarse angle, cosine correction, exact X/Y projection bank/address pairs and absolute Q14 components.

Loading the record replaces repeated camera arithmetic and projection-address construction. Eager Q14 components also avoid a second banked direction fetch when a ray encounters a door or needs precision continuation. Axis-degenerate and origin-door restart paths retain the original signed Q14 table. Generic vector LOS and raw diagnostic probes retain their arithmetic path.

An address/vector-only prototype saved too little casting time to justify its table. Adding Q14 components to the same record made better use of the banked read without increasing the allocation. This is an exact ROM-for-CPU trade, with no projection approximation.

| Resource | Allocation |
|---|---:|
| Prepared records | 1,048,576 bytes, banks 173–236 |
| Remaining cartridge capacity | 311,296 bytes, banks 237–255 |
| Projection-pointer scratch | 4 banked WRAM bytes, $D8F3–$D8F6 |
| Additional HRAM / VRAM | 0 / 0 |
| Resident reserve | 3,123 bytes below $8000 |

All 61,696 valid records are checked against the original camera/projection math. Actual SM83 loads cross every camera bank boundary and restore ROM bank 1. `LUPINE3D_PREPARED_RAYS=0` retains a smaller arithmetic build; its nine reviewed captures must match the default build.

## 4. Measure complete frames and live motion

The archived beta.4 ROM is the baseline:
`8813ab38201f937c18c9b15e26d58c94fe2e873bbaf900a358fcf933fef34e0b`.

Candidate:
`8f0425f07220d7649ff419c9c3fb0a212c4a234b40463ab431c1f97e1b7b3cd3`.

Three isolated scene checkpoints measured expansion, then events, then prepared rays. Their source-ROM/output hashes and complete measurements are preserved in [the evidence file](../research/results/columns_beta5.json). Expansion fell from about 89,000 to 30,492 cycles; events from 86,124–89,440 to 40,980–43,220. Adding prepared rays then saved 3,600–29,400 casting cycles across those scenes.

The final comparison covers all 53 frozen scenes:

| CPU cycles | Baseline mean | Candidate mean | Reduction |
|---|---:|---:|---:|
| Complete presentation, including waits | 1,234,852 | 1,115,603 | 9.66% |
| Entire wall-casting pipeline | 833,776 | 707,708 | 15.12% |
| Column expansion only | 89,497 | 30,726 | 65.67% |
| Surface/door events only | 87,854 | 42,438 | 51.69% |

Expansion and events are parts of the casting pipeline; these savings must not be added together. Interrupt timing and publication waits explain why kernel savings do not translate directly into frame-rate gains. The comparison normalizes only OBJ bank bit 3 in disabled Y=0 OAM slots; visible objects remain exact.

`benchmark_motion.py` then runs held input against the actual ROM for 144 LCD-frame-counter increments per case (about 2.394 seconds). It performs a diagnostic warmup, then makes zero game-RAM writes during each timed trial. Every completed presentation validates the host descriptors and published packets, exact cache invalidation, page ownership, OAM limits and DMA safety.

| Live trial | Baseline full geometry updates/s | Candidate full geometry updates/s |
|---|---:|---:|
| Walking | 6.26 | 6.68 |
| Turning | 7.93 | 9.19 |
| Walking and turning | 7.52 | 8.77 |

The door trial injects one LCD-frame B tap, observes multiple opening fractions and reaches fully open. Both builds complete five full geometry updates; mean cost of those updates falls from 1,349,229 to 1,180,695 cycles. The remaining stationary time uses wall reuse, so its 44.27 total presentations/s is **not** a geometry-rendering rate. All four trials have zero queue overflow and unsafe GDMA starts.

These are short deterministic project-emulator trials. Faster rendering samples different live snapshots, so live frames are validated against their own world state rather than required to match the slower build's poses. The separate frozen comparison supplies the exact-output proof. No guaranteed gameplay FPS or original-LCD measurement is claimed.

## Reproduce

```sh
make test
make playtest playtest-world playtest-art playthrough variants
make wall-reuse motion
python3 tools/benchmark_runtime.py \
  --baseline-rom /path/to/beta4.gb \
  --baseline-symbols /path/to/beta4.sym \
  --output build/columns_comparison.json
python3 tools/benchmark_motion.py \
  --baseline-rom /path/to/beta4.gb \
  --baseline-symbols /path/to/beta4.sym
```

CI runs the current motion and flag-off gates without depending on an old artifact. The original baseline and checkpoint data remain historical evidence. SameBoy CGB-0/CGB-E and mGBA pass the exact candidate; original CGB, Nintendo boot ROM and flash-cartridge acceptance remain pending.
