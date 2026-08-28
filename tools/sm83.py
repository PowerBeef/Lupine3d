#!/usr/bin/env python3
"""Tiny purpose-built SM83 assembler used by Lupine 3D.

It intentionally implements only the instruction forms the engine uses. The
result is deterministic and removes any external toolchain requirement from the
project's reference build.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REG8 = {"b": 0, "c": 1, "d": 2, "e": 3, "h": 4, "l": 5, "(hl)": 6, "a": 7}
REG16 = {"bc": 0, "de": 1, "hl": 2, "sp": 3}
COND = {None: None, "nz": 0, "z": 1, "nc": 2, "c": 3}

@dataclass
class Fixup:
    offset: int
    label: str
    kind: str  # abs16, rel8, hi8, or lo8
    addend: int = 0

class Assembler:
    def __init__(self, origin: int = 0x0150, *, optimize_high_page: bool = False) -> None:
        self.origin = origin
        self.optimize_high_page = optimize_high_page
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[Fixup] = []
        self.listing: list[tuple[int, bytes, str]] = []

    @property
    def pc(self) -> int:
        return self.origin + len(self.code)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate label: {name}")
        self.labels[name] = self.pc
        self.listing.append((self.pc, b"", f"{name}:"))

    def _emit(self, data: Iterable[int], text: str = "") -> None:
        b = bytes((x & 0xFF for x in data))
        at = self.pc
        self.code.extend(b)
        self.listing.append((at, b, text))

    def db(self, *values: int, text: str = "db") -> None:
        self._emit(values, text)

    def bytes(self, data: bytes | bytearray, text: str = "data") -> None:
        self._emit(data, text)

    def dw(self, value: int, text: str = "dw") -> None:
        self._emit((value & 0xFF, value >> 8), text)

    def dw_label(self, label: str, addend: int = 0, text: str | None = None) -> None:
        off = len(self.code)
        self._emit((0, 0), text or f"dw {label}")
        self.fixups.append(Fixup(off, label, "abs16", addend))

    def align(self, boundary: int, fill: int = 0x00, text: str = "align") -> None:
        if boundary <= 0 or boundary & (boundary - 1):
            raise ValueError("alignment must be a positive power of two")
        padding = (-self.pc) & (boundary - 1)
        if padding:
            self._emit((fill,) * padding, f"{text} {boundary} ({padding} bytes)")

    def db_label_part(self, label: str, part: str, addend: int = 0) -> None:
        if part not in ("hi8", "lo8"):
            raise ValueError(part)
        off = len(self.code)
        self._emit((0,), f"db {part}({label})")
        self.fixups.append(Fixup(off, label, part, addend))

    def nop(self) -> None: self._emit((0x00,), "nop")
    def di(self) -> None: self._emit((0xF3,), "di")
    def ei(self) -> None: self._emit((0xFB,), "ei")
    def halt(self) -> None: self._emit((0x76,), "halt")
    def stop(self) -> None: self._emit((0x10, 0x00), "stop")
    def ret(self, cond: str | None = None) -> None:
        if cond is None: self._emit((0xC9,), "ret")
        else: self._emit((0xC0 + COND[cond] * 8,), f"ret {cond}")
    def reti(self) -> None: self._emit((0xD9,), "reti")

    def push(self, rr: str) -> None:
        op = {"bc":0xC5,"de":0xD5,"hl":0xE5,"af":0xF5}[rr]
        self._emit((op,), f"push {rr}")
    def pop(self, rr: str) -> None:
        op = {"bc":0xC1,"de":0xD1,"hl":0xE1,"af":0xF1}[rr]
        self._emit((op,), f"pop {rr}")

    def ld_r_r(self, dst: str, src: str) -> None:
        self._emit((0x40 + REG8[dst]*8 + REG8[src],), f"ld {dst},{src}")
    def ld_r_n(self, reg: str, value: int) -> None:
        op = {"b":0x06,"c":0x0E,"d":0x16,"e":0x1E,"h":0x26,"l":0x2E,"a":0x3E}[reg]
        self._emit((op, value), f"ld {reg},${value & 0xFF:02X}")
    def ld_r_label_part(self, reg: str, label: str, part: str, addend: int = 0) -> None:
        if part not in ("hi8", "lo8"):
            raise ValueError(part)
        op = {"b":0x06,"c":0x0E,"d":0x16,"e":0x1E,"h":0x26,"l":0x2E,"a":0x3E}[reg]
        off = len(self.code) + 1
        self._emit((op, 0), f"ld {reg},{part}({label})")
        self.fixups.append(Fixup(off, label, part, addend))
    def ld_rr_nn(self, rr: str, value: int) -> None:
        self._emit((0x01 + REG16[rr]*0x10, value & 0xFF, value >> 8), f"ld {rr},${value:04X}")
    def ld_rr_label(self, rr: str, label: str, addend: int = 0) -> None:
        off = len(self.code) + 1
        self._emit((0x01 + REG16[rr]*0x10, 0, 0), f"ld {rr},{label}")
        self.fixups.append(Fixup(off, label, "abs16", addend))

    def ld_mem_rr_a(self, rr: str) -> None:
        op = {"bc":0x02,"de":0x12}[rr]
        self._emit((op,), f"ld ({rr}),a")
    def ld_a_mem_rr(self, rr: str) -> None:
        op = {"bc":0x0A,"de":0x1A}[rr]
        self._emit((op,), f"ld a,({rr})")
    def ldi_hl_a(self) -> None: self._emit((0x22,), "ld (hl+),a")
    def ldi_a_hl(self) -> None: self._emit((0x2A,), "ld a,(hl+)")
    def ldd_hl_a(self) -> None: self._emit((0x32,), "ld (hl-),a")
    def ldd_a_hl(self) -> None: self._emit((0x3A,), "ld a,(hl-)")
    def ld_hl_a(self) -> None: self._emit((0x77,), "ld (hl),a")
    def ld_a_hl(self) -> None: self._emit((0x7E,), "ld a,(hl)")
    def ld_hl_n(self, value: int) -> None: self._emit((0x36, value), f"ld (hl),${value & 0xFF:02X}")

    def ld_abs_a(self, addr: int) -> None:
        # CGB HRAM and I/O live on the $FFxx page.  The immediate LDH form is
        # one byte and one machine cycle smaller than LD (a16),A while having
        # identical semantics for every address on that page.
        if self.optimize_high_page and addr & 0xFF00 == 0xFF00:
            self.ldh_n_a(addr & 0xFF)
            return
        self._emit((0xEA, addr & 0xFF, addr >> 8), f"ld (${addr:04X}),a")
    def ld_a_abs(self, addr: int) -> None:
        if self.optimize_high_page and addr & 0xFF00 == 0xFF00:
            self.ldh_a_n(addr & 0xFF)
            return
        self._emit((0xFA, addr & 0xFF, addr >> 8), f"ld a,(${addr:04X})")
    def ld_abs_sp(self, addr: int) -> None:
        self._emit((0x08, addr & 0xFF, addr >> 8), f"ld (${addr:04X}),sp")
    def ld_sp_hl(self) -> None: self._emit((0xF9,), "ld sp,hl")
    def ldh_n_a(self, n: int) -> None:
        self._emit((0xE0, n), f"ldh ($FF{n & 0xFF:02X}),a")
    def ldh_a_n(self, n: int) -> None:
        self._emit((0xF0, n), f"ldh a,($FF{n & 0xFF:02X})")
    def ldh_c_a(self) -> None: self._emit((0xE2,), "ldh (c),a")
    def ldh_a_c(self) -> None: self._emit((0xF2,), "ldh a,(c)")

    def inc_r(self, reg: str) -> None:
        op = {"b":0x04,"c":0x0C,"d":0x14,"e":0x1C,"h":0x24,"l":0x2C,"(hl)":0x34,"a":0x3C}[reg]
        self._emit((op,), f"inc {reg}")
    def dec_r(self, reg: str) -> None:
        op = {"b":0x05,"c":0x0D,"d":0x15,"e":0x1D,"h":0x25,"l":0x2D,"(hl)":0x35,"a":0x3D}[reg]
        self._emit((op,), f"dec {reg}")
    def inc_rr(self, rr: str) -> None:
        self._emit((0x03 + REG16[rr]*0x10,), f"inc {rr}")
    def dec_rr(self, rr: str) -> None:
        self._emit((0x0B + REG16[rr]*0x10,), f"dec {rr}")
    def add_hl_rr(self, rr: str) -> None:
        self._emit((0x09 + REG16[rr]*0x10,), f"add hl,{rr}")

    def alu_r(self, op: str, reg: str) -> None:
        base = {"add":0x80,"adc":0x88,"sub":0x90,"sbc":0x98,"and":0xA0,"xor":0xA8,"or":0xB0,"cp":0xB8}[op]
        self._emit((base + REG8[reg],), f"{op} a,{reg}" if op not in ("sub","and","xor","or","cp") else f"{op} {reg}")
    def alu_n(self, op: str, value: int) -> None:
        code = {"add":0xC6,"adc":0xCE,"sub":0xD6,"sbc":0xDE,"and":0xE6,"xor":0xEE,"or":0xF6,"cp":0xFE}[op]
        self._emit((code, value), f"{op} ${value & 0xFF:02X}")
    def add_a_r(self, reg: str) -> None: self.alu_r("add", reg)
    def adc_a_r(self, reg: str) -> None: self.alu_r("adc", reg)
    def sub_r(self, reg: str) -> None: self.alu_r("sub", reg)
    def sbc_a_r(self, reg: str) -> None: self.alu_r("sbc", reg)
    def and_r(self, reg: str) -> None: self.alu_r("and", reg)
    def xor_r(self, reg: str) -> None: self.alu_r("xor", reg)
    def or_r(self, reg: str) -> None: self.alu_r("or", reg)
    def cp_r(self, reg: str) -> None: self.alu_r("cp", reg)
    def add_a_n(self, v: int) -> None: self.alu_n("add", v)
    def adc_a_n(self, v: int) -> None: self.alu_n("adc", v)
    def sub_n(self, v: int) -> None: self.alu_n("sub", v)
    def sbc_a_n(self, v: int) -> None: self.alu_n("sbc", v)
    def and_n(self, v: int) -> None: self.alu_n("and", v)
    def xor_n(self, v: int) -> None: self.alu_n("xor", v)
    def or_n(self, v: int) -> None: self.alu_n("or", v)
    def cp_n(self, v: int) -> None: self.alu_n("cp", v)

    def rlca(self) -> None: self._emit((0x07,), "rlca")
    def rrca(self) -> None: self._emit((0x0F,), "rrca")
    def rla(self) -> None: self._emit((0x17,), "rla")
    def rra(self) -> None: self._emit((0x1F,), "rra")
    def cpl(self) -> None: self._emit((0x2F,), "cpl")
    def scf(self) -> None: self._emit((0x37,), "scf")
    def ccf(self) -> None: self._emit((0x3F,), "ccf")
    def cb(self, op: str, reg: str, bit: int | None = None) -> None:
        r = REG8[reg]
        if op in ("rlc","rrc","rl","rr","sla","sra","swap","srl"):
            base = {"rlc":0x00,"rrc":0x08,"rl":0x10,"rr":0x18,"sla":0x20,"sra":0x28,"swap":0x30,"srl":0x38}[op]
            code = base + r
            text = f"{op} {reg}"
        else:
            if bit is None or not 0 <= bit <= 7: raise ValueError("bit index required")
            base = {"bit":0x40,"res":0x80,"set":0xC0}[op]
            code = base + bit*8 + r
            text = f"{op} {bit},{reg}"
        self._emit((0xCB, code), text)

    def jp(self, label: str, cond: str | None = None) -> None:
        op = 0xC3 if cond is None else 0xC2 + COND[cond]*8
        off = len(self.code) + 1
        self._emit((op, 0, 0), f"jp {cond + ',' if cond else ''}{label}")
        self.fixups.append(Fixup(off, label, "abs16"))
    def jp_hl(self) -> None: self._emit((0xE9,), "jp (hl)")
    def jr(self, label: str, cond: str | None = None) -> None:
        op = 0x18 if cond is None else 0x20 + COND[cond]*8
        off = len(self.code) + 1
        self._emit((op, 0), f"jr {cond + ',' if cond else ''}{label}")
        self.fixups.append(Fixup(off, label, "rel8"))
    def call(self, label: str, cond: str | None = None) -> None:
        op = 0xCD if cond is None else 0xC4 + COND[cond]*8
        off = len(self.code) + 1
        self._emit((op, 0, 0), f"call {cond + ',' if cond else ''}{label}")
        self.fixups.append(Fixup(off, label, "abs16"))
    def call_abs(self, address: int) -> None:
        self._emit((0xCD, address & 0xFF, address >> 8), f"call ${address:04X}")

    def resolve(self) -> bytes:
        out = bytearray(self.code)
        for f in self.fixups:
            if f.label not in self.labels:
                raise ValueError(f"undefined label: {f.label}")
            target = self.labels[f.label] + f.addend
            if f.kind == "abs16":
                out[f.offset] = target & 0xFF
                out[f.offset+1] = (target >> 8) & 0xFF
            elif f.kind == "hi8":
                out[f.offset] = (target >> 8) & 0xFF
            elif f.kind == "lo8":
                out[f.offset] = target & 0xFF
            elif f.kind == "rel8":
                operand_addr = self.origin + f.offset
                after = operand_addr + 1
                delta = target - after
                if not -128 <= delta <= 127:
                    raise ValueError(f"JR out of range to {f.label}: {delta}")
                out[f.offset] = delta & 0xFF
            else:
                raise AssertionError(f.kind)
        return bytes(out)

    def write_listing(self, path: Path) -> None:
        resolved = self.resolve()
        lines = []
        for addr, data, text in self.listing:
            if data:
                start = addr - self.origin
                actual = resolved[start:start + len(data)]
            else:
                actual = data
            # Keep large data blocks compact while preserving their address/size.
            if len(actual) > 24:
                head = " ".join(f"{b:02X}" for b in actual[:12])
                tail = " ".join(f"{b:02X}" for b in actual[-4:])
                hexbytes = f"{head} ... {tail} [{len(actual)} bytes]"
            else:
                hexbytes = " ".join(f"{b:02X}" for b in actual)
            lines.append(f"{addr:04X}  {hexbytes:<58} {text}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
