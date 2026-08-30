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
class ReadabilityReport:
    """Build-time spatial-legibility certificate for a gameplay level."""
    walkable_cells: int
    unreachable_cells: int
    critical_path_steps: int
    critical_path_turns: int
    maximum_sightline: int
    maximum_open_rectangle: tuple[int, int]
    minimum_door_separation: int
    material_seams: int
    material_singleton_runs: int
    physical_segments: int


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
    readability: ReadabilityReport | None = None

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
    """Assign one ID to every physically contiguous exposed face run.

    Entries are cell-major with four bytes per cell: west, east, north,
    south. Static wall materials 1 and 2 share continuity; a paint change is
    not geometry. Doors remain separate movable surfaces and therefore always
    split a run.
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

    def surface_class(cell_material: int, x: int, y: int) -> int:
        # Every authored door is independent movable geometry. Static paint
        # families intentionally collapse to the same class.
        return 0x100 + y * width + x if cell_material == 3 else 1

    # Vertical planes: consecutive Y cells form one segment while their
    # physical class and exposed side agree. Paint does not split the plane.
    for side in (0, 1):
        for x in range(width):
            run: list[tuple[int, int]] = []
            run_material = -1
            for y in range(height + 1):
                valid = y < height and exposed(x, y, side)
                cell_material = surface_class(material(x, y), x, y) if valid else -1
                if valid and (not run or cell_material == run_material):
                    run.append((x, y)); run_material = cell_material
                    continue
                allocate(run, side)
                run = [(x, y)] if valid else []
                run_material = cell_material
            allocate(run, side)

    # Horizontal planes use the same geometry-only rule.
    for side in (2, 3):
        for y in range(height):
            run = []
            run_material = -1
            for x in range(width + 1):
                valid = x < width and exposed(x, y, side)
                cell_material = surface_class(material(x, y), x, y) if valid else -1
                if valid and (not run or cell_material == run_material):
                    run.append((x, y)); run_material = cell_material
                    continue
                allocate(run, side)
                run = [(x, y)] if valid else []
                run_material = cell_material
            allocate(run, side)
    return bytes(table)


def _passable_cells(grid: bytes, width: int, height: int) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(height)
        for x in range(width)
        if grid[y * width + x] in (0, 3)
    }


def _reachable_cells(
    passable: set[tuple[int, int]], start: tuple[int, int],
    blocked: tuple[int, int] | None = None,
) -> set[tuple[int, int]]:
    if start == blocked or start not in passable:
        return set()
    queue = deque((start,))
    visited = {start}
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            cell = (x + dx, y + dy)
            if cell == blocked or cell in visited or cell not in passable:
                continue
            visited.add(cell)
            queue.append(cell)
    return visited


def _shortest_path_steps_and_turns(
    passable: set[tuple[int, int]], start: tuple[int, int], goal: tuple[int, int],
) -> tuple[int, int] | None:
    """Return distance and the fewest turns among all shortest paths."""
    queue = deque(((start[0], start[1], -1, 0, 0),))
    best: dict[tuple[int, int, int], tuple[int, int]] = {}
    solutions: list[tuple[int, int]] = []
    directions = ((-1, 0), (1, 0), (0, -1), (0, 1))
    while queue:
        x, y, previous, steps, turns = queue.popleft()
        if solutions and steps > solutions[0][0]:
            break
        if (x, y) == goal:
            solutions.append((steps, turns))
            continue
        for direction, (dx, dy) in enumerate(directions):
            cell = (x + dx, y + dy)
            if cell not in passable:
                continue
            candidate = (steps + 1, turns + int(previous >= 0 and previous != direction))
            state = (cell[0], cell[1], direction)
            if state in best and best[state] <= candidate:
                continue
            best[state] = candidate
            queue.append((cell[0], cell[1], direction, *candidate))
    if not solutions:
        return None
    shortest = min(item[0] for item in solutions)
    return shortest, min(turns for steps, turns in solutions if steps == shortest)


def _maximum_sightline(passable: set[tuple[int, int]], width: int, height: int) -> int:
    maximum = 0
    for y in range(height):
        run = 0
        for x in range(width):
            run = run + 1 if (x, y) in passable else 0
            maximum = max(maximum, run)
    for x in range(width):
        run = 0
        for y in range(height):
            run = run + 1 if (x, y) in passable else 0
            maximum = max(maximum, run)
    return maximum


def _maximum_open_rectangle(
    passable: set[tuple[int, int]], width: int, height: int,
) -> tuple[int, int]:
    """Return the largest-area axis-aligned open rectangle dimensions."""
    best_area, best_width, best_height = 0, 0, 0
    heights = [0] * width
    for y in range(height):
        for x in range(width):
            heights[x] = heights[x] + 1 if (x, y) in passable else 0
        for left in range(width):
            minimum = height + 1
            for right in range(left, width):
                minimum = min(minimum, heights[right])
                if minimum == 0:
                    continue
                rect_width = right - left + 1
                area = rect_width * minimum
                if area > best_area:
                    best_area, best_width, best_height = area, rect_width, minimum
    return best_width, best_height


def _has_oversized_open_room(
    passable: set[tuple[int, int]], width: int, height: int,
) -> bool:
    """Detect any open 5x4 or 4x5 window, irrespective of larger corridors."""
    for rect_width, rect_height in ((5, 4), (4, 5)):
        for y0 in range(height - rect_height + 1):
            for x0 in range(width - rect_width + 1):
                if all(
                    (x, y) in passable
                    for y in range(y0, y0 + rect_height)
                    for x in range(x0, x0 + rect_width)
                ):
                    return True
    return False


def _material_run_metrics(grid: bytes, width: int, height: int) -> tuple[int, int]:
    """Count paint seams and one-cell islands within physical surfaces."""
    segment_table = build_segment_table(grid, width, height)
    members: dict[int, list[tuple[int, int]]] = {}
    for cell_index, cell_material in enumerate(grid):
        if cell_material not in (1, 2):
            continue
        for side in range(4):
            segment = segment_table[cell_index * 4 + side]
            if segment:
                members.setdefault(segment, []).append((cell_index, cell_material))

    seam_count = 0
    singleton_count = 0
    for entries in members.values():
        if len(entries) <= 1:
            continue
        ordered = [material for _, material in sorted(entries)]
        run_material, run_length = ordered[0], 1
        run_lengths: list[int] = []
        for material in ordered[1:] + [-1]:
            if material == run_material:
                run_length += 1
                continue
            run_lengths.append(run_length)
            run_material, run_length = material, 1
        seam_count += len(run_lengths) - 1
        singleton_count += sum(length == 1 for length in run_lengths)
    return seam_count, singleton_count


def analyze_level_readability(
    grid: bytes, width: int, height: int, start: tuple[int, int],
    sentinel: tuple[int, int], doors: tuple[DoorSpec, ...],
) -> ReadabilityReport:
    passable = _passable_cells(grid, width, height)
    reachable = _reachable_cells(passable, start)
    critical = _shortest_path_steps_and_turns(passable, start, sentinel)
    if critical is None:
        critical = (0, 0)
    separations = [
        len(passable) - len(_reachable_cells(passable, start, (door.x, door.y))) - 1
        for door in doors
    ]
    segment_table = build_segment_table(grid, width, height)
    material_seams, material_singletons = _material_run_metrics(grid, width, height)
    return ReadabilityReport(
        walkable_cells=len(passable),
        unreachable_cells=len(passable - reachable),
        critical_path_steps=critical[0],
        critical_path_turns=critical[1],
        maximum_sightline=_maximum_sightline(passable, width, height),
        maximum_open_rectangle=_maximum_open_rectangle(passable, width, height),
        minimum_door_separation=min(separations, default=0),
        material_seams=material_seams,
        material_singleton_runs=material_singletons,
        physical_segments=max(segment_table, default=0),
    )


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
    readability = analyze_level_readability(
        grid, width, height,
        (player_x_q8 >> 8, player_y_q8 >> 8),
        (entities[0].x_q8 >> 8, entities[0].y_q8 >> 8),
        doors,
    )
    if level_format == "lupine-level-v2":
        limits = source.get("readability", {})
        max_sightline = int(limits.get("maximum_sightline", 6))
        min_door_separation = int(limits.get("minimum_door_separation", 4))
        min_path_steps = int(limits.get("minimum_critical_path_steps", 12))
        min_path_turns = int(limits.get("minimum_critical_path_turns", 2))
        max_singletons = int(limits.get("maximum_material_singletons", 16))
        if readability.unreachable_cells:
            raise ValueError(
                f"readability: {readability.unreachable_cells} walkable cells are unreachable"
            )
        if readability.minimum_door_separation < min_door_separation:
            raise ValueError(
                "readability: an ordinary door fails to separate enough walkable cells "
                f"({readability.minimum_door_separation} < {min_door_separation})"
            )
        if readability.critical_path_steps < min_path_steps:
            raise ValueError(
                f"readability: critical path is too short ({readability.critical_path_steps} < {min_path_steps})"
            )
        if readability.critical_path_turns < min_path_turns:
            raise ValueError(
                f"readability: critical path has too few turns ({readability.critical_path_turns} < {min_path_turns})"
            )
        if readability.maximum_sightline > max_sightline:
            raise ValueError(
                f"readability: sightline is too long ({readability.maximum_sightline} > {max_sightline})"
            )
        # Long 1-3-cell-wide corridors are fine; room-like open rectangles
        # must fit inside the renderer's legible 4x4 envelope.
        if _has_oversized_open_room(_passable_cells(grid, width, height), width, height):
            rect_width, rect_height = readability.maximum_open_rectangle
            raise ValueError(
                f"readability: open rectangle {rect_width}x{rect_height} exceeds the 4x4 room envelope"
            )
        if readability.material_singleton_runs > max_singletons:
            raise ValueError(
                "readability: exposed material paint is too fragmented "
                f"({readability.material_singleton_runs} singleton runs > {max_singletons})"
            )
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
        readability=readability,
    )


def active_level(root: Path) -> CompiledLevel:
    configured = os.environ.get("LUPINE3D_LEVEL")
    path = Path(configured) if configured else root / "levels" / "living_world.json"
    return compile_level(path.resolve())
