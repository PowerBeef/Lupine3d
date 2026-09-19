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
BLANK_PATTERN = DIGIT_PATTERNS
# Map cells the runtime rewrites. Each entry is a screen-relative tile index.
NO_SLOT = 0xFFFF


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
    # Digits first, then a blank: a runtime map write alone can show a number
    # or clear a cell, which is how the code entry blinks its cursor.
    patterns = _digit_tiles() + [tiles(canvas(8, 8, 0))]
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
    if len(slots) > SCREEN_SLOT_CAPACITY:
        raise ValueError(f"screen reserves {len(slots)} of {SCREEN_SLOT_CAPACITY} digit slots")
    offsets = tuple(row * SCREEN_COLUMNS + column for column, row in slots)
    return b"".join(patterns), bytes(tilemap), offsets


# Authored screens. Order is the runtime screen index; keep it stable, the
# emitter indexes a directory by it.
SCREEN_TITLE, SCREEN_GAMEOVER, SCREEN_ENDING, SCREEN_INTERMISSION, SCREEN_PASSWORD = range(5)

SCREEN_SOURCES = (
    # The skill digit sits on the authored zero; left and right change it.
    ("title", (
        ("LUPINE", 28, 2, 3),
        ("SABLE OUTPOST", 58, 3, 1),
        ("PRESS START", 92, 2, 1),
        ("SKILL 0", 112, 3, 1),
     ), ((11, 14),)),
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
    # The continue code sits on its own line; the runtime writes all four
    # digits, so the authored zeroes are only a placeholder.
    ("intermission", (
        ("SECTOR CLEAR", 36, 2, 2),
        ("CODE 0000", 74, 3, 1),
        ("PRESS START", 108, 2, 1),
     ), ((10, 9), (11, 9), (12, 9), (13, 9))),
    ("password", (
        ("CONTINUE", 32, 2, 2),
        ("CODE 0000", 72, 3, 1),
        ("START ACCEPTS", 104, 1, 1),
        ("SELECT CANCELS", 118, 1, 1),
     ), ((10, 9), (11, 9), (12, 9), (13, 9))),
)


@lru_cache(maxsize=1)
def screen_assets() -> list[tuple[str, bytes, bytes, tuple[int, ...]]]:
    """(name, patterns, map, slot offsets) for every authored screen."""
    composed = []
    for name, lines, slots in SCREEN_SOURCES:
        patterns, tilemap, offsets = compose_screen(lines, slots)
        composed.append((name, patterns, tilemap, offsets))
    return composed


def continue_codes(levels: int, skills: int) -> list[tuple[int, ...]]:
    """One unambiguous four-digit code per (sector, skill) pair.

    Deterministic, never repeated, and never starting with a zero, so a code
    read off the intermission screen types back in exactly as it appears.
    """
    codes, seen = [], set()
    for value in range(levels * skills):
        code = (1373 * (value + 11)) % 9000 + 1000
        while code in seen:
            code = (code - 999) % 9000 + 1000
        seen.add(code)
        codes.append(tuple(int(digit) for digit in f"{code:04d}"))
    return codes


def screen_directory() -> bytes:
    """Per-screen header: pattern bytes, map offset and the runtime slots.

    Layout is pattern count, pattern address, map address, slot count and then
    SCREEN_SLOT_CAPACITY screen-relative offsets, so the loader streams both
    payloads and learns its rewritable cells without a second table.
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
        records.append(len(offsets))
        for index in range(SCREEN_SLOT_CAPACITY):
            slot = offsets[index] if index < len(offsets) else NO_SLOT
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
    # HL = record base: pattern count, pattern address, map address, slot
    # count and then SCREEN_SLOT_CAPACITY screen-relative offsets.
    a.ld_a_abs(SCREEN_INDEX); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.ld_r_r("h", "d"); a.ld_r_r("l", "e")
    for _ in range(SCREEN_RECORD_BYTES - 1): a.add_hl_rr("de")
    a.ld_rr_nn("de", SCREEN_ROM_ADDRESS); a.add_hl_rr("de")
    a.ld_r_n("a", SCREEN_ROM_BANK); a.ld_abs_a(0x2000)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_PATTERN_COUNT)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_SOURCE_L); a.ldi_a_hl(); a.ld_abs_a(SCREEN_SOURCE_H)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_MAP_L); a.ldi_a_hl(); a.ld_abs_a(SCREEN_MAP_H)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_SLOT_COUNT)
    for index in range(2 * SCREEN_SLOT_CAPACITY - 1):
        a.ldi_a_hl(); a.ld_abs_a(SCREEN_SLOTS + index)
    a.ld_a_hl(); a.ld_abs_a(SCREEN_SLOTS + 2 * SCREEN_SLOT_CAPACITY - 1)
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
    # The digits go in while the LCD is still off, so no VRAM access on this
    # path ever has to race mode 3.
    a.call("screen_write_slots")
    a.ld_r_n("a", 0x81); a.ldh_n_a(LCDC)   # LCD and BG only: no objects, no split
    a.ret()

    a.label("screen_slot_address")  # C = slot index -> HL = its map cell
    a.ld_r_r("a", "c"); a.add_a_r("a"); a.add_a_n(SCREEN_SLOTS & 255)
    a.ld_r_r("l", "a"); a.ld_r_n("h", SCREEN_SLOTS >> 8)
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.cp_n(0xFF); a.ret("z")        # an unused slot keeps HL pointing at WRAM
    # Slot offsets are screen-relative; expand the 20-column row to 32.
    a.ld_r_r("a", "e"); a.ld_r_n("b", 0)
    a.label("screen_slot_rows")
    a.cp_n(SCREEN_COLUMNS); a.jr("screen_slot_ready", "c")
    a.sub_n(SCREEN_COLUMNS); a.inc_r("b"); a.jr("screen_slot_rows")
    a.label("screen_slot_ready")
    a.ld_r_r("e", "a"); a.ld_r_r("a", "b"); a.cb("swap", "a"); a.add_a_r("a")
    a.ld_r_r("l", "a"); a.ld_r_n("h", 0); a.ld_r_r("a", "e"); a.add_a_r("l"); a.ld_r_r("l", "a")
    a.ld_r_n("a", 0); a.adc_a_r("h"); a.add_a_n(0x98); a.ld_r_r("h", "a")
    a.ret()

    a.label("screen_write_slot")   # C = slot index, writes SCREEN_DIGITS[C]
    a.ld_a_abs(SCREEN_SLOT_COUNT); a.cp_r("c"); a.ret("c"); a.ret("z")
    a.push("bc"); a.call("screen_slot_address")
    a.ld_r_r("a", "d"); a.cp_n(0xFF); a.jr("screen_write_slot_done", "z")
    a.pop("bc"); a.push("bc")
    a.ld_r_r("a", "c"); a.add_a_n(SCREEN_DIGITS & 255)
    a.ld_r_r("e", "a"); a.ld_r_n("d", SCREEN_DIGITS >> 8)
    a.ld_a_mem_rr("de"); a.ld_hl_a()
    a.label("screen_write_slot_done"); a.pop("bc"); a.ret()

    a.label("screen_write_slots")
    a.ld_r_n("c", 0)
    a.label("screen_write_slots_loop")
    a.call("screen_write_slot")
    a.ld_r_r("a", "c"); a.inc_r("a"); a.ld_r_r("c", "a")
    a.cp_n(SCREEN_SLOT_CAPACITY); a.jr("screen_write_slots_loop", "c"); a.ret()

    a.label("screen_wait_start")
    a.call("wait_vblank")
    a.di(); a.ld_a_abs(INPUT_EDGE_LATCH); a.ld_r_r("b", "a")
    a.xor_r("a"); a.ld_abs_a(INPUT_EDGE_LATCH); a.ei()
    a.ld_r_r("a", "b"); a.and_n(0x80); a.ret("nz")
    # Only the title offers a second way out: SELECT opens code entry.
    a.ld_a_abs(SCREEN_INDEX); a.cp_n(SCREEN_TITLE); a.jr("screen_wait_no_select", "nz")
    a.ld_r_r("a", "b"); a.and_n(0x40); a.ret("nz")
    a.label("screen_wait_no_select")
    # Left and right change the skill. The slot write happens here, at the top
    # of VBlank, so it never races the fetcher.
    a.ld_r_r("a", "b"); a.and_n(0x03); a.call("screen_adjust_skill", "nz")
    # A full-screen mode enables VBlank only, so the sequencer has no STAT
    # boundary to ride; this loop is its once-per-frame tick.
    a.call("music_tick")
    a.jr("screen_wait_start")

    a.label("screen_adjust_skill")   # B = edge bits, bit 0 right, bit 1 left
    a.ld_a_abs(SCREEN_INDEX); a.cp_n(SCREEN_TITLE); a.ret("nz")
    a.ld_a_abs(DIFFICULTY)
    a.cb("bit", "b", 0); a.jr("screen_skill_lower", "z")
    a.inc_r("a"); a.cp_n(DIFFICULTY_LEVELS); a.jr("screen_skill_store", "c")
    a.ld_r_n("a", DIFFICULTY_LEVELS - 1); a.jr("screen_skill_store")
    a.label("screen_skill_lower")
    a.or_r("a"); a.jr("screen_skill_store", "z"); a.dec_r("a")
    a.label("screen_skill_store")
    a.ld_abs_a(DIFFICULTY); a.inc_r("a"); a.ld_abs_a(SCREEN_DIGIT)
    a.jp("screen_write_slots")

    # Continue codes. The table is a build-time list of four-digit codes, one
    # per (sector, skill) pair, so the console only ever compares bytes.
    a.label("password_for_progress")   # SCREEN_DIGITS = the code for where we are
    a.ld_a_abs(LEVEL_INDEX); a.ld_r_r("b", "a"); a.add_a_r("a"); a.add_a_r("b")
    a.ld_r_r("b", "a"); a.ld_a_abs(DIFFICULTY); a.add_a_r("b")
    a.add_a_r("a"); a.add_a_r("a")                    # four digits per record
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "password_codes"); a.add_hl_rr("de")
    a.ld_rr_nn("de", SCREEN_DIGITS); a.ld_rr_nn("bc", PASSWORD_DIGITS); a.jp("copy_bc")

    a.label("password_lookup")   # A = matching record + 1, or zero
    a.xor_r("a"); a.ld_abs_a(PASSWORD_SCAN)
    a.ld_rr_label("hl", "password_codes")
    a.label("password_scan")
    a.ld_rr_nn("de", SCREEN_DIGITS); a.ld_r_n("b", PASSWORD_DIGITS)
    a.label("password_compare")
    a.ld_a_mem_rr("de"); a.inc_rr("de"); a.cp_r("(hl)"); a.inc_rr("hl")
    a.jr("password_mismatch", "nz")
    a.dec_r("b"); a.jr("password_compare", "nz")
    a.ld_a_abs(PASSWORD_SCAN); a.inc_r("a"); a.ret()
    a.label("password_mismatch")
    # B still counts the byte that failed, so B-1 bytes of this record remain.
    a.ld_r_r("a", "b"); a.dec_r("a"); a.ld_r_r("e", "a"); a.ld_r_n("d", 0); a.add_hl_rr("de")
    a.ld_a_abs(PASSWORD_SCAN); a.inc_r("a"); a.ld_abs_a(PASSWORD_SCAN)
    a.cp_n(LEVEL_COUNT * DIFFICULTY_LEVELS); a.jr("password_scan", "c")
    a.xor_r("a"); a.ret()

    a.label("password_entry")    # A = 1 when a code was accepted
    for index in range(PASSWORD_DIGITS):
        a.xor_r("a"); a.ld_abs_a(SCREEN_DIGITS + index)
    a.xor_r("a"); a.ld_abs_a(PASSWORD_CURSOR); a.ld_abs_a(PASSWORD_BLINK)
    a.ld_r_n("a", SCREEN_PASSWORD); a.call("show_screen")
    a.di(); a.xor_r("a"); a.ld_abs_a(INPUT_EDGE_LATCH); a.ei()
    a.label("password_loop")
    a.call("wait_vblank")
    a.di(); a.ld_a_abs(INPUT_EDGE_LATCH); a.ld_r_r("b", "a")
    a.xor_r("a"); a.ld_abs_a(INPUT_EDGE_LATCH); a.ei()
    a.ld_r_r("a", "b"); a.and_n(0x80); a.jr("password_submit", "nz")
    a.ld_r_r("a", "b"); a.and_n(0x40); a.jr("password_cancel", "nz")
    a.call("password_edit")
    a.call("password_cursor_blink")
    a.call("music_tick")
    a.jr("password_loop")
    a.label("password_cancel")
    a.xor_r("a"); a.ret()
    a.label("password_submit")
    a.call("password_lookup"); a.or_r("a"); a.jr("password_loop", "z")
    a.dec_r("a"); a.ld_r_n("b", 0)
    a.label("password_split")
    a.cp_n(DIFFICULTY_LEVELS); a.jr("password_split_done", "c")
    a.sub_n(DIFFICULTY_LEVELS); a.inc_r("b"); a.jr("password_split")
    a.label("password_split_done")
    a.ld_abs_a(DIFFICULTY)
    a.ld_r_r("a", "b"); a.ld_abs_a(LEVEL_INDEX)
    a.ld_r_n("a", 1); a.ret()

    a.label("password_edit")     # B = edge bits
    a.ld_a_abs(PASSWORD_CURSOR); a.ld_r_r("c", "a")
    a.cb("bit", "b", 0); a.jr("password_edit_left", "z")
    a.ld_r_r("a", "c"); a.inc_r("a"); a.cp_n(PASSWORD_DIGITS); a.jr("password_move", "c")
    a.ld_r_n("a", 0); a.jr("password_move")
    a.label("password_edit_left")
    a.cb("bit", "b", 1); a.jr("password_edit_value", "z")
    a.ld_r_r("a", "c"); a.or_r("a"); a.jr("password_move", "z")
    a.dec_r("a")
    a.label("password_move")
    a.ld_abs_a(PASSWORD_CURSOR); a.ret()
    a.label("password_edit_value")
    # Up and down roll the selected digit; C already holds the cursor.
    a.ld_r_r("a", "c"); a.add_a_n(SCREEN_DIGITS & 255)
    a.ld_r_r("l", "a"); a.ld_r_n("h", SCREEN_DIGITS >> 8); a.ld_a_hl()
    a.cb("bit", "b", 2); a.jr("password_edit_down", "z")
    a.inc_r("a"); a.cp_n(10); a.jr("password_value_store", "c"); a.xor_r("a")
    a.jr("password_value_store")
    a.label("password_edit_down")
    a.cb("bit", "b", 3); a.ret("z")
    a.or_r("a"); a.jr("password_value_wrap", "z"); a.dec_r("a"); a.jr("password_value_store")
    a.label("password_value_wrap"); a.ld_r_n("a", 9)
    a.label("password_value_store")
    a.ld_hl_a(); a.jp("screen_write_slot")

    a.label("password_cursor_blink")
    a.ld_a_abs(PASSWORD_BLINK); a.inc_r("a"); a.ld_abs_a(PASSWORD_BLINK)
    a.and_n(0x10)
    a.ld_a_abs(PASSWORD_CURSOR); a.ld_r_r("c", "a"); a.jp("screen_write_slot", "z")
    a.call("screen_slot_address"); a.ld_r_r("a", "d"); a.cp_n(0xFF); a.ret("z")
    a.ld_r_n("a", BLANK_PATTERN); a.ld_hl_a(); a.ret()
