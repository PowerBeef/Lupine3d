"""Geometry-neutral surface profiles and atomic CGB attribute packets."""
from .layout import *  # noqa: F401,F403


def surface_attributes(profiles: list[int], page: int) -> bytes:
    result = bytearray(384)
    for column in range(32):
        group = profiles[column * 8:column * 8 + 8]
        if ENABLE_MICRO_REPROJECTION and column in (20, 31):
            group = profiles[152:160] if column == 20 else profiles[:8]
        profile = group[0] if len(group) == 8 and len(set(group)) == 1 else 0
        upper, lower = ((0, 2), (5, 6), (3, 4))[profile]
        for row in range(12):
            result[row * 32 + column] = (page << 3) | (upper if row < 6 else lower) | (0x40 if FOLDED_COMPOSITOR and row >= 6 else 0)
    return bytes(result)


def emit_surfaces(a: Assembler) -> None:
    a.label("build_surface_attributes")
    a.xor_r("a"); a.ld_abs_a(SURFACE_COLUMN)
    a.label("surface_column_loop")
    a.xor_r("a"); a.ld_abs_a(SURFACE_PROFILE)
    a.ld_a_abs(SURFACE_COLUMN); a.cp_n(20); a.jr("surface_group_ready", "nc")
    a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(3): a.add_hl_rr("hl")
    a.ld_rr_nn("de", PIXEL_SURFACE); a.add_hl_rr("de"); a.ldi_a_hl(); a.ld_abs_a(SURFACE_PROFILE); a.ld_r_r("b", "a"); a.ld_r_n("c", 7)
    a.label("surface_compare_loop")
    a.ldi_a_hl(); a.cp_r("b"); a.jr("surface_mixed", "nz"); a.dec_r("c"); a.jr("surface_compare_loop", "nz"); a.jr("surface_group_ready")
    a.label("surface_mixed"); a.xor_r("a"); a.ld_abs_a(SURFACE_PROFILE)
    a.label("surface_group_ready")
    # Never recolour a neighbouring wall to fill a palette-mixed tile. Mixed
    # eight-pixel groups keep the structural palette and precise silhouettes.
    a.ld_a_abs(SURFACE_PROFILE); a.or_r("a")
    a.ld_r_n("b", 0); a.ld_r_n("c", 2); a.jr("surface_palette_ready", "z")
    a.cp_n(1); a.ld_r_n("b", 5); a.ld_r_n("c", 6); a.jr("surface_palette_ready", "z")
    a.ld_r_n("b", 3); a.ld_r_n("c", 4)
    a.label("surface_palette_ready")
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1)
    for _ in range(3): a.add_a_r("a")
    a.ld_r_r("d", "a"); a.or_r("b"); a.ld_r_r("b", "a")
    a.ld_r_r("a", "d"); a.or_r("c")
    if FOLDED_COMPOSITOR: a.or_n(0x40)
    a.ld_r_r("c", "a")
    a.ld_a_abs(SURFACE_COLUMN); a.ld_r_r("l", "a"); a.ld_r_n("h", VIEW_ATTRIBUTES >> 8)
    a.ld_rr_nn("de", 32)
    for row in range(12):
        a.ld_r_r("a", "b" if row < 6 else "c"); a.ld_hl_a(); a.add_hl_rr("de")
    a.ld_a_abs(SURFACE_COLUMN); a.inc_r("a"); a.ld_abs_a(SURFACE_COLUMN); a.cp_n(32); a.jp("surface_column_loop", "c")
    if ENABLE_MICRO_REPROJECTION:
        for row in range(12):
            a.ld_a_abs(VIEW_ATTRIBUTES + row * 32); a.ld_abs_a(VIEW_ATTRIBUTES + row * 32 + 31)
            a.ld_a_abs(VIEW_ATTRIBUTES + row * 32 + 19); a.ld_abs_a(VIEW_ATTRIBUTES + row * 32 + 20)
    a.ret()

    a.label("upload_surface_attributes")
    a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.ld_r_n("a", VIEW_ATTRIBUTES >> 8); a.ldh_n_a(HDMA1)
    a.xor_r("a"); a.ldh_n_a(HDMA2); a.ldh_n_a(HDMA4)
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.or_r("a"); a.ld_r_n("a", 0x18); a.jr("surface_upload_page", "z"); a.ld_r_n("a", 0x1C)
    a.label("surface_upload_page"); a.ldh_n_a(HDMA3); a.ld_r_n("a", 23); a.ldh_n_a(HDMA5); a.ret()
