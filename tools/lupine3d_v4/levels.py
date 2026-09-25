"""Compile authored JSON levels into the compact active-level ROM payload."""
from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lupine3d_v4.game import DROPS, GAME as _GAME, Game
from lupine3d_v4.limits import LIMITS as _LIMITS


PROFILE_IDS = {"renderer-heavy": 0, "entity-heavy": 1}
# Enemy kinds are the game's (game.json `kinds`): a level names one, and its
# declaration order is the runtime kind byte and stat-table index. Kinds share
# the actor cels and differ by stats and OBJ palette, so variety costs ROM
# bytes rather than VRAM patterns; the kind byte is masked to two bits, so a
# game has at most four.
ENTITY_KIND_IDS = _GAME.kind_ids
# Themes are the game's (game.json `themes`): a level's `palette_profile`
# names one, and its declaration order is the header byte that selects the
# 128-byte palette set `init_palettes` uploads at every world entry and the
# texture set the textured kernel reads, so levels of one campaign may differ.
PALETTE_IDS = _GAME.theme_ids
# Songs are the game's (game.json `audio`): a level's optional `music` names
# one, the world song by default, and its index is header byte 21, which
# load_level keeps in LEVEL_SONG for enter_world to play.
SONG_IDS = _GAME.song_ids
ORIENTATION_IDS = {"vertical": 0, "horizontal": 1}
MAX_DOORS = 6
DOOR_RECORD_BYTES = 6
# Simulated actor slots. The renderer admits at most four per frame (sixteen
# world objects, four per scanline, 32 masked patterns), so a level keeps at
# most four actors on any one sightline; the slots beyond that are for actors
# elsewhere in the sector.
MAX_ACTORS = 6
LEVEL_HEADER_BYTES = 24
MAX_FIXTURES = 16
# The creator-facing table (limits.py, docs/reference/limits.md) states these.
assert (MAX_DOORS, MAX_ACTORS, MAX_FIXTURES) == tuple(
    _LIMITS[name].maximum for name in ("doors_per_level", "actors_per_level", "fixtures_per_level"))
DOOR_X = 0
DOOR_Y = 1
DOOR_ORIENTATION = 2
DOOR_FLAGS = 3
DOOR_STATE = 4
DOOR_FRACTION = 5
DOOR_FLAG_EXIT = 0x01
DOOR_FLAG_LOCK_SENTINEL = 0x02
DOOR_FLAG_KEYCARD = 0x04
DOOR_FLAG_REMOTE = 0x08          # only a trigger opens it; B is refused
DOOR_KEY_SHIFT = 4               # bits 4-5: the key colour a card door wants, plus one; 0 is any card
# What a dead actor leaves behind, selected by its kind rather than by a byte
# in its slot: the slot is exactly full, and the kind is already there.
DROP_KIND_IDS = {name: index for index, name in enumerate(DROPS)}
KIND_DROPS = {kind.name: kind.drop for kind in _GAME.kinds}
# Engine vocabulary in a level file. Each value has a neutral name and the
# name the showcase was written with; both mean the same thing.
UNLOCK_WHEN_CLEARED = ("enemies_cleared", "sentinel_dead")
# A game with items drops item types: each actor leaves its kind's drop, or
# the one its level names for it, or nothing (NO_DROP).
ITEM_DROPS = bool(_GAME.items)
NO_DROP = 0xFF
# An actor's wake radius beside the level's: its kind byte's bits 4-5 pick
# one of these (cells, exclusive, on both axes), and bit 6 asks for sight too.
WAKE_RADII = {2: 1, 4: 2, 7: 3}            # authored cells -> the kind byte's code
WAKE_CELLS = (3, 5, 8)                      # code 1..3 -> the radius the AI compares against
KIND_WAKE_SHIFT = 4
KIND_SIGHT = 0x40
DROP_SOURCES = ("drop", "sentinel_drop")

# Campaign levels are packed five to a ROM bank from LEVEL_ROM_BANK_BASE, in
# 256-byte-aligned slots, at fixed offsets inside the slot. A resident
# directory gives the loader each level's bank and the page of its slot; every
# reader adds that page to the high byte of its offset, so the first slot of a
# bank (page 0) reads exactly as the one-level-per-bank layout did.
# lookup_segment_id reads the segment and its surface through one pointer, so
# the surface table must stay exactly 1024 bytes above the segment table.
LEVEL_ROM_BANK_BASE = 241
LEVELS_PER_BANK = 5
LEVEL_SLOT_PITCH = 0x0B00       # 2,816 bytes: the payload rounded up to a page
LEVEL_SEGMENT_OFFSET = 0x4000   # 1024 bytes, indexed (cell * 4 + side)
LEVEL_SURFACE_OFFSET = 0x4400   # 1024 bytes, same index
LEVEL_GRID_OFFSET = 0x4800      # the 16x16 world map
LEVEL_HEADER_OFFSET = 0x4900
LEVEL_DOOR_OFFSET = 0x4920      # MAX_DOORS * DOOR_RECORD_BYTES, 16-aligned
LEVEL_ACTOR_OFFSET = 0x4950     # MAX_ACTORS * 16 bounded Sentinel slots
LEVEL_FIXTURE_OFFSET = 0x49B0   # MAX_FIXTURES * 16 wall-mounted landmarks
# The slot's tail holds the placed items, the loadout and the triggers
# (CompiledLevel.extras_bytes), inside the slot pitch.
LEVEL_EXTRAS_OFFSET = 0x4AB0
MAX_ITEMS = _LIMITS["items_per_level"].maximum
MAX_TRIGGERS = _LIMITS["triggers_per_level"].maximum
EXTRAS_ITEMS = 1                 # after the item count: MAX_ITEMS (cell, type) pairs
EXTRAS_LOADOUT = EXTRAS_ITEMS + 2 * MAX_ITEMS          # pool 0, pool 1, armour
EXTRAS_TRIGGER_COUNT = EXTRAS_LOADOUT + 3
EXTRAS_TRIGGERS = EXTRAS_TRIGGER_COUNT + 1             # MAX_TRIGGERS (cell, door index) pairs
EXTRAS_DROPS = EXTRAS_TRIGGERS + 2 * MAX_TRIGGERS    # MAX_ACTORS item types an actor leaves
EXTRAS_BYTES = EXTRAS_DROPS + MAX_ACTORS
INFINITE_AMMO = 0xFF
LEVEL_PAYLOAD_END = LEVEL_EXTRAS_OFFSET + EXTRAS_BYTES
assert LEVEL_DOOR_OFFSET + MAX_DOORS * DOOR_RECORD_BYTES <= LEVEL_ACTOR_OFFSET
assert LEVEL_ACTOR_OFFSET + MAX_ACTORS * 16 <= LEVEL_FIXTURE_OFFSET
assert LEVEL_FIXTURE_OFFSET + MAX_FIXTURES * 16 <= LEVEL_EXTRAS_OFFSET
assert LEVEL_PAYLOAD_END - 0x4000 <= LEVEL_SLOT_PITCH, "a level payload overruns its slot"
assert LEVELS_PER_BANK * LEVEL_SLOT_PITCH <= 0x4000, "level slots overrun their bank"
assert LEVEL_SLOT_PITCH % 256 == 0, "the loader adds a slot's page to the high byte alone"


def level_location(index: int) -> tuple[int, int]:
    """(ROM bank, page offset of the slot) of campaign level `index`.

    The page offset is what the console adds to the high byte of every
    slot-relative offset: 0 for a bank's first slot, LEVEL_SLOT_PITCH >> 8 for
    the second, and so on.
    """
    bank, slot = divmod(index, LEVELS_PER_BANK)
    return LEVEL_ROM_BANK_BASE + bank, slot * (LEVEL_SLOT_PITCH >> 8)


def level_rom_offset(index: int) -> int:
    """Absolute ROM offset of the level's slot (its `$4000`)."""
    bank, page = level_location(index)
    return bank * 0x4000 + (page << 8)
# The campaign is the game's: its manifest's episodes list the level files in
# order (lupine3d_v4/game.py), and that order is the campaign, the
# continue-code table and the level directory. LUPINE3D_LEVEL still selects a
# single level for diagnostic and research builds, a one-level campaign.
# CAMPAIGN_ORDER is the file names of the game's campaign, kept for tools
# that name levels by file.
CAMPAIGN_ORDER = tuple(path.name for path in _GAME.level_paths)


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
    drop: int = NO_DROP        # with items: the item type it leaves, or NO_DROP
    wake: int = 0              # 0: the level's radius; else WAKE_CELLS[wake - 1]
    sight: bool = False        # waking needs a clear line to the player as well

    @property
    def kind_byte(self) -> int:
        return ENTITY_KIND_IDS[self.kind] | (self.wake << KIND_WAKE_SHIFT) | (KIND_SIGHT if self.sight else 0)


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
    surface_table: bytes
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
    fixtures: tuple[tuple[int, int, int, int], ...] = ()
    song: int = 1                      # the world song, SONG_IDS["world"]
    items: tuple[tuple[int, int, int], ...] = ()       # (x, y, item type)
    loadout: tuple[int, int, int] = (INFINITE_AMMO, INFINITE_AMMO, 0)   # pool 0, pool 1, armour
    triggers: tuple[tuple[int, int, int], ...] = ()    # (x, y, door index) a step onto the cell opens

    def header_bytes(self) -> bytes:
        """Fixed per-level header consumed by the SM83 loader.

        Bytes 0..17 are the original resident header. The counts that follow
        used to be assembled as immediate operands from the single build-time
        level; the loader reads them so one ROM can carry a campaign.
        """
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
            len(self.entities), len(self.fixtures), self.medkit_value, self.song,
        )).ljust(LEVEL_HEADER_BYTES, b"\0")

    @property
    def medkit_value(self) -> int:
        """The health a medkit drop restores; the only per-level drop number
        (a game with items gives each item type its own)."""
        return next((p.value for p in self.pickups if p.kind == "medkit"), 0)

    def extras_bytes(self) -> bytes:
        """The slot tail load_level reads: items, loadout and triggers."""
        items = b"".join(bytes(((y << 4) | x, kind)) for x, y, kind in self.items)
        triggers = b"".join(bytes(((y << 4) | x, door)) for x, y, door in self.triggers)
        drops = bytes(entity.drop for entity in self.entities).ljust(MAX_ACTORS, bytes((NO_DROP,)))
        data = (bytes((len(self.items),)) + items.ljust(2 * MAX_ITEMS, b"\0")
                + bytes(self.loadout) + bytes((len(self.triggers),)) + triggers.ljust(2 * MAX_TRIGGERS, b"\0")
                + drops)
        assert len(data) == EXTRAS_BYTES
        return data

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
        # Opening a door exposes its jambs. Allocate those latent faces at
        # build time as well; ID zero must never masquerade as continuity.
        return material(x + dx, y + dy) in (0, 3)

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



def _validate_keycard_gates(
    grid: bytes, width: int, height: int, start: tuple[int, int],
    entities: tuple[EntitySpec, ...], doors: tuple[DoorSpec, ...],
    pickups: tuple[PickupSpec, ...], placed_cards: bool = False,
) -> None:
    """A keycard door has to be openable, which is a property of the level.

    A dead actor's drop follows from its kind, so a level that locks a door
    behind a card is solvable only if an actor of a card-dropping kind can be
    reached and killed without passing through any such door. That also keeps
    the controller route honest: it clears every actor and takes every drop
    before it walks to the exit, so a card it could not reach would deadlock
    it rather than merely make the level unfair.
    """
    keyed = [door for door in doors if door.flags & DOOR_FLAG_KEYCARD]
    declared = {pickup.kind for pickup in pickups}
    dropped = {KIND_DROPS[entity.kind] for entity in entities}
    unauthored = declared - dropped
    if unauthored and not ITEM_DROPS:
        raise ValueError(f"declared drops no actor leaves: {sorted(unauthored)}")
    passable = _passable_cells(grid, width, height)
    # Every actor stands on a walkable cell the player can walk to with the
    # Sentinel-locked doors shut, whether or not the level has a card door:
    # those doors open only once every actor is dead, so an actor behind one
    # (or inside a wall) can never be engaged and the route would deadlock.
    locked = {(door.x, door.y) for door in doors if door.flags & DOOR_FLAG_LOCK_SENTINEL}
    engageable = _reachable_cells(passable - locked, start)
    for entity in entities:
        cell = (entity.x_q8 >> 8, entity.y_q8 >> 8)
        if grid[cell[1] * width + cell[0]] != 0:
            raise ValueError(f"actor at cell {cell} is not on a walkable cell")
        if cell not in engageable:
            raise ValueError(f"actor at cell {cell} is behind a door that opens only when the enemies are cleared, or unreachable")
    if ITEM_DROPS or placed_cards:
        return      # _validate_gates walks placed cards, drops and triggers together
    if not keyed:
        if "keycard" in declared:
            raise ValueError("a declared keycard drop opens nothing in this level")
        return
    if "keycard" not in declared:
        raise ValueError("a keycard door needs the level to declare its card drop")
    # Every keycard door is a wall until the card is in hand.
    without_cards = passable - {(door.x, door.y) for door in keyed}
    before = _reachable_cells(without_cards, start)
    carriers = [
        entity for entity in entities
        if KIND_DROPS[entity.kind] == "keycard"
        and (entity.x_q8 >> 8, entity.y_q8 >> 8) in before
    ]
    if not carriers:
        raise ValueError("no card-dropping actor is reachable with the keycard doors shut")


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


def build_surface_table(grid: bytes, overrides: list[dict[str, Any]], width: int = 16) -> bytes:
    """One presentation profile per oriented face, independent of geometry.

    Deliberately small initial vocabulary: neutral structure, machinery and
    cyan doors. Unknown profiles/duplicate records are errors, not ignored.
    """
    profiles = {"structure": 0, "machinery": 1, "door": 2}
    sides = {"west": 0, "east": 1, "north": 2, "south": 3}
    result = bytearray(profile for material in grid for profile in [(1 if material == 2 else 2 if material == 3 else 0)] * 4)
    seen = set()
    for item in overrides:
        x, y = int(item["x"]), int(item["y"])
        if not 0 <= x < width or not 0 <= y < len(grid) // width or not grid[y * width + x]:
            raise ValueError("surface record must address a solid cell")
        index = (y * width + x) * 4 + sides[str(item["side"])]
        if index in seen:
            raise ValueError("duplicate per-face surface record")
        seen.add(index)
        profile = profiles[str(item["profile"])]
        if (grid[y * width + x] == 3) != (profile == 2):
            raise ValueError("the door colour signal is reserved for functioning doors")
        result[index] = profile
    return bytes(result)


def _theme_id(name: str) -> int:
    if name not in PALETTE_IDS:
        raise ValueError(f"palette_profile {name!r} is not a theme of {_GAME.id} "
                         f"({', '.join(PALETTE_IDS)}; game.json `themes`)")
    return PALETTE_IDS[name]


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
            | (DOOR_FLAG_LOCK_SENTINEL if str(item.get("unlock", "none")) in UNLOCK_WHEN_CLEARED else 0)
            | (DOOR_FLAG_KEYCARD if str(item.get("unlock", "none")) == "keycard" else 0)
            | (DOOR_FLAG_REMOTE if item.get("remote", False) is True else 0)
            | (_door_key(item, path) << DOOR_KEY_SHIFT),
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
    for door in doors:
        if door.flags & DOOR_FLAG_REMOTE and door.flags & (DOOR_FLAG_EXIT | DOOR_FLAG_LOCK_SENTINEL | DOOR_FLAG_KEYCARD):
            raise ValueError(f"door {door.name}: a remote door opens only by its trigger, so it cannot also be "
                             "the exit or wait for a card or for the enemies")
    entities = tuple(
        EntitySpec(
            kind=str(item["kind"]),
            x_q8=_bounded_int(item, "x_q8", 0, width * 256 - 1),
            y_q8=_bounded_int(item, "y_q8", 0, height * 256 - 1),
            health=_bounded_int(item, "health", 1, 255),
            activation_radius_q4=_bounded_int(item, "activation_radius_q4", 1, 127),
            drop=_entity_drop(item, path),
            wake=_entity_wake(item, path),
            sight=_entity_sight(item, path),
        )
        for item in source.get("entities", [])
    )
    pickups = tuple(
        PickupSpec(str(item["kind"]), str(item["source"]), _bounded_int(item, "value", 1, 255))
        for item in source.get("pickups", [])
    )
    if not 1 <= len(entities) <= MAX_ACTORS:
        raise ValueError(f"levels require one to {MAX_ACTORS} actors")
    unknown = [entity.kind for entity in entities if entity.kind not in ENTITY_KIND_IDS]
    if unknown:
        raise ValueError(f"unknown enemy kinds {sorted(set(unknown))}: {_GAME.id}'s kinds are "
                         f"{', '.join(ENTITY_KIND_IDS)} (game.json `kinds`)")
    # Every pickup is a drop from a dead actor; its kind follows from that
    # actor's kind, so a level declares which drops it fields rather than
    # placing them. The medkit's value is the only per-level number. A game
    # with items drops item types instead, named by kind or per actor.
    if ITEM_DROPS:
        pass
    elif not 1 <= len(pickups) <= len(DROP_KIND_IDS):
        raise ValueError(f"levels declare one to {len(DROP_KIND_IDS)} drops")
    if not ITEM_DROPS:
        if any(pickup.source not in DROP_SOURCES for pickup in pickups):
            raise ValueError("every drop comes from a dead actor")
        kinds = [pickup.kind for pickup in pickups]
        if len(set(kinds)) != len(kinds) or set(kinds) - set(DROP_KIND_IDS):
            raise ValueError(f"drop kinds must be distinct and one of {sorted(DROP_KIND_IDS)}")
        if "medkit" not in kinds:
            raise ValueError("a level must field the medkit drop its actors leave")
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
            raise ValueError("v2 gameplay levels require exactly one exit door (\"kind\": \"exit\") that opens when the enemies are cleared (\"unlock\": \"enemies_cleared\")")
    items, loadout, triggers = _extras(source, path, grid, width, height, doors, exit_spec,
                                       (player_x_q8 >> 8, player_y_q8 >> 8))
    _validate_keycard_gates(grid, width, height,
                            (player_x_q8 >> 8, player_y_q8 >> 8), entities, doors, pickups,
                            any(_GAME.items[kind].effect == "key" for _, _, kind in items))
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
    _validate_gates(grid, width, height, (player_x_q8 >> 8, player_y_q8 >> 8), entities, doors, items, triggers, exit_spec)
    fixtures = []
    sides = {"west": 0, "east": 1, "north": 2, "south": 3}
    kinds = {name: index for index, name in enumerate(_GAME.fixture_kinds)}
    for fixture in source.get("fixtures", []):
        x = _bounded_int(fixture, "x", 0, width-1); y = _bounded_int(fixture, "y", 0, height-1)
        side = sides[fixture["side"]]
        if fixture["kind"] not in kinds:
            raise ValueError(f"fixture kind {fixture['kind']!r} is not one of {_GAME.id}'s "
                             f"({', '.join(kinds)}; game.json `fixture_kinds`)")
        kind = kinds[fixture["kind"]]
        dx,dy = ((-1,0),(1,0),(0,-1),(0,1))[side]
        if not grid[y*width+x] or not (0 <= x+dx < width and 0 <= y+dy < height):
            raise ValueError("fixture requires an interior wall face")
        if grid[(y+dy)*width+x+dx] not in (0,3): raise ValueError("fixture face must be exposed")
        if grid[y*width+x] == 3:
            door = next(d for d in doors if d.x==x and d.y==y)
            if side//2 != door.orientation: raise ValueError("door fixture must face the moving panel")
        record = (x,y,side,kind)
        if record in fixtures: raise ValueError("duplicate wall fixture")
        fixtures.append(record)
    if len(fixtures) > 16: raise ValueError("at most 16 authored wall fixtures")
    return CompiledLevel(
        format=level_format, name=str(source["name"]), width=width, height=height, grid=grid,
        segment_table=build_segment_table(grid, width, height),
        surface_table=build_surface_table(grid, source.get("surfaces", []), width),
        player_x_q8=player_x_q8,
        player_y_q8=player_y_q8,
        player_angle=_bounded_int(spawn, "angle", 0, 255),
        safe_radius_cells=safe_radius_cells,
        doors=doors, entities=entities, pickups=pickups, exit=exit_spec,
        palette_profile=_theme_id(str(source["palette_profile"])),
        vram_profile=PROFILE_IDS[str(source["vram_profile"])],
        readability=readability,
        fixtures=tuple(fixtures),
        song=_song_id(source.get("music", "world"), path),
        items=items, loadout=loadout, triggers=triggers,
    )


def _entity_drop(item: dict[str, Any], path: Path) -> int:
    """With items: the item type an actor leaves (its own `drop`, else its
    kind's), or NO_DROP. Without items the kind alone decides."""
    if not ITEM_DROPS:
        if "drop" in item:
            raise ValueError(f"{path.name}: an entity's drop needs the game to define items")
        return NO_DROP
    name = item.get("drop", KIND_DROPS.get(str(item.get("kind")), "none"))
    if name == "none":
        return NO_DROP
    if name not in _GAME.item_ids:
        raise ValueError(f"{path.name}: drop {name!r} is not one of {_GAME.id}'s items ({', '.join(_GAME.item_ids)}) or none")
    return _GAME.item_ids[name]


def _entity_wake(item: dict[str, Any], path: Path) -> int:
    if "wake" not in item:
        return 0
    if item["wake"] not in WAKE_RADII:
        raise ValueError(f"{path.name}: an entity's wake is {item['wake']!r}; it is one of "
                         f"{', '.join(map(str, WAKE_RADII))} cells (or left out for the level's radius)")
    return WAKE_RADII[item["wake"]]


def _entity_sight(item: dict[str, Any], path: Path) -> bool:
    sight = item.get("sight", False)
    if not isinstance(sight, bool):
        raise ValueError(f"{path.name}: an entity's sight is true or false")
    return sight


def _door_key(item: dict[str, Any], path: Path) -> int:
    """A card door's key colour, plus one (0: any card opens it)."""
    if "key" not in item:
        return 0
    if str(item.get("unlock", "none")) != "keycard":
        raise ValueError(f"{path.name}: door {item.get('id')}: a key colour needs \"unlock\": \"keycard\"")
    if item["key"] not in _GAME.keys:
        raise ValueError(f"{path.name}: door {item.get('id')}: key {item['key']!r} is not one of {_GAME.id}'s keys "
                         f"({', '.join(_GAME.keys) or 'none: add `keys` to game.json'})")
    return _GAME.keys.index(item["key"]) + 1


def _extras(source: dict[str, Any], path: Path, grid: bytes, width: int, height: int,
            doors: tuple[DoorSpec, ...], exit_spec: ExitSpec, spawn: tuple[int, int],
            ) -> tuple[tuple[tuple[int, int, int], ...], tuple[int, int, int], tuple[tuple[int, int, int], ...]]:
    """Placed items, the loadout and the triggers: what the slot tail holds."""
    item_ids = _GAME.item_ids
    raw_items = source.get("items", [])
    if len(raw_items) > MAX_ITEMS:
        raise ValueError(f"{path.name}: {_LIMITS['items_per_level'].what}: {len(raw_items)} is more than {MAX_ITEMS}")
    items, cells = [], set()
    for index, raw in enumerate(raw_items):
        name = str(raw.get("item"))
        if name not in item_ids:
            raise ValueError(f"{path.name}: items[{index}] {name!r} is not one of {_GAME.id}'s items "
                             f"({', '.join(item_ids) or 'none: add `items` to game.json'})")
        x, y = _bounded_int(raw, "x", 1, width - 2), _bounded_int(raw, "y", 1, height - 2)
        if grid[y * width + x]:
            raise ValueError(f"{path.name}: items[{index}] {name} at ({x}, {y}) is not on a walkable cell")
        if (x, y) in cells or (x, y) in ((exit_spec.x, exit_spec.y), spawn):
            raise ValueError(f"{path.name}: items[{index}] {name} at ({x}, {y}) shares its cell with another item, "
                             "the exit or the player's spawn")
        cells.add((x, y))
        items.append((x, y, item_ids[name]))
    loadout = (INFINITE_AMMO, INFINITE_AMMO, 0)
    if "loadout" in source:
        raw = source["loadout"]
        allowed = set(_GAME.ammo) | {"armour"}
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ValueError(f"{path.name}: loadout names {unknown}; it takes {', '.join(sorted(allowed))}")
        pools = [_bounded_int(raw, name, 0, _LIMITS["ammo"].maximum) if name in raw else 0 for name in _GAME.ammo]
        pools += [INFINITE_AMMO] * (2 - len(pools))
        loadout = (pools[0], pools[1], _bounded_int(raw, "armour", 0, 100) if "armour" in raw else 0)
    names = {door.name: index for index, door in enumerate(doors)}
    triggers, trigger_cells = [], set()
    for index, raw in enumerate(source.get("triggers", [])):
        kind = str(raw.get("kind"))
        if kind == "activate_exit":
            continue        # the exit opening when the enemies are cleared: every level's, stated in its doors
        if kind != "open_door":
            raise ValueError(f"{path.name}: triggers[{index}] kind {kind!r} must be open_door or activate_exit")
        door = str(raw.get("door"))
        if door not in names or not doors[names[door]].flags & DOOR_FLAG_REMOTE:
            raise ValueError(f"{path.name}: triggers[{index}] opens {door!r}, which is not a remote door of this level")
        x, y = _bounded_int(raw, "x", 1, width - 2), _bounded_int(raw, "y", 1, height - 2)
        if grid[y * width + x] or (x, y) in trigger_cells:
            raise ValueError(f"{path.name}: triggers[{index}] at ({x}, {y}) must be a walkable cell of its own")
        trigger_cells.add((x, y))
        triggers.append((x, y, names[door]))
    if len(triggers) > MAX_TRIGGERS:
        raise ValueError(f"{path.name}: {_LIMITS['triggers_per_level'].what}: {len(triggers)} is more than {MAX_TRIGGERS}")
    opened = {door for _, _, door in triggers}
    for index, door in enumerate(doors):
        if door.flags & DOOR_FLAG_REMOTE and index not in opened:
            raise ValueError(f"{path.name}: remote door {door.name} has no trigger that opens it")
    return tuple(items), loadout, tuple(triggers)


def _validate_gates(grid: bytes, width: int, height: int, start: tuple[int, int],
                    entities: tuple[EntitySpec, ...], doors: tuple[DoorSpec, ...],
                    items: tuple[tuple[int, int, int], ...], triggers: tuple[tuple[int, int, int], ...],
                    exit_spec: ExitSpec) -> None:
    """Every card door, remote door and placed item has to be reachable in play.

    Walk the level as the player can: card doors open once a card of their
    colour is in hand (a placed card, or the one a card-dropping actor
    leaves, which is the first colour), remote doors once their trigger's cell
    is reached; the doors that open when the enemies are cleared stay shut.
    Everything must be reached that way."""
    if not ITEM_DROPS and not items and not triggers and not any(
            door.flags & (DOOR_FLAG_REMOTE | (3 << DOOR_KEY_SHIFT)) for door in doors):
        return      # nothing but what _validate_keycard_gates already proves
    passable = _passable_cells(grid, width, height)
    locked = {(door.x, door.y) for door in doors if door.flags & DOOR_FLAG_LOCK_SENTINEL}
    gated = {index for index, door in enumerate(doors) if door.flags & (DOOR_FLAG_KEYCARD | DOOR_FLAG_REMOTE)}
    item_types = _GAME.items
    keys, opened = 0, set()
    while True:
        closed = locked | {(doors[i].x, doors[i].y) for i in gated - opened}
        reach = _reachable_cells(passable - closed, start)
        found = keys
        for x, y, kind in items:
            if (x, y) in reach and item_types[kind].effect == "key":
                found |= item_types[kind].value
        for entity in entities:
            if (entity.x_q8 >> 8, entity.y_q8 >> 8) not in reach:
                continue
            if ITEM_DROPS:
                if entity.drop != NO_DROP and item_types[entity.drop].effect == "key":
                    found |= item_types[entity.drop].value
            elif KIND_DROPS[entity.kind] == "keycard":
                found |= 1
        now = set(opened)
        for x, y, door in triggers:
            if (x, y) in reach:
                now.add(door)
        for index in gated:
            flags = doors[index].flags
            if flags & DOOR_FLAG_KEYCARD:
                colour = (flags >> DOOR_KEY_SHIFT) & 3
                if (colour == 0 and found) or (colour and found & (1 << (colour - 1))):
                    now.add(index)
        if (found, now) == (keys, opened):
            break
        keys, opened = found, now
    for index in sorted(gated - opened):
        raise ValueError(f"door {doors[index].name} can never be opened: its card or its trigger is out of reach")
    for x, y, kind in items:
        if (x, y) not in reach:
            raise ValueError(f"the {item_types[kind].name} at ({x}, {y}) can never be reached")
    for entity in entities:
        cell = (entity.x_q8 >> 8, entity.y_q8 >> 8)
        if cell not in reach:
            raise ValueError(f"the {entity.kind} at cell {cell} can never be reached")


def _song_id(name: object, path: Path) -> int:
    if name not in SONG_IDS:
        raise ValueError(f"{path.name}: music {name!r} is not one of the game's songs ({', '.join(SONG_IDS)})")
    return SONG_IDS[name]


# The engine's evidence (goldens, witnesses, cycle gates, the sustained tapes)
# was recorded on the showcase's first sector as v0.12 populated it. The
# sector's geometry is frozen; its population is the game's to change. A
# process run with LUPINE3D_POPULATION=evidence swaps in the frozen v0.12
# population, so the evidence keeps measuring the scene it was recorded on
# while the shipped game moves on. Only the population may differ: the
# swap refuses a sector whose frozen fields disagree with the fixture.
POPULATIONS = ("shipped", "evidence")
EVIDENCE_LEVEL = Path(__file__).resolve().parents[2] / "tests" / "levels" / "living_world_v012.json"


def population() -> str:
    """`LUPINE3D_POPULATION`: `shipped` (the default) or `evidence`."""
    value = os.environ.get("LUPINE3D_POPULATION", "shipped")
    if value not in POPULATIONS:
        raise ValueError(f"LUPINE3D_POPULATION must be one of {', '.join(POPULATIONS)}, not {value!r}")
    return value


def frozen_fields(level: CompiledLevel) -> dict[str, Any]:
    """What the evidence population holds fixed: everything but who is in the sector."""
    return dict(
        grid=level.grid, segment_table=level.segment_table, surface_table=level.surface_table,
        spawn=(level.player_x_q8, level.player_y_q8, level.player_angle, level.safe_radius_cells),
        exit=level.exit, fixtures=level.fixtures,
        doors=tuple((door.name, door.x, door.y, door.orientation) for door in level.doors),
        profiles=(level.palette_profile, level.vram_profile),
    )


def evidence_level(shipped: CompiledLevel) -> CompiledLevel:
    """The frozen v0.12 population of the showcase's first sector, checked
    against the shipped sector's frozen fields."""
    frozen = compile_level(EVIDENCE_LEVEL)
    expected, actual = frozen_fields(frozen), frozen_fields(shipped)
    moved = [name for name in expected if expected[name] != actual[name]]
    if moved:
        raise ValueError(f"the showcase's first sector changed its frozen {', '.join(moved)}: the evidence "
                         f"population ({EVIDENCE_LEVEL.name}) only replaces who is in the sector")
    return frozen


def campaign(game: Game | None = None) -> tuple[CompiledLevel, ...]:
    """The game's ordered campaign, or the single level a diagnostic build selected.

    Under the evidence population the showcase's first sector is the frozen
    v0.12 one; a single-level build and any other game have no such sector,
    so the setting does not apply to them."""
    configured = os.environ.get("LUPINE3D_LEVEL")
    evidence = population() == "evidence"
    if configured:
        return (compile_level(Path(configured).resolve()),)
    game = game or _GAME
    levels = [compile_level(path) for path in game.level_paths]
    if evidence and game.is_showcase:
        levels[0] = evidence_level(levels[0])
    return tuple(levels)


def active_level(game: Game | None = None) -> CompiledLevel:
    return campaign(game)[0]
