# Limits

What a game can hold. Every limit is a property of the engine, not of a
game, and each comes with the engine fact that sets it, so you know what
it would take to move one. The game loader (`tools/lupine3d_v4/game.py`)
and the level compiler (`tools/lupine3d_v4/levels.py`) refuse content past
a limit in these words; this table is `tools/lupine3d_v4/limits.py`, and
the documentation check holds the page to it.

Several limits share one budget, so they are proven together: `make limits`
builds a game at every maximum at once (`tools/make_limits_game.py`) and
enters its levels by continue code with every frame check.

## A game

| Limit | Minimum | Maximum | Counts | Why |
|---|---|---|---|---|
| `levels` | 1 | 20 | levels in the campaign | levels pack five to a ROM bank in banks 241-244; bank 245 holds the weapons |
| `episodes` | 1 | 3 | episodes | each episode after the first adds its screen dispatch to the fixed half of bank 0, which keeps 64 bytes free with three |
| `kinds` | 1 | 4 | enemy kinds | an actor's kind is two bits of its slot |
| `actor_palettes` | 1 | 3 | enemy palettes | OBJ palettes 1, 6 and 7 are the enemies'; the other five draw the weapon, drops, effects, decor and reticle |
| `contact_damage` | 0 | 170 | an enemy's contact damage | the hard skill adds half again, and the result must fit a byte |
| `weapons` | 4 | 4 | weapons | the weapon index is two bits and SELECT walks all four |
| `themes` | 1 | 4 | themes | each theme's 36-byte texture directory sits in the fixed half of bank 0 beside the resident engine, which leaves 64 bytes with three themes and three episodes |
| `textures` | 1 | 7 | wall textures | a texture is four 5 KiB shade blocks, three to a bank, and the textured kernel owns ten banks: thirty blocks |
| `screen_patterns` | 11 | 128 | distinct 8x8 patterns on one screen, the ten digits and a blank included | a screen's patterns are copied to $9000-$97FF, 128 patterns below the map |
| `hud_word` | 1 | 4 | characters in a HUD word | the HUD's objective panel is four characters wide |
| `song_rows` | 1 | 1322 | rows in one song | a playing song is copied into WRAM bank 5 above the sequencer's state, three bytes a row |

## A level

| Limit | Minimum | Maximum | Counts | Why |
|---|---|---|---|---|
| `level_size` | 16 | 16 | cells on a side of a level | the map is a 16x16 byte grid, one page |
| `doors_per_level` | 0 | 6 | doors in a level | a level's six-byte door records fill 48 bytes of its slot |
| `actors_per_level` | 0 | 6 | enemies in a level | six simulated actor slots; the OBJ budget admits four on screen at once |
| `fixtures_per_level` | 0 | 16 | wall fixtures in a level | a level's fixture records fill 256 bytes |

## Shared budgets

- **The fixed half of bank 0.** The resident engine runs from bank 0,
  which also holds each theme's 36-byte texture directory and each
  episode's screen dispatch (about 26 bytes after the first), and every
  weapon unlocked after the first level adds a compare. With the most
  themes and episodes the half still ends at `$3FF0`; past that the
  build names what grew.
- **The screen bank.** Every screen's distinct patterns and map share one
  16 KiB bank; the build names each screen's pattern count if they do not
  fit.
- **The music bank.** The three songs share one bank, three bytes a row.
