#!/usr/bin/env python3
"""Build Lupine 3D v0.2.2: exact DDA + low-noise material renderer."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sm83 import Assembler  # noqa: E402
import build_rom_v1 as v1  # noqa: E402

BUILD = ROOT / "build"
BUILD.mkdir(parents=True, exist_ok=True)

# Hardware registers (LDH offsets).
P1 = v1.P1
NR10, NR11, NR12, NR13, NR14 = v1.NR10, v1.NR11, v1.NR12, v1.NR13, v1.NR14
NR50, NR51, NR52 = v1.NR50, v1.NR51, v1.NR52
LCDC, SCY, SCX, LY = v1.LCDC, v1.SCY, v1.SCX, v1.LY
KEY1, VBK = v1.KEY1, v1.VBK
HDMA1, HDMA2, HDMA3, HDMA4, HDMA5 = v1.HDMA1, v1.HDMA2, v1.HDMA3, v1.HDMA4, v1.HDMA5
BGPI, BGPD, OBPI, OBPD, SVBK = v1.BGPI, v1.BGPD, v1.OBPI, v1.OBPD, v1.SVBK

# WRAM0 frame-composition buffers.
DYNAMIC_TILES = 0xC000          # 96 * 16 = 1536 bytes
VIEW_MAP = 0xC600               # 12 rows * 32 bytes = 384 bytes
DYNAMIC_TILE_CAPACITY = 96

# Existing gameplay state remains stable for compatibility with v0.1.0 tests.
MAP = v1.MAP
PLAYER_XL, PLAYER_XH = v1.PLAYER_XL, v1.PLAYER_XH
PLAYER_YL, PLAYER_YH = v1.PLAYER_YL, v1.PLAYER_YH
ANGLE, BUTTONS, PREV_BUTTONS = v1.ANGLE, v1.BUTTONS, v1.PREV_BUTTONS
FLASH, CURRENT_PAGE, PRESSED = v1.FLASH, v1.CURRENT_PAGE, v1.PRESSED

# 80 compact ray descriptors in switchable WRAM bank 1.
RAY_TOPS = 0xD200
RAY_STYLES = 0xD250
RAY_KEYS = 0xD300
RAY_ALONG = 0xD350

# DDA state.
DDA_MAP_X = 0xD2A0
DDA_MAP_Y = 0xD2A1
DDA_ABS_X = 0xD2A2
DDA_ABS_Y = 0xD2A3
DDA_STEP_X = 0xD2A4
DDA_STEP_Y = 0xD2A5
DDA_NEXT_X_L = 0xD2A6
DDA_NEXT_X_H = 0xD2A7
DDA_NEXT_Y_L = 0xD2A8
DDA_NEXT_Y_H = 0xD2A9
DDA_ERR_L = 0xD2AA
DDA_ERR_H = 0xD2AB
DDA_AXIS = 0xD2AC
DDA_DIST_L = 0xD2AD
DDA_DIST_H = 0xD2AE
DDA_MATERIAL = 0xD2AF
DDA_CROSSINGS = 0xD2B0
DDA_ANGLE_L = 0xD2B1
DDA_ANGLE_H = 0xD2B2
DDA_CORRECTION = 0xD2B3
TOP_RESULT = 0xD2B4
STYLE_RESULT = 0xD2B5
FACE_RESULT = 0xD2B6
ALONG_RESULT = 0xD2B7
ADAPTIVE_CASTS = 0xD2B8
CAST_INDEX = 0xD2B9
ADAPTIVE_INDEX = 0xD2BA

# Cast loop pointers.
CAST_OFFSET_PTR_L = 0xD2C0
CAST_OFFSET_PTR_H = 0xD2C1
CAST_CORR_PTR_L = 0xD2C2
CAST_CORR_PTR_H = 0xD2C3
CAST_TOP_PTR_L = 0xD2C4
CAST_TOP_PTR_H = 0xD2C5
CAST_STYLE_PTR_L = 0xD2C6
CAST_STYLE_PTR_H = 0xD2C7
CAST_COUNT = 0xD2C8

# Tile compositor state.
DYN_COUNT = 0xD2D0
DYN_HIGH_WATER = 0xD2D1
DYN_OVERFLOW = 0xD2D2
DYN_PTR_L = 0xD2D3
DYN_PTR_H = 0xD2D4
MAP_PTR_L = 0xD2D5
MAP_PTR_H = 0xD2D6
SCAN_TOP_PTR_L = 0xD2D7
SCAN_TOP_PTR_H = 0xD2D8
SCAN_STYLE_PTR_L = 0xD2D9
SCAN_STYLE_PTR_H = 0xD2DA
TILE_ROW = 0xD2DB
TILE_Y0 = 0xD2DC
TILE_COL_COUNT = 0xD2DD
MIN_TOP = 0xD2DE
MAX_TOP = 0xD2DF
FIRST_STYLE = 0xD2E0
STYLE_DIFF = 0xD2E1
CLASSIFY_COUNT = 0xD2E2
DYNAMIC_FLAG = 0xD2E3
GEN_GLOBAL_Y = 0xD2E4
GEN_ROW_COUNT = 0xD2E5
GEN_PAIR_COUNT = 0xD2E6
ACC_LOW = 0xD2E7
ACC_HIGH = 0xD2E8
TEMP_TOP = 0xD2E9
TEMP_STYLE = 0xD2EA
TILE_ID_RESULT = 0xD2EB
ROW_PAD_COUNT = 0xD2EC
COLUMN_COUNT = 0xD2ED
ROW_RENDER_COUNT = 0xD2EE
COLUMN_MAP_L = 0xD2EF
COLUMN_MAP_H = 0xD2F0
COMPOSE_DST_L = 0xD2F1
COMPOSE_DST_H = 0xD2F2
STRIP_STATE = 0xD2F3
STRIP_STYLE = 0xD2F4
STRIP_PAIR = 0xD2F5

# Renderer constants / tile IDs.
RAYS = 80
RAY_WIDTH = 2
VIEWPORT = (160, 96)
CEILING_TILE = 96
FLOOR_TILE = 97
WALL_TILE_BASE = 98
STYLE_COUNT = 5
MICRO_STATE_COUNT = 19
STATIC_VIEW_TILES = 2 + STYLE_COUNT
FOV_DEGREES = 60.5
RAY_VECTOR_SCALE = 127

NINTENDO_LOGO = v1.NINTENDO_LOGO
rgb15 = v1.rgb15
words_le = v1.words_le
tile_from_pixels = v1.tile_from_pixels
make_ui_tiles = v1.make_ui_tiles
make_weapon_tiles = v1.make_weapon_tiles
make_map = v1.make_map
load_hl_abs = v1.load_hl_abs
store_hl_abs = v1.store_hl_abs


# Each material is authored at the compositor's native two-pixel horizontal
# resolution: eight rows by four two-pixel pairs.  Unlike the v0.2.0
# row-only patterns, every row contains both wall colours, so no material can
# form a full-width horizontal stripe when adjacent tiles repeat.
#
# Colour 2 is the warm midtone; colour 3 is the darker structural shade.
# Styles 0/1 and 2/3 are light/shadow orientation variants selected by exact
# DDA wall side. Style 4 is the reinforced door.
WALL_MATERIAL_NAMES = (
    "warm plaster - light face",
    "warm plaster - shadow face",
    "vertical tech panel - light face",
    "vertical tech panel - shadow face",
    "reinforced door panel",
)

WALL_PATTERNS: tuple[tuple[tuple[int, int, int, int], ...], ...] = (
    (  # 0: warm plaster, light-facing — intentionally flat and quiet
        (2, 2, 2, 2),
        (2, 2, 2, 2),
        (2, 2, 2, 2),
        (2, 2, 2, 2),
        (2, 2, 2, 2),
        (2, 2, 2, 2),
        (2, 2, 2, 2),
        (2, 2, 2, 2),
    ),
    (  # 1: warm plaster, shadow-facing — flat exact-side shadow
        (3, 3, 3, 3),
        (3, 3, 3, 3),
        (3, 3, 3, 3),
        (3, 3, 3, 3),
        (3, 3, 3, 3),
        (3, 3, 3, 3),
        (3, 3, 3, 3),
        (3, 3, 3, 3),
    ),
    (  # 2: technology/stone, light-facing — vertical frame, sparse rivets
        (3, 2, 2, 2),
        (3, 2, 2, 2),
        (3, 2, 3, 2),
        (3, 2, 2, 2),
        (3, 2, 2, 2),
        (3, 2, 2, 3),
        (3, 2, 2, 2),
        (3, 2, 2, 2),
    ),
    (  # 3: technology/stone, shadow-facing — dark slab with a lit rim
        (2, 3, 3, 3),
        (2, 3, 3, 3),
        (2, 3, 2, 3),
        (2, 3, 3, 3),
        (2, 3, 3, 3),
        (2, 3, 3, 2),
        (2, 3, 3, 3),
        (2, 3, 3, 3),
    ),
    (  # 4: reinforced door — bright plate with a dark vertical spine
        (2, 2, 3, 2),
        (2, 2, 3, 2),
        (2, 3, 3, 2),
        (2, 2, 3, 2),
        (2, 2, 3, 2),
        (3, 2, 3, 2),
        (2, 2, 3, 2),
        (2, 2, 3, 2),
    ),
)

WALL_BASE_COLORS = (2, 3, 2, 3, 2)



def validate_wall_patterns() -> None:
    if len(WALL_PATTERNS) != STYLE_COUNT:
        raise ValueError("wall pattern/style count mismatch")
    for style, pattern in enumerate(WALL_PATTERNS):
        if len(pattern) != 8 or any(len(row) != 4 for row in pattern):
            raise ValueError(f"style {style} must be an 8x4 pair pattern")
        base = WALL_BASE_COLORS[style]
        for row in pattern:
            if any(color not in (2, 3) for color in row):
                raise ValueError(f"style {style} uses a non-wall colour")
            # A uniform base-colour row is visually flat, not a stripe. A
            # uniform non-base row would recreate the old full-width bands.
            if len(set(row)) == 1 and row[0] != base:
                raise ValueError(f"style {style} contains a full-width contrast band")
    # Exact-side lighting must remain visible even after the contrast reduction.
    light0 = sum(color == 2 for row in WALL_PATTERNS[0] for color in row)
    dark0 = sum(color == 2 for row in WALL_PATTERNS[1] for color in row)
    light1 = sum(color == 2 for row in WALL_PATTERNS[2] for color in row)
    dark1 = sum(color == 2 for row in WALL_PATTERNS[3] for color in row)
    if not (light0 > dark0 and light1 > dark1):
        raise ValueError("orientation variants lost their luminance ordering")


def wall_color(style: int, pair: int, y: int) -> int:
    """Return a phase-locked 2bpp wall colour at two-pixel pair granularity."""
    return WALL_PATTERNS[style][y & 7][pair & 3]


validate_wall_patterns()


def solid_tile(color: int) -> bytes:
    return tile_from_pixels([[color] * 8 for _ in range(8)])


def make_static_view_tiles() -> bytes:
    tiles = [solid_tile(0), solid_tile(1)]
    for style in range(STYLE_COUNT):
        pixels = [[wall_color(style, x // 2, row) for x in range(8)] for row in range(8)]
        tiles.append(tile_from_pixels(pixels))
    assert len(tiles) == STATIC_VIEW_TILES
    return b"".join(tiles)


def microstrip_region(state: int, row: int) -> str:
    if state == 0:
        return "ceiling"
    if state == 1:
        return "floor"
    if state == 2:
        return "wall"
    if 3 <= state <= 10:
        wall_start = state - 3
        return "ceiling" if row < wall_start else "wall"
    floor_start = state - 10  # states 11..18 encode rows 1..8
    return "wall" if row < floor_start else "floor"


def make_microstrips() -> bytes:
    """Precompose every 2-pixel boundary strip for four tile positions."""
    out = bytearray()
    for style in range(STYLE_COUNT):
        for state in range(MICRO_STATE_COUNT):
            for pair in range(4):
                shift = 6 - pair * 2
                mask = 0x03 << shift
                for row in range(8):
                    region = microstrip_region(state, row)
                    color = 0 if region == "ceiling" else 1 if region == "floor" else wall_color(style, pair, row)
                    out.extend((mask if color & 1 else 0, mask if color & 2 else 0))
    assert len(out) == STYLE_COUNT * MICRO_STATE_COUNT * 4 * 16
    return bytes(out)

def make_tilemap() -> bytes:
    data = bytearray([CEILING_TILE] * 1024)
    # Keep the lower HUD contract from v0.1.0.
    for x in range(20):
        data[12 * 32 + x] = 255
    data[14 * 32 + 1] = 251
    data[14 * 32 + 2] = 250
    data[14 * 32 + 3] = 250
    data[14 * 32 + 9] = 254
    data[14 * 32 + 15] = 252
    data[14 * 32 + 16] = 241
    data[14 * 32 + 17] = 249
    return bytes(data)


def make_attrmap(view_bank: int) -> bytes:
    data = bytearray([1] * 1024)  # HUD palette 1, tile bank 0
    for y in range(12):
        for x in range(20):
            data[y * 32 + x] = (view_bank << 3) | 0
    return bytes(data)


@lru_cache(maxsize=1)
def make_tables() -> dict[str, bytes]:
    # Legacy 256-direction Q8 vectors remain for movement and door reach.
    step_dx = bytearray()
    step_dy = bytearray()
    move_dx = bytearray()
    move_dy = bytearray()
    for angle in range(256):
        rad = angle * math.tau / 256.0
        step_dx.append(round(math.cos(rad) * 64) & 0xFF)
        step_dy.append(round(math.sin(rad) * 64) & 0xFF)
        move_dx.append(round(math.cos(rad) * 20) & 0xFF)
        move_dy.append(round(math.sin(rad) * 20) & 0xFF)

    # 1024-direction Q0.7-ish render vectors provide quarter-angle-unit
    # precision while keeping every signed component representable in one
    # byte. 127 is materially more accurate than v0.1.0's scale of 64 and
    # still keeps the DDA's 256*component cross-products inside signed 16-bit.
    ray_dx = bytearray()
    ray_dy = bytearray()
    for angle in range(1024):
        rad = angle * math.tau / 1024.0
        ray_dx.append(round(math.cos(rad) * RAY_VECTOR_SCALE) & 0xFF)
        ray_dy.append(round(math.sin(rad) * RAY_VECTOR_SCALE) & 0xFF)

    plane = math.tan(math.radians(FOV_DEGREES * 0.5))
    offsets: list[int] = []
    corrections = bytearray()
    for i in range(RAYS):
        screen_x = (i + 0.5) * VIEWPORT[0] / RAYS
        camera_x = 2.0 * screen_x / VIEWPORT[0] - 1.0
        off_rad = math.atan(camera_x * plane)
        offsets.append(round(off_rad * 1024.0 / math.tau))
        corrections.append(round(math.cos(off_rad) * RAY_VECTOR_SCALE))

    offsets_blob = bytearray()
    for value in offsets:
        value &= 0xFFFF
        offsets_blob.extend((value & 0xFF, value >> 8))

    projection_half = bytearray()
    for perpendicular_sixteenths in range(256):
        if perpendicular_sixteenths == 0:
            half = 48
        else:
            half = max(2, min(48, round(480.0 / perpendicular_sixteenths)))
        projection_half.append(half)

    return {
        "step_dx": bytes(step_dx), "step_dy": bytes(step_dy),
        "move_dx": bytes(move_dx), "move_dy": bytes(move_dy),
        "ray_dx": bytes(ray_dx), "ray_dy": bytes(ray_dy),
        "ray_offsets": bytes(offsets_blob), "ray_corrections": bytes(corrections),
        "projection_half": bytes(projection_half),
    }


@lru_cache(maxsize=1)
def reference_grid() -> bytes:
    """Immutable baseline map shared by host-side differential models."""
    return make_map()


@dataclass(frozen=True)
class ReferenceRayHit:
    ray_index: int
    angle_index: int
    dx: int
    dy: int
    map_x: int
    map_y: int
    axis: int
    axis_distance_q8: int
    material: int
    crossings: int
    top: int
    style: int
    face_key: int
    along: int


def reference_cast_hit(player_x_q8: int, player_y_q8: int, player_angle: int,
                       ray_index: int, grid: bytes | None = None) -> ReferenceRayHit:
    """Byte-exact host model of one ROM signed-error DDA ray."""
    if not 0 <= ray_index < RAYS:
        raise ValueError(f"ray index out of range: {ray_index}")
    tables = make_tables()
    off = int.from_bytes(tables["ray_offsets"][ray_index * 2:ray_index * 2 + 2], "little", signed=True)
    corr = tables["ray_corrections"][ray_index]
    angle_index = ((player_angle << 2) + off) & 0x3FF
    dx_raw = tables["ray_dx"][angle_index]
    dy_raw = tables["ray_dy"][angle_index]
    dx = dx_raw - 256 if dx_raw & 0x80 else dx_raw
    dy = dy_raw - 256 if dy_raw & 0x80 else dy_raw
    ax, ay = abs(dx), abs(dy)
    mx, my = player_x_q8 >> 8, player_y_q8 >> 8
    fx, fy = player_x_q8 & 0xFF, player_y_q8 & 0xFF
    nx = (256 - fx if dx > 0 else fx) if dx else 0x7FFF
    ny = (256 - fy if dy > 0 else fy) if dy else 0x7FFF
    sx = 1 if dx > 0 else -1
    sy = 1 if dy > 0 else -1
    if dx == 0:
        err = 0x7FFF
    elif dy == 0:
        err = -0x8000
    else:
        err = nx * ay - ny * ax
    cells = grid if grid is not None else reference_grid()
    material = 1
    axis = 0
    distance = 0x0FFF
    crossings = 0
    for crossings in range(1, 33):
        choose_x = dx != 0 and (dy == 0 or err <= 0)
        if choose_x:
            mx += sx
            axis, distance = 0, nx
        else:
            my += sy
            axis, distance = 1, ny
        if crossings >= 32:
            material = 1
            break
        material = cells[my * 16 + mx]
        if material:
            break
        if choose_x:
            nx += 256
            err += 256 * ay
        else:
            ny += 256
            err -= 256 * ax

    component = ax if axis == 0 else ay
    d16 = min(255, (distance + 8) >> 4)
    perp16 = 255 if component == 0 else min(255, (d16 * corr + component // 2) // component)
    projection = tables["projection_half"]
    top = 48 - projection[perp16]
    style = 4 if material == 3 else (2 + axis if material == 2 else axis)
    if axis == 0:
        plane, along = mx + (1 if sx < 0 else 0), my
    else:
        plane, along = my + (1 if sy < 0 else 0), mx
    face_key = (axis << 7) | ((material & 3) << 5) | (plane & 31)
    return ReferenceRayHit(
        ray_index=ray_index, angle_index=angle_index, dx=dx, dy=dy,
        map_x=mx, map_y=my, axis=axis, axis_distance_q8=distance,
        material=material, crossings=crossings, top=top, style=style,
        face_key=face_key, along=along & 0xFF,
    )


def reference_full_descriptor_view(player_x_q8: int, player_y_q8: int, player_angle: int,
                                   grid: bytes | None = None) -> tuple[list[int], list[int], list[int], list[int]]:
    """Host reference for all 80 exact DDA descriptors and wall-face keys."""
    hits = [reference_cast_hit(player_x_q8, player_y_q8, player_angle, i, grid) for i in range(RAYS)]
    return (
        [hit.top for hit in hits],
        [hit.style for hit in hits],
        [hit.face_key for hit in hits],
        [hit.along for hit in hits],
    )

def reference_adaptive_descriptor_view(player_x_q8: int, player_y_q8: int, player_angle: int) -> tuple[list[int], list[int], list[int], list[int], int]:
    """Apply the ROM's validated one-level affine span reconstruction."""
    full_tops, full_styles, full_keys, full_alongs = reference_full_descriptor_view(player_x_q8, player_y_q8, player_angle)
    tops = [0] * RAYS
    styles = [0] * RAYS
    keys = [0] * RAYS
    alongs = [0] * RAYS
    cast_count = 0
    for i in range(0, RAYS, 2):
        tops[i], styles[i], keys[i], alongs[i] = full_tops[i], full_styles[i], full_keys[i], full_alongs[i]
        cast_count += 1
    tops[79], styles[79], keys[79], alongs[79] = full_tops[79], full_styles[79], full_keys[79], full_alongs[79]
    cast_count += 1
    for i in range(1, 78, 2):
        same_face = (
            keys[i - 1] == keys[i + 1]
            and abs(alongs[i - 1] - alongs[i + 1]) <= 1
            and abs(tops[i - 1] - tops[i + 1]) <= 2
        )
        if same_face:
            tops[i] = (tops[i - 1] + tops[i + 1] + 1) // 2
            styles[i], keys[i], alongs[i] = styles[i - 1], keys[i - 1], alongs[i - 1]
        else:
            tops[i], styles[i], keys[i], alongs[i] = full_tops[i], full_styles[i], full_keys[i], full_alongs[i]
            cast_count += 1
    return tops, styles, keys, alongs, cast_count


def reference_descriptor_view(player_x_q8: int, player_y_q8: int, player_angle: int) -> tuple[list[int], list[int]]:
    tops, styles, _, _, _ = reference_adaptive_descriptor_view(player_x_q8, player_y_q8, player_angle)
    return tops, styles


def reference_strip_state(top: int, tile_y0: int) -> int:
    """Host equivalent of ``compute_strip_state`` in the ROM."""
    if tile_y0 + 7 < top:
        return 0
    bottom = 96 - top
    if tile_y0 >= bottom:
        return 1
    if tile_y0 < top:
        return 3 + (top - tile_y0)
    if tile_y0 + 7 < bottom:
        return 2
    return 10 + (bottom - tile_y0)


def reference_compose_view(tops: list[int], styles: list[int]) -> tuple[bytes, bytes, int, bool]:
    """Byte-exact host model of the edge-microstrip tile compositor.

    The ROM walks viewport columns first so dynamic-tile allocation order is
    column-major even though the 32-byte BG map itself is row-major.  Every
    padding cell is initialized to the ceiling tile so the complete 384-byte
    DMA payload is deterministic on hardware whose WRAM power-on contents are
    not an engine contract.
    """
    if len(tops) != RAYS or len(styles) != RAYS:
        raise ValueError(f"expected {RAYS} ray descriptors")

    dynamic = bytearray()
    view_map = bytearray([CEILING_TILE] * (12 * 32))
    overflow = False

    for tile_col in range(20):
        first = tile_col * 4
        col_tops = tops[first:first + 4]
        col_styles = styles[first:first + 4]
        min_top = min(col_tops)
        max_top = max(col_tops)
        one_style = len(set(col_styles)) == 1

        for tile_row in range(12):
            y0 = tile_row * 8
            if y0 + 7 < min_top:
                tile_id = CEILING_TILE
            elif y0 >= 96 - min_top:
                tile_id = FLOOR_TILE
            elif y0 >= max_top and y0 + 7 < 96 - max_top and one_style:
                tile_id = WALL_TILE_BASE + col_styles[0]
            else:
                tile_id = len(dynamic) // 16
                if tile_id >= DYNAMIC_TILE_CAPACITY:
                    overflow = True
                    tile_id = WALL_TILE_BASE
                else:
                    tile = bytearray(16)
                    for pair, (top, style) in enumerate(zip(col_tops, col_styles)):
                        state = reference_strip_state(top, y0)
                        mask = 0x03 << (6 - pair * 2)
                        for row in range(8):
                            region = microstrip_region(state, row)
                            color = 0 if region == "ceiling" else 1 if region == "floor" else wall_color(style, pair, row)
                            if color & 1:
                                tile[row * 2] |= mask
                            if color & 2:
                                tile[row * 2 + 1] |= mask
                    dynamic.extend(tile)
            view_map[tile_row * 32 + tile_col] = tile_id

    return bytes(dynamic), bytes(view_map), len(dynamic) // 16, overflow

def emit_mul_u8(a: Assembler) -> None:
    """B*C -> HL, unsigned; clobbers B,C,D,E."""
    a.label("mul_u8")
    a.ld_r_n("d", 0); a.ld_r_r("e", "b")
    a.ld_rr_nn("hl", 0); a.ld_r_n("b", 8)
    a.label("mul_u8_loop")
    a.cb("bit", "c", 0); a.jr("mul_u8_skip", "z")
    a.add_hl_rr("de")
    a.label("mul_u8_skip")
    a.cb("sla", "e"); a.cb("rl", "d"); a.cb("srl", "c")
    a.dec_r("b"); a.jr("mul_u8_loop", "nz")
    a.ret()


def emit_div_u16_u8_sat(a: Assembler) -> None:
    """HL/B -> A, saturated to 255. B must be nonzero for normal division."""
    a.label("div_u16_u8_sat")
    a.ld_r_r("a", "b"); a.or_r("a"); a.jr("div_sat", "z")
    a.ld_r_r("a", "h"); a.cp_r("b"); a.jr("div_sat", "nc")
    a.ld_r_r("a", "h"); a.ld_r_r("c", "l")
    a.ld_r_n("d", 0); a.ld_r_n("e", 8)
    a.label("div_loop")
    a.cb("sla", "c"); a.rla(); a.cb("sla", "d")
    a.cp_r("b"); a.jr("div_no_sub", "c")
    a.sub_r("b"); a.inc_r("d")
    a.label("div_no_sub")
    a.dec_r("e"); a.jr("div_loop", "nz")
    a.ld_r_r("a", "d"); a.ret()
    a.label("div_sat")
    a.ld_r_n("a", 0xFF); a.ret()


def emit_vram_init(a: Assembler) -> None:
    a.label("init_vram")
    # The map upload covers all 32 bytes of each of the twelve viewport rows.
    # Initialize the hidden padding once instead of relying on WRAM power-on
    # contents that happen to be zero in the project harness.
    a.ld_rr_nn("hl", VIEW_MAP); a.ld_rr_nn("bc", 12 * 32); a.ld_r_n("d", CEILING_TILE)
    a.label("init_view_map_loop")
    a.ld_r_r("a", "d"); a.ldi_hl_a(); a.dec_rr("bc")
    a.ld_r_r("a", "b"); a.or_r("c"); a.jr("init_view_map_loop", "nz")
    # Bank 0: shared static viewport tiles, UI tiles and tile maps.
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_rr_label("hl", "static_view_tiles"); a.ld_rr_nn("de", 0x8600); a.ld_rr_nn("bc", STATIC_VIEW_TILES * 16); a.call("copy_bc")
    a.ld_rr_label("hl", "ui_tiles"); a.ld_rr_nn("de", 0x8F00); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9800); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9C00); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    # Bank 1 mirrors viewport tiles and holds weapon OBJ tiles plus attributes.
    a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.ld_rr_label("hl", "static_view_tiles"); a.ld_rr_nn("de", 0x8600); a.ld_rr_nn("bc", STATIC_VIEW_TILES * 16); a.call("copy_bc")
    a.ld_rr_label("hl", "weapon_tiles"); a.ld_rr_nn("de", 0x8F00); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_rr_label("hl", "attrmap_page0"); a.ld_rr_nn("de", 0x9800); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.ld_rr_label("hl", "attrmap_page1"); a.ld_rr_nn("de", 0x9C00); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.xor_r("a"); a.ldh_n_a(VBK); a.ret()


def emit_dma(a: Assembler) -> None:
    a.label("upload_dynamic_tiles")
    a.ld_a_abs(DYN_COUNT); a.or_r("a"); a.ret("z")
    a.ld_r_r("b", "a")
    a.ld_r_n("a", 0xC0); a.ldh_n_a(HDMA1)
    a.xor_r("a"); a.ldh_n_a(HDMA2); a.ldh_n_a(HDMA3); a.ldh_n_a(HDMA4)
    a.ld_r_r("a", "b"); a.dec_r("a"); a.ldh_n_a(HDMA5)
    a.ret()

    a.label("upload_view_map")
    # Tile IDs always live in VRAM bank 0; bank 1 holds CGB attributes.
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_r_n("a", 0xC6); a.ldh_n_a(HDMA1)
    a.xor_r("a"); a.ldh_n_a(HDMA2)
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.or_r("a"); a.jr("upload_map_9800", "z")
    a.ld_r_n("a", 0x1C); a.jr("upload_map_dest_ready")
    a.label("upload_map_9800")
    a.ld_r_n("a", 0x18)
    a.label("upload_map_dest_ready")
    a.ldh_n_a(HDMA3); a.xor_r("a"); a.ldh_n_a(HDMA4)
    a.ld_r_n("a", 0x17); a.ldh_n_a(HDMA5)  # 24 blocks = 384 bytes
    a.ret()

    a.label("upload_initial_both_pages")
    # Dynamic tile pixels live in the VRAM bank selected by each page's
    # preloaded attribute map. Tile-number maps themselves always live in
    # VRAM bank 0; writing them with VBK=1 would corrupt CGB attributes.
    a.xor_r("a"); a.ldh_n_a(VBK); a.call("upload_dynamic_tiles")
    a.ld_r_n("a", 1); a.ld_abs_a(CURRENT_PAGE)  # hidden page = 0 -> 9800
    a.xor_r("a"); a.ldh_n_a(VBK); a.call("upload_view_map")
    a.ld_r_n("a", 1); a.ldh_n_a(VBK); a.call("upload_dynamic_tiles")
    a.xor_r("a"); a.ld_abs_a(CURRENT_PAGE)     # hidden page = 1 -> 9C00
    a.ldh_n_a(VBK); a.call("upload_view_map")
    a.xor_r("a"); a.ld_abs_a(CURRENT_PAGE); a.ldh_n_a(VBK); a.ret()

    a.label("upload_hidden_page")
    a.call("wait_vblank")
    # Upload dynamic pixels to the hidden page's selected tile-data bank.
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.ldh_n_a(VBK)
    a.call("upload_dynamic_tiles")
    # Upload tile numbers to the hidden BG map in VRAM bank 0, preserving
    # the static attribute maps in VRAM bank 1.
    a.xor_r("a"); a.ldh_n_a(VBK); a.call("upload_view_map")
    a.call("update_muzzle_oam")
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.ld_abs_a(CURRENT_PAGE)
    a.or_r("a"); a.jr("display_page_zero", "z")
    a.ld_r_n("a", 0x9B); a.ldh_n_a(LCDC); a.jr("display_page_done")
    a.label("display_page_zero")
    a.ld_r_n("a", 0x93); a.ldh_n_a(LCDC)
    a.label("display_page_done")
    a.xor_r("a"); a.ldh_n_a(VBK); a.ret()


def emit_dda(a: Assembler) -> None:
    a.label("dda_setup")
    # Map coordinates.
    a.ld_a_abs(PLAYER_XH); a.ld_abs_a(DDA_MAP_X)
    a.ld_a_abs(PLAYER_YH); a.ld_abs_a(DDA_MAP_Y)

    # Lookup 1024-direction dx.
    load_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_rr_label("de", "ray_dx_1024"); a.add_hl_rr("de")
    a.ld_a_hl(); a.ld_r_r("b", "a")
    a.cb("bit", "b", 7); a.jr("dda_dx_nonnegative", "z")
    a.ld_r_r("a", "b"); a.cpl(); a.inc_r("a"); a.ld_abs_a(DDA_ABS_X)
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_STEP_X); a.jr("dda_dx_done")
    a.label("dda_dx_nonnegative")
    a.ld_r_r("a", "b"); a.ld_abs_a(DDA_ABS_X); a.or_r("a"); a.jr("dda_dx_zero", "z")
    a.ld_r_n("a", 1); a.ld_abs_a(DDA_STEP_X); a.jr("dda_dx_done")
    a.label("dda_dx_zero")
    a.xor_r("a"); a.ld_abs_a(DDA_STEP_X)
    a.label("dda_dx_done")

    # Lookup 1024-direction dy.
    load_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_rr_label("de", "ray_dy_1024"); a.add_hl_rr("de")
    a.ld_a_hl(); a.ld_r_r("b", "a")
    a.cb("bit", "b", 7); a.jr("dda_dy_nonnegative", "z")
    a.ld_r_r("a", "b"); a.cpl(); a.inc_r("a"); a.ld_abs_a(DDA_ABS_Y)
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_STEP_Y); a.jr("dda_dy_done")
    a.label("dda_dy_nonnegative")
    a.ld_r_r("a", "b"); a.ld_abs_a(DDA_ABS_Y); a.or_r("a"); a.jr("dda_dy_zero", "z")
    a.ld_r_n("a", 1); a.ld_abs_a(DDA_STEP_Y); a.jr("dda_dy_done")
    a.label("dda_dy_zero")
    a.xor_r("a"); a.ld_abs_a(DDA_STEP_Y)
    a.label("dda_dy_done")

    # Initial distance to next X boundary in Q8.8.
    a.ld_a_abs(DDA_STEP_X); a.cp_n(1); a.jr("dda_next_x_positive", "z")
    a.cp_n(0xFF); a.jr("dda_next_x_negative", "z")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_NEXT_X_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_NEXT_X_H); a.jr("dda_next_x_done")
    a.label("dda_next_x_positive")
    a.ld_a_abs(PLAYER_XL); a.cpl(); a.inc_r("a"); a.ld_abs_a(DDA_NEXT_X_L)
    a.jr("dda_next_x_positive_nonzero", "nz")
    a.ld_r_n("a", 1); a.ld_abs_a(DDA_NEXT_X_H); a.jr("dda_next_x_done")
    a.label("dda_next_x_positive_nonzero")
    a.xor_r("a"); a.ld_abs_a(DDA_NEXT_X_H); a.jr("dda_next_x_done")
    a.label("dda_next_x_negative")
    a.ld_a_abs(PLAYER_XL); a.ld_abs_a(DDA_NEXT_X_L); a.xor_r("a"); a.ld_abs_a(DDA_NEXT_X_H)
    a.label("dda_next_x_done")

    # Initial distance to next Y boundary.
    a.ld_a_abs(DDA_STEP_Y); a.cp_n(1); a.jr("dda_next_y_positive", "z")
    a.cp_n(0xFF); a.jr("dda_next_y_negative", "z")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_NEXT_Y_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_NEXT_Y_H); a.jr("dda_next_y_done")
    a.label("dda_next_y_positive")
    a.ld_a_abs(PLAYER_YL); a.cpl(); a.inc_r("a"); a.ld_abs_a(DDA_NEXT_Y_L)
    a.jr("dda_next_y_positive_nonzero", "nz")
    a.ld_r_n("a", 1); a.ld_abs_a(DDA_NEXT_Y_H); a.jr("dda_next_y_done")
    a.label("dda_next_y_positive_nonzero")
    a.xor_r("a"); a.ld_abs_a(DDA_NEXT_Y_H); a.jr("dda_next_y_done")
    a.label("dda_next_y_negative")
    a.ld_a_abs(PLAYER_YL); a.ld_abs_a(DDA_NEXT_Y_L); a.xor_r("a"); a.ld_abs_a(DDA_NEXT_Y_H)
    a.label("dda_next_y_done")

    # Special axial rays avoid product overflow/sentinel arithmetic.
    a.ld_a_abs(DDA_ABS_X); a.or_r("a"); a.jr("dda_error_x_nonzero", "nz")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_ERR_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_ERR_H); a.jr("dda_error_done")
    a.label("dda_error_x_nonzero")
    a.ld_a_abs(DDA_ABS_Y); a.or_r("a"); a.jr("dda_error_general", "nz")
    a.xor_r("a"); a.ld_abs_a(DDA_ERR_L); a.ld_r_n("a", 0x80); a.ld_abs_a(DDA_ERR_H); a.jr("dda_error_done")

    a.label("dda_error_general")
    # X product = nextX * absY.
    a.ld_a_abs(DDA_NEXT_X_L); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_ABS_Y); a.ld_r_r("c", "a"); a.call("mul_u8")
    a.ld_a_abs(DDA_NEXT_X_H); a.or_r("a"); a.jr("dda_xprod_no_high", "z")
    a.ld_a_abs(DDA_ABS_Y); a.add_a_r("h"); a.ld_r_r("h", "a")
    a.label("dda_xprod_no_high")
    a.ld_r_r("a", "l"); a.ld_abs_a(DDA_ERR_L); a.ld_r_r("a", "h"); a.ld_abs_a(DDA_ERR_H)
    # Y product, then error = X - Y.
    a.ld_a_abs(DDA_NEXT_Y_L); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_ABS_X); a.ld_r_r("c", "a"); a.call("mul_u8")
    a.ld_a_abs(DDA_NEXT_Y_H); a.or_r("a"); a.jr("dda_yprod_no_high", "z")
    a.ld_a_abs(DDA_ABS_X); a.add_a_r("h"); a.ld_r_r("h", "a")
    a.label("dda_yprod_no_high")
    a.ld_a_abs(DDA_ERR_L); a.sub_r("l"); a.ld_abs_a(DDA_ERR_L)
    a.ld_a_abs(DDA_ERR_H); a.sbc_a_r("h"); a.ld_abs_a(DDA_ERR_H)
    a.label("dda_error_done")
    a.xor_r("a"); a.ld_abs_a(DDA_CROSSINGS); a.ret()

    a.label("dda_read_cell")
    a.ld_a_abs(DDA_MAP_Y); a.cb("swap", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_MAP_X); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0xD0)
    a.ld_a_hl(); a.ret()

    a.label("dda_cast")
    a.call("dda_setup")
    a.label("dda_loop")
    # Choose X on negative or zero signed error; Y on positive error.
    a.ld_a_abs(DDA_ABS_X); a.or_r("a"); a.jp("dda_step_y", "z")
    a.ld_a_abs(DDA_ABS_Y); a.or_r("a"); a.jp("dda_step_x", "z")
    a.ld_a_abs(DDA_ERR_H); a.cb("bit", "a", 7); a.jp("dda_step_x", "nz")
    a.or_r("a"); a.jp("dda_step_y", "nz")
    a.ld_a_abs(DDA_ERR_L); a.or_r("a"); a.jp("dda_step_y", "nz")

    a.label("dda_step_x")
    a.ld_a_abs(DDA_STEP_X); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_MAP_X); a.add_a_r("b"); a.ld_abs_a(DDA_MAP_X)
    a.xor_r("a"); a.ld_abs_a(DDA_AXIS)
    a.ld_a_abs(DDA_NEXT_X_L); a.ld_abs_a(DDA_DIST_L); a.ld_a_abs(DDA_NEXT_X_H); a.ld_abs_a(DDA_DIST_H)
    a.call("dda_post_step"); a.ret("nz")
    a.ld_a_abs(DDA_NEXT_X_H); a.inc_r("a"); a.ld_abs_a(DDA_NEXT_X_H)
    a.ld_a_abs(DDA_ABS_Y); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_ERR_H); a.add_a_r("b"); a.ld_abs_a(DDA_ERR_H)
    a.jp("dda_loop")

    a.label("dda_step_y")
    a.ld_a_abs(DDA_STEP_Y); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_MAP_Y); a.add_a_r("b"); a.ld_abs_a(DDA_MAP_Y)
    a.ld_r_n("a", 1); a.ld_abs_a(DDA_AXIS)
    a.ld_a_abs(DDA_NEXT_Y_L); a.ld_abs_a(DDA_DIST_L); a.ld_a_abs(DDA_NEXT_Y_H); a.ld_abs_a(DDA_DIST_H)
    a.call("dda_post_step"); a.ret("nz")
    a.ld_a_abs(DDA_NEXT_Y_H); a.inc_r("a"); a.ld_abs_a(DDA_NEXT_Y_H)
    a.ld_a_abs(DDA_ABS_X); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_ERR_H); a.sub_r("b"); a.ld_abs_a(DDA_ERR_H)
    a.jp("dda_loop")

    a.label("dda_post_step")
    a.ld_a_abs(DDA_CROSSINGS); a.inc_r("a"); a.ld_abs_a(DDA_CROSSINGS); a.cp_n(32); a.jr("dda_force_hit", "nc")
    a.call("dda_read_cell"); a.or_r("a"); a.jr("dda_hit", "nz")
    a.xor_r("a"); a.ret()
    a.label("dda_force_hit")
    a.ld_r_n("a", 1)
    a.label("dda_hit")
    a.ld_abs_a(DDA_MATERIAL); a.or_r("a"); a.ret()


def emit_projection_and_casting(a: Assembler) -> None:
    a.label("project_hit")
    # D16 = round(axis distance / 16), saturated to 255.
    a.ld_a_abs(DDA_DIST_L); a.add_a_n(8); a.ld_r_r("l", "a")
    a.ld_a_abs(DDA_DIST_H); a.adc_a_n(0); a.ld_r_r("h", "a")
    a.cp_n(0x10); a.jr("project_d16_sat", "nc")
    a.cb("swap", "a"); a.and_n(0xF0); a.ld_r_r("b", "a")
    a.ld_r_r("a", "l"); a.cb("swap", "a"); a.and_n(0x0F); a.or_r("b"); a.jr("project_d16_ready")
    a.label("project_d16_sat"); a.ld_r_n("a", 0xFF)
    a.label("project_d16_ready")
    a.ld_r_r("b", "a"); a.ld_a_abs(DDA_CORRECTION); a.ld_r_r("c", "a"); a.call("mul_u8")
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.jr("project_component_y", "nz")
    a.ld_a_abs(DDA_ABS_X); a.jr("project_component_ready")
    a.label("project_component_y"); a.ld_a_abs(DDA_ABS_Y)
    a.label("project_component_ready")
    # Rounded unsigned division: (HL + component/2) / component.  This
    # removes a systematic near-wall height bias at a small fixed cost.
    a.ld_r_r("b", "a"); a.ld_r_r("c", "a"); a.cb("srl", "c")
    a.ld_r_n("d", 0); a.ld_r_r("e", "c"); a.add_hl_rr("de"); a.call("div_u16_u8_sat")
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "projection_half"); a.add_hl_rr("de")
    a.ld_a_hl(); a.ld_r_r("b", "a"); a.ld_r_n("a", 48); a.sub_r("b"); a.ld_abs_a(TOP_RESULT)

    # Exact wall-side style.
    a.ld_a_abs(DDA_MATERIAL); a.cp_n(3); a.jr("style_door", "z"); a.cp_n(2); a.jr("style_tech", "z")
    a.ld_a_abs(DDA_AXIS); a.jr("style_store")
    a.label("style_tech"); a.ld_a_abs(DDA_AXIS); a.add_a_n(2); a.jr("style_store")
    a.label("style_door"); a.ld_r_n("a", 4)
    a.label("style_store"); a.ld_abs_a(STYLE_RESULT)

    # Compact face identity: axis | material | wall-plane coordinate.
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.jr("face_axis_y", "nz")
    a.ld_a_abs(DDA_MAP_X); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_STEP_X); a.cp_n(0xFF); a.jr("face_x_plane_ready", "nz"); a.inc_r("b")
    a.label("face_x_plane_ready"); a.ld_a_abs(DDA_MAP_Y); a.ld_abs_a(ALONG_RESULT); a.xor_r("a"); a.ld_r_r("d", "a"); a.jr("face_pack")
    a.label("face_axis_y")
    a.ld_a_abs(DDA_MAP_Y); a.ld_r_r("b", "a"); a.ld_a_abs(DDA_STEP_Y); a.cp_n(0xFF); a.jr("face_y_plane_ready", "nz"); a.inc_r("b")
    a.label("face_y_plane_ready"); a.ld_a_abs(DDA_MAP_X); a.ld_abs_a(ALONG_RESULT); a.ld_r_n("d", 0x80)
    a.label("face_pack")
    a.ld_a_abs(DDA_MATERIAL); a.and_n(3)
    for _ in range(5): a.add_a_r("a")
    a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.and_n(0x1F); a.or_r("c"); a.or_r("d"); a.ld_abs_a(FACE_RESULT); a.ret()

    a.label("cast_one_v2"); a.call("dda_cast"); a.call("project_hit"); a.ret()

    a.label("cast_indexed")  # CAST_INDEX selects the ray
    a.ld_a_abs(CAST_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "ray_offsets_q10"); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(ANGLE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.add_hl_rr("hl"); a.add_hl_rr("hl"); a.add_hl_rr("de")
    a.ld_r_r("a", "h"); a.and_n(0x03); a.ld_r_r("h", "a"); store_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_a_abs(CAST_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "ray_corrections"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(DDA_CORRECTION)
    a.call("cast_one_v2"); a.ret()

    a.label("cast_and_store")  # input A ray index
    a.ld_abs_a(CAST_INDEX)
    a.ld_a_abs(ADAPTIVE_CASTS); a.inc_r("a"); a.ld_abs_a(ADAPTIVE_CASTS)
    a.call("cast_indexed")
    a.ld_a_abs(CAST_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_abs(TOP_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_STYLES); a.add_hl_rr("de"); a.ld_a_abs(STYLE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_abs(FACE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_abs(ALONG_RESULT); a.ld_hl_a(); a.ret()

    a.label("cast_all")
    a.xor_r("a"); a.ld_abs_a(ADAPTIVE_CASTS); a.call("cast_and_store")
    a.ld_r_n("a", 2); a.ld_abs_a(ADAPTIVE_INDEX)
    a.label("cast_anchor_loop")
    a.ld_a_abs(ADAPTIVE_INDEX); a.call("cast_and_store")
    a.ld_a_abs(ADAPTIVE_INDEX); a.add_a_n(2); a.ld_abs_a(ADAPTIVE_INDEX); a.cp_n(80); a.jr("cast_anchor_loop", "c")
    a.ld_r_n("a", 79); a.call("cast_and_store")
    a.ld_r_n("a", 1); a.ld_abs_a(ADAPTIVE_INDEX)
    a.label("adaptive_fill_loop")
    # Compare left/right face keys.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jp("adaptive_cast_mid", "nz")
    # Same plane/material: require identical or adjacent along-plane cells.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.sub_r("b"); a.jr("adaptive_along_positive", "nc"); a.cpl(); a.inc_r("a")
    a.label("adaptive_along_positive"); a.cp_n(2); a.jp("adaptive_cast_mid", "nc")
    # Quantized projection is only approximately affine.  Require the two
    # anchors to differ by no more than two top-edge pixels; this preserves
    # the inexpensive midpoint path while eliminating large near-wall errors.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.sub_r("b"); a.jr("adaptive_top_positive", "nc"); a.cpl(); a.inc_r("a")
    a.label("adaptive_top_positive"); a.cp_n(3); a.jp("adaptive_cast_mid", "nc")
    # Affine midpoint of the two integer top edges.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(ADAPTIVE_INDEX); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.add_a_r("b"); a.inc_r("a"); a.cb("srl", "a"); a.ld_abs_a(TOP_RESULT)
    # Copy left style/key/along to midpoint.
    a.ld_a_abs(ADAPTIVE_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_STYLES); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(STYLE_RESULT)
    a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(FACE_RESULT)
    a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ALONG_RESULT)
    # Store the interpolated descriptor without incrementing cast count.
    a.ld_a_abs(ADAPTIVE_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_abs(TOP_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_STYLES); a.add_hl_rr("de"); a.ld_a_abs(STYLE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_abs(FACE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_abs(ALONG_RESULT); a.ld_hl_a(); a.jr("adaptive_fill_done")
    a.label("adaptive_cast_mid"); a.ld_a_abs(ADAPTIVE_INDEX); a.call("cast_and_store")
    a.label("adaptive_fill_done")
    a.ld_a_abs(ADAPTIVE_INDEX); a.add_a_n(2); a.ld_abs_a(ADAPTIVE_INDEX); a.cp_n(79); a.jp("adaptive_fill_loop", "c"); a.ret()

def emit_renderer(a: Assembler) -> None:
    # These two fixed-size kernels sit in the hottest compositor path.  The
    # looped versions spent roughly one quarter of their time decrementing a
    # counter and branching.  Unrolling costs well under 200 ROM bytes and
    # removes about one thousand cycles from every generated boundary tile.
    a.label("copy_16")  # HL source, DE destination
    for _ in range(16):
        a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()

    a.label("or_16")  # HL source, DE destination
    for _ in range(16):
        a.ldi_a_hl(); a.ld_r_r("c", "a"); a.ld_a_mem_rr("de")
        a.or_r("c"); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()

    a.label("compute_strip_state")  # input A top, output A state
    a.ld_r_r("b", "a")
    a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.cp_r("b"); a.jr("strip_ceiling", "c")
    a.ld_r_n("a", 96); a.sub_r("b"); a.ld_r_r("c", "a")  # C = bottom
    a.ld_a_abs(TILE_Y0); a.cp_r("c"); a.jr("strip_floor", "nc")
    a.cp_r("b"); a.jr("strip_top_edge", "c")
    a.add_a_n(7); a.cp_r("c"); a.jr("strip_wall", "c")
    # Bottom edge: state = 10 + (bottom - y0), range 11..17.
    a.ld_r_r("a", "c"); a.ld_r_r("d", "a"); a.ld_a_abs(TILE_Y0); a.ld_r_r("e", "a"); a.ld_r_r("a", "d"); a.sub_r("e"); a.add_a_n(10); a.ret()
    a.label("strip_top_edge")
    a.ld_r_r("a", "b"); a.ld_r_r("d", "a"); a.ld_a_abs(TILE_Y0); a.ld_r_r("e", "a"); a.ld_r_r("a", "d"); a.sub_r("e"); a.add_a_n(3); a.ret()
    a.label("strip_ceiling"); a.xor_r("a"); a.ret()
    a.label("strip_floor"); a.ld_r_n("a", 1); a.ret()
    a.label("strip_wall"); a.ld_r_n("a", 2); a.ret()

    a.label("get_microstrip_ptr")
    # Base pointer for the style.
    a.ld_a_abs(STRIP_STYLE); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "microstrip_style_bases"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    # state * 64 + pair * 16
    a.ld_a_abs(STRIP_STATE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(6): a.add_hl_rr("hl")
    a.ld_a_abs(STRIP_PAIR); a.cb("swap", "a"); a.and_n(0xF0); a.ld_r_r("c", "a"); a.ld_r_n("b", 0); a.add_hl_rr("bc")
    a.add_hl_rr("de"); a.ret()

    a.label("compose_dynamic_tile")
    load_hl_abs(a, DYN_PTR_L, DYN_PTR_H); store_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H)
    a.xor_r("a"); a.ld_abs_a(STRIP_PAIR)
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.push("hl")
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl")
    a.label("compose_pair_loop")
    a.ldi_a_hl(); a.ld_abs_a(TEMP_TOP)
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.ld_abs_a(STRIP_STYLE)
    a.push("hl"); a.push("de")
    a.ld_a_abs(TEMP_TOP); a.call("compute_strip_state"); a.ld_abs_a(STRIP_STATE); a.call("get_microstrip_ptr")
    a.ld_a_abs(STRIP_PAIR); a.or_r("a"); a.jr("compose_or_strip", "nz")
    # HL already points at the first microstrip. Preserve it while loading
    # the dynamic-tile destination; get_microstrip_ptr clobbers DE.
    a.push("hl"); load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl")
    a.call("copy_16")
    a.ld_r_r("a", "e"); a.ld_abs_a(DYN_PTR_L); a.ld_r_r("a", "d"); a.ld_abs_a(DYN_PTR_H); a.jr("compose_strip_done")
    a.label("compose_or_strip")
    a.push("hl"); load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.call("or_16")
    a.label("compose_strip_done")
    a.pop("de"); a.pop("hl")
    a.ld_a_abs(STRIP_PAIR); a.inc_r("a"); a.ld_abs_a(STRIP_PAIR); a.cp_n(4); a.jr("compose_pair_loop", "nz"); a.ret()

    a.label("scan_column")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(MIN_TOP); a.xor_r("a"); a.ld_abs_a(MAX_TOP); a.ld_abs_a(STYLE_DIFF)
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.push("hl")
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl")
    a.ld_a_mem_rr("de"); a.ld_abs_a(FIRST_STYLE); a.ld_r_n("a", 4); a.ld_abs_a(CLASSIFY_COUNT)
    a.label("scan_column_loop")
    a.ldi_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(MIN_TOP); a.cp_r("b"); a.jr("scan_min_keep", "c"); a.jr("scan_min_keep", "z"); a.ld_r_r("a", "b"); a.ld_abs_a(MIN_TOP)
    a.label("scan_min_keep")
    a.ld_a_abs(MAX_TOP); a.cp_r("b"); a.jr("scan_max_keep", "nc"); a.ld_r_r("a", "b"); a.ld_abs_a(MAX_TOP)
    a.label("scan_max_keep")
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.ld_r_r("b", "a"); a.ld_a_abs(FIRST_STYLE); a.cp_r("b"); a.jr("scan_style_same", "z")
    a.ld_r_n("a", 1); a.ld_abs_a(STYLE_DIFF)
    a.label("scan_style_same")
    a.ld_a_abs(CLASSIFY_COUNT); a.dec_r("a"); a.ld_abs_a(CLASSIFY_COUNT); a.jr("scan_column_loop", "nz"); a.ret()

    a.label("classify_row")
    a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.ld_r_r("b", "a")
    a.ld_a_abs(MIN_TOP); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.cp_r("c"); a.jr("row_ceiling", "c")
    a.ld_r_n("a", 96); a.sub_r("c"); a.ld_r_r("b", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("b"); a.jr("row_floor", "nc")
    a.ld_a_abs(MAX_TOP); a.ld_r_r("c", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("c"); a.jr("row_dynamic", "c")
    a.ld_r_n("a", 96); a.sub_r("c"); a.ld_r_r("c", "a"); a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.cp_r("c"); a.jr("row_dynamic", "nc")
    a.ld_a_abs(STYLE_DIFF); a.or_r("a"); a.jr("row_dynamic", "nz")
    a.ld_a_abs(FIRST_STYLE); a.add_a_n(WALL_TILE_BASE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_ceiling"); a.ld_r_n("a", CEILING_TILE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_floor"); a.ld_r_n("a", FLOOR_TILE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_dynamic"); a.ld_r_n("a", 1); a.ld_abs_a(DYNAMIC_FLAG); a.ret()

    a.label("render_view")
    a.xor_r("a"); a.ld_abs_a(DYN_COUNT); a.ld_abs_a(DYN_OVERFLOW)
    a.ld_rr_nn("hl", DYNAMIC_TILES); store_hl_abs(a, DYN_PTR_L, DYN_PTR_H)
    a.ld_rr_nn("hl", VIEW_MAP); store_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H)
    a.ld_rr_nn("hl", RAY_TOPS); store_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H)
    a.ld_rr_nn("hl", RAY_STYLES); store_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H)
    a.ld_r_n("a", 20); a.ld_abs_a(COLUMN_COUNT)
    a.label("render_column_loop")
    a.call("scan_column")
    a.xor_r("a"); a.ld_abs_a(TILE_ROW); a.ld_abs_a(TILE_Y0)
    load_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H); store_hl_abs(a, MAP_PTR_L, MAP_PTR_H)
    a.ld_r_n("a", 12); a.ld_abs_a(ROW_RENDER_COUNT)
    a.label("render_row_loop")
    a.call("classify_row")
    a.ld_a_abs(DYNAMIC_FLAG); a.or_r("a"); a.jr("render_static_tile", "z")
    a.ld_a_abs(DYN_COUNT); a.cp_n(DYNAMIC_TILE_CAPACITY); a.jr("render_dynamic_overflow", "nc")
    a.ld_abs_a(TILE_ID_RESULT); a.call("compose_dynamic_tile")
    a.ld_a_abs(DYN_COUNT); a.inc_r("a"); a.ld_abs_a(DYN_COUNT)
    a.ld_r_r("b", "a"); a.ld_a_abs(DYN_HIGH_WATER); a.cp_r("b"); a.jr("render_dynamic_high_keep", "nc"); a.ld_r_r("a", "b"); a.ld_abs_a(DYN_HIGH_WATER)
    a.label("render_dynamic_high_keep"); a.jr("render_write_tile")
    a.label("render_dynamic_overflow")
    a.ld_r_n("a", 1); a.ld_abs_a(DYN_OVERFLOW); a.ld_r_n("a", WALL_TILE_BASE); a.ld_abs_a(TILE_ID_RESULT); a.jr("render_write_tile")
    a.label("render_static_tile")
    a.label("render_write_tile")
    load_hl_abs(a, MAP_PTR_L, MAP_PTR_H); a.ld_a_abs(TILE_ID_RESULT); a.ld_hl_a(); a.ld_rr_nn("de", 32); a.add_hl_rr("de"); store_hl_abs(a, MAP_PTR_L, MAP_PTR_H)
    a.ld_a_abs(TILE_ROW); a.inc_r("a"); a.ld_abs_a(TILE_ROW)
    a.ld_a_abs(TILE_Y0); a.add_a_n(8); a.ld_abs_a(TILE_Y0)
    a.ld_a_abs(ROW_RENDER_COUNT); a.dec_r("a"); a.ld_abs_a(ROW_RENDER_COUNT); a.jp("render_row_loop", "nz")
    # Advance four descriptors and one BG-map column.
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.ld_rr_nn("de", 4); a.add_hl_rr("de"); store_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H)
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_rr_nn("de", 4); a.add_hl_rr("de"); store_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H)
    load_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H); a.inc_rr("hl"); store_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H)
    a.ld_a_abs(COLUMN_COUNT); a.dec_r("a"); a.ld_abs_a(COLUMN_COUNT); a.jp("render_column_loop", "nz"); a.ret()

def build_engine() -> tuple[bytes, Assembler, dict[str, object]]:
    tables = make_tables()
    a = Assembler(origin=0x0150)
    a.label("start")
    a.di(); a.ld_rr_nn("sp", 0xDFFF); a.ld_r_n("a", 1); a.ldh_n_a(SVBK)
    a.xor_r("a"); a.ld_abs_a(0xFFFF); a.ld_abs_a(0xFF0F)
    a.ld_r_n("a", 1); a.ldh_n_a(KEY1); a.stop()
    a.label("startup_wait_vblank")
    a.ldh_a_n(LY); a.cp_n(144); a.jr("startup_wait_vblank", "c")
    a.xor_r("a"); a.ldh_n_a(LCDC); a.ldh_n_a(SCX); a.ldh_n_a(SCY)
    a.ld_rr_label("hl", "map_data"); a.ld_rr_nn("de", MAP); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_r_n("a", 0x80); a.ld_abs_a(PLAYER_XL); a.ld_abs_a(PLAYER_YL)
    a.ld_r_n("a", 1); a.ld_abs_a(PLAYER_XH); a.ld_abs_a(PLAYER_YH)
    a.xor_r("a"); a.ld_abs_a(ANGLE); a.ld_abs_a(BUTTONS); a.ld_abs_a(PREV_BUTTONS); a.ld_abs_a(FLASH); a.ld_abs_a(CURRENT_PAGE); a.ld_abs_a(DYN_HIGH_WATER)
    a.call("init_palettes"); a.call("init_vram"); a.call("init_oam"); a.call("init_audio")
    a.call("cast_all"); a.call("render_view"); a.call("upload_initial_both_pages")
    a.ld_r_n("a", 0x93); a.ldh_n_a(LCDC)
    a.label("main_loop")
    a.call("read_joypad"); a.call("update_input"); a.call("cast_all"); a.call("render_view"); a.call("upload_hidden_page"); a.jp("main_loop")

    # Runtime routines.
    v1.emit_copy_routine(a); v1.emit_wait_vblank(a); v1.emit_palette_init(a)
    emit_vram_init(a); v1.emit_oam_init(a); v1.emit_audio(a); emit_dma(a); v1.emit_joypad(a)
    # Legacy quarter-step helpers are retained only for the two-step door interaction.
    v1.emit_ray_helpers(a)
    emit_mul_u8(a); emit_div_u16_u8_sat(a); emit_dda(a); emit_projection_and_casting(a); emit_renderer(a)
    v1.emit_movement(a); v1.emit_input_update(a)

    # Data section.
    a.align(16, text="data alignment")
    a.label("map_data"); a.bytes(make_map(), "16x16 world map")
    a.label("ui_tiles"); a.bytes(make_ui_tiles(), "HUD / utility tiles 240-255")
    a.label("weapon_tiles"); a.bytes(make_weapon_tiles(), "32x32 weapon tiles 240-255")
    a.label("static_view_tiles"); a.bytes(make_static_view_tiles(), "ceiling/floor plus five repeating wall styles")
    a.label("tilemap_data"); a.bytes(make_tilemap(), "base 32x32 tile-number map")
    a.label("attrmap_page0"); a.bytes(make_attrmap(0), "page 0 CGB attributes")
    a.label("attrmap_page1"); a.bytes(make_attrmap(1), "page 1 CGB attributes")

    bg_palette_values = [
        rgb15(2, 4, 10), rgb15(7, 8, 11), rgb15(26, 17, 8), rgb15(16, 9, 5),
        rgb15(1, 2, 3), rgb15(7, 8, 9), rgb15(29, 27, 20), rgb15(31, 5, 4),
    ]
    obj_palette_values = [
        rgb15(0, 0, 0), rgb15(6, 7, 9), rgb15(16, 18, 20), rgb15(30, 29, 24),
        rgb15(0, 0, 0), rgb15(31, 10, 0), rgb15(31, 24, 1), rgb15(31, 31, 25),
    ]
    a.label("bg_palettes"); a.bytes(words_le(bg_palette_values), "two CGB BG palettes")
    a.label("obj_palettes"); a.bytes(words_le(obj_palette_values), "two CGB OBJ palettes")

    a.align(256, text="legacy movement table alignment")
    for name in ("step_dx", "step_dy", "move_dx", "move_dy"):
        a.label(name); a.bytes(tables[name], name)
    a.align(1024, text="1024-direction ray table alignment")
    a.label("ray_dx_1024"); a.bytes(tables["ray_dx"], "signed render dx")
    a.label("ray_dy_1024"); a.bytes(tables["ray_dy"], "signed render dy")
    a.label("ray_offsets_q10"); a.bytes(tables["ray_offsets"], "80 signed 10-bit camera-plane offsets")
    a.label("ray_corrections"); a.bytes(tables["ray_corrections"], "80 cosine correction factors")
    a.align(256, text="projection table alignment")
    a.label("projection_half"); a.bytes(tables["projection_half"], "perpendicular sixteenths to wall half-height")
    microstrips = make_microstrips()
    style_block = MICRO_STATE_COUNT * 4 * 16
    a.label("microstrip_style_bases")
    for style in range(STYLE_COUNT): a.dw_label(f"microstrips_style_{style}")
    for style in range(STYLE_COUNT):
        a.label(f"microstrips_style_{style}")
        a.bytes(microstrips[style * style_block:(style + 1) * style_block], f"style {style} edge microstrips")

    code = a.resolve()
    metadata = {
        "engine_origin": a.origin,
        "engine_end": a.origin + len(code),
        "engine_size": len(code),
        "renderer": "signed-error DDA + low-noise 2D material microstrip compositor",
        "framebuffer_bytes": 0,
        "dynamic_tile_capacity": DYNAMIC_TILE_CAPACITY,
        "dynamic_tile_buffer_bytes": DYNAMIC_TILE_CAPACITY * 16,
        "view_map_buffer_bytes": 384,
        "maximum_commit_bytes": DYNAMIC_TILE_CAPACITY * 16 + 384,
        "maximum_commit_blocks": DYNAMIC_TILE_CAPACITY + 24,
        "rays": RAYS,
        "ray_width_pixels": RAY_WIDTH,
        "adaptive_anchor_casts": 41,
        "adaptive_validation": "same axis/material/plane, adjacent face cells, and <=2-pixel anchor slope",
        "ray_direction_table_entries": 1024,
        "ray_vector_scale": RAY_VECTOR_SCALE,
        "viewport": list(VIEWPORT),
        "map": [16, 16],
        "wall_styles": STYLE_COUNT,
        "wall_material_names": list(WALL_MATERIAL_NAMES),
        "wall_pattern_resolution_pairs": [4, 8],
        "full_width_contrast_bands": 0,
        "static_view_tiles": STATIC_VIEW_TILES,
        "microstrip_states": MICRO_STATE_COUNT,
        "microstrip_rom_bytes": STYLE_COUNT * MICRO_STATE_COUNT * 4 * 16,
        "rom_banks": 2,
        "cartridge_type": "ROM ONLY",
    }
    return code, a, metadata


def make_rom() -> tuple[bytes, Assembler, dict[str, object]]:
    engine, assembler, metadata = build_engine()
    if 0x0150 + len(engine) > 0x8000:
        raise RuntimeError(f"engine does not fit 32 KiB ROM: end={0x0150 + len(engine):04X}")
    rom = bytearray([0xFF] * 0x8000)
    rom[0x0100:0x0104] = bytes((0x00, 0xC3, 0x50, 0x01))
    rom[0x0104:0x0134] = NINTENDO_LOGO
    rom[0x0134:0x0143] = b"LUPINE3D".ljust(15, b"\0")
    rom[0x0143] = 0xC0; rom[0x0144:0x0146] = b"00"; rom[0x0146] = 0
    rom[0x0147] = 0; rom[0x0148] = 0; rom[0x0149] = 0; rom[0x014A] = 1; rom[0x014B] = 0x33; rom[0x014C] = 2
    rom[0x0150:0x0150 + len(engine)] = engine
    chk = 0
    for value in rom[0x0134:0x014D]: chk = (chk - value - 1) & 0xFF
    rom[0x014D] = chk
    rom[0x014E] = rom[0x014F] = 0
    total = sum(rom) & 0xFFFF
    rom[0x014E] = (total >> 8) & 0xFF; rom[0x014F] = total & 0xFF
    metadata.update({
        "header_checksum": chk, "global_checksum": total, "title": "LUPINE3D",
        "cgb_flag": "0xC0 (CGB-only)", "rom_size_bytes": len(rom),
        "sha256": hashlib.sha256(rom).hexdigest(),
        "symbols": {k: f"0x{v:04X}" for k, v in sorted(assembler.labels.items(), key=lambda item: item[1])},
    })
    return bytes(rom), assembler, metadata


def main() -> None:
    rom, assembler, metadata = make_rom()
    rom_path = BUILD / "lupine3d.gb"; rom_path.write_bytes(rom)
    assembler.write_listing(BUILD / "lupine3d.lst")
    (BUILD / "lupine3d.sym").write_text("\n".join(f"{addr:04X} {name}" for name, addr in sorted(assembler.labels.items(), key=lambda item: item[1])) + "\n", encoding="utf-8")
    (BUILD / "build_manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Built {rom_path} ({len(rom)} bytes)")
    print(f"Engine: {metadata['engine_size']} bytes, end={metadata['engine_end']:#06x}")
    print(f"Header checksum: {metadata['header_checksum']:#04x}; global: {metadata['global_checksum']:#06x}")


if __name__ == "__main__":
    main()
