"""v0.7 foundation contracts, independent of the emitter's byte layout."""
from __future__ import annotations

import itertools
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from sm83emu import CGB
from playtest import oam_budget


class OverhaulTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.manifest = br.make_rom()

    def boot(self):
        cgb = CGB(self.rom, self.asm.labels)
        cgb.run(until_pc=self.asm.labels["main_loop"], max_steps=2_000_000)
        return cgb

    def test_every_door_combination_has_ids_for_all_visible_faces(self):
        level = br.ACTIVE_LEVEL
        doors = [i for i, cell in enumerate(level.grid) if cell == 3]
        self.assertEqual(len(doors), 4)
        for states in itertools.product((False, True), repeat=len(doors)):
            grid = bytearray(level.grid)
            for index, opened in zip(doors, states):
                if opened:
                    grid[index] = 0
            for y in range(16):
                for x in range(16):
                    if not grid[y * 16 + x]:
                        continue
                    for side, (dx, dy) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < 16 and 0 <= ny < 16 and not grid[ny * 16 + nx]:
                            self.assertNotEqual(level.segment_table[(y * 16 + x) * 4 + side], 0,
                                                (states, x, y, side))

    def test_projection_depth_matches_integer_distance_not_height_class(self):
        cgb = self.boot()
        cgb.write8(br.WORLD_MODE, 0)
        projection = br.make_tables()["projection_half"]
        for component in (1, 7, 16, 63, 64, 113, 127):
            for correction in (110, 118, 127):
                for distance in (0, 20, 21, 112, 113, 255, 256, 511):
                    cgb.write8(br.DDA_AXIS, 0)
                    cgb.write8(br.DDA_ABS_X, component)
                    cgb.write8(br.DDA_CORRECTION, correction)
                    cgb.write16(br.DDA_DIST_L, distance * 8)
                    cgb.call_subroutine("project_hit")
                    depth = min(511, (distance * correction + component // 2) // component)
                    self.assertEqual(cgb.read8(br.TOP_RESULT), 48 - projection[depth])
                    self.assertEqual(cgb.read8(br.DEPTH_RESULT), min(255, depth))
        # A near wall must not become zero-depth merely because top clipped.
        self.assertEqual(br.make_projection_top_lut()[((127 * 18 + 17) * 512 + 16) * 2 + 1], 16)
        self.assertEqual(br.PROJECTION_LUT_BYTES, 2_359_296)

    def test_current_pose_hitscan_rejects_stale_aim_and_new_wall(self):
        cgb = self.boot()
        for y in range(16):
            for x in range(16):
                cgb.write8(br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
        cgb.write16(br.PLAYER_XL, 0x0280); cgb.write16(br.PLAYER_YL, 0x0280)
        cgb.write16(br.SENTINEL_XL, 0x0480); cgb.write16(br.SENTINEL_YL, 0x0280)
        cgb.write8(br.ANGLE, 0); cgb.write8(br.SENTINEL_HEALTH, 3)
        cgb.write8(br.SENTINEL_VISIBLE, 0); cgb.write8(br.SENTINEL_SCREEN_X, 255)
        cgb.call_subroutine("player_fire_hitscan")
        self.assertEqual(cgb.read8(br.SENTINEL_HEALTH), 2)
        cgb.write8(br.ANGLE, 64)
        cgb.write8(br.SENTINEL_VISIBLE, 1); cgb.write8(br.SENTINEL_SCREEN_X, 80)
        cgb.call_subroutine("player_fire_hitscan")
        self.assertEqual(cgb.read8(br.SENTINEL_HEALTH), 2)
        cgb.write8(br.ANGLE, 0); cgb.write8(br.MAP + 2 * 16 + 3, 1)
        cgb.call_subroutine("player_fire_hitscan")
        self.assertEqual(cgb.read8(br.SENTINEL_HEALTH), 2)

    def test_shared_camera_and_projected_feet(self):
        self.assertLess(abs(br.CAMERA_FOCAL_PIXELS - 80 / math.tan(math.radians(br.FOV_DEGREES / 2))), .5)
        cgb = self.boot()
        cgb.write16(br.PLAYER_XL, 0x0280); cgb.write16(br.PLAYER_YL, 0x0280); cgb.write8(br.ANGLE, 0)
        cgb.write16(br.SENTINEL_XL, 0x0480); cgb.write16(br.SENTINEL_YL, 0x0380)
        cgb.call_subroutine("project_sentinel")
        self.assertEqual(cgb.read8(br.SENTINEL_SCREEN_X), 80 + 137 // 2)
        self.assertEqual(cgb.read8(br.ENTITY_FOOT_Y), 16 + 48 + 15)
        cgb.write16(br.SENTINEL_XL, 0x0680)
        cgb.call_subroutine("project_sentinel")
        self.assertEqual(cgb.read8(br.ENTITY_FOOT_Y), 16 + 48 + 7)

    def test_folded_mixed_columns_preserve_all_wall_pixels(self):
        rng = random.Random(700)
        def decode(tile):
            return [[((tile[y * 2] >> (7 - x)) & 1) | (((tile[y * 2 + 1] >> (7 - x)) & 1) << 1)
                     for x in range(8)] for y in range(8)]
        for _ in range(1024):
            tops = [rng.randrange(48) for _ in range(8)]
            styles = [rng.randrange(br.RENDER_STYLE_COUNT) for _ in range(8)]
            y0 = rng.randrange(6) * 8
            _, upper = br.reference_tile_signature_and_bytes(tops, styles, y0, 0)
            _, lower = br.reference_tile_signature_and_bytes(tops, styles, 88 - y0, 0)
            expected = [[1 if c == 0 else c for c in row] for row in reversed(decode(upper))]
            self.assertEqual(expected, decode(lower))

    def test_signed_bg_and_cold_banks_do_not_overlap_sprite_pool(self):
        self.assertEqual([br.bg_tile_address(i) for i in (0, 95, 119, 127, 128, 255)],
                         [0x9000, 0x95f0, 0x9770, 0x97f0, 0x8800, 0x8ff0])
        self.assertEqual(br.TILE_ATLAS_COUNT, 121)
        self.assertLessEqual(br.ENTITY_OAM_COUNT * 2 * 16, br.HUD_TILE_BASE * 16)
        start = br.BOOT_ASSETS_ROM_BANK*0x4000 + self.asm.labels["entity_tiles"] - 0x4000
        self.assertEqual(self.rom[start:start+len(br.make_entity_tiles())], br.make_entity_tiles())
        self.assertLess((br.WEAPON_TILE_BASE + 16) * 16, 0x800)
        self.assertLess(self.manifest["memory_budget"]["fixed_code_end"], 0x4000)
        self.assertGreaterEqual(self.manifest["memory_budget"]["resident_free_bytes"], 3000)
        self.assertLessEqual(br.STACK_TOP, 0xcfff)
        cgb = self.boot()
        self.assertEqual(cgb.rom_bank, 1)

    def test_staged_packet_keeps_old_oam_until_final_publish(self):
        cgb = self.boot()
        before = bytes(cgb.oam)
        cgb.write8(br.DYN_COUNT, 96); cgb.write8(br.OAM_DIRTY, 1)
        marker = bytes((64, 88, br.PICKUP_TILE, 9))
        for i, value in enumerate(marker):
            cgb.write8(br.OAM_SHADOW + 72 + i, value)
        # Stop at the continuation immediately before the second wait returns.
        cgb.pc = self.asm.labels["upload_hidden_page"]
        cgb.run(until_pc=self.asm.labels["upload_packet_ready"], max_steps=500_000)
        self.assertEqual(bytes(cgb.oam), before)
        self.assertEqual(cgb.page_swaps, 0)
        cgb.run(until_swaps=1, max_steps=500_000)
        self.assertEqual(bytes(cgb.oam[72:76]), marker)
        self.assertTrue(cgb.commit_events[-1]["staged"])
        self.assertTrue(cgb.commit_events[-1]["vblank_safe"])

    def test_joypad_poll_is_not_a_clock_tick_and_ai_retains_remainder(self):
        cgb = self.boot(); cgb.ime = False
        cgb.write8(br.INPUT_SAMPLE_COUNT, 11)
        cgb.call_subroutine("sample_joypad_latched")
        self.assertEqual(cgb.read8(br.INPUT_SAMPLE_COUNT), 11)
        cgb.write8(br.SENTINEL_AI_STAMP, 0)
        cgb.call_subroutine("update_world")
        self.assertEqual(cgb.read8(br.SENTINEL_AI_STAMP), 8)
        cgb.write8(br.SENTINEL_AI_STAMP, 252); cgb.write8(br.INPUT_SAMPLE_COUNT, 3)
        cgb.call_subroutine("update_world")
        self.assertEqual(cgb.read8(br.SENTINEL_AI_STAMP), 0)
        cgb.write8(br.INPUT_SAMPLE_COUNT, 40)
        cgb.call_subroutine("update_world")
        self.assertEqual(cgb.read8(br.SENTINEL_AI_STAMP), 16)  # bounded, not discarded

    def test_oam_selection_counts_offscreen_x_and_total_allocator_is_bounded(self):
        cgb = self.boot(); cgb.oam[:] = bytes(160)
        for i in range(11):
            cgb.oam[i * 4] = 50
        self.assertEqual(oam_budget(cgb)["max_oam_per_scanline"], 11)
        cgb.call_subroutine("clear_entity_oam_shadow")
        cgb.write8(br.OAM_SHADOW + 160, 0xa5)
        for index in range(30):
            cgb.b, cgb.c, cgb.d, cgb.e = 16 + (index % 8) * 16, 88, 0, 9
            cgb.call_subroutine("submit_oam_8x8")
        self.assertEqual(cgb.read8(br.SENTINEL_OAM_USED), 16)
        self.assertEqual(cgb.read8(br.OAM_SHADOW + 160), 0xa5)

    def test_ppu_does_not_draw_the_eleventh_y_selected_object(self):
        cgb = CGB(self.rom)
        cgb.io[0x40] = br.BG_LCDC
        cgb.obj_palette[2] = 31  # colour 1 = red
        for row in range(8):
            cgb.vram[0][row * 2] = 255
        for index in range(11):
            cgb.oam[index * 4] = 32
        cgb.oam[10 * 4 + 1] = 16
        self.assertEqual(cgb.render_screen().getpixel((8, 16)), (0, 0, 0))
        cgb.oam[0] = 0
        self.assertEqual(cgb.render_screen().getpixel((8, 16)), (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
