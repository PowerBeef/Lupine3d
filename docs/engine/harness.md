# The harness

`tools/sm83emu.py` is a deterministic Game Boy Color model: the SM83 CPU
with exact timing, the PPU's modes and scanlines, HBlank and general DMA,
OAM DMA, the joypad and the MBC5. Every playtest, the controller route and
most checks run ROMs in it; two pinned emulator cores keep it honest.

## Running a ROM

```python
import build_rom as br
from sm83emu import CGB, parse_symbols, run_to_world

rom = (br.GAME_BUILD / "lupine3d.gb").read_bytes()
cgb = CGB(rom, parse_symbols(br.GAME_BUILD / "lupine3d.sym"))
run_to_world(cgb)                                  # holds START through the title
cgb.button_provider = lambda *_: 0x04              # hold Up
cgb.run(until_presentations=cgb.presentations + 10, max_steps=30_000_000)
cgb.render_screen().save("build/ten_frames_later.png")
```

| API | Does |
|---|---|
| `CGB(rom, symbols)` | a machine at power-on |
| `run_to_world(cgb)` | advances through the title to the world loop, pressing START |
| `run(until_presentations=…, until_pc=…, until_swaps=…, max_steps=…)` | runs until a condition; raises at the step limit |
| `step()` | one instruction |
| `button_provider` | a function returning the pad byte (right 1, left 2, up 4, down 8, A 16, B 32, select 64, start 128) |
| `read8`, `read16`, `write8` | memory as the CPU sees it |
| `live_wramx[bank]` | WRAM banks directly (the live world is in bank 2) |
| `call_subroutine(label)` | run one ROM routine to its `ret`, for differential probes |
| `diagnostic_barrier()` | bring an overlapped-publication machine to the top of the main loop before a host write |
| `render_screen()` | the picture the LCD shows, from VRAM, OAM and palettes |
| `presentations`, `frame_count`, `cycles` | published frames, LCD frames, T-cycles |

Every tool that imports `build_rom` builds the configuration its flags name,
so run a harness script in a process whose `LUPINE3D_*` flags (and
`LUPINE3D_GAME`) match the ROM it loads.

## Checking frames

`playtest.validate_frame(cgb)` checks the frame just published against the
host model (descriptors, patterns, maps, masks, DMA timing and the OBJ
budget) and raises naming the check that failed. Writes to a running machine
go through `playtest.set_test_world_byte`, after `diagnostic_barrier`, so a
diagnostic pose never races the publication in flight
([verification](../explanation/verification.md)).

## Against the cores

`tools/sameboy_smoke.c` and `tools/mgba_smoke.c` are adapters that link the
pinned cores' libraries and replay a controller script with per-frame
safety checks; `tools/independent_witnesses.py` compares frozen scenes
between the harness and both cores; `tools/harness_conformance.py` compares
the CPU instruction by instruction with SameBoy. [Development](development.md)
says how to build the cores.
