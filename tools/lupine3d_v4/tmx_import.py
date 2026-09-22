"""Tiled (TMX) authoring for levels: a lossless round trip with the JSON form.

The mapping is documented in docs/LEVEL_FORMAT.md. The map is orthogonal,
16x16 cells of TILE pixels, so a Q8 coordinate is pixel * 256 / TILE: with
TILE = 32 that is pixel * 8, exact in both directions. The JSON file stays
the format the compiler reads; TMX is an editing view of it. Keys the
mapping does not model are carried as `json:<key>` map properties, so a
level survives the round trip whether or not this module knows every key.

Only the standard library is used (xml.etree). The importer never reads the
tileset image; the exporter can write a swatch strip so Tiled has something
to draw (`write_swatch`), which is an editor convenience, not a build step.
"""
from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

TILE = 32
SIZE = 16
MATERIALS = ("walkable", "structure", "machinery", "door")
SWATCH_RGB = ((30, 34, 38), (116, 140, 148), (48, 124, 92), (24, 108, 132))
MAP_PROPERTIES = ("format", "name", "palette_profile", "vram_profile")
MODELLED = MAP_PROPERTIES + ("width", "height", "rows", "player_spawn", "doors", "entities", "fixtures",
                             "surfaces", "exit")


def _q8_to_px(value: int) -> str:
    pixels = value * TILE / 256
    return str(int(pixels)) if pixels == int(pixels) else repr(pixels)


def _px_to_q8(text: str) -> int:
    q8 = float(text) * 256 / TILE
    if q8 != int(q8):
        raise ValueError(f"{text} px is not a Q8 coordinate at {TILE}-pixel tiles")
    return int(q8)


def _properties(parent: ET.Element, items: dict) -> None:
    if not items:
        return
    node = ET.SubElement(parent, "properties")
    for key, value in items.items():
        prop = ET.SubElement(node, "property", name=key)
        if isinstance(value, bool):
            prop.set("type", "bool"); prop.set("value", "true" if value else "false")
        elif isinstance(value, int):
            prop.set("type", "int"); prop.set("value", str(value))
        elif isinstance(value, float):
            prop.set("type", "float"); prop.set("value", repr(value))
        else:
            prop.set("value", str(value))


def _read_properties(node: ET.Element) -> dict:
    out: dict = {}
    props = node.find("properties")
    if props is None:
        return out
    for prop in props.findall("property"):
        kind = prop.get("type", "string")
        text = prop.get("value")
        if text is None:
            text = prop.text or ""
        if kind == "int":
            out[prop.get("name")] = int(text)
        elif kind == "float":
            out[prop.get("name")] = float(text)
        elif kind == "bool":
            out[prop.get("name")] = text == "true"
        else:
            out[prop.get("name")] = text
    return out


def _cell_object(layer: ET.Element, ident: int, x: int, y: int, *, name: str = "", kind: str = "",
                 properties: dict | None = None) -> None:
    attributes = {"id": str(ident), "x": str(x * TILE), "y": str(y * TILE), "width": str(TILE), "height": str(TILE)}
    if name:
        attributes["name"] = name
    if kind:
        attributes["type"] = kind
    _properties(ET.SubElement(layer, "object", attributes), properties or {})


def _point_object(layer: ET.Element, ident: int, x_q8: int, y_q8: int, *, name: str = "", kind: str = "",
                  properties: dict | None = None) -> None:
    attributes = {"id": str(ident), "x": _q8_to_px(x_q8), "y": _q8_to_px(y_q8)}
    if name:
        attributes["name"] = name
    if kind:
        attributes["type"] = kind
    node = ET.SubElement(layer, "object", attributes)
    _properties(node, properties or {})
    ET.SubElement(node, "point")


def export_tmx(level: dict, *, swatch: str = "materials.png") -> str:
    """The TMX text for an authored level dictionary."""
    width, height = int(level["width"]), int(level["height"])
    root = ET.Element("map", version="1.10", tiledversion="1.10.2", orientation="orthogonal", renderorder="right-down",
                      width=str(width), height=str(height), tilewidth=str(TILE), tileheight=str(TILE), infinite="0")
    properties = {key: level[key] for key in MAP_PROPERTIES if key in level}
    # The authored key order is content to a reviewer's diff, so it rides along.
    properties["key_order"] = ",".join(level)
    for key in sorted(level):
        if key not in MODELLED:
            properties[f"json:{key}"] = json.dumps(level[key], separators=(",", ":"))
    _properties(root, properties)
    tileset = ET.SubElement(root, "tileset", firstgid="1", name="materials", tilewidth=str(TILE), tileheight=str(TILE),
                            tilecount=str(len(MATERIALS)), columns=str(len(MATERIALS)))
    ET.SubElement(tileset, "image", source=swatch, width=str(TILE * len(MATERIALS)), height=str(TILE))
    for code, material in enumerate(MATERIALS):
        tile = ET.SubElement(tileset, "tile", id=str(code), type=material)
        _properties(tile, {"material": code})
    layer = ET.SubElement(root, "layer", id="1", name="materials", width=str(width), height=str(height))
    data = ET.SubElement(layer, "data", encoding="csv")
    data.text = "\n" + ",\n".join(",".join(str(int(code) + 1) for code in row) for row in level["rows"]) + "\n"

    ident = 1
    spawn = level["player_spawn"]
    group = ET.SubElement(root, "objectgroup", id="2", name="spawn")
    extra = {key: value for key, value in spawn.items() if key not in ("x_q8", "y_q8")}
    _point_object(group, ident, int(spawn["x_q8"]), int(spawn["y_q8"]), name="spawn", properties=extra); ident += 1

    group = ET.SubElement(root, "objectgroup", id="3", name="doors")
    for door in level.get("doors", []):
        extra = {key: value for key, value in door.items() if key not in ("id", "x", "y")}
        _cell_object(group, ident, int(door["x"]), int(door["y"]), name=str(door.get("id", "")),
                     properties=extra); ident += 1

    group = ET.SubElement(root, "objectgroup", id="4", name="entities")
    for entity in level.get("entities", []):
        extra = {key: value for key, value in entity.items() if key not in ("kind", "x_q8", "y_q8")}
        _point_object(group, ident, int(entity["x_q8"]), int(entity["y_q8"]), kind=str(entity["kind"]),
                      properties=extra); ident += 1

    group = ET.SubElement(root, "objectgroup", id="5", name="fixtures")
    for fixture in level.get("fixtures", []):
        extra = {key: value for key, value in fixture.items() if key not in ("kind", "x", "y")}
        _cell_object(group, ident, int(fixture["x"]), int(fixture["y"]), kind=str(fixture["kind"]),
                     properties=extra); ident += 1

    group = ET.SubElement(root, "objectgroup", id="6", name="surfaces")
    for surface in level.get("surfaces", []):
        extra = {key: value for key, value in surface.items() if key not in ("profile", "x", "y")}
        _cell_object(group, ident, int(surface["x"]), int(surface["y"]), kind=str(surface["profile"]),
                     properties=extra); ident += 1

    group = ET.SubElement(root, "objectgroup", id="7", name="exit")
    exit_spec = level["exit"]
    extra = {key: value for key, value in exit_spec.items() if key not in ("x", "y")}
    _cell_object(group, ident, int(exit_spec["x"]), int(exit_spec["y"]), name="exit", properties=extra); ident += 1
    root.set("nextobjectid", str(ident)); root.set("nextlayerid", "8")
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _cell_of(node: ET.Element) -> tuple[int, int]:
    x, y = float(node.get("x")), float(node.get("y"))
    if x % TILE or y % TILE:
        raise ValueError(f"object {node.get('id')} is not aligned to a cell")
    return int(x) // TILE, int(y) // TILE


def _objects(root: ET.Element, name: str) -> list[ET.Element]:
    for group in root.findall("objectgroup"):
        if group.get("name") == name:
            return group.findall("object")
    return []


def _kind(node: ET.Element) -> str:
    return node.get("type") or node.get("class") or ""


def import_tmx(text: str) -> dict:
    """The level dictionary a TMX map describes, in the JSON key order the
    authored levels use."""
    root = ET.fromstring(text)
    width, height = int(root.get("width")), int(root.get("height"))
    if (int(root.get("tilewidth")), int(root.get("tileheight"))) != (TILE, TILE):
        raise ValueError(f"levels are authored at {TILE}-pixel tiles")
    properties = _read_properties(root)
    firstgid = 1
    for tileset in root.findall("tileset"):
        if tileset.get("name") == "materials":
            firstgid = int(tileset.get("firstgid", "1"))
    layer = next((l for l in root.findall("layer") if l.get("name") == "materials"), None)
    if layer is None:
        raise ValueError("no `materials` tile layer")
    data = layer.find("data")
    if data.get("encoding") != "csv":
        raise ValueError("the materials layer must be CSV-encoded")
    gids = [int(token) for token in data.text.replace("\n", "").split(",") if token.strip()]
    if len(gids) != width * height:
        raise ValueError("materials layer size does not match the map")
    codes = [gid - firstgid if gid else 0 for gid in gids]
    if any(not 0 <= code < len(MATERIALS) for code in codes):
        raise ValueError("materials layer uses a tile outside the four materials")
    rows = ["".join(str(code) for code in codes[y * width:(y + 1) * width]) for y in range(height)]

    level: dict = {}
    for key in ("format", "name"):
        level[key] = properties.get(key)
    level["width"], level["height"], level["rows"] = width, height, rows

    spawn_nodes = _objects(root, "spawn")
    if len(spawn_nodes) != 1:
        raise ValueError("exactly one spawn object")
    node = spawn_nodes[0]
    level["player_spawn"] = {"x_q8": _px_to_q8(node.get("x")), "y_q8": _px_to_q8(node.get("y")), **_read_properties(node)}

    doors = []
    for node in _objects(root, "doors"):
        x, y = _cell_of(node)
        record = {"id": node.get("name")} if node.get("name") else {}
        doors.append({**record, "x": x, "y": y, **_read_properties(node)})
    level["doors"] = doors

    entities = []
    for node in _objects(root, "entities"):
        entities.append({"kind": _kind(node), "x_q8": _px_to_q8(node.get("x")), "y_q8": _px_to_q8(node.get("y")),
                         **_read_properties(node)})
    level["entities"] = entities

    extras = {key[len("json:"):]: json.loads(value) for key, value in properties.items() if key.startswith("json:")}
    for key in ("pickups", "triggers"):
        if key in extras:
            level[key] = extras.pop(key)

    exits = _objects(root, "exit")
    if len(exits) != 1:
        raise ValueError("exactly one exit object")
    x, y = _cell_of(exits[0])
    level["exit"] = {"x": x, "y": y, **_read_properties(exits[0])}
    if "readability" in extras:
        level["readability"] = extras.pop("readability")

    level["fixtures"] = [{"x": x, "y": y, **_read_properties(node), "kind": _kind(node)}
                         for node in _objects(root, "fixtures") for x, y in (_cell_of(node),)]
    level["surfaces"] = [{"x": x, "y": y, **_read_properties(node), "profile": _kind(node)}
                         for node in _objects(root, "surfaces") for x, y in (_cell_of(node),)]
    for key in ("palette_profile", "vram_profile"):
        level[key] = properties.get(key)
    level.update(extras)
    # The authored key order decides which optional lists the file carries:
    # a map exported from a level without `fixtures` comes back without it.
    order = [key for key in properties.get("key_order", "").split(",") if key in level]
    if order:
        return {key: level[key] for key in order + [key for key in level if key not in order and level[key]]}
    return {key: value for key, value in level.items() if value not in ([], None)}


def write_swatch(path: Path) -> None:
    """A 128x32 strip of the four material colours for Tiled's tileset view.
    An editor convenience only: no build reads it."""
    from PIL import Image
    image = Image.new("RGB", (TILE * len(MATERIALS), TILE))
    for code, colour in enumerate(SWATCH_RGB):
        image.paste(colour, (code * TILE, 0, (code + 1) * TILE, TILE))
    image.save(path)


def export_file(source: Path, destination: Path, *, swatch: bool = False) -> None:
    destination.write_text(export_tmx(json.loads(source.read_text(encoding="utf-8"))), encoding="utf-8")
    if swatch:
        write_swatch(destination.parent / "materials.png")


def dump_level(level: dict) -> str:
    """The authored JSON style: one record per line, rows one per line, so a
    review diff shows a moved door as one changed line."""
    lines = ["{"]
    items = list(level.items())
    for index, (key, value) in enumerate(items):
        comma = "," if index + 1 < len(items) else ""
        if isinstance(value, list) and value and all(isinstance(item, (dict, str)) for item in value):
            body = ",\n".join("    " + json.dumps(item) for item in value)
            lines.append(f'  "{key}": [\n{body}\n  ]{comma}')
        elif isinstance(value, dict) and len(value) > 4:
            body = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in value.items())
            lines.append(f'  "{key}": {{\n{body}\n  }}{comma}')
        else:
            lines.append(f'  "{key}": {json.dumps(value)}{comma}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def import_file(source: Path, destination: Path) -> None:
    level = import_tmx(source.read_text(encoding="utf-8"))
    destination.write_text(dump_level(level), encoding="utf-8")
