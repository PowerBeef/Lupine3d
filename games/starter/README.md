# Starter

The smallest complete Lupine 3D game: two levels, two enemy kinds, one theme,
three songs and its own screens. It exists to be copied. Everything it builds
from is inside this folder, so a copy is a new game:

```sh
python tools/lupine.py new-game games/my_game       # a copy with its own id, title and header
python tools/lupine.py game check --game games/my_game
python tools/lupine.py build --game games/my_game   # build/games/my_game/lupine3d.gb
```

`build/games/<id>/lupine3d.gb` runs in any Game Boy Color emulator. This
page says what each file is and what to change first.

## What is here

| File | What it is | Edit it to |
|---|---|---|
| `game.json` | The manifest: the game's name, its episodes and levels, enemy kinds, weapons, themes, textures, palettes, HUD words, and which sprite plays which role | change anything about the game as a whole |
| `levels/first_steps.json` | A drone in a room; the exit door opens when every enemy is dead; the drone leaves a medkit | learn the level format |
| `levels/keycard.json` | A carrier drops a keycard that opens the door to the drone guarding the exit | see a keycard door and two kinds together |
| `screens.json` | Title, game over, ending, level-clear and continue-code screens, as text in the engine's font | retitle the game, rewrite its story |
| `audio/title.json`, `world.json`, `victory.json` | The three songs, one character per row on three channels | write your own music |
| `audio/sound.json` | The instruments and the nine sound effects, as register bytes | reshape a sound |
| `textures/*.png` | The wall, machinery and door textures: indexed 16x8 PNGs, the top half of a face | give the walls a new look |
| `art/sprites.json`, `art/native/*.png` | The enemy, weapon, HUD, portrait, drop, effect, beacon and fixture sheets, each checked against its record's size, palette and hash | redraw the art |
| `playtests/tour.json` | The driven tour `lupine run` plays, every frame checked against the engine's model | test what you changed |
| `snapshots/` | The tour's golden images, accepted with a note | review a visual change |

## What to edit first

1. **The title.** `title` in `game.json` and the `title` screen in
   `screens.json`. `lupine new-game` already gave the copy its own id,
   title and cartridge header.
2. **A level.** Open `levels/first_steps.json`: `rows` is the 16x16 map
   (`0` floor, `1` wall, `2` machinery, `3` door). Move a wall, then run
   `python tools/lupine.py game check --game games/my_game`: the compiler
   prints the level's certificate or says exactly why it refuses it.
3. **The colours.** The `training` theme in `game.json`: ceiling, floor, the
   wall tones and each enemy's four colours, as RGB555 triples (0..31 each).
4. **The enemies.** `kinds` in `game.json`: contact damage, speed, recovery
   and what each leaves behind (a `medkit` or a `keycard`).

Then build and look:

```sh
python tools/lupine.py build --game games/my_game
python tools/lupine.py run --game games/my_game --snapshot-mode record
```

`run` writes a contact sheet to `build/games/my_game/playtest/coherence_tour/`.
When the pictures are what you meant, keep them as your goldens:

```sh
python tools/lupine.py snapshot --game games/my_game accept --suite tour --note "first look"
```

## What the engine fixes

A game can hold 20 levels in up to 3 episodes, 4 enemy kinds, 4 themes and 7
wall textures; exactly 4 weapons; 16x16 levels with up to 6 doors, 6 enemies
and 16 wall fixtures. The loader names the limit and the reason when a game
passes one ([limits](../../docs/reference/limits.md)).

The starter's sprites and textures are copies of the showcase's
([Sable Outpost](../sable_outpost/)); its levels, theme, songs and screens
are its own.
