#!/usr/bin/env python3
"""Build Lupine 3D, a pure-CGB fixed-point raycasting demo.

The generated ROM is self-contained, 32 KiB, CGB-only, and uses no cartridge
coprocessor. A tiny purpose-built assembler lives in tools/sm83.py so the
reference ROM can be rebuilt with stock Python 3.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from sm83 import Assembler  # noqa: E402

BUILD = ROOT / "build"
BUILD.mkdir(parents=True, exist_ok=True)

# I/O registers (LDH offsets where possible)
P1 = 0x00
NR10 = 0x10
NR11 = 0x11
NR12 = 0x12
NR13 = 0x13
NR14 = 0x14
NR50 = 0x24
NR51 = 0x25
NR52 = 0x26
LCDC = 0x40
STAT = 0x41
SCY = 0x42
SCX = 0x43
LY = 0x44
BGP = 0x47
OBP0 = 0x48
OBP1 = 0x49
KEY1 = 0x4D
VBK = 0x4F
HDMA1 = 0x51
HDMA2 = 0x52
HDMA3 = 0x53
HDMA4 = 0x54
HDMA5 = 0x55
BGPI = 0x68
BGPD = 0x69
OBPI = 0x6A
OBPD = 0x6B
SVBK = 0x70

# WRAM layout. D000-DFFF is explicitly selected as bank 1.
FB = 0xC000                   # 3840 bytes: 20 columns * 12 tiles * 16 bytes
MAP = 0xD000                  # 16x16 bytes
STATES = 0xD100               # 40 ray render-state bytes
PLAYER_XL = 0xD140
PLAYER_XH = 0xD141
PLAYER_YL = 0xD142
PLAYER_YH = 0xD143
ANGLE = 0xD144
BUTTONS = 0xD145
PREV_BUTTONS = 0xD146
FLASH = 0xD147
CURRENT_PAGE = 0xD148
PRESSED = 0xD149
RAY_XL = 0xD150
RAY_XH = 0xD151
RAY_YL = 0xD152
RAY_YH = 0xD153
RAY_DX = 0xD154
RAY_DX_SIGN = 0xD155
RAY_DY = 0xD156
RAY_DY_SIGN = 0xD157
RAY_STEPS = 0xD158
RAY_ANGLE = 0xD159
HIT_TYPE = 0xD15A
OFFPTR_L = 0xD160
OFFPTR_H = 0xD161
HEIGHTPTR_L = 0xD162
HEIGHTPTR_H = 0xD163
STATEPTR_L = 0xD164
STATEPTR_H = 0xD165
LOOP_COUNT = 0xD166
RESULT = 0xD167
DSTPTR_L = 0xD168
DSTPTR_H = 0xD169
ROW_COUNT = 0xD16A
PAIR_COUNT = 0xD16B
CAND_L = 0xD16C
CAND_H = 0xD16D
MOVE_ANGLE = 0xD16E
DOOR_COUNT = 0xD16F

NINTENDO_LOGO = bytes([
    0xCE, 0xED, 0x66, 0x66, 0xCC, 0x0D, 0x00, 0x0B,
    0x03, 0x73, 0x00, 0x83, 0x00, 0x0C, 0x00, 0x0D,
    0x00, 0x08, 0x11, 0x1F, 0x88, 0x89, 0x00, 0x0E,
    0xDC, 0xCC, 0x6E, 0xE6, 0xDD, 0xDD, 0xD9, 0x99,
    0xBB, 0xBB, 0x67, 0x63, 0x6E, 0x0E, 0xEC, 0xCC,
    0xDD, 0xDC, 0x99, 0x9F, 0xBB, 0xB9, 0x33, 0x3E,
])


def rgb15(r: int, g: int, b: int) -> int:
    return (r & 31) | ((g & 31) << 5) | ((b & 31) << 10)


def words_le(values: list[int]) -> bytes:
    out = bytearray()
    for value in values:
        out.extend((value & 0xFF, (value >> 8) & 0xFF))
    return bytes(out)


def tile_from_pixels(pixels: list[list[int]]) -> bytes:
    """Convert an 8x8 2bpp pixel matrix to Game Boy tile bytes."""
    if len(pixels) != 8 or any(len(row) != 8 for row in pixels):
        raise ValueError("tile must be 8x8")
    out = bytearray()
    for row in pixels:
        lo = hi = 0
        for x, color in enumerate(row):
            bit = 7 - x
            lo |= (color & 1) << bit
            hi |= ((color >> 1) & 1) << bit
        out.extend((lo, hi))
    return bytes(out)


DIGITS = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
}


def make_ui_tiles() -> bytes:
    tiles: list[bytes] = []
    tiles.append(tile_from_pixels([[0] * 8 for _ in range(8)]))  # 240 blank
    for digit in "0123456789":
        px = [[0] * 8 for _ in range(8)]
        glyph = DIGITS[digit]
        for gy, row in enumerate(glyph):
            for gx, on in enumerate(row):
                if on == "1":
                    # Double-width, single-height compact HUD digits.
                    px[gy + 1][gx * 2 + 1] = 2
                    px[gy + 1][gx * 2 + 2] = 3
        tiles.append(tile_from_pixels(px))

    # 251 heart
    heart = [[0] * 8 for _ in range(8)]
    shape = [
        "0110110", "1111111", "1111111", "1111111",
        "0111110", "0011100", "0001000",
    ]
    for y, row in enumerate(shape):
        for x, on in enumerate(row):
            if on == "1": heart[y][x] = 3
    tiles.append(tile_from_pixels(heart))

    # 252 ammunition / cartridge icon
    ammo = [[0] * 8 for _ in range(8)]
    for y in range(1, 7):
        for x in range(2, 6): ammo[y][x] = 2 if y < 5 else 3
    ammo[0][3] = ammo[0][4] = 3
    tiles.append(tile_from_pixels(ammo))

    # 253 muzzle flash star (used as an OBJ tile from VRAM bank 0)
    star = [[0] * 8 for _ in range(8)]
    for x, y in [(3,0),(4,0),(3,1),(4,1),(0,3),(1,3),(2,3),(3,3),(4,3),(5,3),(6,3),(7,3),
                 (0,4),(1,4),(2,4),(3,4),(4,4),(5,4),(6,4),(7,4),(3,5),(4,5),(3,6),(4,6),(3,7),(4,7),
                 (1,1),(2,2),(5,2),(6,1),(1,6),(2,5),(5,5),(6,6)]:
        star[y][x] = 3 if 2 <= x <= 5 and 2 <= y <= 5 else 2
    tiles.append(tile_from_pixels(star))

    # 254 crosshair OBJ tile
    cross = [[0] * 8 for _ in range(8)]
    for i in range(8):
        if i not in (3, 4):
            cross[3][i] = 2
            cross[4][i] = 2
            cross[i][3] = 2
            cross[i][4] = 2
    tiles.append(tile_from_pixels(cross))

    # 255 HUD separator / metal plate
    sep = [[1 if y in (0, 7) else (2 if (x + y) % 4 == 0 else 0) for x in range(8)] for y in range(8)]
    tiles.append(tile_from_pixels(sep))

    assert len(tiles) == 16
    return b"".join(tiles)


def make_weapon_tiles() -> bytes:
    """Create a 32x32 chunky sci-fi pistol and split it into 16 tiles."""
    px = [[0] * 32 for _ in range(32)]
    # Muzzle and top slide.
    for y in range(3, 8):
        for x in range(11, 21): px[y][x] = 2
    for y in range(8, 14):
        for x in range(7, 25): px[y][x] = 2 if y < 11 else 1
    for y in range(9, 12):
        for x in range(10, 22): px[y][x] = 3
    # Receiver.
    for y in range(14, 21):
        left = 5 + (y - 14) // 2
        right = 27 - (y - 14) // 2
        for x in range(left, right): px[y][x] = 2
    for y in range(15, 18):
        for x in range(10, 22): px[y][x] = 3
    # Grip.
    for y in range(20, 32):
        left = 12 + (y - 20) // 4
        right = 21 + (y - 20) // 6
        for x in range(left, right): px[y][x] = 1 if (x + y) % 3 else 2
    # Hands / glove silhouette.
    for y in range(24, 32):
        for x in range(4, 13):
            if (x - 8) ** 2 + (y - 28) ** 2 < 26: px[y][x] = 1
        for x in range(21, 30):
            if (x - 25) ** 2 + (y - 28) ** 2 < 26: px[y][x] = 1
    # Highlights.
    for x in range(9, 23): px[8][x] = 3
    for y in range(4, 18):
        if 0 <= 8 + y // 4 < 32: px[y][8 + y // 4] = 3

    tiles = []
    for ty in range(4):
        for tx in range(4):
            tile = [row[tx * 8:(tx + 1) * 8] for row in px[ty * 8:(ty + 1) * 8]]
            tiles.append(tile_from_pixels(tile))
    assert len(tiles) == 16
    return b"".join(tiles)


def make_tilemap() -> bytes:
    data = bytearray([240] * 1024)
    for y in range(12):
        for x in range(20):
            data[y * 32 + x] = x * 12 + y  # column-major framebuffer tiles
    for x in range(20):
        data[12 * 32 + x] = 255
    # HUD: health 99, face-like central reticle marker, ammunition 08.
    data[14 * 32 + 1] = 251
    data[14 * 32 + 2] = 250  # digit 9: 241 + 9
    data[14 * 32 + 3] = 250
    data[14 * 32 + 9] = 254
    data[14 * 32 + 15] = 252
    data[14 * 32 + 16] = 241  # 0
    data[14 * 32 + 17] = 249  # 8
    return bytes(data)


def make_attrmap(view_bank: int) -> bytes:
    data = bytearray([1] * 1024)  # HUD palette 1, bank 0
    for y in range(12):
        for x in range(20):
            data[y * 32 + x] = (view_bank << 3) | 0
    return bytes(data)


def make_map() -> bytes:
    rows = [
        "1111111111111111",
        "1000000000000001",
        "1011110111110101",
        "1010000100010101",
        "1010220103010101",
        "1010000000010101",
        "1010111111010101",
        "1000100000010001",
        "1110101111011101",
        "1000101000010001",
        "1011101011110101",
        "1000001000000101",
        "1011111111100101",
        "1000000000000001",
        "1000000000000001",
        "1111111111111111",
    ]
    data = bytes(int(c) for row in rows for c in row)
    assert len(data) == 256
    assert data[1 * 16 + 1] == 0
    return data


def make_ray_tables() -> tuple[bytes, bytes, bytes, bytes, bytes]:
    step_dx = bytearray()
    step_dy = bytearray()
    move_dx = bytearray()
    move_dy = bytearray()
    for angle in range(256):
        rad = angle * math.tau / 256.0
        step_dx.append(round(math.cos(rad) * 64) & 0xFF)  # 1/4 tile
        step_dy.append(round(math.sin(rad) * 64) & 0xFF)
        move_dx.append(round(math.cos(rad) * 20) & 0xFF)
        move_dy.append(round(math.sin(rad) * 20) & 0xFF)

    # 60.5-degree field of view, centered between rays 19 and 20.
    offsets = [round(-21.5 + i * (43.0 / 39.0)) for i in range(40)]
    ray_offsets = bytes(x & 0xFF for x in offsets)

    heights = [4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 56, 64, 72, 80, 96]
    height_tables = bytearray()
    for off in offsets:
        correction = max(0.70, math.cos(off * math.tau / 256.0))
        for steps in range(128):
            if steps == 0:
                h = 96
            else:
                # step distance is 1/4 tile; 60-pixel wall at one tile.
                h = min(96, max(4, round(240.0 / (steps * correction))))
            level = min(range(len(heights)), key=lambda i: abs(heights[i] - h))
            height_tables.append(level)
    assert len(height_tables) == 40 * 128
    return bytes(step_dx), bytes(step_dy), bytes(move_dx), bytes(move_dy), ray_offsets + bytes(height_tables)


def make_patterns() -> tuple[bytes, list[int]]:
    heights = [4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 56, 64, 72, 80, 96]
    patterns = bytearray()
    offsets: list[int] = []
    for level, height in enumerate(heights):
        for variant in range(4):
            offsets.append(len(patterns))
            top = (96 - height) // 2
            bottom = top + height
            for y in range(96):
                if y < top:
                    color = 0  # ceiling
                elif y >= bottom:
                    color = 1  # floor
                else:
                    wy = y - top
                    if variant == 0:       # light brick face
                        color = 2 if wy % 8 == 0 else 3
                    elif variant == 1:     # shadowed side
                        color = 3 if wy % 7 else 2
                    elif variant == 2:     # stone / tech wall
                        color = 2 if ((wy // 4) & 1) else 3
                    else:                  # door panel
                        color = 3 if (wy % 12 in (0, 1, 10, 11)) else 2
                low = 0x0F if color & 1 else 0x00
                high = 0x0F if color & 2 else 0x00
                patterns.extend((low, high))
    assert len(offsets) == 64
    assert len(patterns) == 64 * 96 * 2
    return bytes(patterns), offsets


def load_hl_abs(a: Assembler, lo_addr: int, hi_addr: int) -> None:
    a.ld_a_abs(lo_addr); a.ld_r_r("l", "a")
    a.ld_a_abs(hi_addr); a.ld_r_r("h", "a")


def store_hl_abs(a: Assembler, lo_addr: int, hi_addr: int) -> None:
    a.ld_r_r("a", "l"); a.ld_abs_a(lo_addr)
    a.ld_r_r("a", "h"); a.ld_abs_a(hi_addr)


def emit_copy_routine(a: Assembler) -> None:
    a.label("copy_bc")
    a.ldi_a_hl()
    a.ld_mem_rr_a("de")
    a.inc_rr("de")
    a.dec_rr("bc")
    a.ld_r_r("a", "b")
    a.or_r("c")
    a.jr("copy_bc", "nz")
    a.ret()


def emit_wait_vblank(a: Assembler) -> None:
    a.label("wait_vblank")
    a.label("wait_vblank_leave_old")
    a.ldh_a_n(LY)
    a.cp_n(144)
    a.jr("wait_vblank_leave_old", "nc")
    a.label("wait_vblank_enter")
    a.ldh_a_n(LY)
    a.cp_n(144)
    a.jr("wait_vblank_enter", "c")
    a.ret()


def emit_palette_init(a: Assembler) -> None:
    a.label("init_palettes")
    a.ld_r_n("a", 0x80); a.ldh_n_a(BGPI)
    a.ld_rr_label("hl", "bg_palettes")
    a.ld_r_n("b", 16)
    a.label("init_bg_palette_loop")
    a.ldi_a_hl(); a.ldh_n_a(BGPD)
    a.dec_r("b"); a.jr("init_bg_palette_loop", "nz")
    a.ld_r_n("a", 0x80); a.ldh_n_a(OBPI)
    a.ld_rr_label("hl", "obj_palettes")
    a.ld_r_n("b", 16)
    a.label("init_obj_palette_loop")
    a.ldi_a_hl(); a.ldh_n_a(OBPD)
    a.dec_r("b"); a.jr("init_obj_palette_loop", "nz")
    a.ret()


def emit_vram_init(a: Assembler) -> None:
    a.label("init_vram")
    # Bank 0: HUD tiles and both tile-number maps.
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_rr_label("hl", "ui_tiles"); a.ld_rr_nn("de", 0x8F00); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9800); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.ld_rr_label("hl", "tilemap_data"); a.ld_rr_nn("de", 0x9C00); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    # Bank 1: weapon OBJ tiles and tile attributes.
    a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.ld_rr_label("hl", "weapon_tiles"); a.ld_rr_nn("de", 0x8F00); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_rr_label("hl", "attrmap_page0"); a.ld_rr_nn("de", 0x9800); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.ld_rr_label("hl", "attrmap_page1"); a.ld_rr_nn("de", 0x9C00); a.ld_rr_nn("bc", 1024); a.call("copy_bc")
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ret()


def emit_oam_init(a: Assembler) -> None:
    a.label("init_oam")
    # Hide all sprites first.
    a.ld_rr_nn("hl", 0xFE00)
    a.ld_rr_nn("bc", 160)
    a.label("clear_oam_loop")
    a.ld_hl_n(0); a.inc_rr("hl"); a.dec_rr("bc")
    a.ld_r_r("a", "b"); a.or_r("c")
    a.jr("clear_oam_loop", "nz")
    # 4x4 weapon sprite grid, using tiles 240..255 from VRAM bank 1.
    a.ld_rr_nn("hl", 0xFE00)
    for row in range(4):
        for col in range(4):
            a.ld_r_n("a", 64 + row * 8 + 16); a.ldi_hl_a()  # OAM Y
            a.ld_r_n("a", 64 + col * 8 + 8); a.ldi_hl_a()   # OAM X
            a.ld_r_n("a", 240 + row * 4 + col); a.ldi_hl_a()
            a.ld_r_n("a", 0x08); a.ldi_hl_a()               # bank 1, OBJ palette 0
    # Sprite 16: crosshair, bank 0, OBJ palette 1.
    a.ld_r_n("a", 44 + 16); a.ldi_hl_a()
    a.ld_r_n("a", 76 + 8); a.ldi_hl_a()
    a.ld_r_n("a", 254); a.ldi_hl_a()
    a.ld_r_n("a", 0x01); a.ldi_hl_a()
    # Sprite 17: muzzle flash (hidden initially).
    a.xor_r("a"); a.ldi_hl_a()
    a.ld_r_n("a", 76 + 8); a.ldi_hl_a()
    a.ld_r_n("a", 253); a.ldi_hl_a()
    a.ld_r_n("a", 0x01); a.ldi_hl_a()
    a.ret()


def emit_audio(a: Assembler) -> None:
    a.label("init_audio")
    a.ld_r_n("a", 0x80); a.ldh_n_a(NR52)
    a.ld_r_n("a", 0x77); a.ldh_n_a(NR50)
    a.ld_r_n("a", 0x11); a.ldh_n_a(NR51)
    a.ret()

    a.label("sound_shoot")
    a.ld_r_n("a", 0x15); a.ldh_n_a(NR10)
    a.ld_r_n("a", 0x80); a.ldh_n_a(NR11)
    a.ld_r_n("a", 0xF2); a.ldh_n_a(NR12)
    a.xor_r("a"); a.ldh_n_a(NR13)
    a.ld_r_n("a", 0xC7); a.ldh_n_a(NR14)
    a.ret()

    a.label("sound_door")
    a.xor_r("a"); a.ldh_n_a(NR10)
    a.ld_r_n("a", 0x40); a.ldh_n_a(NR11)
    a.ld_r_n("a", 0xB3); a.ldh_n_a(NR12)
    a.ld_r_n("a", 0x70); a.ldh_n_a(NR13)
    a.ld_r_n("a", 0xC4); a.ldh_n_a(NR14)
    a.ret()


def emit_gdma(a: Assembler) -> None:
    a.label("gdma_first_half")
    a.ld_r_n("a", 0xC0); a.ldh_n_a(HDMA1)
    a.xor_r("a"); a.ldh_n_a(HDMA2); a.ldh_n_a(HDMA3); a.ldh_n_a(HDMA4)
    a.ld_r_n("a", 0x77); a.ldh_n_a(HDMA5)  # 120 * 16 = 1920 bytes
    a.ret()

    a.label("gdma_second_half")
    a.ld_r_n("a", 0xC7); a.ldh_n_a(HDMA1)
    a.ld_r_n("a", 0x80); a.ldh_n_a(HDMA2)
    a.ld_r_n("a", 0x07); a.ldh_n_a(HDMA3)
    a.ld_r_n("a", 0x80); a.ldh_n_a(HDMA4)
    a.ld_r_n("a", 0x77); a.ldh_n_a(HDMA5)
    a.ret()

    a.label("upload_initial_both_pages")
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.call("gdma_first_half"); a.call("gdma_second_half")
    a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.call("gdma_first_half"); a.call("gdma_second_half")
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ret()

    a.label("upload_hidden_page")
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.ldh_n_a(VBK)
    a.call("wait_vblank"); a.call("gdma_first_half")
    a.call("wait_vblank"); a.call("gdma_second_half")
    a.call("update_muzzle_oam")
    # Display the newly completed tilemap/page.
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.ld_abs_a(CURRENT_PAGE)
    a.or_r("a"); a.jr("display_page_zero", "z")
    a.ld_r_n("a", 0x9B); a.ldh_n_a(LCDC)
    a.jr("display_page_done")
    a.label("display_page_zero")
    a.ld_r_n("a", 0x93); a.ldh_n_a(LCDC)
    a.label("display_page_done")
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ret()


def emit_joypad(a: Assembler) -> None:
    a.label("read_joypad")
    a.ld_r_n("a", 0x20); a.ldh_n_a(P1)
    a.ldh_a_n(P1); a.ldh_a_n(P1)
    a.cpl(); a.and_n(0x0F); a.ld_r_r("b", "a")
    a.ld_r_n("a", 0x10); a.ldh_n_a(P1)
    a.ldh_a_n(P1); a.ldh_a_n(P1)
    a.cpl(); a.and_n(0x0F); a.cb("swap", "a"); a.or_r("b")
    a.ld_abs_a(BUTTONS)
    a.ld_r_n("a", 0x30); a.ldh_n_a(P1)
    a.ret()


def emit_ray_helpers(a: Assembler) -> None:
    a.label("ray_setup")  # input A = angle
    a.ld_abs_a(RAY_ANGLE)
    a.ld_a_abs(PLAYER_XL); a.ld_abs_a(RAY_XL)
    a.ld_a_abs(PLAYER_XH); a.ld_abs_a(RAY_XH)
    a.ld_a_abs(PLAYER_YL); a.ld_abs_a(RAY_YL)
    a.ld_a_abs(PLAYER_YH); a.ld_abs_a(RAY_YH)
    # dx lookup
    a.ld_a_abs(RAY_ANGLE); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "step_dx"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.xor_r("a"); a.cb("bit", "b", 7); a.jr("ray_dx_positive", "z"); a.dec_r("a")
    a.label("ray_dx_positive")
    a.ld_abs_a(RAY_DX_SIGN); a.ld_r_r("a", "b"); a.ld_abs_a(RAY_DX)
    # dy lookup
    a.ld_a_abs(RAY_ANGLE); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "step_dy"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.xor_r("a"); a.cb("bit", "b", 7); a.jr("ray_dy_positive", "z"); a.dec_r("a")
    a.label("ray_dy_positive")
    a.ld_abs_a(RAY_DY_SIGN); a.ld_r_r("a", "b"); a.ld_abs_a(RAY_DY)
    a.ret()

    a.label("ray_advance")
    a.ld_a_abs(RAY_DX); a.ld_r_r("b", "a")
    a.ld_a_abs(RAY_XL); a.add_a_r("b"); a.ld_abs_a(RAY_XL)
    a.ld_a_abs(RAY_DX_SIGN); a.ld_r_r("b", "a")
    a.ld_a_abs(RAY_XH); a.adc_a_r("b"); a.ld_abs_a(RAY_XH)
    a.ld_a_abs(RAY_DY); a.ld_r_r("b", "a")
    a.ld_a_abs(RAY_YL); a.add_a_r("b"); a.ld_abs_a(RAY_YL)
    a.ld_a_abs(RAY_DY_SIGN); a.ld_r_r("b", "a")
    a.ld_a_abs(RAY_YH); a.adc_a_r("b"); a.ld_abs_a(RAY_YH)
    a.ret()

    a.label("ray_map_cell")
    a.ld_a_abs(RAY_YH); a.cb("swap", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(RAY_XH); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0xD0)
    a.ld_a_hl(); a.ret()  # HL is left pointing to the map cell


def emit_casting(a: Assembler) -> None:
    a.label("cast_one")  # A = ray angle, HEIGHTPTR points at this ray's table
    a.call("ray_setup")
    a.xor_r("a"); a.ld_abs_a(RAY_STEPS)
    a.label("cast_one_step")
    a.call("ray_advance")
    a.ld_a_abs(RAY_STEPS); a.inc_r("a"); a.ld_abs_a(RAY_STEPS)
    a.call("ray_map_cell")
    a.or_r("a"); a.jr("cast_one_step", "z")
    a.ld_abs_a(HIT_TYPE)
    # Per-ray fish-eye-corrected distance-to-height lookup.
    load_hl_abs(a, HEIGHTPTR_L, HEIGHTPTR_H)
    a.ld_a_abs(RAY_STEPS); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.add_hl_rr("de")
    a.ld_a_hl(); a.add_a_r("a"); a.add_a_r("a"); a.ld_r_r("b", "a")
    # Variant 3 = door, 2 = stone, 0/1 = wall-facing approximation.
    a.ld_a_abs(HIT_TYPE); a.cp_n(3); a.jr("cast_variant_door", "z")
    a.cp_n(2); a.jr("cast_variant_stone", "z")
    a.ld_a_abs(RAY_ANGLE); a.and_n(0x20); a.jr("cast_variant_light", "z")
    a.ld_r_n("a", 1); a.jr("cast_variant_merge")
    a.label("cast_variant_light")
    a.xor_r("a"); a.jr("cast_variant_merge")
    a.label("cast_variant_stone")
    a.ld_r_n("a", 2); a.jr("cast_variant_merge")
    a.label("cast_variant_door")
    a.ld_r_n("a", 3)
    a.label("cast_variant_merge")
    a.or_r("b")
    a.ret()

    a.label("cast_all")
    a.ld_rr_label("hl", "ray_offsets"); store_hl_abs(a, OFFPTR_L, OFFPTR_H)
    a.ld_rr_label("hl", "height_tables"); store_hl_abs(a, HEIGHTPTR_L, HEIGHTPTR_H)
    a.ld_rr_nn("hl", STATES); store_hl_abs(a, STATEPTR_L, STATEPTR_H)
    a.ld_r_n("a", 40); a.ld_abs_a(LOOP_COUNT)
    a.label("cast_all_loop")
    load_hl_abs(a, OFFPTR_L, OFFPTR_H)
    a.ldi_a_hl(); a.ld_r_r("b", "a"); store_hl_abs(a, OFFPTR_L, OFFPTR_H)
    a.ld_a_abs(ANGLE); a.add_a_r("b"); a.call("cast_one"); a.ld_abs_a(RESULT)
    load_hl_abs(a, STATEPTR_L, STATEPTR_H)
    a.ld_a_abs(RESULT); a.ldi_hl_a(); store_hl_abs(a, STATEPTR_L, STATEPTR_H)
    load_hl_abs(a, HEIGHTPTR_L, HEIGHTPTR_H)
    a.ld_rr_nn("de", 128); a.add_hl_rr("de"); store_hl_abs(a, HEIGHTPTR_L, HEIGHTPTR_H)
    a.ld_a_abs(LOOP_COUNT); a.dec_r("a"); a.ld_abs_a(LOOP_COUNT)
    a.jp("cast_all_loop", "nz")
    a.ret()


def emit_renderer(a: Assembler) -> None:
    # Helpers update STATEPTR and return pattern pointers in BC or DE.
    a.label("next_pattern_bc")
    load_hl_abs(a, STATEPTR_L, STATEPTR_H)
    a.ldi_a_hl(); a.push("af"); store_hl_abs(a, STATEPTR_L, STATEPTR_H); a.pop("af")
    a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "pattern_ptrs"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("c", "a"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ret()

    a.label("next_pattern_de")
    load_hl_abs(a, STATEPTR_L, STATEPTR_H)
    a.ldi_a_hl(); a.push("af"); store_hl_abs(a, STATEPTR_L, STATEPTR_H); a.pop("af")
    a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "pattern_ptrs"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ret()

    a.label("render_states")
    a.ld_rr_nn("hl", STATES); store_hl_abs(a, STATEPTR_L, STATEPTR_H)
    a.ld_rr_nn("hl", FB); store_hl_abs(a, DSTPTR_L, DSTPTR_H)
    a.ld_r_n("a", 20); a.ld_abs_a(PAIR_COUNT)
    a.label("render_pair_loop")
    a.call("next_pattern_bc")
    a.call("next_pattern_de")
    load_hl_abs(a, DSTPTR_L, DSTPTR_H)
    a.ld_r_n("a", 96); a.ld_abs_a(ROW_COUNT)
    a.label("render_row_loop")
    # Low bitplane: left ray occupies high nibble, right ray low nibble.
    a.ld_a_mem_rr("bc"); a.inc_rr("bc"); a.cb("swap", "a"); a.ld_hl_a()
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.or_r("(hl)"); a.ldi_hl_a()
    # High bitplane.
    a.ld_a_mem_rr("bc"); a.inc_rr("bc"); a.cb("swap", "a"); a.ld_hl_a()
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.or_r("(hl)"); a.ldi_hl_a()
    a.ld_a_abs(ROW_COUNT); a.dec_r("a"); a.ld_abs_a(ROW_COUNT)
    a.jp("render_row_loop", "nz")
    store_hl_abs(a, DSTPTR_L, DSTPTR_H)
    a.ld_a_abs(PAIR_COUNT); a.dec_r("a"); a.ld_abs_a(PAIR_COUNT)
    a.jp("render_pair_loop", "nz")
    a.ret()


def emit_movement(a: Assembler) -> None:
    a.label("move_player")  # input A angle/direction
    a.ld_abs_a(MOVE_ANGLE)
    # Candidate X = X + signed move_dx[angle].
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "move_dx"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_r_n("c", 0); a.cb("bit", "b", 7); a.jr("move_x_positive", "z"); a.dec_r("c")
    a.label("move_x_positive")
    a.ld_a_abs(PLAYER_XL); a.add_a_r("b"); a.ld_abs_a(CAND_L)
    a.ld_a_abs(PLAYER_XH); a.adc_a_r("c"); a.ld_abs_a(CAND_H)
    a.ld_a_abs(PLAYER_YH); a.cb("swap", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(CAND_H); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0xD0); a.ld_a_hl(); a.or_r("a")
    a.jr("move_x_blocked", "nz")
    a.ld_a_abs(CAND_L); a.ld_abs_a(PLAYER_XL)
    a.ld_a_abs(CAND_H); a.ld_abs_a(PLAYER_XH)
    a.label("move_x_blocked")
    # Candidate Y = Y + signed move_dy[angle].
    a.ld_a_abs(MOVE_ANGLE); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "move_dy"); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_r_r("b", "a")
    a.ld_r_n("c", 0); a.cb("bit", "b", 7); a.jr("move_y_positive", "z"); a.dec_r("c")
    a.label("move_y_positive")
    a.ld_a_abs(PLAYER_YL); a.add_a_r("b"); a.ld_abs_a(CAND_L)
    a.ld_a_abs(PLAYER_YH); a.adc_a_r("c"); a.ld_abs_a(CAND_H)
    a.ld_a_abs(CAND_H); a.cb("swap", "a"); a.ld_r_r("b", "a")
    a.ld_a_abs(PLAYER_XH); a.add_a_r("b"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0xD0); a.ld_a_hl(); a.or_r("a")
    a.jr("move_y_blocked", "nz")
    a.ld_a_abs(CAND_L); a.ld_abs_a(PLAYER_YL)
    a.ld_a_abs(CAND_H); a.ld_abs_a(PLAYER_YH)
    a.label("move_y_blocked")
    a.ret()

    a.label("open_door")
    a.ld_a_abs(ANGLE); a.call("ray_setup")
    a.ld_r_n("a", 2); a.ld_abs_a(DOOR_COUNT)
    a.label("open_door_advance")
    a.call("ray_advance")
    a.ld_a_abs(DOOR_COUNT); a.dec_r("a"); a.ld_abs_a(DOOR_COUNT)
    a.jr("open_door_advance", "nz")
    a.call("ray_map_cell"); a.cp_n(3); a.ret("nz")
    a.xor_r("a"); a.ld_hl_a()
    a.call("sound_door")
    a.ret()


def emit_input_update(a: Assembler) -> None:
    a.label("update_input")
    # rising-edge buttons
    a.ld_a_abs(PREV_BUTTONS); a.cpl(); a.ld_r_r("b", "a")
    a.ld_a_abs(BUTTONS); a.and_r("b"); a.ld_abs_a(PRESSED)
    a.ld_a_abs(BUTTONS); a.ld_abs_a(PREV_BUTTONS)
    # Turn left/right.
    a.ld_a_abs(BUTTONS); a.and_n(0x02); a.jr("no_turn_left", "z")
    a.ld_a_abs(ANGLE); a.sub_n(4); a.ld_abs_a(ANGLE)
    a.label("no_turn_left")
    a.ld_a_abs(BUTTONS); a.and_n(0x01); a.jr("no_turn_right", "z")
    a.ld_a_abs(ANGLE); a.add_a_n(4); a.ld_abs_a(ANGLE)
    a.label("no_turn_right")
    # Move forward/backward.
    a.ld_a_abs(BUTTONS); a.and_n(0x04); a.jr("no_move_forward", "z")
    a.ld_a_abs(ANGLE); a.call("move_player")
    a.label("no_move_forward")
    a.ld_a_abs(BUTTONS); a.and_n(0x08); a.jr("no_move_backward", "z")
    a.ld_a_abs(ANGLE); a.add_a_n(128); a.call("move_player")
    a.label("no_move_backward")
    # B opens the door in front; A fires with sound + muzzle flash.
    a.ld_a_abs(PRESSED); a.and_n(0x20); a.jr("no_open_door", "z"); a.call("open_door")
    a.label("no_open_door")
    a.ld_a_abs(PRESSED); a.and_n(0x10); a.jr("no_shoot", "z")
    a.ld_r_n("a", 3); a.ld_abs_a(FLASH); a.call("sound_shoot")
    a.label("no_shoot")
    a.ret()

    a.label("update_muzzle_oam")
    a.ld_a_abs(FLASH); a.or_r("a"); a.jr("muzzle_hidden", "z")
    a.dec_r("a"); a.ld_abs_a(FLASH)
    a.ld_r_n("a", 56 + 16); a.ld_abs_a(0xFE00 + 17 * 4)
    a.ret()
    a.label("muzzle_hidden")
    a.xor_r("a"); a.ld_abs_a(0xFE00 + 17 * 4)
    a.ret()


def build_engine() -> tuple[bytes, Assembler, dict[str, object]]:
    step_dx, step_dy, move_dx, move_dy, ray_blob = make_ray_tables()
    ray_offsets = ray_blob[:40]
    height_tables = ray_blob[40:]
    patterns, pattern_offsets = make_patterns()

    a = Assembler(origin=0x0150)
    a.label("start")
    a.di()
    a.ld_rr_nn("sp", 0xDFFF)
    a.ld_r_n("a", 1); a.ldh_n_a(SVBK)
    a.xor_r("a"); a.ld_abs_a(0xFFFF); a.ld_abs_a(0xFF0F)
    # CGB double-speed switch.
    a.ld_r_n("a", 1); a.ldh_n_a(KEY1); a.stop()
    # LCD may be on after boot; disable only during VBlank.
    a.label("startup_wait_vblank")
    a.ldh_a_n(LY); a.cp_n(144); a.jr("startup_wait_vblank", "c")
    a.xor_r("a"); a.ldh_n_a(LCDC); a.ldh_n_a(SCX); a.ldh_n_a(SCY)
    # Copy mutable map and initialize state.
    a.ld_rr_label("hl", "map_data"); a.ld_rr_nn("de", MAP); a.ld_rr_nn("bc", 256); a.call("copy_bc")
    a.ld_r_n("a", 0x80); a.ld_abs_a(PLAYER_XL); a.ld_abs_a(PLAYER_YL)
    a.ld_r_n("a", 1); a.ld_abs_a(PLAYER_XH); a.ld_abs_a(PLAYER_YH)
    a.xor_r("a"); a.ld_abs_a(ANGLE); a.ld_abs_a(BUTTONS); a.ld_abs_a(PREV_BUTTONS); a.ld_abs_a(FLASH); a.ld_abs_a(CURRENT_PAGE)
    a.call("init_palettes")
    a.call("init_vram")
    a.call("init_oam")
    a.call("init_audio")
    a.call("cast_all")
    a.call("render_states")
    a.call("upload_initial_both_pages")
    a.ld_r_n("a", 0x93); a.ldh_n_a(LCDC)
    a.label("main_loop")
    a.call("read_joypad")
    a.call("update_input")
    a.call("cast_all")
    a.call("render_states")
    a.call("upload_hidden_page")
    a.jp("main_loop")

    # Routines. They can be located after main; all calls are absolute.
    emit_copy_routine(a)
    emit_wait_vblank(a)
    emit_palette_init(a)
    emit_vram_init(a)
    emit_oam_init(a)
    emit_audio(a)
    emit_gdma(a)
    emit_joypad(a)
    emit_ray_helpers(a)
    emit_casting(a)
    emit_renderer(a)
    emit_movement(a)
    emit_input_update(a)

    # Data section.
    a.align(16, text="data alignment")
    a.label("map_data"); a.bytes(make_map(), "16x16 world map")
    a.label("ui_tiles"); a.bytes(make_ui_tiles(), "HUD / utility tiles 240-255")
    a.label("weapon_tiles"); a.bytes(make_weapon_tiles(), "32x32 weapon tiles 240-255")
    a.label("tilemap_data"); a.bytes(make_tilemap(), "32x32 tile-number map")
    a.label("attrmap_page0"); a.bytes(make_attrmap(0), "page 0 CGB attributes")
    a.label("attrmap_page1"); a.bytes(make_attrmap(1), "page 1 CGB attributes")

    bg_palette_values = [
        rgb15(2, 4, 10), rgb15(7, 8, 11), rgb15(26, 18, 8), rgb15(12, 6, 4),
        rgb15(1, 2, 3), rgb15(7, 8, 9), rgb15(29, 27, 20), rgb15(31, 5, 4),
    ]
    obj_palette_values = [
        rgb15(0, 0, 0), rgb15(6, 7, 9), rgb15(16, 18, 20), rgb15(30, 29, 24),
        rgb15(0, 0, 0), rgb15(31, 10, 0), rgb15(31, 24, 1), rgb15(31, 31, 25),
    ]
    a.label("bg_palettes"); a.bytes(words_le(bg_palette_values), "two CGB BG palettes")
    a.label("obj_palettes"); a.bytes(words_le(obj_palette_values), "two CGB OBJ palettes")

    a.align(256, text="ray table page alignment")
    a.label("step_dx"); a.bytes(step_dx, "signed Q8 step dx")
    a.label("step_dy"); a.bytes(step_dy, "signed Q8 step dy")
    a.label("move_dx"); a.bytes(move_dx, "signed Q8 movement dx")
    a.label("move_dy"); a.bytes(move_dy, "signed Q8 movement dy")
    a.label("ray_offsets"); a.bytes(ray_offsets, "40 signed FOV offsets")
    a.align(128, text="height tables alignment")
    a.label("height_tables"); a.bytes(height_tables, "40x128 corrected height levels")
    a.align(2, text="pointer table alignment")
    a.label("pattern_ptrs")
    # Pattern labels are defined after the table; emit relocatable pointers.
    for i in range(64): a.dw_label(f"pattern_{i}")
    a.label("patterns")
    for i, off in enumerate(pattern_offsets):
        a.label(f"pattern_{i}")
        a.bytes(patterns[off:off + 192], f"wall pattern state {i}")

    code = a.resolve()
    metadata = {
        "engine_origin": a.origin,
        "engine_end": a.origin + len(code),
        "engine_size": len(code),
        "framebuffer_bytes": 3840,
        "rays": 40,
        "viewport": [160, 96],
        "map": [16, 16],
        "patterns": 64,
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
    title = b"LUPINE3D"
    rom[0x0134:0x0143] = title.ljust(15, b"\0")
    rom[0x0143] = 0xC0  # CGB-only
    rom[0x0144:0x0146] = b"00"
    rom[0x0146] = 0x00  # no SGB functions
    rom[0x0147] = 0x00  # ROM ONLY
    rom[0x0148] = 0x00  # 32 KiB
    rom[0x0149] = 0x00  # no external RAM
    rom[0x014A] = 0x01  # non-Japanese
    rom[0x014B] = 0x33  # use new licensee field
    rom[0x014C] = 0x00
    rom[0x0150:0x0150 + len(engine)] = engine
    chk = 0
    for value in rom[0x0134:0x014D]: chk = (chk - value - 1) & 0xFF
    rom[0x014D] = chk
    rom[0x014E] = rom[0x014F] = 0
    total = sum(rom) & 0xFFFF
    rom[0x014E] = (total >> 8) & 0xFF
    rom[0x014F] = total & 0xFF
    metadata.update({
        "header_checksum": chk,
        "global_checksum": total,
        "title": "LUPINE3D",
        "cgb_flag": "0xC0 (CGB-only)",
        "rom_size_bytes": len(rom),
        "symbols": {k: f"0x{v:04X}" for k, v in sorted(assembler.labels.items(), key=lambda item: item[1])},
    })
    return bytes(rom), assembler, metadata


def main() -> None:
    rom, assembler, metadata = make_rom()
    rom_path = BUILD / "lupine3d.gb"
    rom_path.write_bytes(rom)
    assembler.write_listing(BUILD / "lupine3d.lst")
    (BUILD / "lupine3d.sym").write_text(
        "\n".join(f"{addr:04X} {name}" for name, addr in sorted(assembler.labels.items(), key=lambda item: item[1])) + "\n",
        encoding="utf-8",
    )
    (BUILD / "build_manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Built {rom_path} ({len(rom)} bytes)")
    print(f"Engine: {metadata['engine_size']} bytes, end={metadata['engine_end']:#06x}")
    print(f"Header checksum: {metadata['header_checksum']:#04x}; global: {metadata['global_checksum']:#06x}")


if __name__ == "__main__":
    main()
