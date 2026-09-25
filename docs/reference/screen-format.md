# Screen format (`lupine-screens-v1`)

A game's full-screen modes are authored in one file that `game.json`
`screens` names. These are the title, game over, the ending, the level-clear
intermission (or a debrief after each level), code entry, and each episode's
opening and closing. `docs/schema/screens-v1.schema.json` states its shape.

```json
{
  "format": "lupine-screens-v1",
  "screens": {
    "title": {"frame": false, "lines": [
      {"image": "art/title/wordmark.png", "row": 1},
      {"say": "PRESS START", "row": 14, "colour": 2},
      {"field": "skill", "label": "SKILL", "row": 15, "colour": 1}
    ]},
    "gameover": [
      {"say": "SIGNAL LOST", "row": 4, "colour": 3},
      {"say": "PRESS START", "row": 15, "colour": 1}
    ]
  },
  "debriefs": [
    [{"say": "{sector}", "row": 1, "colour": 3}, {"say": "NEXT", "row": 12, "colour": 1},
     {"say": "{next}", "row": 13, "colour": 3}, {"field": "code", "label": "CODE ", "row": 8, "colour": 2, "column": 4},
     {"field": "kills", "label": "KILLS", "row": 9, "colour": 2, "column": 4},
     {"field": "time", "label": "TIME ", "row": 10, "colour": 2, "column": 4}]
  ]
}
```

## Screens

`screens` maps each screen's name to its lines. The engine shows the screens
below, and a file must author exactly these, no more:

| Screen | Shown | Fields the engine writes |
|---|---|---|
| `title` | at power-on and after the ending; left and right choose the skill, START begins, SELECT opens code entry | `skill` (1 digit) |
| `gameover` | when the player dies; START retries the level | none |
| `ending` | after the last level; START returns to the title | `kills` (3), `time` (4: the run's whole seconds, up to 9,999) |
| `intermission` | after every other level, unless the game has debriefs | `code` (4), `kills` (2), `time` (3), and in a game with items `items` (3: the share of the level's placed items taken, 0..100, leading zeros blank) |
| `password` | code entry, from the title | `code` (4) |
| each episode's `opening` | before the episode's first level; the first episode's is a prologue, shown after the title's START and before a continue code into the first level | none |
| each episode's `closing` | on the intermission after the episode's last level (not the last episode's) | none |

The episode screens take the names the episodes give them in `game.json`.

A screen is a list of lines, or `{"frame": false, "lines": [...]}` for one
drawn without the steel frame (the whole 20×18 map is then the screen's).

**Debriefs** (optional) replace the intermission with one screen per level
but the last, shown after that level: the place for a story. There must be
exactly as many as the campaign has levels less one. Each writes the
intermission's fields, and `{sector}` and `{next}` in its text become the
cleared level's `name` and the next one's, in capitals.

Every screen but the title also passes when START has been held for a
second, so a player holding START through a run of story pages is not made
to let go at each; the title still wants a press.

## Lines

A **reading line** (`say`) is text in the engine's reading face: one 8×8 tile
a character, so it sits on the tile grid and each character is one pattern.

| Key | Required | Value |
|---|---|---|
| `say` | yes | upper-case letters, digits, space and `- / . , ! ? : ' % < >`; in a debrief, also `{sector}` and `{next}` |
| `row` | yes | the tile row, 0..17 (1..16 inside the frame) |
| `colour` | yes | 0..3: a colour of the shared `hud` palette (BG 1) |
| `column` | no | the first tile column; without it the line is centred |

A line holds 18 characters inside the frame, 20 without it.

A **field** is a label followed by the digits the engine writes at run time.
With `row`, it is in the reading face: the label, one blank cell, then the
digits, from `column` or centred. Give every field on a screen the same
colour: a screen's runtime digits are one set of patterns. A screen's fields
must appear in the order the table above gives.

| Key | Required | Value |
|---|---|---|
| `field` | yes | `skill`, `code`, `kills`, `time` or `items` |
| `label` | yes | the text before the digits |
| `suffix` | no | reading-face text after the digits, such as `%` |
| `row`, `colour`, `column` | as for a reading line | |

An **image** is an indexed PNG drawn on the tile grid: whole 8×8 tiles,
palette indices 0..3 drawn in the four colours of BG 1, index 0 the
background. The showcase's title draws its wordmark and the helmet emblem
this way (`games/sable_outpost/art/tools/make_title_art.py` derives both).

| Key | Required | Value |
|---|---|---|
| `image` | yes | a PNG inside the game directory, relative to `game.json` |
| `row` | yes | its top tile row |
| `column` | no | its left tile column; without it the image is centred |

A **small line** is the 3×5 face at any pixel row and a scale, the face the
starter game's screens use:

| Key | Required | Value |
|---|---|---|
| `text` | yes | as for a reading line |
| `y` | yes | the top pixel row |
| `colour` | yes | 0..3 |
| `scale` | no | pixel size of the 3×5 font, 1..4; default 1 |

A small field has `y` and `scale` in place of `row` and `column`.

## What the loader and the build refuse

- A character a face does not have (it would draw nothing).
- A reading line wider than its screen, or off its rows; two reading lines
  or images on the same tile.
- A small line wider than 152 pixels (38 characters at scale 1, 12 at
  scale 3) or outside the frame: a line's top is at least 5 and its bottom
  (`y + 5 × scale`) at most 139.
- A small field whose glyphs straddle two tile rows or run into the digits:
  the digits own whole 8×8 cells, placed by the engine, never by hand.
- An image that is not an indexed PNG of whole tiles in indices 0..3, or that
  leaves its screen.
- Fields in two faces or two colours on one screen.
- A screen that needs more than 128 distinct 8×8 patterns, the ten digits
  and a blank included.
- Screens that together overflow the screen bank and its overflow. Text
  screens share pattern pools, so a page of reading text costs little more
  than its 360-byte map ([limits](limits.md)).
