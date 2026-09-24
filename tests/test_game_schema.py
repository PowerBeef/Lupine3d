"""The published JSON Schemas say what the loader reads.

`docs/schema/*.schema.json` are what an editor uses to complete and check a
game's files; the loader (`tools/lupine3d_v4/game.py`) is the validator of
record. They must not drift: every object the loader reads has the same
allowed and required keys in its schema, the counts the schema bounds are
the engine's limits, and the showcase's files validate.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from lupine3d_v4.game import KEYS  # noqa: E402
from lupine3d_v4.limits import LIMITS  # noqa: E402

SCHEMAS = ROOT / "docs" / "schema"
SABLE = ROOT / "games" / "sable_outpost"
# The object at a schema's root; every other KEYS object is one of the
# schemas' $defs, under its KEYS name.
ROOTS = {"game": "game-v1", "screens": "screens-v1", "song": "song-v1", "sound": "sound-v1"}


def load(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate(instance, schema: dict, root: dict, where: str = "$") -> list[str]:
    """The subset of JSON Schema 2020-12 the game schemas use."""
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return validate(instance, target, root, where)
    problems: list[str] = []
    if "anyOf" in schema:
        if all(validate(instance, option, root, where) for option in schema["anyOf"]):
            problems.append(f"{where}: matches none of anyOf")
        return problems
    kinds = schema.get("type")
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        checks = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
                  "string": lambda v: isinstance(v, str), "null": lambda v: v is None,
                  "boolean": lambda v: isinstance(v, bool),
                  "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                  "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
        if not any(checks[kind](instance) for kind in kinds):
            return [f"{where}: {instance!r} is not {kinds}"]
    if "const" in schema and instance != schema["const"]:
        problems.append(f"{where}: {instance!r} != {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        problems.append(f"{where}: {instance!r} not in {schema['enum']}")
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            problems.append(f"{where}: {instance!r} does not match {schema['pattern']}")
        if len(instance) < schema.get("minLength", 0) or len(instance) > schema.get("maxLength", 1 << 30):
            problems.append(f"{where}: length of {instance!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if instance < schema.get("minimum", -1e18) or instance > schema.get("maximum", 1e18):
            problems.append(f"{where}: {instance} out of range")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            problems.append(f"{where}: {instance} too small")
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            problems.append(f"{where}: {instance} too large")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0) or len(instance) > schema.get("maxItems", 1 << 30):
            problems.append(f"{where}: {len(instance)} items")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in instance}) != len(instance):
            problems.append(f"{where}: items repeat")
        if "items" in schema:
            for index, item in enumerate(instance):
                problems += validate(item, schema["items"], root, f"{where}[{index}]")
    if isinstance(instance, dict):
        if len(instance) < schema.get("minProperties", 0) or len(instance) > schema.get("maxProperties", 1 << 30):
            problems.append(f"{where}: {len(instance)} properties")
        for key in schema.get("required", ()):
            if key not in instance:
                problems.append(f"{where}: missing {key}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if "propertyNames" in schema:
                problems += validate(key, schema["propertyNames"], root, f"{where} key {key!r}")
            if key in properties:
                problems += validate(value, properties[key], root, f"{where}.{key}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{where}: unexpected {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                problems += validate(value, schema["additionalProperties"], root, f"{where}.{key}")
    return problems


class GameSchemaTests(unittest.TestCase):
    def schema_of(self, name: str) -> dict:
        if name in ROOTS:
            return load(ROOTS[name])
        owners = [file.stem.removesuffix(".schema") for file in SCHEMAS.glob("*-v1.schema.json")
                  if name in load(file.stem.removesuffix(".schema")).get("$defs", {})]
        self.assertEqual(len(owners), 1, f"{name}: defined in {owners}")
        return load(owners[0])["$defs"][name]

    def test_every_object_the_loader_reads_has_the_same_keys_in_its_schema(self):
        for name, (allowed, required) in KEYS.items():
            with self.subTest(name):
                schema = self.schema_of(name)
                self.assertEqual(set(schema["properties"]), set(allowed))
                self.assertEqual(set(schema["required"]), set(required))
                self.assertIs(schema["additionalProperties"], False)

    def test_the_counts_a_schema_bounds_are_the_engines_limits(self):
        game = load("game-v1")
        top = game["properties"]
        for key, limit in (("episodes", "episodes"), ("kinds", "kinds"), ("themes", "themes"),
                           ("weapons", "weapons"), ("actor_palettes", "actor_palettes")):
            self.assertEqual((top[key]["minItems"], top[key]["maxItems"]),
                             (LIMITS[limit].minimum, LIMITS[limit].maximum), key)
        self.assertEqual(top["textures"]["maxProperties"], LIMITS["textures"].maximum)
        self.assertEqual(game["$defs"]["kind"]["properties"]["contact_damage"]["maximum"],
                         LIMITS["contact_damage"].maximum)
        self.assertEqual(game["$defs"]["hud.words"]["properties"]["hunt"]["maxLength"], LIMITS["hud_word"].maximum)
        level = load("level-v2")["properties"]
        self.assertEqual(level["doors"]["maxItems"], LIMITS["doors_per_level"].maximum)

    def test_the_showcase_and_the_starter_validate(self):
        for game in (SABLE, ROOT / "games" / "starter"):
            manifest = json.loads((game / "game.json").read_text(encoding="utf-8"))
            files = [("game-v1", "game.json"), ("screens-v1", manifest["screens"]),
                     ("sound-v1", manifest["audio"]["sound"]), ("sprites-v1", manifest["sprites"]["manifest"])]
            files += [("song-v1", path) for path in manifest["audio"]["songs"].values()]
            files += [("level-v2", path) for episode in manifest["episodes"] for path in episode["levels"]]
            for schema_name, relative in files:
                with self.subTest(f"{game.name}/{relative}"):
                    schema = load(schema_name)
                    instance = json.loads((game / relative).read_text(encoding="utf-8"))
                    self.assertEqual(validate(instance, schema, schema), [])

    def test_the_validator_refuses_what_the_loader_refuses(self):
        schema = load("game-v1")
        manifest = json.loads((SABLE / "game.json").read_text(encoding="utf-8"))
        manifest["kindz"] = []
        manifest["themes"] *= 2
        manifest["rom"]["header_title"] = "lower"
        problems = validate(manifest, schema, schema)
        self.assertTrue(any("unexpected kindz" in p for p in problems), problems)
        self.assertTrue(any("$.themes: 6 items" in p for p in problems), problems)
        self.assertTrue(any("header_title" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
