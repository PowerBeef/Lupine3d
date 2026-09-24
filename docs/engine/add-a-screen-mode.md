# Add a screen mode

The full-screen modes (title, game over, ending, intermission, code entry and
the episode screens) share one presentation: a screen owns the whole
background, drawn with the LCD off, while the world's composition window is
idle. A new mode is engine work; a game only supplies its text.

## 1. Name it

Add the screen's name to `FIXED_SCREENS` in `tools/lupine3d_v4/game.py`, with
its runtime fields in `SCREEN_FIELDS` (field name → digits the engine
writes), and author the screen in every game's `screens.json`: the loader
refuses a game without it, which is the point, since every game must say
what its new screen shows. Update `docs/schema/screens-v1.schema.json` and
[screen format](../reference/screen-format.md).

Runtime screen indices are positional: the fixed screens, then each
episode's closings, then openings (`SCREEN_EPISODE_CLOSINGS` and
`SCREEN_EPISODE_OPENINGS` in `screens.py` follow). Give the new mode its
index constant beside `SCREEN_TITLE` and the others, in the same order as
`FIXED_SCREENS`.

## 2. Compose it

`compose_screen` (`screens.py`) renders a screen's lines to patterns and a
20×18 map at build time: patterns 0-9 are the digits and 10 is blank, so a
runtime number or a cleared cell is one map write. It places field cells on
tile boundaries, refuses a line that straddles a tile row, and refuses more
than 128 patterns or `SCREEN_SLOT_CAPACITY` runtime cells. Never place
runtime cells by hand.

## 3. Give it a mode

In `emit_screens`: a full-screen mode owns the whole background with LCDC
`$81` and VBlank only (no HUD boundary, so no STAT split), writes with the
LCD off, ticks the music sequencer from its wait loop (never from VBlank),
and reads the pad itself, following rising edges. Runtime digits go into
the screen's reserved cells before the LCD comes back on, or at the top of
VBlank from the screen loop. `enter_world` repeats the boot upload, so a
screen never has to put the world back.

## 4. Prove it

Drive it in a scenario, add the frame to a snapshot suite, and run both
cores if the mode moves data with the LCD off:

```sh
make test playtest
make sameboy SAMEBOY_DIR=build/deps/SameBoy
make mgba MGBA_DIR=build/deps/mgba
```
