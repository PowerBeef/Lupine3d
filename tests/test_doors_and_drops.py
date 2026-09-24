"""Keyed doors, and what an actor leaves behind when it dies."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4 import levels as level_codec  # noqa: E402
from lupine3d_v4.levels import (  # noqa: E402
    DOOR_FLAG_EXIT, DOOR_FLAG_KEYCARD, DOOR_FLAG_LOCK_SENTINEL, DROP_KIND_IDS,
    KIND_DROPS,
)
from sm83emu import CGB, run_to_world  # noqa: E402


class DropTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()
        start = cls.asm.labels["actor_kind_stats"]
        size = br.ACTOR_KIND_RECORD_BYTES
        cls.stats = [cls.rom[start + i * size:start + (i + 1) * size] for i in range(4)]

    def test_each_kind_drops_what_the_compiler_says_it_drops(self):
        for kind, index in level_codec.ENTITY_KIND_IDS.items():
            self.assertEqual(self.stats[index][br.ACTOR_KIND_DROP],
                             DROP_KIND_IDS[KIND_DROPS[kind]], kind)
        # The kind byte is masked to two bits, so the spares must still drop
        # something a player can use.
        for spare in self.stats[len(level_codec.ENTITY_KIND_IDS):]:
            self.assertIn(spare[br.ACTOR_KIND_DROP], set(DROP_KIND_IDS.values()))

    def test_a_drop_cel_exists_for_every_drop_kind(self):
        # render_dropped_pickup adds the drop id to PICKUP_TILE, so the cels
        # must be consecutive and inside the reserved pair.
        self.assertEqual(br.HIT_EFFECT_TILE_BASE - br.PICKUP_TILE, len(DROP_KIND_IDS))
        tiles = br.make_entity_tiles()
        for kind, index in DROP_KIND_IDS.items():
            cel = tiles[(br.PICKUP_TILE + index) * 16:(br.PICKUP_TILE + index + 1) * 16]
            self.assertNotEqual(cel, bytes(16), f"{kind} has no cel")
        medkit = tiles[br.PICKUP_TILE * 16:(br.PICKUP_TILE + 1) * 16]
        keycard = tiles[(br.PICKUP_TILE + 1) * 16:(br.PICKUP_TILE + 2) * 16]
        self.assertNotEqual(medkit, keycard, "the two drops must look different")


class CompiledDoorTests(unittest.TestCase):
    def test_the_campaign_uses_keyed_doors_and_compiles_their_flag(self):
        keyed = [(level.name, door.name) for level in br.CAMPAIGN
                 for door in level.doors if door.flags & DOOR_FLAG_KEYCARD]
        self.assertTrue(keyed, "no level locks a door behind a card")
        for level in br.CAMPAIGN:
            payload = level.door_bytes()
            for index, door in enumerate(level.doors):
                self.assertEqual(payload[index * br.DOOR_RECORD_BYTES + br.DOOR_FLAGS_OFFSET],
                                 door.flags, (level.name, door.name))
                # A card door is never also the Sentinel-locked exit: the two
                # refusals have to stay tellable apart.
                if door.flags & DOOR_FLAG_KEYCARD:
                    self.assertFalse(door.flags & (DOOR_FLAG_EXIT | DOOR_FLAG_LOCK_SENTINEL))

    def test_a_keyed_level_declares_the_drop_that_opens_it(self):
        for level in br.CAMPAIGN:
            kinds = {pickup.kind for pickup in level.pickups}
            if any(door.flags & DOOR_FLAG_KEYCARD for door in level.doors):
                self.assertIn("keycard", kinds, level.name)
            self.assertIn("medkit", kinds, level.name)
            for kind in kinds:
                self.assertIn(kind, {KIND_DROPS[e.kind] for e in level.entities}, level.name)


class CompilerRefusalTests(unittest.TestCase):
    """The certificate has to refuse a level nobody could finish."""

    @staticmethod
    def _source(name="vent_stacks.json"):
        return json.loads((ROOT / "games" / "sable_outpost" / "levels" / name).read_text())

    def _compile(self, source):
        # compile_level reads a path, so round-trip the edited source through
        # one, exactly as the build does.
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "level.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            return level_codec.compile_level(path)

    def test_the_authored_levels_still_compile(self):
        self.assertIsNotNone(self._compile(self._source()))

    def test_a_card_door_with_no_card_dropper_is_refused(self):
        source = self._source()
        for entity in source["entities"]:
            entity["kind"] = "sentinel"          # nothing here carries a card
        with self.assertRaises(ValueError):
            self._compile(source)

    def test_a_declared_drop_no_actor_leaves_is_refused(self):
        source = self._source("living_world.json")
        source["pickups"].append({"kind": "keycard", "source": "sentinel_drop", "value": 1})
        with self.assertRaises(ValueError):
            self._compile(source)

    def test_a_card_drop_that_opens_nothing_is_refused(self):
        source = self._source("coolant_spine.json")
        source["pickups"].append({"kind": "keycard", "source": "sentinel_drop", "value": 1})
        with self.assertRaises(ValueError):
            self._compile(source)

    def test_a_level_with_no_medkit_drop_is_refused(self):
        source = self._source()
        source["pickups"] = [p for p in source["pickups"] if p["kind"] != "medkit"]
        with self.assertRaises(ValueError):
            self._compile(source)

    def test_a_card_locked_behind_its_own_door_is_refused(self):
        # Move every card dropper behind the door its card opens.
        source = copy.deepcopy(self._source())
        level = self._compile(self._source())
        keyed = next(d for d in level.doors if d.flags & DOOR_FLAG_KEYCARD)
        from lupine3d_v4.levels import _passable_cells, _reachable_cells
        passable = _passable_cells(level.grid, level.width, level.height)
        start = (level.player_x_q8 >> 8, level.player_y_q8 >> 8)
        before = _reachable_cells(passable - {(keyed.x, keyed.y)}, start)
        beyond = next(cell for cell in sorted(passable - before - {(keyed.x, keyed.y)}))
        for entity, authored in zip(source["entities"], level.entities):
            if KIND_DROPS[authored.kind] == "keycard":
                entity["x_q8"] = (beyond[0] << 8) | 0x80
                entity["y_q8"] = (beyond[1] << 8) | 0x80
        with self.assertRaises(ValueError):
            self._compile(source)


class KeycardRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def _sector(self, index):
        """Run to the world, then load the campaign sector that has a card door."""
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        cgb.io[br.SVBK & 0x7F] = 2
        cgb.write8(br.LEVEL_INDEX, index)
        cgb.call_subroutine("select_level", max_steps=200_000)
        cgb.call_subroutine("load_level", max_steps=2_000_000)
        cgb.call_subroutine("init_actors", max_steps=2_000_000)
        return cgb

    @staticmethod
    def _keyed_sector():
        for index, level in enumerate(br.CAMPAIGN):
            for door in level.doors:
                if door.flags & DOOR_FLAG_KEYCARD:
                    return index, level, door
        raise AssertionError("no campaign level locks a door behind a card")

    def test_loading_a_sector_takes_the_card_away(self):
        index, _, _ = self._keyed_sector()
        cgb = self._sector(index)
        cgb.write8(br.PLAYER_KEYS, 1)
        cgb.call_subroutine("load_level", max_steps=2_000_000)
        self.assertEqual(cgb.read8(br.PLAYER_KEYS), 0)

    def _try_door(self, cgb, door, keys):
        """Stand one cell west of the door, face it, and press the use key."""
        cgb.write8(br.PLAYER_KEYS, keys)
        base = br.DOOR_TABLE + self._door_index(cgb, door) * br.DOOR_RECORD_BYTES
        cgb.write8(base + br.DOOR_STATE_OFFSET, 0)
        cgb.write8(br.PLAYER_XL, 0x80); cgb.write8(br.PLAYER_XH, door.x - 1)
        cgb.write8(br.PLAYER_YL, 0x80); cgb.write8(br.PLAYER_YH, door.y)
        cgb.write8(br.ANGLE, 0)                       # +x, at the door
        cgb.call_subroutine("open_door", max_steps=500_000)
        return cgb.read8(base + br.DOOR_STATE_OFFSET)

    @staticmethod
    def _door_index(cgb, door):
        for index in range(cgb.read8(br.DOOR_COUNT)):
            base = br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES
            if (cgb.read8(base + br.DOOR_X_OFFSET), cgb.read8(base + br.DOOR_Y_OFFSET)) == (door.x, door.y):
                return index
        raise AssertionError("the loaded level does not carry that door")

    def test_a_card_door_refuses_an_empty_hand_and_opens_for_a_card(self):
        index, _, door = self._keyed_sector()
        cgb = self._sector(index)
        self.assertEqual(self._try_door(cgb, door, keys=0), 0, "it opened without a card")
        self.assertEqual(self._try_door(cgb, door, keys=1), 1, "it stayed shut with a card")

    def test_taking_a_skirmishers_drop_puts_a_card_in_hand(self):
        index, level, _ = self._keyed_sector()
        cgb = self._sector(index)
        slot = next(i for i, e in enumerate(level.entities) if KIND_DROPS[e.kind] == "keycard")
        cgb.write8(br.ENTITY_SLOT, slot)
        cgb.call_subroutine("actor_load", max_steps=100_000)
        cgb.write8(br.SENTINEL_STATE, br.SENTINEL_DEAD)
        cgb.write8(br.PICKUP_ACTIVE, 1)
        cgb.write8(br.PLAYER_KEYS, 0)
        health = cgb.read8(br.PLAYER_HEALTH)
        for address in (br.PLAYER_XL, br.PLAYER_YL): cgb.write8(address, 0x80)
        cgb.write8(br.PLAYER_XH, cgb.read8(br.SENTINEL_XH))
        cgb.write8(br.PLAYER_YH, cgb.read8(br.SENTINEL_YH))
        cgb.call_subroutine("collect_pickup_and_exit", max_steps=500_000)
        self.assertEqual(cgb.read8(br.PICKUP_ACTIVE), 0)
        self.assertEqual(cgb.read8(br.PLAYER_KEYS), 1)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), health, "a card is not a medkit")

    def test_taking_a_sentinels_drop_still_heals(self):
        index, level, _ = self._keyed_sector()
        cgb = self._sector(index)
        slot = next(i for i, e in enumerate(level.entities) if KIND_DROPS[e.kind] == "medkit")
        cgb.write8(br.ENTITY_SLOT, slot)
        cgb.call_subroutine("actor_load", max_steps=100_000)
        cgb.write8(br.SENTINEL_STATE, br.SENTINEL_DEAD)
        cgb.write8(br.PICKUP_ACTIVE, 1)
        cgb.write8(br.PLAYER_KEYS, 0)
        cgb.write8(br.PLAYER_HEALTH, 10)
        for address in (br.PLAYER_XL, br.PLAYER_YL): cgb.write8(address, 0x80)
        cgb.write8(br.PLAYER_XH, cgb.read8(br.SENTINEL_XH))
        cgb.write8(br.PLAYER_YH, cgb.read8(br.SENTINEL_YH))
        cgb.call_subroutine("collect_pickup_and_exit", max_steps=500_000)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), 10 + level.medkit_value)
        self.assertEqual(cgb.read8(br.PLAYER_KEYS), 0, "a medkit is not a card")


if __name__ == "__main__":
    unittest.main()
