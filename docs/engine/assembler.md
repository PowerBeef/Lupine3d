# The assembler

`tools/sm83.py` is a small, purpose-built SM83 assembler: it implements only
the instruction forms the engine uses, is deterministic, and needs no
external toolchain. The engine's emitters call it directly from Python.

## Using it

```python
from sm83 import Assembler

a = Assembler(origin=0x0150)
a.section("example")
a.label("count_down")            # B = count; clobbers A, B and the flags
a.ld_r_n("a", 0)
a.label("count_down_loop")
a.inc_r("a"); a.dec_r("b"); a.jr("count_down_loop", "nz")
a.ret()
a.label("table"); a.bytes(bytes(range(8)), "a lookup table")
code = a.resolve()               # fixups applied; a.labels maps names to addresses
```

| Method | Emits |
|---|---|
| `label(name)`, `section(name)` | a label at the current address; a named placement section |
| `bytes(data, text)`, `db`, `dw`, `dw_label(name)`, `align(n)` | data, recorded as a data span so static analysis never decodes it |
| `ld_r_r`, `ld_r_n`, `ld_rr_nn`, `ld_rr_label`, `ld_abs_a`, `ld_a_abs`, `ldh_n_a`, `ldh_a_n`, `ldi_a_hl`, `ldi_hl_a`, … | the load forms (`r` a register name, `rr` a pair, `abs` a 16-bit address) |
| `add_a_r`, `sub_n`, `and_n`, `xor_r`, `or_r`, `cp_n`, `inc_r`, `dec_rr`, `add_hl_rr`, … | ALU forms |
| `jp`, `jr`, `call` with an optional condition `"z"`, `"nz"`, `"c"`, `"nc"`; `ret`, `reti`, `jp_hl` | control flow to labels, fixed up at `resolve` |
| `push`, `pop`, `di`, `ei`, `halt`, `cb(...)` | the rest |

Registers are named `"a"`, `"b"`, `"c"`, `"d"`, `"e"`, `"h"`, `"l"` and
`"(hl)"`; pairs `"bc"`, `"de"`, `"hl"`, `"sp"`. `write_listing(path)` writes
the listing every build ships as `lupine3d.lst`.

## Adding an instruction form

1. Add the encoder to `Assembler` in `tools/sm83.py`, following the forms
   around it.
2. Add its execution to `tools/sm83emu.py`, with exact timing and flags.
3. Run the differential conformance test: seeded micro-programs of every
   form the emitter can produce, run in the harness and in pinned SameBoy and
   compared register for register and byte for byte:

   ```sh
   make conformance SAMEBOY_DIR=build/deps/SameBoy
   ```

A form the harness gets wrong would make every other check lie, so this
test is what makes the rest trustworthy.
