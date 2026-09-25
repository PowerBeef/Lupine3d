"""What an actor leaves when it dies, and when it wakes."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4 import levels as level_codec  # noqa: E402
from lupine3d_v4.game import GAME  # noqa: E402

FIXTURE = ROOT / "tests" / "levels" / "placed_items.json"


def variant(change) -> level_codec.CompiledLevel:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    change(data)
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "variant.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return level_codec.compile_level(path)


def cells_sentry(data):
    data["entities"][0].update(drop="cells", wake=2, sight=True)


@unittest.skipUnless(level_codec.ITEM_DROPS, "the game drops the engine's own medkit and keycard")
class CompilerTests(unittest.TestCase):
    def test_an_actor_leaves_its_kinds_drop_unless_its_level_names_another(self):
        default = level_codec.compile_level(FIXTURE)
        kind = GAME.kinds[level_codec.ENTITY_KIND_IDS[default.entities[0].kind]]
        self.assertEqual(default.entities[0].drop, GAME.item_ids[kind.drop])
        level = variant(cells_sentry)
        self.assertEqual(level.entities[0].drop, GAME.item_ids["cells"])
        self.assertEqual(variant(lambda d: d["entities"][0].update(drop="none")).entities[0].drop, level_codec.NO_DROP)
        drops = level.extras_bytes()[level_codec.EXTRAS_DROPS:level_codec.EXTRAS_DROPS + br.MAX_ACTORS]
        self.assertEqual(drops, bytes((GAME.item_ids["cells"],)) + bytes((level_codec.NO_DROP,)) * (br.MAX_ACTORS - 1))

    def test_wake_and_sight_ride_the_kind_byte(self):
        entity = variant(cells_sentry).entities[0]
        kind = level_codec.ENTITY_KIND_IDS[entity.kind]
        self.assertEqual(entity.kind_byte, kind | (level_codec.WAKE_RADII[2] << level_codec.KIND_WAKE_SHIFT) | level_codec.KIND_SIGHT)
        self.assertEqual(entity.kind_byte & 3, kind, "every reader masks the kind to two bits")
        self.assertEqual(level_codec.compile_level(FIXTURE).entities[0].kind_byte, kind, "no key, no flags")

    def test_what_the_compiler_refuses(self):
        for change, message in ((lambda d: d["entities"][0].update(wake=3), "wake is 3"),
                                (lambda d: d["entities"][0].update(drop="banana"), "drop 'banana' is not one of"),
                                (lambda d: d["entities"][0].update(sight="yes"), "sight is true or false")):
            with self.assertRaisesRegex(ValueError, message):
                variant(change)

    def test_a_card_carrier_opens_its_door_in_the_certificate(self):
        # The mess hatch wants amber. Without the placed card, a skirmisher in
        # the corridor (whose kind drops one) keeps the level solvable; told to
        # drop nothing it does not. The sentinel cannot carry it: it stands
        # behind that very hatch.
        def carrier(data, drop):
            data["items"] = [item for item in data["items"] if item["item"] != "amber card"]
            data["entities"].append({"kind": "skirmisher", "x_q8": 2 * 256 + 128, "y_q8": 9 * 256 + 128,
                                     "health": 2, "activation_radius_q4": 96, **({"drop": drop} if drop else {})})
        variant(lambda d: carrier(d, None))
        with self.assertRaisesRegex(ValueError, "mess_hatch can never be opened"):
            variant(lambda d: carrier(d, "none"))
        with self.assertRaisesRegex(ValueError, "mess_hatch can never be opened"):
            variant(lambda d: (carrier(d, None), d["entities"][0].update(drop="amber card"),
                               d["entities"].pop()))


@unittest.skipUnless(level_codec.ITEM_DROPS, "the game drops the engine's own medkit and keycard")
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rom, cls.asm, _ = br.make_rom()
        image = bytearray(rom)
        payload = br.make_level_payload(variant(cells_sentry))
        start = br.level_rom_offset(0)
        image[start:start + len(payload)] = payload
        cls.rom = bytes(image)

    def world(self):
        from sm83emu import CGB, run_to_world
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        cgb.io[br.SVBK & 0x7F] = 2
        return cgb

    def test_the_loader_puts_each_actors_drop_in_bank_six(self):
        cgb = self.world()
        self.assertEqual(cgb.wramx[br.SIM_EXTRAS_BANK][br.ACTOR_DROP - 0xD000], GAME.item_ids["cells"])
        self.assertEqual(cgb.io[br.SVBK & 0x7F], 2)

    def test_a_kill_leaves_the_actors_item_and_taking_it_applies_it(self):
        cgb = self.world()
        cgb.write8(br.ENTITY_SLOT, 0)
        cgb.call_subroutine("actor_drop_item", max_steps=100_000)
        self.assertEqual(cgb.a, GAME.item_ids["cells"] + 1)
        self.assertEqual(cgb.io[br.SVBK & 0x7F], 2, "the drop lookup must put the live world back")
        px, py = cgb.read8(br.PLAYER_XH), cgb.read8(br.PLAYER_YH)
        for address, value in ((br.SENTINEL_XH, px), (br.SENTINEL_YH, py), (br.SENTINEL_STATE, br.SENTINEL_DEAD),
                               (br.PICKUP_ACTIVE, GAME.item_ids["cells"] + 1), (br.PICKUP_COLLECTED, 0),
                               (br.AMMO + GAME.ammo.index("cells"), 0), (br.EXIT_ACTIVE, 0)):
            cgb.write8(address, value)
        cgb.call_subroutine("collect_pickup_and_exit", max_steps=200_000)
        self.assertEqual(cgb.read8(br.AMMO + GAME.ammo.index("cells")), 20)
        self.assertEqual((cgb.read8(br.PICKUP_ACTIVE), cgb.read8(br.PICKUP_COLLECTED)), (0, 1))

    def test_a_drop_with_nothing_to_give_stays_down(self):
        cgb = self.world()
        px, py = cgb.read8(br.PLAYER_XH), cgb.read8(br.PLAYER_YH)
        for address, value in ((br.SENTINEL_XH, px), (br.SENTINEL_YH, py), (br.SENTINEL_STATE, br.SENTINEL_DEAD),
                               (br.PICKUP_ACTIVE, GAME.item_ids["medkit"] + 1), (br.PLAYER_HEALTH, 99), (br.EXIT_ACTIVE, 0)):
            cgb.write8(address, value)
        cgb.call_subroutine("collect_pickup_and_exit", max_steps=200_000)
        self.assertEqual(cgb.read8(br.PICKUP_ACTIVE), GAME.item_ids["medkit"] + 1)

    def test_a_sentry_wakes_inside_its_own_radius_and_only_with_sight(self):
        for distance, wall, wakes in ((3, False, False), (2, False, True), (2, True, False)):
            with self.subTest(distance=distance, wall=wall):
                cgb = self.world()
                for y in range(16):
                    for x in range(16):
                        cgb.write8(br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
                if wall:
                    cgb.write8(br.MAP + 5 * 16 + 6, 1)
                for address, value in ((br.PLAYER_XL, 128), (br.PLAYER_XH, 5), (br.PLAYER_YL, 128), (br.PLAYER_YH, 5),
                                       (br.SENTINEL_XL, 128), (br.SENTINEL_XH, 5 + distance), (br.SENTINEL_YL, 128),
                                       (br.SENTINEL_YH, 5), (br.SENTINEL_STATE, br.SENTINEL_DORMANT), (br.DOOR_COUNT, 0),
                                       (br.SENTINEL_KIND, (level_codec.WAKE_RADII[2] << level_codec.KIND_WAKE_SHIFT) | level_codec.KIND_SIGHT),
                                       (br.ACTIVATION_RADIUS, 15)):
                    cgb.write8(address, value)
                cgb.call_subroutine("sentinel_ai_tick", max_steps=400_000)
                self.assertEqual(cgb.read8(br.SENTINEL_STATE) != br.SENTINEL_DORMANT, wakes)


if __name__ == "__main__":
    unittest.main()


class CombatTests(unittest.TestCase):
    """Ranged kinds, armour and strafing, on an open synthetic room."""

    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def room(self, kind, distance, state=br.SENTINEL_CHASE):
        from sm83emu import CGB, run_to_world
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        cgb.io[br.SVBK & 0x7F] = 2
        for y in range(16):
            for x in range(16):
                cgb.write8(br.MAP + y * 16 + x, int(x in (0, 15) or y in (0, 15)))
        for address, value in ((br.PLAYER_XL, 128), (br.PLAYER_XH, 3), (br.PLAYER_YL, 128), (br.PLAYER_YH, 5),
                               (br.PLAYER_HEALTH, 99), (br.PLAYER_ARMOUR, 0), (br.DOOR_COUNT, 0), (br.DIFFICULTY, 1),
                               (br.SENTINEL_XL, 128), (br.SENTINEL_XH, 3 + distance), (br.SENTINEL_YL, 128),
                               (br.SENTINEL_YH, 5), (br.SENTINEL_STATE, state), (br.SENTINEL_HEALTH, 5),
                               (br.SENTINEL_COOLDOWN, 0), (br.SENTINEL_KIND, kind)):
            cgb.write8(address, value)
        return cgb

    def tick(self, cgb, count=1):
        for _ in range(count):
            cgb.call_subroutine("sentinel_ai_tick", max_steps=400_000)

    def ranged_kind(self):
        kinds = [n for n, kind in enumerate(GAME.kinds) if kind.range]
        if not kinds:
            self.skipTest("the game has no ranged kind")
        return kinds[0], GAME.kinds[kinds[0]]

    def test_a_ranged_kind_aims_then_shoots_from_range(self):
        index, kind = self.ranged_kind()
        cgb = self.room(index, kind.range)
        self.tick(cgb)
        self.assertEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_AIM, "in sight and in reach it winds up")
        self.assertEqual((cgb.read8(br.SENTINEL_XH), cgb.read8(br.PLAYER_HEALTH)), (3 + kind.range, 99),
                         "it holds its ground and the wind-up is harmless")
        self.tick(cgb, kind.windup_ticks)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), 99 - kind.ranged_damage, "the shot lands after the wind-up")
        self.assertEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_CHASE)
        self.tick(cgb, 2)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), 99 - kind.ranged_damage, "it recovers before it aims again")

    def test_a_shot_needs_sight_and_reach(self):
        index, kind = self.ranged_kind()
        cgb = self.room(index, kind.range + 1)
        self.tick(cgb)
        self.assertNotEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_AIM, "out of reach it closes in")
        cgb = self.room(index, kind.range)
        cgb.write8(br.MAP + 5 * 16 + 4, 1)                      # a wall between them
        self.tick(cgb, kind.windup_ticks + 2)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), 99)

    def test_a_melee_kind_never_shoots(self):
        melee = next(n for n, kind in enumerate(GAME.kinds) if not kind.range)
        cgb = self.room(melee, 4)
        self.tick(cgb, 12)
        self.assertNotEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_AIM)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), 99)

    def test_armour_takes_half_of_a_blow_while_it_lasts(self):
        cgb = self.room(0, 1)
        for armour, damage, health, left in ((50, 8, 95, 46), (2, 8, 93, 0), (0, 8, 91, 0)):
            cgb.write8(br.PLAYER_ARMOUR, armour); cgb.write8(br.PLAYER_HEALTH, 99)
            cgb.b = damage
            cgb.call_subroutine("apply_player_damage", max_steps=10_000)
            self.assertEqual((cgb.read8(br.PLAYER_HEALTH), cgb.read8(br.PLAYER_ARMOUR)), (health, left), armour)

    def test_b_with_left_or_right_strafes_instead_of_turning(self):
        cgb = self.room(0, 8, state=br.SENTINEL_DORMANT)
        cgb.write8(br.ANGLE, 0)                                  # facing +x; left is -y
        for held, moved in ((0x22, -1), (0x21, 1)):
            cgb.write8(br.PLAYER_YL, 128); cgb.write8(br.PLAYER_YH, 5)
            cgb.write8(br.PREV_BUTTONS, held); cgb.write8(br.PRESSED, 0)
            cgb.call_subroutine("apply_input_actions", max_steps=200_000)
            y = cgb.read8(br.PLAYER_YH) * 256 + cgb.read8(br.PLAYER_YL)
            self.assertEqual(cgb.read8(br.ANGLE), 0, "a strafe keeps the aim")
            self.assertEqual((y > 5 * 256 + 128) - (y < 5 * 256 + 128), moved, held)


@unittest.skipUnless(br.CARRY_OVER, "the game does not carry the loadout between levels")
class CarryOverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def test_a_cleared_level_hands_the_next_what_the_player_carries(self):
        from sm83emu import CGB, run_to_world
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        cgb.io[br.SVBK & 0x7F] = 2
        for address, value in ((br.PLAYER_HEALTH, 31), (br.PLAYER_ARMOUR, 40), (br.AMMO, 12), (br.AMMO + 1, 55)):
            cgb.write8(address, value)
        cgb.write8(br.WEAPONS_OWNED, 0b1011)
        cgb.call_subroutine("store_carry", max_steps=100_000)
        self.assertEqual(cgb.io[br.SVBK & 0x7F], 2)
        self.assertEqual(bytes(cgb.wramx[br.SIM_EXTRAS_BANK][br.CARRY - 0xD000:br.CARRY_END - 0xD000]),
                         bytes((31, 40, 12, 55, 0b1011, 1)))
        # The next level: its loadout, then what was carried on top.
        cgb.io[br.SVBK & 0x7F] = 1
        for address, value in ((br.PLAYER_HEALTH, 99), (br.PLAYER_ARMOUR, 0), (br.AMMO, 20), (br.AMMO + 1, br.INFINITE_AMMO)):
            cgb.write8(address, value)
        cgb.write8(br.WEAPONS_OWNED, 0b0011)
        cgb.call_subroutine("apply_carry", max_steps=100_000)
        self.assertEqual([cgb.read8(a) for a in (br.PLAYER_HEALTH, br.PLAYER_ARMOUR, br.AMMO, br.AMMO + 1)],
                         [br.CARRY_MINIMUM_HEALTH, 40, 20, br.INFINITE_AMMO])
        self.assertEqual(cgb.read8(br.WEAPONS_OWNED), 0b1011)
        self.assertEqual(cgb.io[br.SVBK & 0x7F], 1)
        # A new run starts from the loadout.
        cgb.call_subroutine("clear_carry", max_steps=100_000)
        cgb.write8(br.PLAYER_HEALTH, 99)
        cgb.call_subroutine("apply_carry", max_steps=100_000)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), 99)
