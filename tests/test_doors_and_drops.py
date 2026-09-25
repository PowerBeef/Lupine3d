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
from lupine3d_v4.game import GAME  # noqa: E402

FIXTURE = ROOT / "tests" / "levels" / "placed_items.json"


def drop_effect(entity):
    """What an actor's drop does: an item effect with items, else the engine's drop name."""
    if level_codec.ITEM_DROPS:
        return None if entity.drop == level_codec.NO_DROP else GAME.items[entity.drop].effect
    return {"medkit": "health", "keycard": "key"}[KIND_DROPS[entity.kind]]


def pickup_byte(entity):
    """PICKUP_ACTIVE as a kill leaves it."""
    return entity.drop + 1 if level_codec.ITEM_DROPS else 1


class DropTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()
        start = cls.asm.labels["actor_kind_stats"]
        size = br.ACTOR_KIND_RECORD_BYTES
        cls.stats = [cls.rom[start + i * size:start + (i + 1) * size] for i in range(4)]

    def test_each_kind_drops_what_the_compiler_says_it_drops(self):
        # The table's drop byte is the engine's own drop; a game with items
        # drops item types from the level's actor drops (bank 6), and the
        # byte reads the medkit for any of them.
        for kind, index in level_codec.ENTITY_KIND_IDS.items():
            self.assertEqual(self.stats[index][br.ACTOR_KIND_DROP],
                             DROP_KIND_IDS.get(KIND_DROPS[kind], 0), kind)
        if level_codec.ITEM_DROPS:
            for level in br.CAMPAIGN:
                drops = level.extras_bytes()[level_codec.EXTRAS_DROPS:level_codec.EXTRAS_DROPS + len(level.entities)]
                self.assertEqual(list(drops), [entity.drop for entity in level.entities], level.name)
        # The kind byte is masked to two bits, so the spares must still drop
        # something a player can use.
        for spare in self.stats[len(level_codec.ENTITY_KIND_IDS):]:
            self.assertIn(spare[br.ACTOR_KIND_DROP], set(DROP_KIND_IDS.values()))

    def test_a_drop_cel_exists_for_every_drop_kind(self):
        # render_dropped_pickup adds the drop id times PICKUP_STRIDE to
        # PICKUP_TILE. A drop is the top of an 8x16 object, so on the Sable
        # profiles the pattern after each cel is empty: packed, the medkit
        # was drawn over the keycard and the keycard over the hit effect.
        stride = br.PICKUP_STRIDE
        self.assertEqual(stride, 2 if br.SABLE_ART else 1)
        self.assertEqual(br.HIT_EFFECT_TILE_BASE - br.PICKUP_TILE, len(DROP_KIND_IDS) * stride)
        tiles = br.make_entity_tiles()
        cels = {}
        for kind, index in DROP_KIND_IDS.items():
            tile = br.PICKUP_TILE + index * stride
            cels[kind] = tiles[tile * 16:(tile + 1) * 16]
            self.assertNotEqual(cels[kind], bytes(16), f"{kind} has no cel")
            if stride == 2:
                self.assertEqual(tiles[(tile + 1) * 16:(tile + 2) * 16], bytes(16), f"{kind} draws over another cel")
        self.assertNotEqual(cels["medkit"], cels["keycard"], "the two drops must look different")


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

    def test_a_keyed_level_has_a_card_for_its_doors(self):
        for level in br.CAMPAIGN:
            if not any(door.flags & DOOR_FLAG_KEYCARD for door in level.doors):
                continue
            placed = level_codec.ITEM_DROPS and any(GAME.items[kind].effect == "key" for _, _, kind in level.items)
            dropped = any(drop_effect(entity) == "key" for entity in level.entities)
            self.assertTrue(placed or dropped, level.name)
            if not level_codec.ITEM_DROPS:
                kinds = {pickup.kind for pickup in level.pickups}
                self.assertIn("keycard", kinds, level.name)
                self.assertIn("medkit", kinds, level.name)


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

    @staticmethod
    def _fixture():
        return json.loads(FIXTURE.read_text())

    def test_the_authored_levels_still_compile(self):
        self.assertIsNotNone(self._compile(self._fixture() if level_codec.ITEM_DROPS else self._source()))

    def test_a_card_door_with_no_card_is_refused(self):
        if level_codec.ITEM_DROPS:
            source = self._fixture()
            source["items"] = [item for item in source["items"] if "card" not in item["item"]]
        else:
            source = self._source()
            for entity in source["entities"]:
                entity["kind"] = "sentinel"          # nothing here carries a card
        with self.assertRaises(ValueError):
            self._compile(source)

    @unittest.skipIf(level_codec.ITEM_DROPS, "a game with items drops item types; nothing is declared")
    def test_a_declared_drop_no_actor_leaves_is_refused(self):
        source = self._source("living_world.json")
        source["pickups"].append({"kind": "keycard", "source": "sentinel_drop", "value": 1})
        with self.assertRaises(ValueError):
            self._compile(source)

    @unittest.skipIf(level_codec.ITEM_DROPS, "a game with items drops item types; nothing is declared")
    def test_a_card_drop_that_opens_nothing_is_refused(self):
        source = self._source("coolant_spine.json")
        source["pickups"].append({"kind": "keycard", "source": "sentinel_drop", "value": 1})
        with self.assertRaises(ValueError):
            self._compile(source)

    @unittest.skipIf(level_codec.ITEM_DROPS, "a game with items drops item types; nothing is declared")
    def test_a_level_with_no_medkit_drop_is_refused(self):
        source = self._source()
        source["pickups"] = [p for p in source["pickups"] if p["kind"] != "medkit"]
        with self.assertRaises(ValueError):
            self._compile(source)

    def test_a_card_locked_behind_its_own_door_is_refused(self):
        # Move every card - placed, or carried by an actor - behind the door it opens.
        source = copy.deepcopy(self._fixture() if level_codec.ITEM_DROPS else self._source())
        level = self._compile(copy.deepcopy(source))
        keyed = next(d for d in level.doors if d.flags & DOOR_FLAG_KEYCARD)
        from lupine3d_v4.levels import _passable_cells, _reachable_cells
        passable = _passable_cells(level.grid, level.width, level.height)
        start = (level.player_x_q8 >> 8, level.player_y_q8 >> 8)
        before = _reachable_cells(passable - {(keyed.x, keyed.y)}, start)
        beyond = next(cell for cell in sorted(passable - before - {(keyed.x, keyed.y)}))
        for entity, authored in zip(source["entities"], level.entities):
            if drop_effect(authored) == "key":
                entity["x_q8"] = (beyond[0] << 8) | 0x80
                entity["y_q8"] = (beyond[1] << 8) | 0x80
        for item in source.get("items", []):
            if "card" in item["item"]:
                item["x"], item["y"] = beyond
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

    def _try_door(self, cgb, door, keys, level):
        """Stand on an open side of the door, near enough for B's reach, face
        it, and press the use key."""
        cgb.write8(br.PLAYER_KEYS, keys)
        base = br.DOOR_TABLE + self._door_index(cgb, door) * br.DOOR_RECORD_BYTES
        cgb.write8(base + br.DOOR_STATE_OFFSET, 0)
        for (dx, dy), angle, near in (((-1, 0), 0, (0xC0, 0x80)), ((1, 0), 128, (0x40, 0x80)),
                                      ((0, -1), 64, (0x80, 0xC0)), ((0, 1), 192, (0x80, 0x40))):
            if level.grid[(door.y + dy) * 16 + door.x + dx] == 0:
                break
        cgb.write8(br.PLAYER_XL, near[0]); cgb.write8(br.PLAYER_XH, door.x + dx)
        cgb.write8(br.PLAYER_YL, near[1]); cgb.write8(br.PLAYER_YH, door.y + dy)
        cgb.write8(br.ANGLE, angle)
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
        index, level, door = self._keyed_sector()
        cgb = self._sector(index)
        colour = (door.flags >> level_codec.DOOR_KEY_SHIFT) & 3
        card = colour or 1
        self.assertEqual(self._try_door(cgb, door, 0, level), 0, "it opened without a card")
        if colour:
            self.assertEqual(self._try_door(cgb, door, 3 ^ card, level), 0, "it opened for the other colour")
        self.assertEqual(self._try_door(cgb, door, card, level), 1, "it stayed shut with its card")

    @staticmethod
    def _dropping(effect):
        for index, level in enumerate(br.CAMPAIGN):
            for slot, entity in enumerate(level.entities):
                if drop_effect(entity) == effect:
                    return index, level, slot
        raise unittest.SkipTest(f"no campaign actor drops {effect}")

    def test_taking_a_carriers_drop_puts_a_card_in_hand(self):
        index, level, slot = self._dropping("key")
        cgb = self._sector(index)
        cgb.write8(br.ENTITY_SLOT, slot)
        cgb.call_subroutine("actor_load", max_steps=100_000)
        cgb.write8(br.SENTINEL_STATE, br.SENTINEL_DEAD)
        cgb.write8(br.PICKUP_ACTIVE, pickup_byte(level.entities[slot]))
        cgb.write8(br.PLAYER_KEYS, 0)
        health = cgb.read8(br.PLAYER_HEALTH)
        for address in (br.PLAYER_XL, br.PLAYER_YL): cgb.write8(address, 0x80)
        cgb.write8(br.PLAYER_XH, cgb.read8(br.SENTINEL_XH))
        cgb.write8(br.PLAYER_YH, cgb.read8(br.SENTINEL_YH))
        cgb.call_subroutine("collect_pickup_and_exit", max_steps=500_000)
        expected = GAME.items[level.entities[slot].drop].value if level_codec.ITEM_DROPS else 1
        self.assertEqual(cgb.read8(br.PICKUP_ACTIVE), 0)
        self.assertEqual(cgb.read8(br.PLAYER_KEYS), expected)
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), health, "a card is not a medkit")

    def test_taking_a_health_drop_heals(self):
        index, level, slot = self._dropping("health")
        cgb = self._sector(index)
        cgb.write8(br.ENTITY_SLOT, slot)
        cgb.call_subroutine("actor_load", max_steps=100_000)
        cgb.write8(br.SENTINEL_STATE, br.SENTINEL_DEAD)
        cgb.write8(br.PICKUP_ACTIVE, pickup_byte(level.entities[slot]))
        cgb.write8(br.PLAYER_KEYS, 0)
        cgb.write8(br.PLAYER_HEALTH, 10)
        for address in (br.PLAYER_XL, br.PLAYER_YL): cgb.write8(address, 0x80)
        cgb.write8(br.PLAYER_XH, cgb.read8(br.SENTINEL_XH))
        cgb.write8(br.PLAYER_YH, cgb.read8(br.SENTINEL_YH))
        cgb.call_subroutine("collect_pickup_and_exit", max_steps=500_000)
        healed = GAME.items[level.entities[slot].drop].value if level_codec.ITEM_DROPS else level.medkit_value
        self.assertEqual(cgb.read8(br.PLAYER_HEALTH), 10 + healed)
        self.assertEqual(cgb.read8(br.PLAYER_KEYS), 0, "a medkit is not a card")


if __name__ == "__main__":
    unittest.main()
