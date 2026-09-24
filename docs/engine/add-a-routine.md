# Add a routine

An engine routine is Python that emits SM83 code through the assembler
(`tools/sm83.py`) into a section of the ROM.

## 1. Emit it where its area lives

Write an `emit_…(a)` function in the module that owns the area
([engine development](README.md)), and call it from the section list in
`tools/build_rom.py`. Document, in its docstring or at its label:

- the registers and flags it clobbers, and what it expects in each;
- the stack it uses;
- which ROM bank must be mapped, and whether it switches banks;
- any overflow or range its correctness relies on.

```python
def emit_heal_player(a) -> None:
    """`heal_player`: add A to PLAYER_HEALTH, saturating at 99.
    Clobbers A, B and the flags; no stack; any ROM bank."""
    a.label("heal_player")
    a.ld_r_r("b", "a"); a.ld_a_abs(PLAYER_HEALTH); a.add_a_r("b")
    a.jr("heal_player_cap", "c"); a.cp_n(100); a.jr("heal_player_store", "c")
    a.label("heal_player_cap"); a.ld_r_n("a", 99)
    a.label("heal_player_store"); a.ld_abs_a(PLAYER_HEALTH); a.ret()
```

## 2. Place it

Placement is a build decision, proven by `bank_safety.py` against the
emitted image:

- Code that writes the bank register (`$2000`), or that an interrupt can
  reach, is **resident**: it goes in `resident_sections` and lands in bank 0.
  Bank 0 is nearly full ([limits](../reference/limits.md)); the build names
  what grew when it overflows.
- Code that is bank-neutral (it neither switches banks nor runs while a
  foreign bank is mapped, and no interrupt reaches it) goes in
  `cold_sections` and lands above `$4000` in bank 1, the engine's resting
  bank.
- A banked lookup (switch, read, switch back) restores ROM bank 1
  **unconditionally**; a conditional restore leaves a window no static
  reading can prove closed.

The linker refuses a build that breaks the 3,000-byte resident reserve, and
`bank_safety.py` one that breaks the bank rule.

## 3. Keep the host model in step

If the routine changes what the console draws or simulates, the host model
changes with it in the same commit: `reference.py` for geometry,
`texture_reference.py` for walls, or the module's own model. Tests compare
the ROM with the model; neither is trusted alone.

## 4. A new instruction form

The assembler implements only the forms the engine uses. A new one needs
the encoder in `tools/sm83.py`, its execution in `tools/sm83emu.py`, and a
run of the harness against SameBoy ([the assembler](assembler.md)):

```sh
make conformance SAMEBOY_DIR=build/deps/SameBoy
```

## 5. Prove it

```sh
make test playtest playtest-world
python tools/rom_identity.py compare --base origin/main   # if nothing should have changed
```

and the checks [AGENTS.md](../../AGENTS.md), "Verification and evidence",
lists for the area: both pinned cores for anything touching banks,
interrupts, DMA or publication; the variants and wall-reuse lanes for
geometry and composition.
