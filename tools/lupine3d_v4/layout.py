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
from lupine3d_v4.configuration import RENDER_CONFIG  # noqa: E402

BUILD = ROOT / "build"
BUILD.mkdir(parents=True, exist_ok=True)
ASSETS = ROOT / "assets"
TILE_ATLAS_ASSETS = Path(os.environ.get("LUPINE3D_TILE_ATLAS_DIR", ASSETS))
ENTITY_ATLAS_ASSETS = Path(os.environ.get("LUPINE3D_ENTITY_ATLAS_DIR", ASSETS / "entity_atlas_80"))
CAMPAIGN = level_codec.campaign(ROOT)
ACTIVE_LEVEL = CAMPAIGN[0]
LEVEL_COUNT = len(CAMPAIGN)
# The resident wall atlas is chosen once, at build time: the VRAM profile
# selects which of the two atlases stays resident and which is banked. A
# campaign level that wanted the other profile would have to stream its atlas
# through a transition, so require one profile for the whole run. The palette
# set is not resident: every world entry uploads the set the level header
# names, so episodes may differ.
for _level in CAMPAIGN[1:]:
    if _level.vram_profile != ACTIVE_LEVEL.vram_profile:
        raise ValueError(f"campaign level {_level.name!r} does not share the resident VRAM profile")
PALETTE_SET_COUNT = len(level_codec.PALETTE_IDS)
PALETTE_SET_NAMES = tuple(sorted(level_codec.PALETTE_IDS, key=level_codec.PALETTE_IDS.get))
assert set(level_codec.PALETTE_IDS.values()) == set(range(PALETTE_SET_COUNT))
SLIM_DISPLAY = RENDER_CONFIG["display"] == "slim"
COMPACT_DISPLAY = RENDER_CONFIG["display"] != "legacy"
SABLE_ART = RENDER_CONFIG["art"] == "sable-v2"
ART_ANIMATION = RENDER_CONFIG["art_animation"]
VIEW_HEIGHT = 120 if SLIM_DISPLAY else 112 if COMPACT_DISPLAY else 96
HORIZON = VIEW_HEIGHT // 2
VIEW_ROWS = VIEW_HEIGHT // 8
FOLDED_ROWS = (VIEW_ROWS + 1) // 2
VIEW_MAP_BYTES = VIEW_ROWS * 32
HUD_HEIGHT = 144 - VIEW_HEIGHT

# Hardware registers (LDH offsets).
P1 = v1.P1
NR10, NR11, NR12, NR13, NR14 = v1.NR10, v1.NR11, v1.NR12, v1.NR13, v1.NR14
NR50, NR51, NR52 = v1.NR50, v1.NR51, v1.NR52
# CH1 stays reserved for sound effects. The sequencer owns CH2, CH3 and CH4,
# so a gunshot can never cut the music.
NR21, NR22, NR23, NR24 = 0x16, 0x17, 0x18, 0x19
NR30, NR31, NR32, NR33, NR34 = 0x1A, 0x1B, 0x1C, 0x1D, 0x1E
NR41, NR42, NR43, NR44 = 0x20, 0x21, 0x22, 0x23
WAVE_RAM = 0x30
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
ENTITY_FOOT_Y = 0xC8A0
AI_CATCHUP_BUDGET = 0xC8A1
PUBLISHED_WORLD_X = 0xC8A2    # 16 immutable base X positions for reprojection
COPY_REMAINDER = 0xC8B2
OBJ_PAGE = 0xC8B3             # published mask-pattern bank, independent of BG page
WALL_CACHE_VALID = 0xC8B4
FRAME_REUSED = 0xC8B5         # this completed update reused the published wall view
PRESENT_SERIAL = 0xC8B6       # increment after every atomic publication, wraps at 256
WALL_CACHE_DISABLE = 0xC8B7   # diagnostic reference path; never a gameplay setting
WALL_EPOCH = 0xC8B8           # content/VRAM reload generation, fixed WRAM u16
WALL_CACHE_MAP = 0xCD00       # exact 256-byte map key, below the reserved stack
WALL_CACHE_META = 0xDE50      # the snapshot key's scalars, between the ray and physical surface profiles
WALL_REUSE_ENABLED = os.environ.get("LUPINE3D_WALL_REUSE", "1") != "0"
SIM_CLOCK = 0xC8D0             # monotonic VBlank clock (wraps modulo 65536)
INPUT_QUEUE_HEAD = 0xC8D2
INPUT_QUEUE_TAIL = 0xC8D3
INPUT_QUEUE_OVERFLOW = 0xC8D4
SIM_READY = 0xC8D5
SIM_TICK = 0xC8D6              # last consumed timestamp, not render count
SIM_BUDGET = 0xC8D8
FRAME_TICK = 0xC8DA
SIM_STEPS = 0xC8DC             # diagnostic 16-bit consumed record count
WORLD_COPY_BUFFER = 0xC900     # 256 map + 8 pose + 128 world bytes
FIXTURE_VISIBILITY = WORLD_COPY_BUFFER  # reused only after snapshot copy is complete
RENDER_HRAM_SAVE = 0xCB00
INPUT_QUEUE = 0xCC00           # 64 x [tick low, tick high, held, edges]
INPUT_QUEUE_CAPACITY = 64
FIXED_SIMULATION = os.environ.get("LUPINE3D_FIXED_SIM", "1") != "0"
STACK_TOP = 0xCFFF             # fixed WRAM: safe across future SVBK changes
DYNAMIC_TILE_VRAM = 0x9000
BG_LCDC = 0x87                # signed BG; hardware 8x16 OBJ mode
HUD_UNSIGNED = True           # viewport-boundary STAT selects bank-0 OBJ-only HUD patterns
HUD_TILE_BASE = 32
# Wall fixture (decal) projection scratch, in the block the wall key vacated.
DECAL_RECORD = 0xDF20          # x/y Q8, segment, kind, side, along-cell, door index
DECAL_INDEX = 0xDF29
DECAL_USED = 0xDF2A
DECAL_PROJECTING = 0xDF2B
DECAL_HEIGHT = 0xDF2C
DECAL_Y = 0xDF2D
DECAL_SOURCE = 0xDF2E
DECAL_WIDE = 0xDF2F
DECAL_SAVED = 0xDF30           # four public projection bytes restored after decor
DECAL_COLUMN = 0xDF34
DECAL_END = DECAL_COLUMN + 1
HUD_PACKET = 0xD3D8            # immutable tile IDs prepared before VBlank, every profile
WEAPON_TILE_BASE = 32 if SABLE_ART else 64          # bank 1 $8400, disjoint from all BG patterns
FOLDED_COMPOSITOR = os.environ.get("LUPINE3D_FOLDED", "1") != "0"
COMPACT_STRIPS = RENDER_CONFIG["compact_strips"]
UNFOLDED_STRIP_ROM_BANK = 237
STRIP_SCRATCH = 0xC8E0 if SLIM_DISPLAY else 0xC7C0 if COMPACT_DISPLAY else 0xC780
INCREMENTAL_CERTIFICATE = RENDER_CONFIG["incremental_certificate"]
DYNAMIC_TILE_CACHE = RENDER_CONFIG["dynamic_tile_cache"]
CACHE_KEY_MIX = RENDER_CONFIG["cache_key_mix"]
ATTRIBUTE_PADDING = RENDER_CONFIG["attribute_padding"]
# HBlank-streamed publication: hidden dynamic patterns and the hidden BG map
# travel by HBlank DMA while the CPU is still composing, so a full packet
# needs one VBlank instead of two or three. Both sources are fixed WRAM,
# because an HBlank block reads through SVBK and a simulation yield may have
# bank 2 mapped when it lands. Banked sources (masks, attributes) stay GDMA
# in the VBlank tail. DYN_STREAMED counts the dynamic patterns already handed
# to the transfer; render_view resets it and chains at column boundaries.
HDMA_STREAMING = RENDER_CONFIG["hdma_streaming"]
DYN_STREAMED = 0xC8CE
# The folded compositor's column of tile IDs, written once per row and
# copied into the map (both halves) once per column, after the snapshot copy
# buffer and before the saved render HRAM.
COLUMN_ROWS = 0xCAF0           # after the snapshot copy buffer (WORLD_COPY_BUFFER + WORLD_COPY_BYTES)
NARROW_YIELDS = RENDER_CONFIG["narrow_yields"]
ANCHOR_PACKETS = RENDER_CONFIG["anchor_packets"]
PACKET_BOUNDS_REUSE = RENDER_CONFIG["packet_bounds_reuse"]
PACKET_WORKSPACE = 0xD2A0       # current packet plus two pending 32-byte siblings
PHYSICAL_DEPTH = RENDER_CONFIG["physical_depth"]
PIXEL_DEPTH_VALID = 0xDF42      # 160 validity bits for the current exact wall key
PIXEL_DEPTH = 0xDF60            # 160 Q5 depths from actual physical-column queries
# Textured walls (docs/TEXTURED_WALLS.md). Every cast records where along its
# face it landed (RAY_U, Q8 within the cell); physical pixels take it by the
# pair expansion (PIXEL_U, in the window physical depth would otherwise use:
# the two are exclusive). Bank 247 holds the per-direction slopes the ROM
# multiplies the axis distance by, the height-class row table and the stride
# classes; the row-window tables follow, three 5-KiB shade blocks per bank.
TEXTURED_WALLS = RENDER_CONFIG["textured_walls"]
RAY_U = 0xD2A0                      # the packet traversal workspace; anchor packets are excluded
PIXEL_U = 0xDF60
TEXTURE_LUT_ROM_BANK = 247
TEXTURE_SLOPES_OFFSET = 0x4000      # 1024 directions x (S_x, S_y) 16-bit = 4 KiB
TEXTURE_V_LUT_OFFSET = 0x5000       # 61 height classes x 64 rows
TEXTURE_STRIDE_LUT_OFFSET = 0x6000  # 8 run lengths x 256 coordinate differences
# Row-window blocks, 5 KiB per (texture, shade), three to a bank, in this
# bank order: seven textures (a structure and a machinery texture per
# episode, one shared door plate) are 28 blocks. 248-251 hold the first
# episode's three textures exactly where they always were; 246 and 155 are
# free under every profile.
TEXTURE_WINDOW_BANKS = (248, 249, 250, 251, 252, 253, 254, 255, 246, 155)
TEXTURE_WINDOW_ROM_BANK_BASE = TEXTURE_WINDOW_BANKS[0]
TEXTURE_SET_DIRECTORY_BYTES = 3 * 4 * 3   # surface profiles x shades x (bank, address)
TEXTURE_WINDOW_BLOCK_BYTES = 5 * 1024
U_RESULT = 0xD8F7                   # the cast's along-face coordinate, beside the other results
U_SLOPE_H = 0xD8F8                  # slope high byte kept across the three products
REFINEMENT_DIRTY = 0xD3A4
REFINEMENT_QUERIED = 0xD3A5
COVERAGE_MODE = 0xD3A6
COVERAGE_LEFT = 0xD3A7
COVERAGE_REMAIN = 0xD3A8
PHYSICAL_DEPTH_MISSING = 0xD3A9
PHYSICAL_QUERY_COUNT = 0xD3AA
GEOMETRY_BACKBONE_RAN = 0xD3AB
PHYSICAL_COVERAGE = 0xD3B0      # twenty required-column bytes, separate from validity
ACTOR_PRECISION = RENDER_CONFIG["actor_precision"]
ACTOR_DX_Q8 = 0xD3C4
ACTOR_DY_Q8 = 0xD3C6
ACTOR_COS_Q14 = 0xD3C8
ACTOR_SIN_Q14 = 0xD3CA
ACTOR_FORWARD_Q8 = 0xD3CC
ACTOR_LATERAL_Q8 = 0xD3CE
ACTOR_ACCUM = 0xD3D0
ACTOR_SIGN = 0xD3D4
ACTOR_SCREEN_SIGN = 0xD3D5
SCANLINE_ADMISSION = RENDER_CONFIG["scanline_admission"]
DOOR_IDENTITY = RENDER_CONFIG["door_identity"]
PROJECTION_STORAGE = RENDER_CONFIG["projection_storage"]
NEAR_FIELD = RENDER_CONFIG["near_field"]
NEAR_PERP_Q8 = 0xD3D6
FOREGROUND_PUBLICATION = RENDER_CONFIG["foreground_publication"]
FG_HEAD, FG_TAIL = 0xC8BA, 0xC8BB
FG_SEQUENCE, FG_CONSUMED_SEQUENCE = 0xC8BC, 0xC8BE
FG_ACTIVE, FG_WORLD_PENDING, FG_READY, FG_SERIAL = 0xC8C0, 0xC8C1, 0xC8C2, 0xC8C3
FG_OVERFLOW = 0xC8C4
FG_FRAME_GENERATION, FG_PUBLISHED_GENERATION, FG_TARGET_GENERATION = 0xC8C6, 0xC8C8, 0xC8CA
FG_BUDGET, FG_CHANGED = 0xC8CC, 0xC8CD
FG_COMPOSITE_OAM, FG_PUBLISHED_OAM, FG_QUEUE = 0xD000, 0xD100, 0xD200  # bank 4
ADMISSION_RECORDS = 0xCB80     # four Y/X/cel/palette/mask records
ADMISSION_COUNT = 0xCB94
ADMISSION_FAILED = 0xCB95
ADMISSION_MODE = 0xCB96
ADMISSION_LINE = 0xCB97
ADMISSION_INDEX = 0xCB98
ADMISSION_DISTANCE_LOD = 0xCB99
CERTIFICATE_THRESHOLD = 0xD3A0  # Nx + Ny, ordinary coarse traversal only
FRAME_SETUP_BANK = 0xD3A2
FRAME_SETUP_PAGE = 0xD3A3
DYNAMIC_CACHE_STAGE = 0xCB70    # validity, profile, generation u16, complete key[10]
DYNAMIC_CACHE_POINTER = 0xCB7E  # fixed-WRAM address across selecting bank 3


def bg_tile_address(tile_id: int) -> int:
    """LCDC.4=0: IDs 0..127 at $9000, IDs 128..255 at $8800."""
    if not 0 <= tile_id <= 255:
        raise ValueError("BG tile ID outside byte range")
    return 0x9000 + (tile_id if tile_id < 128 else tile_id - 256) * 16
# The weapon's OAM window. Sable weapons are rendered from models into a
# 40x32 window right of centre: five 8x16 objects across, two down, four
# cels of twenty patterns (tools/render_weapons.py). The per-scanline
# admission counts these objects before it admits any world object, so ten
# per line still holds with the muzzle flash on the top row. The legacy art
# profile keeps its 32x32 centred window of eight objects.
WEAPON_COLUMNS = 5 if SABLE_ART else 4
WEAPON_OBJECTS = WEAPON_COLUMNS * 2
WEAPON_CEL_PATTERNS = WEAPON_OBJECTS * 2
WEAPON_SCREEN_X = 68 if SABLE_ART else 64
RETICLE_OAM = WEAPON_OBJECTS
MUZZLE_OAM = WEAPON_OBJECTS + 1
ENTITY_OAM_FIRST = WEAPON_OBJECTS + 2   # the weapon's objects, crosshair, muzzle
ENTITY_OAM_COUNT = 16          # bounded 32-pattern masked publication packet
MASK_TILE_COUNT = 0xD8D0
MASK_BITS = 0xD8D1
MASK_OAM_Y = 0xD8D2
MASK_OAM_X = 0xD8D3
MASK_SOURCE_TILE = 0xD8D4
MASK_ATTRIBUTES = 0xD8D5
MASK_ROWS = 0xD8D6
MASK_SCAN_START = 0xD8D7
MASK_SCAN_COUNT = 0xD8D8
ENTITY_SLOT = 0xD8D9
MAX_ACTORS = level_codec.MAX_ACTORS
LOD_HISTORY = 0xD8E0           # MAX_ACTORS actor histories + the generic beacon
WORLD_SCANLINES = 0xD900      # 144 selected-object counters
ENTITY_SLOTS = 0xD990         # MAX_ACTORS fixed 16-byte actor slots (ACTOR_COUNT is fixed WRAM)
ACTOR_DEPTHS = ENTITY_SLOTS + MAX_ACTORS * 16
ACTOR_BEST = ACTOR_DEPTHS + MAX_ACTORS
ACTOR_BEST_DEPTH = ACTOR_BEST + 1
ACTOR_PASS = ACTOR_BEST_DEPTH + 1
assert LOD_HISTORY + MAX_ACTORS + 1 <= 0xD8F0 and ACTOR_PASS < 0xDA00
MASK_TILES = 0xDA00          # at most 32 patterns = 512 bytes
VIEW_ATTRIBUTES = 0xDC00      # hidden 12x32 attribute packet
RAY_SURFACE = 0xDE00
PIXEL_SURFACE = 0xDE80
SURFACE_RESULT = 0xD8F0
SURFACE_COLUMN = 0xD8F1
SURFACE_PROFILE = 0xD8F2
RAY_PROJECTION_X = 0xD8F3    # prepared MBC5 bank and address high byte
RAY_PROJECTION_Y = 0xD8F5

# MBC5 turns otherwise-idle cartridge space into an exact arithmetic unit.
# Banks 0/1 retain the complete 32 KiB engine image; banks 2..145 contain a
# byte-exact projection result for every live (component, correction, D32)
# tuple.  The 4 MiB power-of-two image is accepted by unmodified MBC5 carts.
ROM_BYTES = 4 * 1024 * 1024
ROM_BANKS = ROM_BYTES // 0x4000
PROJECTION_LUT_BASE_BANK = 2
PROJECTION_LUT_CORRECTION_MIN = 110
PROJECTION_LUT_CORRECTION_COUNT = 18
PROJECTION_LUT_COMPONENTS = 128
PROJECTION_LUT_DISTANCES = 512
PROJECTION_LUT_RECORD_BYTES = 2
PROJECTION_LUT_BYTES = (
    PROJECTION_LUT_COMPONENTS
    * PROJECTION_LUT_CORRECTION_COUNT
    * PROJECTION_LUT_DISTANCES
    * PROJECTION_LUT_RECORD_BYTES
)
PRODUCT_LUT_BASE_BANK = PROJECTION_LUT_BASE_BANK + PROJECTION_LUT_BYTES // 0x4000
PRODUCT_LUT_MULTIPLIERS = 256  # full bytes also accelerate Q14 partial products
PRODUCT_LUT_MULTIPLICANDS = 256
PRODUCT_LUT_BYTES = PRODUCT_LUT_MULTIPLIERS * PRODUCT_LUT_MULTIPLICANDS * 2
BANKED_ATLAS_ROM_BANK = PRODUCT_LUT_BASE_BANK + PRODUCT_LUT_BYTES // 0x4000
BANKED_ATLAS_ROM_ADDRESS = 0x4000
# This bank carried the single build-time level's segment/surface tables.
# Campaign levels carry their own in their own banks, so it is now reserved;
# the numbering is kept so no later bank moves.
SEGMENT_TABLE_ROM_BANK = BANKED_ATLAS_ROM_BANK + 1
BOOT_ASSETS_ROM_BANK = SEGMENT_TABLE_ROM_BANK + 1
Q14_ROM_BANK = BOOT_ASSETS_ROM_BANK + 1
Q14_ORDER_ENABLED = os.environ.get("LUPINE3D_Q14", "1") != "0"
# One 1-KiB page per camera angle: 80 pair rays, 160 physical rays,
# centre ray, then padding. Sixteen pages fit in each of sixteen banks.
Q14_ROM_BYTES = 256 * 1024
PREPARED_RAYS = os.environ.get("LUPINE3D_PREPARED_RAYS", "1") != "0"
CAMERA_SETUP = RENDER_CONFIG["camera_setup"] and PREPARED_RAYS
RAY_SETUP_ROM_BANK = Q14_ROM_BANK + Q14_ROM_BYTES // 0x4000
RAY_SETUP_RECORD_BYTES = 16
RAY_SETUP_ROM_BYTES = 256 * 256 * RAY_SETUP_RECORD_BYTES
# Raw direction vectors and the camera-plane offset/correction tables. Prepared
# ray records replaced them on every production cast, so they are cold: only the
# raw-probe sentinel and the disabled packet records still read them. Keeping
# them out of banks 0/1 buys back the resident space they used to occupy.
RAW_RAY_ROM_BANK = 238
RAW_RAY_ROM_ADDRESS = 0x4000
# Authored full-screen presentation. Composition owns the dynamic pattern
# window while the world renders, so these screens borrow it when it is idle.
SCREEN_ROM_BANK = 239
SCREEN_ROM_ADDRESS = 0x4000
SCREEN_SLOT_CAPACITY = 10      # digits one screen can rewrite at runtime
SCREEN_RECORD_BYTES = 6 + 2 * SCREEN_SLOT_CAPACITY
# Songs. The VBlank sequencer must never switch the ROM bank: it could land
# between a banked lookup's switch and its read. The selected song is copied
# into a WRAM bank instead, and the tick saves and restores SVBK.
MUSIC_ROM_BANK = 240
MUSIC_ROM_ADDRESS = 0x4000
MUSIC_RECORD_BYTES = 8
MUSIC_WRAM_BANK = 5
MUSIC_NOTE_TABLE = 0xD000      # 64 periods, two bytes each
MUSIC_ROWS = 0xD080            # three bytes per row: pulse, wave, noise
MUSIC_ROW_CAPACITY = (0xE000 - MUSIC_ROWS) // 3
MUSIC_ROW_BYTES = 3
# Sequencer state in fixed WRAM, above the BG map and below the OAM shadow:
# the ISR reads it under any SVBK, and every display profile leaves this
# window free (slim's map ends here, and the strip scratch sits elsewhere).
MUSIC_STATE = 0xC7E0
# A switchable-WRAM address alone does not name its bank: the render snapshot
# (bank 1) and the live world (bank 2) share every name by design, and banks
# 4 and 5 reuse low addresses. The debugger export takes bank 1 for a
# switchable address unless the name is listed here (lupine3d_v4/symbols.py).
WRAM_BANK_OF_NAME = {"FG_COMPOSITE_OAM": 4, "FG_PUBLISHED_OAM": 4, "FG_QUEUE": 4,
                     "MUSIC_NOTE_TABLE": MUSIC_WRAM_BANK, "MUSIC_ROWS": MUSIC_WRAM_BANK}
MUSIC_ENABLED = MUSIC_STATE
MUSIC_SONG = MUSIC_STATE + 1
MUSIC_SPEED = MUSIC_STATE + 2
MUSIC_TICK = MUSIC_STATE + 3
MUSIC_ROW = MUSIC_STATE + 4          # u16 index of the next row
MUSIC_ROW_COUNT = MUSIC_STATE + 6    # u16
MUSIC_LOOP_ROW = MUSIC_STATE + 8     # u16
MUSIC_POINTER = MUSIC_STATE + 10     # u16 into the copied rows
MUSIC_STATE_END = MUSIC_STATE + 12
# Skill and per-actor stat scratch share the same free fixed-WRAM window.
DIFFICULTY = MUSIC_STATE_END            # 0 easy, 1 normal, 2 hard
DIFFICULTY_LEVELS = 3
ACTOR_STEP = MUSIC_STATE_END + 1        # chase/patrol step for the loaded actor
ACTOR_PALETTE = MUSIC_STATE_END + 2     # OBJ palette for the loaded actor
# Which weapon is in hand, whether its patterns still have to be streamed in,
# and how long until it can fire again. The window the screens vacated.
WEAPON_INDEX = MUSIC_STATE_END + 3
WEAPON_RELOAD = WEAPON_INDEX + 1
WEAPON_COOLDOWN = WEAPON_RELOAD + 1
WORLD_STATE_END = WEAPON_COOLDOWN + 1
# Campaign scalars that cannot change while a frame is in flight live in fixed
# WRAM, readable under any bank: load_level writes them with the LCD off, like
# LEVEL_FIXTURE_COUNT. The actor count used to ride the snapshot copy; it is a
# per-level constant, so it belongs here with the palette set, the weapons in
# the player's possession, and the level's ROM page and texture directory.
ACTOR_COUNT = WORLD_STATE_END           # actors the level fields, 1..MAX_ACTORS
PALETTE_SET = ACTOR_COUNT + 1           # BG/OBJ palette set, from the level header
WEAPONS_OWNED = PALETTE_SET + 1         # bit per weapon
LEVEL_PAGE = WEAPONS_OWNED + 1          # high byte of the level's slot in its bank
TEX_DIRECTORY_L = LEVEL_PAGE + 1        # u16: the level's texture block directory
TEX_DIRECTORY_H = TEX_DIRECTORY_L + 1
CAMPAIGN_SCALARS_END = TEX_DIRECTORY_H + 1
# The live map changes only when a door finishes opening (or a level loads),
# so the snapshot copies its 256 bytes only when this generation moved. Every
# live map writer increments LIVE_MAP_GEN; begin_frame_snapshot records the
# generation it copied in SNAP_MAP_GEN.
LIVE_MAP_GEN = CAMPAIGN_SCALARS_END
SNAP_MAP_GEN = LIVE_MAP_GEN + 1
MAP_GENERATION_END = SNAP_MAP_GEN + 1
assert MAP_GENERATION_END <= 0xC800, "campaign scalars overrun the OAM shadow"
WEAPON_COUNT = 4                        # a power of two: the index is masked
WEAPON_STAT_BYTES = 2                   # damage, cooldown in simulation ticks
WEAPON_TILE_BYTES = 1280 if SABLE_ART else 256
WEAPON_CELS = WEAPON_TILE_BYTES // (WEAPON_CEL_PATTERNS * 16)   # Sable 4, legacy 1
assert WEAPON_CELS * WEAPON_CEL_PATTERNS * 16 == WEAPON_TILE_BYTES
WEAPON_PATTERNS = WEAPON_TILE_BYTES // 16
# The four cel sheets share one ROM bank of their own; weapon_source hands
# the swap and init_vram a pointer into it, and both map it only for the copy.
WEAPON_ROM_BANK = 245
WEAPON_SHEET_LABELS = ("weapon_tiles", "slug_tiles", "arc_tiles", "pulse_tiles")
# The sector (LEVEL_INDEX) from which each weapon is owned: load_level derives
# WEAPONS_OWNED from the index, so a continue code restores the arsenal for
# free and a code that moves backwards can take a weapon away.
WEAPON_UNLOCK_SECTORS = (0, 0, 6, 12)
# Episodes are six sectors each. The title is the first episode's opening;
# reaching the first sector of a later episode (by clearing the one before or
# by a continue code) shows that episode's opening, and clearing an episode
# shows its closing before the next opening.
EPISODE_SECTORS = 6
EPISODE_STARTS = (6, 12)
assert len(WEAPON_UNLOCK_SECTORS) == WEAPON_COUNT == len(WEAPON_SHEET_LABELS) and WEAPON_COUNT & (WEAPON_COUNT - 1) == 0
# Runtime screen digits and the map cells they land in, plus the code-entry
# cursor. A screen with no slots leaves all of this untouched.
#
# It borrows the bottom of the BG map staging buffer. A full-screen mode owns
# the whole background with LCDC $81 and VBlank only, so composition is idle
# for exactly as long as this state exists - the same argument that lets a
# screen borrow the $9000 pattern window - and `enter_world` repeats
# `init_vram`, whose `init_view_map_loop` refills every byte of the buffer. A
# screen never has to put anything back. Keeping it here rather than in the
# $C7E0 window is what lets SCREEN_SLOT_CAPACITY grow at all: that window has
# one byte free and a slot costs three.
SCREEN_STATE = VIEW_MAP
SCREEN_DIGITS = SCREEN_STATE                          # SCREEN_SLOT_CAPACITY values
SCREEN_SLOTS = SCREEN_DIGITS + SCREEN_SLOT_CAPACITY   # two bytes per slot
SCREEN_SLOT_COUNT = SCREEN_SLOTS + 2 * SCREEN_SLOT_CAPACITY
PASSWORD_CURSOR = SCREEN_SLOT_COUNT + 1
PASSWORD_BLINK = PASSWORD_CURSOR + 1
PASSWORD_SCAN = PASSWORD_BLINK + 1
PASSWORD_DIGITS = 4
SCREEN_DIGIT = SCREEN_DIGITS            # the first runtime digit, by itself
# Decimal conversion scratch. A results screen is the only place a number is
# turned into digits, and it has the LCD off while it does it.
SCREEN_VALUE = PASSWORD_SCAN + 1        # u16 being written out
SCREEN_POWER_PTR = SCREEN_VALUE + 2     # u16 into screen_number_powers
SCREEN_DIGITS_LEFT = SCREEN_POWER_PTR + 2
SCREEN_SLOT_INDEX = SCREEN_DIGITS_LEFT + 1
SCREEN_STATE_END = SCREEN_SLOT_INDEX + 1
# `screen_slot_address` and `screen_write_slot` index both arrays with an
# eight-bit add, so neither may cross a page, and all of it has to fit inside
# the buffer it borrows.
assert SCREEN_DIGITS >> 8 == (SCREEN_SLOT_COUNT - 1) >> 8
assert SCREEN_STATE_END <= VIEW_MAP + VIEW_MAP_BYTES

GAME_MODE = 0xC8CF            # fixed WRAM: the ISR reads it under any SVBK
MODE_TITLE, MODE_PLAYING, MODE_GAMEOVER, MODE_ENDING, MODE_INTERMISSION = range(5)
# Screen-mode scratch, fixed WRAM above the strip scratch. Only the non-world
# modes touch it, so it never overlaps a render or simulation lifetime.
SCREEN_INDEX = 0xC8F0
SCREEN_PATTERN_COUNT = 0xC8F1
SCREEN_SOURCE_L, SCREEN_SOURCE_H = 0xC8F2, 0xC8F3
SCREEN_MAP_L, SCREEN_MAP_H = 0xC8F4, 0xC8F5
SCREEN_ROW_COUNT = 0xC8F8
SCREEN_PALETTE = 1            # the reserved steel HUD palette
# The world holds its last frame briefly after death or completion so the HUD
# can be read before a screen replaces it. Frozen frames are cached
# presentations at about sixty a second.
PENDING_MODE = 0xC8F9
MODE_DELAY = 0xC8FA
MODE_DELAY_FRAMES = 120
# Level selection lives in fixed WRAM: the loader writes it with the LCD off
# and no bank selected, and the renderer's segment lookup reads it under the
# bank-1 snapshot. It is deliberately outside the snapshot copy, because it
# cannot change while a frame is in flight.
LEVEL_INDEX = 0xC8FB
LEVEL_BANK = 0xC8FC
LEVEL_FIXTURE_COUNT = 0xC8FD
LEVEL_PICKUP_VALUE = 0xC8FE
Q14_RECORD = 0xD8A0            # 255 disables the certificate for raw ABI probes
Q14_X = 0xD8A2                 # unsigned Q14 component after sign decoding
Q14_Y = 0xD8A4
Q14_ERROR = 0xD8A6             # signed 32-bit crossing error
Q14_PRODUCT = 0xD8AA           # 32-bit multiplication result
Q14_MULTIPLICAND = 0xD8AE      # 32-bit shifted multiplicand
Q14_MULTIPLIER = 0xD8B2        # 16-bit multiplier
Q14_FALLBACKS = 0xD8B4         # diagnostic count per rendered update
Q14_ACTIVE = 0xD8B5
DOOR_ACTIVE_ORIENTATION = 0xD8B6
DOOR_PLANE_DISTANCE = 0xD8B8
DOOR_DIVISOR = 0xD8BA
DOOR_PARALLEL = 0xD8BC
DOOR_RAY_MATERIAL = 0xD8BE
Q14_LOADED = 0xD8BF
COLLISION_X = 0xD8C0
COLLISION_Y = 0xD8C2
LOS_TARGET_X = 0xD8C4
LOS_TARGET_Y = 0xD8C6

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
# Physical-segment identity is expanded alongside the other 160-column
# descriptors. Decoration uses this authoritative geometry certificate rather
# than inferring corners from a face key that also contains paint material.
PIXEL_SEGMENT = 0xD800

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
MAX_FIXTURES = level_codec.MAX_FIXTURES
LEVEL_HEADER_BYTES = level_codec.LEVEL_HEADER_BYTES
LEVEL_ROM_BANK_BASE = level_codec.LEVEL_ROM_BANK_BASE
LEVELS_PER_BANK = level_codec.LEVELS_PER_BANK
LEVEL_SLOT_PITCH = level_codec.LEVEL_SLOT_PITCH
level_location = level_codec.level_location
level_rom_offset = level_codec.level_rom_offset
LEVEL_BANK_COUNT = (LEVEL_COUNT + LEVELS_PER_BANK - 1) // LEVELS_PER_BANK
LEVEL_SEGMENT_OFFSET = level_codec.LEVEL_SEGMENT_OFFSET
LEVEL_SURFACE_OFFSET = level_codec.LEVEL_SURFACE_OFFSET
LEVEL_GRID_OFFSET = level_codec.LEVEL_GRID_OFFSET
LEVEL_HEADER_OFFSET = level_codec.LEVEL_HEADER_OFFSET
LEVEL_DOOR_OFFSET = level_codec.LEVEL_DOOR_OFFSET
LEVEL_ACTOR_OFFSET = level_codec.LEVEL_ACTOR_OFFSET
LEVEL_FIXTURE_OFFSET = level_codec.LEVEL_FIXTURE_OFFSET
LEVEL_PAYLOAD_END = level_codec.LEVEL_PAYLOAD_END
if LEVEL_ROM_BANK_BASE + LEVEL_BANK_COUNT > 256:
    raise ValueError("campaign level banks exceed the 4 MiB MBC5 image")


def add_level_page(a) -> None:
    """HL = HL + (LEVEL_PAGE << 8): from a slot-relative level offset to the
    running level's slot. Six M-cycles; A is clobbered, HL cannot carry
    because every offset plus its index stays inside the slot."""
    a.ld_a_abs(LEVEL_PAGE); a.add_a_r("h"); a.ld_r_r("h", "a")
DOOR_X_OFFSET = level_codec.DOOR_X
DOOR_Y_OFFSET = level_codec.DOOR_Y
DOOR_ORIENTATION_OFFSET = level_codec.DOOR_ORIENTATION
DOOR_FLAGS_OFFSET = level_codec.DOOR_FLAGS
DOOR_STATE_OFFSET = level_codec.DOOR_STATE
DOOR_FRACTION_OFFSET = level_codec.DOOR_FRACTION
DOOR_FLAG_EXIT = level_codec.DOOR_FLAG_EXIT
DOOR_FLAG_LOCK_SENTINEL = level_codec.DOOR_FLAG_LOCK_SENTINEL
DOOR_FLAG_KEYCARD = level_codec.DOOR_FLAG_KEYCARD
DROP_KIND_IDS = level_codec.DROP_KIND_IDS
# A shot lands when the actor's Q5 depth is below the centre ray's wall depth
# plus this slack: a quarter cell, so an actor flush against the wall it is
# pressed to (its centre on the wall plane) is hittable, while one behind a
# wall or a closed panel, at least half a cell further, is not.
HITSCAN_DEPTH_SLACK = 8
# Eight bytes per kind: damage, recovery, step, palette, drop, three spare.
ACTOR_KIND_RECORD_BYTES = 8
ACTOR_KIND_DROP = 4
KIND_DROPS = level_codec.KIND_DROPS
EXIT_CELL_X = DOOR_TABLE + MAX_DOORS * DOOR_RECORD_BYTES
EXIT_CELL_Y = EXIT_CELL_X + 1
# The exact wall key: camera (5), profile and world mode (2), the door count
# and every door record, the reload generation (2), then the whole map.
WALL_KEY_META_BYTES = 5 + 2 + 1 + MAX_DOORS * DOOR_RECORD_BYTES + 2
WALL_KEY_BYTES = WALL_KEY_META_BYTES + 256
assert WALL_CACHE_META + WALL_KEY_META_BYTES <= PIXEL_SURFACE, "wall key scalars overrun the physical surface profiles"

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
# Folded lower-half destination. It walks backwards by one map row while
# MAP_PTR walks forwards, so the mirrored row index never has to be rebuilt
# from TILE_ROW inside the row loop.
MIRROR_MAP_L = _hram("MIRROR_MAP_L")
MIRROR_MAP_H = _hram("MIRROR_MAP_H")
SCAN_TOP_PTR_L = _hram("SCAN_TOP_PTR_L")
SCAN_TOP_PTR_H = _hram("SCAN_TOP_PTR_H")
SCAN_STYLE_PTR_L = _hram("SCAN_STYLE_PTR_L")
SCAN_STYLE_PTR_H = _hram("SCAN_STYLE_PTR_H")
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
# Reserved compositor detail byte. Spatial Clarity deliberately leaves it
# inactive; eye-height surface rails proved to be a false horizon cue.
DETAIL_MASK = STYLE_DIFF

# The textured kernel replaces the microstrip compositor and the atlas lookup
# under its profile, so their compositor-local HRAM scratch becomes its own
# scalars: HRAM is full (the OAM-DMA stub sits four bytes above) and these
# names are read by no other live routine. All live for one composed column.
TEX_RUN_COUNT = SIGNATURE_HASH      # runs in the tile column being composed
TEX_COL_OFFSET = ATLAS_ENTRY_COUNT  # first physical pixel of that column
TEX_REC_L, TEX_REC_H = COMPOSE_DST_L, COMPOSE_DST_H   # the run record in hand
TEX_LOOP = DYNAMIC_FLAG             # runs left to set up / merge
TEX_INTERIOR = STRIP_STATE          # the tile needs no coverage masks
TEX_CACHE_L = STRIP_PAIR            # the run's window cache (low byte)
TEX_DST_L, TEX_DST_H = ATLAS_ENTRY_PTR_L, ATLAS_ENTRY_PTR_H   # where the run composes
TEX_TMP0, TEX_TMP1, TEX_TMP2, TEX_TMP3, TEX_TMP4 = TEMP_TOP, SECOND_TOP, SECOND_STYLE, STRIP_STYLE, STRIP_KIND

# Renderer constants / tile IDs.
RAYS = 80
PHYSICAL_COLUMNS = 160
RAY_WIDTH = 2
VIEWPORT = (160, VIEW_HEIGHT)
RAY_DIRECTION_BITS = 10
RAY_DIRECTION_COUNT = 1 << RAY_DIRECTION_BITS
RAY_PLAYER_SHIFT = RAY_DIRECTION_BITS - 8
RAY_DIRECTION_HIGH_MASK = (RAY_DIRECTION_COUNT >> 8) - 1
FLAT_CEILING_TILE, FLAT_FLOOR_TILE, FLAT_WALL_TILE_BASE = 96, 97, 98
CEILING_TILE = FLAT_CEILING_TILE
FLOOR_TILE = FLAT_FLOOR_TILE
WALL_TILE_BASE = FLAT_WALL_TILE_BASE
STYLE_COUNT = 5
RENDER_STYLE_COUNT = 8
CREASE_STYLE = 5
# Separate semantic IDs keep the presentation grammar explicit even though
# the two dark event styles share the existing light/dark microstrip tables.
TECH_RIB_STYLE = 6
DOOR_SPINE_STYLE = 7
SURFACE_RAIL_Y0 = 48
SURFACE_DETAIL_ENABLED = False
MICRO_STATE_COUNT = 21 if SLIM_DISPLAY else 19
FOLDED_STORED_STATES = (0, 2, 4, 5, 6, 7, 8, 9, 10) + ((19, 20) if SLIM_DISPLAY else ())
STORED_STRIP_STATES = FOLDED_STORED_STATES if COMPACT_STRIPS else tuple(range(MICRO_STATE_COUNT))
STORED_STRIP_COUNT = len(STORED_STRIP_STATES)
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
SURFACE_RAIL_TILE_BASE = FLAT_WALL_TILE_BASE + len(STATIC_WALL_MASKS)
STATIC_VIEW_TILES = 2 + len(STATIC_WALL_MASKS) + SURFACE_RAIL_VARIANTS
ATLAS_TILE_BASE = SURFACE_RAIL_TILE_BASE + SURFACE_RAIL_VARIANTS
# Textured walls compose every wall tile, so the seam tiles and the trained
# atlas retire and the dynamic patterns take BG ids 0..237 of each bank; the
# ceiling and floor move above them, below the sixteen UI tiles at $8F00.
# The WRAM buffer keeps 96 slots and becomes a ring the HBlank stream drains.
DYNAMIC_RING_SLOTS = 96
TEXTURED_CEILING_TILE, TEXTURED_FLOOR_TILE = 238, 239
TEXTURED_DYNAMIC_TILE_CAPACITY = 238
if TEXTURED_WALLS:
    CEILING_TILE, FLOOR_TILE = TEXTURED_CEILING_TILE, TEXTURED_FLOOR_TILE
    WALL_TILE_BASE = TEXTURED_CEILING_TILE
    STATIC_VIEW_TILES = 2
    DYNAMIC_TILE_CAPACITY = TEXTURED_DYNAMIC_TILE_CAPACITY
TEXTURE_STEP_OFFSET = 0x6800        # 61 half heights x Q8 row step (little-endian)
# The kernel's per-column state: eight run records in fixed WRAM (mask, top,
# Q8 accumulator, Q8 step, window cache address) and each run's sixteen-byte
# row-window cache in the render bank, both alive for one composed column.
TEX_RUNS = 0xCBA0                   # eight 12-byte run records
TEX_RUN_BYTES = 12
TEX_WINDOWS = 0xD170                # eight 16-byte window caches (WRAM bank 1)
TEX_MASKS = 0xD130                  # a boundary tile's outline mask per row (WRAM bank 1)
DYN_INFLIGHT = 0xC8DE               # first pattern of the HBlank transfer in flight
FOV_DEGREES = 60.5
CAMERA_FOCAL_PIXELS = round(80 / math.tan(math.radians(FOV_DEGREES / 2)))
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
# Shift signatures without changing checked-in pattern payloads. The odd
# slim viewport has different upper/lower row offsets and a new centre row.
def _translate_atlas(entries):
    buckets = [[] for _ in range(256)]
    for offset in range(0, len(entries), 11):
        record = bytearray(entries[offset:offset+11])
        # Keep both edge offsets exact when the horizon is half a tile.
        # Upper rows move eight pixels; lower rows move sixteen, leaving
        # the self-mirrored centre row to the exact compositor.
        shift = ((HORIZON - 48)//8)*8
        record[0] += (VIEW_HEIGHT - 96 - shift) if record[0] >= 48 else shift
        for index in range(2,10): record[index] += shift
        key = 0
        for byte in record[:10]: key = (((key << 1) | (key >> 7)) & 255) ^ byte
        buckets[key].append(bytes(record))
    starts, counts, records = bytearray(), bytearray(), bytearray()
    for bucket in buckets:
        starts.append(len(records)//11); counts.append(len(bucket))
        records.extend(b"".join(bucket))
    return bytes(starts), bytes(counts), bytes(records)

if COMPACT_DISPLAY:
    RENDERER_ATLAS_BUCKET_START, RENDERER_ATLAS_BUCKET_COUNT, RENDERER_ATLAS_ENTRIES = _translate_atlas(RENDERER_ATLAS_ENTRIES)
    ENTITY_ATLAS_BUCKET_START, ENTITY_ATLAS_BUCKET_COUNT, ENTITY_ATLAS_ENTRIES = _translate_atlas(ENTITY_ATLAS_ENTRIES)
    TILE_ATLAS_BUCKET_START, TILE_ATLAS_BUCKET_COUNT, TILE_ATLAS_ENTRIES = RENDERER_ATLAS_BUCKET_START, RENDERER_ATLAS_BUCKET_COUNT, RENDERER_ATLAS_ENTRIES

# Signed BG allocation decouples OBJ art from the wall atlas. Keep the measured
# 80-pattern option for A/B research, but ship the full cache with entities.
COMPACT_ENTITY_ATLAS = os.environ.get("LUPINE3D_COMPACT_ATLAS", "0") == "1"
if not COMPACT_ENTITY_ATLAS:
    ENTITY_ATLAS_TILES = RENDERER_ATLAS_TILES
    ENTITY_ATLAS_BUCKET_START = RENDERER_ATLAS_BUCKET_START
    ENTITY_ATLAS_BUCKET_COUNT = RENDERER_ATLAS_BUCKET_COUNT
    ENTITY_ATLAS_ENTRIES = RENDERER_ATLAS_ENTRIES
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


# The host geometry models are byte-exact oracles, so they must read the same
# authored tables the running ROM loaded rather than the build-time first
# level. Diagnostics that drive a campaign re-select this from the ROM's own
# LEVEL_INDEX on every validated frame, so it can never drift.
_REFERENCE_LEVEL = [ACTIVE_LEVEL]


def reference_level():
    return _REFERENCE_LEVEL[0]


def select_reference_level(index: int) -> None:
    _REFERENCE_LEVEL[0] = CAMPAIGN[index]


def make_map() -> bytes:
    return reference_level().grid


def make_segment_table() -> bytes:
    return reference_level().segment_table


# Geometry styles 0..4 remain the exact DDA side/material contract.  In v0.3
# their base fills are deliberately phase-free: surface structure is attached
# to geometry events in the 160-column descriptor pass instead of repeating
# in screen-tile coordinates. Render-only styles 5..7 identify a dark crease,
# a reserved soft technology detail, and a run-centred door spine.
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
ENTITY_TILE_BASE = 0
SENTINEL_NEAR_TILE_BASE = ENTITY_TILE_BASE
SENTINEL_NEAR_FRAMES = 12 if SABLE_ART else 4
SENTINEL_NEAR_TILES_PER_FRAME = 8
SENTINEL_FAR_TILE_BASE = SENTINEL_NEAR_TILE_BASE + SENTINEL_NEAR_FRAMES * SENTINEL_NEAR_TILES_PER_FRAME
SENTINEL_FAR_FRAMES = 12 if SABLE_ART else 2
SENTINEL_FAR_TILES_PER_FRAME = 2
PICKUP_TILE = SENTINEL_FAR_TILE_BASE + SENTINEL_FAR_FRAMES * SENTINEL_FAR_TILES_PER_FRAME
HIT_EFFECT_TILE_BASE = PICKUP_TILE + 2
EXIT_BEACON_TILE = HIT_EFFECT_TILE_BASE + 4
EXIT_BEACON_FRAMES = 2
SENTINEL_MID_TILE_BASE = EXIT_BEACON_TILE + EXIT_BEACON_FRAMES * 2
SENTINEL_MID_FRAMES = 12 if SABLE_ART else 2
ENTITY_TILE_LIMIT = 256 if SABLE_ART else WEAPON_TILE_BASE
if EXIT_BEACON_TILE + EXIT_BEACON_FRAMES > ENTITY_TILE_LIMIT:
    raise ValueError("entity-heavy profile exceeds tile IDs 199..239")

HUD_DIGIT_BASE = 32
HUD_SMALL_DIGIT_BASE = 52
HUD_PACKET_BYTES = 16 if SLIM_DISPLAY else 15 if COMPACT_DISPLAY else 11
HUD_STATUS_OFFSET = 5 if SLIM_DISPLAY else 6 if COMPACT_DISPLAY else 8
HUD_PORTRAIT_OFFSET = 10 if SLIM_DISPLAY else 11
HUD_PORTRAIT_TILES = 6 if SLIM_DISPLAY else 4
HUD_HEALTH_TENS_X = 3 if COMPACT_DISPLAY else 2
HUD_HEALTH_ONES_X = HUD_HEALTH_TENS_X + 1
HUD_STATUS_TENS_X = 14 if SLIM_DISPLAY else 15 if COMPACT_DISPLAY else 16
HUD_STATUS_ONES_X = HUD_STATUS_TENS_X + 1
HUD_ROW = VIEW_ROWS + 1 if COMPACT_DISPLAY else 14
HUD_HEALTH_ROW = VIEW_ROWS if SLIM_DISPLAY else HUD_ROW
HUD_PORTRAIT_ROW = VIEW_ROWS if SLIM_DISPLAY else HUD_ROW
HUD_STATUS_ROW = VIEW_ROWS + 1 if SLIM_DISPLAY else HUD_ROW + 1 if COMPACT_DISPLAY else 17
HUD_CAPTION_ROW = VIEW_ROWS if SLIM_DISPLAY else HUD_STATUS_ROW
HUD_CAPTION_X = 16 if SLIM_DISPLAY else 13

ENABLE_MICRO_REPROJECTION = os.environ.get("LUPINE3D_REPROJECTION", "0") == "1"
REPROJECT_LIMIT = 4
REPROJECT_GDMA_THRESHOLD = 72

# Shared by snapshot emission and the allocation/lifetime validator. The
# world window holds the living-world scalars, the door table, the art clocks
# and the campaign state; the actor slots are copied whole, and the count
# beside them is a fixed-WRAM scalar.
WORLD_WINDOW_BYTES = 136
WORLD_COPY_RANGES = ((MAP, 256), (PLAYER_XL, 8), (VRAM_PROFILE, WORLD_WINDOW_BYTES), (ENTITY_SLOTS, MAX_ACTORS * 16))
WORLD_COPY_BYTES = sum(count for _, count in WORLD_COPY_RANGES)

RETICLE_TILE = 112 if SABLE_ART else 80
MUZZLE_TILE = RETICLE_TILE + 2

# Copied world slack right after the exit cell: persistent cosmetic clocks,
# isolated per bank. They follow the door table, so they move with MAX_DOORS.
SHOT_TICK = EXIT_CELL_Y + 1
SHOT_ACTIVE = SHOT_TICK + 2
HURT_TICK = SHOT_ACTIVE + 1
HURT_ACTIVE = HURT_TICK + 2
HINT_TICK = HURT_ACTIVE + 1
HINT_ACTIVE = HINT_TICK + 2
ACTOR_REACTION_TICK = HINT_ACTIVE + 1
ACTOR_REACTION = ACTOR_REACTION_TICK + 2
SENTINEL_KIND = ACTOR_REACTION + 1   # per-actor stat/palette selector, inside the snapshot
ART_STATE_END = SENTINEL_KIND + 1
# Campaign state in the slack at the top of the copied world window. It rides
# the existing snapshot copy rather than growing it, so the renderer
# and the screens read it as coherently as the world itself, and the simulation
# writes the live copy in WRAM bank 2 like every other world field.
GAME_STATE = ART_STATE_END
# A 16-byte actor slot is exactly full, so per-actor auxiliary state goes in a
# parallel array indexed by ENTITY_SLOT - the same shape as ACTOR_DEPTHS.
ACTOR_PATROL = GAME_STATE            # 0..3: +x, -x, +y, -y
ACTIVATION_RADIUS = ACTOR_PATROL + MAX_ACTORS   # cells, from the level header
PLAYER_KEYS = ACTIVATION_RADIUS + 1   # cards in hand; cleared by every level load
# What a results screen reports. Kills fit a byte at four actors a sector;
# time is counted in VBlanks and divided once, on the screen, with the LCD off.
SECTOR_KILLS = PLAYER_KEYS + 1
CAMPAIGN_KILLS = SECTOR_KILLS + 1
SECTOR_START = CAMPAIGN_KILLS + 1     # u16 SIM_CLOCK when the sector loaded
SECTOR_TIME = SECTOR_START + 2        # u16 VBlanks, stamped when it is cleared
CAMPAIGN_TIME = SECTOR_TIME + 2       # u16 VBlanks across the run
GAME_STATE_END = CAMPAIGN_TIME + 2
VBLANKS_PER_SECOND = 60

# The depth pass projects every actor; the draw pass used to project each
# one again with identical inputs. The depth pass now keeps what the draw
# pass reads (SENTINEL_VISIBLE..SENTINEL_LOD, the foot row, the two strip
# masks and MASK_BITS) per slot, beside the copied world window, and a flag
# per slot says the record is this frame's. Bank 2 never reads either.
ACTOR_PROJECTION = VRAM_PROFILE + WORLD_WINDOW_BYTES   # MAX_ACTORS records, ACTOR_PROJECTION_BYTES each
ACTOR_PROJECTION_BYTES = 8
ACTOR_PROJECTED = ACTOR_PROJECTION + MAX_ACTORS * ACTOR_PROJECTION_BYTES
assert ACTOR_PROJECTED + MAX_ACTORS <= 0xD800
# actor_projection_pointer adds a slot's offset to the low byte alone.
assert (ACTOR_PROJECTION & 0xFF) + MAX_ACTORS * ACTOR_PROJECTION_BYTES <= 0x100
assert (ACTOR_PROJECTED & 0xFF) + MAX_ACTORS <= 0x100

# One bounded actor slot, in the order actor_save writes it. The first ten
# bytes are the SENTINEL_XL..SENTINEL_COOLDOWN block; these follow.
ACTOR_SLOT_TAIL = ((PICKUP_ACTIVE, PICKUP_COLLECTED, ACTOR_REACTION_TICK,
                    ACTOR_REACTION_TICK + 1, ACTOR_REACTION, SENTINEL_KIND)
                   if SABLE_ART else (PICKUP_ACTIVE, PICKUP_COLLECTED, SENTINEL_KIND))
ACTOR_KIND_OFFSET = 10 + ACTOR_SLOT_TAIL.index(SENTINEL_KIND)
if 10 + len(ACTOR_SLOT_TAIL) > 16:
    raise ValueError("actor slot tail exceeds the sixteen-byte slot")
