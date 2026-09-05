# v0.8 qualification report

This report describes the shipped **160×120 / 24-pixel steel HUD / animated Sable**
configuration. Qualification is emulator-only. The owner has no physical CGB or
flash cartridge; physical hardware and original Nintendo boot-ROM testing remain
false. The previous release is retained in [the beta.6 report](TEST_REPORT_BETA6.md).

**ROM SHA-256:**
`a5f3d54eb7d9be446d2d6ca36c010e9be264792c14c73f9691d6027871057ccb`

[Machine-readable qualification](../milestones/v0.8/qualification/report.json)
binds the manifest, executed test log, sustained samples, budget decision,
controller replay and independent-core results to this ROM. The release archive
also carries fresh short-route/variant reports and separate clean-room evidence.

## Executed checks

| Lane | Result and scope |
| --- | --- |
| Regression suite | 140 tests; frozen v1 hash and explicit legacy regressions plus fresh-process default art/display validation |
| Current release checks | 86 checks pass; the discovered test inventory is not used as proof of test execution |
| Coherence/world/art routes | All pass; nine current RGB fixtures match, with earlier oracles retained |
| Exact wall reuse | 53 frozen comparisons, timed feedback, disabled-path equality |
| Variants | Folded/unfolded, prepared-disabled, reuse-disabled, two actors and reprojection diagnostics |
| Controller completion/restart | 1,938 LCD intervals; no game-RAM injection; completion, pickup and restart verified |
| Native art and emitted animation | 18 groups: 36 enemy cels, weapon phases, rapid restarts, clock wrap, masks/admission, HUD states and raster/publication boundaries |
| Display | Seven diagnostic poses with independent Q5 geometry; legacy ROM remains byte-exact |
| Independent core scenes | 87 frozen scenes match the harness in all three core/model lanes |
| Sustained controller motion | Eight approximately 60-second trials; reconciled CPU time, no post-setup diagnostic writes, no queue overflow or unsafe GDMA starts |
| Static geometry/tail | 24,384 views / 3,901,440 physical-column samples, separately configured benchmark ROM |

Pinned cores: SameBoy `213a12ce93d66b105a113debd9396306066a7cfc`
(CGB-0 and CGB-E), mGBA `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6`.
These lanes use a minimal synthetic bootstrap, not a Nintendo boot ROM.
Diagnostic frozen scenes are distinct from the controller-only completion run.

## Sustained performance

CPU T-cycles are canonical: 8,388,608 cycles/s in double-speed mode. The table
converts those recorded cycles to milliseconds. Each trial observes 3,584 LCD
intervals (about 59.99 seconds); host execution time is irrelevant.

| Scenario | Full geometry/s | Full mean ms | Full p95 ms | Full worst ms |
| --- | ---: | ---: | ---: | ---: |
| walking | 6.22 | 160.70 | 167.43 | 167.43 |
| turning | 7.92 | 126.19 | 150.69 | 151.27 |
| walking turning | 7.47 | 133.79 | 150.69 | 167.43 |
| opening door | 0.08 | 167.54 | 200.92 | 200.92 |
| moving fire | 7.45 | 134.09 | 150.70 | 167.44 |
| open door | 5.90 | 169.28 | 184.17 | 184.17 |
| closed door | 6.83 | 146.07 | 150.69 | 150.69 |
| two actor corner | 5.50 | 181.48 | 234.40 | 284.63 |

The opening-door trial intentionally becomes stationary after the door finishes;
its 0.08 full updates/s is wall-cache reuse, not moving-camera throughput. Active
scenarios deliver **5.50–7.92 full geometry updates/s**. Cached sprite/HUD
presentations are counted separately and do not inflate this rate. The ten-full-
updates/s target is unmet.

The original quality rule, `Q <= (B + P) / 2`, fails for this complete visual
upgrade. [The unchanged budget evaluation](../milestones/v0.8/qualification/evidence/quality-budget.json)
uses the immutable pre-viewport baseline/performance lanes and identical replay
identities. **The owner explicitly accepted the visual/performance tradeoff.**
This is an acceptance exception, not a passing mathematical result, and does not
relax memory, publication safety or unrelated experiment gates.

Raw sustained JSON is retained as deterministic gzip in the qualification
bundle; its uncompressed SHA matches the budget's input hash. It includes
exclusive timing categories, nested casting phases, frame tails, input/snapshot
age, diagnostic provenance and per-frame observations. Reproduce with
`tools/sable_sustained.py` and `tools/sable_quality_budget.py`.

## Visual and geometry scope

The 24-pixel HUD preserves the approved armoured portrait. The skull is enemies
remaining; GOAL/HUNT changes to GOAL/EXIT after combat, and terminal states show
DEAD/DONE. Caption/main text begin at HUD y=4/y=10, clear of the upper rail.
The final spacing change adds six map writes / 108 CPU T-cycles (12.9 µs) per
HUD publication and leaves world pixels unchanged in the frozen comparison.

Current oracle: `playtests/sable_objective_spaced_capture_pixels.json`.
[HUD state captures](images/sable_objective_spaced_states_4x.png) and
[current combat playback](images/v08_combat.gif) show emitted ROM output.
Combat previews include explicit diagnostic setup, then controller input; GIF
frame delays are quantized to 10 ms. The archive also contains inspection-cadence
and native-resolution previews. Generated masters are art references, not ROM
screenshots.

The explicit legacy profile retains beta.6 SHA
`48c80fcd588365a38eb08c7ce1cc4ce2439c432127e4f389651b8e0bdafe2e99`.
Taller profiles preserve projection scale. For slim's four-pixel tile phase,
some existing one-pixel edge accents differ in the central 96 pixels; the display
validator bounds those changes to the documented boundary phase. Unclipped
geometry and other interior pixels agree; clipped regions use the independent
Q5 reference. No broad central-image identity claim is made.

Static geometry uses the retained solid-cell benchmark, separately from finite-
door runtime witnesses. Its ROM SHA is
`37fabb40c5d1d661d1e4eef419eb6291809cfd88006d975d024ca407dc097608`.
The historical >20% mean-error gate is applied over the **common 96-pixel window**:
mean 0.233 px, a 30.43% improvement versus v0.2.2. The full 120-pixel domain,
including newly visible near-clipped edges, has mean 0.299 px, p95 0.975 px,
and worst 4.490 px. No column reaches the five-pixel tail threshold; 67 segment
and three material mismatches remain. These host-reference results are not
independent-core geometry proofs. Archived research and thresholds are unchanged.

## Resources and release integrity

- Fixed code ends at `$3910`: 1,776 bytes remain below `$4000`.
- Resident end `$73CD`: 3,123 bytes free, preserving the 3,000-byte reserve.
- HUD 94/96 patterns; weapon/UI 86 preloaded OBJ patterns; masked pool 32;
  enemy/fixture ROM dictionary 242 patterns; cold bank 12,810 bytes.
- Dynamic BG 96; world objects 16/four per scanline; hardware total 40/ten.
- Full packet ceiling 176 GDMA blocks, plus bounded extra-row CPU copies;
  two or three VBlanks for full packets, one for cached packets.

The packager verifies retained evidence hashes against the rebuilt ROM, stages
allow-listed sources, rebuilds, writes the ZIP, extracts it, rebuilds again and
runs all tests from that extracted source tree. The release's
`Lupine3D_v0.8_clean_room_verification.json` records the archive hash and outcome;
`Lupine3D_v0.8_SHA256SUMS.txt` covers downloadable artifacts. CI additionally runs
on the committed main source. No ROM, emulator core or release ZIP is committed.
