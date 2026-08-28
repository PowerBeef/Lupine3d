"""Hardware layout, generated ABI, assets, and engine constants."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from sm83 import Assembler  # noqa: E402
import build_rom_v1 as v1  # noqa: E402

BUILD = ROOT / "build"
BUILD.mkdir(parents=True, exist_ok=True)
ASSETS = ROOT / "assets"
TILE_ATLAS_ASSETS = Path(os.environ.get("LUPINE3D_TILE_ATLAS_DIR", ASSETS))

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
# VBlank input sampler state. The ISR only touches these bytes and BUTTONS;
# gameplay pose remains exclusively owned by the main loop.
INPUT_LAST_RAW = _hram("INPUT_LAST_RAW")
INPUT_EDGE_LATCH = _hram("INPUT_EDGE_LATCH")
INPUT_SAMPLE_COUNT = _hram("INPUT_SAMPLE_COUNT")
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
RAY_DIRECTION_BITS = 10
RAY_DIRECTION_COUNT = 1 << RAY_DIRECTION_BITS
RAY_PLAYER_SHIFT = RAY_DIRECTION_BITS - 8
RAY_DIRECTION_HIGH_MASK = (RAY_DIRECTION_COUNT >> 8) - 1
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

TILE_ATLAS_TILES = (TILE_ATLAS_ASSETS / "tile_atlas_tiles.bin").read_bytes()
TILE_ATLAS_BUCKET_START = (TILE_ATLAS_ASSETS / "tile_atlas_bucket_start.bin").read_bytes()
TILE_ATLAS_BUCKET_COUNT = (TILE_ATLAS_ASSETS / "tile_atlas_bucket_count.bin").read_bytes()
TILE_ATLAS_ENTRIES = (TILE_ATLAS_ASSETS / "tile_atlas_entries.bin").read_bytes()
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
