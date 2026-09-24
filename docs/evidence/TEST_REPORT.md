# v0.11 qualification report

This report describes the **eighteen-sector, three-episode campaign on the
160×120 / 24-pixel steel HUD / animated Sable configuration with
HBlank-streamed publication**, plus the opt-in textured-walls profile.
Qualification is emulator-only. The owner has no physical CGB or flash
cartridge; physical hardware and original Nintendo boot-ROM testing remain
false. The previous release is retained in [the v0.10 report](../archive/TEST_REPORT_V10.md).

**ROM SHA-256:**
`76b6f974477021fd79c868643c16002006bd3ccf3690f20b95acdfd3dc16c58a`

The bound evidence is archived in `milestones/v0.11/qualification/`
(`tools/qualify_sable_release.py`: 25 evidence files, each hashed, for this
ROM only).

## What changed

- **Three episodes of six sectors**, every sector redrawn as a named place
  ([campaign](../../games/sable_outpost/docs/campaign.md), "Three episodes" and "Named places"), with a
  level directory packing five levels to a ROM bank, six doors and six actor
  slots per level, a palette set per episode, four weapons owned by episode,
  a boss kind, and episode opening and closing screens.
- **Golden-image verification** ([verification](../explanation/verification.md)) replaces
  the pixel-hash oracles; engine invariants stay hard gates.
- **The opt-in textured profile** ([textured walls](../explanation/textured-walls.md)),
  with a texture set per episode.
- **The SDK**: RGBDS-form exports, `tools/lupine.py`, the level format and
  certificate, the Tiled round trip, the art pipeline and the developer
  guide ([docs index](../README.md)).

## Executed checks

| Lane | Result and scope |
| --- | --- |
| Regression suite | **291 tests** pass, 9 skipped (`tools/run_tests.py`), including the eighteen-sector certificate, continue codes for every sector and skill, the level directory, six doors and actors, palette sets, weapons, the boss, episode screens, the snapshot workflow, the textured kernel and its reference |
| Release checks | **90 of 90** pass (`tools/release_check.py`), among them every campaign level's certificate, the route over every sector with the restart, the six actor slots, and the first sector's latent-jamb seams |
| Controller route | **24,057 verified updates** clear all eighteen sectors on controller input alone, in CI's five chunks: sectors 1-6 from the title, then 7-9, 10-12, 13-15 and 16-18 from their continue codes, the last restarting the campaign from the ending. No game-RAM writes; zero unsafe GDMA starts |
| Slim emitted-ROM gate | `tools/check_sable.py` passes, including the streamed-publication windows, HBlank bank isolation and the HUD fixture |
| Display | `tools/check_display.py` passes; the legacy ROM stays byte-identical |
| Coherence/world/art routes | All pass, every frame validated against the host model |
| MBC5 bank contract | 43 bank-register writes, all in the fixed half; 1,638 pinned instruction bytes; a 447-byte interrupt closure with no bank write |
| Exact wall reuse | 53 frozen comparisons, timed feedback, disabled-path equality |
| Variants | Folded/unfolded, prepared-disabled, reuse-disabled, two actors and reprojection diagnostics |
| Independent cores | Pinned SameBoy CGB-0 and CGB-E and pinned mGBA pass on this ROM: 32 page swaps and 293/294 presentations in 480 world frames, zero unsafe GDMA or OAM starts, zero visible mask writes, zero VRAM or palette writes in mode 3 |
| Independent witnesses | 87 frozen scenes, host and every core byte-identical |
| Harness CPU conformance | 64 seeded programs of 240 emitted instruction forms each: registers, flags and scratch memory identical between the harness and pinned SameBoy CGB-E, zero mismatches |
| Golden snapshots | Both profiles: `tour` 9, `world` 14, `art` 6, `sable` 6, `witnesses` 87, all matching this ROM's captures |
| Textured profile (opt-in; ROM SHA-256 `2535c7c822896ff487290d41eb35286de7b55823974411561c47cdaad5dfd344`) | Its three driven tours and Sable checks pass, including the texture set per episode; its goldens match |
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

| Scenario | Full geometry/s | v0.10 | Full mean ms | Full worst ms |
| --- | ---: | ---: | ---: | ---: |
| turning | **10.25** | 10.27 | 97.52 | 117.47 |
| moving fire | **9.79** | 9.89 | 102.17 | 134.00 |
| walking turning | **9.80** | 9.87 | 101.97 | 133.99 |
| closed door | **8.68** | 8.68 | 114.73 | 117.25 |
| open door | **8.38** | 7.30 | 119.10 | 133.95 |
| walking | **7.77** | 7.77 | 128.59 | 133.95 |
| two actor corner | **6.62** | 6.80 | 150.94 | 251.16 |
| opening door | **0.10** | 0.08 | 120.03 | 133.94 |

**The v0.10 column is not a like-for-like comparison.** The replays start at
the first sector's spawn, and that sector was redrawn: the spawn, the airlock
door and the Sentinel keep their cells, but the rooms the camera sees are
new. Only `two_actor_corner` runs in a synthetic arena independent of the
map, and it is the one comparable row: 6.80/s became 6.62/s (mean full
update +2.7%). Over the same span the engine gained six simulated actor slots
instead of four and the ten-object 40×32 weapon; this report does not
apportion the difference between them.

The opening-door trial intentionally becomes stationary after the door
finishes; its rate is wall-cache reuse, not moving-camera throughput. The
ten-full-updates/s target is met while turning, missed by about 0.2/s while
moving and firing and while walking and turning, and unmet in the four other
active scenarios. It is not a guarantee.

The original quality rule, `Q <= (B + P) / 2`, now computes as **passed** in
every case (`build/v011/quality-budget.json`). That is not the rule being
met on equal terms: `B` and `P` are the immutable v0.8 inputs measured on the
old first sector, and `Q` is measured on the redrawn one. The owner's
explicit acceptance of the art and viewport tradeoff remains the basis for
the default configuration, as it has been since v0.8.

## What changed visually

Every golden of the first sector was re-accepted, with a note, in both
profiles: the tour (four captures renamed, because the zig-zag door became
the mess hatch), the world route, two art scenes, and the witness scenes,
which read level 0's surface tables. The Sable poses stand in the airlock,
which kept its cells, and did not change. A changed scene was accepted only
when its HUD was untouched or differed only on the helmet's eye slits, whose
blink lands on other captures now that update timing moved.

## Memory and contracts

| | Figure |
| --- | --- |
| Resident ROM free | 3,963 bytes below `$8000` (floor 3,000) |
| Fixed code | ends at `$3970`, 1,680 bytes below the `$4000` boundary |
| Instruction bytes | 18,560, of which **1,638** are pinned to the fixed half |
| Bank-register writes | 43, all in the fixed half |
| Interrupt closure | 447 bytes, none of it switching a bank |
| Campaign | 18 levels, five to a bank from 241; six doors and six actors per level |

Object and mask limits, the 512-byte stack and the 3,000-byte resident
reserve are unchanged and still enforced. Reprojection and the foreground
feedback lane remain disabled and legacy-only.
