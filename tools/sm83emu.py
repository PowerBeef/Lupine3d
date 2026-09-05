#!/usr/bin/env python3
"""Small deterministic CGB validation harness for Lupine 3D.

This is not intended to replace a cycle-accurate public emulator. It executes
all SM83 opcodes emitted by the project, models the CGB memory regions used by
the engine, performs General Purpose VRAM DMA, advances LY, scans joypad input,
and renders BG/OBJ output to PNG. Its purpose is repeatable CI smoke testing.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

Z = 0x80
N = 0x40
H = 0x20
C = 0x10

P1 = 0xFF00
IF = 0xFF0F
LCDC = 0xFF40
STAT = 0xFF41
SCX = 0xFF43
LY = 0xFF44
LYC = 0xFF45
DMA = 0xFF46
KEY1 = 0xFF4D
VBK = 0xFF4F
HDMA1 = 0xFF51
HDMA2 = 0xFF52
HDMA3 = 0xFF53
HDMA4 = 0xFF54
HDMA5 = 0xFF55
BGPI = 0xFF68
BGPD = 0xFF69
OBPI = 0xFF6A
OBPD = 0xFF6B
SVBK = 0xFF70


class CPUError(RuntimeError):
    pass


@dataclass
class Snapshot:
    steps: int
    cycles: int
    frames: int
    swaps: int
    pc: int
    player_x: int
    player_y: int
    angle: int


class CGB:
    def __init__(self, rom: bytes, symbols: dict[str, int] | None = None) -> None:
        if len(rom) < 0x8000 or len(rom) % 0x4000:
            raise ValueError("harness expects a ROM made of complete 16 KiB banks")
        self.rom = rom
        self.rom_bank = 1
        self.symbols = symbols or {}
        self.vram = [bytearray(0x2000), bytearray(0x2000)]
        self.wram0 = bytearray(0x1000)
        self.wramx = [bytearray(0x1000) for _ in range(8)]
        self.oam = bytearray(0xA0)
        self.io = bytearray(0x80)
        self.hram = bytearray(0x7F)
        self.ie = 0
        self.bg_palette = bytearray(64)
        self.obj_palette = bytearray(64)

        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.sp = 0xFFFE
        self.pc = 0x0100
        self.ime = False
        self._ime_enable_delay = 0
        self.halted = False
        self.double_speed = False
        self.cycles = 0
        self.steps = 0
        self.ppu_dots = 0
        self.ly = 0
        self.frame_count = 0
        self.page_swaps = 0
        self.main_iterations = 0
        self.buttons = 0  # active-high standard bit layout
        self.button_provider: Callable[[int, int], int] | None = None
        self.extra_cycles = 0
        self.gdma_events: list[dict[str, int | bool]] = []
        self.commit_events: list[dict[str, object]] = []
        self.gdma_vblank_violations = 0
        self.interrupt_events: list[dict[str, int]] = []
        self.scx_events: list[dict[str, int]] = []
        self.raster_lcdc: dict[int, tuple[int, int, int]] = {}
        self._pending_commit_event_indexes: list[int] = []
        self.last_lcdc = 0x91
        self.io[LCDC & 0x7F] = 0x91
        self.io[P1 & 0x7F] = 0xCF
        self.io[KEY1 & 0x7F] = 0x00
        self.io[SVBK & 0x7F] = 0x01
        self.breakpoints: dict[int, Callable[["CGB"], None]] = {}
        if "main_loop" in self.symbols:
            self.breakpoints[self.symbols["main_loop"]] = self._main_loop_breakpoint

    # ----- register pairs -------------------------------------------------
    @property
    def af(self) -> int: return (self.a << 8) | self.f
    @af.setter
    def af(self, value: int) -> None: self.a = (value >> 8) & 0xFF; self.f = value & 0xF0
    @property
    def bc(self) -> int: return (self.b << 8) | self.c
    @bc.setter
    def bc(self, value: int) -> None: self.b = (value >> 8) & 0xFF; self.c = value & 0xFF
    @property
    def de(self) -> int: return (self.d << 8) | self.e
    @de.setter
    def de(self, value: int) -> None: self.d = (value >> 8) & 0xFF; self.e = value & 0xFF
    @property
    def hl(self) -> int: return (self.h << 8) | self.l
    @hl.setter
    def hl(self, value: int) -> None: self.h = (value >> 8) & 0xFF; self.l = value & 0xFF

    def _main_loop_breakpoint(self, _cpu: "CGB") -> None:
        self.main_iterations += 1
        if self.button_provider:
            self.buttons = self.button_provider(self.main_iterations, self.page_swaps) & 0xFF

    # ----- memory ---------------------------------------------------------
    def read8(self, addr: int) -> int:
        addr &= 0xFFFF
        if addr < 0x4000:
            return self.rom[addr]
        if addr < 0x8000:
            offset = self.rom_bank * 0x4000 + (addr - 0x4000)
            return self.rom[offset] if offset < len(self.rom) else 0xFF
        if addr < 0xA000:
            return self.vram[self.io[VBK & 0x7F] & 1][addr - 0x8000]
        if addr < 0xC000:
            return 0xFF
        if addr < 0xD000:
            return self.wram0[addr - 0xC000]
        if addr < 0xE000:
            bank = self.io[SVBK & 0x7F] & 7
            if bank == 0: bank = 1
            return self.wramx[bank][addr - 0xD000]
        if addr < 0xF000:
            return self.wram0[addr - 0xE000]
        if addr < 0xFE00:
            bank = self.io[SVBK & 0x7F] & 7
            if bank == 0: bank = 1
            return self.wramx[bank][addr - 0xF000]
        if addr < 0xFEA0:
            return self.oam[addr - 0xFE00]
        if addr < 0xFF00:
            return 0xFF
        if addr == P1:
            return self._read_p1()
        if addr == LY:
            return self.ly
        if addr < 0xFF80:
            return self.io[addr - 0xFF00]
        if addr < 0xFFFF:
            return self.hram[addr - 0xFF80]
        return self.ie

    def write8(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        value &= 0xFF
        if addr < 0x8000:
            # MBC5's nine-bit ROM bank register.  ROM-only 32 KiB images used
            # by the frozen regression oracle continue to ignore this range.
            if len(self.rom) > 0x8000:
                if 0x2000 <= addr < 0x3000:
                    self.rom_bank = (self.rom_bank & 0x100) | value
                elif 0x3000 <= addr < 0x4000:
                    self.rom_bank = (self.rom_bank & 0x0FF) | ((value & 1) << 8)
            return
        if addr < 0xA000:
            self.vram[self.io[VBK & 0x7F] & 1][addr - 0x8000] = value
            return
        if addr < 0xC000:
            return
        if addr < 0xD000:
            self.wram0[addr - 0xC000] = value
            return
        if addr < 0xE000:
            bank = self.io[SVBK & 0x7F] & 7
            if bank == 0: bank = 1
            self.wramx[bank][addr - 0xD000] = value
            return
        if addr < 0xF000:
            self.wram0[addr - 0xE000] = value
            return
        if addr < 0xFE00:
            bank = self.io[SVBK & 0x7F] & 7
            if bank == 0: bank = 1
            self.wramx[bank][addr - 0xF000] = value
            return
        if addr < 0xFEA0:
            self.oam[addr - 0xFE00] = value
            return
        if addr < 0xFF00:
            return
        if addr == P1:
            self.io[0] = (self.io[0] & 0xCF) | (value & 0x30)
            return
        if addr == LY:
            self.ly = 0
            self.ppu_dots = 0
            return
        if addr == DMA:
            self.io[DMA & 0x7F] = value
            source = value << 8
            for index in range(0xA0):
                self.oam[index] = self.read8(source + index)
            return
        if addr == SCX:
            self.io[SCX & 0x7F] = value
            self.scx_events.append({"value": value, "frame": self.frame_count, "ly": self.ly})
            return
        if addr == LCDC:
            old = self.io[LCDC & 0x7F]
            self.io[LCDC & 0x7F] = value
            if old & value & 0x80 and self.ly < 144 and (old ^ value) & 0x10:
                self.raster_lcdc[self.ly] = (0x10, value & 0x10, old & 0x10)
            if not (value & 0x80):
                self.raster_lcdc.clear()
                self.ly = 0
                self.ppu_dots = 0
                self._pending_commit_event_indexes.clear()
            elif not (old & 0x80):
                self.ly = 0
                self.ppu_dots = 0
                # Initial uploads happen while the LCD is disabled and are not
                # visual-frame commits. Begin tracking only after LCD enable.
                self._pending_commit_event_indexes.clear()
            elif (old ^ value) & 0x08:
                events = [self.gdma_events[i] for i in self._pending_commit_event_indexes]
                blocks = sum(int(event["blocks"]) for event in events)
                same_frame = bool(events) and all(int(event["frame"]) == int(events[0]["frame"]) for event in events)
                vblank_safe = bool(events) and all(bool(event["vblank_safe_complete"]) for event in events)
                vblank_safe = vblank_safe and self.frame_count == int(events[-1]["frame"]) and self.ly >= 144
                self.commit_events.append({
                    "swap": self.page_swaps + 1,
                    "displayed_map": 1 if value & 0x08 else 0,
                    "frame": self.frame_count,
                    "ly": self.ly,
                    "blocks": blocks,
                    "event_count": len(events),
                    "vblank_safe": vblank_safe,
                    "staged": not same_frame,
                    "events": tuple(events),
                })
                self._pending_commit_event_indexes.clear()
                self.page_swaps += 1
            self.last_lcdc = value
            return
        if addr == BGPD:
            index = self.io[BGPI & 0x7F] & 0x3F
            self.bg_palette[index] = value
            if self.io[BGPI & 0x7F] & 0x80:
                self.io[BGPI & 0x7F] = 0x80 | ((index + 1) & 0x3F)
            return
        if addr == OBPD:
            index = self.io[OBPI & 0x7F] & 0x3F
            self.obj_palette[index] = value
            if self.io[OBPI & 0x7F] & 0x80:
                self.io[OBPI & 0x7F] = 0x80 | ((index + 1) & 0x3F)
            return
        if addr < 0xFF80:
            self.io[addr - 0xFF00] = value
            if addr == HDMA5 and not (value & 0x80):
                self._do_gdma(value)
            return
        if addr < 0xFFFF:
            self.hram[addr - 0xFF80] = value
            return
        self.ie = value

    def read16(self, addr: int) -> int:
        return self.read8(addr) | (self.read8((addr + 1) & 0xFFFF) << 8)

    def write16(self, addr: int, value: int) -> None:
        self.write8(addr, value & 0xFF)
        self.write8((addr + 1) & 0xFFFF, (value >> 8) & 0xFF)

    def _read_p1(self) -> int:
        # Input is an external signal, so expose provider changes at each
        # electrical sample rather than only once per visual update.
        if self.button_provider:
            self.buttons = self.button_provider(self.main_iterations, self.page_swaps) & 0xFF
        select = self.io[P1 & 0x7F] & 0x30
        low = 0x0F
        if not (select & 0x10):
            low &= ~(self.buttons & 0x0F)
        if not (select & 0x20):
            low &= ~((self.buttons >> 4) & 0x0F)
        return 0xC0 | select | low

    def _do_gdma(self, control: int) -> None:
        blocks = (control & 0x7F) + 1
        src = (self.io[HDMA1 & 0x7F] << 8) | (self.io[HDMA2 & 0x7F] & 0xF0)
        dst = 0x8000 | ((self.io[HDMA3 & 0x7F] & 0x1F) << 8) | (self.io[HDMA4 & 0x7F] & 0xF0)
        lcd_on = bool(self.io[LCDC & 0x7F] & 0x80)
        vblank_safe_start = (not lcd_on) or self.ly >= 144
        complete = (not lcd_on) or (self.ly >= 144 and
            self.ly * 456 + self.ppu_dots + blocks * 32 + 16 <= 154 * 456)
        event: dict[str, int | bool] = {
            "frame": self.frame_count, "ly": self.ly,
            "bank": self.io[VBK & 0x7F] & 1,
            "source": src, "destination": dst, "blocks": blocks,
            "lcd_on": lcd_on, "vblank_safe_start": vblank_safe_start,
            "vblank_safe_complete": complete,
        }
        self.gdma_events.append(event)
        if lcd_on:
            self._pending_commit_event_indexes.append(len(self.gdma_events) - 1)
            if not vblank_safe_start:
                self.gdma_vblank_violations += 1
        for i in range(blocks * 16):
            self.vram[self.io[VBK & 0x7F] & 1][(dst - 0x8000 + i) & 0x1FFF] = self.read8((src + i) & 0xFFFF)
        src = (src + blocks * 16) & 0xFFFF
        dst = 0x8000 | ((dst - 0x8000 + blocks * 16) & 0x1FF0)
        self.io[HDMA1 & 0x7F] = (src >> 8) & 0xFF
        self.io[HDMA2 & 0x7F] = src & 0xF0
        self.io[HDMA3 & 0x7F] = (dst >> 8) & 0x1F
        self.io[HDMA4 & 0x7F] = dst & 0xF0
        self.io[HDMA5 & 0x7F] = 0xFF
        # Approximately 8 microseconds per 16-byte block. In CPU T-cycles,
        # that is ~32 normal-speed or ~64 double-speed cycles.
        self.extra_cycles += blocks * (64 if self.double_speed else 32)

    # ----- helpers --------------------------------------------------------
    def fetch8(self) -> int:
        value = self.read8(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch16(self) -> int:
        lo = self.fetch8(); hi = self.fetch8()
        return lo | (hi << 8)

    def push16(self, value: int) -> None:
        self.sp = (self.sp - 1) & 0xFFFF; self.write8(self.sp, (value >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF; self.write8(self.sp, value & 0xFF)

    def pop16(self) -> int:
        lo = self.read8(self.sp); self.sp = (self.sp + 1) & 0xFFFF
        hi = self.read8(self.sp); self.sp = (self.sp + 1) & 0xFFFF
        return lo | (hi << 8)

    def get_r(self, index: int) -> int:
        if index == 0: return self.b
        if index == 1: return self.c
        if index == 2: return self.d
        if index == 3: return self.e
        if index == 4: return self.h
        if index == 5: return self.l
        if index == 6: return self.read8(self.hl)
        return self.a

    def set_r(self, index: int, value: int) -> None:
        value &= 0xFF
        if index == 0: self.b = value
        elif index == 1: self.c = value
        elif index == 2: self.d = value
        elif index == 3: self.e = value
        elif index == 4: self.h = value
        elif index == 5: self.l = value
        elif index == 6: self.write8(self.hl, value)
        else: self.a = value

    def get_rr(self, index: int) -> int:
        return [self.bc, self.de, self.hl, self.sp][index]

    def set_rr(self, index: int, value: int) -> None:
        value &= 0xFFFF
        if index == 0: self.bc = value
        elif index == 1: self.de = value
        elif index == 2: self.hl = value
        else: self.sp = value

    def flag(self, mask: int) -> bool:
        return bool(self.f & mask)

    def condition(self, index: int) -> bool:
        return [not self.flag(Z), self.flag(Z), not self.flag(C), self.flag(C)][index]

    @staticmethod
    def signed8(value: int) -> int:
        return value - 256 if value & 0x80 else value

    def _tick(self, cycles: int) -> None:
        cycles += self.extra_cycles
        self.extra_cycles = 0
        self.cycles += cycles
        lcdc = self.io[LCDC & 0x7F]
        if lcdc & 0x80:
            dots = cycles // (2 if self.double_speed else 1)
            self.ppu_dots += dots
            while self.ppu_dots >= 456:
                self.ppu_dots -= 456
                self.ly += 1
                if self.ly == 144:
                    self.io[IF & 0x7F] |= 0x01
                if self.ly == self.io[LYC & 0x7F] and self.io[STAT & 0x7F] & 0x40:
                    self.io[IF & 0x7F] |= 0x02
                if self.ly >= 154:
                    self.ly = 0
                    self.frame_count += 1
        else:
            self.ly = 0
            self.ppu_dots = 0

    def _alu(self, kind: int, value: int) -> None:
        a = self.a
        carry = 1 if self.flag(C) else 0
        if kind == 0:  # ADD
            result = a + value
            self.f = (Z if (result & 0xFF) == 0 else 0) | (H if ((a & 0xF) + (value & 0xF) > 0xF) else 0) | (C if result > 0xFF else 0)
            self.a = result & 0xFF
        elif kind == 1:  # ADC
            result = a + value + carry
            self.f = (Z if (result & 0xFF) == 0 else 0) | (H if ((a & 0xF) + (value & 0xF) + carry > 0xF) else 0) | (C if result > 0xFF else 0)
            self.a = result & 0xFF
        elif kind == 2:  # SUB
            result = a - value
            self.f = N | (Z if (result & 0xFF) == 0 else 0) | (H if (a & 0xF) < (value & 0xF) else 0) | (C if a < value else 0)
            self.a = result & 0xFF
        elif kind == 3:  # SBC
            result = a - value - carry
            self.f = N | (Z if (result & 0xFF) == 0 else 0) | (H if (a & 0xF) < ((value & 0xF) + carry) else 0) | (C if a < value + carry else 0)
            self.a = result & 0xFF
        elif kind == 4:  # AND
            self.a = a & value
            self.f = (Z if self.a == 0 else 0) | H
        elif kind == 5:  # XOR
            self.a = a ^ value
            self.f = Z if self.a == 0 else 0
        elif kind == 6:  # OR
            self.a = a | value
            self.f = Z if self.a == 0 else 0
        else:  # CP
            result = a - value
            self.f = N | (Z if (result & 0xFF) == 0 else 0) | (H if (a & 0xF) < (value & 0xF) else 0) | (C if a < value else 0)

    def _inc8(self, value: int) -> int:
        result = (value + 1) & 0xFF
        self.f = (self.f & C) | (Z if result == 0 else 0) | (H if (value & 0x0F) == 0x0F else 0)
        return result

    def _dec8(self, value: int) -> int:
        result = (value - 1) & 0xFF
        self.f = (self.f & C) | N | (Z if result == 0 else 0) | (H if (value & 0x0F) == 0 else 0)
        return result

    # ----- instruction execution ----------------------------------------
    def step(self) -> int:
        pending = self.ie & self.io[IF & 0x7F] & 0x1F
        if self.halted:
            if pending:
                self.halted = False
            else:
                self.steps += 1
                self._tick(4)
                return 4
        if self.ime and pending:
            bit = next(index for index in range(5) if pending & (1 << index))
            vector = 0x40 + bit * 8
            self.ime = False
            self._ime_enable_delay = 0
            self.io[IF & 0x7F] &= ~(1 << bit)
            old_pc = self.pc
            self.push16(old_pc)
            self.pc = vector
            self.interrupt_events.append({
                "bit": bit, "vector": vector, "pc": old_pc,
                "frame": self.frame_count, "ly": self.ly,
            })
            self.steps += 1
            self._tick(20)
            return 20
        if self.pc in self.breakpoints:
            self.breakpoints[self.pc](self)
        start_pc = self.pc
        op = self.fetch8()
        cycles = 0

        # Large regular instruction groups first.
        if 0x40 <= op <= 0x7F:
            if op == 0x76:
                self.halted = True; cycles = 4
            else:
                dst = (op >> 3) & 7; src = op & 7
                self.set_r(dst, self.get_r(src))
                cycles = 8 if 6 in (dst, src) else 4
        elif 0x80 <= op <= 0xBF:
            kind = (op >> 3) & 7; src = op & 7
            self._alu(kind, self.get_r(src))
            cycles = 8 if src == 6 else 4
        elif op & 0xC7 == 0x06:  # LD r,d8
            reg = (op >> 3) & 7
            self.set_r(reg, self.fetch8())
            cycles = 12 if reg == 6 else 8
        elif op & 0xC7 == 0x04:  # INC r
            reg = (op >> 3) & 7
            self.set_r(reg, self._inc8(self.get_r(reg)))
            cycles = 12 if reg == 6 else 4
        elif op & 0xC7 == 0x05:  # DEC r
            reg = (op >> 3) & 7
            self.set_r(reg, self._dec8(self.get_r(reg)))
            cycles = 12 if reg == 6 else 4
        elif op & 0xCF == 0x01:  # LD rr,d16
            rr = (op >> 4) & 3
            self.set_rr(rr, self.fetch16()); cycles = 12
        elif op & 0xCF == 0x03:  # INC rr
            rr = (op >> 4) & 3
            self.set_rr(rr, self.get_rr(rr) + 1); cycles = 8
        elif op & 0xCF == 0x0B:  # DEC rr
            rr = (op >> 4) & 3
            self.set_rr(rr, self.get_rr(rr) - 1); cycles = 8
        elif op & 0xCF == 0x09:  # ADD HL,rr
            rr = (op >> 4) & 3
            lhs = self.hl; rhs = self.get_rr(rr); result = lhs + rhs
            self.f = (self.f & Z) | (H if ((lhs & 0xFFF) + (rhs & 0xFFF) > 0xFFF) else 0) | (C if result > 0xFFFF else 0)
            self.hl = result & 0xFFFF; cycles = 8
        elif op in (0xC6, 0xCE, 0xD6, 0xDE, 0xE6, 0xEE, 0xF6, 0xFE):
            kind = (op >> 3) & 7
            self._alu(kind, self.fetch8()); cycles = 8
        elif op == 0xCB:
            cb = self.fetch8(); group = cb >> 6; y = (cb >> 3) & 7; r = cb & 7
            value = self.get_r(r)
            if group == 0:
                carry_in = 1 if self.flag(C) else 0
                if y == 0: result = ((value << 1) | (value >> 7)) & 0xFF; carry_out = value >> 7
                elif y == 1: result = ((value >> 1) | ((value & 1) << 7)) & 0xFF; carry_out = value & 1
                elif y == 2: result = ((value << 1) | carry_in) & 0xFF; carry_out = value >> 7
                elif y == 3: result = ((value >> 1) | (carry_in << 7)) & 0xFF; carry_out = value & 1
                elif y == 4: result = (value << 1) & 0xFF; carry_out = value >> 7
                elif y == 5: result = ((value >> 1) | (value & 0x80)) & 0xFF; carry_out = value & 1
                elif y == 6: result = ((value << 4) | (value >> 4)) & 0xFF; carry_out = 0
                else: result = value >> 1; carry_out = value & 1
                self.set_r(r, result)
                self.f = (Z if result == 0 else 0) | (C if carry_out else 0)
            elif group == 1:
                bit_set = bool(value & (1 << y))
                self.f = (self.f & C) | H | (0 if bit_set else Z)
            elif group == 2:
                self.set_r(r, value & ~(1 << y))
            else:
                self.set_r(r, value | (1 << y))
            cycles = 16 if r == 6 else 8
        else:
            # Irregular core instructions.
            if op == 0x00: cycles = 4
            elif op == 0x02: self.write8(self.bc, self.a); cycles = 8
            elif op == 0x0A: self.a = self.read8(self.bc); cycles = 8
            elif op == 0x12: self.write8(self.de, self.a); cycles = 8
            elif op == 0x1A: self.a = self.read8(self.de); cycles = 8
            elif op == 0x08: addr = self.fetch16(); self.write16(addr, self.sp); cycles = 20
            elif op == 0x10:
                _padding = self.fetch8()
                key1 = self.io[KEY1 & 0x7F]
                if key1 & 1:
                    self.double_speed = not self.double_speed
                    self.io[KEY1 & 0x7F] = (0x80 if self.double_speed else 0x00)
                cycles = 4
            elif op == 0x22: self.write8(self.hl, self.a); self.hl = (self.hl + 1) & 0xFFFF; cycles = 8
            elif op == 0x2A: self.a = self.read8(self.hl); self.hl = (self.hl + 1) & 0xFFFF; cycles = 8
            elif op == 0x32: self.write8(self.hl, self.a); self.hl = (self.hl - 1) & 0xFFFF; cycles = 8
            elif op == 0x3A: self.a = self.read8(self.hl); self.hl = (self.hl - 1) & 0xFFFF; cycles = 8
            elif op == 0x07:
                carry = self.a >> 7; self.a = ((self.a << 1) | carry) & 0xFF; self.f = C if carry else 0; cycles = 4
            elif op == 0x0F:
                carry = self.a & 1; self.a = ((self.a >> 1) | (carry << 7)) & 0xFF; self.f = C if carry else 0; cycles = 4
            elif op == 0x17:
                cin = 1 if self.flag(C) else 0; cout = self.a >> 7; self.a = ((self.a << 1) | cin) & 0xFF; self.f = C if cout else 0; cycles = 4
            elif op == 0x1F:
                cin = 1 if self.flag(C) else 0; cout = self.a & 1; self.a = ((self.a >> 1) | (cin << 7)) & 0xFF; self.f = C if cout else 0; cycles = 4
            elif op == 0x2F: self.a ^= 0xFF; self.f = (self.f & (Z | C)) | N | H; cycles = 4
            elif op == 0x37: self.f = (self.f & Z) | C; cycles = 4
            elif op == 0x3F: self.f = (self.f & Z) | (0 if self.flag(C) else C); cycles = 4
            elif op == 0x18:
                # JR displacement is relative to the address after the operand.
                # Fetch first so self.pc points at that architectural base.
                delta = self.signed8(self.fetch8())
                self.pc = (self.pc + delta) & 0xFFFF; cycles = 12
            elif op in (0x20, 0x28, 0x30, 0x38):
                cond = (op >> 3) & 3; delta = self.signed8(self.fetch8())
                if self.condition(cond): self.pc = (self.pc + delta) & 0xFFFF; cycles = 12
                else: cycles = 8
            elif op == 0xC3: self.pc = self.fetch16(); cycles = 16
            elif op in (0xC2, 0xCA, 0xD2, 0xDA):
                cond = (op >> 3) & 3; target = self.fetch16()
                if self.condition(cond): self.pc = target; cycles = 16
                else: cycles = 12
            elif op == 0xE9: self.pc = self.hl; cycles = 4
            elif op == 0xCD:
                target = self.fetch16(); self.push16(self.pc); self.pc = target; cycles = 24
            elif op in (0xC4, 0xCC, 0xD4, 0xDC):
                cond = (op >> 3) & 3; target = self.fetch16()
                if self.condition(cond): self.push16(self.pc); self.pc = target; cycles = 24
                else: cycles = 12
            elif op == 0xC9: self.pc = self.pop16(); cycles = 16
            elif op == 0xD9: self.pc = self.pop16(); self.ime = True; self._ime_enable_delay = 0; cycles = 16
            elif op in (0xC0, 0xC8, 0xD0, 0xD8):
                cond = (op >> 3) & 3
                if self.condition(cond): self.pc = self.pop16(); cycles = 20
                else: cycles = 8
            elif op in (0xC5, 0xD5, 0xE5, 0xF5):
                rr = (op >> 4) & 3; value = [self.bc, self.de, self.hl, self.af][rr]
                self.push16(value); cycles = 16
            elif op in (0xC1, 0xD1, 0xE1, 0xF1):
                rr = (op >> 4) & 3; value = self.pop16()
                if rr == 0: self.bc = value
                elif rr == 1: self.de = value
                elif rr == 2: self.hl = value
                else: self.af = value
                cycles = 12
            elif op == 0xE0: self.write8(0xFF00 | self.fetch8(), self.a); cycles = 12
            elif op == 0xF0: self.a = self.read8(0xFF00 | self.fetch8()); cycles = 12
            elif op == 0xE2: self.write8(0xFF00 | self.c, self.a); cycles = 8
            elif op == 0xF2: self.a = self.read8(0xFF00 | self.c); cycles = 8
            elif op == 0xEA: self.write8(self.fetch16(), self.a); cycles = 16
            elif op == 0xFA: self.a = self.read8(self.fetch16()); cycles = 16
            elif op == 0xF9: self.sp = self.hl; cycles = 8
            elif op == 0xF3: self.ime = False; self._ime_enable_delay = 0; cycles = 4
            elif op == 0xFB: self._ime_enable_delay = 2; cycles = 4
            elif op == 0x76: self.halted = True; cycles = 4
            else:
                label = next((name for name, addr in self.symbols.items() if addr == start_pc), "")
                raise CPUError(f"unsupported opcode {op:02X} at {start_pc:04X} {label}")

        self.steps += 1
        self._tick(cycles)
        if self._ime_enable_delay:
            self._ime_enable_delay -= 1
            if not self._ime_enable_delay:
                self.ime = True
        return cycles

    def call_subroutine(self, target: int | str, *, max_steps: int = 1_000_000,
                        restore_pc: bool = True) -> Snapshot:
        """Execute one ROM routine until its RET reaches a private sentinel.

        The helper is intentionally small and deterministic: it uses the CPU's
        real stack, advances timing normally, and verifies that the routine
        restored SP. It is useful for differential ROM-vs-host probes without
        replaying a complete visual frame for every pose.
        """
        if isinstance(target, str):
            if target not in self.symbols:
                raise KeyError(f"unknown symbol: {target}")
            target = self.symbols[target]
        target &= 0xFFFF
        sentinel = 0xFF80
        old_pc, old_sp = self.pc, self.sp
        self.push16(sentinel)
        self.pc = target
        for _ in range(max_steps):
            if self.pc == sentinel:
                break
            self.step()
        else:
            raise CPUError(f"subroutine limit reached at PC={self.pc:04X}, target={target:04X}")
        if self.sp != old_sp:
            raise CPUError(f"unbalanced stack after {target:04X}: SP={self.sp:04X}, expected={old_sp:04X}")
        if restore_pc:
            self.pc = old_pc
        return self.snapshot()

    def run(self, *, max_steps: int = 5_000_000, until_swaps: int | None = None,
            until_pc: int | None = None) -> Snapshot:
        for _ in range(max_steps):
            if until_swaps is not None and self.page_swaps >= until_swaps:
                break
            if until_pc is not None and self.pc == until_pc:
                break
            self.step()
        else:
            raise CPUError(f"execution limit reached at PC={self.pc:04X}, swaps={self.page_swaps}")
        return self.snapshot()

    def snapshot(self) -> Snapshot:
        def wram_word(addr: int) -> int: return self.read8(addr) | (self.read8(addr + 1) << 8)
        return Snapshot(
            steps=self.steps, cycles=self.cycles, frames=self.frame_count, swaps=self.page_swaps,
            pc=self.pc, player_x=wram_word(0xD140), player_y=wram_word(0xD142), angle=self.read8(0xD144),
        )

    # ----- video output ---------------------------------------------------
    @staticmethod
    def _rgb_from_palette(data: bytearray, palette: int, color: int) -> tuple[int, int, int]:
        index = palette * 8 + color * 2
        word = data[index] | (data[index + 1] << 8)
        r = word & 31; g = (word >> 5) & 31; b = (word >> 10) & 31
        return (r * 255 // 31, g * 255 // 31, b * 255 // 31)

    def render_screen(self) -> Image.Image:
        image = Image.new("RGB", (160, 144))
        pixels = image.load()
        lcdc = self.io[LCDC & 0x7F]
        tilemap_base = 0x1C00 if (lcdc & 0x08) else 0x1800
        bg_colors = [[0] * 160 for _ in range(144)]
        bg_priority = [[False] * 160 for _ in range(144)]
        # Background.
        for y in range(144):
            line_lcdc = lcdc
            if self.raster_lcdc:
                _, (mask, _, before) = min(self.raster_lcdc.items())
                line_lcdc = (line_lcdc & ~mask) | before
            for line, (mask, value, _) in sorted(self.raster_lcdc.items()):
                if y >= line: line_lcdc = (line_lcdc & ~mask) | value
            for x in range(160):
                bx, by = (x + self.io[0x43]) & 255, (y + self.io[0x42]) & 255
                base = tilemap_base
                wx, wy = self.io[0x4B] - 7, self.io[0x4A]
                if lcdc & 0x20 and y >= wy and x >= wx and wx < 160:
                    bx, by = x - wx, y - wy
                    base = 0x1C00 if lcdc & 0x40 else 0x1800
                map_index = base + (by // 8) * 32 + (bx // 8)
                tile = self.vram[0][map_index]
                attr = self.vram[1][map_index]
                bank = (attr >> 3) & 1
                tx = bx & 7; ty = by & 7
                if attr & 0x20: tx = 7 - tx
                if attr & 0x40: ty = 7 - ty
                tile_base = tile * 16 if line_lcdc & 0x10 else 0x1000 + (tile if tile < 128 else tile - 256) * 16
                tile_addr = tile_base + ty * 2
                lo = self.vram[bank][tile_addr]; hi = self.vram[bank][tile_addr + 1]
                bit = 7 - tx
                color = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)
                bg_colors[y][x] = color
                bg_priority[y][x] = bool(attr & 0x80)
                pixels[x, y] = self._rgb_from_palette(self.bg_palette, attr & 7, color)
        background = image.copy().load()
        # OBJ. Draw high OAM indices first so lower indices win.
        if lcdc & 0x02:
            sprite_height = 16 if lcdc & 0x04 else 8
            selected = [set([i for i in range(40)
                             if self.oam[i * 4] - 16 <= y < self.oam[i * 4] - 16 + sprite_height][:10])
                        for y in range(144)]
            for index in range(39, -1, -1):
                off = index * 4
                sy = self.oam[off] - 16; sx = self.oam[off + 1] - 8
                tile = self.oam[off + 2]; attr = self.oam[off + 3]
                if sx <= -8 or sx >= 160 or sy <= -sprite_height or sy >= 144:
                    continue
                if sprite_height == 16: tile &= 0xFE
                for py in range(sprite_height):
                    yy = sy + py
                    if not 0 <= yy < 144: continue
                    if index not in selected[yy]: continue
                    source_y = sprite_height - 1 - py if attr & 0x40 else py
                    tile_index = tile + source_y // 8
                    row = source_y & 7
                    bank = (attr >> 3) & 1
                    addr = tile_index * 16 + row * 2
                    lo = self.vram[bank][addr]; hi = self.vram[bank][addr + 1]
                    for px in range(8):
                        xx = sx + px
                        if not 0 <= xx < 160: continue
                        source_x = px if not (attr & 0x20) else 7 - px
                        bit = 7 - source_x
                        color = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)
                        if color == 0: continue
                        if lcdc & 1 and bg_colors[yy][xx] and (bg_priority[yy][xx] or attr & 0x80):
                            pixels[xx, yy] = background[xx, yy]
                            continue
                        pixels[xx, yy] = self._rgb_from_palette(self.obj_palette, attr & 7, color)
        return image


def parse_symbols(path: Path) -> dict[str, int]:
    symbols: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        address, name = line.split(maxsplit=1)
        symbols[name] = int(address, 16)
    return symbols


def default_input(iteration: int, _swaps: int) -> int:
    # Four forward updates, then turn right, then fire once.
    if 2 <= iteration <= 5: return 0x04
    if 6 <= iteration <= 9: return 0x01
    if iteration == 10: return 0x10
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=Path(__file__).resolve().parents[1] / "build/lupine3d.gb")
    parser.add_argument("--symbols", type=Path, default=Path(__file__).resolve().parents[1] / "build/lupine3d.sym")
    parser.add_argument("--swaps", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "build/harness_frame.png")
    parser.add_argument("--no-input", action="store_true")
    args = parser.parse_args()
    symbols = parse_symbols(args.symbols)
    cgb = CGB(args.rom.read_bytes(), symbols)
    if not args.no_input:
        cgb.button_provider = default_input
    snap = cgb.run(until_swaps=args.swaps)
    image = cgb.render_screen()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    report = {
        **snap.__dict__,
        "double_speed": cgb.double_speed,
        "main_iterations": cgb.main_iterations,
        "lcdc": f"0x{cgb.io[LCDC & 0x7F]:02X}",
        "vram_pages_differ": cgb.vram[0][:3840] != cgb.vram[1][:3840],
        "output": str(args.output),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
