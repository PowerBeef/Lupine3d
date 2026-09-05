"""Pure resource, lookup-table, palette, and tile-data generation."""
from __future__ import annotations

import math
from functools import lru_cache

from .layout import *  # noqa: F401,F403

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
    a physical pixel position. Physical creases and the wider, run-centred
    door spine deliberately occupy separate semantic styles.
    """
    if style < STYLE_COUNT:
        return WALL_BASE_COLORS[style]
    if style in (CREASE_STYLE, DOOR_SPINE_STYLE):
        return 3
    if style == TECH_RIB_STYLE:
        return 2
    raise ValueError(f"unknown render style: {style}")


validate_wall_patterns()


def solid_tile(color: int) -> bytes:
    return tile_from_pixels([[color] * 8 for _ in range(8)])


def _split_pixels(pixels: list[list[int]], width: int, height: int) -> bytes:
    if len(pixels) != height or any(len(row) != width for row in pixels):
        raise ValueError("pixel canvas dimensions do not match")
    out = bytearray()
    for tile_y in range(height // 8):
        for tile_x in range(width // 8):
            tile = [
                row[tile_x * 8:(tile_x + 1) * 8]
                for row in pixels[tile_y * 8:(tile_y + 1) * 8]
            ]
            out.extend(tile_from_pixels(tile))
    return bytes(out)


def make_ui_tiles() -> bytes:
    """Create an original industrial-gothic HUD in the fixed 16-tile budget."""
    tiles: list[bytes] = []

    # 240: a compact lupine visor badge. It gives the status bar a character
    # focal point without borrowing another game's face or artwork.
    badge = [[0] * 8 for _ in range(8)]
    for y in range(1, 7):
        for x in range(1, 7):
            badge[y][x] = 1
    for x, y in ((1, 1), (6, 1), (2, 2), (5, 2), (2, 3), (5, 3),
                 (3, 3), (4, 3), (3, 4), (4, 4), (2, 5), (5, 5),
                 (3, 6), (4, 6)):
        badge[y][x] = 2
    badge[3][2] = badge[3][5] = 3
    badge[5][3] = badge[5][4] = 3
    tiles.append(tile_from_pixels(badge))

    # 241..250: compact bone-coloured digits with a one-pixel metal shadow.
    for digit in "0123456789":
        px = [[0] * 8 for _ in range(8)]
        glyph = v1.DIGITS[digit]
        for gy, row in enumerate(glyph):
            for gx, on in enumerate(row):
                if on == "1":
                    x, y = gx + 2, gy + 1
                    if x + 1 < 8 and y + 1 < 8:
                        px[y + 1][x + 1] = 1
                    px[y][x] = 2
        tiles.append(tile_from_pixels(px))

    # 251: blood-red medical plate with a pale cross.
    health = [[0] * 8 for _ in range(8)]
    for y in range(1, 7):
        for x in range(1, 7):
            health[y][x] = 3 if x in (1, 6) or y in (1, 6) else 1
    for x, y in ((3, 2), (4, 2), (3, 3), (4, 3), (2, 3), (5, 3),
                 (2, 4), (3, 4), (4, 4), (5, 4), (3, 5), (4, 5)):
        health[y][x] = 2
    tiles.append(tile_from_pixels(health))

    # 252: objective-lock housing. The adjacent live 00/01 readout reports
    # whether the exit has been armed by completing the combat objective.
    objective = [[0] * 8 for _ in range(8)]
    for y in range(1, 7):
        objective[y][1] = objective[y][6] = 3
    for x in range(1, 7):
        objective[1][x] = objective[6][x] = 3
    for x, y in ((3, 2), (4, 2), (4, 3), (5, 3), (4, 4), (5, 4),
                 (3, 5), (4, 5)):
        objective[y][x] = 2
    tiles.append(tile_from_pixels(objective))

    # 253: asymmetric muzzle bloom, deliberately chunkier at its hot core.
    star = [[0] * 8 for _ in range(8)]
    for x, y in ((3, 0), (4, 0), (2, 1), (5, 1), (3, 2), (4, 2),
                 (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (7, 3),
                 (1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4),
                 (2, 5), (5, 5), (1, 6), (6, 6), (4, 7)):
        star[y][x] = 3 if 2 <= x <= 5 and 2 <= y <= 5 else 2
    star[3][3] = star[3][4] = star[4][3] = star[4][4] = 3
    tiles.append(tile_from_pixels(star))

    # 254: four-corner combat reticle with a clear centre pixel window.
    cross = [[0] * 8 for _ in range(8)]
    for x, y in ((1, 1), (2, 1), (1, 2), (5, 1), (6, 1), (6, 2),
                 (1, 5), (1, 6), (2, 6), (6, 5), (5, 6), (6, 6),
                 (3, 0), (4, 0), (0, 3), (0, 4), (7, 3), (7, 4),
                 (3, 7), (4, 7)):
        cross[y][x] = 2
    cross[3][3] = cross[3][4] = cross[4][3] = cross[4][4] = 3
    tiles.append(tile_from_pixels(cross))

    # 255: alternating warning stripe used as the viewport/status threshold.
    separator = [[0] * 8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            separator[y][x] = 1 if y in (0, 7) else (2 if ((x + y) // 2) & 1 else 3)
    tiles.append(tile_from_pixels(separator))

    assert len(tiles) == 16
    return b"".join(tiles)


def make_weapon_tiles() -> bytes:
    """Create a 32x32 original twin-bore industrial sidearm and gloves."""
    px = [[0] * 32 for _ in range(32)]

    # Two dark bores and a compact front sight make the first-person shape
    # legible immediately, even on the unscaled CGB display.
    px[3][15] = px[3][16] = 3
    for left in (10, 17):
        for y in range(5, 11):
            for x in range(left, left + 5):
                edge = x in (left, left + 4) or y in (5, 10)
                px[y][x] = 2 if edge else 1
        px[6][left + 2] = 0
        px[7][left + 2] = 1

    # Broad riveted receiver, deliberately tapered toward the player.
    for y in range(11, 21):
        spread = (y - 11) // 3
        left, right = 8 - spread, 24 + spread
        for x in range(left, right):
            px[y][x] = 1 if x in (left, right - 1) or y in (11, 20) else 2
    for x in range(11, 21):
        px[12][x] = 3
    for x, y in ((9, 14), (22, 14), (7, 18), (24, 18)):
        px[y][x] = 3
    for y in range(15, 19):
        px[y][14] = px[y][17] = 1

    # The central pistol grip continues behind the hands.
    for y in range(20, 32):
        inset = (y - 20) // 5
        for x in range(12 + inset, 20 - inset):
            px[y][x] = 1 if x in (12 + inset, 19 - inset) else 2
    for y in (23, 27):
        for x in range(14, 18):
            px[y][x] = 1

    # Warm gloves and pale cuffs approach from the lower corners and overlap
    # the receiver. This overlap is what makes the sprite read as held rather
    # than as a freestanding machine.
    for y in range(21, 32):
        t = y - 21
        left_edge, left_inner = max(0, 8 - t), 14
        right_inner, right_edge = 18, min(32, 24 + t)
        for x in range(left_edge, left_inner):
            px[y][x] = 1 if x in (left_edge, left_inner - 1) else 3
        for x in range(right_inner, right_edge):
            px[y][x] = 1 if x in (right_inner, right_edge - 1) else 3
    for x in range(7, 14):
        px[21][x] = px[22][x] = 2
    for x in range(18, 25):
        px[21][x] = px[22][x] = 2
    for x, y in ((5, 26), (8, 25), (10, 28), (26, 26), (23, 25), (21, 28)):
        px[y][x] = 2

    tiles = _split_pixels(px, 32, 32)
    return b"".join(tiles[(row * 4 + col) * 16:(row * 4 + col + 1) * 16]
                    for pair in range(2) for col in range(4) for row in (pair * 2, pair * 2 + 1))


def _sentinel_near_frame(frame: int) -> bytes:
    """Generate one original skull-faced industrial Sentinel animation cel."""
    px = [[0] * 16 for _ in range(32)]
    hurt = frame == 3
    attack = frame == 2
    bob = frame & 1
    armour = 3 if hurt else 2
    bone = 2 if hurt else 3

    # Horned sensor crown and skull mask.
    for x, y in ((2, 1 + bob), (3, 2 + bob), (13, 1 + bob), (12, 2 + bob),
                 (5, 2 + bob), (10, 2 + bob)):
        px[y][x] = 1
    for y in range(3 + bob, 11 + bob):
        inset = 1 if y in (3 + bob, 10 + bob) else 0
        for x in range(4 + inset, 12 - inset):
            px[y][x] = 1 if x in (4 + inset, 11 - inset) else bone
    px[6 + bob][6] = px[6 + bob][9] = 2
    px[8 + bob][7] = px[8 + bob][8] = 1
    px[9 + bob][6] = px[9 + bob][9] = 1

    # Layered shoulder plates, ribbed torso, and luminous reactor core.
    for y in range(11 + bob, 23 + bob):
        inset = 1 if y in (11 + bob, 22 + bob) else 0
        for x in range(2 + inset, 14 - inset):
            px[y][x] = 1 if x in (2 + inset, 13 - inset) else armour
    for y in (13 + bob, 17 + bob, 21 + bob):
        for x in range(4, 12):
            px[y][x] = bone
    for y in range(14 + bob, 20 + bob):
        px[y][7] = px[y][8] = 3

    # Attack frame opens both weapon arms; walk frames alternate talons.
    arm_y = 13 + bob
    for x in range(0 if attack else 1, 3):
        px[arm_y][x] = px[arm_y + 1][x] = bone if attack else armour
    for x in range(13, 16 if attack else 15):
        px[arm_y][x] = px[arm_y + 1][x] = bone if attack else armour
    if attack:
        px[arm_y][0] = px[arm_y][15] = 3
    left_foot = 2 if frame == 1 else 4
    right_foot = 12 if frame == 1 else 10
    for y in range(23 + bob, 31):
        for x in range(left_foot, left_foot + 3): px[y][x] = 1 if y in (26, 30) else armour
        for x in range(right_foot - 2, right_foot + 1): px[y][x] = 1 if y in (26, 30) else armour
    if hurt:
        for x, y in ((1, 7), (14, 12), (4, 18), (11, 24)):
            px[y][x] = 3
    return _split_pixels(px, 16, 32)


def _sentinel_far_frame(frame: int) -> bytes:
    px = [[0] * 8 for _ in range(16)]
    bob = frame & 1
    px[0 + bob][1] = px[0 + bob][6] = 1
    for y in range(2 + bob, 7 + bob):
        for x in range(2, 6): px[y][x] = 1 if x in (2, 5) else 3
    px[4 + bob][3] = px[4 + bob][4] = 2
    for y in range(8 + bob, 14 + bob):
        for x in range(1, 7): px[y][x] = 1 if x in (1, 6) or y in (8 + bob, 12 + bob) else 2
    px[10 + bob][3] = px[10 + bob][4] = 3
    px[15][2 if frame else 3] = 2
    px[15][5 if frame else 4] = 2
    return _split_pixels(px, 8, 16)


def make_entity_tiles() -> bytes:
    """ROM-source animation cels and wall fixtures; VRAM receives masked pairs."""
    out = bytearray()
    for frame in range(SENTINEL_NEAR_FRAMES):
        tiles = _sentinel_near_frame(frame)
        out.extend(b"".join(tiles[i * 16:(i + 1) * 16] for i in (0, 2, 4, 6, 1, 3, 5, 7)))
    for frame in range(SENTINEL_FAR_FRAMES):
        out.extend(_sentinel_far_frame(frame))

    pickup = [[0] * 8 for _ in range(8)]
    for y in range(2, 7):
        for x in range(1, 7): pickup[y][x] = 1 if y in (2, 6) or x in (1, 6) else 3
    for x, y in ((3, 3), (4, 3), (3, 4), (4, 4), (3, 5), (4, 5), (2, 4), (5, 4)):
        pickup[y][x] = 2
    pickup[1][3] = pickup[1][4] = 1
    out.extend(tile_from_pixels(pickup))
    out.extend(bytes(16))

    for phase in range(2):
        effect = [[0] * 8 for _ in range(8)]
        radius = 2 + phase
        for x, y in ((4, 4 - radius), (4, 4 + radius - 1), (4 - radius, 4), (4 + radius - 1, 4),
                     (4 - phase, 4 - phase), (4 + phase, 4 + phase)):
            if 0 <= x < 8 and 0 <= y < 8: effect[y][x] = 3
        out.extend(tile_from_pixels(effect))
        out.extend(bytes(16))

    # A high-contrast diegetic exit beacon consumes the final two tiles freed
    # by the entity profile. The armoured chevron remains legible at 8x8.
    for phase in range(EXIT_BEACON_FRAMES):
        beacon = [[0] * 8 for _ in range(8)]
        border = 2 + phase
        for x in range(1, 7):
            beacon[1][x] = beacon[6][x] = border
        for y in range(1, 7):
            beacon[y][1] = beacon[y][6] = border
        for x, y in ((3, 2), (4, 2), (4, 3), (5, 3), (4, 4), (5, 4), (3, 5), (4, 5)):
            beacon[y][x] = 3
        out.extend(tile_from_pixels(beacon))
        out.extend(bytes(16))

    # Medium 16x16 LOD keeps width while reducing height. Derived from the
    # same authored cels; adjacent vertical tiles are paired for 8x16 mode.
    for frame in range(SENTINEL_MID_FRAMES):
        source = _sentinel_near_frame(frame)
        px = [[0] * 16 for _ in range(16)]
        for y in range(16):
            for x in range(16):
                offset = ((y * 2 // 8) * 2 + x // 8) * 16 + (y * 2 % 8) * 2
                px[y][x] = ((source[offset] >> (7 - x % 8)) & 1) | (((source[offset + 1] >> (7 - x % 8)) & 1) << 1)
        tiles = _split_pixels(px, 16, 16)
        out.extend(b"".join(tiles[i * 16:(i + 1) * 16] for i in (0, 2, 1, 3)))

    expected_tiles = SENTINEL_MID_TILE_BASE + SENTINEL_MID_FRAMES * 4 - ENTITY_TILE_BASE
    assert len(out) == expected_tiles * 16
    from .artwork import make_fixture_tiles
    out.extend(make_fixture_tiles())
    return bytes(out)


def make_oam_shadow() -> bytes:
    """Initial 40-entry OAM image with UI capacity permanently reserved."""
    data = bytearray(OAM_BYTES)
    # Existing 4x4 weapon grid keeps OAM indices 0..15 and guaranteed priority.
    for row in range(2):
        for col in range(4):
            index = row * 4 + col
            data[index * 4:index * 4 + 4] = bytes((
                64 + row * 16 + 16, 64 + col * 8 + 8,
                WEAPON_TILE_BASE + (row * 4 + col) * 2, 0x0D if row == 1 and col in (0,3) else 0x08,
            ))
    data[8 * 4:8 * 4 + 4] = bytes((44 + 16, 76 + 8, 80, 0x0E))
    data[9 * 4:9 * 4 + 4] = bytes((0, 76 + 8, 82, 0x0B))
    return bytes(data)


def make_obj_ui_tiles() -> bytes:
    from .artwork import make_obj_ui_tiles as authored
    return authored()


def make_static_view_tiles() -> bytes:
    tiles = [solid_tile(0), solid_tile(1)]
    for dark_mask in STATIC_WALL_MASKS:
        pixels = [[3 if dark_mask & (0x80 >> x) else 2 for x in range(8)] for _ in range(8)]
        tiles.append(tile_from_pixels(pixels))
    # The legacy rail variants are intentionally absent in Spatial Clarity.
    for base in ((2, 3) if SURFACE_DETAIL_ENABLED else ()):
        pixels = [[base] * 8 for _ in range(8)]
        pixels[0] = [3] * 8
        pixels[1] = [2] * 8
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


def make_microstrips(states=None) -> bytes:
    """Precompose every physical-pixel boundary strip.

    The position-expanded table is deliberately used here: it removes mask
    logic from the hot compositor while still fitting comfortably in 32 KiB
    after the phase-free material simplification.
    """
    states = tuple(range(MICRO_STATE_COUNT)) if states is None else tuple(states)
    out = bytearray()
    for style in range(2):  # visual light/dark; geometry styles normalize with &1
        for state in states:
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
    assert len(out) == 2 * len(states) * 8 * 16
    return bytes(out)


def make_pair_microstrips(states=None) -> bytes:
    """Fast two-pixel strips used when a synthesized pair remains identical."""
    states = tuple(range(MICRO_STATE_COUNT)) if states is None else tuple(states)
    out = bytearray()
    for style in range(2):
        for state in states:
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
    assert len(out) == 2 * len(states) * 4 * 16
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
    # The 96-pixel viewport terminates in a warning rail. The lower status row
    # contains live health on the left, the original Lupine badge in the
    # centre, and the exit-objective state on the right.
    for x in range(20):
        data[12 * 32 + x] = 255
    # A solid dark-metal status plate uses an existing static tile, preserving
    # the fixed sixteen-tile UI vocabulary while giving the readouts a dense,
    # dashboard-like foundation.
    for y in range(13, 18):
        for x in range(20):
            data[y * 32 + x] = FLOOR_TILE
    data[14 * 32 + 1] = 251
    data[14 * 32 + HUD_HEALTH_TENS_X] = HUD_DIGIT_BASE + 9
    data[14 * 32 + HUD_HEALTH_ONES_X] = HUD_DIGIT_BASE + 9
    data[14 * 32 + 9] = 240
    data[14 * 32 + 15] = 252
    data[14 * 32 + HUD_STATUS_TENS_X] = HUD_DIGIT_BASE
    data[14 * 32 + HUD_STATUS_ONES_X] = HUD_DIGIT_BASE
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
            if FOLDED_COMPOSITOR and y >= 6:
                data[y * 32 + x] |= 0x40 | 2
    return bytes(data)


# Authored native art replaces the retained early generator functions. Keeping
# the wall/table generators independent preserves their numerical contracts.
from .artwork import make_weapon_tiles, _sentinel_near_frame, _sentinel_far_frame


def make_tilemap() -> bytes:
    from .artwork import hud_assets
    data = bytearray(hud_assets()[1]); data[:384] = bytes([CEILING_TILE]) * 384
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
        move_dx.append(round(math.cos(rad) * (4 if FIXED_SIMULATION else 20)) & 0xFF)
        move_dy.append(round(math.sin(rad) * (4 if FIXED_SIMULATION else 20)) & 0xFF)

    # The render-direction table increases angular precision while keeping
    # every signed component representable in one byte. Magnitude 127 is
    # materially more accurate than v0.1.0's scale of 64 and still keeps the
    # DDA's 256*component cross-products inside signed 16-bit.
    ray_dx = bytearray()
    ray_dy = bytearray()
    ray_packed = bytearray()
    for angle in range(RAY_DIRECTION_COUNT):
        rad = angle * math.tau / RAY_DIRECTION_COUNT
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
        offsets.append(round(off_rad * RAY_DIRECTION_COUNT / math.tau))
        corrections.append(round(math.cos(off_rad) * RAY_VECTOR_SCALE))

    physical_offsets: list[int] = []
    physical_corrections = bytearray()
    for i in range(PHYSICAL_COLUMNS):
        screen_x = i + 0.5
        camera_x = 2.0 * screen_x / VIEWPORT[0] - 1.0
        off_rad = math.atan(camera_x * plane)
        physical_offsets.append(round(off_rad * RAY_DIRECTION_COUNT / math.tau))
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

    Each record contains (top, saturated perpendicular Q5 depth). Sixteen
    1024-byte slices fit each MBC5 bank. Live components are only 0..127, so
    retaining depth costs no additional ROM compared with the old table.
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
                out[cursor + 1] = min(255, perpendicular)
                cursor += PROJECTION_LUT_RECORD_BYTES
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
def make_top_depth_lut() -> bytes:
    """Conservative corrected-depth certificate for each projected top.

    Projection intentionally collapses several Q5 depths onto one integer
    wall height. The nearest member of each exact equivalence class prevents
    a billboard from leaking through a wall while avoiding a divider in every
    ray. Values are still corrected perpendicular Q5 distances, not heights.
    """
    projection = make_tables()["projection_half"]
    buckets: list[list[int]] = [[] for _ in range(256)]
    for depth, half_height in enumerate(projection):
        buckets[48 - half_height].append(depth)
    result = bytearray(256)
    for top, depths in enumerate(buckets):
        result[top] = min(255, min(depths)) if depths else 255
    return bytes(result)
