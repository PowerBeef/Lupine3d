# Sound (`lupine-sound-v1`)

A game's `audio/sound.json` (named by `game.json` `audio.sound`) holds the
sequencer's three instruments and the nine sound effects, as the register
bytes the console writes. `docs/schema/sound-v1.schema.json` states its
shape. A byte is a whole number (0..255) or a string `"0x00"`..`"0xFF"`.

The Game Boy Color has four sound channels. The engine gives **CH1 to sound
effects alone** and **CH2, CH3 and CH4 to music**, so firing never cuts a bar
of the music:

| Channel | Plays | Configured by |
|---|---|---|
| CH1, pulse with sweep | the effects | `effects` |
| CH2, pulse | the melody (a song's `pulse` channel) | `instruments.pulse` |
| CH3, wave | the bass (`wave`) | `instruments.wave` |
| CH4, noise | the drums (`noise`) | `instruments.noise` |

```json
{
  "format": "lupine-sound-v1",
  "instruments": {
    "pulse": {"duty": "0x80", "envelope": "0x97"},
    "wave": {"volume": "0x20", "pattern": ["0x02", "0x46", "0x8A", "0xCD", "0xEF", "0xFE", "0xDC", "0xA8",
                                           "0x64", "0x21", "0x02", "0x46", "0x8A", "0xCD", "0xFE", "0xA8"]},
    "noise": {"kick": ["0x20", "0xC2", "0x55", "0xC0"], "snare": ["0x30", "0xA2", "0x33", "0xC0"],
              "hat": ["0x3C", "0x61", "0x22", "0xC0"]}
  },
  "effects": {
    "shoot": ["0x15", "0x80", "0xF2", "0x00", "0xC7"]
  }
}
```

(Every effect must be present; the example shows one.)

## Instruments

| Key | Bytes | Register |
|---|---|---|
| `pulse.duty` | 1 | NR21: the melody's duty cycle (bits 7-6: 12.5, 25, 50 or 75%) |
| `pulse.envelope` | 1 | NR22: its volume envelope (bits 7-4 start volume, bit 3 direction, bits 2-0 pace) |
| `wave.volume` | 1 | NR32: the bass's output level (bits 6-5: mute, 100, 50, 25%) |
| `wave.pattern` | 16 | wave RAM: thirty-two 4-bit samples, high nibble first |
| `noise.kick`, `noise.snare`, `noise.hat` | 4 each | NR41..NR44 for that drum: length, envelope, the noise's clock and width, and the trigger |

## Effects

Each effect is one write of NR10..NR14 (sweep, duty and length, envelope,
frequency low, frequency high with the trigger bit), five bytes, played once
with no per-frame service.

| Effect | Plays when |
|---|---|
| `shoot` | the player fires |
| `door` | a door starts to open |
| `swap` | SELECT swaps to another weapon |
| `keycard` | a keycard door refuses a player without a card |
| `locked` | the exit door refuses while enemies remain |
| `hurt` | an enemy's touch takes health |
| `kill` | an enemy dies |
| `pickup` | the player picks up a drop |
| `complete` | the player reaches the open exit |

A zero register byte is emitted one byte shorter than any other value, so
effects live in resident code that the [limits](limits.md) account for.
