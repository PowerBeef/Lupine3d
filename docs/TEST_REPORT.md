# Lupine 3D 0.7.0-beta.6 test report

Production ROM SHA-256:
`48c80fcd588365a38eb08c7ce1cc4ce2439c432127e4f389651b8e0bdafe2e99`

4 MiB MBC5 · CGB-only · no cartridge RAM · **emulator-qualified**

The release version changes packaging metadata. Its ROM is byte-identical to
the accepted performance milestone. The [beta.5 report](TEST_REPORT_BETA5.md)
and immutable comparison archives retain historical evidence separately.

## Executed verification

**137 tests and 86 release checks pass locally.** The packaged source is also
rebuilt, extracted into a fresh directory, rebuilt again and tested. Test
inventory is recorded separately from actual execution logs.

Coverage includes:

- The frozen v1 ROM hash, deterministic builds and the original nine RGB fixtures.
- All 282 legal folded selectors and 6,768 pattern comparisons, plus the complete
  19-state unfolded domain and both stored strip widths/styles.
- Fifty-three same-snapshot descriptor, allocation, packet and RGB comparisons.
- Certificate carries, all camera banks, cache collisions/reloads/generation
  wrap, bank restoration and cooperative simulation state.
- Four-anchor packet bounds, splits, scalar fallbacks and prepared padding.
- Physical-query provenance, same-key refinement promotion, one through four
  actors, all-screen refinement bounds and forced-full agreement.
- Q8.8 actor transforms, atomic capacity rollback, hidden-X OAM selection,
  LOD fallback and physical door-run separation.
- All 2,359,296 logical projection bytes, emitted directory/page boundaries,
  and the bounded near-field projection candidate.
- Foreground queue overflow, sequence/generation wrap, reload ownership,
  coherent OAM publication and maximum 176-block staged transfers.
- The coherence/world/art routes, controller-only completion/restart, variants,
  short motion checks and the full 24,384-view geometry-tail scan.
- Both committed atlas profiles: training hashes, complete bucket directories,
  all 510 signature/pattern comparisons and eleven validated forced-full
  diagnostic presentations per profile.

## Production measurements

The review baseline is commit `466bd09786d076c1e4b528f32647aa2885d201ff`, ROM
`8f0425f07220d7649ff419c9c3fb0a212c4a234b40463ab431c1f97e1b7b3cd3`.
Each sustained lane spans 3,584 LCD intervals (59.989 seconds). The baseline
and production receive identical controller tapes and no post-setup game-RAM
writes. Timing categories reconcile exactly in CPU T-cycles.

| Scenario | Baseline mean | Production mean | Production p95 | Full geometry/s |
|---|---:|---:|---:|---:|
| Walking | 1,212,118 | 1,151,487 | 1,264,268 | 7.25 |
| Turning | 921,810 | 866,184 | 983,424 | 9.67 |
| Walking and turning | 980,133 | 906,582 | 1,123,992 | 9.23 |
| Moving fire | 978,764 | 906,582 | 1,123,916 | 9.23 |
| Open door | 1,271,867 | 1,225,335 | 1,264,160 | 6.83 |
| Closed door | 1,035,856 | 963,202 | 1,124,568 | 8.68 |
| Two-actor corner | 1,348,764 | 1,283,440 | 1,685,396 | 6.52 |

Mean improvement is 3.7–7.5% across the six primary moving scenarios. The 10 Hz
target remains unmet. The two-actor arena has intermittent contention: both
actors reach admission together in three frames, with world OAM submitted in
47 production frames. Its five-second windows all contain translation/turning.

The stationary door-tap lane has five full geometry frames while the door
opens, followed by cached presentations. Those cached frames are not geometry
throughput. Controller-only completion occurs at update 274 and restart is
verified at update 276, with no gameplay-RAM injection. The bot reads live state
to steer; this is functional verification, not blind human navigation.

| Driven route | Coherence | Combat diagnostic |
|---|---:|---:|
| Presentations / captures | 11 / 9 | 47 / 14 |
| Full / cached | 9 / 2 | 22 / 25 |
| Mean T-cycles/presentation | 738,315 | 600,030 |
| Maximum T-cycles/presentation | 1,128,288 | 1,404,568 |
| Peak dynamic patterns | 18 / 96 | 25 / 96 |
| Peak objects per scanline | 4 / 10 | 7 / 10 |
| Unsafe GDMA starts | 0 | 0 |

Live sampling changes as rendering becomes faster. Same-snapshot exactness is
established separately; controller-driven RGB differences alone are not used
to classify a regression. The nine production RGB fixtures remain unchanged.

## Independent emulators and geometric witnesses

| Core / model | Pinned revision | Production result |
|---|---|---|
| SameBoy CGB-0 | `213a12ce93d66b105a113debd9396306066a7cfc` | Pass |
| SameBoy CGB-E | Same revision | Pass |
| mGBA CGB | `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6` | Pass |

Startup and controller routes pass on the exact ROM. All 51 frozen-world
images agree with the project harness in the production, quality and near-field
configurations on all three lanes. The rational plane oracle independently
provides expected visibility; emulator agreement alone does not establish
geometric correctness. Frozen-scene writes are explicitly diagnostic.

Scalar, unfolded, packet and both compact-storage reference configurations also
pass the independent controller lanes. Foreground moving-fire traces exercise
the actual foreground lane with no mixed world OAM. SameBoy observes DMA,
publication and visible-mask writes; mGBA does not instrument DMA writes.
Neither bootstrap tests the original Nintendo boot ROM.

## Enable/disable decisions and resources

Production enables compact strips, invariant camera setup, narrow yield contexts
and exact attribute padding. The other rendering candidates remain disabled
where their timing, quality or feedback gates fail. In particular, the physical
depth/actor/admission combination exceeds the mean/p95 half-gains budget, and
foreground sample-to-visible p95 is 40.606 ms versus the 33.485 ms target.
See the [implementation ledger](RENDERING_IMPLEMENTATION.md) for candidate
hashes, partial rejection gates and reviewed before/after motion sequences.

The allocation ledger checks fixed ROM, banked ROM, WRAM, HRAM, stack, VRAM and
OAM ownership. The production resident image ends at `$68CD`, leaving **5,939
bytes**. Fixed code ends at `$3090`; the 3,000-byte reserve, 512-byte stack,
96 dynamic patterns, 32 masks and 176-block staged-publication limit hold.
The 3,840-byte strip-table saving yields 2,816 net linked bytes; it does not
expand the fixed-ROM execution ceiling.

## Release evidence and hardware status

The source bundle includes `build/rendering_qualification/report.json` and its
65 hash-bound evidence files. It records two deterministic ROM rebuilds,
sustained/frozen/reference results, controller replays and the actual test log.
The packager verifies these hashes and emits a separate clean-room report,
release manifest and SHA-256 checksums for its distributable files.

GitHub Actions status is reported separately from these local results. The
owner has no physical CGB or flash cartridge; hardware status remains false
and does not block emulator-qualified releases. Development takes place on
`main`. See the [development policy](../AGENTS.md) and optional future
[hardware checklist](HARDWARE_TEST_CHECKLIST.md).
