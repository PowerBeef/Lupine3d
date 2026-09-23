"""The textured-wall compositor: SM83 emission of `texture_reference.compose_kernel`.

Under the textured profile every wall tile is composed; there is no seam
atlas. A tile column is split into runs of one face (same face key, surface
profile and shade bit), each with a height class (its tallest pixel), a
shade set, a stride class and a phase. Those four select one sixteen-byte
row window - the eight texels of every texture row - which the column setup
copies from its ROM bank into a WRAM cache once per run and column. A tile
row is then one cache read at the run's Q8 row accumulator, masked by the
run's pixels and, on boundary tiles, by the row's coverage and outline.

Two code paths share one contract:
* the **resident** part (`emit_textured_kernel`) switches ROM banks - the
  step, stride and window tables live in banks 247 and 248+ - and so stays
  below $4000; it also owns the ring's HBlank hand-off and the LCD-off flush;
* the **cold** part (`emit_textured_compositor`) is bank-neutral: the row
  kernel, the mask passes, the seam merge and the centre-tile mirror.

Dynamic patterns are numbered in composition order (0..237 in VRAM: ids
below 128 at $9000, the rest at $8800) and composed into a 96-slot ring in
fixed WRAM that HBlank DMA drains in chunks that never cross the ring wrap or
the VRAM half; a tile waits on the transfer only when it would lap a slot
still in flight. With the LCD off the ring is flushed synchronously into
both VRAM banks, so `enter_world` needs no separate pattern upload.
"""
from __future__ import annotations

from .layout import *  # noqa: F401,F403
from .texture_assets import block_directory
from .texture_reference import MID_HALF, NEAR_HALF, TEXEL_ROWS

# Record fields (TEX_RUN_BYTES wide). START/LAST/SURF/SHADE are only read
# by the setup, which then overwrites them with the accumulator and step.
R_TOP, R_MASK, R_CACHE_L, R_ACC_L, R_ACC_H, R_STEP_L, R_STEP_H = range(7)
R_START, R_LAST, R_SURF, R_SHADE = 3, 4, 5, 6
CENTRE_Y0 = (FOLDED_ROWS - 1) * 8            # the self-mirrored centre tile row
VRAM_HALF = 128                              # ids from here live at $8800


def load_hram_pair(a, low: int, high: int, pair: str) -> None:
    lo, hi = pair[1], pair[0]
    a.ld_a_abs(low); a.ld_r_r(lo, "a"); a.ld_a_abs(high); a.ld_r_r(hi, "a")


def emit_textured_kernel(a) -> None:
    """Resident: column setup (bank switches), ring hand-off, flushes."""
    from .texture_reference import TEXTURE_SETS
    assert len(TEXTURE_SETS) == PALETTE_SET_COUNT and TEXTURE_SET_DIRECTORY_BYTES == 36
    a.label("tex_block_directory")
    a.bytes(block_directory(TEXTURE_WINDOW_BANKS), text="texture window blocks per set: bank, address")

    # ----- tex_column_runs: the tile column's runs and their window caches -----
    # In: COLUMN_COUNT (20 down to 1), MIN_TOP. Clobbers everything.
    a.label("tex_column_runs")
    a.ld_a_abs(COLUMN_COUNT); a.ld_r_r("b", "a"); a.ld_r_n("a", 20); a.sub_r("b")
    for _ in range(3): a.add_a_r("a")
    a.ld_abs_a(TEX_COL_OFFSET); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    # One face across the column is the common case: three equality walks
    # with an early exit decide it before any change bit is built.
    a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de")
    for _ in range(7): a.ldi_a_hl(); a.cp_r("(hl)"); a.jr("tex_runs_bits", "nz")
    a.ld_rr_nn("hl", PIXEL_SURFACE); a.add_hl_rr("de")
    for _ in range(7): a.ldi_a_hl(); a.cp_r("(hl)"); a.jr("tex_runs_bits", "nz")
    a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de")
    for _ in range(7): a.ldi_a_hl(); a.xor_r("(hl)"); a.and_n(1); a.jr("tex_runs_bits", "nz")
    a.jp("tex_runs_single")
    # Change bits between neighbouring pixels: pixel 7 in bit 0 .. pixel 1 in
    # bit 6, over the face key, the surface profile and the shade bit.
    a.label("tex_runs_bits")
    a.ld_rr_nn("hl", PIXEL_KEYS); a.add_hl_rr("de"); a.ld_r_n("c", 0)
    for _ in range(7): a.ldi_a_hl(); a.sub_r("(hl)"); a.add_a_n(0xFF); a.cb("rl", "c")
    a.ld_rr_nn("hl", PIXEL_SURFACE); a.add_hl_rr("de"); a.ld_r_n("b", 0)
    for _ in range(7): a.ldi_a_hl(); a.sub_r("(hl)"); a.add_a_n(0xFF); a.cb("rl", "b")
    a.ld_r_r("a", "b"); a.or_r("c"); a.ld_r_r("c", "a")
    a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_r_n("b", 0)
    for _ in range(7): a.ldi_a_hl(); a.xor_r("(hl)"); a.and_n(1); a.add_a_n(0xFF); a.cb("rl", "b")
    a.ld_r_r("a", "b"); a.or_r("c"); a.ld_r_r("c", "a")
    a.or_r("a"); a.jp("tex_runs_general", "nz")
    # One face across the column: the record is immediate.
    a.label("tex_runs_single")
    a.ld_rr_nn("hl", TEX_RUNS)
    a.ld_a_abs(MIN_TOP); a.ldi_hl_a()                       # TOP
    a.ld_r_n("a", 0xFF); a.ldi_hl_a()                       # MASK
    a.ld_r_n("a", TEX_WINDOWS & 0xFF); a.ldi_hl_a()         # CACHE_L
    a.xor_r("a"); a.ldi_hl_a()                              # START
    a.ld_r_n("a", 7); a.ldi_hl_a()                          # LAST
    a.push("hl"); a.ld_rr_nn("hl", PIXEL_SURFACE); a.add_hl_rr("de"); a.ld_a_hl(); a.pop("hl"); a.ldi_hl_a()
    a.push("hl"); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_a_hl(); a.pop("hl"); a.and_n(1); a.ldi_hl_a()
    a.ld_r_n("a", 1); a.ld_abs_a(TEX_RUN_COUNT)
    a.jp("tex_setup_runs")

    a.label("tex_runs_general")
    a.cb("sla", "c")                                         # pixel 1's change bit into bit 7
    a.ld_rr_nn("hl", PIXEL_TOPS); a.add_hl_rr("de")
    a.ld_r_n("d", 0x80); a.ld_r_n("e", 0)                    # D = pixel bit, E = pixel index
    a.xor_r("a"); a.ld_abs_a(TEX_RUN_COUNT)
    a.ld_r_n("a", (TEX_RUNS - TEX_RUN_BYTES) & 0xFF); a.ld_abs_a(TEX_REC_L)
    a.ld_r_n("a", (TEX_RUNS - TEX_RUN_BYTES) >> 8); a.ld_abs_a(TEX_REC_H)
    a.jr("tex_run_start")
    a.label("tex_run_pixel")
    a.cb("sla", "c"); a.jr("tex_run_extend", "nc")
    a.label("tex_run_start")
    a.push("hl"); a.push("de")
    a.ld_a_abs(TEX_REC_L); a.add_a_n(TEX_RUN_BYTES); a.ld_abs_a(TEX_REC_L); a.ld_r_r("l", "a")
    a.ld_a_abs(TEX_REC_H); a.ld_r_r("h", "a")
    a.ld_r_n("a", 0xFF); a.ldi_hl_a()                       # TOP: the minimum so far
    a.xor_r("a"); a.ldi_hl_a()                              # MASK
    a.ld_a_abs(TEX_RUN_COUNT); a.cb("swap", "a"); a.add_a_n(TEX_WINDOWS & 0xFF); a.ldi_hl_a()   # CACHE_L = base + run*16
    a.ld_r_r("a", "e"); a.ldi_hl_a(); a.ldi_hl_a()           # START, LAST
    a.ld_a_abs(TEX_COL_OFFSET); a.add_a_r("e"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.push("hl"); a.ld_rr_nn("hl", PIXEL_SURFACE); a.add_hl_rr("de"); a.ld_a_hl(); a.pop("hl"); a.ldi_hl_a()
    a.push("hl"); a.ld_rr_nn("hl", PIXEL_STYLES); a.add_hl_rr("de"); a.ld_a_hl(); a.pop("hl"); a.and_n(1); a.ldi_hl_a()
    a.ld_a_abs(TEX_RUN_COUNT); a.inc_r("a"); a.ld_abs_a(TEX_RUN_COUNT)
    a.pop("de"); a.pop("hl")
    a.label("tex_run_extend")
    a.ld_a_hl(); a.ld_r_r("b", "a")                          # this pixel's top
    a.push("hl")
    load_hram_pair(a, TEX_REC_L, TEX_REC_H, "hl")
    a.ld_a_hl(); a.cp_r("b"); a.jr("tex_run_top_kept", "c"); a.ld_r_r("a", "b"); a.ld_hl_a()
    a.label("tex_run_top_kept"); a.inc_rr("hl")
    a.ld_a_hl(); a.or_r("d"); a.ldi_hl_a()                   # MASK |= pixel
    a.inc_rr("hl"); a.inc_rr("hl"); a.ld_r_r("a", "e"); a.ld_hl_a()   # LAST = pixel
    a.pop("hl"); a.inc_rr("hl")
    a.cb("rrc", "d"); a.inc_r("e"); a.ld_r_r("a", "e"); a.cp_n(8); a.jr("tex_run_pixel", "nz")
    # fall through

    # ----- tex_setup_runs: shade, tables and the window cache of every run -----
    a.label("tex_setup_runs")
    a.ld_r_n("a", TEX_RUNS & 0xFF); a.ld_abs_a(TEX_REC_L); a.ld_r_n("a", TEX_RUNS >> 8); a.ld_abs_a(TEX_REC_H)
    a.ld_a_abs(TEX_RUN_COUNT); a.ld_abs_a(TEX_LOOP)
    a.label("tex_setup_loop")
    load_hram_pair(a, TEX_REC_L, TEX_REC_H, "hl")
    # half = HORIZON - TOP -> TEX_TMP0 and C
    a.ld_a_hl(); a.ld_r_r("b", "a"); a.ld_r_n("a", HORIZON); a.sub_r("b"); a.ld_abs_a(TEX_TMP0); a.ld_r_r("c", "a")
    # shade: the dark side is set 3; else near/mid/far by half
    a.ld_rr_nn("de", R_SHADE); a.add_hl_rr("de"); a.ld_a_hl(); a.or_r("a"); a.ld_r_n("a", 3); a.jr("tex_shade_ready", "nz")
    a.ld_r_r("a", "c"); a.cp_n(NEAR_HALF); a.ld_r_n("a", 0); a.jr("tex_shade_ready", "nc")
    a.ld_r_r("a", "c"); a.cp_n(MID_HALF); a.ld_r_n("a", 1); a.jr("tex_shade_ready", "nc")
    a.ld_r_n("a", 2)
    a.label("tex_shade_ready"); a.ld_abs_a(TEX_TMP1)
    # directory entry = (SURF*4 + shade) * 3 -> bank in TEX_TMP2, address in DE
    a.dec_rr("hl"); a.ld_a_hl(); a.add_a_r("a"); a.add_a_r("a"); a.ld_r_r("b", "a")
    a.ld_a_abs(TEX_TMP1); a.add_a_r("b"); a.ld_r_r("b", "a"); a.add_a_r("a"); a.add_a_r("b")
    # The level's texture set: `load_level` points TEX_DIRECTORY at it.
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_a_abs(TEX_DIRECTORY_L); a.ld_r_r("l", "a"); a.ld_a_abs(TEX_DIRECTORY_H); a.ld_r_r("h", "a"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_abs_a(TEX_TMP2)
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.push("de")
    # bank 247: the row step of this half, then the stride class
    a.ld_r_n("a", TEXTURE_LUT_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_a_abs(TEX_TMP0); a.add_a_r("a"); a.ld_r_r("l", "a"); a.ld_r_n("h", TEXTURE_STEP_OFFSET >> 8)
    a.ldi_a_hl(); a.ld_abs_a(TEX_TMP3); a.ld_a_hl(); a.ld_abs_a(TEX_TMP4)
    load_hram_pair(a, TEX_REC_L, TEX_REC_H, "hl"); a.ld_rr_nn("de", R_START); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("c", "a"); a.ld_a_hl(); a.ld_r_r("b", "a")          # C = START, B = LAST
    a.ld_a_abs(TEX_COL_OFFSET); a.add_a_r("c"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_nn("hl", PIXEL_U); a.add_hl_rr("de"); a.ld_a_hl(); a.ld_abs_a(TEX_TMP0)   # u_first
    a.ld_a_abs(TEX_COL_OFFSET); a.add_a_r("b"); a.ld_r_r("e", "a")
    a.ld_rr_nn("hl", PIXEL_U); a.add_hl_rr("de"); a.ld_a_hl()                       # u_last
    a.ld_r_r("e", "a"); a.ld_a_abs(TEX_TMP0); a.ld_r_r("d", "a"); a.ld_r_r("a", "e"); a.sub_r("d"); a.ld_r_r("l", "a")
    a.ld_r_r("a", "b"); a.sub_r("c"); a.add_a_n(TEXTURE_STRIDE_LUT_OFFSET >> 8); a.ld_r_r("h", "a")
    a.ld_a_hl(); a.ld_abs_a(TEX_TMP1)                                                # k
    # phase = (u_first - START << (k + 1)) >> 2
    a.ld_r_r("b", "a"); a.inc_r("b"); a.ld_r_r("a", "c")
    a.label("tex_phase_shift"); a.add_a_r("a"); a.dec_r("b"); a.jr("tex_phase_shift", "nz")
    a.ld_r_r("d", "a"); a.ld_a_abs(TEX_TMP0); a.sub_r("d"); a.cb("srl", "a"); a.cb("srl", "a")
    # window = block + k * 1024 + phase * 16
    a.pop("de")
    a.cb("swap", "a"); a.ld_r_r("c", "a"); a.and_n(0xF0); a.add_a_r("e"); a.ld_r_r("e", "a")
    a.ld_r_r("a", "c"); a.and_n(0x0F); a.adc_a_r("d"); a.ld_r_r("d", "a")
    a.ld_a_abs(TEX_TMP1); a.add_a_r("a"); a.add_a_r("a"); a.add_a_r("d"); a.ld_r_r("d", "a")
    # the run's cache address, then the copy from the window bank
    a.push("de"); load_hram_pair(a, TEX_REC_L, TEX_REC_H, "hl"); a.inc_rr("hl"); a.inc_rr("hl"); a.ld_a_hl(); a.pop("hl")
    a.ld_r_r("e", "a"); a.ld_r_n("d", TEX_WINDOWS >> 8)
    a.ld_a_abs(TEX_TMP2); a.ld_abs_a(0x2000)
    a.push("de"); a.call("copy_16"); a.pop("de")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    # The accumulator's high byte is the cache row address: it starts at
    # the cache itself (row 0) and each texture row advances it by one.
    load_hram_pair(a, TEX_REC_L, TEX_REC_H, "hl"); a.ld_rr_nn("de", R_ACC_L); a.add_hl_rr("de")
    a.xor_r("a"); a.ldi_hl_a(); a.ld_r_r("a", "e"); a.ldi_hl_a()
    a.ld_a_abs(TEX_TMP3); a.ldi_hl_a(); a.ld_a_abs(TEX_TMP4); a.ld_hl_a()
    a.ld_a_abs(TEX_REC_L); a.add_a_n(TEX_RUN_BYTES); a.ld_abs_a(TEX_REC_L)
    a.ld_a_abs(TEX_LOOP); a.dec_r("a"); a.ld_abs_a(TEX_LOOP); a.jp("tex_setup_loop", "nz")
    a.ret()

    # ----- the ring's transfers -------------------------------------------------
    # tex_chunk_bounds: B = blocks of the next chunk (Z and B=0 when nothing
    # is pending), C = its first pattern. A chunk stops at the ring wrap and at
    # the VRAM half so both its source and its destination stay contiguous.
    a.label("tex_chunk_bounds")
    a.ld_a_abs(DYN_STREAMED); a.ld_r_r("c", "a"); a.ld_a_abs(DYN_COUNT); a.sub_r("c"); a.ld_r_r("b", "a"); a.ret("z")
    a.ld_r_r("a", "c"); a.cp_n(DYNAMIC_RING_SLOTS); a.ld_r_n("a", DYNAMIC_RING_SLOTS); a.jr("tex_chunk_limit", "c")
    a.ld_r_r("a", "c"); a.cp_n(VRAM_HALF); a.ld_r_n("a", VRAM_HALF); a.jr("tex_chunk_limit", "c")
    a.ld_r_n("a", 2 * DYNAMIC_RING_SLOTS)
    a.label("tex_chunk_limit"); a.sub_r("c"); a.cp_r("b"); a.jr("tex_chunk_ready", "nc"); a.ld_r_r("b", "a")
    a.label("tex_chunk_ready"); a.ld_r_r("a", "b"); a.or_r("a"); a.ret()

    # tex_chunk_registers: HDMA1-4 for the chunk (B, C); clobbers A, D.
    a.label("tex_chunk_registers")
    a.ld_r_r("a", "c"); a.cp_n(DYNAMIC_RING_SLOTS); a.jr("tex_chunk_slot", "c"); a.sub_n(DYNAMIC_RING_SLOTS)
    a.label("tex_chunk_slot")
    a.ld_r_r("d", "a"); a.cb("swap", "a"); a.and_n(0x0F); a.add_a_n(DYNAMIC_TILES >> 8); a.ldh_n_a(HDMA1)
    a.ld_r_r("a", "d"); a.cb("swap", "a"); a.and_n(0xF0); a.ldh_n_a(HDMA2)
    a.ld_r_r("a", "c"); a.cp_n(VRAM_HALF); a.jr("tex_chunk_low_half", "c")
    a.sub_n(VRAM_HALF); a.ld_r_r("d", "a"); a.cb("swap", "a"); a.and_n(0x0F); a.add_a_n(0x08); a.jr("tex_chunk_dest")
    a.label("tex_chunk_low_half"); a.ld_r_r("d", "a"); a.cb("swap", "a"); a.and_n(0x0F); a.add_a_n(0x10)
    a.label("tex_chunk_dest"); a.ldh_n_a(HDMA3); a.ld_r_r("a", "d"); a.cb("swap", "a"); a.and_n(0xF0); a.ldh_n_a(HDMA4)
    a.ret()

    # tex_stream_hblank: hand the next chunk to HBlank DMA into the hidden
    # bank. Requires the LCD on and HDMA idle; a no-op when nothing is pending.
    a.label("tex_stream_hblank")
    a.call("tex_chunk_bounds"); a.ret("z")
    a.call("tex_chunk_registers")
    a.ld_r_r("a", "c"); a.ld_abs_a(DYN_INFLIGHT); a.add_a_r("b"); a.ld_abs_a(DYN_STREAMED)
    a.ld_a_abs(CURRENT_PAGE); a.xor_n(1); a.ldh_n_a(VBK)
    a.ld_r_r("a", "b"); a.dec_r("a"); a.or_n(0x80); a.ldh_n_a(HDMA5); a.ret()

    # tex_flush_gdma: with the LCD off, move every pending pattern into both
    # VRAM banks by general-purpose DMA, chunk by chunk, synchronously.
    a.label("tex_flush_gdma")
    a.call("tex_chunk_bounds"); a.ret("z")
    a.push("bc"); a.call("tex_chunk_registers"); a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_r_r("a", "b"); a.dec_r("a"); a.ldh_n_a(HDMA5); a.pop("bc")
    a.push("bc"); a.call("tex_chunk_registers"); a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.ld_r_r("a", "b"); a.dec_r("a"); a.ldh_n_a(HDMA5); a.pop("bc")
    a.ld_r_r("a", "c"); a.add_a_r("b"); a.ld_abs_a(DYN_STREAMED); a.ld_abs_a(DYN_INFLIGHT)
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.jr("tex_flush_gdma")

    # tex_ring_wait: before pattern DYN_COUNT is composed into its slot, the
    # pattern that used the slot 96 ago must have reached VRAM.
    a.label("tex_ring_wait")
    a.ld_a_abs(DYN_COUNT); a.sub_n(DYNAMIC_RING_SLOTS); a.ret("c")
    a.ld_r_r("c", "a")
    a.label("tex_ring_again")
    a.ldh_a_n(LCDC); a.rla(); a.jr("tex_ring_lcd_off", "nc")
    a.ldh_a_n(HDMA5); a.rla(); a.jr("tex_ring_idle", "c")
    a.ld_a_abs(DYN_INFLIGHT); a.ld_r_r("b", "a"); a.ld_r_r("a", "c"); a.cp_r("b"); a.ret("c")   # below the transfer: landed
    a.call("stream_wait_idle"); a.jr("tex_ring_again")
    a.label("tex_ring_idle")
    a.ld_a_abs(DYN_STREAMED); a.ld_r_r("b", "a"); a.ld_r_r("a", "c"); a.cp_r("b"); a.ret("c")   # streamed and idle: landed
    a.push("bc"); a.call("tex_stream_hblank"); a.pop("bc"); a.jr("tex_ring_again")
    a.label("tex_ring_lcd_off")
    a.jp("tex_flush_gdma")


def emit_textured_column(a) -> None:
    """Inline in render_view: one tile column, replacing the folded column."""
    a.call("tex_column_runs")
    a.ld_a_abs(TEX_RUN_COUNT); a.dec_r("a"); a.jr("tex_column_multi", "nz")
    a.call("tex_column_single"); a.jp("tex_column_map")
    a.label("tex_column_multi")
    for row in range(FOLDED_ROWS):
        y0 = row * 8
        a.ld_r_n("a", y0); a.ld_abs_a(TILE_Y0)
        a.ld_a_abs(MIN_TOP); a.cp_n(y0 + 8); a.jr(f"tex_row_{row}_compose", "c")
        a.ld_r_n("a", CEILING_TILE); a.jr(f"tex_row_{row}_write")
        a.label(f"tex_row_{row}_compose"); a.call("tex_compose_tile")
        a.label(f"tex_row_{row}_write"); a.ld_abs_a(COLUMN_ROWS + row)
    a.label("tex_column_map")
    load_hram_pair(a, COLUMN_MAP_L, COLUMN_MAP_H, "hl"); a.ld_rr_nn("de", 32)
    for row in range(FOLDED_ROWS):
        if row: a.add_hl_rr("de")
        a.ld_a_abs(COLUMN_ROWS + row); a.ld_hl_a()
    for row in range(VIEW_ROWS - 1 - FOLDED_ROWS, -1, -1):
        a.add_hl_rr("de"); a.ld_a_abs(COLUMN_ROWS + row); a.ld_hl_a()


def emit_textured_compositor(a) -> None:
    """Cold (bank-neutral): the tile kernel, masks, seam merge and mirror."""
    # ----- tex_compose_tile: pattern DYN_COUNT from the column's runs; A = id -----
    a.label("tex_compose_tile")
    a.call("tex_ring_wait")
    a.ld_a_abs(MAX_TOP); a.ld_r_r("b", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("b")
    a.jr("tex_tile_boundary", "c"); a.jr("tex_tile_boundary", "z")
    a.ld_r_n("a", 1); a.ld_abs_a(TEX_INTERIOR); a.jr("tex_tile_runs")
    a.label("tex_tile_boundary")
    a.xor_r("a"); a.ld_abs_a(TEX_INTERIOR); a.call("tex_mask_tables")
    a.label("tex_tile_runs")
    a.ld_a_abs(DYN_PTR_L); a.ld_abs_a(TEX_DST_L); a.ld_a_abs(DYN_PTR_H); a.ld_abs_a(TEX_DST_H)
    a.ld_a_abs(TEX_RUN_COUNT); a.cp_n(1); a.jr("tex_tile_multi", "nz")
    a.ld_rr_nn("hl", TEX_RUNS); a.call("tex_compose_run"); a.jp("tex_tile_masks")
    a.label("tex_tile_multi")
    # The first run composes straight into the slot and keeps its own pixels;
    # if it starts below this tile the slot is cleared instead. Every later
    # run composes into the scratch tile and is merged under its mask.
    a.dec_r("a"); a.ld_abs_a(TEX_LOOP)
    a.ld_rr_nn("hl", TEX_RUNS); a.call("tex_compose_run")
    load_hram_pair(a, DYN_PTR_L, DYN_PTR_H, "hl")
    a.jr("tex_tile_first_absent", "c")
    a.ld_a_abs(TEX_RUNS + R_MASK); a.ld_r_r("b", "a")
    for _ in range(16): a.ld_a_hl(); a.and_r("b"); a.ldi_hl_a()
    a.jr("tex_tile_first_done")
    a.label("tex_tile_first_absent")
    a.xor_r("a")
    for _ in range(16): a.ldi_hl_a()
    a.label("tex_tile_first_done")
    a.ld_r_n("a", STRIP_SCRATCH & 0xFF); a.ld_abs_a(TEX_DST_L); a.ld_r_n("a", STRIP_SCRATCH >> 8); a.ld_abs_a(TEX_DST_H)
    a.ld_rr_nn("hl", TEX_RUNS + TEX_RUN_BYTES)
    a.label("tex_tile_multi_loop")
    a.push("hl"); a.call("tex_compose_run"); a.pop("hl")
    a.jr("tex_tile_multi_next", "c")                          # the run starts below this tile
    # slot |= scratch & MASK
    a.push("hl"); a.inc_rr("hl"); a.ld_a_hl(); a.ld_r_r("b", "a")
    load_hram_pair(a, DYN_PTR_L, DYN_PTR_H, "hl"); a.ld_rr_nn("de", STRIP_SCRATCH)
    for _ in range(16): a.ld_a_mem_rr("de"); a.and_r("b"); a.or_r("(hl)"); a.ldi_hl_a(); a.inc_r("e")
    a.pop("hl")
    a.label("tex_tile_multi_next")
    a.ld_rr_nn("de", TEX_RUN_BYTES); a.add_hl_rr("de")
    a.ld_a_abs(TEX_LOOP); a.dec_r("a"); a.ld_abs_a(TEX_LOOP); a.jp("tex_tile_multi_loop", "nz")
    a.label("tex_tile_masks")
    a.ld_a_abs(TEX_INTERIOR); a.or_r("a"); a.jr("tex_tile_centre", "nz")
    load_hram_pair(a, DYN_PTR_L, DYN_PTR_H, "hl"); a.call("tex_apply_masks")
    a.label("tex_tile_centre")
    a.ld_a_abs(TILE_Y0); a.cp_n(CENTRE_Y0); a.jr("tex_tile_done", "nz")
    load_hram_pair(a, DYN_PTR_L, DYN_PTR_H, "hl"); a.call("tex_mirror_centre")
    a.label("tex_tile_done")
    a.ld_a_abs(DYN_COUNT); a.ld_abs_a(TILE_ID_RESULT); a.inc_r("a"); a.ld_abs_a(DYN_COUNT)
    a.ld_r_r("b", "a"); a.ld_a_abs(DYN_HIGH_WATER); a.cp_r("b"); a.jr("tex_tile_high_kept", "nc"); a.ld_r_r("a", "b"); a.ld_abs_a(DYN_HIGH_WATER)
    a.label("tex_tile_high_kept")
    a.ld_a_abs(DYN_PTR_L); a.add_a_n(16); a.ld_abs_a(DYN_PTR_L); a.jr("tex_tile_ptr_ready", "nc")
    a.ld_a_abs(DYN_PTR_H); a.inc_r("a"); a.cp_n((DYNAMIC_TILES + DYNAMIC_RING_SLOTS * 16) >> 8); a.jr("tex_tile_ptr_wrapped", "nz")
    a.ld_r_n("a", DYNAMIC_TILES >> 8)
    a.label("tex_tile_ptr_wrapped"); a.ld_abs_a(DYN_PTR_H)
    a.label("tex_tile_ptr_ready")
    a.ld_a_abs(TILE_ID_RESULT); a.ret()

    # ----- tex_column_single: every tile of a one-face column ---------------------
    # The accumulator (HL), the step (DE) and the ring slot (BC) stay in
    # registers from the first composed tile to the last; the rows are the
    # same unrolled kernel, entered at the run's first row of the first tile
    # (and four rows in on the centre tile). Ceiling rows above the wall are
    # written first; the map copy is the column's, afterwards.
    a.label("tex_column_single")
    a.ld_a_abs(MIN_TOP); a.and_n(0xF8); a.ld_abs_a(TILE_Y0)
    a.ld_a_abs(MIN_TOP); a.and_n(7); a.ld_abs_a(TEX_TMP1)                  # rows to skip in the first tile
    a.ld_a_abs(MIN_TOP)
    for _ in range(3): a.cb("srl", "a")
    a.ld_r_r("c", "a"); a.ld_r_n("a", 8); a.sub_r("c"); a.ld_abs_a(TEX_LOOP)     # tiles to compose
    a.ld_rr_nn("hl", COLUMN_ROWS); a.ld_r_r("a", "c"); a.or_r("a"); a.jr("tex_single_no_ceiling", "z")
    a.label("tex_single_ceiling"); a.ld_hl_n(CEILING_TILE); a.inc_rr("hl"); a.dec_r("c"); a.jr("tex_single_ceiling", "nz")
    a.label("tex_single_no_ceiling")
    a.ld_rr_nn("hl", TEX_RUNS + R_STEP_L); a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(TEX_RUNS + R_CACHE_L); a.ld_r_r("h", "a"); a.ld_r_n("l", 0)
    load_hram_pair(a, DYN_PTR_L, DYN_PTR_H, "bc")
    a.label("tex_single_tile")
    # the slot must be free: only a pattern beyond the ring's depth can wait
    a.ld_a_abs(DYN_COUNT); a.cp_n(DYNAMIC_RING_SLOTS); a.jr("tex_single_slot_free", "c")
    a.push("hl"); a.push("de"); a.push("bc"); a.call("tex_ring_wait"); a.pop("bc"); a.pop("de"); a.pop("hl")
    a.label("tex_single_slot_free")
    a.ld_r_r("a", "c"); a.ld_abs_a(TEX_DST_L); a.ld_r_r("a", "b"); a.ld_abs_a(TEX_DST_H)
    # entry row: a tile with no rows to skip enters at row 0, or row 4 on the
    # centre tile; a first tile entered part way dispatches through the table
    # with the slot advanced past the skipped rows (four more on the centre tile).
    a.ld_a_abs(TEX_TMP1); a.or_r("a"); a.jr("tex_single_dispatch", "nz")
    a.ld_a_abs(TILE_Y0); a.cp_n(CENTRE_Y0); a.jp("tex_single_rows_4", "z"); a.jp("tex_single_rows_0")
    a.label("tex_single_dispatch")
    a.ld_a_abs(TILE_Y0); a.cp_n(CENTRE_Y0); a.ld_a_abs(TEX_TMP1); a.jr("tex_single_entry_ready", "nz")
    a.add_a_n(4); a.cp_n(8); a.jr("tex_single_entry_ready", "c"); a.ld_r_n("a", 8)
    a.label("tex_single_entry_ready")
    a.ld_r_r("l", "a"); a.ld_r_r("a", "h"); a.ld_abs_a(TEX_TMP2)                       # acc high byte parked; the fraction is 0 at a run's start
    a.ld_a_abs(TEX_TMP1); a.add_a_r("a"); a.add_a_r("c"); a.ld_r_r("c", "a")             # the slot past the skipped rows
    a.ld_r_r("a", "l"); a.add_a_r("a"); a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.push("de")
    a.ld_rr_nn("de", 0); a.ld_r_r("e", "l"); a.ld_rr_label("hl", "tex_single_entries"); a.add_hl_rr("de"); a.pop("de")
    a.ldi_a_hl(); a.ld_r_r("h", "(hl)"); a.ld_r_r("l", "a"); a.push("hl")
    a.ld_a_abs(TEX_TMP2); a.ld_r_r("h", "a"); a.ld_r_n("l", 0)
    a.ret()
    for row in range(8):
        a.label(f"tex_single_rows_{row}")
        a.push("hl")
        a.ld_r_r("l", "h"); a.ld_r_n("h", TEX_WINDOWS >> 8)
        a.ld_a_hl(); a.ld_mem_rr_a("bc"); a.inc_r("c")
        a.ld_r_r("a", "l"); a.add_a_n(TEXEL_ROWS); a.ld_r_r("l", "a")
        a.ld_a_hl(); a.ld_mem_rr_a("bc"); a.inc_r("c")
        a.pop("hl"); a.add_hl_rr("de")
    a.label("tex_single_rows_8")
    a.xor_r("a"); a.ld_abs_a(TEX_TMP1)                                    # later tiles enter at row 0
    # boundary tile: the outline and coverage masks; centre tile: the mirror
    a.push("hl"); a.push("de"); a.push("bc")
    a.ld_a_abs(MAX_TOP); a.ld_r_r("b", "a"); a.ld_a_abs(TILE_Y0); a.cp_r("b")
    a.ld_r_n("a", 0)                                                      # flags kept: xor would set Z
    a.jr("tex_single_interior", "z"); a.jr("tex_single_interior", "c")   # a top on or below this row: boundary
    a.ld_r_n("a", 1)
    a.label("tex_single_interior"); a.ld_abs_a(TEX_INTERIOR); a.or_r("a"); a.jr("tex_single_centre", "nz")
    a.call("tex_mask_tables"); load_hram_pair(a, TEX_DST_L, TEX_DST_H, "hl"); a.call("tex_apply_masks")
    a.label("tex_single_centre")
    a.ld_a_abs(TILE_Y0); a.cp_n(CENTRE_Y0); a.jr("tex_single_tile_done", "nz")
    load_hram_pair(a, TEX_DST_L, TEX_DST_H, "hl"); a.call("tex_mirror_centre")
    a.label("tex_single_tile_done")
    # the tile's id into the column, the next slot with the ring's wrap
    a.ld_a_abs(TILE_Y0)
    for _ in range(3): a.cb("srl", "a")
    a.add_a_n(COLUMN_ROWS & 0xFF); a.ld_r_r("l", "a"); a.ld_r_n("h", COLUMN_ROWS >> 8)
    a.ld_a_abs(DYN_COUNT); a.ld_hl_a(); a.inc_r("a"); a.ld_abs_a(DYN_COUNT)
    a.pop("bc"); a.pop("de"); a.pop("hl")
    a.ld_a_abs(TEX_DST_L); a.add_a_n(16); a.ld_r_r("c", "a"); a.ld_a_abs(TEX_DST_H); a.adc_a_n(0)
    a.cp_n((DYNAMIC_TILES + DYNAMIC_RING_SLOTS * 16) >> 8); a.jr("tex_single_slot_next", "nz"); a.ld_r_n("a", DYNAMIC_TILES >> 8)
    a.label("tex_single_slot_next"); a.ld_r_r("b", "a")
    a.ld_a_abs(TILE_Y0); a.add_a_n(8); a.ld_abs_a(TILE_Y0)
    a.ld_a_abs(TEX_LOOP); a.dec_r("a"); a.ld_abs_a(TEX_LOOP); a.jp("tex_single_tile", "nz")
    a.ld_r_r("a", "c"); a.ld_abs_a(DYN_PTR_L); a.ld_r_r("a", "b"); a.ld_abs_a(DYN_PTR_H)
    a.ld_a_abs(DYN_COUNT); a.ld_r_r("b", "a"); a.ld_a_abs(DYN_HIGH_WATER); a.cp_r("b"); a.ret("nc")
    a.ld_r_r("a", "b"); a.ld_abs_a(DYN_HIGH_WATER); a.ret()
    a.label("tex_single_entries")
    for row in range(9): a.dw_label(f"tex_single_rows_{row}")

    # ----- tex_compose_run: HL = record, TEX_DST = destination ------------------
    # Composes the run's eight rows (four for the centre tile) at the row
    # accumulator, unmasked. Carry set and nothing written when the run starts
    # below this tile. The accumulator is stored back for the next tile.
    a.label("tex_compose_run")
    a.ld_r_r("a", "l"); a.ld_abs_a(TEX_REC_L); a.ld_r_r("a", "h"); a.ld_abs_a(TEX_REC_H)
    a.ldi_a_hl(); a.ld_r_r("b", "a")                           # TOP
    a.inc_rr("hl"); a.ldi_a_hl(); a.ld_abs_a(TEX_CACHE_L)      # CACHE_L; HL -> ACC_L
    a.ld_a_abs(TILE_Y0); a.ld_r_r("c", "a")
    a.ld_r_r("a", "b"); a.sub_r("c"); a.jr("tex_run_continuing", "c")
    a.cp_n(8); a.jr("tex_run_starting", "c")
    a.scf(); a.ret()
    a.label("tex_run_starting")
    # The rows above the run's top are never visible (the coverage mask
    # removes them), so the kernel is entered at row n = TOP - y0 with the
    # accumulator at texture row 0 and the destination advanced past them;
    # the centre tile composes its four upper rows only, so it enters four
    # rows further in. The entry address is pushed and reached by `ret`.
    a.ld_r_r("c", "a")
    a.ld_a_abs(TILE_Y0); a.cp_n(CENTRE_Y0); a.ld_r_r("a", "c"); a.jr("tex_run_entry_ready", "nz")
    a.add_a_n(4); a.cp_n(8); a.jr("tex_run_entry_ready", "c"); a.ld_r_n("a", 8)
    a.label("tex_run_entry_ready")
    a.add_a_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_rr_label("hl", "tex_run_entries"); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("h", "(hl)"); a.ld_r_r("l", "a"); a.push("hl")
    load_hram_pair(a, TEX_REC_L, TEX_REC_H, "hl"); a.ld_rr_nn("de", R_STEP_L); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(TEX_CACHE_L); a.ld_r_r("h", "a"); a.ld_r_n("l", 0)
    a.ld_r_r("a", "c"); a.add_a_r("a"); a.ld_r_r("c", "a")
    a.ld_a_abs(TEX_DST_L); a.add_a_r("c"); a.ld_r_r("c", "a"); a.ld_a_abs(TEX_DST_H); a.ld_r_r("b", "a")
    a.ret()
    a.label("tex_run_continuing")
    a.ldi_a_hl(); a.ld_r_r("c", "a"); a.ldi_a_hl(); a.ld_r_r("b", "a")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_r_r("h", "b"); a.ld_r_r("l", "c")
    load_hram_pair(a, TEX_DST_L, TEX_DST_H, "bc")
    a.ld_a_abs(TILE_Y0); a.cp_n(CENTRE_Y0); a.jr("tex_run_rows_4", "z")
    for row in range(8):
        a.label(f"tex_run_rows_{row}")
        # HL = accumulator (H = the cache row's address, L = the fraction),
        # DE = step, BC = destination, sixteen-aligned like the cache.
        a.push("hl")
        a.ld_r_r("l", "h"); a.ld_r_n("h", TEX_WINDOWS >> 8)
        a.ld_a_hl(); a.ld_mem_rr_a("bc"); a.inc_r("c")
        a.ld_r_r("a", "l"); a.add_a_n(TEXEL_ROWS); a.ld_r_r("l", "a")
        a.ld_a_hl(); a.ld_mem_rr_a("bc"); a.inc_r("c")
        a.pop("hl"); a.add_hl_rr("de")
    a.label("tex_run_rows_8")
    a.ld_r_r("e", "l"); a.ld_r_r("d", "h")
    load_hram_pair(a, TEX_REC_L, TEX_REC_H, "hl"); a.ld_rr_nn("bc", R_ACC_L); a.add_hl_rr("bc")
    a.ld_r_r("a", "e"); a.ldi_hl_a(); a.ld_r_r("a", "d"); a.ld_hl_a()
    a.or_r("a"); a.ret()
    a.label("tex_run_entries")
    for row in range(9): a.dw_label(f"tex_run_rows_{row}")

    # ----- tex_mask_tables: the outline pixels of each row of a boundary tile ---
    # TEX_MASKS[r] = pixels whose top is row r; TEX_TMP0 = pixels covered
    # from row 0. Coverage accumulates row by row where the masks are applied.
    a.label("tex_mask_tables")
    a.ld_rr_nn("hl", TEX_MASKS); a.xor_r("a")
    for _ in range(8): a.ldi_hl_a()
    a.ld_abs_a(TEX_TMP0)
    load_hram_pair(a, SCAN_TOP_PTR_L, SCAN_TOP_PTR_H, "hl")
    a.ld_a_abs(TILE_Y0); a.ld_r_r("b", "a"); a.ld_r_n("c", 0x80)
    for pixel in range(8):
        a.ldi_a_hl(); a.sub_r("b"); a.jr(f"tex_mask_below_{pixel}", "c")
        a.cp_n(8); a.jr(f"tex_mask_next_{pixel}", "nc")
        a.add_a_n(TEX_MASKS & 0xFF); a.ld_r_r("e", "a"); a.ld_r_n("d", TEX_MASKS >> 8)
        a.ld_a_mem_rr("de"); a.or_r("c"); a.ld_mem_rr_a("de"); a.jr(f"tex_mask_next_{pixel}")
        a.label(f"tex_mask_below_{pixel}"); a.ld_a_abs(TEX_TMP0); a.or_r("c"); a.ld_abs_a(TEX_TMP0)
        a.label(f"tex_mask_next_{pixel}"); a.cb("rrc", "c")
    a.ret()

    # ----- tex_apply_masks: plane = (plane & cover & ~edge) | edge per row ------
    # B carries the coverage down the rows (cover |= edge); the pixels kept
    # are cover xor edge, since the outline is always covered.
    a.label("tex_apply_masks")          # HL = the tile
    a.ld_rr_nn("de", TEX_MASKS); a.ld_a_abs(TEX_TMP0); a.ld_r_r("b", "a")
    for _ in range(8):
        a.ld_a_mem_rr("de"); a.inc_r("e"); a.ld_r_r("c", "a"); a.or_r("b"); a.ld_r_r("b", "a")
        for _ in range(2): a.xor_r("c"); a.and_r("(hl)"); a.or_r("c"); a.ldi_hl_a(); a.ld_r_r("a", "b")
    a.ret()

    # ----- tex_mirror_centre: rows 7..4 from rows 0..3, floor under the wall -----
    a.label("tex_mirror_centre")        # HL = the tile
    a.ld_r_r("d", "h"); a.ld_r_r("a", "l"); a.add_a_n(14); a.ld_r_r("e", "a")
    a.ld_a_abs(TEX_INTERIOR); a.or_r("a"); a.jr("tex_mirror_boundary", "z")
    for _ in range(4):
        a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_r("e"); a.ldi_a_hl(); a.ld_mem_rr_a("de")
        a.dec_r("e"); a.dec_r("e"); a.dec_r("e")
    a.ret()
    a.label("tex_mirror_boundary")
    a.ld_a_abs(TEX_TMP0); a.ld_r_r("b", "a")
    for row in range(4):
        a.ld_a_abs(TEX_MASKS + row); a.or_r("b"); a.ld_r_r("b", "a"); a.cpl(); a.ld_r_r("c", "a")
        a.ldi_a_hl(); a.or_r("c"); a.ld_mem_rr_a("de"); a.inc_r("e")
        a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.dec_r("e"); a.dec_r("e"); a.dec_r("e")
    a.ret()
