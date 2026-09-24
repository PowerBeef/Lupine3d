# Music and sound

A game has three songs and nine sound effects, all data:

- `audio/title.json`, `audio/world.json`, `audio/victory.json`: the songs
  ([song format](../reference/song-format.md));
- `audio/sound.json`: the instruments the songs play and the effects, as
  register bytes ([sound](../reference/sound.md)).

Music plays on three channels (CH2 melody, CH3 bass, CH4 drums) and effects
on the fourth (CH1), so a shot never cuts the music.

## Write a song

```json
{
  "format": "lupine-song-v1",
  "speed": 6,
  "loop_row": 0,
  "pulse": {"notes": {"e": "E4", "g": "G4", "a": "A4"}, "rows": ["e.g.a...e.g.a..."]},
  "wave": {"notes": {"E": "E2", "A": "A2"}, "rows": ["E...E...A...A..."]},
  "noise": {"notes": {"k": "kick", "s": "snare", "h": "hat"}, "rows": ["k.h.s.h.k.h.s.h."]}
}
```

Each character is one row: a key from `notes` starts that note, `.` holds,
`-` releases. The three channels must be the same length. `speed` is frames
per row (6 is about ten rows a second), and the song returns to `loop_row`
at its end.

## Change a sound

Each effect is five bytes written to NR10..NR14. Start from the starter's or
the showcase's `sound.json` and change one byte at a time: NR12's high
nibble is the starting volume and its low bits the fade, NR13 and NR14's low
bits the pitch, NR10 the sweep. Pan Docs, the Game Boy's hardware reference,
documents every bit.

## Listen

The harness checks frames, not sound. Build and play the ROM in an
emulator (SameBoy and mGBA are the pinned ones):

```sh
python tools/lupine.py build --game games/my_game
```

then open `build/games/my_game/lupine3d.gb`. `python tools/lupine.py game
check` refuses a song past 1,322 rows, a note outside C2..D#7, and a key its
rows use but its notes do not define.
