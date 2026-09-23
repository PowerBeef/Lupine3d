"""The shot's occluder test: an actor pressed against a wall can be hit, an
actor behind a wall or a closed door cannot."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br  # noqa: E402
from playtest import set_test_world_byte  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402


class HitscanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def machine(self, grid):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        for index, value in enumerate(grid):
            set_test_world_byte(cgb, br.MAP + index, value)
        return cgb

    def shoot(self, grid, player, actor, *, doors=()):
        cgb = self.machine(grid)
        px, py = player
        ax, ay = actor
        angle = round(math.atan2(ay - py, ax - px) * 256 / math.tau) & 255
        for address, value in ((br.PLAYER_XL, px & 255), (br.PLAYER_XH, px >> 8), (br.PLAYER_YL, py & 255),
                               (br.PLAYER_YH, py >> 8), (br.ANGLE, angle), (br.SENTINEL_XL, ax & 255),
                               (br.SENTINEL_XH, ax >> 8), (br.SENTINEL_YL, ay & 255), (br.SENTINEL_YH, ay >> 8),
                               (br.SENTINEL_STATE, br.SENTINEL_CHASE), (br.SENTINEL_HEALTH, 5), (br.SENTINEL_KIND, 0),
                               (br.ACTOR_COUNT, 1), (br.DOOR_COUNT, len(doors)), (br.WEAPON_INDEX, 0),
                               (br.WEAPON_COOLDOWN, 0)):
            set_test_world_byte(cgb, address, value)
        for index, (x, y, state) in enumerate(doors):
            base = br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES
            for offset, value in enumerate((x, y, 1, 0, state, 0)):
                set_test_world_byte(cgb, base + offset, value)
        cgb.call_subroutine("save_primary_actor", max_steps=100_000)
        cgb.call_subroutine("player_fire_hitscan", max_steps=2_000_000)
        cgb.call_subroutine("restore_primary_actor", max_steps=100_000)
        return cgb.read8(br.SENTINEL_HEALTH), cgb.read8(br.SENTINEL_SCREEN_X)

    @staticmethod
    def room(walls=()):
        return bytes(int(x in (0, 15) or y in (0, 15) or (x, y) in walls) for y in range(16) for x in range(16))

    def test_an_actor_flush_against_a_wall_can_be_shot(self):
        # A chaser stops with its centre on the wall plane it walks into; the
        # shot's occluder is that very plane, so the test needs slack.
        grid = self.room(walls=((9, 5),))
        health, screen_x = self.shoot(grid, (9 * 256 + 128, 7 * 256 + 128), (9 * 256 + 128, 6 * 256))
        self.assertTrue(72 <= screen_x < 89, screen_x)
        self.assertEqual(health, 4, "an actor pressed against the wall in front of it was not hit")
        # Diagonally as well, one unit past the plane by rounding.
        health, _ = self.shoot(grid, (9 * 256 + 100, 7 * 256 + 200), (9 * 256 + 140, 6 * 256 - 1))
        self.assertEqual(health, 4)

    def test_an_actor_behind_a_wall_or_a_closed_door_is_not(self):
        behind_wall = self.room(walls=((9, 6),))
        health, _ = self.shoot(behind_wall, (9 * 256 + 128, 7 * 256 + 128), (9 * 256 + 128, 5 * 256 + 128))
        self.assertEqual(health, 5, "a shot passed through a wall")
        # A closed door's panel is at the cell centre; the actor at the far
        # edge of the cell beyond it is half a cell further than the panel.
        door = bytearray(self.room()); door[6 * 16 + 9] = 3
        health, _ = self.shoot(bytes(door), (9 * 256 + 128, 7 * 256 + 128), (9 * 256 + 128, 5 * 256 + 250),
                               doors=((9, 6, 0),))
        self.assertEqual(health, 5, "a shot passed through a closed door")
        # And an open panel no longer occludes; the cell was cleared to 0.
        health, _ = self.shoot(self.room(), (9 * 256 + 128, 7 * 256 + 128), (9 * 256 + 128, 5 * 256 + 250),
                               doors=((9, 6, 2),))
        self.assertEqual(health, 4)

    def test_the_slack_is_a_quarter_cell(self):
        self.assertEqual(br.HITSCAN_DEPTH_SLACK, 8)


if __name__ == "__main__":
    unittest.main()
