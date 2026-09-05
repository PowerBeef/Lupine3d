"""Sliding doors are finite segments at the centre of their authored cell.

Fraction F exposes [0,F) along the panel; the remaining [F,256) is solid.
The panel translates into its positive-axis jamb. No projected-height trick.
"""
from .layout import *  # noqa: F401,F403


def door_intersection(px: int, py: int, dx: int, dy: int, x: int, y: int,
                      orientation: int, fraction: int) -> int | None:
    origin, normal = (px, dx) if orientation == 0 else (py, dy)
    parallel_origin, parallel = (py, dy) if orientation == 0 else (px, dx)
    cell, parallel_cell = (x, y) if orientation == 0 else (y, x)
    delta = (cell * 256 + 128 - origin) * (1 if normal >= 0 else -1)
    if not normal or delta < 0:
        return None
    displacement = delta * abs(parallel) // abs(normal)
    coordinate = parallel_origin + displacement * (1 if parallel >= 0 else -1)
    if coordinate >> 8 != parallel_cell or coordinate & 255 < fraction:
        return None
    return delta


def emit_door_geometry(a: Assembler) -> None:
    a.label("door_ray_hit")
    a.ld_a_abs(WORLD_MODE); a.or_r("a"); a.jp("door_ray_solid", "z")
    a.ld_a_abs(Q14_LOADED); a.or_r("a"); a.jr("door_ray_components_ready", "nz")
    a.ld_a_abs(Q14_RECORD); a.cp_n(255); a.jp("door_ray_solid", "z")
    a.call("q14_load_door_components")
    a.label("door_ray_components_ready")
    a.ld_a_abs(DDA_MAP_X); a.ld_r_r("b", "a")
    a.ld_a_abs(DDA_MAP_Y); a.ld_r_r("c", "a"); a.call("lookup_door_bc")
    a.or_r("a"); a.jp("door_ray_solid", "z")
    a.ld_a_abs(DOOR_ACTIVE_STATE); a.cp_n(2); a.jp("door_ray_clear", "z")
    a.ld_a_abs(DOOR_ACTIVE_ORIENTATION); a.or_r("a"); a.jp("door_ray_y", "nz")
    for name, normal, parallel, step, parallel_step, cell, parallel_cell, origin, parallel_origin in (
        ("x", Q14_X, Q14_Y, DDA_STEP_X, DDA_STEP_Y, DDA_MAP_X, DDA_MAP_Y, PLAYER_XL, PLAYER_YL),
        ("y", Q14_Y, Q14_X, DDA_STEP_Y, DDA_STEP_X, DDA_MAP_Y, DDA_MAP_X, PLAYER_YL, PLAYER_XL),
    ):
        a.label(f"door_ray_{name}")
        load_hl_abs(a, normal, normal + 1)
        a.ld_r_r("a", "h"); a.or_r("l"); a.jp("door_ray_clear", "z")
        store_hl_abs(a, DOOR_DIVISOR, DOOR_DIVISOR + 1)
        # Signed centre-plane delta, then orient it along the ray.
        a.ld_r_n("a", 128); a.ld_r_r("b", "a"); a.ld_a_abs(origin); a.ld_r_r("c", "a")
        a.ld_r_r("a", "b"); a.sub_r("c"); a.ld_r_r("l", "a")
        a.ld_a_abs(origin + 1); a.ld_r_r("b", "a"); a.ld_a_abs(cell); a.sbc_a_r("b"); a.ld_r_r("h", "a")
        a.ld_a_abs(step); a.cp_n(255); a.jr(f"door_delta_{name}_positive", "nz"); a.call("negate_hl")
        a.label(f"door_delta_{name}_positive")
        a.cb("bit", "h", 7); a.jp("door_ray_clear", "nz")
        store_hl_abs(a, DOOR_PLANE_DISTANCE, DOOR_PLANE_DISTANCE + 1)
        a.ld_a_abs(parallel); a.ld_r_r("e", "a"); a.ld_a_abs(parallel + 1); a.ld_r_r("d", "a")
        a.call("q14_multiply_u16")
        a.ld_a_abs(DOOR_DIVISOR); a.ld_r_r("e", "a"); a.ld_a_abs(DOOR_DIVISOR + 1); a.ld_r_r("d", "a")
        a.call("divide_u32_u16_bounded")
        a.ld_a_abs(Q14_PRODUCT + 3); a.ld_r_r("b", "a"); a.ld_a_abs(Q14_PRODUCT + 2); a.or_r("b"); a.jp("door_ray_clear", "nz")
        a.ld_a_abs(Q14_PRODUCT + 1); a.cp_n(16); a.jp("door_ray_clear", "nc")
        load_hl_abs(a, Q14_PRODUCT, Q14_PRODUCT + 1)
        a.ld_a_abs(parallel_step); a.cp_n(255); a.jr(f"door_parallel_{name}_positive", "nz"); a.call("negate_hl")
        a.label(f"door_parallel_{name}_positive")
        a.ld_a_abs(parallel_origin); a.ld_r_r("e", "a"); a.ld_a_abs(parallel_origin + 1); a.ld_r_r("d", "a"); a.add_hl_rr("de")
        a.ld_a_abs(parallel_cell); a.cp_r("h"); a.jp("door_ray_clear", "nz")
        a.ld_a_abs(DOOR_ACTIVE_FRACTION); a.cp_r("l"); a.jp("door_ray_plane_solid", "z"); a.jp("door_ray_clear", "nc")
        a.jp("door_ray_plane_solid")
    a.label("door_ray_plane_solid")
    a.ld_a_abs(DOOR_ACTIVE_ORIENTATION); a.ld_abs_a(DDA_AXIS)
    a.ld_a_abs(DOOR_PLANE_DISTANCE); a.ld_abs_a(DDA_DIST_L)
    a.ld_a_abs(DOOR_PLANE_DISTANCE + 1); a.ld_abs_a(DDA_DIST_H)
    a.label("door_ray_solid"); a.ld_r_n("a", 3); a.or_r("a"); a.ret()
    a.label("door_ray_clear"); a.xor_r("a"); a.ret()

    a.label("collision_cell_bc")
    # Full-height walls use the existing grid query. A door uses its finite
    # centre-plane panel, expanded by the same radius as player collision.
    a.call("map_cell_bc"); a.cp_n(3); a.ret("nz")
    a.call("lookup_door_bc"); a.or_r("a"); a.jp("door_ray_solid", "z")
    a.ld_a_abs(DOOR_ACTIVE_STATE); a.cp_n(2); a.jp("door_ray_clear", "z")
    a.ld_a_abs(DOOR_ACTIVE_ORIENTATION); a.or_r("a"); a.jp("collision_door_y", "nz")
    for name, normal, parallel, cell, parallel_cell in (
        ("x", COLLISION_X, COLLISION_Y, DOOR_LOOKUP_X, DOOR_LOOKUP_Y),
        ("y", COLLISION_Y, COLLISION_X, DOOR_LOOKUP_Y, DOOR_LOOKUP_X),
    ):
        a.label(f"collision_door_{name}")
        # Signed distance from centre plane, converted to absolute Q8.
        a.ld_a_abs(normal); a.sub_n(128); a.ld_r_r("l", "a")
        a.ld_a_abs(cell); a.ld_r_r("b", "a"); a.ld_a_abs(normal + 1); a.sbc_a_r("b"); a.ld_r_r("h", "a")
        a.cb("bit", "h", 7); a.jr(f"collision_door_{name}_positive", "z"); a.call("negate_hl")
        a.label(f"collision_door_{name}_positive")
        a.ld_r_r("a", "h"); a.or_r("a"); a.jp("door_ray_clear", "nz")
        a.ld_r_r("a", "l"); a.cp_n(PLAYER_RADIUS_Q8 + 1); a.jp("door_ray_clear", "nc")
        # The upper along-panel extent must stay strictly below F to pass.
        a.ld_a_abs(parallel); a.add_a_n(PLAYER_RADIUS_Q8); a.ld_r_r("l", "a")
        a.ld_a_abs(parallel + 1); a.adc_a_n(0); a.ld_r_r("h", "a")
        a.ld_a_abs(parallel_cell); a.cp_r("h")
        a.jr(f"collision_door_{name}_same_cell", "z")
        a.jp("door_ray_solid", "c"); a.jp("door_ray_clear")
        a.label(f"collision_door_{name}_same_cell")
        a.ld_a_abs(DOOR_ACTIVE_FRACTION); a.cp_r("l"); a.jp("door_ray_solid", "z")
        a.jp("door_ray_clear", "nc"); a.jp("door_ray_solid")
