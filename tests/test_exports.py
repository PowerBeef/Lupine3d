"""The debugger exports: bank-prefixed symbols, the map and their manifest hashes."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br  # noqa: E402
from sm83emu import parse_symbols  # noqa: E402
from lupine3d_v4 import symbols as sym  # noqa: E402

LINE = re.compile(r"^([0-9A-F]{2}):([0-9A-F]{4}) (\S+)$")


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.assembler, cls.metadata = br.make_rom()
        cls.directory = tempfile.TemporaryDirectory()
        cls.output = Path(cls.directory.name)
        br.write_outputs(cls.output, cls.rom, cls.assembler, cls.metadata)
        cls.sym_lines = (cls.output / "lupine3d.sym").read_text().splitlines()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_symbol_file_is_bank_prefixed_and_names_its_rom(self):
        self.assertTrue(self.sym_lines[0].startswith("; Lupine 3D symbols for ROM sha256 " + self.metadata["sha256"]))
        entries = [LINE.match(line) for line in self.sym_lines if not line.startswith(";")]
        self.assertTrue(all(entries), "every symbol line is BB:AAAA name")
        banks = {m.group(3): int(m.group(1), 16) for m in entries}
        addresses = {m.group(3): int(m.group(2), 16) for m in entries}
        # Every assembler label is present at its address, in the bank that owns it.
        for name, address in self.assembler.labels.items():
            self.assertEqual(addresses[name], address, name)
            if name in self.metadata["bank_bound_labels"]:
                self.assertEqual(banks[name], self.metadata["bank_bound_labels"][name], name)
            elif address < 0x4000:
                self.assertEqual(banks[name], 0, name)
            elif address < 0x8000:
                self.assertEqual(banks[name], 1, name)
        self.assertEqual(banks["ui_tiles"], br.BOOT_ASSETS_ROM_BANK)
        # The layout's RAM variables are exported with their WRAM bank.
        self.assertEqual((banks["DYN_COUNT"], addresses["DYN_COUNT"]), (0, br.DYN_COUNT))
        self.assertEqual((banks["RAY_TOPS"], addresses["RAY_TOPS"]), (1, br.RAY_TOPS))
        self.assertEqual((banks["MUSIC_ROWS"], addresses["MUSIC_ROWS"]), (5, br.MUSIC_ROWS))
        self.assertEqual(banks["GAME_MODE"], 0)

    def test_parse_symbols_reads_both_forms(self):
        parsed = parse_symbols(self.output / "lupine3d.sym")
        for name, address in self.assembler.labels.items():
            self.assertEqual(parsed[name], address)
        flat = self.output / "flat.sym"
        flat.write_text("\n".join(f"{addr:04X} {name}" for name, addr in self.assembler.labels.items()) + "\n")
        self.assertEqual({k: parse_symbols(flat)[k] for k in self.assembler.labels}, dict(self.assembler.labels))

    def test_map_lists_sections_and_allocations(self):
        text = (self.output / "lupine3d.map").read_text()
        self.assertIn("SECTIONS", text); self.assertIn("ALLOCATIONS", text)
        for name, _ in self.assembler.sections:
            self.assertIn(f" {name}\n", text + "\n", name)
        self.assertIn("resident engine/data and cartridge header", text)
        self.assertRegex(text, r"\n  0[01]:[0-9A-F]{4}-[0-9A-F]{4} +\d+ (code|data|code\+data) ")

    def test_manifest_hashes_the_exports(self):
        manifest = json.loads((self.output / "build_manifest.json").read_text())
        exports = manifest["exports"]
        self.assertEqual(exports["format"], "rgbds-sym-v1")
        self.assertEqual(exports["sym_sha256"], hashlib.sha256((self.output / "lupine3d.sym").read_bytes()).hexdigest())
        self.assertEqual(exports["map_sha256"], hashlib.sha256((self.output / "lupine3d.map").read_bytes()).hexdigest())
        self.assertEqual(exports["symbols"], len([l for l in self.sym_lines if not l.startswith(";")]))
        self.assertEqual(exports["code"] + exports["data"] + exports["ram"], exports["symbols"])

    def test_ram_bank_lookup_is_by_name_for_switchable_wram(self):
        self.assertEqual(sym._bank_of_ram(0xC123), 0)
        self.assertEqual(sym._bank_of_ram(br.MUSIC_ROWS, "MUSIC_ROWS", br.WRAM_BANK_OF_NAME), 5)
        self.assertEqual(sym._bank_of_ram(br.RAY_TOPS, "RAY_TOPS", br.WRAM_BANK_OF_NAME), 1)
        self.assertEqual(sym._bank_of_ram(0xFF90), 0)


if __name__ == "__main__":
    unittest.main()
