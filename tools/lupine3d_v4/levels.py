"""Compile authored JSON levels into the compact active-level ROM payload."""
from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILE_IDS = {"renderer-heavy": 0, "entity-heavy": 1}
PALETTE_IDS = {"outpost": 0}
ORIENTATION_IDS = {"vertical": 0, "horizontal": 1}
MAX_DOORS = 4
DOOR_RECORD_BYTES = 6
DOOR_X = 0
DOOR_Y = 1
DOOR_ORIENTATION = 2
DOOR_FLAGS = 3
DOOR_STATE = 4
DOOR_FRACTION = 5
DOOR_FLAG_EXIT = 0x01
DOOR_FLAG_LOCK_SENTINEL = 0x02


@dataclass(frozen=True)
class DoorSpec:
    name: str
    x: int
    y: int
    orientation: int
    flags: int


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
    format: str
    name: str
    width: int
    height: int
    grid: bytes
    segment_table: bytes
    player_x_q8: int
    player_y_q8: int
    player_angle: int
    safe_radius_cells: int
    doors: tuple[DoorSpec, ...]
    entities: tuple[EntitySpec, ...]
    pickups: tuple[PickupSpec, ...]
    exit: ExitSpec
    palette_profile: int
    vram_profile: int

    def header_bytes(self) -> bytes:
        """Fixed active-level header consumed by the resident SM83 loader."""
        sentinel = self.entities[0]
        return bytes((
            self.width, self.height, self.vram_profile, self.palette_profile,
            self.player_x_q8 & 0xFF, self.player_x_q8 >> 8,
            self.player_y_q8 & 0xFF, self.player_y_q8 >> 8,
            self.player_angle,
            sentinel.x_q8 & 0xFF, sentinel.x_q8 >> 8,
            sentinel.y_q8 & 0xFF, sentinel.y_q8 >> 8,
            sentinel.health, sentinel.activation_radius_q4,
            self.exit.x, self.exit.y,
            len(self.doors),
        ))

    def door_bytes(self) -> bytes:
        """Fixed-capacity door records copied into active WRAM at level load."""
        data = bytearray(MAX_DOORS * DOOR_RECORD_BYTES)
        for index, door in enumerate(self.doors):
            offset = index * DOOR_RECORD_BYTES
            data[offset:offset + DOOR_RECORD_BYTES] = bytes((
                door.x, door.y, door.orientation, door.flags, 0, 0,
            ))
        return bytes(data)


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


def _reachable_distance(
    grid: bytes, width: int, height: int,
    start: tuple[int, int], goal: tuple[int, int],
    *, doors_open: bool,
) -> int | None:
    queue: deque[tuple[int, int, int]] = deque(((start[0], start[1], 0),))
    visited = {start}
    while queue:
        x, y, distance = queue.popleft()
        if (x, y) == goal:
            return distance
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in visited or not (0 <= nx < width and 0 <= ny < height):
                continue
            material = grid[ny * width + nx]
            if material and not (doors_open and material == 3):
                continue
            visited.add((nx, ny))
            queue.append((nx, ny, distance + 1))
    return None


def _validate_spawn(
    grid: bytes, width: int, height: int,
    x_q8: int, y_q8: int, safe_radius_cells: int,
    entities: tuple[EntitySpec, ...],
) -> None:
    spawn_cell = (x_q8 >> 8, y_q8 >> 8)
    if grid[spawn_cell[1] * width + spawn_cell[0]]:
        raise ValueError("player spawn must occupy an empty map cell")

    # Match the runtime's $38 Q8 collision radius at all four starting corners.
    radius = 0x38
    touched = {
        ((x_q8 + dx) >> 8, (y_q8 + dy) >> 8)
        for dx in (-radius, radius)
        for dy in (-radius, radius)
    }
    if any(
        not (0 <= x < width and 0 <= y < height) or grid[y * width + x]
        for x, y in touched
    ):
        raise ValueError("player spawn does not have full collision-radius clearance")

    # A declared safe start may be separated by a closed door (unreachable is
    # ideal) or have at least the requested walking distance to every actor.
    for entity in entities:
        distance = _reachable_distance(
            grid, width, height, spawn_cell,
            (entity.x_q8 >> 8, entity.y_q8 >> 8), doors_open=False,
        )
        if distance is not None and distance < safe_radius_cells:
            raise ValueError(
                f"player spawn is only {distance} cells from {entity.kind}; "
                f"safe_radius_cells requires {safe_radius_cells}"
            )


def compile_level(path: Path) -> CompiledLevel:
    source = json.loads(path.read_text(encoding="utf-8"))
    level_format = str(source.get("format"))
    if level_format not in ("lupine-level-v1", "lupine-level-v2"):
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
    safe_radius_cells = _bounded_int(spawn, "safe_radius_cells", 0, 15) if "safe_radius_cells" in spawn else 0
    seen_door_names: set[str] = set()
    seen_door_cells: set[tuple[int, int]] = set()
    doors = tuple(
        DoorSpec(
            str(item.get("id", f"door_{index}")),
            _bounded_int(item, "x", 0, width - 1),
            _bounded_int(item, "y", 0, height - 1),
            ORIENTATION_IDS[str(item["orientation"])],
            (DOOR_FLAG_EXIT if str(item.get("kind", "standard")) == "exit" else 0)
            | (DOOR_FLAG_LOCK_SENTINEL if str(item.get("unlock", "none")) == "sentinel_dead" else 0),
        )
        for index, item in enumerate(source.get("doors", []))
    )
    if not 1 <= len(doors) <= MAX_DOORS:
        raise ValueError(f"levels require 1..{MAX_DOORS} doors")
    for door in doors:
        if not door.name or door.name in seen_door_names:
            raise ValueError("door IDs must be non-empty and unique")
        seen_door_names.add(door.name)
        if (door.x, door.y) in seen_door_cells:
            raise ValueError("door cells must be unique")
        seen_door_cells.add((door.x, door.y))
        if not (0 < door.x < width - 1 and 0 < door.y < height - 1):
            raise ValueError(f"door {door.name} cannot occupy the solid level boundary")
        if grid[door.y * width + door.x] != 3:
            raise ValueError(f"door {door.name} must occupy a material-3 cell")
        if level_format == "lupine-level-v2":
            west, east = grid[door.y * width + door.x - 1], grid[door.y * width + door.x + 1]
            north = grid[(door.y - 1) * width + door.x]
            south = grid[(door.y + 1) * width + door.x]
            valid_frame = (west and east and not north and not south) if door.orientation == ORIENTATION_IDS["horizontal"] else (north and south and not west and not east)
            if not valid_frame:
                raise ValueError(f"door {door.name} orientation does not match its wall frame")
    authored_door_cells = {
        (x, y)
        for y, row in enumerate(rows)
        for x, code in enumerate(row)
        if code == "3"
    }
    if authored_door_cells != seen_door_cells:
        raise ValueError("every material-3 cell must have exactly one authored door record")
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
    player_x_q8 = _bounded_int(spawn, "x_q8", 0, width * 256 - 1)
    player_y_q8 = _bounded_int(spawn, "y_q8", 0, height * 256 - 1)
    _validate_spawn(
        grid, width, height, player_x_q8, player_y_q8,
        safe_radius_cells, entities,
    )
    if _reachable_distance(
        grid, width, height,
        (player_x_q8 >> 8, player_y_q8 >> 8),
        (exit_spec.x, exit_spec.y), doors_open=True,
    ) is None:
        raise ValueError("exit must be reachable from the player spawn when doors are open")
    if level_format == "lupine-level-v2":
        exit_doors = [door for door in doors if door.flags & DOOR_FLAG_EXIT]
        if len(exit_doors) != 1 or not (exit_doors[0].flags & DOOR_FLAG_LOCK_SENTINEL):
            raise ValueError("v2 gameplay levels require one Sentinel-locked exit door")
    return CompiledLevel(
        format=level_format, name=str(source["name"]), width=width, height=height, grid=grid,
        segment_table=build_segment_table(grid, width, height),
        player_x_q8=player_x_q8,
        player_y_q8=player_y_q8,
        player_angle=_bounded_int(spawn, "angle", 0, 255),
        safe_radius_cells=safe_radius_cells,
        doors=doors, entities=entities, pickups=pickups, exit=exit_spec,
        palette_profile=PALETTE_IDS[str(source["palette_profile"])],
        vram_profile=PROFILE_IDS[str(source["vram_profile"])],
    )


def active_level(root: Path) -> CompiledLevel:
    configured = os.environ.get("LUPINE3D_LEVEL")
    path = Path(configured) if configured else root / "levels" / "living_world.json"
    return compile_level(path.resolve())
