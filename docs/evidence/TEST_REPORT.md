# v0.13 qualification report

This report describes **Sable Outpost v0.13**, the showcase game of the
Lupine 3D engine, overhauled into a game of its own: a story told across 27
screens, a title with an identity, eight songs, and eighteen sectors rebuilt
around placed items, ammunition, coloured card doors, remote doors and their
triggers, ranged Wardens, an Overseer at the end of every episode and
carry-over. The cartridge header reads `SABLE OUTPOST`, mask ROM version 8.
Qualification is emulator-only. The owner has no physical CGB or flash
cartridge; physical hardware and original Nintendo boot-ROM testing remain
false. The previous release is retained in
[the v0.12 report](../archive/TEST_REPORT_V12.md).

**ROM SHA-256:**
`248963771d9d2b730c34d2632199eccfbde088073a6ca947e074d02c9ceab2ca`

The bound evidence is archived in `milestones/v0.13/qualification/`
(`tools/qualify_sable_release.py`: 31 evidence files, each hashed, for this
ROM only).

## What changed

- **Sable Outpost is a game** ([its README](../../games/sable_outpost/README.md),
  [the campaign](../../games/sable_outpost/docs/campaign.md)): the story, the
  title, a prologue, a debrief with Chief Engineer Oda's log after every
  sector, the episode pages and an ending; eight songs; and eighteen sectors
  in which every room holds an encounter, health, ammunition, armour, a card,
  a weapon case or a trap. Each sector fields six actors and eight to
  thirteen items; each episode ends with a boss.
- **What the engine grew for it** ([release notes](../../RELEASE_NOTES.md)):
  placed items, two ammunition pools, coloured card doors, remote doors and
  `open_door` triggers, drops as item types, ranged enemies with a wind-up,
  per-actor wake radius and sight, armour, strafing, carry-over, the HUD's
  ammunition, key and armour indicators, and the results screens' items
  tally.
- **The engine's evidence is pinned** to the first sector as v0.12
  populated it (the evidence population,
  [verification](../explanation/verification.md)), so the repopulated sector
  moved no evidence golden, witness scene, cycle gate or tape.

## Executed checks

| Lane | Result and scope |
| --- | --- |
| Regression suite | **367 tests** pass, 14 skipped (`tools/run_tests.py`) |
| Release checks | **90 of 90** pass (`tools/release_check.py`), among them every campaign level's certificate, the route over every sector with the restart, the six actor slots and the fold identity on compact |
| Controller route | **22,437 verified updates** clear all eighteen repopulated sectors on controller input alone, in CI's eight chunks (sectors 1-3 from the title, then 4-6, 7-9, 10-12, 13-14, 15-16, 17 and 18 from their continue codes, the last restarting the campaign from the ending). No game-RAM writes; zero unsafe GDMA starts |
| Slim emitted-ROM gate | `tools/check_sable.py` passes, including the streamed-publication windows, HBlank bank isolation and the HUD fixture |
| Display | `tools/check_display.py` passes |
| Coherence/world/art routes | All pass, every frame validated against the host model |
| MBC5 bank contract | 54 bank-register writes, all in the fixed half; 2,173 pinned instruction bytes; a 736-byte interrupt closure with no bank write |
| Exact wall reuse | 53 frozen comparisons, timed feedback, disabled-path equality |
| Variants | Folded (slim and compact) and unfolded (compact), prepared-disabled, reuse-disabled, two actors and reprojection diagnostics |
| Independent cores | Pinned SameBoy CGB-0 and CGB-E and pinned mGBA pass on this ROM: 27 page swaps and 223 presentations in 480 world frames, zero unsafe GDMA or OAM starts, zero visible mask writes, zero VRAM or palette writes in mode 3 |
| Independent witnesses | 87 frozen scenes, host and every core byte-identical |
| Harness CPU conformance | 64 seeded programs of emitted instruction forms: registers, flags and scratch memory identical between the harness and pinned SameBoy CGB-E, zero mismatches |
| Golden snapshots | `tour` 9, `world` 14, `art` 6, `sable` 6, `witnesses` 87 and `screens` 27, all matching this ROM's captures |
| The starter game | Built, certified, toured against its goldens, played to its ending and restarted, run in SameBoy; the limits game built at every documented maximum; a new game scaffolded and built |
| Clean room | `tools/package_release.py` stages the allow-listed sources, rebuilds, archives, extracts, rebuilds again and runs the suite |

Pinned cores: SameBoy `213a12ce93d66b105a113debd9396306066a7cfc`
(CGB-0 and CGB-E), mGBA `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6`.
These lanes use a minimal synthetic bootstrap and mGBA's skip-BIOS, not a
Nintendo boot ROM.

## Sustained performance

CPU T-cycles are canonical: 8,388,608 cycles/s in double-speed mode. Each
trial observes about 60 seconds of LCD intervals on the evidence population;
host execution time is irrelevant. Recorded game-RAM writes after trial
start: zero. Zero input-queue overflows and zero unsafe GDMA starts in all
eight trials.

| Scenario | Full geometry/s | v0.12 |
| --- | ---: | ---: |
| turning | **9.99** | 9.89 |
| walking turning | **9.68** | 9.58 |
| moving fire | **9.65** | 9.55 |
| open door | **8.28** | 8.08 |
| walking | **7.45** | 7.45 |
| closed door | **7.45** | 7.23 |
| two actor corner | **7.17** | 7.12 |
| opening door | **0.10** | 0.08 |

Every scenario is as fast as v0.12 or faster, though every tick now also
looks for items and triggers: this release's CPU savings (the windowed
admission preflight, no cast for a dormant actor) more than pay for it. The
ten-full-updates/s target is not met in any scenario. The opening-door trial
becomes stationary once the door finishes; its rate is wall-cache reuse, not
moving-camera throughput.

The original quality rule, `Q <= (B + P) / 2`, **fails** for the
closed-door case (mean 1,123k T against a limit of 1,000k; p95 1,264k
against 1,125k), closer than v0.12 (1,151k and 1,404k), and passes in the
other seven (`build/v013/quality-budget.json`, bound as evidence). `B` and
`P` are the immutable v0.8 inputs, measured on the old first sector and the
flat renderer. The owner's explicit acceptance of the art, viewport and
textured-walls tradeoff remains the basis for the default configuration; the
gate itself is unchanged.

## What changed visually

The engine's evidence suites (`tour`, `world`, `art`, `sable`, `witnesses`)
did not move: they run on the evidence population. The `screens` suite
changed where the game did, each accepted with its note: the new title,
prologue, debriefs, episode pages, game over and ending, and the items tally
on the intermission and every debrief. The HUD gained the ammunition digits,
the key cards and the armour shield, drawn only when there is something to
show.

## Memory and contracts

| | Figure |
| --- | --- |
| Resident ROM free | 7,002 bytes below `$8000` (floor 3,000; the tightest research variant keeps 3,321) |
| Fixed code | ends at `$3BC0`, 1,088 bytes below the `$4000` boundary |
| Instruction bytes | 23,338, of which **2,173** are pinned to the fixed half |
| Bank-register writes | 54, all in the fixed half |
| Interrupt closure | 736 bytes, none of it switching a bank |
| Campaign | 18 levels, five to a bank from 241; six doors, six actors, sixteen items and eight triggers per level at most |

Object and mask limits, the 512-byte stack and the 3,000-byte resident
reserve are unchanged and still enforced. Reprojection and the foreground
feedback lane remain disabled and legacy-only.
