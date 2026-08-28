"""Independent host-side geometry and byte-exact compositor references."""
from __future__ import annotations

from dataclasses import dataclass

from .layout import *  # noqa: F401,F403
from .resources import *  # noqa: F401,F403

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
    depth_q5: int
    segment_id: int


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
    angle_index = (
        (player_angle << RAY_PLAYER_SHIFT) + off
    ) & (RAY_DIRECTION_COUNT - 1)
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
    depth_q5 = make_top_depth_lut()[top]
    side = (0 if sx > 0 else 1) if axis == 0 else (2 if sy > 0 else 3)
    segment_table = make_segment_table()
    segment_id = segment_table[(my * 16 + mx) * 4 + side]
    return ReferenceRayHit(
        ray_index=ray_index, angle_index=angle_index, dx=dx, dy=dy,
        map_x=mx, map_y=my, axis=axis, axis_distance_q8=distance,
        material=material, crossings=crossings, top=top, style=style,
        face_key=face_key, along=along & 0xFF,
        depth_q5=depth_q5, segment_id=segment_id,
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
                                       grid: bytes | None = None) -> tuple[list[int], list[int], list[int], list[int], int, list[int], list[int]]:
    """Apply the ROM's validated one-level affine span reconstruction."""
    hits = [reference_cast_hit(player_x_q8, player_y_q8, player_angle, i, grid) for i in range(RAYS)]
    full_tops = [hit.top for hit in hits]
    full_styles = [hit.style for hit in hits]
    full_keys = [hit.face_key for hit in hits]
    full_alongs = [hit.along for hit in hits]
    full_depths = [hit.depth_q5 for hit in hits]
    full_segments = [hit.segment_id for hit in hits]
    tops = [0] * RAYS
    styles = [0] * RAYS
    keys = [0] * RAYS
    alongs = [0] * RAYS
    depths = [0] * RAYS
    segments = [0] * RAYS
    cast_count = 0
    for i in range(0, RAYS, 2):
        tops[i], styles[i], keys[i], alongs[i] = full_tops[i], full_styles[i], full_keys[i], full_alongs[i]
        depths[i], segments[i] = full_depths[i], full_segments[i]
        cast_count += 1
    tops[79], styles[79], keys[79], alongs[79] = full_tops[79], full_styles[79], full_keys[79], full_alongs[79]
    depths[79], segments[79] = full_depths[79], full_segments[79]
    cast_count += 1
    for i in range(1, 78, 2):
        same_face = (
            keys[i - 1] == keys[i + 1]
            and segments[i - 1] == segments[i + 1]
            and abs(alongs[i - 1] - alongs[i + 1]) <= 1
            and abs(tops[i - 1] - tops[i + 1]) <= 2
        )
        if same_face:
            tops[i] = (tops[i - 1] + tops[i + 1] + 1) // 2
            styles[i], keys[i], alongs[i] = styles[i - 1], keys[i - 1], alongs[i - 1]
            depths[i] = make_top_depth_lut()[tops[i]]
            segments[i] = segments[i - 1]
        else:
            tops[i], styles[i], keys[i], alongs[i] = full_tops[i], full_styles[i], full_keys[i], full_alongs[i]
            depths[i], segments[i] = full_depths[i], full_segments[i]
            cast_count += 1
    return tops, styles, keys, alongs, cast_count, depths, segments


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
    tops, styles, keys, alongs, adaptive_casts, depths, segments = reference_adaptive_descriptor_view(
        player_x_q8, player_y_q8, player_angle, grid
    )
    pixel_tops = [0] * PHYSICAL_COLUMNS
    pixel_styles = [0] * PHYSICAL_COLUMNS
    pixel_keys = [0] * PHYSICAL_COLUMNS
    pixel_alongs = [0] * PHYSICAL_COLUMNS
    pixel_segments = [0] * PHYSICAL_COLUMNS

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
            pixel_segments[output] = segments[i]

    edge_recasts = 0
    for i in range(RAYS - 1):
        if keys[i] == keys[i + 1] and segments[i] == segments[i + 1]:
            continue
        for pixel_index in (i * 2 + 1, i * 2 + 2):
            hit = reference_cast_physical_hit(player_x_q8, player_y_q8, player_angle, pixel_index, grid)
            pixel_tops[pixel_index] = hit.top
            pixel_styles[pixel_index] = hit.style
            pixel_keys[pixel_index] = hit.face_key
            pixel_alongs[pixel_index] = hit.along
            pixel_segments[pixel_index] = hit.segment_id
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
        adaptive_casts + edge_recasts, edge_recasts, events, depths, segments,
    )


def reference_descriptor_view(player_x_q8: int, player_y_q8: int, player_angle: int) -> tuple[list[int], list[int]]:
    tops, styles, *_ = reference_adaptive_descriptor_view(player_x_q8, player_y_q8, player_angle)
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
