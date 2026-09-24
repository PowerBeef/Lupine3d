# HBlank-streamed publication

This document records the v0.10 change to how a full geometry update reaches
the console: the hidden dynamic patterns and the hidden tile-number map now
travel by **HBlank DMA while the CPU is still composing**, so a full packet
needs **one VBlank** instead of two or three. The change is output-exact for
every descriptor, packet, VRAM byte and OAM byte; it changes only *when* a
frame is presented. The legacy display profile keeps the staged VBlank path
byte for byte.

## Why publication was the largest remaining cost

[The v0.8 performance audit](PERFORMANCE_AUDIT_V08.md) measured where a full
update spends its cycles and found that the engine work is only part of it:

| Bucket | Per full update (walking) |
|---|---:|
| engine | 1,003,270 |
| **publication waits** | **215,656** |
| simulation service | 116,999 |

Publication is quantized to LCD intervals because `upload_hidden_page`
busy-polls `LY`. A slim packet took two or three of them: one VBlank for the
dynamic patterns (plus the 96 extra map bytes and the 32-byte attribute prefix
copied by the CPU), an optional extra VBlank above 48 dynamic+mask patterns,
and a final VBlank for the map, the remaining attributes, HUD and OAM. Between
the pattern stage and the tail the CPU did roughly 5,000 cycles of work and
then spun for the remaining ~135,000 cycles of the interval. The audit called
that interval **dead time**, and showed that no engine saving smaller than an
interval converts into frame rate while it exists.

The audit's own answer, committing the tail from the VBlank interrupt while
the next frame casts, buys 29% but costs a frame of publication latency and a
change to where the harness verifies from. This change takes a different
route to the same interval, and keeps the verification vantage point.

## The technique

The hidden BG page is, by construction, never read by the PPU: the displayed
page's attribute map selects the other pattern bank, and the displayed map is
the other map. Anything written into the hidden bank or the hidden map during
the visible frame is invisible until the flip. The CGB's HBlank DMA moves one
16-byte block at the HBlank of every visible line without any CPU
involvement beyond a ~64 T-cycle stall per block, and it writes VRAM safely
by hardware design.

So the full publication is now:

1. `cast_all`, then `render_entities` **before** `render_view`. Neither pass
   reads what the other writes; the masks are banked and go by GDMA in the
   tail anyway.
2. `render_view` composes column by column. At the end of every column, if the
   LCD is on and no transfer is active, `stream_dynamic_tiles` hands the
   patterns composed since the last hand-off to HBlank DMA, into the hidden
   bank at `$9000`. `DYN_STREAMED` records how many have been handed over;
   `render_view` resets it at entry.
3. `upload_hidden_page` waits for the last transfer, streams whatever the last
   column left, then streams the complete hidden tile-number map (30 blocks
   on slim, 28 on compact) while the CPU builds the attribute packet and the
   HUD underneath it.
4. Once the map has landed, one `wait_vblank`, then the tail: masked OBJ
   patterns and the attribute packet by GDMA (at most 62 blocks), the HUD map
   cells, OAM DMA, the LCDC flip and the presentation serial.

The staged path's 192 bytes of CPU map/attribute copying are gone: the whole
480-byte map is 30 aligned blocks, and the whole attribute packet is 30 GDMA
blocks in the tail.

## Contracts

* **A transfer starts only while `HDMA5` reads idle** (bit 7 set) and with the
  LCD on. Nothing ever terminates a transfer; completion is polled. Both
  pinned cores and the harness read back the remaining block count with bit 7
  clear while a transfer is active and `$FF` once the last block has landed,
  so the polls are portable.
* **VBK belongs to the transfer for its whole life.** A block writes the VRAM
  bank selected at the moment it lands. The renderer, the simulation yields
  and both interrupt handlers leave VBK alone; only the publication routines
  write it, and only between transfers.
* **HBlank sources are fixed WRAM.** A block reads its source through the CPU's
  memory map, so SVBK selects the WRAM bank, and a simulation yield may have
  bank 2 mapped when a line ends. `DYNAMIC_TILES` (`$C000`) and `VIEW_MAP`
  (`$C600`) are fixed; `MASK_TILES` and `VIEW_ATTRIBUTES` live in bank 1 and
  therefore keep their VBlank GDMA. `check_sable.py` forces bank 2 across a
  whole transfer and requires the hidden bank to hold the exact bytes.
* **Composition with the LCD off never streams.** `enter_world` composes the
  first frame blind and uploads both pages by GDMA as before; `render_view`
  checks LCDC before chaining.
* **The tail is one VBlank.** Its worst case, 32 mask blocks plus 30 attribute
  blocks plus the HUD, OAM and flip, is checked at every budget boundary and
  must finish before line 153.
* **The cached path is unchanged.** A wall-cache hit still publishes masks, HUD
  and OAM in one VBlank without touching the hidden page.

The harness models HBlank DMA (`tools/sm83emu.py`): a block per visible line
at the nominal first mode-0 dot, read through SVBK, written to the bank VBK
selects, with the CPU stall charged to `dma_cycles`. A presentation is safe
only if no transfer is still active at the flip, every HBlank transfer
completed, and the VBlank GDMA shares the flip's frame. A commit event now
reports `hblank_blocks` and `vblank_blocks` separately.

## What is exact and what moved

Every check the project already ran still passes without a hash change:
descriptor arrays, dynamic patterns, view map, attribute packet, published
map/attributes/masks/OAM, the 53 frozen wall-reuse scenes, the folded /
unfolded / reuse-disabled / prepared-disabled variants, the display
comparison, and the frozen independent scenes on pinned SameBoy CGB-0/E and
mGBA.

One capture of the nine-image tour changed: the ninth, `09_exit_approach`, by
six pixels on HUD row 131. They are the helmet portrait's blink, which uses
accepted snapshot ticks 62–63 modulo 64; that update now completes in five LCD
intervals instead of six, so the accepted tick lands on the blink window
differently. No world pixel, sprite or packet differs. v0.10 therefore
carries its own oracle, `games/sable_outpost/playtests/archive/oracles/sable_v10_capture_pixels.json` (retired since for golden snapshots), with the
other eight hashes identical to v0.9, and the v0.9 oracle is retained.

The controller route died once on the faster ROM, in Coolant Spine, standing
in a doorway firing at a Sentinel pressed against a wall corner: the route's
sampled host-side sight test said the shot was clear, the ROM's exact centre
ray clipped the corner, and the Sentinel's contact attacks drained the player.
That is route fragility exposed by a pose the old timing never reached, not
an engine defect; the route now moves one cell when an exchange settles
nothing, and bounds an exchange at contact range by less LCD time.

## Measurements

Host harness, same routes as [the audit](PERFORMANCE_AUDIT_V08.md), same
ROM otherwise:

| Route | v0.9 mean cycles/update | streamed | delta |
|---|---:|---:|---:|
| nine-image coherence tour | 866,119 | 763,741 | **−11.8%** |
| living-world route | 719,567 | 647,849 | **−10.0%** |

`upload_hidden_page` itself falls from 206,941 to 101,201 mean cycles on the
tour: what remains is the alignment wait to the next VBlank, which no
synchronous scheme can remove (overlapped publication, the slim default
since, hands that wait to the VBlank interrupt). The v0.10 sustained
sixty-second results are in [its test report](archive/TEST_REPORT_V10.md).

## What it does not do

* It does not shorten the alignment wait by itself. Overlapped publication
  (the slim default since Phase 5, `docs/PERFORMANCE_PHASE5.md`) does: the
  VBlank interrupt commits this tail while the next frame is already
  casting.
* It does not raise the GDMA time spent in any VBlank. The tail carries 62
  blocks where the staged final VBlank carried 48 blocks plus 64 CPU bytes;
  measured against line 153 it finishes earlier.
* It does not apply to the legacy profile, whose ROM is byte-identical and
  whose experimental foreground/reprojection lanes depend on the staged
  packet.
