"""Placed items, ammunition pools, coloured card doors and triggers."""
import copy
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


def compile_variant(change) -> level_codec.CompiledLevel:
    """The fixture with `change(data)` applied, compiled from a scratch file."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    change(data)
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "variant.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return level_codec.compile_level(path)


class ItemArtTests(unittest.TestCase):
    def test_the_item_sheet_is_what_its_script_makes(self):
        import subprocess
        result = subprocess.run([sys.executable, str(ROOT / "games" / "sable_outpost" / "art" / "tools" / "make_item_art.py"),
                                 "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CompilerTests(unittest.TestCase):
    def test_the_fixture_compiles_its_items_loadout_and_trigger(self):
        level = level_codec.compile_level(FIXTURE)
        ids = GAME.item_ids
        self.assertEqual(level.items, ((2, 13, ids["stim"]), (3, 12, ids["slugs"]), (2, 2, ids["amber card"]),
                                       (8, 2, ids["armour"]), (9, 7, ids["cells"])))
        self.assertEqual(level.loadout, (3, 0, 0))
        doors = {door.name: index for index, door in enumerate(level.doors)}
        self.assertEqual(level.triggers, ((2, 9, doors["bunk_room"]),))
        self.assertTrue(level.doors[doors["bunk_room"]].flags & level_codec.DOOR_FLAG_REMOTE)
        mess = level.doors[doors["mess_hatch"]].flags
        self.assertEqual(mess >> level_codec.DOOR_KEY_SHIFT, GAME.keys.index("amber") + 1)
        extras = level.extras_bytes()
        self.assertEqual(len(extras), level_codec.EXTRAS_BYTES)
        self.assertEqual(extras[0], 5)
        self.assertEqual(extras[level_codec.EXTRAS_ITEMS:level_codec.EXTRAS_ITEMS + 2], bytes(((13 << 4) | 2, ids["stim"])))
        self.assertEqual(extras[level_codec.EXTRAS_LOADOUT:level_codec.EXTRAS_LOADOUT + 3], bytes((3, 0, 0)))
        self.assertEqual(extras[level_codec.EXTRAS_TRIGGER_COUNT], 1)

    def test_a_level_without_a_loadout_has_infinite_pools(self):
        level = compile_variant(lambda data: data.pop("loadout"))
        self.assertEqual(level.loadout, (level_codec.INFINITE_AMMO, level_codec.INFINITE_AMMO, 0))
        for shipped in br.CAMPAIGN:
            if not shipped.items:
                self.assertEqual(shipped.extras_bytes()[level_codec.EXTRAS_LOADOUT:level_codec.EXTRAS_LOADOUT + 2],
                                 bytes((255, 255)), shipped.name)

    def test_what_the_compiler_refuses(self):
        def drop_trigger(data):
            data["triggers"] = [t for t in data["triggers"] if t["kind"] != "open_door"]

        def teal_door(data):
            next(d for d in data["doors"] if d["id"] == "mess_hatch")["key"] = "teal"

        def item_in_a_wall(data):
            data["items"][0].update(x=0 + 1, y=0 + 5)

        def two_items_one_cell(data):
            data["items"][1].update(x=2, y=13)

        def trigger_behind_its_door(data):
            next(t for t in data["triggers"] if t["kind"] == "open_door").update(x=2, y=3)

        def unknown_item(data):
            data["items"][0]["item"] = "banana"

        cases = ((drop_trigger, "no trigger that opens it"), (teal_door, "can never be opened"),
                 (item_in_a_wall, "not on a walkable cell"), (two_items_one_cell, "shares its cell"),
                 (trigger_behind_its_door, "can never be opened"), (unknown_item, "not one of"))
        for change, message in cases:
            with self.subTest(change.__name__):
                with self.assertRaisesRegex(ValueError, message):
                    compile_variant(change)


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rom, cls.asm, _ = br.make_rom()
        # The fixture in the first sector's slot, as the evidence population is.
        image = bytearray(rom)
        payload = br.make_level_payload(level_codec.compile_level(FIXTURE))
        start = br.level_rom_offset(0)
        image[start:start + len(payload)] = payload
        cls.rom = bytes(image)

    def world(self):
        from sm83emu import CGB, run_to_world
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.rom_bank = 1
        return cgb

    def live(self, cgb, address, value=None):
        """Read, or write, the simulation's live world (WRAM bank 2)."""
        cgb.io[br.SVBK & 0x7F] = 2
        if value is None:
            return cgb.read8(address)
        cgb.write8(address, value)

    def stand_on(self, cgb, x, y):
        for address, value in ((br.PLAYER_XL, 128), (br.PLAYER_XH, x), (br.PLAYER_YL, 128), (br.PLAYER_YH, y)):
            self.live(cgb, address, value)
        cgb.call_subroutine("update_placed", max_steps=200_000)

    def test_the_loader_puts_the_items_in_both_banks_and_fills_the_pools(self):
        cgb = self.world()
        level = level_codec.compile_level(FIXTURE)
        table = level.extras_bytes()[:br.ITEM_TABLE_END - br.ITEM_TABLE]
        for bank in (1, 2):
            cgb.io[br.SVBK & 0x7F] = bank
            self.assertEqual(bytes(cgb.read8(br.ITEM_TABLE + i) for i in range(len(table))), table, bank)
        cgb.io[br.SVBK & 0x7F] = 2
        self.assertEqual(bytes(cgb.read8(br.TRIGGER_TABLE + i) for i in range(2)), bytes(((9 << 4) | 2, 1)))
        self.assertEqual((cgb.read8(br.AMMO), cgb.read8(br.AMMO + 1), cgb.read8(br.PLAYER_ARMOUR)), (3, 0, 0))
        self.assertEqual(cgb.read8(br.LEVEL_TRIGGER_COUNT), 1)
        self.assertEqual((cgb.read8(br.ITEMS_TAKEN), cgb.read8(br.ITEMS_TAKEN + 1), cgb.read8(br.TRIGGERS_FIRED)), (0, 0, 0))

    def test_play_leaves_the_bank_two_tables_alone(self):
        """The simulation's item and trigger records sit in bank-2 ranges
        nothing else uses: firing (whose hitscan projects every actor with
        bank 2 mapped), turning and rendering must leave them as loaded."""
        cgb = self.world()
        level = level_codec.compile_level(FIXTURE)
        extras = level.extras_bytes()
        items = extras[:br.ITEM_TABLE_END - br.ITEM_TABLE]
        triggers = extras[level_codec.EXTRAS_TRIGGERS:level_codec.EXTRAS_TRIGGERS + br.TRIGGER_TABLE_END - br.TRIGGER_TABLE]
        cgb.button_provider = lambda frame, *_: 0x10 | 0x01 if frame % 2 else 0x01   # fire, turning right
        for _ in range(40):
            cgb.run(until_presentations=cgb.presentations + 1, max_steps=6_000_000)
        cgb.diagnostic_barrier()
        self.assertEqual(bytes(cgb.wramx[2][br.ITEM_TABLE - 0xD000:br.ITEM_TABLE_END - 0xD000]), items)
        self.assertEqual(bytes(cgb.wramx[2][br.TRIGGER_TABLE - 0xD000:br.TRIGGER_TABLE_END - 0xD000]), triggers)
        self.assertEqual(bytes(cgb.wramx[1][br.ITEM_TABLE - 0xD000:br.ITEM_TABLE_END - 0xD000]), items)

    def test_walking_onto_items_takes_them_once(self):
        cgb = self.world()
        self.live(cgb, br.PLAYER_HEALTH, 50)
        self.stand_on(cgb, 2, 13)                              # the stim: +10
        self.assertEqual(self.live(cgb, br.PLAYER_HEALTH), 60)
        self.assertEqual(self.live(cgb, br.ITEMS_TAKEN) & 1, 1)
        self.stand_on(cgb, 2, 13)                              # taken: nothing more
        self.assertEqual(self.live(cgb, br.PLAYER_HEALTH), 60)
        self.stand_on(cgb, 3, 12)                              # six slugs on top of three
        self.assertEqual(self.live(cgb, br.AMMO), 9)
        self.stand_on(cgb, 9, 7)                               # twenty cells
        self.assertEqual(self.live(cgb, br.AMMO + 1), 20)
        self.stand_on(cgb, 8, 2)                               # armour
        self.assertEqual(self.live(cgb, br.PLAYER_ARMOUR), 50)
        self.stand_on(cgb, 2, 2)                               # the amber card
        self.assertEqual(self.live(cgb, br.PLAYER_KEYS), 1 << GAME.keys.index("amber"))
        self.assertEqual(self.live(cgb, br.ITEMS_TAKEN), 0b11111)

    def test_an_item_with_nothing_to_give_stays_on_the_floor(self):
        cgb = self.world()
        self.live(cgb, br.PLAYER_HEALTH, 99)
        self.stand_on(cgb, 2, 13)
        self.assertEqual(self.live(cgb, br.ITEMS_TAKEN) & 1, 0, "a stim at full health was taken")
        self.live(cgb, br.AMMO, br.INFINITE_AMMO)
        self.stand_on(cgb, 3, 12)
        self.assertEqual(self.live(cgb, br.ITEMS_TAKEN) & 2, 0, "slugs were taken into an infinite pool")
        self.live(cgb, br.PLAYER_HEALTH, 98)
        self.stand_on(cgb, 2, 13)
        self.assertEqual(self.live(cgb, br.PLAYER_HEALTH), 99)
        self.assertEqual(self.live(cgb, br.ITEMS_TAKEN) & 1, 1)

    def test_a_trigger_opens_its_remote_door_once(self):
        cgb = self.world()
        door = next(i for i, d in enumerate(level_codec.compile_level(FIXTURE).doors) if d.name == "bunk_room")
        state = br.DOOR_TABLE + door * br.DOOR_RECORD_BYTES + br.DOOR_STATE_OFFSET
        self.assertEqual(self.live(cgb, state), 0)
        self.stand_on(cgb, 2, 9)
        self.assertEqual(self.live(cgb, state), 1, "the trigger did not start the door")
        self.assertEqual(cgb.read8(br.TRIGGERS_FIRED), 1)

    def test_b_refuses_a_remote_door_and_a_card_door_wants_its_colour(self):
        cgb = self.world()
        level = level_codec.compile_level(FIXTURE)
        for name, keys, opens in (("bunk_room", 3, False), ("mess_hatch", 0, False),
                                  ("mess_hatch", 1 << GAME.keys.index("teal"), False),
                                  ("mess_hatch", 1 << GAME.keys.index("amber"), True)):
            index = next(i for i, d in enumerate(level.doors) if d.name == name)
            door = level.doors[index]
            state = br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES + br.DOOR_STATE_OFFSET
            self.live(cgb, state, 0)
            self.live(cgb, br.PLAYER_KEYS, keys)
            # Face the door from an open cell beside it, near enough that
            # B's two quarter-cell steps reach it, as the route does.
            below = level.grid[(door.y + 1) * 16 + door.x] == 0
            for address, value in ((br.PLAYER_XL, 128), (br.PLAYER_XH, door.x), (br.PLAYER_YL, 0x40 if below else 0xC0),
                                   (br.PLAYER_YH, door.y + (1 if below else -1)), (br.ANGLE, 192 if below else 64)):
                self.live(cgb, address, value)
            cgb.call_subroutine("open_door", max_steps=400_000)
            self.assertEqual(self.live(cgb, state) == 1, opens, (name, keys))

    def test_a_dry_weapon_refuses_the_shot_and_falls_back_to_the_first(self):
        cgb = self.world()
        rifle = next(i for i, w in enumerate(GAME.weapons) if w.ammo is not None)
        cgb.write8(br.WEAPON_INDEX, rifle)
        pool = GAME.ammo.index(GAME.weapons[rifle].ammo)
        self.live(cgb, br.AMMO + pool, 1)
        cgb.call_subroutine("fire_ammo", max_steps=100_000)
        self.assertFalse(cgb.f & 0x10, "a loaded weapon was refused")
        self.assertEqual(self.live(cgb, br.AMMO + pool), 0)
        cgb.call_subroutine("fire_ammo", max_steps=100_000)
        self.assertTrue(cgb.f & 0x10, "an empty weapon fired")
        self.assertEqual(cgb.read8(br.WEAPON_INDEX), 0)
        self.assertEqual(cgb.read8(br.WEAPON_RELOAD), 1)
        cgb.write8(br.WEAPON_INDEX, rifle)
        self.live(cgb, br.AMMO + pool, br.INFINITE_AMMO)
        cgb.call_subroutine("fire_ammo", max_steps=100_000)
        self.assertFalse(cgb.f & 0x10)
        self.assertEqual(self.live(cgb, br.AMMO + pool), br.INFINITE_AMMO, "an infinite pool was spent")

    @unittest.skipUnless(br.ITEM_CEL_NAMES, "the legacy profile draws no placed items")
    def test_the_renderer_draws_untaken_items_near_the_player(self):
        from sm83emu import CGB
        cgb = self.world()
        # Stand in the spawn room facing the stim and the slugs.
        cgb.io[br.SVBK & 0x7F] = 1
        before = cgb.read8(br.SENTINEL_OAM_USED)
        for address, value in ((br.PLAYER_XL, 128), (br.PLAYER_XH, 4), (br.PLAYER_YL, 128), (br.PLAYER_YH, 13),
                               (br.ANGLE, 128)):
            cgb.write8(address, value)
        cgb.call_subroutine("cast_all", max_steps=4_000_000)
        cgb.call_subroutine("render_entities", max_steps=4_000_000)
        drawn = cgb.read8(br.SENTINEL_OAM_USED)
        self.assertGreaterEqual(drawn, 1, "no item was drawn")
        cgb.write8(br.ITEMS_TAKEN, 0b11)
        cgb.call_subroutine("render_entities", max_steps=4_000_000)
        self.assertLess(cgb.read8(br.SENTINEL_OAM_USED), drawn, "a taken item was still drawn")
        del before


if __name__ == "__main__":
    unittest.main()
