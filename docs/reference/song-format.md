# Song format (`lupine-song-v1`)

Every game has three songs, named in `game.json` `audio.songs`: `title`
(the title screen and code entry), `world` (every level that names no other)
and `victory` (a cleared level's intermission or debrief). It may add a
`gameover` song (the game over screen is silent without one), an `ending`
song (the ending plays `victory` without one), and in `audio.level_songs`
songs its levels name with their `music` key: the showcase plays a song per
episode and one for each episode's last, guarded sector. A game has at most
sixteen ([limits](limits.md)). Each is one JSON file;
`docs/schema/song-v1.schema.json` states its shape.

```json
{
  "format": "lupine-song-v1",
  "speed": 8,
  "loop_row": 0,
  "pulse": {
    "notes": {"c": "C5", "e": "E5", "g": "G5", "a": "A4"},
    "rows": ["c...e...g...e...", "a...c...e...c..."]
  },
  "wave": {
    "notes": {"C": "C3", "A": "A2"},
    "rows": ["C.......C.......", "A.......A......."]
  },
  "noise": {
    "notes": {"k": "kick", "s": "snare", "h": "hat"},
    "rows": ["k...h...s...h...", "k...h...s...h..."]
  }
}
```

## Keys

| Key | Value |
|---|---|
| `format` | `"lupine-song-v1"` |
| `speed` | frames per row, 1..255. The sequencer ticks once a frame (about 59.7 per second), so 8 is about 7.5 rows a second |
| `loop_row` | the row the song goes back to when it reaches the end, 0 to its last row |
| `pulse` | the melody, on CH2 |
| `wave` | the bass, on CH3 |
| `noise` | the drums, on CH4 |

Each channel has `notes`, a map from one character to what it plays, and
`rows`, a list of strings that are read one character per row, joined end to
end (split them into bars of 16 for reading; the split means nothing to the
engine). The three channels must have the same number of rows, at most
1,322 ([limits](limits.md)).

## A row

| Character | Plays |
|---|---|
| a key of `notes` | that note (or drum), from this row |
| `.` | holds: the channel keeps playing what it played |
| `-` | releases: the channel falls silent |

`pulse` and `wave` notes are written `C2` to `D#7`: a letter `A`-`G`, an
optional `#`, and an octave digit (no flats: write `A#` for B flat). `noise`
notes are `kick`, `snare` or `hat`, whose sounds are the game's
[sound file](sound.md) drum presets. A key is any single character except
`.` and `-`, and each channel has its own keys.

## How a song plays

When a mode starts a song, the engine copies it into WRAM bank 5 (three bytes
a row) and plays it from there, so the sequencer never switches the ROM bank.
The world ticks the sequencer from the viewport's STAT boundary and a
full-screen mode from its wait loop; it never runs in VBlank. A game's songs
share one 16 KiB ROM bank.

The showcase's songs are in `games/sable_outpost/audio/`; the starter's in
`games/starter/audio/` are shorter and simpler.
