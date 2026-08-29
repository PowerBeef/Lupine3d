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
from lupine3d_v4 import levels as level_codec  # noqa: E402

BUILD = ROOT / "build"
BUILD.mkdir(parents=True, exist_ok=True)
ASSETS = ROOT / "assets"
TILE_ATLAS_ASSETS = Path(os.environ.get("LUPINE3D_TILE_ATLAS_DIR", ASSETS))
ENTITY_ATLAS_ASSETS = Path(os.environ.get("LUPINE3D_ENTITY_ATLAS_DIR", ASSETS / "entity_atlas_80"))
ACTIVE_LEVEL = level_codec.active_level(ROOT)

# Hardware registers (LDH offsets).
P1 = v1.P1
NR10, NR11, NR12, NR13, NR14 = v1.NR10, v1.NR11, v1.NR12, v1.NR13, v1.NR14
NR50, NR51, NR52 = v1.NR50, v1.NR51, v1.NR52
LCDC, STAT, SCY, SCX, LY, LYC = v1.LCDC, v1.STAT, v1.SCY, v1.SCX, v1.LY, 0x45
OAM_DMA = 0x46
KEY1, VBK = v1.KEY1, v1.VBK
HDMA1, HDMA2, HDMA3, HDMA4, HDMA5 = v1.HDMA1, v1.HDMA2, v1.HDMA3, v1.HDMA4, v1.HDMA5
BGPI, BGPD, OBPI, OBPD, SVBK = v1.BGPI, v1.BGPD, v1.OBPI, v1.OBPD, v1.SVBK

# WRAM0 frame-composition buffers.
DYNAMIC_TILES = 0xC000          # 96 * 16 = 1536 bytes
VIEW_MAP = 0xC600               # 12 rows * 32 bytes = 384 bytes
DYNAMIC_TILE_CAPACITY = 96
OAM_SHADOW = 0xC800             # atomic 40-entry OAM publication source
OAM_BYTES = 160
ENTITY_OAM_FIRST = 18
ENTITY_OAM_COUNT = 22

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
BANKED_ATLAS_ROM_BANK = PRODUCT_LUT_BASE_BANK + PRODUCT_LUT_BYTES // 0x4000
BANKED_ATLAS_ROM_ADDRESS = 0x4000
SEGMENT_TABLE_ROM_BANK = BANKED_ATLAS_ROM_BANK + 1
SEGMENT_TABLE_ROM_ADDRESS = 0x4000

# The active level remains a compact 16x16 WRAM grid. Additional authored
# levels and their graphics stay banked in ROM until a level transition.
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

# Authoritative two-pixel wall occlusion data. Depth is corrected
# perpendicular distance in Q5 tiles, saturated to 255; segment is a
# build-time ID for one contiguous exposed surface.
RAY_DEPTH = 0xD680
RAY_SEGMENT = 0xD6D0

# Living World state and scratch area.
VRAM_PROFILE = 0xD720
WORLD_MODE = 0xD721             # 0 = empty-world oracle, 1 = Living World
SENTINEL_XL = 0xD722
SENTINEL_XH = 0xD723
SENTINEL_YL = 0xD724
SENTINEL_YH = 0xD725
SENTINEL_STATE = 0xD726
SENTINEL_HEALTH = 0xD727
SENTINEL_AI_STAMP = 0xD728
SENTINEL_AI_PHASE = 0xD729
SENTINEL_ANIM = 0xD72A
SENTINEL_COOLDOWN = 0xD72B
SENTINEL_VISIBLE = 0xD72C
SENTINEL_SCREEN_X = 0xD72D
SENTINEL_DEPTH = 0xD72E
SENTINEL_LOD = 0xD72F
SENTINEL_OAM_USED = 0xD730
PLAYER_HEALTH = 0xD731
PICKUP_ACTIVE = 0xD732
PICKUP_COLLECTED = 0xD733
EXIT_ACTIVE = 0xD734
LEVEL_COMPLETE = 0xD735
DOOR_COUNT = 0xD736
DOOR_ACTIVE_INDEX = 0xD737
DOOR_ACTIVE_STATE = 0xD738
DOOR_ACTIVE_FRACTION = 0xD739
DOOR_ACTIVE_FLAGS = 0xD73A
DOOR_LOOKUP_X = 0xD73B
DOOR_LOOKUP_Y = 0xD73C
OAM_DIRTY = 0xD73D
OAM_DEFERRED = 0xD73E
ENTITY_DX = 0xD73F
ENTITY_DY = 0xD740
ENTITY_FORWARD = 0xD741
ENTITY_LATERAL = 0xD742
ENTITY_COS = 0xD743
ENTITY_SIN = 0xD744
ENTITY_TMP_L = 0xD745
ENTITY_TMP_H = 0xD746
ENTITY_SIGN = 0xD747
ENTITY_SCREEN_LEFT = 0xD748
ENTITY_SCREEN_RIGHT = 0xD749
ENTITY_TILE_BASE_STATE = 0xD74A
ENTITY_OAM_PTR_L = 0xD74B
ENTITY_OAM_PTR_H = 0xD74C
LOS_X = 0xD74D
LOS_Y = 0xD74E
LOS_DX = 0xD74F
LOS_DY = 0xD750
LOS_SX = 0xD751
LOS_SY = 0xD752
LOS_ERR = 0xD753
LOS_E2 = 0xD754
LOS_COUNT = 0xD755
LOS_RESULT = 0xD756
MOVE_DELTA = 0xD757
COLLIDE_EDGE = 0xD758
COLLIDE_LOW = 0xD759
COLLIDE_HIGH = 0xD75A
ENTITY_WORLD_XL = 0xD75B
ENTITY_WORLD_XH = 0xD75C
ENTITY_WORLD_YL = 0xD75D
ENTITY_WORLD_YH = 0xD75E
DOOR_LOOP_INDEX = 0xD75F
DOOR_TABLE = 0xD760
MAX_DOORS = level_codec.MAX_DOORS
DOOR_RECORD_BYTES = level_codec.DOOR_RECORD_BYTES
DOOR_X_OFFSET = level_codec.DOOR_X
DOOR_Y_OFFSET = level_codec.DOOR_Y
DOOR_ORIENTATION_OFFSET = level_codec.DOOR_ORIENTATION
DOOR_FLAGS_OFFSET = level_codec.DOOR_FLAGS
DOOR_STATE_OFFSET = level_codec.DOOR_STATE
DOOR_FRACTION_OFFSET = level_codec.DOOR_FRACTION
DOOR_FLAG_EXIT = level_codec.DOOR_FLAG_EXIT
DOOR_FLAG_LOCK_SENTINEL = level_codec.DOOR_FLAG_LOCK_SENTINEL
EXIT_CELL_X = DOOR_TABLE + MAX_DOORS * DOOR_RECORD_BYTES
EXIT_CELL_Y = EXIT_CELL_X + 1

# Compatibility aliases denote the door most recently selected by a lookup.
# Runtime ownership lives in the fixed-capacity table above.
DOOR_STATE = DOOR_ACTIVE_STATE
DOOR_FRACTION = DOOR_ACTIVE_FRACTION
DOOR_CELL_X = DOOR_LOOKUP_X
DOOR_CELL_Y = DOOR_LOOKUP_Y

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
DEPTH_RESULT = _hram("DEPTH_RESULT")
DEPTH_COMPONENT = _hram("DEPTH_COMPONENT")
SEGMENT_RESULT = _hram("SEGMENT_RESULT")
REPROJECT_OFFSET = _hram("REPROJECT_OFFSET")
HRAM_BYTES_USED = _hram_next - 0xFF80

# Ten bytes at the very top of HRAM are reserved for the standard OAM-DMA
# wait stub copied there during startup. State allocation must never overlap.
OAM_DMA_HRAM = 0xFFF4
OAM_DMA_STUB_BYTES = 10
if _hram_next > OAM_DMA_HRAM:
    raise RuntimeError("hot-state ABI overlaps the HRAM OAM-DMA stub")

# Aliases for compositor-local scratch bytes whose legacy names are no longer
# used by another live routine.
SECOND_TOP = GEN_GLOBAL_Y
SECOND_STYLE = GEN_ROW_COUNT
STRIP_KIND = GEN_PAIR_COUNT
D32_LOW = TEMP_CODE
LUT_CORRECTION = PROJECTION_PAGE
LUT_SLICE_LOW = SIGNATURE_COUNT
# The old STYLE_DIFF byte was allocated but never consumed.  Reuse it as the
# per-tile mask for world-height surface rails, preserving the tight HRAM ABI.
DETAIL_MASK = STYLE_DIFF

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
SURFACE_RAIL_Y0 = 48
SURFACE_DETAIL_ENABLED = ACTIVE_LEVEL.vram_profile == 1
MICRO_STATE_COUNT = 19
_COMMON_STATIC_WALL_MASKS = (
    0x00, 0xFF,
    0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01,
    0xC0, 0x60, 0x30, 0x18, 0x0C, 0x06, 0x03,
    0x81, 0x99,
)
STATIC_WALL_MASKS = (
    _COMMON_STATIC_WALL_MASKS
    if SURFACE_DETAIL_ENABLED
    else _COMMON_STATIC_WALL_MASKS + (0x91, 0x89)
)
SURFACE_RAIL_VARIANTS = 2 if SURFACE_DETAIL_ENABLED else 0
SURFACE_RAIL_TILE_BASE = WALL_TILE_BASE + len(STATIC_WALL_MASKS)
STATIC_VIEW_TILES = 2 + len(STATIC_WALL_MASKS) + SURFACE_RAIL_VARIANTS
ATLAS_TILE_BASE = SURFACE_RAIL_TILE_BASE + SURFACE_RAIL_VARIANTS
FOV_DEGREES = 60.5
RAY_VECTOR_SCALE = 127

TILE_ATLAS_TILES = (TILE_ATLAS_ASSETS / "tile_atlas_tiles.bin").read_bytes()
TILE_ATLAS_BUCKET_START = (TILE_ATLAS_ASSETS / "tile_atlas_bucket_start.bin").read_bytes()
TILE_ATLAS_BUCKET_COUNT = (TILE_ATLAS_ASSETS / "tile_atlas_bucket_count.bin").read_bytes()
TILE_ATLAS_ENTRIES = (TILE_ATLAS_ASSETS / "tile_atlas_entries.bin").read_bytes()
RENDERER_ATLAS_TILES = TILE_ATLAS_TILES
RENDERER_ATLAS_BUCKET_START = TILE_ATLAS_BUCKET_START
RENDERER_ATLAS_BUCKET_COUNT = TILE_ATLAS_BUCKET_COUNT
RENDERER_ATLAS_ENTRIES = TILE_ATLAS_ENTRIES
ENTITY_ATLAS_TILES = (ENTITY_ATLAS_ASSETS / "tile_atlas_tiles.bin").read_bytes()
ENTITY_ATLAS_BUCKET_START = (ENTITY_ATLAS_ASSETS / "tile_atlas_bucket_start.bin").read_bytes()
ENTITY_ATLAS_BUCKET_COUNT = (ENTITY_ATLAS_ASSETS / "tile_atlas_bucket_count.bin").read_bytes()
ENTITY_ATLAS_ENTRIES = (ENTITY_ATLAS_ASSETS / "tile_atlas_entries.bin").read_bytes()
# The active level selects the entity cache. Compatibility names describe the
# current profile so host compositor/oracle code stays profile-aware.
if ACTIVE_LEVEL.vram_profile == 1:
    TILE_ATLAS_TILES = ENTITY_ATLAS_TILES
    TILE_ATLAS_BUCKET_START = ENTITY_ATLAS_BUCKET_START
    TILE_ATLAS_BUCKET_COUNT = ENTITY_ATLAS_BUCKET_COUNT
    TILE_ATLAS_ENTRIES = ENTITY_ATLAS_ENTRIES
if ACTIVE_LEVEL.vram_profile == 1:
    ACTIVE_ATLAS_TILES = ENTITY_ATLAS_TILES
    ACTIVE_ATLAS_BUCKET_START = ENTITY_ATLAS_BUCKET_START
    ACTIVE_ATLAS_BUCKET_COUNT = ENTITY_ATLAS_BUCKET_COUNT
    ACTIVE_ATLAS_ENTRIES = ENTITY_ATLAS_ENTRIES
    BANKED_ATLAS_TILES = RENDERER_ATLAS_TILES
    BANKED_ATLAS_BUCKET_START = RENDERER_ATLAS_BUCKET_START
    BANKED_ATLAS_BUCKET_COUNT = RENDERER_ATLAS_BUCKET_COUNT
    BANKED_ATLAS_ENTRIES = RENDERER_ATLAS_ENTRIES
else:
    ACTIVE_ATLAS_TILES = RENDERER_ATLAS_TILES
    ACTIVE_ATLAS_BUCKET_START = RENDERER_ATLAS_BUCKET_START
    ACTIVE_ATLAS_BUCKET_COUNT = RENDERER_ATLAS_BUCKET_COUNT
    ACTIVE_ATLAS_ENTRIES = RENDERER_ATLAS_ENTRIES
    BANKED_ATLAS_TILES = ENTITY_ATLAS_TILES
    BANKED_ATLAS_BUCKET_START = ENTITY_ATLAS_BUCKET_START
    BANKED_ATLAS_BUCKET_COUNT = ENTITY_ATLAS_BUCKET_COUNT
    BANKED_ATLAS_ENTRIES = ENTITY_ATLAS_ENTRIES
BANKED_ATLAS_TILES_ADDRESS = BANKED_ATLAS_ROM_ADDRESS
BANKED_ATLAS_BUCKET_START_ADDRESS = BANKED_ATLAS_TILES_ADDRESS + len(BANKED_ATLAS_TILES)
BANKED_ATLAS_BUCKET_COUNT_ADDRESS = BANKED_ATLAS_BUCKET_START_ADDRESS + len(BANKED_ATLAS_BUCKET_START)
BANKED_ATLAS_ENTRIES_ADDRESS = BANKED_ATLAS_BUCKET_COUNT_ADDRESS + len(BANKED_ATLAS_BUCKET_COUNT)
if BANKED_ATLAS_ENTRIES_ADDRESS + len(BANKED_ATLAS_ENTRIES) > 0x8000:
    raise ValueError("inactive scene atlas does not fit its reserved ROM bank")
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
load_hl_abs = v1.load_hl_abs
store_hl_abs = v1.store_hl_abs


def make_map() -> bytes:
    return ACTIVE_LEVEL.grid


def make_segment_table() -> bytes:
    return ACTIVE_LEVEL.segment_table


# Geometry styles 0..4 remain the exact DDA side/material contract.  In v0.3
# their base fills are deliberately phase-free: surface structure is attached
# to face/cell events in the 160-column descriptor pass instead of repeating
# in screen-tile coordinates.  Render-only styles 5..7 represent a dark
# crease, a run-centred door spine, and a narrow technology rib.
WALL_MATERIAL_NAMES = (
    "oxidized bulkhead - light face",
    "oxidized bulkhead - shadow face",
    "inset machinery panel - light face",
    "inset machinery panel - shadow face",
    "reinforced hazard door",
)

WALL_BASE_COLORS = (2, 3, 2, 3, 2)
WALL_PATTERNS: tuple[tuple[tuple[int, int, int, int], ...], ...] = tuple(
    tuple((base, base, base, base) for _ in range(8))
    for base in WALL_BASE_COLORS
)

# Scene/actor constants.
VRAM_PROFILE_RENDERER = 0
VRAM_PROFILE_ENTITY = 1
WORLD_MODE_EMPTY = 0
WORLD_MODE_LIVING = 1
SENTINEL_DORMANT = 0
SENTINEL_PATROL = 1
SENTINEL_CHASE = 2
SENTINEL_ATTACK = 3
SENTINEL_HURT = 4
SENTINEL_DEAD = 5
AI_TICK_INTERVAL = 4
PLAYER_RADIUS_Q8 = 0x38
ENTITY_ATLAS_PATTERN_COUNT = len(ENTITY_ATLAS_TILES) // 16
ENTITY_TILE_BASE = ATLAS_TILE_BASE + ENTITY_ATLAS_PATTERN_COUNT
SENTINEL_NEAR_TILE_BASE = ENTITY_TILE_BASE
SENTINEL_NEAR_FRAMES = 4
SENTINEL_NEAR_TILES_PER_FRAME = 8
SENTINEL_FAR_TILE_BASE = SENTINEL_NEAR_TILE_BASE + SENTINEL_NEAR_FRAMES * SENTINEL_NEAR_TILES_PER_FRAME
SENTINEL_FAR_FRAMES = 2
SENTINEL_FAR_TILES_PER_FRAME = 2
PICKUP_TILE = SENTINEL_FAR_TILE_BASE + SENTINEL_FAR_FRAMES * SENTINEL_FAR_TILES_PER_FRAME
HIT_EFFECT_TILE_BASE = PICKUP_TILE + 1
EXIT_BEACON_TILE = HIT_EFFECT_TILE_BASE + 2
EXIT_BEACON_FRAMES = 2
ENTITY_TILE_LIMIT = 240
if EXIT_BEACON_TILE + EXIT_BEACON_FRAMES > ENTITY_TILE_LIMIT:
    raise ValueError("entity-heavy profile exceeds tile IDs 199..239")

HUD_DIGIT_BASE = 241
HUD_HEALTH_TENS_X = 2
HUD_HEALTH_ONES_X = 3
HUD_STATUS_TENS_X = 16
HUD_STATUS_ONES_X = 17
HUD_ROW = 14

ENABLE_MICRO_REPROJECTION = os.environ.get("LUPINE3D_REPROJECTION", "0") == "1"
REPROJECT_LIMIT = 4
REPROJECT_GDMA_THRESHOLD = 72
