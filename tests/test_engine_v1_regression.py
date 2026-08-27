#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_rom_v1 import NINTENDO_LOGO, make_rom  # noqa: E402
from sm83emu import CGB, parse_symbols  # noqa: E402


class Lupine3DV1RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rom, cls.assembler, cls.manifest = make_rom()
        cls.symbols = cls.assembler.labels

    def boot_to_main(self) -> CGB:
        cgb = CGB(self.rom, self.symbols)
        cgb.run(until_pc=self.symbols["main_loop"], max_steps=1_000_000)
        return cgb

    def test_rom_header_and_checksums(self) -> None:
        rom = self.rom
        self.assertEqual(len(rom), 32768)
        self.assertEqual(rom[0x0104:0x0134], NINTENDO_LOGO)
        self.assertEqual(rom[0x0134:0x013C], b"LUPINE3D")
        self.assertEqual(rom[0x0143], 0xC0)
        self.assertEqual(rom[0x0147], 0x00)
        self.assertEqual(rom[0x0148], 0x00)
        header = 0
        for value in rom[0x0134:0x014D]:
            header = (header - value - 1) & 0xFF
        self.assertEqual(header, rom[0x014D])
        total = (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF
        self.assertEqual((rom[0x014E] << 8) | rom[0x014F], total)
        self.assertLessEqual(self.manifest["engine_end"], 0x8000)

    def test_build_is_deterministic(self) -> None:
        rom2, _, _ = make_rom()
        self.assertEqual(hashlib.sha256(self.rom).digest(), hashlib.sha256(rom2).digest())

    def test_boot_renders_and_uses_double_speed(self) -> None:
        cgb = self.boot_to_main()
        self.assertTrue(cgb.double_speed)
        self.assertEqual(cgb.io[0x40], 0x93)
        self.assertNotEqual(bytes(cgb.wram0[:3840]), bytes(3840))
        self.assertEqual(cgb.vram[0][:3840], cgb.wram0[:3840])
        self.assertEqual(cgb.vram[1][:3840], cgb.wram0[:3840])
        states = [cgb.read8(0xD100 + i) for i in range(40)]
        self.assertTrue(all(0 <= value < 64 for value in states))
        self.assertGreater(len(set(states)), 3)
        self.assertEqual(cgb.read8(0xD140) | (cgb.read8(0xD141) << 8), 0x0180)

    def test_controls_move_turn_and_page_flip(self) -> None:
        cgb = self.boot_to_main()

        def script(iteration: int, _swaps: int) -> int:
            if 1 <= iteration <= 4: return 0x04  # Up
            if 5 <= iteration <= 7: return 0x01  # Right
            return 0

        cgb.button_provider = script
        cgb.run(until_swaps=7, max_steps=2_000_000)
        x = cgb.read8(0xD140) | (cgb.read8(0xD141) << 8)
        self.assertEqual(x, 0x01D0)
        self.assertEqual(cgb.read8(0xD144), 12)
        self.assertEqual(cgb.page_swaps, 7)
        self.assertEqual(cgb.io[0x40] & 0x08, 0x08)  # odd flip -> map at 9C00
        self.assertNotEqual(cgb.vram[0][:3840], cgb.vram[1][:3840])

    def test_collision_blocks_world_boundary(self) -> None:
        cgb = self.boot_to_main()
        # Face west from the starting corridor and keep walking into tile x=0.
        cgb.write8(0xD144, 128)
        cgb.button_provider = lambda iteration, _swaps: 0x04 if iteration <= 10 else 0
        cgb.run(until_swaps=10, max_steps=3_000_000)
        x = cgb.read8(0xD140) | (cgb.read8(0xD141) << 8)
        self.assertGreaterEqual(x, 0x0100)
        self.assertEqual(x >> 8, 1)

    def test_door_interaction_mutates_map(self) -> None:
        cgb = self.boot_to_main()
        # Stand immediately west of the door at map cell (9,4), facing east.
        cgb.write8(0xD140, 0x80); cgb.write8(0xD141, 8)
        cgb.write8(0xD142, 0x80); cgb.write8(0xD143, 4)
        cgb.write8(0xD144, 0)
        door_addr = 0xD000 + 4 * 16 + 9
        self.assertEqual(cgb.read8(door_addr), 3)
        cgb.button_provider = lambda iteration, _swaps: 0x20 if iteration == 1 else 0
        cgb.run(until_swaps=1, max_steps=1_000_000)
        self.assertEqual(cgb.read8(door_addr), 0)
        self.assertEqual(cgb.read8(0xFF14), 0xC4)

    def test_fire_has_audio_and_visible_muzzle_feedback(self) -> None:
        cgb = self.boot_to_main()
        cgb.button_provider = lambda iteration, _swaps: 0x10 if iteration == 1 else 0
        cgb.run(until_swaps=1, max_steps=1_000_000)
        self.assertEqual(cgb.read8(0xFF14), 0xC7)
        self.assertGreater(cgb.read8(0xD147), 0)
        self.assertEqual(cgb.oam[17 * 4], 72)


if __name__ == "__main__":
    unittest.main(verbosity=2)
