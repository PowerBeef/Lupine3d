"""Executable acceptance gates for the post-foundation overhaul."""
import json
import random
import os
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from lupine3d_v4.precision import q14_direction
from lupine3d_v4.levels import compile_level, build_surface_table
from sm83emu import CGB


class RemainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.manifest = br.make_rom()

    def boot(self):
        c = CGB(self.rom, self.asm.labels)
        c.run(until_pc=self.asm.labels["main_loop"])
        c.ime = False
        return c

    @staticmethod
    def block(c, address, count):
        return bytes(c.read8(address + i) for i in range(count))

    def test_q14_certificate_exhaustively_bounds_every_supported_direction(self):
        tables = br.make_tables()
        maximum = 0
        for angle in range(256):
            for record in range(241):
                if record == 240:
                    offset = 0  # the current-pose centre hitscan is certified too
                else:
                    i, key = (record, "ray_offsets") if record < 80 else (record - 80, "physical_offsets")
                    offset = int.from_bytes(tables[key][i * 2:i * 2 + 2], "little", signed=True)
                index = (angle * 4 + offset) % 1024
                for fine, component in zip(q14_direction(angle, record), ("ray_dx", "ray_dy")):
                    coarse = tables[component][index]
                    if coarse >= 128: coarse -= 256
                    maximum = max(maximum, abs(coarse - fine * 127 / 16384))
        self.assertLess(maximum, 1)

    def test_all_64_retained_tail_rays_select_the_float_oracle_face_in_rom(self):
        c = self.boot(); c.write8(br.SIM_READY, 0); c.write8(br.WORLD_MODE, 0)
        grid = compile_level(br.ROOT / "levels/renderer_benchmark.json").grid
        for i, value in enumerate(grid): c.write8(br.MAP + i, value)
        records = json.loads((br.ROOT / "research/results/tail_failures_v4.json").read_text())["records"]
        self.assertEqual(len(records), 64)
        for row in records:
            c.write16(br.PLAYER_XL, row["player_x_q8"]); c.write16(br.PLAYER_YL, row["player_y_q8"])
            c.write8(br.ANGLE, row["angle"]); c.write8(br.PIXEL_INDEX, row["physical_column"])
            c.call_subroutine("cast_physical_indexed")
            self.assertEqual((c.read8(br.DDA_MAP_X), c.read8(br.DDA_MAP_Y), c.read8(br.DDA_AXIS)),
                             (row["expected_cell_x"], row["expected_cell_y"], row["expected_axis"]))

    def test_wide_arithmetic_in_rom_handles_full_unsigned_range(self):
        c = self.boot(); rng = random.Random(707)
        for x, y in [(65535, 65535), (0, 65535), (256, 16384)] + [(rng.randrange(65536), rng.randrange(1, 65536)) for _ in range(100)]:
            c.hl = x; c.d, c.e = y >> 8, y & 255; c.call_subroutine("q14_multiply_u16")
            self.assertEqual(int.from_bytes(self.block(c, br.Q14_PRODUCT, 4), "little"), x * y)
            c.d, c.e = y >> 8, y & 255; c.call_subroutine("divide_u32_u16")
            self.assertEqual(int.from_bytes(self.block(c, br.Q14_PRODUCT, 4), "little"), x)

    def test_sliding_doors_match_host_from_both_axes_and_multiple_apertures(self):
        c = self.boot(); c.write8(br.SIM_READY, 0)
        for door in br.ACTIVE_LEVEL.doors:
            for fraction in (0, 64, 128, 192, 224):
                for index in range(len(br.ACTIVE_LEVEL.doors)):
                    c.write8(br.DOOR_TABLE + index * 6 + 4, 1); c.write8(br.DOOR_TABLE + index * 6 + 5, fraction)
                x, y = (door.x * 256 - 320, door.y * 256 + 128) if door.orientation == 0 else (door.x * 256 + 128, door.y * 256 - 320)
                angle = 0 if door.orientation == 0 else 64
                c.write16(br.PLAYER_XL, x); c.write16(br.PLAYER_YL, y); c.write8(br.ANGLE, angle)
                states = {(d.x, d.y): (1, fraction) for d in br.ACTIVE_LEVEL.doors}
                for i in range(80):
                    c.write8(br.CAST_INDEX, i); c.call_subroutine("cast_indexed")
                    hit = br.reference_cast_hit(x, y, angle, i, br.make_map(), states)
                    actual = c.read8(br.DDA_MAP_X), c.read8(br.DDA_MAP_Y), c.read8(br.DDA_AXIS), c.read16(br.DDA_DIST_L)
                    self.assertEqual(actual, (hit.map_x, hit.map_y, hit.axis, hit.axis_distance_q8), (door.name, fraction, i))

    def test_door_aperture_is_shared_by_radius_collision_and_exact_los(self):
        c = self.boot()
        for y in range(16):
            for x in range(16): c.write8(br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
        c.write8(br.MAP + 3 * 16 + 3, 3); c.write8(br.DOOR_COUNT, 1)
        for i, value in enumerate((3, 3, 0, 0, 1, 192)): c.write8(br.DOOR_TABLE + i, value)
        c.write16(br.COLLISION_X, 3 * 256 + 128); c.write16(br.COLLISION_Y, 3 * 256 + 128)
        c.b, c.c = 3, 3; c.call_subroutine("collision_cell_bc"); self.assertEqual(c.a, 0)
        c.write8(br.DOOR_TABLE + 5, 160)
        c.b, c.c = 3, 3; c.call_subroutine("collision_cell_bc"); self.assertNotEqual(c.a, 0)
        c.write16(br.PLAYER_XL, 2 * 256 + 128); c.write16(br.PLAYER_YL, 3 * 256 + 128)
        c.write16(br.SENTINEL_XL, 4 * 256 + 128); c.write16(br.SENTINEL_YL, 3 * 256 + 128)
        c.call_subroutine("sentinel_line_of_sight"); self.assertEqual(c.read8(br.LOS_RESULT), 1)
        c.write8(br.DOOR_TABLE + 5, 0)
        c.call_subroutine("sentinel_line_of_sight"); self.assertEqual(c.read8(br.LOS_RESULT), 0)

    def test_timestamped_queue_retains_repeated_edges_and_wraps_at_16_bits(self):
        c = self.boot(); c.write16(br.SIM_CLOCK, 65534)
        for buttons in (16, 0, 16):
            c.buttons = buttons; c.call_subroutine("sample_joypad_latched"); c.call_subroutine("queue_vblank_input")
        packets = [self.block(c, br.INPUT_QUEUE + i * 4, 4) for i in range(3)]
        self.assertEqual([int.from_bytes(p[:2], "little") for p in packets], [65535, 0, 1])
        self.assertEqual([p[3] for p in packets], [16, 0, 16])
        c.call_subroutine("render_yield")
        self.assertEqual(c.read16(br.SIM_TICK), 1)
        self.assertEqual(c.read16(br.SIM_STEPS), 3)
        self.assertEqual(c.read8(br.INPUT_QUEUE_OVERFLOW), 0)

    def test_yield_preserves_the_render_snapshot_and_consumes_bounded_debt(self):
        c = self.boot()
        before = self.block(c, br.MAP, 256), self.block(c, br.PLAYER_XL, 5), self.block(c, br.VRAM_PROFILE, 128)
        for _ in range(10):
            c.buttons = 1; c.call_subroutine("sample_joypad_latched"); c.call_subroutine("queue_vblank_input")
        c.call_subroutine("render_yield")
        self.assertEqual(c.read16(br.SIM_STEPS), 4)
        self.assertEqual(before, (self.block(c, br.MAP, 256), self.block(c, br.PLAYER_XL, 5), self.block(c, br.VRAM_PROFILE, 128)))
        c.call_subroutine("render_yield"); c.call_subroutine("render_yield")
        self.assertEqual(c.read16(br.SIM_STEPS), 10)
        c.call_subroutine("begin_frame_snapshot")
        self.assertEqual(c.read8(br.ANGLE), (br.ACTIVE_LEVEL.player_angle + 10) & 255)
        self.assertEqual(c.read16(br.FRAME_TICK), 10)

    def test_masked_pairs_clip_every_bit_and_preserve_scanline_capacity(self):
        c = self.boot(); c.call_subroutine("clear_entity_oam_shadow")
        c.write8(br.MASK_BITS, 0xF0)
        c.b, c.c, c.d, c.e = 60, 80, 0, 1
        c.call_subroutine("submit_masked_oam")
        self.assertEqual(self.block(c, br.MASK_TILES, 32), bytes(value & 0xF0 for value in br.make_entity_tiles()[:32]))
        for _ in range(10):
            c.b, c.c, c.d, c.e = 60, 80, 0, 1; c.call_subroutine("submit_masked_oam")
        self.assertEqual(c.read8(br.SENTINEL_OAM_USED), 4)
        self.assertEqual(c.read8(br.MASK_TILE_COUNT), 8)
        self.assertLessEqual(max(self.block(c, br.WORLD_SCANLINES, 144)), 4)
        for i in range(80): c.write8(br.RAY_DEPTH + i, 255 if i & 1 else 10)
        c.write8(br.SENTINEL_DEPTH, 20); c.a = 4; c.call_subroutine("entity_column_visible")
        self.assertEqual(c.a, 0x33)

    def test_three_lods_have_hysteresis(self):
        c = self.boot(); c.write8(br.ENTITY_SLOT, 0)
        for distance, expected in ((31, 0), (35, 0), (36, 1), (67, 1), (68, 2), (61, 2), (59, 1), (27, 0)):
            c.write8(br.ENTITY_FORWARD, distance); c.call_subroutine("choose_entity_lod")
            self.assertEqual(c.read8(br.SENTINEL_LOD), expected)

    def test_surface_records_reserve_door_colour_and_emit_exact_attributes(self):
        with self.assertRaises(ValueError):
            build_surface_table(br.make_map(), [{"x": 0, "y": 0, "side": "east", "profile": "door"}])
        c = self.boot()
        profiles = [2] * 80 + [1] * 80
        profiles[4] = 0  # a mixed tile must not repaint neighbouring geometry
        for i, profile in enumerate(profiles): c.write8(br.PIXEL_SURFACE + i, profile)
        c.call_subroutine("build_surface_attributes")
        self.assertEqual(self.block(c, br.VIEW_ATTRIBUTES, 384), br.surface_attributes(profiles, 1))

    def test_two_actor_slots_sort_near_first_and_unlock_only_after_both_die(self):
        c = self.boot(); c.write8(br.SIM_READY, 0)
        for y in range(16):
            for x in range(16): c.write8(br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
        c.write16(br.PLAYER_XL, 0x0280); c.write16(br.PLAYER_YL, 0x0280); c.write8(br.ANGLE, 0)
        c.write16(br.SENTINEL_XL, 0x0480); c.write16(br.SENTINEL_YL, 0x0280)
        c.write8(br.ACTOR_COUNT, 2)
        for i, value in enumerate((0x80, 3, 0x80, 2, 0, 3, 0, 0, 0, 0, 0, 0)):
            c.write8(br.ENTITY_SLOTS + 16 + i, value)
        for i in range(80): c.write8(br.RAY_DEPTH + i, 255)
        c.call_subroutine("render_entities")
        self.assertEqual(c.read8(br.OAM_SHADOW + br.ENTITY_OAM_FIRST * 4), 62)
        self.assertGreater(c.read8(br.SENTINEL_OAM_USED), 4)
        self.assertLessEqual(max(self.block(c, br.WORLD_SCANLINES, 144)), 4)
        c.call_subroutine("player_fire_hitscan")
        self.assertEqual(c.read8(br.ENTITY_SLOTS + 16 + 5), 2)
        self.assertEqual(c.read8(br.SENTINEL_HEALTH), 3)
        for _ in range(2): c.call_subroutine("player_fire_hitscan")
        self.assertEqual(c.read8(br.ENTITY_SLOTS + 16 + 4), br.SENTINEL_DEAD)
        self.assertEqual(c.read8(br.EXIT_ACTIVE), 0)
        for _ in range(3): c.call_subroutine("player_fire_hitscan")
        self.assertEqual(c.read8(br.SENTINEL_STATE), br.SENTINEL_DEAD)
        self.assertEqual(c.read8(br.EXIT_ACTIVE), 1)

    def test_fixed_movement_is_independent_of_service_batching(self):
        positions = []
        for batch in (1, 3, 10):
            c = self.boot()
            c.wramx[2][br.PLAYER_XL - 0xD000:br.ANGLE - 0xD000 + 1] = bytes((128, 2, 128, 2, 0))
            for tick in range(10):
                c.buttons = 4; c.call_subroutine("sample_joypad_latched"); c.call_subroutine("queue_vblank_input")
                if (tick + 1) % batch == 0: c.call_subroutine("render_yield")
            while c.read8(br.INPUT_QUEUE_HEAD) != c.read8(br.INPUT_QUEUE_TAIL): c.call_subroutine("render_yield")
            c.call_subroutine("begin_frame_snapshot")
            positions.append(c.read16(br.PLAYER_XL))
        self.assertEqual(positions, [0x0280 + 40] * 3)

    def test_bulk_copy_preserves_exact_lengths_and_guards(self):
        c = self.boot()
        for length in (0, 1, 2, 3, 4, 5, 127, 255, 256, 457):
            for i in range(460):
                c.write8(0xC000 + i, i & 255); c.write8(0xC300 + i, 0xA5)
            c.hl = 0xC000; c.d, c.e = 0xC3, 0; c.b, c.c = length >> 8, length & 255
            c.call_subroutine("copy_bc")
            self.assertEqual(self.block(c, 0xC300, length), bytes(i & 255 for i in range(length)))
            self.assertEqual(c.read8(0xC300 + length), 0xA5)

    def test_input_queue_overflow_never_overwrites_pending_packets(self):
        c = self.boot()
        for _ in range(63):
            c.buttons = 0; c.call_subroutine("sample_joypad_latched"); c.call_subroutine("queue_vblank_input")
        before = self.block(c, br.INPUT_QUEUE, 252)
        c.buttons = 16; c.call_subroutine("sample_joypad_latched"); c.call_subroutine("queue_vblank_input")
        self.assertEqual(self.block(c, br.INPUT_QUEUE, 252), before)
        self.assertEqual(c.read8(br.INPUT_QUEUE_OVERFLOW), 1)
        self.assertEqual(c.read8(br.INPUT_EDGE_LATCH) & 16, 16)
        c.call_subroutine("render_yield"); c.call_subroutine("queue_vblank_input")
        self.assertEqual(c.read8(br.INPUT_QUEUE + 255) & 16, 16)

    def test_optional_reprojection_uses_published_entity_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(br.ROOT / "tools/verify_variants.py"),
                                     "reprojection", "--output", str(Path(directory) / "report.json")],
                                    env={**os.environ, "LUPINE3D_REPROJECTION": "1"},
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_maximum_176_block_packet_is_staged_and_atomic(self):
        c = self.boot(); c.write8(br.DYN_COUNT, 96); c.write8(br.MASK_TILE_COUNT, 32)
        old_oam = bytes(c.oam)
        c.write8(br.OAM_SHADOW + 40, 64)
        c.pc = self.asm.labels["upload_hidden_page"]
        c.run(until_pc=self.asm.labels["upload_packet_ready"])
        self.assertEqual(bytes(c.oam), old_oam)
        c.run(until_presentations=1)
        self.assertEqual(c.commit_events[-1]["blocks"], 176)
        self.assertTrue(c.commit_events[-1]["staged"])
        self.assertTrue(c.commit_events[-1]["vblank_safe"])
        self.assertEqual(c.gdma_vblank_violations, 0)
        self.assertEqual(c.oam[40], 64)

    def test_start_restarts_dead_and_completed_worlds(self):
        for address, value in ((br.PLAYER_HEALTH, 0), (br.LEVEL_COMPLETE, 1)):
            c = self.boot(); c.wramx[2][address - 0xD000] = value
            c.buttons = 128; c.call_subroutine("sample_joypad_latched"); c.call_subroutine("queue_vblank_input")
            c.call_subroutine("render_yield"); c.call_subroutine("begin_frame_snapshot")
            self.assertEqual(c.read8(br.PLAYER_HEALTH), 99)
            self.assertEqual(c.read8(br.LEVEL_COMPLETE), 0)
            self.assertEqual(c.read8(br.SENTINEL_HEALTH), 3)


if __name__ == "__main__": unittest.main()
