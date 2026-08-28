"""Compile authored JSON levels into the compact active-level ROM payload."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILE_IDS = {"renderer-heavy": 0, "entity-heavy": 1}
PALETTE_IDS = {"outpost": 0}
ORIENTATION_IDS = {"vertical": 0, "horizontal": 1}


@dataclass(frozen=True)
class DoorSpec:
    x: int
    y: int
    orientation: int


@dataclass(frozen=True)
class EntitySpec:
    kind: str
    x_q8: int
    y_q8: int
    health: int
    activation_radius_q4: int


@dataclass(frozen=True)
class PickupSpec:
    kind: str
    source: str
    value: int


@dataclass(frozen=True)
class ExitSpec:
    x: int
    y: int


@dataclass(frozen=True)
class CompiledLevel:
    name: str
    width: int
    height: int
    grid: bytes
    segment_table: bytes
    player_x_q8: int
    player_y_q8: int
    player_angle: int
    doors: tuple[DoorSpec, ...]
    entities: tuple[EntitySpec, ...]
    pickups: tuple[PickupSpec, ...]
    exit: ExitSpec
    palette_profile: int
    vram_profile: int

    def header_bytes(self) -> bytes:
        """Fixed active-level header consumed by the resident SM83 loader."""
        sentinel = self.entities[0]
        door = self.doors[0]
        return bytes((
            self.width, self.height, self.vram_profile, self.palette_profile,
            self.player_x_q8 & 0xFF, self.player_x_q8 >> 8,
            self.player_y_q8 & 0xFF, self.player_y_q8 >> 8,
            self.player_angle,
            sentinel.x_q8 & 0xFF, sentinel.x_q8 >> 8,
            sentinel.y_q8 & 0xFF, sentinel.y_q8 >> 8,
            sentinel.health, sentinel.activation_radius_q4,
            door.x, door.y, door.orientation,
            self.exit.x, self.exit.y,
        ))


def _bounded_int(record: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = int(record[key])
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be in {minimum}..{maximum}, got {value}")
    return value


def build_segment_table(grid: bytes, width: int, height: int) -> bytes:
    """Assign one ID to every contiguous exposed face run.

    Entries are cell-major with four bytes per cell: west, east, north,
    south. IDs are stable for a fixed level and deliberately describe the
    visible surface, not merely its supporting wall plane.
    """
    if len(grid) != width * height:
        raise ValueError("segment grid size mismatch")
    table = bytearray(width * height * 4)
    next_id = 1

    def material(x: int, y: int) -> int:
        if not (0 <= x < width and 0 <= y < height):
            return 1
        return grid[y * width + x]

    def exposed(x: int, y: int, side: int) -> bool:
        if not material(x, y):
            return False
        dx, dy = ((-1, 0), (1, 0), (0, -1), (0, 1))[side]
        return material(x + dx, y + dy) == 0

    def allocate(cells: list[tuple[int, int]], side: int) -> None:
        nonlocal next_id
        if not cells:
            return
        if next_id > 255:
            raise ValueError("level exposes more than 255 wall segments")
        for x, y in cells:
            table[(y * width + x) * 4 + side] = next_id
        next_id += 1

    # Vertical planes: consecutive Y cells form one segment only while their
    # material and exposed side agree.
    for side in (0, 1):
        for x in range(width):
            run: list[tuple[int, int]] = []
            run_material = -1
            for y in range(height + 1):
                valid = y < height and exposed(x, y, side)
                cell_material = material(x, y) if valid else -1
                if valid and (not run or cell_material == run_material):
                    run.append((x, y)); run_material = cell_material
                    continue
                allocate(run, side)
                run = [(x, y)] if valid else []
                run_material = cell_material
            allocate(run, side)

    # Horizontal planes: consecutive X cells use the same rule.
    for side in (2, 3):
        for y in range(height):
            run = []
            run_material = -1
            for x in range(width + 1):
                valid = x < width and exposed(x, y, side)
                cell_material = material(x, y) if valid else -1
                if valid and (not run or cell_material == run_material):
                    run.append((x, y)); run_material = cell_material
                    continue
                allocate(run, side)
                run = [(x, y)] if valid else []
                run_material = cell_material
            allocate(run, side)
    return bytes(table)


def compile_level(path: Path) -> CompiledLevel:
    source = json.loads(path.read_text(encoding="utf-8"))
    if source.get("format") != "lupine-level-v1":
        raise ValueError(f"unsupported level format in {path}")
    width = _bounded_int(source, "width", 1, 16)
    height = _bounded_int(source, "height", 1, 16)
    if (width, height) != (16, 16):
        raise ValueError("the resident v0.6 loader currently requires a 16x16 level")
    rows = source["rows"]
    if len(rows) != height or any(len(row) != width for row in rows):
        raise ValueError("level row dimensions do not match width/height")
    if any(code not in "0123" for row in rows for code in row):
        raise ValueError("level cells must be material codes 0..3")
    grid = bytes(int(code) for row in rows for code in row)
    if any(grid[x] == 0 or grid[(height - 1) * width + x] == 0 for x in range(width)):
        raise ValueError("top and bottom level boundaries must be solid")
    if any(grid[y * width] == 0 or grid[y * width + width - 1] == 0 for y in range(height)):
        raise ValueError("left and right level boundaries must be solid")

    spawn = source["player_spawn"]
    doors = tuple(
        DoorSpec(
            _bounded_int(item, "x", 0, width - 1),
            _bounded_int(item, "y", 0, height - 1),
            ORIENTATION_IDS[str(item["orientation"])],
        )
        for item in source.get("doors", [])
    )
    entities = tuple(
        EntitySpec(
            kind=str(item["kind"]),
            x_q8=_bounded_int(item, "x_q8", 0, width * 256 - 1),
            y_q8=_bounded_int(item, "y_q8", 0, height * 256 - 1),
            health=_bounded_int(item, "health", 1, 255),
            activation_radius_q4=_bounded_int(item, "activation_radius_q4", 1, 127),
        )
        for item in source.get("entities", [])
    )
    pickups = tuple(
        PickupSpec(str(item["kind"]), str(item["source"]), _bounded_int(item, "value", 1, 255))
        for item in source.get("pickups", [])
    )
    if len(doors) != 1 or grid[doors[0].y * width + doors[0].x] != 3:
        raise ValueError("the resident v0.6 slice requires exactly one material-3 door")
    if len(entities) != 1 or entities[0].kind != "sentinel":
        raise ValueError("the resident v0.6 slice requires exactly one Sentinel")
    if len(pickups) != 1 or pickups[0].source != "sentinel_drop":
        raise ValueError("the resident v0.6 slice requires one Sentinel drop")
    exit_spec = ExitSpec(
        _bounded_int(source["exit"], "x", 0, width - 1),
        _bounded_int(source["exit"], "y", 0, height - 1),
    )
    if grid[exit_spec.y * width + exit_spec.x]:
        raise ValueError("exit must occupy an empty map cell")
    return CompiledLevel(
        name=str(source["name"]), width=width, height=height, grid=grid,
        segment_table=build_segment_table(grid, width, height),
        player_x_q8=_bounded_int(spawn, "x_q8", 0, width * 256 - 1),
        player_y_q8=_bounded_int(spawn, "y_q8", 0, height * 256 - 1),
        player_angle=_bounded_int(spawn, "angle", 0, 255),
        doors=doors, entities=entities, pickups=pickups, exit=exit_spec,
        palette_profile=PALETTE_IDS[str(source["palette_profile"])],
        vram_profile=PROFILE_IDS[str(source["vram_profile"])],
    )


def active_level(root: Path) -> CompiledLevel:
    configured = os.environ.get("LUPINE3D_LEVEL")
    path = Path(configured) if configured else root / "levels" / "living_world.json"
    return compile_level(path.resolve())
