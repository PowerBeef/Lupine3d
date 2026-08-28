#!/usr/bin/env python3
"""Build Lupine 3D v0.4.0: exact-fidelity CGB performance architecture."""
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
ASSETS = ROOT / "assets"

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

# MBC5 turns otherwise-idle cartridge space into an exact arithmetic unit.
# Banks 0/1 retain the complete 32 KiB engine image; banks 2..145 contain a
# byte-exact projection result for every live (component, correction, D32)
# tuple.  The 4 MiB power-of-two image is accepted by unmodified MBC5 carts.
ROM_BYTES = 4 * 1024 * 1024
ROM_BANKS = ROM_BYTES // 0x4000
PROJECTION_LUT_BASE_BANK = 2
PROJECTION_LUT_CORRECTION_MIN = 110
PROJECTION_LUT_CORRECTION_COUNT = 18
PROJECTION_LUT_COMPONENTS = 256
PROJECTION_LUT_DISTANCES = 512
PROJECTION_LUT_BYTES = (
    PROJECTION_LUT_COMPONENTS
    * PROJECTION_LUT_CORRECTION_COUNT
    * PROJECTION_LUT_DISTANCES
)
PRODUCT_LUT_BASE_BANK = PROJECTION_LUT_BASE_BANK + PROJECTION_LUT_BYTES // 0x4000
PRODUCT_LUT_MULTIPLIERS = 128
PRODUCT_LUT_MULTIPLICANDS = 256
PRODUCT_LUT_BYTES = PRODUCT_LUT_MULTIPLIERS * PRODUCT_LUT_MULTIPLICANDS * 2

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

# 160 physical-pixel descriptors.  These are synthesized from the 80-ray
# backbone and selectively replaced by exact physical-pixel casts at face
# discontinuities.  The compositor consumes these arrays directly.
PIXEL_TOPS = 0xD400
PIXEL_STYLES = 0xD4A0
PIXEL_KEYS = 0xD540
PIXEL_ALONG = 0xD5E0

# Hot scalar state is a deliberately stable HRAM ABI.  All accesses emitted
# through ld_a_abs/ld_abs_a become the shorter LDH form; descriptor arrays and
# bulk buffers remain in WRAM.  Presentation/interrupt bytes will be allocated
# at the tail so renderer scratch lifetimes can never alias them.
HRAM_LAYOUT: dict[str, int] = {}
_hram_next = 0xFF80


def _hram(name: str) -> int:
    global _hram_next
    if _hram_next >= 0xFFFF:
        raise RuntimeError("Lupine3D HRAM ABI exceeds $FFFE")
    address = _hram_next
    HRAM_LAYOUT[name] = address
    _hram_next += 1
    return address


# DDA state.
DDA_MAP_X = _hram("DDA_MAP_X")
DDA_MAP_Y = _hram("DDA_MAP_Y")
DDA_ABS_X = _hram("DDA_ABS_X")
DDA_ABS_Y = _hram("DDA_ABS_Y")
DDA_STEP_X = _hram("DDA_STEP_X")
DDA_STEP_Y = _hram("DDA_STEP_Y")
DDA_NEXT_X_L = _hram("DDA_NEXT_X_L")
DDA_NEXT_X_H = _hram("DDA_NEXT_X_H")
DDA_NEXT_Y_L = _hram("DDA_NEXT_Y_L")
DDA_NEXT_Y_H = _hram("DDA_NEXT_Y_H")
DDA_ERR_L = _hram("DDA_ERR_L")
DDA_ERR_H = _hram("DDA_ERR_H")
DDA_AXIS = _hram("DDA_AXIS")
DDA_DIST_L = _hram("DDA_DIST_L")
DDA_DIST_H = _hram("DDA_DIST_H")
DDA_MATERIAL = _hram("DDA_MATERIAL")
DDA_CROSSINGS = _hram("DDA_CROSSINGS")
DDA_ANGLE_L = _hram("DDA_ANGLE_L")
DDA_ANGLE_H = _hram("DDA_ANGLE_H")
DDA_CORRECTION = _hram("DDA_CORRECTION")
TOP_RESULT = _hram("TOP_RESULT")
STYLE_RESULT = _hram("STYLE_RESULT")
FACE_RESULT = _hram("FACE_RESULT")
ALONG_RESULT = _hram("ALONG_RESULT")
ADAPTIVE_CASTS = _hram("ADAPTIVE_CASTS")
CAST_INDEX = _hram("CAST_INDEX")
ADAPTIVE_INDEX = _hram("ADAPTIVE_INDEX")

# Cast loop pointers.
CAST_OFFSET_PTR_L = _hram("CAST_OFFSET_PTR_L")
CAST_OFFSET_PTR_H = _hram("CAST_OFFSET_PTR_H")
CAST_CORR_PTR_L = _hram("CAST_CORR_PTR_L")
CAST_CORR_PTR_H = _hram("CAST_CORR_PTR_H")
CAST_TOP_PTR_L = _hram("CAST_TOP_PTR_L")
CAST_TOP_PTR_H = _hram("CAST_TOP_PTR_H")
CAST_STYLE_PTR_L = _hram("CAST_STYLE_PTR_L")
CAST_STYLE_PTR_H = _hram("CAST_STYLE_PTR_H")
CAST_COUNT = _hram("CAST_COUNT")

# Pose-invariant DDA boundary distances, prepared once per visual cast batch.
FRAME_X_POS_L = _hram("FRAME_X_POS_L")
FRAME_X_POS_H = _hram("FRAME_X_POS_H")
FRAME_X_NEG_L = _hram("FRAME_X_NEG_L")
FRAME_X_NEG_H = _hram("FRAME_X_NEG_H")
FRAME_Y_POS_L = _hram("FRAME_Y_POS_L")
FRAME_Y_POS_H = _hram("FRAME_Y_POS_H")
FRAME_Y_NEG_L = _hram("FRAME_Y_NEG_L")
FRAME_Y_NEG_H = _hram("FRAME_Y_NEG_H")

# Tile compositor state.
DYN_COUNT = _hram("DYN_COUNT")
DYN_HIGH_WATER = _hram("DYN_HIGH_WATER")
DYN_OVERFLOW = _hram("DYN_OVERFLOW")
DYN_PTR_L = _hram("DYN_PTR_L")
DYN_PTR_H = _hram("DYN_PTR_H")
MAP_PTR_L = _hram("MAP_PTR_L")
MAP_PTR_H = _hram("MAP_PTR_H")
SCAN_TOP_PTR_L = _hram("SCAN_TOP_PTR_L")
SCAN_TOP_PTR_H = _hram("SCAN_TOP_PTR_H")
SCAN_STYLE_PTR_L = _hram("SCAN_STYLE_PTR_L")
SCAN_STYLE_PTR_H = _hram("SCAN_STYLE_PTR_H")
TILE_ROW = _hram("TILE_ROW")
TILE_Y0 = _hram("TILE_Y0")
TILE_COL_COUNT = _hram("TILE_COL_COUNT")
MIN_TOP = _hram("MIN_TOP")
MAX_TOP = _hram("MAX_TOP")
FIRST_STYLE = _hram("FIRST_STYLE")
STYLE_DIFF = _hram("STYLE_DIFF")
CLASSIFY_COUNT = _hram("CLASSIFY_COUNT")
DYNAMIC_FLAG = _hram("DYNAMIC_FLAG")
GEN_GLOBAL_Y = _hram("GEN_GLOBAL_Y")
GEN_ROW_COUNT = _hram("GEN_ROW_COUNT")
GEN_PAIR_COUNT = _hram("GEN_PAIR_COUNT")
ACC_LOW = _hram("ACC_LOW")
ACC_HIGH = _hram("ACC_HIGH")
TEMP_TOP = _hram("TEMP_TOP")
TEMP_STYLE = _hram("TEMP_STYLE")
TILE_ID_RESULT = _hram("TILE_ID_RESULT")
ROW_PAD_COUNT = _hram("ROW_PAD_COUNT")
COLUMN_COUNT = _hram("COLUMN_COUNT")
ROW_RENDER_COUNT = _hram("ROW_RENDER_COUNT")
COLUMN_MAP_L = _hram("COLUMN_MAP_L")
COLUMN_MAP_H = _hram("COLUMN_MAP_H")
COMPOSE_DST_L = _hram("COMPOSE_DST_L")
COMPOSE_DST_H = _hram("COMPOSE_DST_H")
STRIP_STATE = _hram("STRIP_STATE")
STRIP_STYLE = _hram("STRIP_STYLE")
STRIP_PAIR = _hram("STRIP_PAIR")

# Hybrid subcolumn / face-event state.
PIXEL_INDEX = _hram("PIXEL_INDEX")
PAIR_INDEX = _hram("PAIR_INDEX")
EDGE_INDEX = _hram("EDGE_INDEX")
EDGE_RECASTS = _hram("EDGE_RECASTS")
D32_HIGH = _hram("D32_HIGH")
PROJECTION_PAGE = _hram("PROJECTION_PAGE")
SCAN_KEY_PTR_L = _hram("SCAN_KEY_PTR_L")
SCAN_KEY_PTR_H = _hram("SCAN_KEY_PTR_H")
SCAN_ALONG_PTR_L = _hram("SCAN_ALONG_PTR_L")
SCAN_ALONG_PTR_H = _hram("SCAN_ALONG_PTR_H")
STRIP_MASK = _hram("STRIP_MASK")
DOOR_RUN_START = _hram("DOOR_RUN_START")
DOOR_RUN_END = _hram("DOOR_RUN_END")
EVENT_INDEX = _hram("EVENT_INDEX")
EVENT_COUNT = _hram("EVENT_COUNT")
DARK_MASK = _hram("DARK_MASK")
SIGNATURE_COUNT = _hram("SIGNATURE_COUNT")
SIGNATURE_HASH = _hram("SIGNATURE_HASH")
ATLAS_ENTRY_COUNT = _hram("ATLAS_ENTRY_COUNT")
ATLAS_ENTRY_PTR_L = _hram("ATLAS_ENTRY_PTR_L")
ATLAS_ENTRY_PTR_H = _hram("ATLAS_ENTRY_PTR_H")
TEMP_CODE = _hram("TEMP_CODE")
HRAM_BYTES_USED = _hram_next - 0xFF80

# Aliases for compositor-local scratch bytes whose legacy names are no longer
# used by another live routine.
SECOND_TOP = GEN_GLOBAL_Y
SECOND_STYLE = GEN_ROW_COUNT
STRIP_KIND = GEN_PAIR_COUNT
D32_LOW = TEMP_CODE
LUT_CORRECTION = PROJECTION_PAGE
LUT_SLICE_LOW = SIGNATURE_COUNT

# Renderer constants / tile IDs.
RAYS = 80
PHYSICAL_COLUMNS = 160
RAY_WIDTH = 2
VIEWPORT = (160, 96)
CEILING_TILE = 96
FLOOR_TILE = 97
WALL_TILE_BASE = 98
STYLE_COUNT = 5
RENDER_STYLE_COUNT = 6
CREASE_STYLE = 5
DOOR_SPINE_STYLE = CREASE_STYLE
TECH_RIB_STYLE = CREASE_STYLE
MICRO_STATE_COUNT = 19
STATIC_WALL_MASKS = (
    0x00, 0xFF,
    0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01,
    0xC0, 0x60, 0x30, 0x18, 0x0C, 0x06, 0x03,
    0x81, 0x99, 0x91, 0x89,
)
STATIC_VIEW_TILES = 2 + len(STATIC_WALL_MASKS)
ATLAS_TILE_BASE = WALL_TILE_BASE + len(STATIC_WALL_MASKS)
FOV_DEGREES = 60.5
RAY_VECTOR_SCALE = 127

TILE_ATLAS_TILES = (ASSETS / "tile_atlas_tiles.bin").read_bytes()
TILE_ATLAS_BUCKET_START = (ASSETS / "tile_atlas_bucket_start.bin").read_bytes()
TILE_ATLAS_BUCKET_COUNT = (ASSETS / "tile_atlas_bucket_count.bin").read_bytes()
TILE_ATLAS_ENTRIES = (ASSETS / "tile_atlas_entries.bin").read_bytes()
TILE_ATLAS_COUNT = len(TILE_ATLAS_TILES) // 16
TILE_ATLAS_SIGNATURE_BYTES = 10
TILE_ATLAS_ENTRY_BYTES = TILE_ATLAS_SIGNATURE_BYTES + 1
TILE_ATLAS_SIGNATURE_COUNT = len(TILE_ATLAS_ENTRIES) // TILE_ATLAS_ENTRY_BYTES
if len(TILE_ATLAS_TILES) % 16 or len(TILE_ATLAS_ENTRIES) % TILE_ATLAS_ENTRY_BYTES:
    raise ValueError("malformed exact tile-atlas assets")
if len(TILE_ATLAS_BUCKET_START) != 256 or len(TILE_ATLAS_BUCKET_COUNT) != 256:
    raise ValueError("tile-atlas bucket tables must contain 256 bytes")
if ATLAS_TILE_BASE + TILE_ATLAS_COUNT > 240:
    raise ValueError("exact tile atlas overlaps UI/weapon tile IDs")

NINTENDO_LOGO = v1.NINTENDO_LOGO
rgb15 = v1.rgb15
words_le = v1.words_le
tile_from_pixels = v1.tile_from_pixels
make_ui_tiles = v1.make_ui_tiles
make_weapon_tiles = v1.make_weapon_tiles
make_map = v1.make_map
load_hl_abs = v1.load_hl_abs
store_hl_abs = v1.store_hl_abs


# Geometry styles 0..4 remain the exact DDA side/material contract.  In v0.3
# their base fills are deliberately phase-free: surface structure is attached
# to face/cell events in the 160-column descriptor pass instead of repeating
# in screen-tile coordinates.  Render-only styles 5..7 represent a dark
# crease, a run-centred door spine, and a narrow technology rib.
WALL_MATERIAL_NAMES = (
    "warm plaster - light face",
    "warm plaster - shadow face",
    "vertical tech panel - light face",
    "vertical tech panel - shadow face",
    "reinforced door panel",
)

WALL_BASE_COLORS = (2, 3, 2, 3, 2)
WALL_PATTERNS: tuple[tuple[tuple[int, int, int, int], ...], ...] = tuple(
    tuple((base, base, base, base) for _ in range(8))
    for base in WALL_BASE_COLORS
)



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
    """Return one phase-free/render-event 2bpp wall colour.

    ``pair`` is retained as a compatibility name for host callers; it is now
    a physical pixel position.  Only the one-pixel technology rib has sparse
    fasteners.  Because that rib is emitted at world-cell transitions, its
    horizontal placement is stable in the level rather than on the screen.
    """
    if style < STYLE_COUNT:
        return WALL_BASE_COLORS[style]
    if style == CREASE_STYLE:
        return 3
    raise ValueError(f"unknown render style: {style}")


validate_wall_patterns()


def solid_tile(color: int) -> bytes:
    return tile_from_pixels([[color] * 8 for _ in range(8)])


def make_static_view_tiles() -> bytes:
    tiles = [solid_tile(0), solid_tile(1)]
    for dark_mask in STATIC_WALL_MASKS:
        pixels = [[3 if dark_mask & (0x80 >> x) else 2 for x in range(8)] for _ in range(8)]
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
    """Precompose every physical-pixel boundary strip.

    The position-expanded table is deliberately used here: it removes mask
    logic from the hot compositor while still fitting comfortably in 32 KiB
    after the phase-free material simplification.
    """
    out = bytearray()
    for style in range(2):  # visual light/dark; geometry styles normalize with &1
        for state in range(MICRO_STATE_COUNT):
            for pixel in range(8):
                mask = 0x80 >> pixel
                for row in range(8):
                    region = microstrip_region(state, row)
                    color = 0 if region == "ceiling" else 1 if region == "floor" else wall_color(style, pixel, row)
                    top_edge = 3 <= state <= 10 and row == state - 3
                    bottom_edge = 11 <= state <= 18 and row == state - 11
                    if region == "wall" and (top_edge or bottom_edge):
                        color = 3
                    out.extend((mask if color & 1 else 0, mask if color & 2 else 0))
    assert len(out) == 2 * MICRO_STATE_COUNT * 8 * 16
    return bytes(out)


def make_pair_microstrips() -> bytes:
    """Fast two-pixel strips used when a synthesized pair remains identical."""
    out = bytearray()
    for style in range(2):
        for state in range(MICRO_STATE_COUNT):
            for pair in range(4):
                mask = 0xC0 >> (pair * 2)
                for row in range(8):
                    region = microstrip_region(state, row)
                    color = 0 if region == "ceiling" else 1 if region == "floor" else wall_color(style, pair * 2, row)
                    top_edge = 3 <= state <= 10 and row == state - 3
                    bottom_edge = 11 <= state <= 18 and row == state - 11
                    if region == "wall" and (top_edge or bottom_edge):
                        color = 3
                    out.extend((mask if color & 1 else 0, mask if color & 2 else 0))
    assert len(out) == 2 * MICRO_STATE_COUNT * 4 * 16
    return bytes(out)


def make_seam_tile_lookup() -> bytes:
    lookup = bytearray(256)
    for index, mask in enumerate(STATIC_WALL_MASKS):
        lookup[mask] = WALL_TILE_BASE + index
    return bytes(lookup)


def tile_signature_hash(signature: bytes) -> int:
    value = 0
    for code in signature:
        value = ((value << 1) | (value >> 7)) & 0xFF
        value ^= code
    return value


@lru_cache(maxsize=1)
def tile_atlas_signature_map() -> dict[bytes, int]:
    result: dict[bytes, int] = {}
    for offset in range(0, len(TILE_ATLAS_ENTRIES), TILE_ATLAS_ENTRY_BYTES):
        signature = TILE_ATLAS_ENTRIES[offset:offset + TILE_ATLAS_SIGNATURE_BYTES]
        tile_id = TILE_ATLAS_ENTRIES[offset + TILE_ATLAS_SIGNATURE_BYTES]
        if not ATLAS_TILE_BASE <= tile_id < ATLAS_TILE_BASE + TILE_ATLAS_COUNT:
            raise ValueError(f"atlas entry uses invalid tile ID {tile_id}")
        result[signature] = tile_id
    if len(result) != TILE_ATLAS_SIGNATURE_COUNT:
        raise ValueError("duplicate exact signatures in tile atlas")
    return result

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
    # Palette 1 remains reserved for the HUD.  A row ladder was prototyped for
    # zero-bandwidth depth staging, but ROM-driven visual QA showed that even
    # modest tile-row changes read as the old horizontal-banding defect.  Keep
    # the viewport phase-free and reserve the additional palettes for future
    # face/material selection rather than screen-space gradients.
    row_palettes = (0,) * 12
    for y in range(12):
        for x in range(20):
            data[y * 32 + x] = (view_bank << 3) | row_palettes[y]
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
    ray_packed = bytearray()
    for angle in range(1024):
        rad = angle * math.tau / 1024.0
        dx = round(math.cos(rad) * RAY_VECTOR_SCALE)
        dy = round(math.sin(rad) * RAY_VECTOR_SCALE)
        ray_dx.append(dx & 0xFF)
        ray_dy.append(dy & 0xFF)
        ray_packed.extend((
            abs(dx), abs(dy),
            1 if dx > 0 else 0xFF if dx < 0 else 0,
            1 if dy > 0 else 0xFF if dy < 0 else 0,
        ))

    plane = math.tan(math.radians(FOV_DEGREES * 0.5))
    offsets: list[int] = []
    corrections = bytearray()
    for i in range(RAYS):
        screen_x = (i + 0.5) * VIEWPORT[0] / RAYS
        camera_x = 2.0 * screen_x / VIEWPORT[0] - 1.0
        off_rad = math.atan(camera_x * plane)
        offsets.append(round(off_rad * 1024.0 / math.tau))
        corrections.append(round(math.cos(off_rad) * RAY_VECTOR_SCALE))

    physical_offsets: list[int] = []
    physical_corrections = bytearray()
    for i in range(PHYSICAL_COLUMNS):
        screen_x = i + 0.5
        camera_x = 2.0 * screen_x / VIEWPORT[0] - 1.0
        off_rad = math.atan(camera_x * plane)
        physical_offsets.append(round(off_rad * 1024.0 / math.tau))
        physical_corrections.append(round(math.cos(off_rad) * RAY_VECTOR_SCALE))

    offsets_blob = bytearray()
    for value in offsets:
        value &= 0xFFFF
        offsets_blob.extend((value & 0xFF, value >> 8))

    physical_offsets_blob = bytearray()
    for value in physical_offsets:
        value &= 0xFFFF
        physical_offsets_blob.extend((value & 0xFF, value >> 8))

    projection_half = bytearray()
    for perpendicular_thirty_seconds in range(512):
        if perpendicular_thirty_seconds == 0:
            half = 48
        else:
            half = max(2, min(48, round(960.0 / perpendicular_thirty_seconds)))
        projection_half.append(half)

    return {
        "step_dx": bytes(step_dx), "step_dy": bytes(step_dy),
        "move_dx": bytes(move_dx), "move_dy": bytes(move_dy),
        "ray_dx": bytes(ray_dx), "ray_dy": bytes(ray_dy),
        "ray_packed": bytes(ray_packed),
        "ray_offsets": bytes(offsets_blob), "ray_corrections": bytes(corrections),
        "physical_offsets": bytes(physical_offsets_blob),
        "physical_corrections": bytes(physical_corrections),
        "projection_half": bytes(projection_half),
    }


@lru_cache(maxsize=1)
def make_projection_top_lut() -> bytes:
    """Exhaustive, integer-exact replacement for multiply/divide projection.

    The table is indexed in 512-byte slices so the low nine-bit distance is
    the address within a slice.  Thirty-two slices fit each MBC5 bank.
    Component zero is populated defensively even though an axial hit always
    selects the other non-zero vector component.
    """
    projection = make_tables()["projection_half"]
    out = bytearray(PROJECTION_LUT_BYTES)
    cursor = 0
    for component in range(PROJECTION_LUT_COMPONENTS):
        safe_component = max(1, component)
        for correction in range(
            PROJECTION_LUT_CORRECTION_MIN,
            PROJECTION_LUT_CORRECTION_MIN + PROJECTION_LUT_CORRECTION_COUNT,
        ):
            for distance in range(PROJECTION_LUT_DISTANCES):
                perpendicular = min(
                    511,
                    (distance * correction + safe_component // 2) // safe_component,
                )
                out[cursor] = 48 - projection[perpendicular]
                cursor += 1
    assert cursor == PROJECTION_LUT_BYTES
    return bytes(out)


@lru_cache(maxsize=1)
def make_product_lut() -> bytes:
    """All 8x7-bit unsigned products used by signed-error DDA setup."""
    out = bytearray(PRODUCT_LUT_BYTES)
    cursor = 0
    for multiplier in range(PRODUCT_LUT_MULTIPLIERS):
        for multiplicand in range(PRODUCT_LUT_MULTIPLICANDS):
            product = multiplier * multiplicand
            out[cursor] = product & 0xFF
            out[cursor + 1] = product >> 8
            cursor += 2
    return bytes(out)


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


def _reference_cast_hit(player_x_q8: int, player_y_q8: int, player_angle: int,
                        ray_index: int, offsets_key: str, corrections_key: str,
                        count: int, grid: bytes | None = None) -> ReferenceRayHit:
    """Byte-exact host model shared by pair-centre and physical-pixel rays."""
    if not 0 <= ray_index < count:
        raise ValueError(f"ray index out of range: {ray_index}")
    tables = make_tables()
    offsets = tables[offsets_key]
    corrections = tables[corrections_key]
    off = int.from_bytes(offsets[ray_index * 2:ray_index * 2 + 2], "little", signed=True)
    corr = corrections[ray_index]
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
    d32 = min(511, (distance + 4) >> 3)
    perp32 = 511 if component == 0 else min(511, (d32 * corr + component // 2) // component)
    projection = tables["projection_half"]
    top = 48 - projection[perp32]
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


def reference_cast_hit(player_x_q8: int, player_y_q8: int, player_angle: int,
                       ray_index: int, grid: bytes | None = None) -> ReferenceRayHit:
    """Byte-exact host model of one 80-ray backbone sample."""
    return _reference_cast_hit(
        player_x_q8, player_y_q8, player_angle, ray_index,
        "ray_offsets", "ray_corrections", RAYS, grid,
    )


def reference_cast_physical_hit(player_x_q8: int, player_y_q8: int, player_angle: int,
                                pixel_index: int, grid: bytes | None = None) -> ReferenceRayHit:
    """Byte-exact host model of one physical-pixel edge-recast sample."""
    return _reference_cast_hit(
        player_x_q8, player_y_q8, player_angle, pixel_index,
        "physical_offsets", "physical_corrections", PHYSICAL_COLUMNS, grid,
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

def reference_adaptive_descriptor_view(player_x_q8: int, player_y_q8: int, player_angle: int,
                                       grid: bytes | None = None) -> tuple[list[int], list[int], list[int], list[int], int]:
    """Apply the ROM's validated one-level affine span reconstruction."""
    full_tops, full_styles, full_keys, full_alongs = reference_full_descriptor_view(player_x_q8, player_y_q8, player_angle, grid)
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


def reference_pixel_descriptor_view(
    player_x_q8: int, player_y_q8: int, player_angle: int, grid: bytes | None = None,
) -> tuple[list[int], list[int], list[int], list[int], int, int, int]:
    """Build the final 160 physical-pixel descriptor stream.

    Pair-centre samples are reconstructed at quarter intervals, then the two
    physical samples adjacent to every detected face discontinuity are recast
    exactly.  Finally, face/cell events become render-only styles with simple
    projected-height LOD.  The returned counters are total casts, edge recasts,
    and material events.
    """
    tops, styles, keys, alongs, adaptive_casts = reference_adaptive_descriptor_view(
        player_x_q8, player_y_q8, player_angle, grid
    )
    pixel_tops = [0] * PHYSICAL_COLUMNS
    pixel_styles = [0] * PHYSICAL_COLUMNS
    pixel_keys = [0] * PHYSICAL_COLUMNS
    pixel_alongs = [0] * PHYSICAL_COLUMNS

    for i in range(RAYS):
        current = tops[i]
        previous = tops[i - 1] if i else current
        following = tops[i + 1] if i + 1 < RAYS else current
        pixel_tops[i * 2] = (current * 3 + previous + 2) // 4
        pixel_tops[i * 2 + 1] = (current * 3 + following + 2) // 4
        for output in (i * 2, i * 2 + 1):
            pixel_styles[output] = styles[i]
            pixel_keys[output] = keys[i]
            pixel_alongs[output] = alongs[i]

    edge_recasts = 0
    for i in range(RAYS - 1):
        if keys[i] == keys[i + 1]:
            continue
        for pixel_index in (i * 2 + 1, i * 2 + 2):
            hit = reference_cast_physical_hit(player_x_q8, player_y_q8, player_angle, pixel_index, grid)
            pixel_tops[pixel_index] = hit.top
            pixel_styles[pixel_index] = hit.style
            pixel_keys[pixel_index] = hit.face_key
            pixel_alongs[pixel_index] = hit.along
            edge_recasts += 1

    events = 0
    for i in range(1, PHYSICAL_COLUMNS):
        if pixel_keys[i - 1] != pixel_keys[i]:
            if pixel_tops[i - 1] <= 40:
                pixel_styles[i - 1] = CREASE_STYLE
            if pixel_tops[i] <= 40:
                pixel_styles[i] = CREASE_STYLE
            events += 1
        elif pixel_alongs[i - 1] != pixel_alongs[i] and pixel_tops[i] <= 40:
            material = (pixel_keys[i] >> 5) & 3
            pixel_styles[i] = TECH_RIB_STYLE if material == 2 else CREASE_STYLE
            events += 1

    # Door features are derived from each contiguous projected run, so the
    # frame and spine remain attached to the door instead of repeating every
    # eight screen pixels.
    i = 0
    while i < PHYSICAL_COLUMNS:
        if ((pixel_keys[i] >> 5) & 3) != 3:
            i += 1
            continue
        start = i
        while i < PHYSICAL_COLUMNS and ((pixel_keys[i] >> 5) & 3) == 3:
            i += 1
        end = i - 1
        if pixel_tops[start] <= 40:
            pixel_styles[start] = CREASE_STYLE
        if pixel_tops[end] <= 40:
            pixel_styles[end] = CREASE_STYLE
        if end - start + 1 >= 3:
            middle = (start + end) // 2
            if pixel_tops[middle] <= 32:
                pixel_styles[middle] = DOOR_SPINE_STYLE
                if middle + 1 <= end:
                    pixel_styles[middle + 1] = DOOR_SPINE_STYLE
        events += 1

    return (
        pixel_tops, pixel_styles, pixel_keys, pixel_alongs,
        adaptive_casts + edge_recasts, edge_recasts, events,
    )


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


def reference_tile_signature_and_bytes(tops: list[int], styles: list[int], tile_y0: int) -> tuple[bytes, bytes]:
    """Return the exact ten-byte signature and 16-byte composed tile."""
    dark_mask = sum((style & 1) << (7 - pixel) for pixel, style in enumerate(styles))
    signature = bytearray((tile_y0, dark_mask, *tops))
    tile = bytearray(16)
    for pixel, (top, style) in enumerate(zip(tops, styles)):
        state = reference_strip_state(top, tile_y0)
        mask = 0x80 >> pixel
        for row in range(8):
            region = microstrip_region(state, row)
            color = 0 if region == "ceiling" else 1 if region == "floor" else wall_color(style, pixel, row)
            top_edge = 3 <= state <= 10 and row == state - 3
            bottom_edge = 11 <= state <= 18 and row == state - 11
            if region == "wall" and (top_edge or bottom_edge):
                color = 3
            if color & 1:
                tile[row * 2] |= mask
            if color & 2:
                tile[row * 2 + 1] |= mask
    return bytes(signature), bytes(tile)


def reference_compose_view(tops: list[int], styles: list[int]) -> tuple[bytes, bytes, int, bool]:
    """Byte-exact host model of the edge-microstrip tile compositor.

    The ROM walks viewport columns first so dynamic-tile allocation order is
    column-major even though the 32-byte BG map itself is row-major.  Every
    padding cell is initialized to the ceiling tile so the complete 384-byte
    DMA payload is deterministic on hardware whose WRAM power-on contents are
    not an engine contract.
    """
    if len(tops) != PHYSICAL_COLUMNS or len(styles) != PHYSICAL_COLUMNS:
        raise ValueError(f"expected {PHYSICAL_COLUMNS} physical-pixel descriptors")

    dynamic = bytearray()
    view_map = bytearray([CEILING_TILE] * (12 * 32))
    overflow = False
    atlas = tile_atlas_signature_map()

    for tile_col in range(20):
        first = tile_col * 8
        col_tops = tops[first:first + 8]
        col_styles = styles[first:first + 8]
        min_top = min(col_tops)
        max_top = max(col_tops)
        dark_mask = sum((style & 1) << (7 - pixel) for pixel, style in enumerate(col_styles))
        static_wall_tile = make_seam_tile_lookup()[dark_mask]

        for tile_row in range(12):
            y0 = tile_row * 8
            if y0 + 7 < min_top:
                tile_id = CEILING_TILE
            elif y0 >= 96 - min_top:
                tile_id = FLOOR_TILE
            elif y0 >= max_top and y0 + 7 < 96 - max_top and static_wall_tile:
                tile_id = static_wall_tile
            else:
                signature, tile = reference_tile_signature_and_bytes(col_tops, col_styles, y0)
                atlas_id = atlas.get(signature)
                if atlas_id is not None:
                    tile_id = atlas_id
                else:
                    tile_id = len(dynamic) // 16
                    if tile_id >= DYNAMIC_TILE_CAPACITY:
                        overflow = True
                        tile_id = WALL_TILE_BASE
                    else:
                        dynamic.extend(tile)
            view_map[tile_row * 32 + tile_col] = tile_id

    return bytes(dynamic), bytes(view_map), len(dynamic) // 16, overflow

def emit_mul_u8(a: Assembler) -> None:
    """B*C -> HL through a four-bank exact MBC5 product table.

    DDA components are bounded to 0..127, so C selects one of 128 complete
    256-entry product rows.  This replaces an eight-iteration shift/add loop
    without changing a single arithmetic result.
    """
    a.label("mul_u8")
    a.ld_r_r("a", "c")
    for _ in range(5): a.cb("srl", "a")
    a.add_a_n(PRODUCT_LUT_BASE_BANK); a.ld_abs_a(0x2000)
    # Address = $4000 + (C&31)*512 + B*2.
    a.ld_r_r("a", "c"); a.and_n(0x1F); a.add_a_r("a"); a.ld_r_r("d", "a")
    a.ld_r_r("a", "b"); a.add_a_r("a"); a.ld_r_r("l", "a")
    a.ld_r_n("a", 0); a.adc_a_n(0); a.or_r("d"); a.or_n(0x40); a.ld_r_r("h", "a")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    a.ld_r_r("h", "d"); a.ld_r_r("l", "e")
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


def emit_div_u16_u8_sat9(a: Assembler) -> None:
    """HL/B -> 9-bit quotient as PROJECTION_PAGE:A, saturated to 511."""
    a.label("div_u16_u8_sat9")
    a.xor_r("a"); a.ld_abs_a(PROJECTION_PAGE)
    a.ld_r_r("a", "b"); a.or_r("a"); a.jr("div9_sat", "z")
    # A quotient below 256 can use the compact existing divider directly.
    a.ld_r_r("a", "h"); a.cp_r("b"); a.jp("div_u16_u8_sat", "c")
    # Subtract B*256.  The residual quotient is the low byte and the table
    # page records the implicit +256.  A second full page saturates to 511.
    a.sub_r("b"); a.ld_r_r("h", "a"); a.cp_r("b"); a.jr("div9_sat", "nc")
    a.ld_r_n("a", 1); a.ld_abs_a(PROJECTION_PAGE)
    a.jp("div_u16_u8_sat")
    a.label("div9_sat")
    a.ld_r_n("a", 1); a.ld_abs_a(PROJECTION_PAGE)
    a.ld_r_n("a", 0xFF); a.ret()


def emit_palette_init(a: Assembler) -> None:
    """Upload all eight BG palettes and the two OBJ palettes in use."""
    a.label("init_palettes")
    a.ld_r_n("a", 0x80); a.ldh_n_a(BGPI)
    a.ld_rr_label("hl", "bg_palettes"); a.ld_r_n("b", 64)
    a.label("init_bg_palette_loop")
    a.ldi_a_hl(); a.ldh_n_a(BGPD); a.dec_r("b"); a.jr("init_bg_palette_loop", "nz")
    a.ld_r_n("a", 0x80); a.ldh_n_a(OBPI)
    a.ld_rr_label("hl", "obj_palettes"); a.ld_r_n("b", 16)
    a.label("init_obj_palette_loop")
    a.ldi_a_hl(); a.ldh_n_a(OBPD); a.dec_r("b"); a.jr("init_obj_palette_loop", "nz")
    a.ret()


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
    a.ld_rr_label("hl", "tile_atlas_tiles"); a.ld_rr_nn("de", 0x8000 + ATLAS_TILE_BASE * 16); a.ld_rr_nn("bc", len(TILE_ATLAS_TILES)); a.call("copy_bc")
    a.ld_rr_label("hl", "ui_tiles"); a.ld_rr_nn("de", 0x8F00); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9800); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9C00); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    # Bank 1 mirrors viewport tiles and holds weapon OBJ tiles plus attributes.
    a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.ld_rr_label("hl", "static_view_tiles"); a.ld_rr_nn("de", 0x8600); a.ld_rr_nn("bc", STATIC_VIEW_TILES * 16); a.call("copy_bc")
    a.ld_rr_label("hl", "tile_atlas_tiles"); a.ld_rr_nn("de", 0x8000 + ATLAS_TILE_BASE * 16); a.ld_rr_nn("bc", len(TILE_ATLAS_TILES)); a.call("copy_bc")
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
    a.label("prepare_frame_boundaries")
    # Distance from the player fraction to each side of its current cell. The
    # four values are pose-invariant across every ray in one visual update.
    a.ld_a_abs(PLAYER_XL); a.ld_abs_a(FRAME_X_NEG_L); a.xor_r("a"); a.ld_abs_a(FRAME_X_NEG_H)
    a.ld_a_abs(PLAYER_XL); a.cpl(); a.inc_r("a"); a.ld_abs_a(FRAME_X_POS_L)
    a.ld_r_n("a", 0); a.jr("frame_x_pos_high_ready", "nz"); a.inc_r("a")
    a.label("frame_x_pos_high_ready"); a.ld_abs_a(FRAME_X_POS_H)
    a.ld_a_abs(PLAYER_YL); a.ld_abs_a(FRAME_Y_NEG_L); a.xor_r("a"); a.ld_abs_a(FRAME_Y_NEG_H)
    a.ld_a_abs(PLAYER_YL); a.cpl(); a.inc_r("a"); a.ld_abs_a(FRAME_Y_POS_L)
    a.ld_r_n("a", 0); a.jr("frame_y_pos_high_ready", "nz"); a.inc_r("a")
    a.label("frame_y_pos_high_ready"); a.ld_abs_a(FRAME_Y_POS_H); a.ret()

    a.label("dda_setup")
    # Map coordinates.
    a.ld_a_abs(PLAYER_XH); a.ld_abs_a(DDA_MAP_X)
    a.ld_a_abs(PLAYER_YH); a.ld_abs_a(DDA_MAP_Y)

    # One sequential four-byte fetch replaces two tables plus sign decoding.
    load_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.add_hl_rr("hl"); a.add_hl_rr("hl")
    a.ld_rr_label("de", "ray_vectors_packed"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_abs_a(DDA_ABS_X)
    a.ldi_a_hl(); a.ld_abs_a(DDA_ABS_Y)
    a.ldi_a_hl(); a.ld_abs_a(DDA_STEP_X)
    a.ld_a_hl(); a.ld_abs_a(DDA_STEP_Y)

    # Initial distance to next X boundary in Q8.8.
    a.ld_a_abs(DDA_STEP_X); a.cp_n(1); a.jr("dda_next_x_positive", "z")
    a.cp_n(0xFF); a.jr("dda_next_x_negative", "z")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_NEXT_X_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_NEXT_X_H); a.jr("dda_next_x_done")
    a.label("dda_next_x_positive")
    a.ld_a_abs(FRAME_X_POS_L); a.ld_abs_a(DDA_NEXT_X_L); a.ld_a_abs(FRAME_X_POS_H); a.ld_abs_a(DDA_NEXT_X_H); a.jr("dda_next_x_done")
    a.label("dda_next_x_negative")
    a.ld_a_abs(FRAME_X_NEG_L); a.ld_abs_a(DDA_NEXT_X_L); a.ld_a_abs(FRAME_X_NEG_H); a.ld_abs_a(DDA_NEXT_X_H)
    a.label("dda_next_x_done")

    # Initial distance to next Y boundary.
    a.ld_a_abs(DDA_STEP_Y); a.cp_n(1); a.jr("dda_next_y_positive", "z")
    a.cp_n(0xFF); a.jr("dda_next_y_negative", "z")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(DDA_NEXT_Y_L); a.ld_r_n("a", 0x7F); a.ld_abs_a(DDA_NEXT_Y_H); a.jr("dda_next_y_done")
    a.label("dda_next_y_positive")
    a.ld_a_abs(FRAME_Y_POS_L); a.ld_abs_a(DDA_NEXT_Y_L); a.ld_a_abs(FRAME_Y_POS_H); a.ld_abs_a(DDA_NEXT_Y_H); a.jr("dda_next_y_done")
    a.label("dda_next_y_negative")
    a.ld_a_abs(FRAME_Y_NEG_L); a.ld_abs_a(DDA_NEXT_Y_L); a.ld_a_abs(FRAME_Y_NEG_H); a.ld_abs_a(DDA_NEXT_Y_H)
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
    # Q5 distance: D32 = round(axis distance / 8), saturated to 511.
    # The additional fractional bit materially reduces near-wall height
    # quantization while keeping the product inside 16 bits.
    a.ld_a_abs(DDA_DIST_L); a.add_a_n(4); a.ld_r_r("l", "a")
    a.ld_a_abs(DDA_DIST_H); a.adc_a_n(0); a.ld_r_r("h", "a")
    for _ in range(3):
        a.cb("srl", "h"); a.cb("rr", "l")
    a.ld_r_r("a", "h"); a.cp_n(2); a.jr("project_d32_sat", "nc")
    a.ld_abs_a(D32_HIGH); a.ld_r_r("b", "l"); a.jr("project_d32_ready")
    a.label("project_d32_sat")
    a.ld_r_n("a", 1); a.ld_abs_a(D32_HIGH); a.ld_r_n("b", 0xFF)
    a.label("project_d32_ready")
    a.ld_r_r("a", "b"); a.ld_abs_a(D32_LOW)
    # Select the component perpendicular to the wall exactly as the former
    # arithmetic path did.  The table's 512-byte slices are ordered by
    # component*18 + (correction-110).
    a.ld_a_abs(DDA_AXIS); a.or_r("a"); a.jr("project_component_y", "nz")
    a.ld_a_abs(DDA_ABS_X); a.jr("project_component_ready")
    a.label("project_component_y"); a.ld_a_abs(DDA_ABS_Y)
    a.label("project_component_ready")
    a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.ld_r_r("d", "h"); a.ld_r_r("e", "l")
    for _ in range(4): a.add_hl_rr("hl")
    a.add_hl_rr("de"); a.add_hl_rr("de")
    a.ld_a_abs(DDA_CORRECTION); a.sub_n(PROJECTION_LUT_CORRECTION_MIN); a.ld_abs_a(LUT_CORRECTION)
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.add_hl_rr("de")
    a.ld_r_r("a", "l"); a.ld_abs_a(LUT_SLICE_LOW)
    # Bank = 2 + slice/32.  The selected bank is restored to bank 1 before
    # any conventional engine data in $4000-$7FFF is touched again.
    for _ in range(5): a.cb("srl", "h"); a.cb("rr", "l")
    a.ld_r_r("a", "l"); a.add_a_n(PROJECTION_LUT_BASE_BANK); a.ld_abs_a(0x2000)
    # Address = $4000 + (slice&31)*512 + D32.
    a.ld_a_abs(LUT_SLICE_LOW); a.and_n(0x1F); a.add_a_r("a"); a.or_n(0x40); a.ld_r_r("h", "a")
    a.ld_a_abs(D32_HIGH); a.or_r("h"); a.ld_r_r("h", "a")
    a.ld_a_abs(D32_LOW); a.ld_r_r("l", "a"); a.ld_a_hl(); a.ld_abs_a(TOP_RESULT)
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)

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

    a.label("cast_indexed")  # Public self-contained probe entry.
    a.call("prepare_frame_boundaries"); a.jp("cast_indexed_prepared")
    a.label("cast_indexed_prepared")  # CAST_INDEX selects the ray
    a.ld_a_abs(CAST_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "ray_offsets_q10"); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(ANGLE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.add_hl_rr("hl"); a.add_hl_rr("hl"); a.add_hl_rr("de")
    a.ld_r_r("a", "h"); a.and_n(0x03); a.ld_r_r("h", "a"); store_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_a_abs(CAST_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "ray_corrections"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(DDA_CORRECTION)
    a.call("cast_one_v2"); a.ret()

    a.label("cast_physical_indexed")  # Public self-contained probe entry.
    a.call("prepare_frame_boundaries"); a.jp("cast_physical_indexed_prepared")
    a.label("cast_physical_indexed_prepared")  # PIXEL_INDEX selects one of 160 columns
    a.ld_a_abs(PIXEL_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("a", 0); a.adc_a_n(0); a.ld_r_r("d", "a")
    a.ld_rr_label("hl", "physical_offsets_q10"); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(ANGLE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.add_hl_rr("hl"); a.add_hl_rr("hl"); a.add_hl_rr("de")
    a.ld_r_r("a", "h"); a.and_n(0x03); a.ld_r_r("h", "a"); store_hl_abs(a, DDA_ANGLE_L, DDA_ANGLE_H)
    a.ld_a_abs(PIXEL_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "physical_corrections"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(DDA_CORRECTION)
    a.call("cast_one_v2"); a.ret()

    a.label("cast_and_store")  # input A ray index
    a.ld_abs_a(CAST_INDEX)
    a.ld_a_abs(ADAPTIVE_CASTS); a.inc_r("a"); a.ld_abs_a(ADAPTIVE_CASTS)
    a.call("cast_indexed_prepared")
    a.ld_a_abs(CAST_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_abs(TOP_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_STYLES); a.add_hl_rr("de"); a.ld_a_abs(STYLE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ld_a_abs(FACE_RESULT); a.ld_hl_a()
    a.ld_rr_nn("hl", RAY_ALONG); a.add_hl_rr("de"); a.ld_a_abs(ALONG_RESULT); a.ld_hl_a(); a.ret()

    a.label("cast_physical_and_store")
    a.ld_a_abs(EDGE_RECASTS); a.inc_r("a"); a.ld_abs_a(EDGE_RECASTS)
    a.call("cast_physical_indexed_prepared")
    a.ld_a_abs(PIXEL_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    for address, result in (
        (PIXEL_TOPS, TOP_RESULT), (PIXEL_STYLES, STYLE_RESULT),
        (PIXEL_KEYS, FACE_RESULT), (PIXEL_ALONG, ALONG_RESULT),
    ):
        a.ld_rr_nn("hl", address); a.add_hl_rr("de"); a.ld_a_abs(result); a.ld_hl_a()
    a.ret()

    a.label("cast_all")
    a.call("prepare_frame_boundaries")
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
    a.ld_a_abs(ADAPTIVE_INDEX); a.add_a_n(2); a.ld_abs_a(ADAPTIVE_INDEX); a.cp_n(79); a.jp("adaptive_fill_loop", "c")
    a.call("build_pixel_descriptors"); a.call("decorate_pixel_styles"); a.ret()

    a.label("build_pixel_descriptors")
    a.xor_r("a"); a.ld_abs_a(PAIR_INDEX); a.ld_abs_a(EDGE_RECASTS)
    a.label("pixel_pair_loop")
    # Current pair-centre top.
    a.ld_a_abs(PAIR_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(TEMP_TOP)
    # Left physical top = round((3*current + previous) / 4).
    a.ld_a_abs(PAIR_INDEX); a.or_r("a"); a.jr("pixel_left_has_previous", "nz")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("b", "a"); a.jr("pixel_left_previous_ready")
    a.label("pixel_left_has_previous")
    a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.label("pixel_left_previous_ready")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("c", "a"); a.add_a_r("c"); a.add_a_r("c"); a.add_a_r("b"); a.add_a_n(2); a.cb("srl", "a"); a.cb("srl", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(PAIR_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ld_hl_a()
    # Right physical top = round((3*current + following) / 4).
    a.ld_a_abs(PAIR_INDEX); a.cp_n(RAYS - 1); a.jr("pixel_right_has_following", "nz")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("b", "a"); a.jr("pixel_right_following_ready")
    a.label("pixel_right_has_following")
    a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", RAY_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.label("pixel_right_following_ready")
    a.ld_a_abs(TEMP_TOP); a.ld_r_r("c", "a"); a.add_a_r("c"); a.add_a_r("c"); a.add_a_r("b"); a.add_a_n(2); a.cb("srl", "a"); a.cb("srl", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(PAIR_INDEX); a.add_a_r("a"); a.inc_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ld_hl_a()
    # Geometry style, key and along-cell identity are initially duplicated.
    for source, destination in (
        (RAY_STYLES, PIXEL_STYLES), (RAY_KEYS, PIXEL_KEYS),
        (RAY_ALONG, PIXEL_ALONG),
    ):
        a.ld_a_abs(PAIR_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", source); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
        a.ld_a_abs(PAIR_INDEX); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", destination); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ldi_hl_a(); a.ld_hl_a()
    a.ld_a_abs(PAIR_INDEX); a.inc_r("a"); a.ld_abs_a(PAIR_INDEX); a.cp_n(RAYS); a.jp("pixel_pair_loop", "c")

    # Recast only the two physical pixels adjacent to a pair-level face break.
    a.xor_r("a"); a.ld_abs_a(EDGE_INDEX)
    a.label("edge_recast_loop")
    a.ld_a_abs(EDGE_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", RAY_KEYS); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_r_r("b", "a"); a.ld_a_hl(); a.cp_r("b"); a.jr("edge_recast_skip", "z")
    a.ld_a_abs(EDGE_INDEX); a.add_a_r("a"); a.inc_r("a"); a.ld_abs_a(PIXEL_INDEX); a.call("cast_physical_and_store")
    a.ld_a_abs(EDGE_INDEX); a.add_a_r("a"); a.add_a_n(2); a.ld_abs_a(PIXEL_INDEX); a.call("cast_physical_and_store")
    a.label("edge_recast_skip")
    a.ld_a_abs(EDGE_INDEX); a.inc_r("a"); a.ld_abs_a(EDGE_INDEX); a.cp_n(RAYS - 1); a.jp("edge_recast_loop", "c"); a.ret()

    a.label("decorate_pixel_styles")
    a.xor_r("a"); a.ld_abs_a(EVENT_COUNT); a.ld_r_n("a", 1); a.ld_abs_a(EVENT_INDEX)
    a.label("event_boundary_loop")
    # Compare adjacent face keys.
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(EVENT_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jr("event_same_face", "z")
    # Face break: darken one physical pixel on each side when >=16 px tall.
    for delta in (-1, 0):
        a.ld_a_abs(EVENT_INDEX)
        if delta < 0: a.dec_r("a")
        a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(41); skip = f"event_face_lod_skip_{delta + 1}"; a.jr(skip, "nc")
        a.ld_a_abs(EVENT_INDEX)
        if delta < 0: a.dec_r("a")
        a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", CREASE_STYLE); a.ld_hl_a(); a.label(skip)
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT); a.jr("event_boundary_done")
    a.label("event_same_face")
    # A change in along-face cell coordinate is a world-anchored panel seam.
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(EVENT_INDEX); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", PIXEL_ALONG); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_r("b"); a.jr("event_boundary_done", "z")
    a.ld_a_abs(EVENT_INDEX); a.ld_r_r("e", "a"); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(41); a.jr("event_boundary_done", "nc")
    a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.and_n(0x60); a.cp_n(0x40); a.ld_r_n("a", CREASE_STYLE); a.jr("event_cell_style_ready", "nz"); a.ld_r_n("a", TECH_RIB_STYLE)
    a.label("event_cell_style_ready"); a.ld_r_r("b", "a"); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_r("a", "b"); a.ld_hl_a()
    a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT)
    a.label("event_boundary_done")
    a.ld_a_abs(EVENT_INDEX); a.inc_r("a"); a.ld_abs_a(EVENT_INDEX); a.cp_n(PHYSICAL_COLUMNS); a.jp("event_boundary_loop", "c")

    # Derive door frames and a run-centred spine from contiguous material-3
    # pixels. This is independent of screen-tile phase.
    a.xor_r("a"); a.ld_abs_a(EVENT_INDEX)
    a.label("door_scan_loop")
    a.ld_a_abs(EVENT_INDEX); a.cp_n(PHYSICAL_COLUMNS); a.ret("nc")
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.and_n(0x60); a.cp_n(0x60); a.jp("door_scan_advance", "nz")
    a.ld_a_abs(EVENT_INDEX); a.ld_abs_a(DOOR_RUN_START)
    a.label("door_find_end")
    a.ld_a_abs(EVENT_INDEX); a.inc_r("a"); a.ld_abs_a(EVENT_INDEX); a.cp_n(PHYSICAL_COLUMNS); a.jr("door_end_ready", "nc")
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_a_hl(); a.and_n(0x60); a.cp_n(0x60); a.jr("door_find_end", "z")
    a.label("door_end_ready")
    a.ld_a_abs(EVENT_INDEX); a.ld_abs_a(DOOR_RUN_END)
    # Frame at run start.
    a.ld_a_abs(DOOR_RUN_START); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(41); a.jr("door_start_lod_done", "nc"); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", CREASE_STYLE); a.ld_hl_a()
    a.label("door_start_lod_done")
    # Frame at inclusive run end.
    a.ld_a_abs(DOOR_RUN_END); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(41); a.jr("door_end_lod_done", "nc"); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", CREASE_STYLE); a.ld_hl_a()
    a.label("door_end_lod_done")
    # Require a three-pixel run before adding its centre spine.
    a.ld_a_abs(DOOR_RUN_END); a.ld_r_r("b", "a"); a.ld_a_abs(DOOR_RUN_START); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.sub_r("c"); a.cp_n(3); a.jr("door_event_count", "c")
    a.dec_r("a"); a.cb("srl", "a"); a.add_a_r("c"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de"); a.ld_a_hl(); a.cp_n(33); a.jr("door_event_count", "nc")
    a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("a", DOOR_SPINE_STYLE); a.ldi_hl_a(); a.ld_hl_a()
    a.label("door_event_count"); a.ld_a_abs(EVENT_COUNT); a.inc_r("a"); a.ld_abs_a(EVENT_COUNT); a.jp("door_scan_loop")
    a.label("door_scan_advance"); a.ld_a_abs(EVENT_INDEX); a.inc_r("a"); a.ld_abs_a(EVENT_INDEX); a.jp("door_scan_loop")

def emit_renderer(a: Assembler) -> None:
    # These two fixed-size kernels sit in the hottest compositor path.  The
    # looped versions spent roughly one quarter of their time decrementing a
    # counter and branching.  Unrolling costs well under 200 ROM bytes and
    # removes about one thousand cycles from every generated boundary tile.
    a.label("copy_16")  # HL source, DE destination
    for _ in range(16):
        a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ret()

    a.label("or_16")  # positioned HL source, DE destination
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
    # state * 128 + physical pixel * 16.
    a.ld_a_abs(STRIP_STATE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(7): a.add_hl_rr("hl")
    a.ld_a_abs(STRIP_PAIR); a.cb("swap", "a"); a.and_n(0xF0); a.ld_r_r("c", "a"); a.ld_r_n("b", 0); a.add_hl_rr("bc")
    a.add_hl_rr("de"); a.ret()

    a.label("get_pair_microstrip_ptr")
    a.ld_a_abs(STRIP_STYLE); a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "pair_microstrip_style_bases"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    # state * 64 + pair * 16.
    a.ld_a_abs(STRIP_STATE); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(6): a.add_hl_rr("hl")
    a.ld_a_abs(STRIP_PAIR); a.cb("srl", "a"); a.cb("swap", "a"); a.and_n(0xF0); a.ld_r_r("c", "a"); a.ld_r_n("b", 0); a.add_hl_rr("bc")
    a.add_hl_rr("de"); a.ret()

    a.label("build_tile_signature")
    # Hash y0, the already-produced dark mask, and the eight source tops in
    # place.  The earlier prototype copied all ten bytes into WRAM and then
    # read them back; direct hashing removes that entire memory pass.
    a.ld_r_n("c", 0)
    for address in (TILE_Y0, DARK_MASK):
        a.ld_r_r("a", "c"); a.rlca(); a.ld_r_r("c", "a")
        a.ld_a_abs(address); a.xor_r("c"); a.ld_r_r("c", "a")
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.ld_r_n("b", 8)
    a.label("signature_hash_loop")
    a.ld_r_r("a", "c"); a.rlca(); a.ld_r_r("c", "a"); a.ldi_a_hl(); a.xor_r("c"); a.ld_r_r("c", "a")
    a.dec_r("b"); a.jr("signature_hash_loop", "nz")
    a.ld_r_r("a", "c"); a.ld_abs_a(SIGNATURE_HASH); a.ret()

    a.label("find_atlas_tile")
    a.ld_a_abs(SIGNATURE_HASH); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "tile_atlas_bucket_start"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_rr_label("hl", "tile_atlas_bucket_count"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(ATLAS_ENTRY_COUNT); a.or_r("a"); a.jr("atlas_miss", "z")
    # HL = tile_atlas_entries + start * 11.
    a.ld_r_r("e", "b"); a.ld_r_n("d", 0); a.ld_r_r("h", "d"); a.ld_r_r("l", "e")
    for _ in range(3): a.add_hl_rr("hl")
    for _ in range(3): a.add_hl_rr("de")
    a.ld_rr_label("de", "tile_atlas_entries"); a.add_hl_rr("de")
    store_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H)
    a.label("atlas_candidate_loop")
    load_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H)
    # Reject on the two cheapest fields before touching the eight-column
    # source array.  Exact top comparison keeps hash collisions harmless.
    a.ld_a_abs(TILE_Y0); a.cp_r("(hl)"); a.jr("atlas_candidate_mismatch", "nz"); a.inc_rr("hl")
    a.ld_a_abs(DARK_MASK); a.cp_r("(hl)"); a.jr("atlas_candidate_mismatch", "nz"); a.inc_rr("hl")
    a.push("hl"); load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.ld_r_n("b", 8)
    a.label("atlas_compare_loop")
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.cp_r("(hl)"); a.jr("atlas_candidate_mismatch", "nz")
    a.inc_rr("hl"); a.dec_r("b"); a.jr("atlas_compare_loop", "nz")
    a.ld_a_hl(); a.ret()
    a.label("atlas_candidate_mismatch")
    load_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H); a.ld_rr_nn("de", TILE_ATLAS_ENTRY_BYTES); a.add_hl_rr("de"); store_hl_abs(a, ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H)
    a.ld_a_abs(ATLAS_ENTRY_COUNT); a.dec_r("a"); a.ld_abs_a(ATLAS_ENTRY_COUNT); a.jr("atlas_candidate_loop", "nz")
    a.label("atlas_miss"); a.xor_r("a"); a.ret()

    a.label("compose_dynamic_tile")
    load_hl_abs(a, DYN_PTR_L, DYN_PTR_H); store_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H)
    a.xor_r("a"); a.ld_abs_a(STRIP_PAIR)
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.push("hl")
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl")
    a.label("compose_pair_loop")
    a.ldi_a_hl(); a.ld_abs_a(TEMP_TOP)
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.and_n(1); a.ld_abs_a(STRIP_STYLE)
    a.xor_r("a"); a.ld_abs_a(STRIP_KIND)
    # Keep the original two-pixel fast path whenever both synthesized pixels
    # have the same silhouette and visual light/dark style.
    a.ld_a_abs(STRIP_PAIR); a.and_n(1); a.jr("compose_strip_ready", "nz")
    a.ld_a_hl(); a.ld_abs_a(SECOND_TOP); a.ld_r_r("b", "a"); a.ld_a_abs(TEMP_TOP); a.cp_r("b"); a.jr("compose_strip_ready", "nz")
    a.ld_a_mem_rr("de"); a.and_n(1); a.ld_abs_a(SECOND_STYLE); a.ld_r_r("b", "a"); a.ld_a_abs(STRIP_STYLE); a.cp_r("b"); a.jr("compose_strip_ready", "nz")
    a.inc_rr("hl"); a.inc_rr("de"); a.ld_r_n("a", 1); a.ld_abs_a(STRIP_KIND)
    a.label("compose_strip_ready")
    a.push("hl"); a.push("de")
    a.ld_a_abs(TEMP_TOP); a.call("compute_strip_state"); a.ld_abs_a(STRIP_STATE)
    a.ld_a_abs(STRIP_KIND); a.or_r("a"); a.jr("compose_get_pixel_strip", "z"); a.call("get_pair_microstrip_ptr"); a.jr("compose_got_strip")
    a.label("compose_get_pixel_strip"); a.call("get_microstrip_ptr")
    a.label("compose_got_strip")
    a.ld_a_abs(STRIP_PAIR); a.or_r("a"); a.jr("compose_or_strip", "nz")
    a.push("hl"); load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.call("copy_16")
    a.ld_r_r("a", "e"); a.ld_abs_a(DYN_PTR_L); a.ld_r_r("a", "d"); a.ld_abs_a(DYN_PTR_H); a.jr("compose_strip_done")
    a.label("compose_or_strip")
    a.push("hl"); load_hl_abs(a, COMPOSE_DST_L, COMPOSE_DST_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl"); a.call("or_16")
    a.label("compose_strip_done")
    a.pop("de"); a.pop("hl")
    a.ld_a_abs(STRIP_KIND); a.inc_r("a"); a.ld_r_r("b", "a"); a.ld_a_abs(STRIP_PAIR); a.add_a_r("b"); a.ld_abs_a(STRIP_PAIR); a.cp_n(8); a.jp("compose_pair_loop", "nz"); a.ret()

    a.label("scan_column")
    a.ld_r_n("a", 0xFF); a.ld_abs_a(MIN_TOP); a.xor_r("a"); a.ld_abs_a(MAX_TOP); a.ld_abs_a(STYLE_DIFF); a.ld_abs_a(DARK_MASK)
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.push("hl")
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_r_r("d", "h"); a.ld_r_r("e", "l"); a.pop("hl")
    a.ld_a_mem_rr("de"); a.ld_abs_a(FIRST_STYLE); a.ld_r_n("a", 8); a.ld_abs_a(CLASSIFY_COUNT)
    a.label("scan_column_loop")
    a.ldi_a_hl(); a.ld_r_r("b", "a")
    a.ld_a_abs(MIN_TOP); a.cp_r("b"); a.jr("scan_min_keep", "c"); a.jr("scan_min_keep", "z"); a.ld_r_r("a", "b"); a.ld_abs_a(MIN_TOP)
    a.label("scan_min_keep")
    a.ld_a_abs(MAX_TOP); a.cp_r("b"); a.jr("scan_max_keep", "nc"); a.ld_r_r("a", "b"); a.ld_abs_a(MAX_TOP)
    a.label("scan_max_keep")
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.ld_r_r("b", "a")
    # All light base styles resolve to colour 2 and all odd render styles to
    # colour 3. Build the exact eight-pixel dark mask for the static seam atlas.
    a.ld_a_abs(DARK_MASK); a.add_a_r("a"); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.and_n(1); a.or_r("c"); a.ld_abs_a(DARK_MASK)
    a.ld_a_abs(CLASSIFY_COUNT); a.dec_r("a"); a.ld_abs_a(CLASSIFY_COUNT); a.jr("scan_column_loop", "nz"); a.ret()

    a.label("classify_row")
    a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.ld_r_r("b", "a")
    a.ld_a_abs(MIN_TOP); a.ld_r_r("c", "a"); a.ld_r_r("a", "b"); a.cp_r("c"); a.jr("row_ceiling", "c")
    a.ld_r_n("a", 96); a.sub_r("c"); a.ld_r_r("b", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("b"); a.jr("row_floor", "nc")
    a.ld_a_abs(MAX_TOP); a.ld_r_r("c", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("c"); a.jr("row_dynamic", "c")
    a.ld_r_n("a", 96); a.sub_r("c"); a.ld_r_r("c", "a"); a.ld_a_abs(TILE_Y0); a.add_a_n(7); a.cp_r("c"); a.jr("row_dynamic", "nc")
    a.ld_a_abs(DARK_MASK); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "seam_tile_lookup"); a.add_hl_rr("de"); a.ld_a_hl(); a.or_r("a"); a.jr("row_dynamic", "z")
    a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_ceiling"); a.ld_r_n("a", CEILING_TILE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_floor"); a.ld_r_n("a", FLOOR_TILE); a.ld_abs_a(TILE_ID_RESULT); a.xor_r("a"); a.ld_abs_a(DYNAMIC_FLAG); a.ret()
    a.label("row_dynamic"); a.ld_r_n("a", 1); a.ld_abs_a(DYNAMIC_FLAG); a.ret()

    a.label("render_view")
    a.xor_r("a"); a.ld_abs_a(DYN_COUNT); a.ld_abs_a(DYN_OVERFLOW)
    a.ld_rr_nn("hl", DYNAMIC_TILES); store_hl_abs(a, DYN_PTR_L, DYN_PTR_H)
    a.ld_rr_nn("hl", VIEW_MAP); store_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H)
    a.ld_rr_nn("hl", PIXEL_TOPS); store_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H)
    a.ld_rr_nn("hl", PIXEL_STYLES); store_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H)
    a.ld_r_n("a", 20); a.ld_abs_a(COLUMN_COUNT)
    a.label("render_column_loop")
    a.call("scan_column")
    a.xor_r("a"); a.ld_abs_a(TILE_ROW); a.ld_abs_a(TILE_Y0)
    load_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H); store_hl_abs(a, MAP_PTR_L, MAP_PTR_H)
    a.ld_r_n("a", 12); a.ld_abs_a(ROW_RENDER_COUNT)
    a.label("render_row_loop")
    a.call("classify_row")
    a.ld_a_abs(DYNAMIC_FLAG); a.or_r("a"); a.jr("render_static_tile", "z")
    a.call("build_tile_signature"); a.call("find_atlas_tile"); a.or_r("a"); a.jr("render_dynamic_miss", "z")
    a.ld_abs_a(TILE_ID_RESULT); a.jr("render_write_tile")
    a.label("render_dynamic_miss")
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
    # Advance eight physical-pixel descriptors and one BG-map column.
    load_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H); a.ld_rr_nn("de", 8); a.add_hl_rr("de"); store_hl_abs(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H)
    load_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H); a.ld_rr_nn("de", 8); a.add_hl_rr("de"); store_hl_abs(a, SCAN_STYLE_PTR_L, SCAN_STYLE_PTR_H)
    load_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H); a.inc_rr("hl"); store_hl_abs(a, COLUMN_MAP_L, COLUMN_MAP_H)
    a.ld_a_abs(COLUMN_COUNT); a.dec_r("a"); a.ld_abs_a(COLUMN_COUNT); a.jp("render_column_loop", "nz"); a.ret()

def build_engine() -> tuple[bytes, Assembler, dict[str, object]]:
    tables = make_tables()
    a = Assembler(origin=0x0150, optimize_high_page=True)
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
    v1.emit_copy_routine(a); v1.emit_wait_vblank(a); emit_palette_init(a)
    emit_vram_init(a); v1.emit_oam_init(a); v1.emit_audio(a); emit_dma(a); v1.emit_joypad(a)
    # Legacy quarter-step helpers are retained only for the two-step door interaction.
    v1.emit_ray_helpers(a)
    emit_mul_u8(a)
    emit_dda(a); emit_projection_and_casting(a); emit_renderer(a)
    v1.emit_movement(a); v1.emit_input_update(a)

    # Data section.
    a.align(16, text="data alignment")
    a.label("map_data"); a.bytes(make_map(), "16x16 world map")
    a.label("ui_tiles"); a.bytes(make_ui_tiles(), "HUD / utility tiles 240-255")
    a.label("weapon_tiles"); a.bytes(make_weapon_tiles(), "32x32 weapon tiles 240-255")
    a.label("static_view_tiles"); a.bytes(make_static_view_tiles(), "ceiling/floor plus phase-free seam atlas")
    a.label("tile_atlas_tiles"); a.bytes(TILE_ATLAS_TILES, "exact boundary-tile atlas mirrored in both VRAM banks")
    a.label("tilemap_data"); a.bytes(make_tilemap(), "base 32x32 tile-number map")
    a.label("attrmap_page0"); a.bytes(make_attrmap(0), "page 0 CGB attributes")
    a.label("attrmap_page1"); a.bytes(make_attrmap(1), "page 1 CGB attributes")

    wall_light, wall_dark = rgb15(26, 17, 8), rgb15(16, 9, 5)
    bg_palette_values = [
        rgb15(2, 4, 10), rgb15(7, 8, 11), wall_light, wall_dark,
        rgb15(1, 2, 3), rgb15(7, 8, 9), rgb15(29, 27, 20), rgb15(31, 5, 4),
        rgb15(3, 5, 11), rgb15(8, 8, 10), wall_light, wall_dark,
        rgb15(4, 6, 12), rgb15(9, 8, 9), wall_light, wall_dark,
        rgb15(5, 7, 13), rgb15(10, 8, 8), wall_light, wall_dark,
        rgb15(6, 8, 14), rgb15(11, 8, 7), wall_light, wall_dark,
        rgb15(7, 9, 15), rgb15(12, 8, 6), wall_light, wall_dark,
        rgb15(7, 9, 15), rgb15(12, 8, 6), wall_light, wall_dark,
    ]
    obj_palette_values = [
        rgb15(0, 0, 0), rgb15(6, 7, 9), rgb15(16, 18, 20), rgb15(30, 29, 24),
        rgb15(0, 0, 0), rgb15(31, 10, 0), rgb15(31, 24, 1), rgb15(31, 31, 25),
    ]
    a.label("bg_palettes"); a.bytes(words_le(bg_palette_values), "eight CGB BG palettes")
    a.label("obj_palettes"); a.bytes(words_le(obj_palette_values), "two CGB OBJ palettes")

    a.align(256, text="legacy movement table alignment")
    for name in ("step_dx", "step_dy", "move_dx", "move_dy"):
        a.label(name); a.bytes(tables[name], name)
    a.align(1024, text="1024-direction ray table alignment")
    a.label("ray_vectors_packed"); a.bytes(tables["ray_packed"], "abs dx, abs dy, step x, step y")
    a.label("ray_offsets_q10"); a.bytes(tables["ray_offsets"], "80 signed 10-bit camera-plane offsets")
    a.label("ray_corrections"); a.bytes(tables["ray_corrections"], "80 cosine correction factors")
    a.label("physical_offsets_q10"); a.bytes(tables["physical_offsets"], "160 signed physical-pixel offsets")
    a.label("physical_corrections"); a.bytes(tables["physical_corrections"], "160 physical-pixel cosine corrections")
    a.label("seam_tile_lookup"); a.bytes(make_seam_tile_lookup(), "dark-mask to static seam tile lookup")
    a.label("tile_atlas_bucket_start"); a.bytes(TILE_ATLAS_BUCKET_START, "signature-hash bucket starts")
    a.label("tile_atlas_bucket_count"); a.bytes(TILE_ATLAS_BUCKET_COUNT, "signature-hash bucket counts")
    a.label("tile_atlas_entries"); a.bytes(TILE_ATLAS_ENTRIES, "ten exact signature bytes plus tile ID")
    microstrips = make_microstrips()
    style_block = MICRO_STATE_COUNT * 8 * 16
    a.label("microstrip_style_bases")
    for style in range(2): a.dw_label(f"microstrips_style_{style}")
    for style in range(2):
        a.label(f"microstrips_style_{style}")
        a.bytes(microstrips[style * style_block:(style + 1) * style_block], f"style {style} edge microstrips")
    pair_microstrips = make_pair_microstrips()
    pair_style_block = MICRO_STATE_COUNT * 4 * 16
    a.label("pair_microstrip_style_bases")
    for style in range(2): a.dw_label(f"pair_microstrips_style_{style}")
    for style in range(2):
        a.label(f"pair_microstrips_style_{style}")
        a.bytes(pair_microstrips[style * pair_style_block:(style + 1) * pair_style_block], f"style {style} pair microstrips")

    code = a.resolve()
    metadata = {
        "engine_origin": a.origin,
        "engine_end": a.origin + len(code),
        "engine_size": len(code),
        "renderer": "Q5 signed-error DDA + hybrid 160-column face-event compositor",
        "framebuffer_bytes": 0,
        "dynamic_tile_capacity": DYNAMIC_TILE_CAPACITY,
        "dynamic_tile_buffer_bytes": DYNAMIC_TILE_CAPACITY * 16,
        "view_map_buffer_bytes": 384,
        "maximum_commit_bytes": DYNAMIC_TILE_CAPACITY * 16 + 384,
        "maximum_commit_blocks": DYNAMIC_TILE_CAPACITY + 24,
        "rays": RAYS,
        "physical_columns": PHYSICAL_COLUMNS,
        "ray_width_pixels": RAY_WIDTH,
        "adaptive_anchor_casts": 41,
        "adaptive_validation": "same axis/material/plane, adjacent face cells, and <=2-pixel anchor slope",
        "ray_direction_table_entries": 1024,
        "packed_direction_record_bytes": 4,
        "shared_frame_boundary_fractions": True,
        "ray_vector_scale": RAY_VECTOR_SCALE,
        "projection_fractional_bits": 5,
        "selective_edge_recasts": True,
        "viewport": list(VIEWPORT),
        "map": [16, 16],
        "wall_styles": STYLE_COUNT,
        "render_styles": RENDER_STYLE_COUNT,
        "wall_material_names": list(WALL_MATERIAL_NAMES),
        "wall_pattern_resolution_pairs": [1, 1],
        "full_width_contrast_bands": 0,
        "world_anchored_face_events": True,
        "palette_depth_ladder_enabled": False,
        "palette_depth_ladder_rejection": "ROM playtest exposed screen-space horizontal banding",
        "static_view_tiles": STATIC_VIEW_TILES,
        "microstrip_states": MICRO_STATE_COUNT,
        "microstrip_rom_bytes": len(microstrips) + len(pair_microstrips),
        "hram_hot_state_bytes": HRAM_BYTES_USED,
        "hram_hot_state_range": [min(HRAM_LAYOUT.values()), max(HRAM_LAYOUT.values())],
        "projection_lut_bytes": PROJECTION_LUT_BYTES,
        "projection_lut_banks": PROJECTION_LUT_BYTES // 0x4000,
        "projection_lut_base_bank": PROJECTION_LUT_BASE_BANK,
        "projection_lut_exact": True,
        "product_lut_bytes": PRODUCT_LUT_BYTES,
        "product_lut_banks": PRODUCT_LUT_BYTES // 0x4000,
        "product_lut_base_bank": PRODUCT_LUT_BASE_BANK,
        "product_lut_exact": True,
        "rom_banks": ROM_BANKS,
        "cartridge_type": "MBC5",
    }
    return code, a, metadata


def make_rom() -> tuple[bytes, Assembler, dict[str, object]]:
    engine, assembler, metadata = build_engine()
    if 0x0150 + len(engine) > 0x8000:
        raise RuntimeError(f"resident engine does not fit banks 0/1: end={0x0150 + len(engine):04X}")
    rom = bytearray([0xFF] * ROM_BYTES)
    rom[0x0100:0x0104] = bytes((0x00, 0xC3, 0x50, 0x01))
    rom[0x0104:0x0134] = NINTENDO_LOGO
    rom[0x0134:0x0143] = b"LUPINE3D".ljust(15, b"\0")
    rom[0x0143] = 0xC0; rom[0x0144:0x0146] = b"00"; rom[0x0146] = 0
    rom[0x0147] = 0x19; rom[0x0148] = 0x07; rom[0x0149] = 0; rom[0x014A] = 1; rom[0x014B] = 0x33; rom[0x014C] = 4
    rom[0x0150:0x0150 + len(engine)] = engine
    projection_lut = make_projection_top_lut()
    lut_start = PROJECTION_LUT_BASE_BANK * 0x4000
    rom[lut_start:lut_start + len(projection_lut)] = projection_lut
    product_lut = make_product_lut()
    product_start = PRODUCT_LUT_BASE_BANK * 0x4000
    rom[product_start:product_start + len(product_lut)] = product_lut
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
