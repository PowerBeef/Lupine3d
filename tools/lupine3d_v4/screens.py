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
from .game import FIXED_SCREENS, SCREEN_FIELDS, ScreenLine, screen_fields
from .fonts import GLYPH_ADVANCE, GLYPH_HEIGHT, GLYPH_WIDTH, SCREEN_FACE  # noqa: F401
from .limits import LIMITS

SCREEN_COLUMNS = 20
SCREEN_ROWS = 18
SCREEN_MAP_BYTES = SCREEN_COLUMNS * SCREEN_ROWS
# show_screen copies a screen's patterns linearly from $9000, and the BG map
# starts at $9800: 128 patterns, whatever the world's composition window is.
SCREEN_PATTERN_CAPACITY = LIMITS["screen_patterns"].maximum
assert SCREEN_PATTERN_CAPACITY * 16 == 0x9800 - 0x9000
DIGIT_PATTERNS = 10
BLANK_PATTERN = DIGIT_PATTERNS
# Map cells the runtime rewrites. Each entry is a screen-relative tile index.
NO_SLOT = 0xFFFF


def _digit_tiles(face: str = "small", colour: int = 2) -> list[bytes]:
    """Patterns 0..9, so a map write alone can show a number: the 3x5 digit
    in ivory, or the reading face's in the colour of the screen's fields."""
    out = []
    for digit in "0123456789":
        px = canvas(8, 8, 0)
        if face == "reading":
            _reading_glyph(px, digit, 0, 0, colour)
        else:
            text_pixels(px, digit, 2, 1, 2)
        out.append(tiles(px))
    return out


def _reading_glyph(px, char: str, x: int, y: int, colour: int) -> None:
    """One reading-face glyph in the 8x8 cell at pixel (x, y)."""
    for row, bits in enumerate(SCREEN_FACE.get(char, ())):
        for column, bit in enumerate(bits):
            if bit == "#":
                px[y + row][x + 1 + column] = colour


def _image_pixels(path) -> list[list[int]]:
    """An image line's indexed pixels, refused unless they draw in the
    screen palette's four colours on whole tiles."""
    from PIL import Image
    image = Image.open(path)
    if image.mode != "P":
        raise ValueError(f"{path.name} is {image.mode}, not an indexed (P) PNG")
    width, height = image.size
    if width % 8 or height % 8:
        raise ValueError(f"{path.name} is {width}x{height}; an image covers whole 8x8 tiles")
    pixels = [[image.getpixel((x, y)) for x in range(width)] for y in range(height)]
    if max(max(row) for row in pixels) > 3:
        raise ValueError(f"{path.name} uses palette index {max(max(row) for row in pixels)}; a screen draws indices 0-3")
    return pixels


def _frame(px) -> None:
    """A plain steel border, matching the HUD chassis vocabulary."""
    rect(px, 0, 0, 160, 1, 1)
    rect(px, 0, 143, 160, 1, 1)
    rect(px, 0, 0, 1, 144, 1)
    rect(px, 159, 0, 1, 144, 1)
    rect(px, 4, 4, 152, 1, 3)
    rect(px, 4, 139, 152, 1, 3)


SCREEN_NUMBER_POWERS = (10000, 1000, 100, 10, 1)


def load_hl(a, address: int) -> None:
    a.ld_a_abs(address); a.ld_r_r("l", "a")
    a.ld_a_abs(address + 1); a.ld_r_r("h", "a")


def store_hl(a, address: int) -> None:
    a.ld_r_r("a", "l"); a.ld_abs_a(address)
    a.ld_r_r("a", "h"); a.ld_abs_a(address + 1)


def _field_layout(label, digits, y, scale):
    """Where a label and the runtime digits after it sit, in pixels and tiles.

    A runtime digit owns a whole map cell, because a map write is the only
    thing a screen can do to change one. So the digits are placed on tile
    boundaries and the label is placed to their left, rather than the label
    being centred and the cells guessed afterwards - which is how the continue
    code ended up overlapping its own caption.
    """
    label_width = len(label) * GLYPH_ADVANCE * scale
    block = digits * 8
    start = max(0, (SCREEN_COLUMNS * 8 - (label_width + GLYPH_ADVANCE * scale + block)) // 2)
    first = -(-(start + label_width + GLYPH_ADVANCE * scale) // 8)
    row, bottom = y // 8, (y + GLYPH_HEIGHT * scale - 1) // 8
    if row != bottom:
        raise ValueError(f"{label!r} at y={y} straddles two tile rows")
    if start + label_width > first * 8:
        raise ValueError(f"{label!r} runs into the cells the runtime writes")
    if first + digits > SCREEN_COLUMNS:
        raise ValueError(f"{label!r} and {digits} digits do not fit a row")
    return start, tuple((first + index, row) for index in range(digits))


def _as_line(line) -> ScreenLine:
    """The composer's input: a ScreenLine, or the historical tuple form
    (text, y, colour, scale[, digits]) of the 3x5 face."""
    if isinstance(line, ScreenLine):
        return line
    text, y, colour, scale = line[:4]
    return ScreenLine(text=text, y=y, colour=colour, scale=scale, field="digits" if len(line) > 4 else None)


def compose_screen(lines, slots=(), frame: bool = True, digits: dict | None = None
                   ) -> tuple[bytes, bytes, tuple[int, ...]]:
    """Render one screen to (patterns, 20x18 map, runtime slot offsets).

    Lines are 3x5 text centred at a pixel row, a 3x5 label followed by the
    cells the runtime rewrites, reading-face text on a tile row (centred, or
    from a column), a reading-face label and its cells, or an image on the
    tile grid. `digits` maps a field to its cell count (the historical tuple
    form carries it as the fifth element). Field cells become slots in line
    order; `slots` are extra (column, row) map cells reserved by hand.
    """
    px = canvas(160, 144, 0)
    if frame:
        _frame(px)
    reserved = list(slots)
    claimed: dict[tuple[int, int], int] = {}   # tile cell -> line index, for reading text and images
    field_faces, field_colours = set(), set()

    def claim(cells, index):
        for cell in cells:
            if cell in claimed:
                raise ValueError(f"line {index} overlaps line {claimed[cell]} at column {cell[0]}, row {cell[1]}")
            claimed[cell] = index

    for index, raw in enumerate(lines):
        line = _as_line(raw)
        count = (raw[4] if not isinstance(raw, ScreenLine) and len(raw) > 4
                 else (digits or {}).get(line.field, 0))
        if line.face == "image":
            pixels = _image_pixels(line.image)
            width, height = len(pixels[0]) // 8, len(pixels) // 8
            column = line.column if line.column is not None else (SCREEN_COLUMNS - width) // 2
            first, last = (1, SCREEN_COLUMNS - 2) if frame else (0, SCREEN_COLUMNS - 1)
            top, bottom = (1, SCREEN_ROWS - 2) if frame else (0, SCREEN_ROWS - 1)
            if column < first or column + width - 1 > last or line.row < top or line.row + height - 1 > bottom:
                raise ValueError(f"{line.image.name} ({width}x{height} tiles) at column {column}, row {line.row} "
                                 f"leaves the {'frame' if frame else 'screen'}")
            claim([(column + x, line.row + y) for y in range(height) for x in range(width)], index)
            for y, row in enumerate(pixels):
                for x, value in enumerate(row):
                    if value:
                        px[line.row * 8 + y][column * 8 + x] = value
            continue
        if line.face == "reading":
            suffix = getattr(line, "suffix", "")
            cells = len(line.text) + (1 + count + len(suffix) if line.field else 0)
            column = line.column if line.column is not None else (SCREEN_COLUMNS - cells) // 2
            claim([(column + n, line.row) for n in range(cells)], index)
            for n, char in enumerate(line.text):
                if char != " ":
                    _reading_glyph(px, char, (column + n) * 8, line.row * 8, line.colour)
            if line.field:
                reserved.extend((column + len(line.text) + 1 + n, line.row) for n in range(count))
                field_faces.add("reading"); field_colours.add(line.colour)
                # A suffix ("%") is static text after the runtime cells.
                for n, char in enumerate(suffix):
                    if char != " ":
                        _reading_glyph(px, char, (column + len(line.text) + 1 + count + n) * 8, line.row * 8,
                                       line.colour)
            continue
        if line.field:
            x, cells = _field_layout(line.text, count, line.y, line.scale)
            reserved.extend(cells)
            field_faces.add("small")
        else:
            x = (160 - len(line.text) * GLYPH_ADVANCE * line.scale) // 2
        text_pixels(px, line.text, x, line.y, line.colour, line.scale)
    if len(field_faces) > 1 or len(field_colours) > 1:
        raise ValueError("a screen's runtime digits are one set of patterns: its fields must share one face "
                         "and one colour")
    # Digits first, then a blank: a runtime map write alone can show a number
    # or clear a cell, which is how the code entry blinks its cursor.
    face = next(iter(field_faces), "small")
    patterns = _digit_tiles(face, next(iter(field_colours), 2)) + [tiles(canvas(8, 8, 0))]
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
        raise ValueError(f"it needs {len(patterns)} distinct 8x8 patterns and a screen holds {SCREEN_PATTERN_CAPACITY} "
                         "(the ten digits and a blank included): use fewer lines, a smaller scale, or lines that "
                         "share tile rows")
    if len(reserved) > SCREEN_SLOT_CAPACITY:
        raise ValueError(f"screen reserves {len(reserved)} of {SCREEN_SLOT_CAPACITY} digit slots")
    offsets = tuple(row * SCREEN_COLUMNS + column for column, row in reserved)
    # A reserved cell must be empty in the authored art: the runtime writes the
    # whole cell, so anything drawn there would be lost.
    for offset, (column, row) in zip(offsets, reserved):
        if tilemap[offset] != BLANK_PATTERN:
            raise ValueError(f"reserved cell at row {row}, column {column} is not empty")
    return b"".join(patterns), bytes(tilemap), offsets


# Authored screens. Order is the runtime screen index; keep it stable, the
# emitter indexes a directory by it.
SCREEN_TITLE, SCREEN_GAMEOVER, SCREEN_ENDING, SCREEN_INTERMISSION, SCREEN_PASSWORD = range(5)
# Episode screens follow the fixed five: every closing but the last episode's
# (the ending closes it), then every opening, the first episode's prologue
# included when it has one. OPENING_STARTS gives the level each opening is
# shown before, in the same order. The debriefs, one per level but the last,
# come after them: DEBRIEF_BASE is the one shown after the first level.
SCREEN_EPISODE_CLOSINGS = tuple(len(FIXED_SCREENS) + n for n in range(len(EPISODE_STARTS)))
OPENING_STARTS = GAME.opening_starts
SCREEN_EPISODE_OPENINGS = tuple(len(FIXED_SCREENS) + len(EPISODE_STARTS) + n for n in range(len(OPENING_STARTS)))
DEBRIEF_BASE = len(FIXED_SCREENS) + len(EPISODE_STARTS) + len(OPENING_STARTS) if GAME.debriefs else None

# The game's screens (games/<id>/screens.json, loaded by game.py), in
# runtime order: the five fixed modes, the episode screens its episodes
# name, then its debriefs. A field is a label and the map cells the runtime
# writes after it; its cells become slots in the order the lines appear.
assert FIXED_SCREENS[:5] == ("title", "gameover", "ending", "intermission", "password")
assert SCREEN_FIELDS["intermission"]["code"] == SCREEN_FIELDS["password"]["code"] == PASSWORD_DIGITS
SCREEN_SOURCES = tuple(
    (name, lines, GAME.screen_frames.get(name, True), screen_fields(name, bool(GAME.items)))
    for name, lines in GAME.screens.items())
assert tuple(name for name, _, _, _ in SCREEN_SOURCES[5:]) == GAME.episode_screen_names + GAME.debrief_names, (
    f"the game's episode screens {GAME.episode_screen_names} are not the authored ones")
assert len(SCREEN_SOURCES) < 256, "a screen index is one byte"


@lru_cache(maxsize=1)
def screen_assets() -> list[tuple[str, bytes, bytes, tuple[int, ...]]]:
    """(name, patterns, map, slot offsets) for every authored screen."""
    composed = []
    for name, lines, frame, digits in SCREEN_SOURCES:
        try:
            patterns, tilemap, offsets = compose_screen(lines, (), frame, digits)
        except ValueError as error:
            raise ValueError(f"{GAME.id}: screens.json screen {name!r}: {error}") from None
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


def screen_pools() -> list[tuple[bytes, list[int]]]:
    """Screens that can share one pattern block, and the block.

    show_screen copies a record's patterns wherever they are, so text screens
    that draw with the same digits compose against one shared block: each
    keeps only its map. A screen joins the first pool whose union with it
    stays within SCREEN_PATTERN_CAPACITY; pools never mix digit styles,
    because patterns 0-10 are the runtime digits and the blank.
    Returns (pattern block, member screen indices) per pool."""
    pools: list[tuple[list[bytes], list[int]]] = []
    for number, (name, patterns, _, _) in enumerate(screen_assets()):
        own = [patterns[i:i + 16] for i in range(0, len(patterns), 16)]
        for block, members in pools:
            if block[:BLANK_PATTERN + 1] != own[:BLANK_PATTERN + 1]:
                continue
            extra = [pattern for pattern in own if pattern not in block]
            if len(block) + len(extra) <= SCREEN_PATTERN_CAPACITY:
                block.extend(extra); members.append(number)
                break
        else:
            pools.append((list(own), [number]))
    return [(b"".join(block), members) for block, members in pools]


def screen_directory() -> tuple[bytes, bytes]:
    """The screen bank and the overflow: (bank SCREEN_ROM_BANK from $4000,
    bank SCREEN_OVERFLOW_ROM_BANK from SCREEN_OVERFLOW_ADDRESS).

    The directory comes first, one record per screen: pattern count, pattern
    address, map address, the payload's bank, slot count and then
    SCREEN_SLOT_CAPACITY screen-relative offsets, so the loader streams both
    payloads and learns its rewritable cells without a second table. Pattern
    blocks are pooled (screen_pools); maps are remapped to their pool."""
    assets = screen_assets()
    places = {SCREEN_ROM_BANK: [SCREEN_ROM_ADDRESS + len(assets) * SCREEN_RECORD_BYTES, bytearray(), 0x8000],
              SCREEN_OVERFLOW_ROM_BANK: [SCREEN_OVERFLOW_ADDRESS, bytearray(), 0x8000]}

    def place(data: bytes) -> tuple[int, int]:
        for bank, spot in places.items():
            if spot[0] + len(data) <= spot[2]:
                address = spot[0]; spot[0] += len(data); spot[1].extend(data)
                return bank, address
        raise ValueError(f"{GAME.id}: the {len(assets)} screens do not fit the screen bank and its overflow; "
                         "each distinct pattern costs 16 bytes and each screen's map 360: "
                         + ", ".join(f"{name} {len(patterns) // 16}" for name, patterns, _, _ in assets))

    records: dict[int, bytes] = {}
    for block, members in screen_pools():
        pool = [block[i:i + 16] for i in range(0, len(block), 16)]
        where = {pattern: n for n, pattern in reversed(list(enumerate(pool)))}
        # A record has one bank byte for its patterns and its map, so a pool's
        # block sits in the bank of every map that uses it: a pool that runs
        # out of room carries on with a second copy of its block in the next.
        remaining = list(members)
        while remaining:
            bank = next((b for b, spot in places.items()
                         if spot[0] + len(block) + SCREEN_MAP_BYTES <= spot[2]), None)
            if bank is None:
                place(bytes(len(block) + SCREEN_MAP_BYTES))      # raises, naming every screen
            spot = places[bank]
            pattern_address = spot[0]; spot[0] += len(block); spot[1].extend(block)
            while remaining and spot[0] + SCREEN_MAP_BYTES <= spot[2]:
                number = remaining.pop(0)
                name, patterns, tilemap, offsets = assets[number]
                own = [patterns[i:i + 16] for i in range(0, len(patterns), 16)]
                remapped = bytes(where[own[cell]] for cell in tilemap)
                map_address = spot[0]; spot[0] += len(remapped); spot[1].extend(remapped)
                record = bytearray((len(pool), pattern_address & 255, pattern_address >> 8,
                                    map_address & 255, map_address >> 8, bank, len(offsets)))
                for index in range(SCREEN_SLOT_CAPACITY):
                    slot = offsets[index] if index < len(offsets) else NO_SLOT
                    record.extend((slot & 255, slot >> 8))
                records[number] = bytes(record)
    directory = b"".join(records[number] for number in range(len(assets)))
    assert len(directory) == len(assets) * SCREEN_RECORD_BYTES
    return directory + bytes(places[SCREEN_ROM_BANK][1]), bytes(places[SCREEN_OVERFLOW_ROM_BANK][1])


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
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_PAYLOAD_BANK)
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_SLOT_COUNT)
    a.ld_rr_nn("de", SCREEN_SLOTS)
    a.ld_rr_nn("bc", 2 * SCREEN_SLOT_CAPACITY); a.call("copy_bc")
    # The patterns and the map are in the bank the record names.
    a.ld_a_abs(SCREEN_PAYLOAD_BANK); a.ld_abs_a(0x2000)
    a.xor_r("a"); a.ld_abs_a(SCREEN_HOLD)
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
    # Slot offsets are screen-relative; expand the 20-column row to 32. Both
    # halves of the offset take part: a screen reserves cells past 255 now.
    a.ld_r_n("b", 0)
    a.label("screen_slot_rows")
    a.ld_r_r("a", "e"); a.sub_n(SCREEN_COLUMNS); a.ld_r_r("c", "a")
    a.ld_r_r("a", "d"); a.sbc_a_n(0); a.jr("screen_slot_ready", "c")
    a.ld_r_r("d", "a"); a.ld_r_r("e", "c"); a.inc_r("b"); a.jr("screen_slot_rows")
    a.label("screen_slot_ready")
    # HL = $9800 + row * 32 + column. Shifting HL rather than A keeps the
    # carry: row eight onwards passes 256 and used to lose it, which put every
    # digit the runtime wrote eight rows above where it belonged. The continue
    # code sat on row nine, so it was never once visible on a real screen.
    a.ld_r_r("l", "b"); a.ld_r_n("h", 0)
    for _ in range(5): a.add_hl_rr("hl")
    a.ld_r_r("a", "e"); a.add_a_r("l"); a.ld_r_r("l", "a")
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

    # A results screen is the only place a number becomes digits, and it does
    # it with the LCD off, so plain repeated subtraction is fast enough and
    # needs no division routine anywhere near the renderer.
    a.label("screen_write_number")   # SCREEN_VALUE = u16, B = digits, C = first slot
    a.ld_r_r("a", "b"); a.ld_abs_a(SCREEN_DIGITS_LEFT)
    a.ld_r_r("a", "c"); a.ld_abs_a(SCREEN_SLOT_INDEX)
    a.ld_r_n("a", len(SCREEN_NUMBER_POWERS)); a.sub_r("b"); a.add_a_r("a")
    a.ld_r_r("e", "a"); a.ld_r_n("d", 0)
    a.ld_rr_label("hl", "screen_number_powers"); a.add_hl_rr("de")
    store_hl(a, SCREEN_POWER_PTR)
    a.label("screen_number_digit")
    load_hl(a, SCREEN_POWER_PTR)
    a.ldi_a_hl(); a.ld_r_r("c", "a"); a.ldi_a_hl(); a.ld_r_r("b", "a")   # BC = power
    store_hl(a, SCREEN_POWER_PTR)
    a.ld_r_n("d", 0)                                                     # D = digit
    a.label("screen_number_subtract")
    load_hl(a, SCREEN_VALUE)
    a.ld_r_r("a", "l"); a.sub_r("c"); a.ld_r_r("e", "a")
    a.ld_r_r("a", "h"); a.sbc_a_r("b"); a.jr("screen_number_digit_done", "c")
    a.ld_r_r("h", "a"); a.ld_r_r("l", "e"); store_hl(a, SCREEN_VALUE)
    a.inc_r("d"); a.jr("screen_number_subtract")
    a.label("screen_number_digit_done")
    a.ld_a_abs(SCREEN_SLOT_INDEX); a.add_a_n(SCREEN_DIGITS & 255)
    a.ld_r_r("l", "a"); a.ld_r_n("h", SCREEN_DIGITS >> 8)
    a.ld_r_r("a", "d"); a.ld_hl_a()
    a.ld_a_abs(SCREEN_SLOT_INDEX); a.inc_r("a"); a.ld_abs_a(SCREEN_SLOT_INDEX)
    a.ld_a_abs(SCREEN_DIGITS_LEFT); a.dec_r("a"); a.ld_abs_a(SCREEN_DIGITS_LEFT)
    a.jr("screen_number_digit", "nz")
    a.ret()
    a.label("screen_number_powers")
    a.bytes(b"".join(bytes((value & 0xFF, value >> 8)) for value in SCREEN_NUMBER_POWERS),
            "decimal place values")

    a.label("screen_value_seconds")   # SCREEN_VALUE: VBlanks -> whole seconds
    a.ld_r_n("d", 0); a.ld_r_n("e", 0)
    a.label("screen_seconds_loop")
    load_hl(a, SCREEN_VALUE)
    a.ld_r_r("a", "l"); a.sub_n(VBLANKS_PER_SECOND); a.ld_r_r("c", "a")
    a.ld_r_r("a", "h"); a.sbc_a_n(0); a.jr("screen_seconds_done", "c")
    a.ld_r_r("h", "a"); a.ld_r_r("l", "c"); store_hl(a, SCREEN_VALUE)
    a.inc_rr("de"); a.jr("screen_seconds_loop")
    a.label("screen_seconds_done")
    a.ld_r_r("h", "d"); a.ld_r_r("l", "e"); store_hl(a, SCREEN_VALUE); a.ret()

    a.label("screen_number_from")   # HL -> a u16 in memory; B digits, C slot
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_VALUE)
    a.ld_a_hl(); a.ld_abs_a(SCREEN_VALUE + 1)
    a.jp("screen_write_number")

    a.label("screen_seconds_from")  # the same, in VBlanks
    a.ldi_a_hl(); a.ld_abs_a(SCREEN_VALUE)
    a.ld_a_hl(); a.ld_abs_a(SCREEN_VALUE + 1)
    a.push("bc"); a.call("screen_value_seconds"); a.pop("bc")
    a.jp("screen_write_number")

    a.label("screen_sector_stats")  # kills and time for the sector just cleared
    a.ld_a_abs(SECTOR_KILLS); a.ld_abs_a(SCREEN_VALUE)
    a.xor_r("a"); a.ld_abs_a(SCREEN_VALUE + 1)
    a.ld_r_n("b", 2); a.ld_r_n("c", PASSWORD_DIGITS); a.call("screen_write_number")
    if ITEM_DROPS:
        # The share of the placed items taken, in the three cells after the
        # time, its leading zeros blank: "ITEMS  78%".
        items_slot = PASSWORD_DIGITS + 2 + 3
        a.ld_a_abs(SECTOR_ITEMS); a.ld_abs_a(SCREEN_VALUE)
        a.xor_r("a"); a.ld_abs_a(SCREEN_VALUE + 1)
        a.ld_r_n("b", 3); a.ld_r_n("c", items_slot); a.call("screen_write_number")
        a.ld_rr_nn("hl", SCREEN_DIGITS + items_slot)
        for _ in range(2):
            a.ld_a_hl(); a.or_r("a"); a.jr("screen_items_digits", "nz")
            a.ld_hl_n(BLANK_PATTERN); a.inc_rr("hl")
        a.label("screen_items_digits")
    a.ld_rr_nn("hl", SECTOR_TIME)
    a.ld_r_n("b", 3); a.ld_r_n("c", PASSWORD_DIGITS + 2); a.jp("screen_seconds_from")

    a.label("screen_campaign_stats")   # the whole run, on the ending
    a.ld_a_abs(CAMPAIGN_KILLS); a.ld_abs_a(SCREEN_VALUE)
    a.xor_r("a"); a.ld_abs_a(SCREEN_VALUE + 1)
    a.ld_r_n("b", 3); a.ld_r_n("c", 0); a.call("screen_write_number")
    a.ld_rr_nn("hl", CAMPAIGN_TIME)                 # already whole seconds
    a.ld_r_n("b", 4); a.ld_r_n("c", 3); a.jp("screen_number_from")

    # Episode screens. The title opens episode one; a later episode's opening
    # shows whenever its first sector is about to load (a cleared sector or a
    # continue code), and an episode's closing shows on the intermission that
    # advanced LEVEL_INDEX onto the next episode, before that opening. Three
    # compares, no modulo: LEVEL_INDEX is fixed WRAM. Each screen waits for
    # START like any other and returns; the caller then loads the level.
    a.label("show_episode_closing")   # after an intermission only
    a.ld_a_abs(GAME_MODE); a.cp_n(MODE_INTERMISSION); a.ret("nz")
    a.ld_a_abs(LEVEL_INDEX)
    for episode, start in enumerate(EPISODE_STARTS):
        a.cp_n(start); a.jr(f"episode_closing_{episode}", "z")
    a.ret()
    for episode in range(len(EPISODE_STARTS)):
        a.label(f"episode_closing_{episode}")
        a.ld_r_n("a", SCREEN_EPISODE_CLOSINGS[episode]); a.call("show_screen"); a.call("screen_wait_start")
        a.jr("show_episode_opening")
    a.label("show_episode_opening")
    # The first episode's opening, when a game has one, is a prologue: the
    # title (or a continue code into the first level) leads to it.
    a.ld_a_abs(LEVEL_INDEX)
    for opening, start in enumerate(OPENING_STARTS):
        a.cp_n(start); a.jr(f"episode_opening_{opening}", "z")
    a.ret()
    for opening in range(len(OPENING_STARTS)):
        a.label(f"episode_opening_{opening}")
        a.ld_r_n("a", SCREEN_EPISODE_OPENINGS[opening]); a.call("show_screen"); a.jp("screen_wait_start")

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
    # Every screen but the title also passes when START has been held for a
    # second: story pages come one after another, and a hand (or a harness)
    # that holds START through them should not have to let go at each.
    a.ld_a_abs(SCREEN_INDEX); a.cp_n(SCREEN_TITLE); a.jr("screen_wait_start", "z")
    a.ld_a_abs(INPUT_LAST_RAW); a.and_n(0x80); a.jr("screen_start_held", "nz")
    a.ld_abs_a(SCREEN_HOLD); a.jr("screen_wait_start")
    a.label("screen_start_held")
    a.ld_a_abs(SCREEN_HOLD); a.inc_r("a"); a.ld_abs_a(SCREEN_HOLD)
    a.cp_n(SCREEN_HOLD_FRAMES); a.jr("screen_wait_start", "c")
    a.ld_r_n("a", 0x80); a.ret()

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
    # The old cursor cell may currently be blank because of blink. Restore its
    # digit before handing blink ownership to the new cursor.
    a.push("af"); a.push("bc"); a.call("screen_write_slot"); a.pop("bc"); a.pop("af")
    a.ld_abs_a(PASSWORD_CURSOR)
    a.xor_r("a"); a.ld_abs_a(PASSWORD_BLINK); a.ret()
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
