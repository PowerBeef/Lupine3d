#!/usr/bin/env python3
"""Differential CPU conformance for the host harness against pinned SameBoy.

`tools/sm83emu.py` executes only the instruction forms `tools/sm83.py` emits,
so the public conformance suites (mooneye, blargg, cgb-acid2) cannot run on it
and are not claimed. What can be checked, exactly, is that every form the
emitter can produce computes the same registers, flags and memory in the
harness as in an independent core. This tool assembles seeded random
micro-programs from the assembler's own opcode vocabulary, runs each in the
harness and in SameBoy (`tools/sameboy_dump.c`), and compares the final
A F B C D E H L SP and a 512-byte WRAM scratch window byte for byte.

Programs re-seed every pointer register just before it addresses memory, so
all loads and stores stay inside deterministic scratch (WRAM `$C100-$C2FF`,
HRAM `$FF80-$FFFE`); nothing reads an I/O register, and interrupts stay
disabled (IE = 0), so the comparison is about the CPU alone. A mismatch is a
harness defect (or an unmodelled hardware quirk) and fails the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sm83 import Assembler  # noqa: E402
from sm83emu import CGB  # noqa: E402

PINNED_CORE = "213a12ce93d66b105a113debd9396306066a7cfc"
SCRATCH = 0xC100          # ..$C2FF: the memory the programs may touch
DUMP = 0xC000             # A F B C D E H L SPlo SPhi at $C000..$C009, done flag at $C0FF
DONE = 0xC0FF
STACK = 0xDFF0
REGS = ("a", "b", "c", "d", "e", "h", "l")
PAIRS = ("bc", "de", "hl")
ALU = ("add", "adc", "sub", "sbc", "and", "xor", "or", "cp")
SHIFTS = ("rlc", "rrc", "rl", "rr", "sla", "sra", "swap", "srl")
CONDS = ("nz", "z", "nc", "c")


def scratch(rng: random.Random) -> int:
    return SCRATCH + rng.randrange(0x1F0)


def emit_program(a: Assembler, rng: random.Random, ops: int) -> None:
    """One micro-program: clear scratch, seed registers, `ops` random forms, dump."""
    a.label("reset")
    a.di(); a.ld_rr_nn("sp", STACK)
    a.xor_r("a"); a.ldh_n_a(0xFF); a.ldh_n_a(0x0F)          # IE = 0, IF = 0
    a.ld_rr_nn("hl", DUMP); a.ld_rr_nn("bc", 0x0300)         # clear $C000-$C2FF
    a.label("clear"); a.xor_r("a"); a.ldi_hl_a(); a.dec_rr("bc"); a.ld_r_r("a", "b"); a.or_r("c"); a.jr("clear", "nz")
    a.ld_rr_nn("hl", 0xFF80); a.ld_r_n("b", 0x7E)            # clear HRAM $FF80-$FFFD
    a.label("clear_hram"); a.xor_r("a"); a.ldi_hl_a(); a.dec_r("b"); a.jr("clear_hram", "nz")
    # Seed A and F together through the stack, then the other registers.
    a.ld_rr_nn("bc", (rng.randrange(256) << 8) | (rng.randrange(16) << 4)); a.push("bc"); a.pop("af")
    for reg in ("b", "c", "d", "e"):
        a.ld_r_n(reg, rng.randrange(256))
    a.ld_rr_nn("hl", scratch(rng))
    skip = 0
    for _ in range(ops):
        form = rng.choice(FORMS)
        skip = form(a, rng, skip)
    # Dump. Register moves and absolute stores leave the flags alone, so F is
    # read last, through the stack, once every other register is on record.
    a.ld_abs_a(DUMP)
    for offset, reg in ((2, "b"), (3, "c"), (4, "d"), (5, "e"), (6, "h"), (7, "l")):
        a.ld_r_r("a", reg); a.ld_abs_a(DUMP + offset)
    a.push("af"); a.pop("bc"); a.ld_r_r("a", "c"); a.ld_abs_a(DUMP + 1)
    a.ld_abs_sp(DUMP + 8)
    a.ld_r_n("a", 0xA5); a.ld_abs_a(DONE)
    a.label("halt_loop"); a.jr("halt_loop")
    a.label("sub_ret"); a.ret()
    a.label("sub_ret_cc"); a.ret("z"); a.inc_r("a"); a.ret("nc"); a.dec_r("a"); a.ret()
    a.label("sub_reti"); a.reti()


# ----- instruction forms ----------------------------------------------------
# Each form appends one or a few instructions and returns the running label
# counter (for forward branches). B and C are dumped from the pushed AF copy
# path above, so every form is free to clobber any register but SP.

def f_ld_r_r(a, rng, k):
    a.ld_r_r(rng.choice(REGS), rng.choice(REGS)); return k

def f_ld_r_n(a, rng, k):
    a.ld_r_n(rng.choice(REGS), rng.randrange(256)); return k

def f_ld_rr_nn(a, rng, k):
    a.ld_rr_nn(rng.choice(PAIRS), rng.randrange(0x10000)); return k

def f_hl_memory(a, rng, k):
    a.ld_rr_nn("hl", scratch(rng))
    choice = rng.randrange(12)
    if choice == 0: a.ld_r_r(rng.choice(REGS), "(hl)")
    elif choice == 1: a.ld_r_r("(hl)", rng.choice(REGS))
    elif choice == 2: a.ld_hl_n(rng.randrange(256))
    elif choice == 3: a.inc_r("(hl)")
    elif choice == 4: a.dec_r("(hl)")
    elif choice == 5: a.alu_r(rng.choice(ALU), "(hl)")
    elif choice == 6: a.cb(rng.choice(SHIFTS), "(hl)")
    elif choice == 7: a.cb(rng.choice(("bit", "res", "set")), "(hl)", rng.randrange(8))
    elif choice == 8: a.ldi_hl_a(); a.ldi_a_hl()
    elif choice == 9: a.ldd_hl_a(); a.ldd_a_hl()
    elif choice == 10: a.ldi_a_hl(); a.ldd_hl_a()
    else: a.ld_hl_a(); a.ld_a_hl()
    return k

def f_pair_memory(a, rng, k):
    pair = rng.choice(("bc", "de"))
    a.ld_rr_nn(pair, scratch(rng))
    if rng.randrange(2): a.ld_mem_rr_a(pair)
    else: a.ld_a_mem_rr(pair)
    return k

def f_abs_memory(a, rng, k):
    if rng.randrange(2): a.ld_abs_a(scratch(rng))
    else: a.ld_a_abs(scratch(rng))
    return k

def f_hram(a, rng, k):
    n = 0x80 + rng.randrange(0x7E)
    choice = rng.randrange(4)
    if choice == 0: a.ldh_n_a(n)
    elif choice == 1: a.ldh_a_n(n)
    elif choice == 2: a.ld_r_n("c", n); a.ldh_c_a()
    else: a.ld_r_n("c", n); a.ldh_a_c()
    return k

def f_inc_dec(a, rng, k):
    if rng.randrange(2): a.inc_r(rng.choice(REGS))
    else: a.dec_r(rng.choice(REGS))
    return k

def f_inc_dec_rr(a, rng, k):
    if rng.randrange(2): a.inc_rr(rng.choice(PAIRS))
    else: a.dec_rr(rng.choice(PAIRS))
    return k

def f_add_hl(a, rng, k):
    a.add_hl_rr(rng.choice(PAIRS + ("sp",))); return k

def f_alu(a, rng, k):
    op = rng.choice(ALU)
    if rng.randrange(2): a.alu_r(op, rng.choice(REGS))
    else: a.alu_n(op, rng.randrange(256))
    return k

def f_rotates(a, rng, k):
    rng.choice((a.rlca, a.rrca, a.rla, a.rra, a.cpl, a.scf, a.ccf))(); return k

def f_cb(a, rng, k):
    reg = rng.choice(REGS)
    if rng.randrange(2): a.cb(rng.choice(SHIFTS), reg)
    else: a.cb(rng.choice(("bit", "res", "set")), reg, rng.randrange(8))
    return k

def f_push_pop(a, rng, k):
    a.push(rng.choice(("bc", "de", "hl", "af"))); a.pop(rng.choice(("bc", "de", "hl", "af"))); return k

def f_branch(a, rng, k):
    label = f"skip_{k}"; cond = rng.choice(CONDS)
    if rng.randrange(2): a.jr(label, cond)
    else: a.jp(label, cond)
    a.inc_r(rng.choice(REGS))   # skipped or not, depending on the flag
    a.label(label)
    return k + 1

def f_call(a, rng, k):
    target = rng.choice(("sub_ret", "sub_ret_cc", "sub_reti"))
    if rng.randrange(2): a.call(target)
    else: a.call(target, rng.choice(CONDS))
    return k

def f_jp_hl(a, rng, k):
    label = f"land_{k}"
    a.ld_rr_label("hl", label); a.jp_hl(); a.label(label)
    return k + 1

def f_sp_forms(a, rng, k):
    a.ld_rr_nn("hl", STACK); a.ld_sp_hl(); a.ld_abs_sp(scratch(rng) & 0xFFFE); return k

FORMS = ([f_ld_r_r] * 6 + [f_ld_r_n] * 4 + [f_ld_rr_nn] * 2 + [f_hl_memory] * 6 + [f_pair_memory] * 2
         + [f_abs_memory] * 2 + [f_hram] * 2 + [f_inc_dec] * 4 + [f_inc_dec_rr] * 2 + [f_add_hl] * 2
         + [f_alu] * 8 + [f_rotates] * 3 + [f_cb] * 5 + [f_push_pop] * 2 + [f_branch] * 3 + [f_call] * 2
         + [f_jp_hl] + [f_sp_forms])


def make_micro_rom(seed: int, ops: int) -> tuple[bytes, dict[str, int]]:
    a = Assembler(origin=0x0150)
    emit_program(a, random.Random(seed), ops)
    code = a.resolve()
    rom = bytearray([0xFF] * 0x8000)
    rom[0x0100:0x0104] = bytes((0x00, 0xC3, 0x50, 0x01))
    from build_rom import NINTENDO_LOGO
    rom[0x0104:0x0134] = NINTENDO_LOGO
    rom[0x0134:0x0143] = b"CONFORM".ljust(15, b"\0")
    rom[0x0143] = 0xC0; rom[0x0147] = 0x00; rom[0x0148] = 0x00; rom[0x0149] = 0x00; rom[0x014A] = 1; rom[0x014B] = 0x33
    rom[0x014D] = (-sum(rom[0x0134:0x014D]) - 0x19) & 0xFF
    if 0x0150 + len(code) > 0x4000:
        raise ValueError("micro-program does not fit the fixed bank")
    rom[0x0150:0x0150 + len(code)] = code
    # Interrupt vectors, in case IME is ever set by reti: return at once.
    for vector in (0x40, 0x48, 0x50, 0x58, 0x60):
        rom[vector] = 0xD9
    return bytes(rom), dict(a.labels)


def run_harness(rom: bytes, labels: dict[str, int]) -> bytes:
    cgb = CGB(rom, labels)
    cgb.run(until_pc=labels["halt_loop"], max_steps=2_000_000)
    return bytes(cgb.read8(DUMP + i) for i in range(0x300))


def build_dump_adapter(core: Path) -> Path:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=core, text=True).strip()
    if revision != PINNED_CORE:
        raise SystemExit(f"expected pinned SameBoy {PINNED_CORE}, got {revision}")
    executable = ROOT / "build" / "sameboy_dump"
    executable.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cc", f"-I{core}", str(ROOT / "tools/sameboy_dump.c"),
                    str(core / "build/lib/libsameboy.a"), "-lm", "-ldl", "-o", str(executable)], check=True)
    return executable


def run_core(executable: Path, rom_path: Path, out_path: Path, model: str) -> tuple[bytes, dict]:
    result = subprocess.run([str(executable), str(rom_path), str(out_path), model], text=True, capture_output=True)
    status = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {"done": False}
    if not status.get("done"):
        raise RuntimeError(f"SameBoy did not finish {rom_path.name}: {status} {result.stderr}")
    return out_path.read_bytes(), status


FIELDS = ("A", "F", "B", "C", "D", "E", "H", "L", "SP_lo", "SP_hi")


def describe(host: bytes, core: bytes) -> list[str]:
    differences = []
    for index, name in enumerate(FIELDS):
        if host[index] != core[index]:
            differences.append(f"{name}: harness {host[index]:02X} core {core[index]:02X}")
    for offset in range(SCRATCH - DUMP, 0x300):
        if host[offset] != core[offset]:
            differences.append(f"${DUMP + offset:04X}: harness {host[offset]:02X} core {core[offset]:02X}")
            if len(differences) > 12:
                differences.append("..."); break
    return differences


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--core", type=Path, help="pinned SameBoy checkout with build/lib/libsameboy.a")
    p.add_argument("--programs", type=int, default=64)
    p.add_argument("--ops", type=int, default=240)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--model", default="205", help="SameBoy model hex (205 CGB-E, 200 CGB-0)")
    p.add_argument("--output-dir", type=Path, default=ROOT / "build" / "conformance")
    p.add_argument("--generate-only", action="store_true", help="write the micro-ROMs and harness dumps without a core")
    args = p.parse_args()
    out = args.output_dir; out.mkdir(parents=True, exist_ok=True)
    executable = None if args.generate_only else build_dump_adapter(args.core.resolve()) if args.core else None
    if executable is None and not args.generate_only:
        raise SystemExit("--core is required (or --generate-only)")
    rows, mismatches = [], 0
    for index in range(args.programs):
        seed = args.seed * 100_003 + index
        rom, labels = make_micro_rom(seed, args.ops)
        rom_path = out / f"program_{index:03d}.gb"; rom_path.write_bytes(rom)
        host = run_harness(rom, labels)
        (out / f"program_{index:03d}.harness.bin").write_bytes(host)
        row = {"program": index, "seed": seed, "rom_sha256": hashlib.sha256(rom).hexdigest(),
               "instructions": len(rom[0x150:0x4000].rstrip(b"\xFF")), "harness_state": host[:10].hex()}
        if executable is not None:
            core, status = run_core(executable, rom_path, out / f"program_{index:03d}.sameboy.bin", args.model)
            differences = describe(host, core)
            row.update(core_state=core[:10].hex(), core_frames=status["frames"], match=not differences, differences=differences)
            mismatches += bool(differences)
            print(f"program {index:03d}: {'match' if not differences else 'MISMATCH ' + '; '.join(differences[:3])}", flush=True)
        rows.append(row)
    report = {"schema": "lupine3d.harness-conformance.v1", "core": "SameBoy", "core_commit": PINNED_CORE if executable else None,
              "model": args.model, "programs": args.programs, "ops_per_program": args.ops, "seed": args.seed,
              "scope": "registers, flags, WRAM $C100-$C2FF after every emitted instruction form; no timing, no I/O, IME off",
              "mismatches": mismatches, "passed": executable is not None and mismatches == 0, "rows": rows}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    if executable is not None and mismatches:
        raise SystemExit(f"{mismatches} micro-program(s) diverge between the harness and SameBoy")


if __name__ == "__main__":
    main()
