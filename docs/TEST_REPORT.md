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
| Regression suite | RESULT_TESTS |
| Slim emitted-ROM gate | `tools/check_sable.py` passes, now including streamed-publication windows on both sides of every historical budget boundary up to the maximal 96+32 packet, the HBlank bank-isolation check (every block lands with WRAM bank 2 mapped) and the LCD-off/chaining checks |
| Display | `tools/check_display.py` passes; the legacy ROM is byte-identical to the one the v0.9 sources build |
| Coherence/world/art routes | All pass; nine RGB fixtures match `sable_v10_capture_pixels.json`, eight of them identical to v0.9's; see **What changed visually** |
| MBC5 bank contract | Six clauses against the emitted image: 40 bank writes, all in the fixed half; 1,620 pinned instruction bytes; 447-byte interrupt closure with no bank write |
| Exact wall reuse | 53 frozen comparisons, timed feedback, disabled-path equality |
| Variants | Folded/unfolded, prepared-disabled, reuse-disabled, two actors and reprojection diagnostics, all nine images equal |
| Controller completion/restart | RESULT_ROUTE |
| Independent cores | RESULT_CORES |
| Sustained controller motion | Eight approximately 60-second trials; reconciled CPU time, no post-setup diagnostic writes, no queue overflow or unsafe GDMA starts |

Pinned cores: SameBoy `213a12ce93d66b105a113debd9396306066a7cfc`
(CGB-0 and CGB-E), mGBA `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6`.
These lanes use a minimal synthetic bootstrap and mGBA's skip-BIOS, not a
Nintendo boot ROM.

## Sustained performance

CPU T-cycles are canonical: 8,388,608 cycles/s in double-speed mode. Each trial
observes about 59.99 seconds of LCD intervals; host execution time is
irrelevant. Recorded game-RAM writes after trial start: zero. The v0.9 column
is the retained v0.9 evidence on the same replays.

RESULT_SUSTAINED

The opening-door trial intentionally becomes stationary after the door
finishes; its full-update rate is wall-cache reuse, not moving-camera
throughput. Cached sprite/HUD presentations are counted separately and do not
inflate these rates.

On the host harness the nine-image tour falls from 866,119 to 674,644
T-cycles per full update (**−22.1%**) and the living-world route from 719,567
to 632,973 (**−12.0%**). Of the tour's saving, streaming alone is 102,378
cycles per update; the exact engine work is the rest.

The original quality rule, `Q <= (B + P) / 2`, is the v0.8 acceptance
exception: the owner explicitly accepted the art and viewport tradeoff, and
this release does not re-litigate it. The ten-full-updates/s target is
RESULT_TARGET.

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
