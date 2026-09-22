"""Host reference for textured walls: what a textured tile byte must be.

Two compositions are defined and proven equal on every scene:

* the **pixel-level** semantics, which say for every world pixel which texel
  it shows: the face's along-face coordinate selects the texture column, the
  wall's height class and the screen row select the texture row, the face
  side and the distance band select the shade; and
* the **row-window** composition the console will run: within one tile column
  the eight texture columns are affine in x (`u_i = u0 + i * delta`), so a
  tile row is one table lookup keyed by texture, shade, delta class, phase
  and texture row, masked by the per-pixel silhouette.

The equality is the contract the emitted kernel will be checked against, the
way `reference_compose_view` is for flat walls. Everything here is exact
integer arithmetic; nothing depends on the emulator.

Textures are authored 16 texels wide and 8 rows tall and mirrored about the
horizon by construction, because the folded compositor draws the lower half of
the view with the Y-flip attribute: a texture that is not vertically symmetric
cannot exist in this renderer.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

from .layout import (FOLDED_ROWS, HORIZON, PHYSICAL_COLUMNS, RAYS, VIEW_HEIGHT, VIEW_MAP_BYTES,
                     VIEW_ROWS, CEILING_TILE, FLOOR_TILE)

TEXELS = 16            # texture columns across one cell face
TEXEL_ROWS = 8         # authored rows, mirrored about the horizon
SHADE_SETS = 4         # near, mid, far on the lit side; the dark side
DELTA_CLASSES = (Fraction(1, 8), Fraction(1, 4), Fraction(1, 2), Fraction(1), Fraction(2))  # texels per pixel
PHASE_STEPS = 4        # sub-texel phases of u0 per class
NEAR_HALF, MID_HALF = 24, 10   # half heights: >= NEAR is near, >= MID is mid, else far


@dataclass(frozen=True)
class Texture:
    name: str
    rows: tuple[tuple[int, ...], ...]   # TEXEL_ROWS rows of TEXELS colour indices in 1..3

    def __post_init__(self) -> None:
        if len(self.rows) != TEXEL_ROWS or any(len(row) != TEXELS for row in self.rows):
            raise ValueError(f"{self.name}: a texture is {TEXELS}x{TEXEL_ROWS} texels")
        if any(c not in (1, 2, 3) for row in self.rows for c in row):
            raise ValueError(f"{self.name}: wall texels use colours 1..3; colour 0 is the outside")

    def texel(self, u: int, v: int) -> int:
        return self.rows[v][u & (TEXELS - 1)]


# Tone remaps per shade set: index 0 near, 1 mid, 2 far on the lit side, 3 the
# dark side. Colour 2 is the lit wall tone, 3 the shaded tone and 1 the deep
# tone the upper palettes share with the floor, so darkening pushes texels
# down that ladder without touching a palette.
SHADE_REMAP: tuple[dict[int, int], ...] = (
    {1: 1, 2: 2, 3: 3},
    {1: 1, 2: 2, 3: 3},
    {1: 1, 2: 3, 3: 1},
    {1: 1, 2: 3, 3: 1},
)


def shade_set(style: int, half: int) -> int:
    """Shade index from the face side (style bit 0 is the dark side) and height."""
    if style & 1:
        return 3
    return 0 if half >= NEAR_HALF else 1 if half >= MID_HALF else 2


def texel_row(half: int, y: int) -> int:
    """Texture row for a screen row of the upper half of a wall of half-height
    `half`; rows above the wall clamp to the first texture row (they are
    masked out of every tile anyway)."""
    top = HORIZON - half
    return max(0, min(TEXEL_ROWS - 1, ((y - top) * TEXEL_ROWS) // half))


def make_v_lut() -> bytes:
    """V[half][y - top] for half in 2..HORIZON, y - top in 0..half-1 (row-major, 64 wide)."""
    out = bytearray()
    for half in range(HORIZON + 1):
        for offset in range(64):
            out.append(texel_row(half, HORIZON - half + offset) if 2 <= half and offset < half else 0)
    return bytes(out)


# ----- along-face coordinate per physical pixel -------------------------------

def reference_ray_u(hits: Sequence) -> list[int]:
    """Per-ray texture coordinate, Q8 along the face, from cast hits."""
    return [hit.along_q8 for hit in hits]


def expand_pixel_u(ray_u: list[int], ray_keys: list[int], ray_segments: list[int],
                   edge_u: dict[int, int]) -> list[int]:
    """Physical-pixel U by the same reconstruction the tops use.

    A pair ray covers two pixels; each is pulled a quarter of the way towards
    its neighbour's ray when both rays lie on the same face (same key and
    segment) and the coordinates do not wrap. The pixels an edge recast
    replaced take the recast's exact coordinate.
    """
    pixel_u = [0] * PHYSICAL_COLUMNS
    for i in range(RAYS):
        current = ray_u[i]
        for output, neighbour in ((i * 2, i - 1), (i * 2 + 1, i + 1)):
            value = current
            if 0 <= neighbour < RAYS and ray_keys[neighbour] == ray_keys[i] and ray_segments[neighbour] == ray_segments[i]:
                other = ray_u[neighbour]
                if abs(other - current) < 128:
                    value = (current * 3 + other + 2) // 4
            pixel_u[output] = value & 0xFF
    for pixel, value in edge_u.items():
        pixel_u[pixel] = value & 0xFF
    return pixel_u


def face_texel_column(u_q8: int, face_side: int) -> Fraction:
    """Texture column, in texels with sub-texel precision, oriented so that it
    increases from the viewer's left to right on every side of a cell."""
    column = Fraction(u_q8 * TEXELS, 256)
    return column if face_side in (0, 3) else Fraction(TEXELS) - column


def face_side_of(key: int, style: int) -> int:
    """0 west, 1 east, 2 north, 3 south, from the descriptor's axis and style.

    The face key packs axis and plane; the sign of travel is what the style
    does not carry, so the side is recovered from the key's plane against the
    hit cell in `texture_pixels`. Callers that already know the side pass it.
    """
    return 0 if not key & 0x80 else 2


# ----- pixel-level composition ----------------------------------------------

@dataclass(frozen=True)
class TexturedColumn:
    """What one physical pixel column shows: silhouette, face and texture."""
    top: int
    style: int
    key: int
    texture: int
    u: Fraction          # texel column with sub-texel precision, oriented


def wall_pixel(textures: Sequence[Texture], column: TexturedColumn, half: int, y: int, *, outline: bool = True) -> int:
    """Colour index of world pixel (x, y) for y in the upper half."""
    if y < column.top:
        return 0
    if y >= VIEW_HEIGHT - column.top:
        return 1
    if outline and y == column.top and half < HORIZON:
        return 3
    v = texel_row(half, min(y, HORIZON - 1)) if y < HORIZON else texel_row(half, VIEW_HEIGHT - 1 - y)
    texel = textures[column.texture].texel(int(column.u) & (TEXELS - 1), v)
    return SHADE_REMAP[shade_set(column.style, half)][texel]


def column_half(columns: Sequence[TexturedColumn]) -> int:
    """The height class a tile column shares: the tallest of its eight pixels
    that lies within two rows of the first, else the first's."""
    first = columns[0].top
    tops = [c.top for c in columns if abs(c.top - first) <= 2]
    return HORIZON - min(tops)


def compose_pixels(textures: Sequence[Texture], columns: Sequence[TexturedColumn], *, outline: bool = True
                   ) -> tuple[bytes, bytes, int, bool, dict[str, int]]:
    """Pixel-level textured compositor: dynamic tiles, view map, count, overflow, stats.

    Every wall tile is composed (there is no seam atlas for textured walls);
    identical tiles within a frame share one pattern, which is what a
    per-frame signature cache would achieve on the console.
    """
    if len(columns) != PHYSICAL_COLUMNS:
        raise ValueError("160 physical columns expected")
    dynamic = bytearray()
    ids: dict[bytes, int] = {}
    view_map = bytearray([CEILING_TILE] * VIEW_MAP_BYTES)
    stats = {"wall_tiles": 0, "boundary_tiles": 0, "seam_tiles": 0, "unique_tiles": 0}
    capacity = 254
    overflow = False
    for tile_col in range(20):
        cols = columns[tile_col * 8:tile_col * 8 + 8]
        min_top = min(c.top for c in cols)
        half = column_half(cols)
        for tile_row in range(FOLDED_ROWS):
            y0 = tile_row * 8
            if y0 + 7 < min_top:
                tile_id = CEILING_TILE
            elif y0 >= VIEW_HEIGHT - min_top:
                tile_id = FLOOR_TILE
            else:
                tile = bytearray(16)
                for i, c in enumerate(cols):
                    for row in range(8):
                        colour = wall_pixel(textures, c, half, y0 + row, outline=outline)
                        if colour & 1: tile[row * 2] |= 0x80 >> i
                        if colour & 2: tile[row * 2 + 1] |= 0x80 >> i
                stats["wall_tiles"] += 1
                if any(y0 <= c.top < y0 + 8 or y0 <= VIEW_HEIGHT - 1 - c.top < y0 + 8 for c in cols):
                    stats["boundary_tiles"] += 1
                if len({(c.key, c.texture) for c in cols}) > 1:
                    stats["seam_tiles"] += 1
                key = bytes(tile)
                if key in ids:
                    tile_id = ids[key]
                else:
                    tile_id = len(dynamic) // 16
                    if tile_id >= capacity:
                        overflow = True; tile_id = 0
                    else:
                        dynamic.extend(tile); ids[key] = tile_id
            view_map[tile_row * 32 + tile_col] = tile_id
            view_map[(VIEW_ROWS - 1 - tile_row) * 32 + tile_col] = tile_id
    stats["unique_tiles"] = len(dynamic) // 16
    return bytes(dynamic), bytes(view_map), len(dynamic) // 16, overflow, stats


# ----- row-window composition ------------------------------------------------

def delta_class(u: Sequence[Fraction]) -> int:
    """Index into DELTA_CLASSES nearest the texel stride across the run."""
    if len(u) < 2:
        return 2
    stride = abs(u[-1] - u[0]) / (len(u) - 1)
    return min(range(len(DELTA_CLASSES)), key=lambda k: abs(DELTA_CLASSES[k] - stride))


def tile_runs(columns: Sequence[TexturedColumn], first: int) -> list[tuple[int, int]]:
    """Runs of one face inside the tile column starting at physical pixel `first`."""
    runs, start = [], first
    while start < first + 8:
        end = start + 1
        while end < first + 8 and (columns[end].key, columns[end].texture, columns[end].style) == (columns[start].key, columns[start].texture, columns[start].style):
            end += 1
        runs.append((start, end)); start = end
    return runs


def affine_columns(columns: Sequence[TexturedColumn]) -> list[TexturedColumn]:
    """Replace each run's texel columns by the affine approximation the
    row-window kernel can afford: within one tile column, a class stride
    from a quantised phase. Faces are oriented so the coordinate never
    decreases along a run; a wrap at a cell boundary is a stride like any
    other because the window reads texels modulo the texture width."""
    out: list[TexturedColumn] = list(columns)
    for first in range(0, len(columns), 8):
        for start, end in tile_runs(columns, first):
            run = columns[start:end]
            u = [c.u for c in run]
            unwrapped = [u[0]]
            for value in u[1:]:
                step = (value - unwrapped[-1]) % TEXELS
                unwrapped.append(unwrapped[-1] + step)
            k = delta_class(unwrapped)
            phase = Fraction(int(run[0].u * PHASE_STEPS), PHASE_STEPS)
            for i, c in enumerate(run):
                out[start + i] = TexturedColumn(c.top, c.style, c.key, c.texture, (phase + i * DELTA_CLASSES[k]) % TEXELS)
    return out


def window_key(run: Sequence[TexturedColumn]) -> tuple[int, int, int, int]:
    """(texture, dark side, delta class, phase index) for one tile-column run."""
    u = [c.u for c in run]
    unwrapped = [u[0]]
    for value in u[1:]:
        unwrapped.append(unwrapped[-1] + (value - unwrapped[-1]) % TEXELS)
    k = delta_class(unwrapped)
    phase = int(run[0].u * PHASE_STEPS) % (TEXELS * PHASE_STEPS)
    return (run[0].texture, run[0].style & 1, k, phase)


def make_row_windows(textures: Sequence[Texture]) -> dict[tuple[int, int, int, int, int], tuple[int, ...]]:
    """Every row window: eight texels for (texture, shade, delta class, phase, v)."""
    windows = {}
    for t, texture in enumerate(textures):
        for shade in range(SHADE_SETS):
            for k, delta in enumerate(DELTA_CLASSES):
                for phase in range(TEXELS * PHASE_STEPS):
                    u0 = Fraction(phase, PHASE_STEPS)
                    for v in range(TEXEL_ROWS):
                        windows[t, shade, k, phase, v] = tuple(
                            SHADE_REMAP[shade][texture.texel(int(u0 + i * delta) & (TEXELS - 1), v)] for i in range(8))
    return windows


def window_table_bytes(texture_count: int) -> int:
    return texture_count * SHADE_SETS * len(DELTA_CLASSES) * TEXELS * PHASE_STEPS * TEXEL_ROWS * 2


def compose_windows(textures: Sequence[Texture], columns: Sequence[TexturedColumn],
                    windows: dict, *, outline: bool = True) -> bytes:
    """The kernel's composition: one window lookup per run and tile row, under
    the silhouette mask, for every wall tile, in the same order as compose_pixels."""
    dynamic = bytearray()
    ids: dict[bytes, int] = {}
    affine = affine_columns(columns)
    for tile_col in range(20):
        cols = affine[tile_col * 8:tile_col * 8 + 8]
        min_top = min(c.top for c in cols)
        half = column_half(cols)
        shade_by_col = [shade_set(c.style, half) for c in cols]
        # Runs inside the tile column: (start, end) with one window key each.
        runs = [(s - tile_col * 8, e - tile_col * 8) for s, e in tile_runs(affine, tile_col * 8)]
        for tile_row in range(FOLDED_ROWS):
            y0 = tile_row * 8
            if y0 + 7 < min_top or y0 >= VIEW_HEIGHT - min_top:
                continue
            tile = bytearray(16)
            for row in range(8):
                y = y0 + row
                # Silhouette masks for this row: wall coverage, outline, floor.
                cover = sum(0x80 >> i for i, c in enumerate(cols) if c.top <= y < VIEW_HEIGHT - c.top)
                floor = sum(0x80 >> i for i, c in enumerate(cols) if y >= VIEW_HEIGHT - c.top)
                edge = sum(0x80 >> i for i, c in enumerate(cols) if outline and y == c.top and half < HORIZON)
                v = texel_row(half, y) if y < HORIZON else texel_row(half, VIEW_HEIGHT - 1 - y)
                plane0 = plane1 = 0
                for s, e in runs:
                    run = cols[s:e]
                    t, dark, k, phase = window_key(run)
                    texels = windows[t, shade_by_col[s], k, phase, v]
                    # The run's first pixel is texel 0 of the window: its pixels sit at s..e-1.
                    for i in range(e - s):
                        bit = 0x80 >> (s + i)
                        if texels[i] & 1: plane0 |= bit
                        if texels[i] & 2: plane1 |= bit
                plane0 = (plane0 & cover & ~edge) | edge | floor
                plane1 = (plane1 & cover & ~edge) | edge
                tile[row * 2], tile[row * 2 + 1] = plane0 & 0xFF, plane1 & 0xFF
            key = bytes(tile)
            if key not in ids:
                ids[key] = len(dynamic) // 16
                dynamic.extend(tile)
    return bytes(dynamic)
