# v0.10 qualification report

This report describes the **six-sector campaign on the 160×120 / 24-pixel
steel HUD / animated Sable configuration with HBlank-streamed publication**.
Qualification is emulator-only. The owner has no physical CGB or flash
cartridge; physical hardware and original Nintendo boot-ROM testing remain
false. The previous release is retained in [the v0.9 report](TEST_REPORT_V09.md).

**ROM SHA-256:**
`76bc716faf798acd4182bbc69e21aa7f0a95b61e7ef7b583bb4b5a680593524c`

## What changed

- **Publication streams** ([design and contracts](STREAMED_PUBLICATION.md)):
  hidden dynamic patterns and the hidden map go by HBlank DMA during
  composition; the tail is one VBlank of at most 62 banked GDMA blocks plus
  HUD, OAM and the flip. The staged two-or-three-VBlank packet is retained
  for the legacy profile and `LUPINE3D_HDMA_STREAMING=0`.
- **Exact engine savings**: unrolled folded rows with one map pointer per
  column, register-resident column scan and folded row classification, a
  per-slot actor projection record reused by the draw pass, eight-byte copy
  and wall-key loops, inline actor slot copies, and result-free midpoint and
  cast-result stores. No pixel, packet or dynamic allocation order moves.
- **A sixth sector**, Cryo Vault, in ROM bank 246.
- **The harness models HBlank DMA**, and the observer charges every DMA stall
  where it lands.

## Executed checks

| Lane | Result and scope |
| --- | --- |
| Regression suite | 248 tests pass (`make test`), including the HBlank DMA model, streamed-publication safety, the compact-strips saving stated exactly over selector bytes and page alignment, the snapshot workflow and the harness mode model |
| Release checks | **89 of 89** pass (`tools/release_check.py`), including the streamed publication ceilings, the campaign certificates for all six sectors, the route and the snapshot suites |
| Slim emitted-ROM gate | `tools/check_sable.py` passes, now including streamed-publication windows on both sides of every historical budget boundary up to the maximal 96+32 packet, the HBlank bank-isolation check (every block lands with WRAM bank 2 mapped) and the LCD-off/chaining checks |
| Display | `tools/check_display.py` passes; the legacy ROM is byte-identical to the one the v0.9 sources build |
| Coherence/world/art routes | All pass; nine RGB fixtures match `sable_v10_capture_pixels.json`, eight of them identical to v0.9's; see **What changed visually** |
| MBC5 bank contract | Six clauses against the emitted image: 40 bank writes, all in the fixed half; 1,620 pinned instruction bytes; 447-byte interrupt closure with no bank write |
| Exact wall reuse | 53 frozen comparisons, timed feedback, disabled-path equality |
| Variants | Folded/unfolded, prepared-disabled, reuse-disabled, two actors and reprojection diagnostics, all nine images equal |
| Controller completion/restart | **4,629-update route** (31,202 LCD intervals) clears all six sectors on controller input alone — Sable Outpost 347, Coolant Spine 603, Reactor Gate 641, Vent Stacks 1,530, Signal Deck 654, Cryo Vault 854 updates — collects every drop, crosses every intermission, swaps weapons in sector three, and the ending restarts the campaign; zero game-RAM writes, zero unsafe GDMA starts, every frame checked against the host geometry and compositor models |
| Independent cores | Pinned SameBoy CGB-0 and CGB-E and pinned mGBA all pass on this ROM (32 page swaps and 290/291 presentations in 480 world frames, zero unsafe GDMA or OAM starts, zero visible mask or map writes), frozen-startup RGB matching the host; **87 frozen scenes** match the harness in all three core/model lanes, HBlank-streamed frames included |
| Sustained controller motion | Eight approximately 60-second trials; reconciled CPU time, no post-setup diagnostic writes, no queue overflow or unsafe GDMA starts |
| Golden snapshots | 122 scenes accepted as the v0.10 baseline on this ROM (`tour` 9, `world` 14, `art` 6, `sable` 6, `witnesses` 87); the nine tour goldens are pixel-identical to the retired `sable_v10` hash oracle |
| Textured profile (opt-in, `LUPINE3D_TEXTURED_WALLS=1`; ROM SHA-256 `048b5477dca8133c56bf18bc355200a7543b82d27f81376d0b2ae1abcb7719a4`) | The emitted row-window kernel (`docs/TEXTURED_WALLS.md`) passes the coherence (11 updates), living-world (47) and art (6) tours with every frame check, including `dynamic_tiles_exact` against `texture_reference.compose_kernel` read from VRAM, `ray_u_exact`, `pixel_u_exact` and zero mode-3 writes; `tools/check_sable.py` under the flag passes 19 checks including blind composition that laps the 96-slot ring and crosses the VRAM half, publication windows up to 160 patterns and the chunked HBlank hand-off; pinned SameBoy CGB-0/CGB-E and mGBA pass with zero unsafe transfers; 122 goldens accepted under `snapshots/slim-sable-v2-textured/`; randomised power-on RAM images boot and validate identically in the harness, and 500 explicit SameBoy seeds pass the frozen-scene lane once the adapters treat world entry as the ROM's own write of the playing mode rather than a read (a pre-existing adapter flaw that timed out about one run in 150 on random RAM, on the v0.10 ROM as well). Measured cost about +140k T per full update against the flat compositor (lab v2: +96k mean over 700 poses, rates projected at turning 8.8/s, walking 6.9/s, two-actor 6.1/s), so the profile is not the default: the prototype gate is **not met** and Phase 5 owns the performance work. The default ROM is byte-identical |
| Harness CPU conformance | 64 seeded micro-programs of 240 emitted instruction forms each: registers, flags and scratch memory identical between the host harness and pinned SameBoy CGB-E, zero mismatches; SameBoy's adapter also counts zero VRAM or palette writes during mode 3 |

Pinned cores: SameBoy `213a12ce93d66b105a113debd9396306066a7cfc`
(CGB-0 and CGB-E), mGBA `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6`.
These lanes use a minimal synthetic bootstrap and mGBA's skip-BIOS, not a
Nintendo boot ROM.

## Sustained performance

CPU T-cycles are canonical: 8,388,608 cycles/s in double-speed mode. Each trial
observes about 59.99 seconds of LCD intervals; host execution time is
irrelevant. Recorded game-RAM writes after trial start: zero. The v0.9 column
is the retained v0.9 evidence on the same replays.

| Scenario | Full geometry/s | v0.9 | Full mean ms | v0.9 | Full worst ms | v0.9 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| turning | **10.27** | 8.15 | 97.33 | 122.37 | 117.46 | 150.69 |
| moving fire | **9.89** | 7.55 | 101.05 | 132.28 | 133.98 | 167.44 |
| walking turning | **9.87** | 7.55 | 101.19 | 132.28 | 133.97 | 167.42 |
| closed door | **8.68** | 7.15 | 114.69 | 139.60 | 117.25 | 150.69 |
| walking | **7.77** | 6.37 | 128.59 | 156.82 | 133.95 | 167.43 |
| open door | **7.30** | 5.90 | 136.51 | 169.04 | 150.69 | 184.17 |
| two actor corner | **6.80** | 5.53 | 146.95 | 180.34 | 234.40 | 284.63 |
| opening door | **0.08** | 0.08 | 130.64 | 164.19 | 150.68 | 200.92 |

Active scenarios deliver **6.80–10.27 full geometry updates/s**, against
v0.9's 5.53–8.15 on the same replays: every scenario's mean full-update time
falls by 17.8–23.0%, and its worst case by 18.2–25.0%. Zero input-queue
overflows and zero unsafe GDMA starts in all eight trials.

The opening-door trial intentionally becomes stationary after the door
finishes; its full-update rate is wall-cache reuse, not moving-camera
throughput. Cached sprite/HUD presentations are counted separately and do not
inflate these rates.

On the host harness the nine-image tour falls from 866,119 to 674,644
T-cycles per full update (**−22.1%**), its slowest image from 6.611 to 7.452
driven updates/s, and the living-world route from 719,567 to 632,973
(**−12.0%**). Of the tour's saving, streaming alone is 102,378
cycles per update; the exact engine work is the rest.

The original quality rule, `Q <= (B + P) / 2`, is the v0.8 acceptance
exception: the owner explicitly accepted the art and viewport tradeoff, and
this release does not re-litigate it. The ten-full-updates/s target is
**met while turning (10.27/s)** for the first time, missed by less than
0.15/s while moving and firing and while walking and turning, and still unmet
in the five remaining scenarios; it is not a guarantee.

## What changed visually

Six pixels, in one capture of the nine-image tour. `09_exit_approach` now
completes in five LCD intervals instead of six, so the accepted snapshot tick
lands differently on the helmet portrait's 62–63 blink window: the six pixels
are the portrait's eyes on HUD row 131, and nothing else in any of the nine
frames differs. Captured before and after from the emitted ROMs. v0.10
therefore carries its own oracle, `playtests/sable_v10_capture_pixels.json`,
beside the retained v0.9 one. No hash was edited.

## Memory and contracts

| | Figure |
| --- | --- |
| Resident ROM free | 5,083 bytes below `$8000` (floor 3,000) |
| Fixed code | ends at `$36D0`, 2,352 bytes below the `$4000` boundary |
| Instruction bytes | 17,791, of which **1,620** are pinned to the fixed half |
| Bank-register writes | 40, all in the fixed half |
| Interrupt closure | 447 bytes, none of it switching a bank |
| Streamed packet | at most 126 HBlank blocks (96 patterns + 30 map), at most 62 VBlank GDMA blocks (32 masks + 30 attributes), one VBlank |
| New fixed WRAM | `DYN_STREAMED` at `$C8CE`; the eight-byte folded column at `$CAD0` |
| New bank-1 WRAM | 36 bytes of per-slot actor projection records at `$D7A0` |

Object and mask limits, the 512-byte stack and the 3,000-byte resident
reserve are unchanged and still enforced. Reprojection and the foreground
feedback lane remain disabled and legacy-only.
