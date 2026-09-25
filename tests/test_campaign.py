"""Three episodes of six sectors: every sector carries the certificate, wears
its episode's palette set, and the episode-closing sectors field a boss."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_rom as br  # noqa: E402
from lupine3d_v4 import levels  # noqa: E402


# The showcase's episodes are six sectors each (games/sable_outpost/game.json).
SECTORS = 6


class CampaignTests(unittest.TestCase):
    def test_three_episodes_of_six_sectors(self):
        self.assertEqual(br.EPISODE_LENGTHS, (SECTORS, SECTORS, SECTORS))
        self.assertEqual(len(br.CAMPAIGN), 3 * SECTORS)
        self.assertEqual(br.EPISODE_STARTS, (SECTORS, 2 * SECTORS))
        # The level directory reaches every sector and the banks stay below the weapon bank.
        self.assertLess(br.level_location(len(br.CAMPAIGN) - 1)[0], br.WEAPON_ROM_BANK)

    def test_every_sector_wears_its_episodes_palette_set(self):
        names = {v: k for k, v in levels.PALETTE_IDS.items()}
        for index, level in enumerate(br.CAMPAIGN):
            episode = index // SECTORS
            self.assertEqual(names[level.palette_profile], ("outpost", "reactor", "spire")[episode], level.name)

    def test_the_last_sector_of_every_episode_fields_a_boss(self):
        for episode in range(len(br.CAMPAIGN) // SECTORS):
            last = br.CAMPAIGN[(episode + 1) * SECTORS - 1]
            kinds = {entity.kind for entity in last.entities}
            if episode == 0:
                # Episode one predates the boss and keeps its shipped sector.
                continue
            self.assertIn("boss", kinds, last.name)

    def test_every_sector_keeps_the_campaign_certificate(self):
        for level in br.CAMPAIGN:
            r = level.readability
            self.assertEqual(r.unreachable_cells, 0, level.name)
            self.assertLessEqual(r.maximum_sightline, 6, level.name)
            self.assertGreaterEqual(r.minimum_door_separation, 8, level.name)
            self.assertGreaterEqual(r.critical_path_turns, 3, level.name)
            self.assertLessEqual(len(level.entities), br.MAX_ACTORS, level.name)
            self.assertLessEqual(len(level.doors), br.MAX_DOORS, level.name)

    def test_continue_codes_cover_every_sector_and_skill(self):
        from lupine3d_v4.screens import continue_codes
        codes = continue_codes(br.LEVEL_COUNT, br.DIFFICULTY_LEVELS)
        self.assertEqual(len(codes), len(br.CAMPAIGN) * br.DIFFICULTY_LEVELS)
        self.assertEqual(len(set(codes)), len(codes))



class CampaignRulesTests(unittest.TestCase):
    """Rules the eighteen-sector campaign exposed: an actor authored inside a
    wall used to certify, and a medkit could push health past two digits."""
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def test_an_actor_inside_a_wall_is_refused(self):
        import json, tempfile
        source = json.loads((ROOT / "games" / "sable_outpost" / "levels" / "antenna_base.json").read_text())
        rows = source["rows"]
        actor = source["entities"][0]
        # The cell north of the actor is a wall in this sector? Find any wall
        # cell and park the actor on it.
        wall = next((x, y) for y in range(1, 15) for x in range(1, 15) if rows[y][x] == "1")
        moved = dict(actor, x_q8=wall[0] * 256 + 128, y_q8=wall[1] * 256 + 128)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "walled.json"
            path.write_text(json.dumps(dict(source, entities=[moved] + source["entities"][1:])))
            with self.assertRaises(ValueError):
                levels.compile_level(path)

    def test_an_actor_behind_the_locked_exit_door_is_refused(self):
        import json, tempfile
        # Sable Outpost's exit cell lies behind its Sentinel-locked door, which
        # opens only once every actor is dead: an actor parked there could
        # never be engaged.
        source = json.loads((ROOT / "games" / "sable_outpost" / "levels" / "living_world.json").read_text())
        exit_cell = source["exit"]
        moved = dict(source["entities"][0], x_q8=exit_cell["x"] * 256 + 128, y_q8=exit_cell["y"] * 256 + 128)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locked_in.json"
            path.write_text(json.dumps(dict(source, entities=[moved] + source["entities"][1:])))
            with self.assertRaises(ValueError):
                levels.compile_level(path)

    def test_an_actor_only_strikes_across_a_clean_diagonal(self):
        """Adjacent diagonally with a wall on one of the two shared sides, an
        actor cannot reach the player (the player's shot could not reach it
        either); with both sides open it strikes as before."""
        from sm83emu import CGB, run_to_world
        for corner_wall, expect_hit in ((True, False), (False, True)):
            cgb = run_to_world(CGB(self.rom, self.asm.labels))
            cgb.rom_bank = 1
            cgb.io[br.SVBK & 0x7F] = 2        # the simulation's live world
            for y in range(16):
                for x in range(16):
                    cgb.write8(br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
            if corner_wall:
                cgb.write8(br.MAP + 5 * 16 + 6, 1)     # the corner between (5,5) and (6,6)
            px, py = 5 * 256 + 128, 5 * 256 + 128
            ax, ay = 6 * 256 + 128, 6 * 256 + 128
            for address, value in ((br.PLAYER_XL, px & 255), (br.PLAYER_XH, px >> 8), (br.PLAYER_YL, py & 255), (br.PLAYER_YH, py >> 8),
                                   (br.PLAYER_HEALTH, 99), (br.ACTOR_COUNT, 1), (br.DOOR_COUNT, 0),
                                   (br.SENTINEL_XL, ax & 255), (br.SENTINEL_XH, ax >> 8), (br.SENTINEL_YL, ay & 255), (br.SENTINEL_YH, ay >> 8),
                                   (br.SENTINEL_STATE, br.SENTINEL_CHASE), (br.SENTINEL_HEALTH, 3), (br.SENTINEL_COOLDOWN, 0),
                                   (br.SENTINEL_KIND, 0), (br.DIFFICULTY, 1)):
                cgb.write8(address, value)
            for _ in range(6):
                cgb.call_subroutine("sentinel_ai_tick", max_steps=400_000)
            health = cgb.read8(br.PLAYER_HEALTH)
            if expect_hit:
                self.assertLess(health, 99, "a clean diagonal must still land a blow")
            else:
                self.assertEqual(health, 99, "an actor struck through a wall corner")

    def test_a_medkit_tops_health_up_to_ninety_nine_and_no_further(self):
        from playtest import set_test_world_byte
        from sm83emu import CGB, run_to_world
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        for health, expected in ((50, 75), (90, 99), (99, 99)):
            px, py = cgb.read8(br.PLAYER_XH), cgb.read8(br.PLAYER_YH)
            for address, value in ((br.PLAYER_HEALTH, health), (br.PICKUP_ACTIVE, 1), (br.PICKUP_COLLECTED, 0),
                                   (br.SENTINEL_XH, px), (br.SENTINEL_YH, py), (br.SENTINEL_STATE, br.SENTINEL_DEAD),
                                   (br.ENTITY_SLOTS + br.ACTOR_KIND_OFFSET, 0)):
                set_test_world_byte(cgb, address, value)
            cgb.write8(br.LEVEL_PICKUP_VALUE, 25)
            cgb.call_subroutine("collect_pickup_and_exit", max_steps=200_000)
            # With items the drop is item 0, Sable's medkit (+25), and one
            # with nothing to give stays on the floor; the engine's own
            # medkit is always taken.
            taken = health < 99 or not br.ITEM_DROPS
            self.assertEqual(cgb.read8(br.PICKUP_COLLECTED), int(taken), health)
            self.assertEqual(cgb.read8(br.PLAYER_HEALTH), expected, health)


if __name__ == "__main__":
    unittest.main()
