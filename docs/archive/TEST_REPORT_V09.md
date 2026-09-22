# v0.9 qualification report

This report describes the shipped **five-sector campaign on the 160×120 /
24-pixel steel HUD / animated Sable** configuration. Qualification is
emulator-only. The owner has no physical CGB or flash cartridge; physical
hardware and original Nintendo boot-ROM testing remain false. The previous
release is retained in [the v0.8 report](TEST_REPORT_V08.md).

**ROM SHA-256:**
`e59f722b698b545e75e5dbb2cdfe3810c5cc6a3ec96e38e868c09d286e2a9b89`

## Executed checks

| Lane | Result and scope |
| --- | --- |
| Regression suite | 229 tests; frozen v1 hash and explicit legacy regressions plus fresh-process default art/display validation |
| Current release checks | 89 checks pass, including a readability certificate for all five sectors; the discovered test inventory is not used as proof of test execution |
| Coherence/world/art routes | All pass; the nine current RGB fixtures match `sable_v09_capture_pixels.json`, with earlier oracles retained |
| MBC5 bank contract | Six clauses checked against the emitted image, with entry points read out of the cartridge's reset and interrupt vectors; each clause separately checked against an image built to break it |
| Exact wall reuse | 53 frozen comparisons, timed feedback, disabled-path equality |
| Variants | Folded/unfolded, prepared-disabled, reuse-disabled, two actors and reprojection diagnostics |
| Controller completion/restart | 24,905 LCD intervals and 2,961 verified updates; five sectors cleared, one of them with the second weapon; no game-RAM injection; completion, pickup, keycard, intermissions, ending and restart verified; zero unsafe GDMA starts |
| Native art and emitted animation | 18 groups: 36 enemy cels, weapon phases, rapid restarts, clock wrap, masks/admission, HUD states and raster/publication boundaries |
| Display | Seven diagnostic poses with independent Q5 geometry; legacy ROM remains byte-exact |
| Independent cores | Pinned SameBoy CGB-0 and CGB-E and pinned mGBA all pass on this ROM, with frozen-startup RGB matching the host; 87 frozen scenes match the harness in all three core/model lanes |
| Sustained controller motion | Eight approximately 60-second trials; reconciled CPU time, no post-setup diagnostic writes, no queue overflow or unsafe GDMA starts |

Pinned cores: SameBoy `213a12ce93d66b105a113debd9396306066a7cfc`
(CGB-0 and CGB-E), mGBA `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6`.
These lanes use a minimal synthetic bootstrap and mGBA's skip-BIOS, not a
Nintendo boot ROM. Diagnostic frozen scenes are distinct from the
controller-only completion run.

### What the pinned cores caught

Both adapters date from before the title screen and drove their route straight
from reset, so on this ROM they sat on the title for all 480 frames and
reported nothing. Both press START first now, and their frame numbers are
counted from the world rather than from reset — the route they describe is
unchanged.

With that fixed, SameBoy reported **192 CPU writes to the displayed background
map**, which the host harness had not seen. The weapon swap turns the LCD off
to stream patterns and was putting back a constant `LCDC`, clearing the
background-map bit that says which page is displayed; `CURRENT_PAGE` still said
the other one, so the next frame's hidden-page copy wrote the visible map. It
restores the `LCDC` it found now. The swap also ran on the very first frame of
a real power-on, because the weapon state lives in fixed WRAM that the console
does not clear and the harness does; boot initialises it.

Neither fault was reachable in the host harness, which zeroes WRAM and models
the page flip from the same state the ROM does. This is what the pinned lanes
are for.

## Sustained performance

CPU T-cycles are canonical: 8,388,608 cycles/s in double-speed mode. Each trial
observes about 59.99 seconds of LCD intervals; host execution time is
irrelevant. Recorded game-RAM writes after trial start: zero.

| Scenario | Full geometry/s | Full mean ms | Full worst ms |
| --- | ---: | ---: | ---: |
| turning | 8.15 | 122.37 | 150.69 |
| moving fire | 7.55 | 132.28 | 167.44 |
| walking turning | 7.55 | 132.28 | 167.42 |
| closed door | 7.15 | 139.60 | 150.69 |
| walking | 6.37 | 156.82 | 167.43 |
| open door | 5.90 | 169.04 | 184.17 |
| two actor corner | 5.53 | 180.34 | 284.63 |
| opening door | 0.08 | 164.19 | 200.92 |

The opening-door trial intentionally becomes stationary after the door
finishes; its 0.08 full updates/s is wall-cache reuse, not moving-camera
throughput. Active scenarios deliver **5.53–8.15 full geometry updates/s**,
against v0.8's 5.50–7.92 on the same replays. Cached sprite/HUD presentations
are counted separately and do not inflate this rate. The ten-full-updates/s
target is unmet.

The nine-image tour measures **6.611 full geometry updates/s**, unchanged
across every commit of the campaign work.

The original quality rule, `Q <= (B + P) / 2`, still fails, for mean and p95 in
every scenario. That failure is v0.8's accepted visual tradeoff, inherited
here: this release does not spend more per frame than v0.8 did. **The owner
explicitly accepted that tradeoff**; this remains an acceptance exception, not
a passing mathematical result, and does not relax memory, publication safety or
unrelated experiment gates. The evaluation uses the immutable pre-viewport
baseline and performance lanes and identical replay identities.

## What changed visually

The reticle moved from OBJ palette 6 to palette 4 so palette 6 could carry a
third enemy kind. Captured before and after from the emitted ROM, that changes
**eight pixels per frame** — the crosshair's own lit pixels, from `(13,28,26)`
to `(16,29,27)` — in every one of the nine tour frames, and nothing else. v0.9
therefore carries its own oracle, `playtests/sable_v09_capture_pixels.json`,
beside the retained v0.8 pair. No hash was edited.

Separately, no runtime digit below map row eight had ever been visible: the row
offset passes 255 and the address arithmetic dropped the carry, so the continue
code on row nine and the skill indicator on row fourteen were written where
nobody could read them. Both display correctly now, and the map cell each
reserved slot resolves to is checked.

## Memory and contracts

| | Figure |
| --- | --- |
| Resident ROM free | 6,475 bytes below `$8000` (floor 3,000) |
| Fixed code | ends at `$3240`, 3,520 bytes below the `$4000` boundary |
| Instruction bytes | 16,514, of which **1,604** are pinned to the fixed half |
| Bank-register writes | 40, all in the fixed half |
| Interrupt closure | 447 bytes, none of it switching a bank |

Publication budgets, object and mask limits, the 512-byte stack and the
3,000-byte resident reserve are unchanged and still enforced. Reprojection and
the foreground feedback lane remain disabled.

The explicit legacy profile retains beta.6 SHA
`48c80fcd588365a38eb08c7ce1cc4ce2439c432127e4f389651b8e0bdafe2e99`.
