# v0.12 qualification report

This report describes **Sable Outpost v0.12**, the showcase game of the
Lupine 3D engine: eighteen sectors in three episodes on the 160×120
textured world, the 24-pixel steel HUD and animated Sable art, with
HBlank-streamed and VBlank-overlapped publication. It is the first release
under the game's own name: the cartridge header reads `SABLE OUTPOST`, mask
ROM version 7. Qualification is emulator-only. The owner has no physical CGB
or flash cartridge; physical hardware and original Nintendo boot-ROM testing
remain false. The previous release is retained in
[the v0.11 report](TEST_REPORT_V11.md).

**ROM SHA-256:**
`9707e90eea9c51fe73dcf1a6517b639d785ab914a82f66fac763c984941b0fa4`

The bound evidence is archived in `milestones/v0.12/qualification/`
(`tools/qualify_sable_release.py`: 31 evidence files, each hashed, for this
ROM only).

## What changed

- **The engine and its game separated.** Sable Outpost is a folder of data,
  `games/sable_outpost/`, that the engine builds
  ([the engine and the game](../explanation/engine-and-game.md)). Through
  the separation every ROM the showcase builds, in all ten identity
  configurations, stayed byte for byte identical; this release's ROM differs
  from that one only in the cartridge header's title, version and two
  checksums.
- **Textured walls and overlapped publication are the default**
  ([textured walls](../explanation/textured-walls.md),
  [performance after textures](../evidence/PERFORMANCE_PHASE5.md)), since v0.11.
- **A starter game, the creator tooling and the handbook**
  ([docs index](../README.md)).

## Executed checks

| Lane | Result and scope |
| --- | --- |
| Regression suite | **322 tests** pass, 9 skipped (`tools/run_tests.py`) |
| Release checks | **90 of 90** pass (`tools/release_check.py`), among them every campaign level's certificate, the route over every sector with the restart, the six actor slots and the fold identity on compact |
| Controller route | **24,198 verified updates** clear all eighteen sectors on controller input alone, in CI's eight chunks (sectors 1-4 from the title, then 5-7, 8-9, 10, 11-13, 14-15, 16-17 and 18 from their continue codes, the last restarting the campaign from the ending). No game-RAM writes; zero unsafe GDMA starts |
| Slim emitted-ROM gate | `tools/check_sable.py` passes, including the streamed-publication windows, HBlank bank isolation and the HUD fixture |
| Display | `tools/check_display.py` passes |
| Coherence/world/art routes | All pass, every frame validated against the host model |
| MBC5 bank contract | 51 bank-register writes, all in the fixed half; 2,006 pinned instruction bytes; a 722-byte interrupt closure with no bank write |
| Exact wall reuse | 53 frozen comparisons, timed feedback, disabled-path equality |
| Variants | Folded (slim and compact) and unfolded (compact), prepared-disabled, reuse-disabled, two actors and reprojection diagnostics |
| Independent cores | Pinned SameBoy CGB-0 and CGB-E and pinned mGBA pass on this ROM: 30 page swaps and 282 presentations (283 on mGBA) in 480 world frames, zero unsafe GDMA or OAM starts, zero visible mask writes, zero VRAM or palette writes in mode 3 |
| Independent witnesses | 87 frozen scenes, host and every core byte-identical |
| Harness CPU conformance | 64 seeded programs of 240 emitted instruction forms each: registers, flags and scratch memory identical between the harness and pinned SameBoy CGB-E, zero mismatches |
| Golden snapshots | `tour` 9, `world` 14, `art` 6, `sable` 6, `witnesses` 87, all matching this ROM's captures |
| The starter game | Built, certified, toured against its goldens, played to its ending and restarted, run in SameBoy; the limits game built at every documented maximum; a new game scaffolded and built |
| Clean room | `tools/package_release.py` stages the allow-listed sources, rebuilds, archives, extracts, rebuilds again and runs the suite |

Pinned cores: SameBoy `213a12ce93d66b105a113debd9396306066a7cfc`
(CGB-0 and CGB-E), mGBA `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6`.
These lanes use a minimal synthetic bootstrap and mGBA's skip-BIOS, not a
Nintendo boot ROM.

## Sustained performance

CPU T-cycles are canonical: 8,388,608 cycles/s in double-speed mode. Each
trial observes about 60 seconds of LCD intervals; host execution time is
irrelevant. Recorded game-RAM writes after trial start: zero. Zero
input-queue overflows and zero unsafe GDMA starts in all eight trials.

| Scenario | Full geometry/s | Full mean ms | Full worst ms |
| --- | ---: | ---: | ---: |
| turning | **9.89** | 101.08 | 134.14 |
| walking turning | **9.58** | 104.21 | 150.68 |
| moving fire | **9.55** | 104.46 | 150.69 |
| open door | **8.08** | 122.32 | 134.14 |
| walking | **7.45** | 133.98 | 150.69 |
| closed door | **7.23** | 137.27 | 167.62 |
| two actor corner | **7.12** | 140.41 | 217.67 |
| opening door | **0.08** | 127.28 | 150.68 |

Every rate equals the overlapped measurement in
[performance after textures](../evidence/PERFORMANCE_PHASE5.md), as it must: the code is
the same and only the header changed. Against v0.11's flat default
(the [v0.11 report](TEST_REPORT_V11.md)) the textured walls cost
walking 7.77 to 7.45/s and closed door 8.68 to 7.23/s; turning (10.25 to
9.89) and the two-actor corner (6.62 to 7.12) are closer or faster because
the overlapped tail no longer waits for VBlank. The ten-full-updates/s
target is not met in any scenario. The opening-door trial becomes stationary
once the door finishes; its rate is wall-cache reuse, not moving-camera
throughput.

The original quality rule, `Q <= (B + P) / 2`, **fails** for the closed-door
case (mean 1,151k T against a limit of 1,000k; p95 1,404k against 1,125k)
and passes in the other seven (`build/v012/quality-budget.json`, bound as
evidence). `B` and `P` are the immutable v0.8 inputs, measured on the old
first sector and the flat renderer. The owner's explicit acceptance of the
art, viewport and textured-walls tradeoff remains the basis for the default
configuration; the gate itself is unchanged.

## What changed visually

Nothing. Every golden in every suite matches this ROM's captures, and the
header is not a picture.

## Memory and contracts

| | Figure |
| --- | --- |
| Resident ROM free | 7,606 bytes below `$8000` (floor 3,000) |
| Fixed code | ends at `$3FC0`, 64 bytes below the `$4000` boundary |
| Instruction bytes | 22,348, of which **2,006** are pinned to the fixed half |
| Bank-register writes | 51, all in the fixed half |
| Interrupt closure | 722 bytes, none of it switching a bank |
| Campaign | 18 levels, five to a bank from 241; six doors and six actors per level |

Object and mask limits, the 512-byte stack and the 3,000-byte resident
reserve are unchanged and still enforced. Reprojection and the foreground
feedback lane remain disabled and legacy-only.
