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
