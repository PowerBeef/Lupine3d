# Rendering implementation ledger

> Retained beta.6 rendering milestone evidence. Its performance baselines remain immutable. The v0.8 art/viewport default and explicitly accepted cost are documented in [the current test report](TEST_REPORT.md).

The implementation follows the supplied review of commit
`466bd09786d076c1e4b528f32647aa2885d201ff`. Baseline ROM SHA-256:
`8f0425f07220d7649ff419c9c3fb0a212c4a234b40463ab431c1f97e1b7b3cd3`.
Local immutable comparison artifacts live in `.render-baselines/`, outside
`make clean`. Generated reports belong to their recorded ROM/configuration;
they are never evidence for a different candidate.

## Acceptance contracts

Exact changes preserve same-snapshot descriptors, dynamic allocation order,
published packets and RGB, with the historical nine-image oracle and v1 ROM
hash retained. Controller-driven measurements are a separate lane. CPU
T-cycles are canonical: 8,388,608 cycles/s at CGB double speed, 140,448 CPU
cycles per 70,224-dot LCD interval (59.7275 Hz). Instrumentation is host-side.

The target is 10 sustained full geometry updates/s. For each affected
scenario, quality cost must satisfy `Q <= (B + P) / 2`, independently for mean
and p95 full-frame time. `B` is the baseline and `P` the accepted exact-output
milestone. Cached and foreground presentations do not count as geometry.
Keep 3,000 resident bytes free, fixed bank-switching code below `$4000`, and
existing publication limits. Reprojection remains disabled by default.

## Stage status

All specified kernels exist as separate build paths. The accepted exact-output
combination is now the production default: compact strips, invariant camera
setup, narrow yield contexts and exact attribute padding. Other candidates
remain available as disabled experiments with explicit measured outcomes.

| Step | Implementation and outcome |
| --- | --- |
| 0 | Immutable baseline archive; reconciled host observation; versioned LCD replays and sustained scenarios. Baseline and performance controller routes complete and restart without game-RAM writes. |
| 1 | Nine stored folded states; full 19-state banked diagnostic. 282 selectors, 6,768 patterns, complete tables and 53 frozen scenes pass. Exactly 3,840 table bytes removed. |
| 2 | 51 complete frozen worlds, rational plane visibility oracle and explicit legacy characterizations. All 51 images agree with SameBoy CGB-0/E and mGBA for both performance and quality paths. |
| 3 | Incremental certificate, invariant camera setup, persistent complete-key cache, alternate cache hash, narrow yields and exact padding initialization implemented. Camera/narrow-yield/padding combination is useful; certificate and cache candidates remain disabled after slower measurements. |
| 4 | Four-anchor packets, bounded iterative splitting, scalar finite-door fallback and optional endpoint-bound reuse implemented. 53 frozen scenes and emitted certificate probes pass. Both candidates are slower and remain disabled. |
| 5 | Physical-depth provenance, coverage, same-key refinement promotion and Q8.8/Q14 actor transforms implemented. Visibility witness corrected; forced-full comparisons pass. Sustained depth candidate exceeds the quality budget; disabled. |
| 6 | Actual UI scanline occupancy, whole-actor transactions, smaller-LOD fallback and physical door identity implemented. Capacity/rollback/hidden-X tests pass. The complete quality combination exceeds budget and remains disabled. |
| 7 | Direct, paged256 and hybrid256 storage implemented. All 2,359,296 logical bytes and emitted page/bank boundaries pass. Both compressed modes are slower. The bounded near-field arithmetic improves its targeted projection error but greatly exceeds the timing budget. All remain disabled. |
| 8 | Bank-4 world/composite OAM, accepted-action queue, sequence/generation ownership and foreground-only publication implemented. Queue/wrap/reload/register/DMA tests and independent moving-fire checks pass. Latency/budget gate fails; disabled. |
| 9 | 137 regression tests, production/reference matrix, independent scenes, controller completion/restart and deterministic rebuild. Release packaging requires an extracted-source rebuild and full suite. Physical hardware is unavailable; releases use emulator qualification. |

The performance candidate is ROM
`48c80fcd588365a38eb08c7ce1cc4ce2439c432127e4f389651b8e0bdafe2e99`.
Its 60-second trials improve mean full-frame time by 3.7–7.5% across six
scenarios. Rates range from 6.8 to 9.7 full geometry updates/s, below the target.
Its 53-scene frozen mean improves by 1.19%. Resident free space is 5,939 bytes:
the 3,840-byte table saving is partly consumed by code and alignment, yielding
2,816 net linked bytes relative to the baseline. This does not expand fixed ROM.

The six primary sustained scenarios use 3,584 LCD intervals each, approximately
59.989 seconds. Values below are CPU T-cycles. The 68-cycle combined-motion p95
increase is within the same LCD presentation interval; it remains recorded.
The strict quality gate still uses the actual values without tolerance.

| Scenario | Baseline mean | Performance mean | Baseline p95 | Performance p95 | Full geometry/s |
|---|---:|---:|---:|---:|---:|
| Walking | 1,212,118 | 1,151,487 | 1,264,528 | 1,264,268 | 7.25 |
| Turning | 921,810 | 866,184 | 1,123,780 | 983,424 | 9.67 |
| Combined movement | 980,133 | 906,582 | 1,123,924 | 1,123,992 | 9.23 |
| Moving fire | 978,764 | 906,582 | 1,123,944 | 1,123,916 | 9.23 |
| Open door | 1,271,867 | 1,225,335 | 1,404,404 | 1,264,160 | 6.83 |
| Closed door | 1,035,856 | 963,202 | 1,124,580 | 1,124,568 | 8.68 |

The additional moving two-actor corner trial improves mean/p95 from
1,348,764 / 1,825,784 to 1,283,440 / 1,685,396 T-cycles (6.52 full updates/s).
Both candidates reach simultaneous actor admission in three frames; submitted
world OAM appears in 46 baseline and 47 production frames. This is intermittent
contention, not a claim that both actors fill the screen throughout the minute.
The stationary door-tap trial has five full geometry frames while the door
opens, followed by cached presentations; those cached frames do not inflate
geometry throughput. Its full-frame mean improves from 1,180,695 to 1,096,428.

Packet traversal is exact but its original/reused-bound variants increase
frozen full-frame time by 7.60%/6.89%. The persistent cache adds lookup overhead
and has insufficient useful hits in this corpus. Fully paged storage uses
945,920 bytes (3503 unique 256-byte payloads plus directory allocation), but
raises frozen full-frame time by 1.19%. These are measured failed experiments,
not assumed speedups from map-read or numerical compression counts.

Quality captures are versioned separately. The complete flat-wall witness
changes its actor mask from `CC` to `FF`; the Q8 transform reduces the focused
fractional-motion screen error by more than half. Slow-motion comparison GIFs
cover fractional actor movement, yaw wrap, near/LOD boundaries and door
apertures. These do not replace the historical nine-image production oracle.
No additional transition hysteresis was introduced without a demonstrated need.

Current quality rejection evidence is bound to these ROMs:

| Candidate | SHA-256 | Failed measurement |
|---|---|---|
| Physical depth + actor precision + scanline admission + door identity, on performance base | `ee21f7773819b4b9dc0590f188598d49e5c2d655ec7e2a1c56d9f804d9f20b4d` | Walking mean 1,860,172 / p95 1,966,788; limits 1,181,803 / 1,264,398 |
| Bounded near-field projection on performance base | `cd881c424883531e4bcdf393c70e87f1369b2d399d8811380f458d915cca87d6` | Walking mean 2,074,818 / p95 2,247,680; turning also fails |
| Foreground lane + admission on performance base | `431a8019dff18c08c61bf139fdd8c80123a49de96cfd2b618904db75998ff633` | Moving-fire mean 942,828 / p95 1,123,996; limits 942,673 / 1,123,930 |

These are explicit partial rejection gates, not complete quality qualifications.
The current foreground sample-to-visible p95 is 340,628 T-cycles (40.606 ms),
above two LCD intervals (280,896 T-cycles, 33.485 ms). Its independent moving-fire
route exercises foreground publications on all three cores with zero mixed
world OAM. Earlier experiment reports remain local historical evidence and are
not substituted for these current candidate hashes.

The foreground queue holds 15 pending ten-byte records. The producer writes
sequence, sampled tick, coherent accepted tick, scene generation and type
before exposing HEAD. VBlank consumes at most two events; world preparation
consumes four before waiting. Overflow preserves existing debt. Reload stops
the consumer before resetting ownership. A full commit updates the authoritative
world copy after the visible commit, with foreground DMA blocked until copying
finishes. The interrupt never writes mask patterns or changes world positions.
At maximal 32-pattern OBJ load the foreground configuration needs a third
VBlank before map/HUD/OAM publication; the total 176-block limit is unchanged.
Late foreground interrupt entry is deferred instead of borrowing a fresh
VBlank budget. A scanline estimate is not an original-hardware latency claim.

## Reproduction and evidence

```sh
make PYTHON=.venv/bin/python test
.venv/bin/python tools/quality_witnesses.py
LUPINE3D_COMPACT_STRIPS=1 .venv/bin/python tools/benchmark_runtime.py \
  --baseline-rom .render-baselines/466bd09786d076c1e4b528f32647aa2885d201ff/lupine3d.gb \
  --baseline-symbols .render-baselines/466bd09786d076c1e4b528f32647aa2885d201ff/lupine3d.sym
make PYTHON=.venv/bin/python sustained
```

All boolean flags below use the `LUPINE3D_` prefix and accept exactly `0` or `1`.
Import-time configuration requires a fresh process. The manifest records every
resolved flag, configuration identity, allocation and table format.

| Flag | Default | Constraint/outcome |
|---|---:|---|
| `COMPACT_STRIPS` | 1 | Requires folding; exact and accepted |
| `CAMERA_SETUP` | 1 | Requires prepared records; exact and accepted |
| `NARROW_YIELDS` | 1 | Excludes reprojection; exact and accepted |
| `ATTRIBUTE_PADDING` | 1 | Exact and accepted |
| `INCREMENTAL_CERTIFICATE` | 0 | Exact but slower |
| `DYNAMIC_TILE_CACHE` | 0 | Exact complete-key cache; slower |
| `CACHE_KEY_MIX` | 0 | Requires dynamic cache; insufficient benefit |
| `ANCHOR_PACKETS` | 0 | Requires Q14/prepared records; exact but slower |
| `PACKET_BOUNDS_REUSE` | 0 | Requires packets; exact but slower |
| `PHYSICAL_DEPTH` | 0 | Correct query provenance; exceeds quality budget |
| `ACTOR_PRECISION` | 0 | Q8.8 transform; quality combination exceeds budget |
| `SCANLINE_ADMISSION` | 0 | Atomic actor admission; quality combination disabled |
| `DOOR_IDENTITY` | 0 | Physical door-run boundaries; quality combination disabled |
| `NEAR_FIELD` | 0 | Requires Q14; targeted accuracy improves, timing fails |
| `FOREGROUND_PUBLICATION` | 0 | Requires fixed simulation/admission, excludes reprojection; timing/latency fail |

`LUPINE3D_PROJECTION_STORAGE` accepts `direct` (default), `paged256`, or
`hybrid256`. Compacted modes preserve logical bytes but add lookup cost.
Prepared projection metadata is versioned when direct pointers become logical
slice IDs. Directory records and payloads cannot cross their declared bank/page
boundaries; unrelated table banks retain their assignments.

Historical `FOLDED=0`, `PREPARED_RAYS=0`, and `REPROJECTION=1` commands disable
only incompatible implicit defaults. Explicit incompatible requests fail.
The unfolded oracle stores full strips in bank 237. Every combination must
still pass the resident and fixed-code limits enforced by the allocation ledger.

Motion report v2 preserves the short default duration and existing CLI output
argument, and adds duration, scenario, external candidate/baseline and output
directory arguments. Its combined-motion tape alternates forward/backward
every 48 LCD intervals to avoid a stationary wall-collision benchmark. Tape
hashes bind comparisons. Every five-second moving/turning window is checked.
Muzzle timings are explicitly scanline estimates, not pixel-transition or
original-LCD measurements. The exclusive cycle categories reconcile exactly;
nested casting costs are a separate view. The sustained CI lane is manual and
has its own 180-minute timeout.

`tools/rendering_qualification.py` checks and collects the production sustained,
frozen, independent and controller-restart evidence, the explicit reference
matrix and current rejected experiments into `build/rendering_qualification/`.
It rebuilds the ROM twice, binds reports and controller tapes by SHA-256, and
retains the actual test log. The source packager includes this evidence and
checks its hashes before clean-room rebuilding and testing. Its final
`clean_room_verification.json` is separate from the measurement manifest.
The accepted `P` archive lives under `.render-baselines/performance-<ROM SHA>/`.

The independent image lane covers all 51 frozen scenes in the performance,
quality and near-field configurations on SameBoy CGB-0, SameBoy CGB-E and mGBA.
It demonstrates agreement with the project harness; the rational geometric
oracle supplies expected visibility independently. Diagnostic frozen captures,
controller-driven traces and original-hardware evidence remain distinct.

Timing/selection rules follow [Pan Docs rendering timing](https://github.com/gbdev/pandocs/blob/master/src/Rendering.md),
[OAM selection](https://github.com/gbdev/pandocs/blob/master/src/OAM.md), and
[CGB DMA](https://github.com/gbdev/pandocs/blob/master/src/CGB_Registers.md).
LCD timing does not double with CPU speed; DMA stalls the CPU. The owner has no
physical CGB or MBC5 flash cartridge. Hardware and original boot-ROM qualification
remain untested and do not block emulator-qualified releases. Development stays
directly on `main`.
