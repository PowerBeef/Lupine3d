"""Debugger exports: a bank-prefixed symbol file and a section/allocation map.

`lupine3d.sym` uses the `BB:AAAA name` form that RGBDS emits and that BGB,
Emulicious and SameBoy's debugger read: bank 0 for the fixed ROM half, bank
1 for the engine's cold sections, the owning bank for labels bound inside a
banked window (boot assets, raw ray tables), and for the layout's RAM
variables - exported too, so a debugger can watch them by name - bank 0 for
fixed WRAM and HRAM and the bank the layout names for a switchable address
(`WRAM_BANK_OF_NAME`; bank 1, the render snapshot, otherwise). A comment line names the ROM the table
belongs to. `sm83emu.parse_symbols` reads this form and the flat `AAAA name`
form of the archived baselines.

`lupine3d.map` lists the assembler's sections with their addresses, sizes
and kinds, then the allocation ledger, so the placement decisions that
`bank_safety` proves are readable without the listing.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Symbol:
    bank: int
    address: int
    name: str
    kind: str          # code, data, ram, hram, io

    @property
    def line(self) -> str:
        return f"{self.bank:02X}:{self.address:04X} {self.name}"


def _bank_of_ram(address: int, name: str = "", overrides: dict[str, int] | None = None) -> int:
    """WRAM bank of a RAM symbol: fixed WRAM and HRAM are bank 0; a
    switchable address is bank 1 (the render snapshot, whose names the live
    copy in bank 2 shares) unless the layout names another bank for it."""
    if 0xC000 <= address < 0xD000 or address >= 0xFF80:
        return 0
    return (overrides or {}).get(name, 1)


def symbol_table(assembler, *, bank_bound: dict[str, int], ram_names: dict[str, int],
                 wram_bank_of_name: dict[str, int] | None = None) -> list[Symbol]:
    """Every label the assembler resolved plus the layout's RAM variables.

    `bank_bound` maps a label to the ROM bank its banked-window address
    belongs to (boot assets, raw ray tables, the unfolded strips). Labels at
    RAM addresses (the ISR's input latches, the presentation serial) are RAM
    symbols; every other label is code, or data when it starts a data span.
    """
    data_starts = {start for start, _ in getattr(assembler, "data_spans", ())}
    out: list[Symbol] = []
    for name, address in assembler.labels.items():
        if address >= 0x8000:
            kind = "hram" if address >= 0xFF80 else "ram"
            out.append(Symbol(_bank_of_ram(address, name, wram_bank_of_name), address, name, kind))
        elif name in bank_bound:
            out.append(Symbol(bank_bound[name], address, name, "data"))
        else:
            bank = 0 if address < 0x4000 else 1
            out.append(Symbol(bank, address, name, "data" if address in data_starts else "code"))
    labelled = {s.name for s in out}
    for name, address in ram_names.items():
        if name in labelled:
            continue
        if 0xC000 <= address < 0xE000:
            out.append(Symbol(_bank_of_ram(address, name, wram_bank_of_name), address, name, "ram"))
        elif 0xFF80 <= address < 0xFFFF:
            out.append(Symbol(0, address, name, "hram"))
    return sorted(out, key=lambda s: (s.kind in ("ram", "hram"), s.bank, s.address, s.name))


def ram_names_from_layout(layout) -> dict[str, int]:
    """The layout's integer constants that name a WRAM or HRAM address."""
    names: dict[str, int] = {}
    for name in dir(layout):
        if not name.isupper() or name.startswith("_"):
            continue
        value = getattr(layout, name)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if 0xC000 <= value < 0xE000 or 0xFF80 <= value < 0xFFFF:
            names[name] = value
    return names


def write_symbols(path: Path, symbols: list[Symbol], *, rom_sha256: str, configuration_id: str) -> None:
    lines = [f"; Lupine 3D symbols for ROM sha256 {rom_sha256}",
             f"; configuration {configuration_id}",
             "; bank:address name - ROM banks 0/1 are the resident halves; RAM symbols carry their WRAM bank"]
    lines += [s.line for s in symbols]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_map(path: Path, assembler, ledger: dict, *, rom_sha256: str) -> None:
    """Sections in emission order with sizes and kinds, then the allocation ledger."""
    sections = list(assembler.sections)
    end = assembler.origin + len(assembler.code)
    data_spans = sorted(getattr(assembler, "data_spans", ()))
    lines = [f"; Lupine 3D map for ROM sha256 {rom_sha256}", "", "SECTIONS (bank:start-end size kind)"]
    for index, (name, start) in enumerate(sections):
        stop = sections[index + 1][1] if index + 1 < len(sections) else end
        bank = 0 if start < 0x4000 else 1
        data = sum(min(stop, b) - max(start, a) for a, b in data_spans if a < stop and b > start)
        kind = "data" if data >= max(1, stop - start) else "code" if data == 0 else "code+data"
        lines.append(f"  {bank:02X}:{start:04X}-{stop:04X} {stop - start:6d} {kind:9s} {name}")
    lines += ["", "ALLOCATIONS (region start-end size owner [lifetime])"]
    for row in ledger.get("ranges", []):
        lifetime = f" [{row['lifetime']}]" if row.get("lifetime") else ""
        lines.append(f"  {row['space']:6s} {row['start']:06X}-{row['end']:06X} {row['end'] - row['start']:8d} {row['owner']}{lifetime}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
