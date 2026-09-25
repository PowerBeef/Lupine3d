"""The music sequencer: song data, where it ticks, and what it plays."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
from lupine3d_v4 import music  # noqa: E402
from sm83emu import CGB, run_to_world  # noqa: E402


class SongDataTests(unittest.TestCase):
    def test_note_periods_rise_with_pitch_and_stay_playable(self):
        periods = music.note_periods()
        self.assertEqual(len(periods), music.NOTE_COUNT)
        for lower, higher in zip(periods, periods[1:]):
            self.assertLess(lower, higher)
        self.assertTrue(all(0 < value < 2048 for value in periods))
        # 131072 / (2048 - period) Hz: the anchor and the bottom of the range.
        self.assertAlmostEqual(131072 / (2048 - periods[music.note("A", 4) - music.NOTE_BASE]),
                               440.0, delta=1.5)
        self.assertAlmostEqual(131072 / (2048 - periods[0]), 65.41, delta=1.0)

    def test_every_song_is_playable_and_fits_one_bank(self):
        for name, speed, loop, data in music.songs():
            rows = len(data) // music.MUSIC_ROW_BYTES
            self.assertEqual(len(data) % music.MUSIC_ROW_BYTES, 0, name)
            self.assertGreater(rows, 0, name)
            self.assertLessEqual(rows, br.MUSIC_ROW_CAPACITY, name)
            self.assertLess(loop, rows, name)
            self.assertGreaterEqual(speed, 1, name)
        payload = music.music_payload()
        self.assertEqual(payload, music.music_payload())
        self.assertLessEqual(len(payload), 0x4000)

    def test_the_directory_addresses_the_rows_it_describes(self):
        payload = music.music_payload()
        for index, (name, speed, loop, data) in enumerate(music.songs()):
            record = payload[index * br.MUSIC_RECORD_BYTES:(index + 1) * br.MUSIC_RECORD_BYTES]
            self.assertEqual(record[0], speed, name)
            self.assertEqual(record[1] | record[2] << 8, len(data) // music.MUSIC_ROW_BYTES, name)
            self.assertEqual(record[3] | record[4] << 8, loop, name)
            start = (record[5] | record[6] << 8) - br.MUSIC_ROM_ADDRESS
            self.assertEqual(payload[start:start + len(data)], data, name)


class SequencerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom, cls.asm, _ = br.make_rom()

    def _span(self, first, last):
        """The emitted bytes of one routine, from its label to the next."""
        start, end = self.asm.labels[first], self.asm.labels[last]
        self.assertLess(start, end)
        return self.rom[start:end]

    def test_the_sequencer_stays_out_of_vblank(self):
        # A staged publication finishes its GDMA about one scanline before 153.
        # The sequencer rides the viewport STAT boundary instead, so the VBlank
        # interrupt must not reach it at all.
        tick = self.asm.labels["music_tick"]
        ordered = sorted(self.asm.labels.items(), key=lambda item: item[1])
        start = self.asm.labels["vblank_isr"]
        end = next(value for _, value in ordered if value > start)
        body = self.rom[start:end]
        for opcode in (0xCD, 0xC3):     # call nn / jp nn
            self.assertNotIn(bytes((opcode, tick & 0xFF, tick >> 8)), body,
                             "the VBlank interrupt reaches the sequencer")
        # It does ride the raster boundary, and the screen loop ticks it too.
        stat = self.asm.labels["stat_isr"]
        stat_end = next(value for _, value in ordered if value > stat)
        self.assertIn(bytes((0xCD, tick & 0xFF, tick >> 8)), self.rom[stat:stat_end])

    def test_the_tick_never_switches_the_rom_bank(self):
        # An interrupt can land between a banked lookup's bank switch and its
        # read. Nothing the tick reaches may write the MBC5 bank register,
        # which is why songs are copied into WRAM instead of read from ROM.
        reachable = ("music_tick", "music_advance_row", "music_note_period",
                     "music_pulse", "music_wave", "music_noise")
        ordered = sorted(self.asm.labels.items(), key=lambda item: item[1])
        for name in reachable:
            address = self.asm.labels[name]
            following = next(value for _, value in ordered if value > address)
            body = self.rom[address:following]
            self.assertNotIn(bytes((0xEA, 0x00, 0x20)), body,
                             f"{name} writes the ROM bank register")

    def test_the_title_plays_and_advances_through_its_song(self):
        cgb = CGB(self.rom, self.asm.labels)
        cgb.button_provider = lambda *_: 0
        for _ in range(1_500_000):
            cgb.step()
        self.assertEqual(cgb.read8(br.GAME_MODE), br.MODE_TITLE)
        self.assertEqual(cgb.read8(br.MUSIC_ENABLED), 1)
        self.assertEqual(cgb.read8(br.MUSIC_SONG), br.SONG_TITLE)
        row = cgb.read8(br.MUSIC_ROW) | cgb.read8(br.MUSIC_ROW + 1) << 8
        count = cgb.read8(br.MUSIC_ROW_COUNT) | cgb.read8(br.MUSIC_ROW_COUNT + 1) << 8
        self.assertGreater(row, 0)
        self.assertLess(row, count)
        self.assertEqual(count, len(music.songs()[br.SONG_TITLE][3]) // music.MUSIC_ROW_BYTES)
        # Both outputs carry all four channels, and the wave body is loaded.
        self.assertEqual(cgb.io[0x25], 0xFF)
        self.assertEqual(cgb.io[0x26] & 0x80, 0x80)
        self.assertEqual(bytes(cgb.io[0x30:0x40]), bytes(music.WAVE_PATTERN))
        # The sequencer's own three channels are sounding.
        self.assertTrue(cgb.io[0x17])                 # CH2 envelope
        self.assertEqual(cgb.io[0x1A], 0x80)          # CH3 DAC enabled
        self.assertTrue(cgb.io[0x21])                 # CH4 envelope

    def test_every_level_plays_the_song_it_names(self):
        """A level's `music` is header byte 21; load_level keeps it for
        enter_world. The showcase gives each episode its song and each
        episode's guarded last sector another."""
        songs = br.GAME.song_ids
        episode_songs = ("world", "reactor", "spire")
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        for index, level in enumerate(br.CAMPAIGN):
            episode = next(n for n, start in enumerate((0,) + br.EPISODE_STARTS + (len(br.CAMPAIGN),)) if start > index) - 1
            last = index + 1 in br.EPISODE_STARTS + (len(br.CAMPAIGN),)
            self.assertEqual(level.song, songs["overseer" if last else episode_songs[episode]], level.name)
            cgb.write8(br.LEVEL_INDEX, index)
            cgb.call_subroutine("load_level", max_steps=4_000_000)
            self.assertEqual(cgb.read8(br.LEVEL_SONG), level.song, level.name)
        # Every directory record is a song the sequencer can start.
        self.assertEqual(len(music.songs()), len(songs))
        self.assertEqual((br.SONG_GAMEOVER, br.SONG_ENDING), (songs["gameover"], songs["ending"]))

    def test_entering_the_world_switches_songs_and_keeps_playing(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        self.assertEqual(cgb.read8(br.MUSIC_SONG), br.SONG_WORLD)
        self.assertEqual(cgb.read8(br.MUSIC_ENABLED), 1)
        before = cgb.read8(br.MUSIC_ROW) | cgb.read8(br.MUSIC_ROW + 1) << 8
        for _ in range(400_000):
            cgb.step()
        after = cgb.read8(br.MUSIC_ROW) | cgb.read8(br.MUSIC_ROW + 1) << 8
        self.assertNotEqual(before, after)
        # Rows were copied into the sequencer's WRAM page, not left in ROM.
        rows = music.songs()[br.SONG_WORLD][3]
        page = bytes(cgb.wramx[br.MUSIC_WRAM_BANK][br.MUSIC_ROWS - 0xD000:
                                                   br.MUSIC_ROWS - 0xD000 + len(rows)])
        self.assertEqual(page, rows)

    def test_a_shot_uses_channel_one_and_leaves_the_music_alone(self):
        cgb = run_to_world(CGB(self.rom, self.asm.labels))
        music_registers = lambda: bytes(cgb.io[0x16:0x24])
        cgb.ime = False           # freeze the sequencer for an exact comparison
        before = music_registers()
        cgb.call_subroutine("sound_shoot", max_steps=10_000)
        self.assertEqual(music_registers(), before)
        for effect in ("sound_hurt", "sound_kill", "sound_pickup", "sound_complete"):
            cgb.call_subroutine(effect, max_steps=10_000)
            self.assertEqual(music_registers(), before, effect)
        self.assertTrue(cgb.io[0x12])   # CH1 envelope was retriggered


if __name__ == "__main__":
    unittest.main()
