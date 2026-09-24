# Game Boy Color hardware primer

What the engine has to work with, and the rules it is built around. The
numbers are the ones the emitter, the host harness and the pinned cores agree
on; where the engine treats a rule as an invariant, the page that owns the
check is named.

## CPU

- **SM83** core (a Z80/8080 hybrid: 8-bit ALU, 16-bit `HL`/`BC`/`DE`/`SP`,
  no index registers, no 16-bit multiply). The engine runs in **double
  speed** (KEY1 + STOP at boot) at 8,388,608 Hz, so one LCD frame is
  **140,448 T-cycles**. CPU T-cycles are the engine's timing unit; the LCD
  does not speed up with the CPU.
- Timing is exact and public: every emitted instruction form is listed by
  `tools/sm83.py`, and `make conformance` compares the host harness's model of
  each form with SameBoy (`tools/harness_conformance.py`).
- There is no hardware divide or multiply. Products and quotients come from
  ROM tables (`docs/archive/RUNTIME_PERFORMANCE.md`), which is why the
  cartridge is 4 MiB.
- Interrupts: the engine uses **VBlank** and one **STAT** interrupt (LYC at
  the HUD boundary, line 120 on slim). Nothing else is enabled. An interrupt
  can land between a bank switch and the read it protects, which is why the
  music tick never switches banks (`AGENTS.md`, "Sound contracts").

## Memory map (the console's side)

| Range | What | Engine use |
|---|---|---|
| `$0000-$3FFF` | ROM bank 0, fixed | resident code: everything that writes a bank register or that an interrupt reaches |
| `$4000-$7FFF` | ROM bank 1..255, switchable (MBC5) | bank 1 holds cold engine sections; other banks hold tables, levels, art, songs |
| `$8000-$9FFF` | VRAM, two banks (VBK) | patterns and maps; the hidden bank is written while the other is displayed |
| `$A000-$BFFF` | cartridge RAM | **none**: there is no save RAM, progress is a continue code |
| `$C000-$CFFF` | fixed WRAM | HBlank DMA sources, the stack, queues, ring buffers |
| `$D000-$DFFF` | WRAM bank 1..7 (SVBK) | 1 render snapshot, 2 live world, 4 foreground, 5 music |
| `$FE00-$FE9F` | OAM | forty objects, written by OAM DMA from a shadow |
| `$FF80-$FFFE` | HRAM | the hot render and ISR scalars (full; new scalars alias old ones) |

The **MBC5 rule** the engine proves with `tools/lupine3d_v4/bank_safety.py`:
no code above `$4000` runs while a foreign bank is mapped, every bank-register
write is below `$4000`, no section falls through into the next, and every
banked lookup restores bank 1 unconditionally. The generated
[memory map](../reference/memory-map.md) lists what the engine put where.

## PPU

- 160×144 pixels, 154 lines of 456 dots; lines 144-153 are VBlank. Per visible
  line: mode 2 (OAM scan, 80 dots), mode 3 (drawing, 172 dots plus penalties
  for scroll and objects), mode 0 (HBlank, the remainder).
- Background: a 32×32 map of 8×8 tiles; two 256-pattern banks; per-tile
  attributes give palette, VRAM bank, X-flip, Y-flip and priority. The engine
  draws the lower half of every wall by **Y-flipping** the upper half's
  patterns with a palette whose colour 0 is the floor (`docs/explanation/architecture.md`,
  "Display and geometry").
- Objects: 40, ten per line, 8×16 in this engine. The engine admits sixteen
  world objects and four per scanline and keeps ten for the weapon and UI.
- Palettes: eight background and eight object palettes of four RGB555 colours.
  The palette registers cannot be written during mode 3; the engine writes
  them with the LCD off. All sixteen are allocated (`docs/reference/asset-formats.md`).
- VRAM is inaccessible in mode 3 and OAM in modes 2-3. The engine never writes
  either directly during a frame: every VRAM byte moves by DMA.

## DMA

- **General DMA** (GDMA) copies 16-byte blocks with the CPU halted, at about
  8 µs a block in either speed. It is used with the LCD off (boot, screens,
  weapon swaps) and for the VBlank tail of a publication (at most 62 blocks).
- **HBlank DMA** (HDMA) copies one block in each visible line's HBlank and
  none during VBlank. The engine streams the hidden bank's patterns and map
  this way while it is still composing (`docs/explanation/streamed-publication.md`). The
  rules it keeps: start only while `HDMA5` reads idle and the LCD is on, never
  terminate a transfer, never write VBK while one is active, and source only
  from fixed WRAM because a block reads through SVBK and a yield may have the
  live-world bank mapped.
- **OAM DMA** copies the 160-byte shadow from a page-aligned buffer; its wait
  loop runs from HRAM.
- The harness models all three, including HBlank DMA continuing across frames,
  and `validate_frame` refuses a frame whose transfers break any rule above.

## Sound

Four channels. CH1 belongs to sound effects (one-shot register presets), the
sequencer owns CH2-CH4 and is ticked from the STAT boundary or a full-screen
mode's loop, never from VBlank, because a staged publication ends about one
scanline before the VBlank deadline.

## What the engine does not use

No cartridge RAM, no timers, no serial, no window layer, no mid-frame palette
rewrites (rejected for horizontal banding, recorded in the manifest), no
boot ROM (a synthetic bootstrap in the adapters). Hardware testing is not
available to the project; qualification is the host harness plus pinned
SameBoy CGB-0/E and mGBA cores (`docs/explanation/verification.md`).

## Further reading

Pan Docs (gbdev.io/pandocs) is the reference for the registers and timings
above. The engine's harness conformance lane and the core witnesses are the
project's own evidence that its reading of them is right.
