"""Actual-program contracts for wall reuse and independent OBJ publication."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br
from lupine3d_v4.wall_cache import WALL_KEY_RANGES
from playtest import apply_diagnostic_camera, read_block, set_test_world_byte, validate_frame
from sm83emu import CGB


class WallReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, cls.manifest = br.make_rom()

    def boot(self, *, full=False):
        c = CGB(self.rom, self.asm.labels)
        c.run(until_pc=self.asm.labels["main_loop"])
        c.write8(br.SIM_READY, 0)
        c.write8(br.WALL_CACHE_DISABLE, int(full))
        return c

    def frame(self, c):
        # Frozen-world diagnostic retains LCD IRQs without filling an input
        # queue whose consumer is deliberately suspended.
        c.write8(br.INPUT_QUEUE_TAIL, c.read8(br.INPUT_QUEUE_HEAD))
        c.run(until_presentations=c.presentations + 1)
        validate_frame(c)
        self.assertTrue(c.commit_events[-1]["vblank_safe"])

    def test_every_mutable_key_byte_invalidates_without_hash_collisions(self):
        c = self.boot(); c.ime = False
        c.call_subroutine("check_wall_reuse"); c.write8(br.WALL_CACHE_VALID, 1)
        for address, _, length in WALL_KEY_RANGES:
            for offset in range(length):
                old = c.read8(address + offset)
                c.write8(address + offset, old ^ 1)
                c.call_subroutine("check_wall_reuse")
                self.assertEqual(c.read8(br.FRAME_REUSED), 0, hex(address + offset))
                c.write8(address + offset, old)
                c.call_subroutine("check_wall_reuse"); c.write8(br.WALL_CACHE_VALID, 1)
                c.call_subroutine("check_wall_reuse")
                self.assertEqual(c.read8(br.FRAME_REUSED), 1)
        for address in (br.PLAYER_HEALTH, br.SENTINEL_XL, br.SENTINEL_ANIM, br.FLASH, br.EXIT_ACTIVE):
            c.write8(address, c.read8(address) ^ 1)
            c.call_subroutine("check_wall_reuse")
            self.assertEqual(c.read8(br.FRAME_REUSED), 1, hex(address))

    def test_reload_and_generation_change_during_a_render_cannot_certify_stale_world(self):
        c = self.boot(); c.ime = False
        c.call_subroutine("check_wall_reuse")
        c.call_subroutine("invalidate_wall_cache")
        c.write8(br.WALL_CACHE_VALID, 1)  # older render finishes after invalidation
        c.call_subroutine("check_wall_reuse")
        self.assertEqual(c.read8(br.FRAME_REUSED), 0)
        c.write16(br.WALL_EPOCH, 65535); c.write8(br.WALL_CACHE_VALID, 1)
        c.call_subroutine("load_level")
        self.assertEqual(c.read16(br.WALL_EPOCH), 0)
        self.assertEqual(c.read8(br.WALL_CACHE_VALID), 0)
        self.assertEqual(c.rom_bank, 1)
        self.assertEqual(read_block(c, br.MAP, 256), br.make_map())

    def test_cached_and_full_renders_match_through_actor_hud_door_and_camera_changes(self):
        fast, full = self.boot(), self.boot(full=True)
        cases = [([2176, 2176, 0], 0), ([2176, 2176, 0], 0),
                 ([2176, 2176, 0], 0), ([2176, 2176, 1], 0),
                 ([2176, 2176, 1], 64), ([2176, 2176, 1], 64),
                 ([2177, 2176, 1], 128), ([2177, 2176, 1], 128)]
        expected_reuse = [False, True, True, False, False, True, False, True]
        for index, ((pose, fraction), reused) in enumerate(zip(cases, expected_reuse)):
            for c in (fast, full):
                apply_diagnostic_camera(c, dict(pose=pose))
                set_test_world_byte(c, br.SENTINEL_ANIM, index % 4)
                set_test_world_byte(c, br.PLAYER_HEALTH, 99-index)
                set_test_world_byte(c, br.DOOR_TABLE + 4, 1)
                set_test_world_byte(c, br.DOOR_TABLE + 5, fraction)
                self.frame(c)
            self.assertEqual(bool(fast.read8(br.FRAME_REUSED)), reused)
            self.assertEqual(fast.render_screen().tobytes(), full.render_screen().tobytes(), index)
            self.assertEqual(bytes(fast.oam), bytes(full.oam), index)
            for address, count in ((br.RAY_DEPTH, 80), (br.RAY_SEGMENT, 80),
                                   (br.VIEW_MAP, 384), (br.DYNAMIC_TILES, fast.read8(br.DYN_COUNT)*16),
                                   (br.MASK_TILES, fast.read8(br.MASK_TILE_COUNT)*16), (br.HUD_PACKET, 11)):
                self.assertEqual(read_block(fast, address, count), read_block(full, address, count))
            if reused:
                self.assertLessEqual(fast.commit_events[-1]["event_count"], 1)
                self.assertTrue(all(event["destination"] == 0x8000 for event in fast.commit_events[-1]["events"]))
        self.assertEqual(fast.page_swaps, 4)
        self.assertEqual(full.page_swaps, 8)
        self.assertEqual(fast.presentations, 8)

    def test_sprite_publication_zero_to_maximum_never_writes_background(self):
        c = self.boot(); self.frame(c)
        for count in range(0, 33, 2):
            c.write8(br.INPUT_QUEUE_TAIL, c.read8(br.INPUT_QUEUE_HEAD))
            c.write8(br.MASK_TILE_COUNT, count); c.write8(br.FRAME_REUSED, 1)
            for i in range(count * 16): c.write8(br.MASK_TILES + i, (i+count) & 255)
            before = tuple(bytes(bank[0x800:0x1800]) for bank in c.vram)
            maps = tuple(bytes(bank[offset:offset+384]) for bank in c.vram for offset in (0x1800, 0x1C00))
            old_page, old_obj, swaps = c.read8(br.CURRENT_PAGE), c.read8(br.OBJ_PAGE), c.page_swaps
            c.call_subroutine("upload_entities_hud")
            self.assertEqual(c.page_swaps, swaps)
            self.assertEqual(c.read8(br.CURRENT_PAGE), old_page)
            self.assertEqual(c.read8(br.OBJ_PAGE), old_obj ^ 1)
            self.assertEqual(before, tuple(bytes(bank[0x800:0x1800]) for bank in c.vram))
            self.assertEqual(maps, tuple(bytes(bank[offset:offset+384]) for bank in c.vram for offset in (0x1800, 0x1C00)))
            self.assertEqual(bytes(c.vram[old_obj ^ 1][:count*16]), read_block(c, br.MASK_TILES, count*16))
            event = c.commit_events[-1]
            self.assertEqual(event["blocks"], count)
            self.assertTrue(event["vblank_safe"])
            self.assertFalse(event["staged"])

    def test_presentation_counter_wrap_and_reserved_memory(self):
        c = self.boot(); self.frame(c)
        c.wram0[br.PRESENT_SERIAL - 0xC000] = 255
        self.frame(c)
        self.assertEqual(c.read8(br.PRESENT_SERIAL), 0)
        self.assertEqual(c.presentations, 2)
        self.assertEqual(c.page_swaps, 1)
        self.assertLessEqual(br.WALL_CACHE_MAP+256, br.STACK_TOP+1-512)
        self.assertGreaterEqual(br.WALL_CACHE_META, br.PIXEL_SURFACE+160)
        self.assertLess(br.WALL_CACHE_META+34, 0xE000)
        self.assertGreaterEqual(self.manifest["memory_budget"]["resident_free_bytes"], 3000)
