"""Songs and the interrupt-driven sequencer that plays them.

CH1 is reserved for sound effects, so a gunshot never cuts the music. The
sequencer owns CH2 (pulse lead), CH3 (wave bass) and CH4 (noise percussion).

The tick deliberately does **not** run in VBlank. A staged publication owns
VBlank and finishes its GDMA with roughly one scanline to spare before 153, so
anything else there costs frames. While the world renders, the sequencer rides
the viewport-boundary STAT interrupt instead, forty-odd lines earlier; a
full-screen mode has no such boundary, so its wait loop ticks the sequencer
directly.

The tick can still land between a banked lookup's bank switch and its read, so
it must never touch the ROM bank either. The selected song is copied into a
WRAM bank once, at `music_start`, and the tick saves and restores SVBK around
the rows it reads. On a frame that is not a row boundary it only decrements a
counter in fixed WRAM.
"""
from .layout import *  # noqa: F401,F403

# 64 periods: five octaves of twelve semitones from C2, then four spare slots.
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NOTE_COUNT = 64
LOWEST_OCTAVE = 2

# Row byte vocabulary. 0 holds the previous note; 1 releases the channel.
HOLD, REST = 0, 1
NOTE_BASE = 2
# Percussion kinds on the noise channel, encoded in the same byte positions.
KICK, SNARE, HAT = 2, 3, 4

PULSE, WAVE, NOISE = range(3)

# A soft asymmetric wave: quiet in the low half, full in the upper, which gives
# the bass a hollow industrial body rather than a clean square.
WAVE_PATTERN = (0x02, 0x46, 0x8A, 0xCD, 0xEF, 0xFE, 0xDC, 0xA8,
                0x64, 0x21, 0x02, 0x46, 0x8A, 0xCD, 0xFE, 0xA8)

# Noise presets: NR41 length, NR42 envelope, NR43 polynomial, NR44 trigger.
NOISE_VOICES = {
    KICK:  (0x20, 0xC2, 0x55, 0xC0),
    SNARE: (0x30, 0xA2, 0x33, 0xC0),
    HAT:   (0x3C, 0x61, 0x22, 0xC0),
}


def note_periods() -> list[int]:
    """Game Boy channel periods for every note index.

    The hardware plays 131072 / (2048 - period) Hz, so the period is derived
    from equal temperament and clamped into the 11-bit register pair.
    """
    periods = []
    for index in range(NOTE_COUNT):
        # Index 0 is C at LOWEST_OCTAVE; A4 = 440 Hz is the anchor.
        semitone = index - (9 + 12 * (4 - LOWEST_OCTAVE))
        frequency = 440.0 * (2.0 ** (semitone / 12.0))
        period = round(2048 - 131072.0 / frequency)
        periods.append(max(0, min(2047, period)))
    return periods


def note(name: str, octave: int) -> int:
    """Row byte for one note, e.g. note("A#", 3)."""
    index = (octave - LOWEST_OCTAVE) * 12 + NOTE_NAMES.index(name)
    if not 0 <= index < NOTE_COUNT:
        raise ValueError(f"{name}{octave} is outside the sequencer's range")
    return NOTE_BASE + index


def _voices(pulse, wave, noise) -> list[tuple[int, int, int]]:
    """Zip three equal-length channel strings into rows."""
    if not len(pulse) == len(wave) == len(noise):
        raise ValueError("song channels must have the same number of rows")
    return list(zip(pulse, wave, noise))


def _line(pattern: str, notes: dict[str, int]) -> list[int]:
    """One channel line. '.' holds, '-' releases, any other key is a note."""
    return [HOLD if step == "." else REST if step == "-" else notes[step]
            for step in pattern]


def _title_song() -> tuple[int, int, list[tuple[int, int, int]]]:
    lead = {"a": note("A", 4), "c": note("C", 5), "d": note("D", 5),
            "e": note("E", 5), "f": note("F", 4), "g": note("G", 4)}
    bass = {"A": note("A", 2), "F": note("F", 2), "D": note("D", 2), "E": note("E", 2)}
    drum = {"k": KICK, "s": SNARE, "h": HAT}
    pulse = _line("a...c...d...c..."  "f...a...c...a..."
                  "d...f...g...f..."  "a...g...e...-...", lead)
    wave = _line("A.......F......."  "D.......A......."
                 "F.......E......."  "A.......E.......", bass)
    noise = _line("k.h.s.h.k.h.s.h."  "k.h.s.h.k.h.s.h."
                  "k.h.s.h.k.h.s.h."  "k.h.s.h.k.h.s.h.", drum)
    return 8, 0, _voices(pulse, wave, noise)


def _world_song() -> tuple[int, int, list[tuple[int, int, int]]]:
    """A darker, sparser loop: the lead stays out of the way of gunfire."""
    lead = {"d": note("D", 4), "f": note("F", 4), "g": note("G", 4),
            "a": note("A", 4), "c": note("C", 5), "b": note("A#", 4)}
    bass = {"D": note("D", 2), "C": note("C", 2), "B": note("A#", 2), "G": note("G", 2)}
    drum = {"k": KICK, "s": SNARE, "h": HAT}
    pulse = _line("d.......a......."  "f.......c......."
                  "g.......b......."  "a.......g.......", lead)
    wave = _line("D...D...D...C..."  "D...D...G...G..."
                 "C...C...B...B..."  "D...D...G...C...", bass)
    noise = _line("k...s...k...s..."  "k...s...k.k.s..."
                  "k...s...k...s..."  "k...s...k.s.s.h.", drum)
    return 10, 0, _voices(pulse, wave, noise)


def _victory_song() -> tuple[int, int, list[tuple[int, int, int]]]:
    lead = {"c": note("C", 5), "e": note("E", 5), "g": note("G", 5), "a": note("A", 5)}
    bass = {"C": note("C", 3), "G": note("G", 2), "F": note("F", 2)}
    drum = {"k": KICK, "s": SNARE, "h": HAT}
    pulse = _line("c.e.g...a...g..."  "e...c...g.......", lead)
    wave = _line("C.......G......."  "F.......C.......", bass)
    noise = _line("k.h.s.h.k.h.s.h."  "k.h.s.h.k.s.k.s.", drum)
    return 9, 0, _voices(pulse, wave, noise)


SONG_TITLE, SONG_WORLD, SONG_VICTORY = range(3)
SONG_SOURCES = (("title", _title_song), ("world", _world_song), ("victory", _victory_song))


def songs() -> list[tuple[str, int, int, bytes]]:
    """(name, speed, loop row, packed rows) for every song."""
    packed = []
    for name, build in SONG_SOURCES:
        speed, loop, rows = build()
        if not 1 <= speed <= 255:
            raise ValueError(f"song {name} has an unplayable speed")
        if not 0 <= loop < len(rows):
            raise ValueError(f"song {name} loops outside itself")
        if len(rows) > MUSIC_ROW_CAPACITY:
            raise ValueError(f"song {name} does not fit the sequencer's WRAM page")
        data = bytearray()
        for row in rows:
            for channel, value in enumerate(row):
                limit = NOTE_BASE + NOTE_COUNT if channel != NOISE else HAT + 1
                if not 0 <= value < limit:
                    raise ValueError(f"song {name} has an unplayable row value {value}")
            data.extend(row)
        packed.append((name, speed, loop, bytes(data)))
    return packed


def music_payload() -> bytes:
    """Directory of eight-byte records, then the packed rows.

    Record: speed, row count u16, loop row u16, row address u16, reserved.
    """
    records, payloads = bytearray(), []
    address = MUSIC_ROM_ADDRESS + len(SONG_SOURCES) * MUSIC_RECORD_BYTES + 2 * NOTE_COUNT
    for _, speed, loop, data in songs():
        rows = len(data) // MUSIC_ROW_BYTES
        records.extend((speed, rows & 255, rows >> 8, loop & 255, loop >> 8,
                        address & 255, address >> 8, 0))
        payloads.append(data)
        address += len(data)
    assert len(records) == len(SONG_SOURCES) * MUSIC_RECORD_BYTES
    assert address <= 0x8000, "songs exceed one MBC5 bank"
    table = bytearray()
    for period in note_periods():
        table.extend((period & 255, period >> 8))
    return bytes(records) + bytes(table) + b"".join(payloads)


def emit_music(a: Assembler) -> None:
    note_table_rom = MUSIC_ROM_ADDRESS + len(SONG_SOURCES) * MUSIC_RECORD_BYTES

    a.label("init_music")
    # Master enable, both outputs at full volume, every channel on both sides.
    a.ld_r_n("a", 0x80); a.ldh_n_a(NR52)
    a.ld_r_n("a", 0x77); a.ldh_n_a(NR50)
    a.ld_r_n("a", 0xFF); a.ldh_n_a(NR51)
    a.xor_r("a"); a.ld_abs_a(MUSIC_ENABLED); a.ld_abs_a(MUSIC_TICK)
    # The note periods move into the sequencer's WRAM page once: the tick
    # cannot reach banked ROM, and this table never changes.
    a.ldh_a_n(SVBK); a.push("af")
    a.ld_r_n("a", MUSIC_WRAM_BANK); a.ldh_n_a(SVBK)
    a.ld_r_n("a", MUSIC_ROM_BANK); a.ld_abs_a(0x2000)
    a.ld_rr_nn("hl", note_table_rom); a.ld_rr_nn("de", MUSIC_NOTE_TABLE)
    a.ld_rr_nn("bc", 2 * NOTE_COUNT); a.call("copy_bc")
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    a.pop("af"); a.ldh_n_a(SVBK)
    # The wave channel needs a body before it can sound at all.
    a.xor_r("a"); a.ldh_n_a(NR30)
    for index, byte in enumerate(WAVE_PATTERN):
        a.ld_r_n("a", byte); a.ldh_n_a(WAVE_RAM + index)
    a.jp("music_silence")

    a.label("music_start")   # A selects the song
    a.push("af")
    a.call("music_stop")
    a.pop("af")
    a.ld_abs_a(MUSIC_SONG)
    # HL = the song's directory record.
    a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    for _ in range(3): a.add_hl_rr("hl")          # eight bytes per record
    a.ld_rr_nn("de", MUSIC_ROM_ADDRESS); a.add_hl_rr("de")
    a.ld_r_n("a", MUSIC_ROM_BANK); a.ld_abs_a(0x2000)
    a.ldi_a_hl(); a.ld_abs_a(MUSIC_SPEED); a.ld_abs_a(MUSIC_TICK)
    a.ldi_a_hl(); a.ld_abs_a(MUSIC_ROW_COUNT); a.ldi_a_hl(); a.ld_abs_a(MUSIC_ROW_COUNT + 1)
    a.ldi_a_hl(); a.ld_abs_a(MUSIC_LOOP_ROW); a.ldi_a_hl(); a.ld_abs_a(MUSIC_LOOP_ROW + 1)
    # BC = row count * 3, the byte length to copy; DE = the song's rows.
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a")
    a.ld_a_abs(MUSIC_ROW_COUNT); a.ld_r_r("l", "a"); a.ld_a_abs(MUSIC_ROW_COUNT + 1); a.ld_r_r("h", "a")
    a.ld_r_r("b", "h"); a.ld_r_r("c", "l")
    a.add_hl_rr("hl"); a.add_hl_rr("bc")          # HL = rows * 3
    a.ld_r_r("b", "h"); a.ld_r_r("c", "l")
    a.ld_r_r("h", "d"); a.ld_r_r("l", "e")
    a.ldh_a_n(SVBK); a.push("af")
    a.ld_r_n("a", MUSIC_WRAM_BANK); a.ldh_n_a(SVBK)
    a.ld_rr_nn("de", MUSIC_ROWS); a.call("copy_bc")
    a.pop("af"); a.ldh_n_a(SVBK)
    a.ld_r_n("a", 1); a.ld_abs_a(0x2000)
    # Play from the first row on the next VBlank.
    a.xor_r("a"); a.ld_abs_a(MUSIC_ROW); a.ld_abs_a(MUSIC_ROW + 1)
    a.ld_r_n("a", MUSIC_ROWS & 255); a.ld_abs_a(MUSIC_POINTER)
    a.ld_r_n("a", MUSIC_ROWS >> 8); a.ld_abs_a(MUSIC_POINTER + 1)
    a.ld_r_n("a", 1); a.ld_abs_a(MUSIC_TICK); a.ld_abs_a(MUSIC_ENABLED)
    a.ret()

    a.label("music_stop")
    a.xor_r("a"); a.ld_abs_a(MUSIC_ENABLED)
    a.label("music_silence")
    # Silence only the sequencer's channels; CH1 belongs to sound effects.
    a.xor_r("a")
    for register in (NR22, NR32, NR42):
        a.ldh_n_a(register)
    a.ld_r_n("a", 0x80)
    for register in (NR24, NR34, NR44):
        a.ldh_n_a(register)
    a.ret()

    # Called from the viewport STAT boundary while the world runs and from the
    # screen loop otherwise, never from VBlank. Clobbers A, BC and HL; DE is
    # saved here, because neither caller saves it.
    # Effects own CH1 alone, so none of them can silence a bar of music.
    # Each is a sweep/envelope preset: one trigger, no per-frame service.
    for name, (sweep, duty, envelope, period, control) in (
        ("sound_hurt",     (0x36, 0x40, 0xD4, 0x30, 0xC5)),
        ("sound_kill",     (0x47, 0x80, 0xF3, 0x60, 0xC6)),
        ("sound_pickup",   (0x13, 0x80, 0xA2, 0xC0, 0xC6)),
        ("sound_complete", (0x14, 0x80, 0xB4, 0x90, 0xC6)),
    ):
        a.label(name)
        a.ld_r_n("a", sweep); a.ldh_n_a(NR10)
        a.ld_r_n("a", duty); a.ldh_n_a(NR11)
        a.ld_r_n("a", envelope); a.ldh_n_a(NR12)
        a.ld_r_n("a", period); a.ldh_n_a(NR13)
        a.ld_r_n("a", control); a.ldh_n_a(NR14)
        a.ret()

    a.label("music_tick")
    a.ld_a_abs(MUSIC_ENABLED); a.or_r("a"); a.ret("z")
    a.ld_a_abs(MUSIC_TICK); a.dec_r("a"); a.ld_abs_a(MUSIC_TICK); a.ret("nz")
    a.ld_a_abs(MUSIC_SPEED); a.ld_abs_a(MUSIC_TICK)
    a.push("de")
    # Rows live in a WRAM bank, never in ROM: a VBlank can land between a
    # banked lookup's bank switch and its read, and must not disturb it.
    a.ldh_a_n(SVBK); a.push("af")
    a.ld_r_n("a", MUSIC_WRAM_BANK); a.ldh_n_a(SVBK)
    a.ld_a_abs(MUSIC_POINTER); a.ld_r_r("l", "a")
    a.ld_a_abs(MUSIC_POINTER + 1); a.ld_r_r("h", "a")
    a.ldi_a_hl(); a.ld_r_r("b", "a")      # pulse
    a.ldi_a_hl(); a.ld_r_r("c", "a")      # wave
    a.ldi_a_hl(); a.push("af")            # noise, kept across the two voices
    a.ld_r_r("a", "l"); a.ld_abs_a(MUSIC_POINTER)
    a.ld_r_r("a", "h"); a.ld_abs_a(MUSIC_POINTER + 1)
    a.ld_r_r("a", "b"); a.call("music_pulse")
    a.ld_r_r("a", "c"); a.call("music_wave")
    a.pop("af"); a.call("music_noise")
    a.pop("af"); a.ldh_n_a(SVBK)
    a.call("music_advance_row")
    a.pop("de"); a.ret()

    a.label("music_advance_row")
    a.ld_a_abs(MUSIC_ROW); a.ld_r_r("l", "a"); a.ld_a_abs(MUSIC_ROW + 1); a.ld_r_r("h", "a")
    a.inc_rr("hl")
    a.ld_a_abs(MUSIC_ROW_COUNT); a.cp_r("l"); a.jr("music_row_stored", "nz")
    a.ld_a_abs(MUSIC_ROW_COUNT + 1); a.cp_r("h"); a.jr("music_row_stored", "nz")
    # The song ended: jump to its loop row and re-derive the row pointer.
    a.ld_a_abs(MUSIC_LOOP_ROW); a.ld_r_r("l", "a")
    a.ld_a_abs(MUSIC_LOOP_ROW + 1); a.ld_r_r("h", "a")
    a.push("hl")
    a.ld_r_r("b", "h"); a.ld_r_r("c", "l"); a.add_hl_rr("hl"); a.add_hl_rr("bc")
    a.ld_rr_nn("de", MUSIC_ROWS); a.add_hl_rr("de")
    a.ld_r_r("a", "l"); a.ld_abs_a(MUSIC_POINTER)
    a.ld_r_r("a", "h"); a.ld_abs_a(MUSIC_POINTER + 1)
    a.pop("hl")
    a.label("music_row_stored")
    a.ld_r_r("a", "l"); a.ld_abs_a(MUSIC_ROW)
    a.ld_r_r("a", "h"); a.ld_abs_a(MUSIC_ROW + 1)
    a.ret()

    a.label("music_note_period")  # A = row byte >= NOTE_BASE -> DE = period
    a.sub_n(NOTE_BASE); a.add_a_r("a")
    a.ld_r_r("l", "a"); a.ld_r_n("h", 0)
    a.ld_rr_nn("de", MUSIC_NOTE_TABLE); a.add_hl_rr("de")
    a.ldi_a_hl(); a.ld_r_r("e", "a"); a.ld_a_hl(); a.ld_r_r("d", "a"); a.ret()

    a.label("music_pulse")   # A = row byte
    a.or_r("a"); a.ret("z")
    a.cp_n(NOTE_BASE); a.jr("music_pulse_note", "nc")
    a.xor_r("a"); a.ldh_n_a(NR22); a.ld_r_n("a", 0x80); a.ldh_n_a(NR24); a.ret()
    a.label("music_pulse_note")
    a.call("music_note_period")
    a.ld_r_n("a", 0x80); a.ldh_n_a(NR21)       # 50% duty, no length counter
    a.ld_r_n("a", 0x97); a.ldh_n_a(NR22)       # decaying envelope
    a.ld_r_r("a", "e"); a.ldh_n_a(NR23)
    a.ld_r_r("a", "d"); a.and_n(7); a.or_n(0x80); a.ldh_n_a(NR24)
    a.ret()

    a.label("music_wave")
    a.or_r("a"); a.ret("z")
    a.cp_n(NOTE_BASE); a.jr("music_wave_note", "nc")
    a.xor_r("a"); a.ldh_n_a(NR30); a.ret()
    a.label("music_wave_note")
    a.call("music_note_period")
    a.ld_r_n("a", 0x80); a.ldh_n_a(NR30)       # DAC on
    a.xor_r("a"); a.ldh_n_a(NR31)
    a.ld_r_n("a", 0x20); a.ldh_n_a(NR32)       # full volume
    a.ld_r_r("a", "e"); a.ldh_n_a(NR33)
    a.ld_r_r("a", "d"); a.and_n(7); a.or_n(0x80); a.ldh_n_a(NR34)
    a.ret()

    a.label("music_noise")
    a.or_r("a"); a.ret("z")
    a.cp_n(NOTE_BASE); a.jr("music_noise_voice", "nc")
    a.xor_r("a"); a.ldh_n_a(NR42); a.ld_r_n("a", 0x80); a.ldh_n_a(NR44); a.ret()
    a.label("music_noise_voice")
    for kind, (length, envelope, polynomial, trigger) in sorted(NOISE_VOICES.items()):
        done = f"music_noise_{kind}"
        a.cp_n(kind); a.jr(done, "nz")
        a.ld_r_n("a", length); a.ldh_n_a(NR41)
        a.ld_r_n("a", envelope); a.ldh_n_a(NR42)
        a.ld_r_n("a", polynomial); a.ldh_n_a(NR43)
        a.ld_r_n("a", trigger); a.ldh_n_a(NR44)
        a.ret()
        a.label(done)
    a.ret()
