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
from .game import (DRUMS, EFFECTS, HOLD_STEP, LOWEST_OCTAVE, MUSIC_ROW_LIMIT, NOTE_COUNT, NOTE_NAMES,  # noqa: F401
                   REST_STEP, SONG_ROLES)

# 64 periods: five octaves of twelve semitones from C2, then four spare slots
# (NOTE_NAMES, NOTE_COUNT and LOWEST_OCTAVE are the song format's, game.py).
assert MUSIC_ROW_LIMIT == MUSIC_ROW_CAPACITY

# Row byte vocabulary. 0 holds the previous note; 1 releases the channel.
HOLD, REST = 0, 1
NOTE_BASE = 2
# Percussion kinds on the noise channel, encoded in the same byte positions.
KICK, SNARE, HAT = 2, 3, 4

PULSE, WAVE, NOISE = range(3)

# The game's instruments (its sound file, game.json `audio.sound`): the wave
# RAM the bass plays (the showcase's is a soft asymmetric wave, quiet in the
# low half and full in the upper, a hollow industrial body rather than a
# clean square) and the drum presets, NR41 length, NR42 envelope, NR43
# polynomial, NR44 trigger.
WAVE_PATTERN = GAME.sound.wave_pattern
NOISE_VOICES = {KICK + index: GAME.sound.drums[drum] for index, drum in enumerate(DRUMS)}


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


def _row_byte(step: int, first: int) -> int:
    """A song step as a row byte: hold, release, or `first` plus the note or drum."""
    return HOLD if step == HOLD_STEP else REST if step == REST_STEP else first + step


def _game_song(role: str):
    def build() -> tuple[int, int, list[tuple[int, int, int]]]:
        song = GAME.songs[role]
        rows = [(_row_byte(pulse, NOTE_BASE), _row_byte(wave, NOTE_BASE), _row_byte(noise, KICK))
                for pulse, wave, noise in zip(song.pulse, song.wave, song.noise)]
        return song.speed, song.loop_row, rows
    return build


# The game's songs (game.json `audio.songs`), in the sequencer's order.
SONG_TITLE, SONG_WORLD, SONG_VICTORY = range(3)
assert SONG_ROLES == ("title", "world", "victory")
SONG_SOURCES = tuple((role, _game_song(role)) for role in SONG_ROLES)


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


def emit_effect(a: Assembler, name: str) -> None:
    """`sound_<name>`: one write of NR10..NR14 from the game's effect preset.

    Clobbers A. A zero register value is `xor a`, anything else `ld a,n`."""
    a.label(f"sound_{name}")
    for register, value in zip((NR10, NR11, NR12, NR13, NR14), GAME.sound.effects[name]):
        if value:
            a.ld_r_n("a", value)
        else:
            a.xor_r("a")
        a.ldh_n_a(register)
    a.ret()


def emit_audio(a: Assembler) -> None:
    """Sound on, both terminals, and the shot and door effects (the section
    the engine's first version emitted; same order, same bytes)."""
    a.label("init_audio")
    a.ld_r_n("a", 0x80); a.ldh_n_a(NR52)
    a.ld_r_n("a", 0x77); a.ldh_n_a(NR50)
    a.ld_r_n("a", 0x11); a.ldh_n_a(NR51)
    a.ret()
    emit_effect(a, "shoot")
    emit_effect(a, "door")


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
    for name in ("hurt", "kill", "pickup", "complete"):
        emit_effect(a, name)

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
    a.ld_r_n("a", GAME.sound.pulse_duty); a.ldh_n_a(NR21)       # duty (the showcase: 50%, no length counter)
    a.ld_r_n("a", GAME.sound.pulse_envelope); a.ldh_n_a(NR22)   # envelope (the showcase: decaying)
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
    a.ld_r_n("a", GAME.sound.wave_volume); a.ldh_n_a(NR32)      # output level (the showcase: full)
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
