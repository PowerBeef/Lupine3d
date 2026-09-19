"""Full-screen text presentation for the non-world game modes.

The world renderer owns the viewport tilemap, the HUD's STAT split and the
dynamic pattern window. None of that is meaningful on a title or results
screen, so these modes take the whole 160x144 background for themselves and
borrow the dynamic pattern region at $9000 while composition is idle.

Screens are composed at build time: a pixel canvas is sliced into 8x8 tiles,
identical tiles are folded together, and the result is a small pattern set plus
a 20x18 map. Patterns 0..9 are always the decimal digits so the runtime can
write a level number or a count straight into a map cell without touching VRAM.
"""
from .artwork import canvas, rect, text_pixels, tiles
from .layout import *  # noqa: F401,F403

SCREEN_COLUMNS = 20
SCREEN_ROWS = 18
SCREEN_MAP_BYTES = SCREEN_COLUMNS * SCREEN_ROWS
# Signed BG addressing keeps IDs 0..127 at $9000, and composition owns 0..95.
SCREEN_PATTERN_CAPACITY = DYNAMIC_TILE_CAPACITY
DIGIT_PATTERNS = 10
# Map cells the runtime rewrites. Each entry is a screen-relative tile index.
SCREEN_SLOT_BYTES = 4


def _digit_tiles() -> list[bytes]:
    """Patterns 0..9, so a map write alone can show a number."""
    out = []
    for digit in "0123456789":
        px = canvas(8, 8, 0)
        text_pixels(px, digit, 2, 1, 2)
        out.append(tiles(px))
    return out


def _frame(px) -> None:
    """A plain steel border, matching the HUD chassis vocabulary."""
    rect(px, 0, 0, 160, 1, 1)
    rect(px, 0, 143, 160, 1, 1)
    rect(px, 0, 0, 1, 144, 1)
    rect(px, 159, 0, 1, 144, 1)
    rect(px, 4, 4, 152, 1, 3)
    rect(px, 4, 139, 152, 1, 3)


def compose_screen(lines, slots=()) -> tuple[bytes, bytes, tuple[int, ...]]:
    """Render one screen to (patterns, 20x18 map, runtime slot offsets).

    `lines` are (text, y, colour, scale) with the text centred horizontally.
    `slots` are (column, row) map cells the runtime overwrites with a digit.
    """
    px = canvas(160, 144, 0)
    _frame(px)
    for text, y, colour, scale in lines:
        width = len(text) * 4 * scale
        text_pixels(px, text, (160 - width) // 2, y, colour, scale)
    patterns = _digit_tiles()
    index = {pattern: number for number, pattern in enumerate(patterns)}
    tilemap = bytearray(SCREEN_MAP_BYTES)
    raw = tiles(px)
    for row in range(SCREEN_ROWS):
        for column in range(SCREEN_COLUMNS):
            offset = (row * SCREEN_COLUMNS + column) * 16
            pattern = raw[offset:offset + 16]
            number = index.get(pattern)
            if number is None:
                number = len(patterns)
                index[pattern] = number
                patterns.append(pattern)
            tilemap[row * SCREEN_COLUMNS + column] = number
    if len(patterns) > SCREEN_PATTERN_CAPACITY:
        raise ValueError(f"screen needs {len(patterns)} of {SCREEN_PATTERN_CAPACITY} patterns")
    offsets = tuple(row * SCREEN_COLUMNS + column for column, row in slots)
    return b"".join(patterns), bytes(tilemap), offsets


# Authored screens. Order is the runtime screen index; keep it stable, the
# emitter indexes a directory by it.
SCREEN_TITLE, SCREEN_GAMEOVER, SCREEN_ENDING, SCREEN_INTERMISSION = range(4)

SCREEN_SOURCES = (
    ("title", (
        ("LUPINE", 30, 2, 3),
        ("SABLE OUTPOST", 60, 3, 1),
        ("PRESS START", 96, 2, 1),
     ), ()),
    ("gameover", (
        ("SIGNAL LOST", 48, 3, 2),
        ("THE OUTPOST HOLDS", 84, 1, 1),
        ("PRESS START", 110, 2, 1),
     ), ()),
    ("ending", (
        ("OUTPOST CLEARED", 40, 2, 2),
        ("THE SABLE LINE IS OPEN", 76, 3, 1),
        ("PRESS START", 110, 2, 1),
     ), ()),
    # The next sector's number sits on its own line; the runtime writes it.
    ("intermission", (
        ("SECTOR CLEAR", 40, 2, 2),
        ("NEXT SECTOR", 78, 3, 1),
        ("PRESS START", 112, 2, 1),
     ), ((10, 11),)),
)


@lru_cache(maxsize=1)
def screen_assets() -> list[tuple[str, bytes, bytes, tuple[int, ...]]]:
    """(name, patterns, map, slot offsets) for every authored screen."""
    composed = []
    for name, lines, slots in SCREEN_SOURCES:
        patterns, tilemap, offsets = compose_screen(lines, slots)
        composed.append((name, patterns, tilemap, offsets))
    return composed


def screen_directory() -> bytes:
    """Per-screen header: pattern bytes, map offset and the first digit slot.

    Layout is pattern_count, map_lo, map_hi, slot_lo, slot_hi so the loader can
    stream both payloads without a second table.
    """
    payloads, records = [], bytearray()
    address = SCREEN_ROM_ADDRESS + len(SCREEN_SOURCES) * SCREEN_RECORD_BYTES
    for _, patterns, tilemap, offsets in screen_assets():
        records.extend((len(patterns) // 16, address & 255, address >> 8))
        payloads.append(patterns)
        address += len(patterns)
        records.extend((address & 255, address >> 8))
        payloads.append(tilemap)
        address += len(tilemap)
        slot = offsets[0] if offsets else 0xFFFF
        records.extend((slot & 255, slot >> 8))
    assert len(records) == len(SCREEN_SOURCES) * SCREEN_RECORD_BYTES
    assert address <= 0x8000, "authored screens exceed one MBC5 bank"
    return bytes(records) + b"".join(payloads)


def emit_screens(a: Assembler) -> None:
    """Present one authored screen and wait for START.

    Runs with the LCD off, so VRAM is written directly. The world's patterns,
    maps and attributes are all restored by `enter_world`, which repeats the
    boot upload; screens therefore never have to put anything back.
    """
    # Stopping the LCD outside VBlank is unsafe on real hardware, and waiting
    # for VBlank while it is already off never returns. Guard both.
    a.label("lcd_off")
    a.ldh_a_n(LCDC); a.and_n(0x80); a.ret("z")
    a.call("wait_vblank")
    a.xor_r("a"); a.ldh_n_a(LCDC); a.ret()

    a.label("show_screen")  # A selects the screen
    a.ld_abs_a(SCREEN_INDEX)
    a.call("lcd_off")
    a.ld_r_n("a", 1); a.ld_abs_a(0xFFFF)   # no STAT split on a full-screen mode
    # HL = record base. Records are seven bytes: pattern count, pattern
    # address, map address, then the first runtime digit slot.
    a.ld_a_abs(SCREEN_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_r_r("h", "d"); a.ld_r_r("l", "e")
    a.add_hl_rr("hl"); a.add_hl_rr("hl")
    for _ in range(3): a.add_hl_rr("de")
    a.ld_rr_nn("de", SCREEN_ROM_ADDRESS); a.add_hl_rr("de")
    a.ld_r_n("a", SCREEN_ROM_BANK); a.ld_abs_a(0x2000)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_PATTERN_COUNT)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_SOURCE_L); a.ldi_a_hl(); a.ld_abs_a(SCREEN_SOURCE_H)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_MAP_L); a.ldi_a_hl(); a.ld_abs_a(SCREEN_MAP_H)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_SLOT_L); a.ld_a_hl(); a.ld_abs_a(SCREEN_SLOT_H)
    # Patterns occupy the idle composition window at $9000.
    load_hl_abs(a, SCREEN_SOURCE_L, SCREEN_SOURCE_H)
    a.ld_rr_nn("de", DYNAMIC_TILE_VRAM)
    a.ld_a_abs(SCREEN_PATTERN_COUNT); a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(4): a.add_hl_rr("hl")          # BC = pattern count * 16
    a.ld_r_r("b", "h"); a.ld_r_r("c", "l")
    load_hl_abs(a, SCREEN_SOURCE_L, SCREEN_SOURCE_H)
    a.call("copy_bc")
    # Twenty visible columns of each row; the map is 32 wide.
    load_hl_abs(a, SCREEN_MAP_L, SCREEN_MAP_H)
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ld_rr_nn("de", 0x9800)
    a.ld_r_n("a", SCREEN_ROWS); a.ld_abs_a(SCREEN_ROW_COUNT)
    a.label("screen_row_loop")
    for _ in range(SCREEN_COLUMNS):
        a.ldi_a_hl(); a.ld_mem_rr_a("de"); a.inc_rr("de")
    a.ld_r_r("a", "e"); a.add_a_n(32 - SCREEN_COLUMNS); a.ld_r_r("e", "a")
    a.ld_r_n("a", 0); a.adc_a_r("d"); a.ld_r_r("d", "a")
    a.ld_a_abs(SCREEN_ROW_COUNT); a.dec_r("a"); a.ld_abs_a(SCREEN_ROW_COUNT); a.jp("screen_row_loop", "nz")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    # One reserved palette across the whole map; no flips, patterns in bank 0.
    a.ld_r_n("a", 1); a.ldh_n_a(VBK)
    a.ld_rr_nn("hl", 0x9800); a.ld_rr_nn("bc", 1024)
    a.label("screen_attribute_loop")
    a.ld_r_n("a", SCREEN_PALETTE); a.ldi_hl_a()
    a.dec_rr("bc"); a.ld_r_r("a", "b"); a.or_r("c"); a.jr("screen_attribute_loop", "nz")
    a.xor_r("a"); a.ldh_n_a(VBK)
    a.ldh_n_a(SCX); a.ldh_n_a(SCY)
    # The digit goes in while the LCD is still off, so no VRAM access on this
    # path ever has to race mode 3.
    a.call("screen_set_digit")
    a.ld_r_n("a", 0x81); a.ldh_n_a(LCDC)   # LCD and BG only: no objects, no split
    a.ret()

    a.label("screen_set_digit")  # SCREEN_DIGIT -> this screen's reserved slot
    a.ld_a_abs(SCREEN_SLOT_H); a.cp_n(0xFF); a.ret("z")
    a.ld_r_r("d", "a"); a.ld_a_abs(SCREEN_SLOT_L); a.ld_r_r("e", "a")
    # Slot offsets are screen-relative; expand the 20-column row to 32.
    a.ld_r_r("a", "e"); a.ld_r_n("b", 0)
    a.label("screen_slot_rows")
    a.cp_n(SCREEN_COLUMNS); a.jr("screen_slot_ready", "c")
    a.sub_n(SCREEN_COLUMNS); a.inc_r("b"); a.jr("screen_slot_rows")
    a.label("screen_slot_ready")
    a.ld_r_r("e", "a"); a.ld_r_r("a", "b"); a.cb("swap", "a"); a.add_a_r("a")
    a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.ld_r_r("a", "e"); a.add_a_r("l"); a.ld_r_r("l", "a")
    a.ld_r_n("a", 0); a.adc_a_r("h"); a.add_a_n(0x98); a.ld_r_r("h", "a")
    a.ld_a_abs(SCREEN_DIGIT); a.ld_hl_a(); a.ret()

    a.label("screen_wait_start")
    a.call("wait_vblank")
    # A full-screen mode enables VBlank only, so the sequencer has no STAT
    # boundary to ride; this loop is its once-per-frame tick.
    a.call("music_tick")
    a.di(); a.ld_a_abs(INPUT_EDGE_LATCH); a.ld_r_r("b", "a")
    a.xor_r("a"); a.ld_abs_a(INPUT_EDGE_LATCH); a.ei()
    a.ld_r_r("a", "b"); a.and_n(0x80); a.jr("screen_wait_start", "z")
    a.ret()
