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
from functools import lru_cache
from typing import Sequence

from .layout import (FOLDED_ROWS, HORIZON, PHYSICAL_COLUMNS, RAYS, VIEW_HEIGHT, VIEW_MAP_BYTES,
                     VIEW_ROWS, TEXTURED_CEILING_TILE, TEXTURED_FLOOR_TILE, TEXTURED_DYNAMIC_TILE_CAPACITY)

# The textured profile's static ids and pattern budget, whatever the build's own profile.
CEILING_TILE, FLOOR_TILE = TEXTURED_CEILING_TILE, TEXTURED_FLOOR_TILE
WALL_TILE_BASE = TEXTURED_CEILING_TILE
DYNAMIC_TILE_CAPACITY = TEXTURED_DYNAMIC_TILE_CAPACITY

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
# The door palettes run the other way round: colour 3 is their light tone
# (mint on teal, yellow on orange, lilac on purple), so the ladder above made
# far doors brighter and inverted them. Far and on the dark side a door
# loses its light tone to its base colour and keeps the base, so it still
# reads as a coloured leaf with dark marks rather than a black cell.
SHADE_REMAP_LIGHT_THREE: tuple[dict[int, int], ...] = (
    {1: 1, 2: 2, 3: 3},
    {1: 1, 2: 2, 3: 3},
    {1: 1, 2: 2, 3: 2},
    {1: 1, 2: 2, 3: 2},
)
LIGHT_THREE_TEXTURES = frozenset({"door_plate"})


def shade_remap(texture: "Texture") -> tuple[dict[int, int], ...]:
    """The distance ladder for this texture's palette."""
    return SHADE_REMAP_LIGHT_THREE if texture.name in LIGHT_THREE_TEXTURES else SHADE_REMAP


def shade_set(style: int, half: int) -> int:
    """Shade index from the face side (style bit 0 is the dark side) and height."""
    if style & 1:
        return 3
    return 0 if half >= NEAR_HALF else 1 if half >= MID_HALF else 2


def row_step(half: int) -> int:
    """Q8 texture rows per screen row for a wall of half-height `half`.

    Floor(2048 / half) keeps the last row of the wall inside texture row 7:
    (half - 1) * step < 2048. The console accumulates this per run and row.
    """
    return (TEXEL_ROWS * 256) // max(half, 1)


def texel_row(half: int, y: int) -> int:
    """Texture row for a screen row of the upper half of a wall of half-height
    `half`, as the console's accumulator computes it; rows above the wall
    read row 0 (they are masked out of every tile anyway)."""
    top = HORIZON - half
    if y < top:
        return 0
    return ((y - top) * row_step(half)) >> 8


def make_step_lut() -> bytes:
    """Little-endian Q8 row steps for half heights 0..HORIZON."""
    return b"".join(row_step(half).to_bytes(2, "little") for half in range(HORIZON + 1))


def make_v_lut() -> bytes:
    """V[half][y - top] for half in 2..HORIZON, y - top in 0..half-1 (row-major, 64 wide)."""
    out = bytearray()
    for half in range(HORIZON + 1):
        for offset in range(64):
            out.append(texel_row(half, HORIZON - half + offset) if 2 <= half and offset < half else 0)
    return bytes(out)


# ----- the console's along-face arithmetic ------------------------------------
#
# A hit knows its axis distance D (Q8, `DDA_DIST`) and its direction index
# (`DDA_ANGLE`, 0..1023). The coordinate along the face is the player's other
# coordinate advanced by D times the direction's slope: S_x = 256*|sin|/|cos|
# for a face perpendicular to x, S_y = 256*|cos|/|sin| for one perpendicular
# to y, each a 16-bit Q8 value from a 1024-entry table. Only the fractional
# cell matters, so the product is taken modulo 65536 and its high byte is the
# advance: three 8x8 products through the product table, no division.

DIRECTIONS = 1024


def direction_slopes(direction: int) -> tuple[int, int]:
    import math
    angle = direction * math.tau / DIRECTIONS
    cos, sin = math.cos(angle), math.sin(angle)
    def slope(numerator: float, denominator: float) -> int:
        if abs(denominator) < 1e-9:
            return 0xFFFF
        return min(0xFFFF, int(round(256 * abs(numerator) / abs(denominator))))
    return slope(sin, cos), slope(cos, sin)


def make_slope_table() -> bytes:
    out = bytearray()
    for direction in range(DIRECTIONS):
        for value in direction_slopes(direction):
            out += value.to_bytes(2, "little")
    return bytes(out)


def rom_advance(distance_q8: int, slope_q8: int) -> int:
    """High byte of (D * S) mod 65536, as three 8x8 products: the fractional-cell advance."""
    d_l, d_h = distance_q8 & 0xFF, (distance_q8 >> 8) & 0xFF
    s_l, s_h = slope_q8 & 0xFF, (slope_q8 >> 8) & 0xFF
    return (((d_l * s_l) >> 8) + (d_l * s_h) + (d_h * s_l)) & 0xFF


def rom_along(other_q8: int, positive: bool, distance_q8: int, slope_q8: int) -> int:
    advance = rom_advance(distance_q8, slope_q8)
    return ((other_q8 & 0xFF) + advance if positive else (other_q8 & 0xFF) - advance) & 0xFF


def midpoint_u(left: int, right: int) -> int:
    """The midpoint's coordinate between two anchors on one face: the circular
    mean, rounding away from the left anchor."""
    forward = (right - left) & 0xFF
    if forward < 128:
        return (left + ((forward + 1) >> 1)) & 0xFF
    backward = (left - right) & 0xFF
    return (left - ((backward + 1) >> 1)) & 0xFF


@lru_cache(maxsize=1)
def make_stride_class_lut() -> bytes:
    """Delta class for (run length - 1, first-to-last coordinate difference)."""
    out = bytearray()
    for span in range(8):
        for difference in range(256):
            if span == 0:
                out.append(2)  # a single pixel: any stride; class 1/2 is the table's middle
                continue
            stride = Fraction(difference * TEXELS, 256 * span)
            out.append(min(range(len(DELTA_CLASSES)), key=lambda k: abs(DELTA_CLASSES[k] - stride)))
    return bytes(out)


# ----- along-face coordinate per physical pixel -------------------------------

def reference_ray_u(hits: Sequence) -> list[int]:
    """Per-ray texture coordinate, Q8 along the face, from cast hits."""
    return [hit.along_q8 for hit in hits]


def expand_pixel_u(ray_u: list[int], edge_u: dict[int, int]) -> list[int]:
    """Physical-pixel U by the same reconstruction the tops use.

    A pair ray covers two pixels; each is pulled a quarter of the way towards
    its neighbour's ray unless the coordinates wrap (a cell boundary inside
    one face, |difference| >= 128). Face breaks need no test: the two pixels
    beside every pair-level break are recast exactly, and `edge_u` carries
    those recasts' own coordinates. The first pair's previous sample and the
    last pair's following sample are the rays themselves.
    """
    pixel_u = [0] * PHYSICAL_COLUMNS
    for i in range(RAYS):
        current = ray_u[i]
        for output, neighbour in ((i * 2, i - 1), (i * 2 + 1, i + 1)):
            value = current
            if 0 <= neighbour < RAYS:
                other = ray_u[neighbour]
                if abs(other - current) < 128:
                    value = (current * 3 + other + 2) // 4
            pixel_u[output] = value & 0xFF
    for pixel, value in edge_u.items():
        pixel_u[pixel] = value & 0xFF
    return pixel_u


def texel_column(u_q8: int) -> Fraction:
    """Texture column in texels with sub-texel precision from an oriented Q8
    coordinate (the cast already reads east and north faces right to left)."""
    return Fraction(u_q8 * TEXELS, 256)


# The kernel's stride classes in Q8 along-face units: a texel is 16 units.
DELTA_Q8 = tuple(int(delta * TEXELS) for delta in DELTA_CLASSES)   # 2, 4, 8, 16, 32
# A pixel's surface profile picks one texture of its level's set:
# structure, machinery, door. The set is the level's palette set (outpost,
# reactor, spire); every episode shares the door plate.
TEXTURE_SETS = ((0, 1, 2), (3, 4, 2), (5, 6, 2))
PROFILE_TEXTURE = TEXTURE_SETS[0]


def level_texture_set() -> tuple[int, int, int]:
    """The texture set of the level the host oracle follows (the running
    ROM's, via `select_reference_level`); an unknown set reads as the first,
    as the console clamps it."""
    from .layout import reference_level
    index = reference_level().palette_profile
    return TEXTURE_SETS[index] if index < len(TEXTURE_SETS) else TEXTURE_SETS[0]


# ----- what one physical column shows ----------------------------------------

@dataclass(frozen=True)
class TexturedColumn:
    """What one physical pixel column shows: silhouette, face and texture.

    `half` is the height class the column's *run* shares - the tallest pixel
    of the run of one face inside the tile column - which is what selects the
    texture row and the shade; `u` is the texel column, oriented.
    """
    top: int
    style: int
    key: int
    texture: int
    u: Fraction
    half: int


def run_identity(column: TexturedColumn) -> tuple[int, int, int]:
    return column.key, column.texture, column.style & 1


def tile_runs(columns: Sequence[TexturedColumn], first: int) -> list[tuple[int, int]]:
    """Runs of one face inside the tile column starting at physical pixel
    `first`: consecutive pixels with the same face key, surface profile and
    shade bit (style bit 0: decoration can darken single pixels of a face)."""
    runs, start = [], first
    while start < first + 8:
        end = start + 1
        while end < first + 8 and run_identity(columns[end]) == run_identity(columns[start]):
            end += 1
        runs.append((start, end)); start = end
    return runs


def rom_texture_columns(tops: Sequence[int], styles: Sequence[int], keys: Sequence[int],
                        surfaces: Sequence[int], pixel_u: Sequence[int],
                        texture_set: Sequence[int] | None = None) -> list[TexturedColumn]:
    """The 160 columns the console kernel composes, from its own descriptors."""
    texture_set = level_texture_set() if texture_set is None else texture_set
    columns = [TexturedColumn(tops[x], styles[x], keys[x], texture_set[surfaces[x]], texel_column(pixel_u[x]), 0)
               for x in range(PHYSICAL_COLUMNS)]
    for first in range(0, PHYSICAL_COLUMNS, 8):
        for start, end in tile_runs(columns, first):
            half = HORIZON - min(c.top for c in columns[start:end])
            for x in range(start, end):
                c = columns[x]
                columns[x] = TexturedColumn(c.top, c.style, c.key, c.texture, c.u, half)
    return columns


def run_window(run: Sequence[TexturedColumn], start_in_tile: int) -> tuple[int, int]:
    """(stride class, phase index) of one run, by the console's rule.

    The class comes from the run's length and the Q8 difference between its
    last and first coordinates (the stride table); the phase is the quarter
    texel of the coordinate extrapolated back to the tile column's first
    pixel, so the window's texel i is the tile's pixel i and a run needs no
    shifting - only its pixel mask.
    """
    u_q8 = [int(c.u * 16) & 0xFF for c in run]
    span = len(run) - 1
    k = make_stride_class_lut()[span * 256 + ((u_q8[-1] - u_q8[0]) & 0xFF)]
    u0 = (u_q8[0] - start_in_tile * DELTA_Q8[k]) & 0xFF
    return k, u0 >> 2


def affine_columns(columns: Sequence[TexturedColumn]) -> list[TexturedColumn]:
    """Replace each run's texel columns by the affine approximation the
    row-window kernel composes: from the run's class and phase, the tile's
    pixel i shows texel phase/4 + i * delta, modulo the texture width."""
    out: list[TexturedColumn] = list(columns)
    for first in range(0, len(columns), 8):
        for start, end in tile_runs(columns, first):
            k, phase = run_window(columns[start:end], start - first)
            for x in range(start, end):
                c = columns[x]
                u = (Fraction(phase, PHASE_STEPS) + (x - first) * DELTA_CLASSES[k]) % TEXELS
                out[x] = TexturedColumn(c.top, c.style, c.key, c.texture, u, c.half)
    return out


# ----- pixel-level composition ----------------------------------------------

def wall_pixel(textures: Sequence[Texture], column: TexturedColumn, y: int, *, outline: bool = True) -> int:
    """Colour index of world pixel (x, y) for a column: 0 above the wall, the
    one-pixel outline in colour 3 on its top and bottom rows, the shaded
    texel between, and the floor tone below."""
    if y < column.top:
        return 0
    if y >= VIEW_HEIGHT - column.top:
        return 1
    if outline and y in (column.top, VIEW_HEIGHT - 1 - column.top):
        return 3
    v = texel_row(column.half, y) if y < HORIZON else texel_row(column.half, VIEW_HEIGHT - 1 - y)
    texture = textures[column.texture]
    texel = texture.texel(int(column.u) & (TEXELS - 1), v)
    return shade_remap(texture)[shade_set(column.style, column.half)][texel]


def compose_pixels(textures: Sequence[Texture], columns: Sequence[TexturedColumn], *, outline: bool = True,
                   dedup: bool = False) -> tuple[bytes, bytes, int, bool, dict[str, int]]:
    """Pixel-level textured compositor: dynamic tiles, view map, count, overflow, stats.

    Every wall tile is composed in the console's order (columns first, rows
    down); there is no seam atlas. With `dedup`, identical tiles share one
    pattern, which reports what a signature cache could save; the console
    does not do that.
    """
    if len(columns) != PHYSICAL_COLUMNS:
        raise ValueError("160 physical columns expected")
    dynamic = bytearray()
    ids: dict[bytes, int] = {}
    view_map = bytearray([CEILING_TILE] * VIEW_MAP_BYTES)
    stats = {"wall_tiles": 0, "boundary_tiles": 0, "seam_tiles": 0, "unique_tiles": 0}
    overflow = False
    for tile_col in range(20):
        cols = columns[tile_col * 8:tile_col * 8 + 8]
        min_top = min(c.top for c in cols)
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
                        colour = wall_pixel(textures, c, y0 + row, outline=outline)
                        if colour & 1: tile[row * 2] |= 0x80 >> i
                        if colour & 2: tile[row * 2 + 1] |= 0x80 >> i
                stats["wall_tiles"] += 1
                if any(y0 <= c.top < y0 + 8 or y0 <= VIEW_HEIGHT - 1 - c.top < y0 + 8 for c in cols):
                    stats["boundary_tiles"] += 1
                if len({(c.key, c.texture) for c in cols}) > 1:
                    stats["seam_tiles"] += 1
                key = bytes(tile)
                if dedup and key in ids:
                    tile_id = ids[key]
                elif len(dynamic) // 16 >= DYNAMIC_TILE_CAPACITY:
                    overflow = True; tile_id = WALL_TILE_BASE
                else:
                    tile_id = len(dynamic) // 16
                    dynamic.extend(tile); ids.setdefault(key, tile_id)
            view_map[tile_row * 32 + tile_col] = tile_id
            view_map[(VIEW_ROWS - 1 - tile_row) * 32 + tile_col] = tile_id
    stats["unique_tiles"] = len(ids)
    return bytes(dynamic), bytes(view_map), len(dynamic) // 16, overflow, stats


# ----- row-window composition: the kernel --------------------------------------

def make_row_windows(textures: Sequence[Texture]) -> dict[tuple[int, int, int, int, int], tuple[int, ...]]:
    """Every row window: eight texels for (texture, shade, delta class, phase, v)."""
    windows = {}
    for t, texture in enumerate(textures):
        remap = shade_remap(texture)
        for shade in range(SHADE_SETS):
            for k, delta in enumerate(DELTA_CLASSES):
                for phase in range(TEXELS * PHASE_STEPS):
                    u0 = Fraction(phase, PHASE_STEPS)
                    for v in range(TEXEL_ROWS):
                        windows[t, shade, k, phase, v] = tuple(
                            remap[shade][texture.texel(int(u0 + i * delta) & (TEXELS - 1), v)] for i in range(8))
    return windows


def window_table_bytes(texture_count: int) -> int:
    return texture_count * SHADE_SETS * len(DELTA_CLASSES) * TEXELS * PHASE_STEPS * TEXEL_ROWS * 2


def window_planes(texels: Sequence[int]) -> tuple[int, int]:
    plane0 = plane1 = 0
    for i, colour in enumerate(texels):
        if colour & 1: plane0 |= 0x80 >> i
        if colour & 2: plane1 |= 0x80 >> i
    return plane0, plane1


def compose_kernel(textures: Sequence[Texture], columns: Sequence[TexturedColumn], windows: dict,
                   *, outline: bool = True) -> tuple[bytes, bytes, int, bool]:
    """The console kernel, instruction for instruction in spirit: per tile
    column, runs of one face with a pixel mask, a height class, a shade, a
    stride class, a phase and a Q8 row accumulator; per tile row, the eight
    rows' coverage and outline masks; per row and run, one sixteen-byte window
    read at the accumulator's texel row, masked into the two planes. The
    self-mirrored centre tile computes its upper four rows and mirrors them
    with the floor tone under the wall. Tiles are numbered in composition
    order without sharing; the map carries each one twice.
    """
    dynamic = bytearray()
    view_map = bytearray([CEILING_TILE] * VIEW_MAP_BYTES)
    overflow = False
    centre = (FOLDED_ROWS - 1) * 8 if VIEW_ROWS % 2 else None
    for tile_col in range(20):
        first = tile_col * 8
        cols = columns[first:first + 8]
        min_top = min(c.top for c in cols)
        runs = []
        for start, end in tile_runs(columns, first):
            run = columns[start:end]
            top = min(c.top for c in run)
            half = HORIZON - top
            shade = shade_set(run[0].style, half)
            k, phase = run_window(run, start - first)
            cache = [window_planes(windows[run[0].texture, shade, k, phase, v]) for v in range(TEXEL_ROWS)]
            mask = sum(0x80 >> (x - first) for x in range(start, end))
            runs.append({"top": top, "step": row_step(half), "acc": 0, "mask": mask, "cache": cache})
        for tile_row in range(FOLDED_ROWS):
            y0 = tile_row * 8
            if y0 + 7 < min_top:
                tile_id = CEILING_TILE
            elif y0 >= VIEW_HEIGHT - min_top:
                tile_id = FLOOR_TILE
            else:
                tile = bytearray(16)
                rows = 4 if y0 == centre else 8
                for row in range(rows):
                    y = y0 + row
                    cover = sum(0x80 >> i for i, c in enumerate(cols) if c.top <= y)
                    edge = sum(0x80 >> i for i, c in enumerate(cols) if c.top == y) if outline else 0
                    plane0 = plane1 = 0
                    for run in runs:
                        if y < run["top"]:
                            continue
                        v = run["acc"] >> 8
                        run["acc"] += run["step"]
                        p0, p1 = run["cache"][v]
                        plane0 |= p0 & run["mask"]; plane1 |= p1 & run["mask"]
                    plane0 = (plane0 & cover & ~edge) | edge
                    plane1 = (plane1 & cover & ~edge) | edge
                    tile[row * 2], tile[row * 2 + 1] = plane0 & 0xFF, plane1 & 0xFF
                    if rows == 4:
                        mirror = 7 - row
                        tile[mirror * 2], tile[mirror * 2 + 1] = (plane0 | ~cover) & 0xFF, plane1 & 0xFF
                if len(dynamic) // 16 >= DYNAMIC_TILE_CAPACITY:
                    overflow = True; tile_id = WALL_TILE_BASE
                else:
                    tile_id = len(dynamic) // 16
                    dynamic.extend(tile)
            view_map[tile_row * 32 + tile_col] = tile_id
            view_map[(VIEW_ROWS - 1 - tile_row) * 32 + tile_col] = tile_id
    return bytes(dynamic), bytes(view_map), len(dynamic) // 16, overflow


_WINDOWS: dict[int, dict] = {}


def asset_windows() -> tuple[tuple[Texture, ...], dict]:
    """The authored textures and their row windows, built once per process."""
    from .texture_assets import textures
    loaded = textures()
    if id(loaded) not in _WINDOWS:
        _WINDOWS[id(loaded)] = make_row_windows(loaded)
    return loaded, _WINDOWS[id(loaded)]


def reference_compose_textured_view(tops: Sequence[int], styles: Sequence[int], keys: Sequence[int],
                                    surfaces: Sequence[int], pixel_u: Sequence[int]) -> tuple[bytes, bytes, int, bool]:
    """Byte-exact host model of the textured compositor from the console's
    own descriptors: dynamic patterns in composition order, the view map,
    the pattern count and the overflow flag."""
    textures, windows = asset_windows()
    return compose_kernel(textures, rom_texture_columns(tops, styles, keys, surfaces, pixel_u), windows)
