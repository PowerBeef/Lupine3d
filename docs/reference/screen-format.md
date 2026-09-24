# Screen format (`lupine-screens-v1`)

A game's full-screen modes (the title, game over, the ending, the
level-clear intermission, code entry, and each episode's opening and
closing) are text in the engine's font, authored in one file that
`game.json` `screens` names. `docs/schema/screens-v1.schema.json` states its
shape.

```json
{
  "format": "lupine-screens-v1",
  "screens": {
    "title": [
      {"text": "STARTER", "y": 28, "colour": 2, "scale": 3},
      {"text": "PRESS START", "y": 92, "colour": 2},
      {"field": "skill", "label": "SKILL", "y": 114, "colour": 3}
    ]
  }
}
```

## Screens

`screens` maps each screen's name to its lines. The engine shows these, and a
file must author exactly these, no more:

| Screen | Shown | Fields the engine writes |
|---|---|---|
| `title` | at power-on; left and right choose the skill, START begins, SELECT opens code entry | `skill` (1 digit) |
| `gameover` | when the player dies; START retries the level | none |
| `ending` | after the last level | `kills` (3), `time` (4) |
| `intermission` | after every other level | `code` (4), `kills` (2), `time` (3) |
| `password` | code entry, from the title | `code` (4) |
| each episode's `opening` | before the episode's first level (not the first episode's) | none |
| each episode's `closing` | on the intermission after the episode's last level (not the last episode's) | none |

The episode screens take the names the episodes give them in `game.json`.

## Lines

A **text line** is centred:

| Key | Required | Value |
|---|---|---|
| `text` | yes | upper-case letters, digits, space and `- / . , ! ? : '` |
| `y` | yes | the top pixel row |
| `colour` | yes | 0..3: a colour of the shared `hud` palette (BG 1) |
| `scale` | no | pixel size of the 3×5 font, 1..4; default 1 |

A **field line** is a label followed by the digits the engine writes at run
time; the screen's fields must appear in the order the table above gives:

| Key | Required | Value |
|---|---|---|
| `field` | yes | `skill`, `code`, `kills` or `time` |
| `label` | yes | the text before the digits |
| `y`, `colour`, `scale` | as for text | |

## What the loader and the build refuse

- A character the font does not have (it would draw nothing).
- A text line wider than 152 pixels (38 characters at scale 1, 12 at
  scale 3) or outside the frame: a line's top is at least 5 and its bottom
  (`y + 5 × scale`) at most 139.
- A field line whose glyphs straddle two tile rows or run into the digits:
  the digits own whole 8×8 cells, placed by the engine, never by hand.
- A screen that needs more than 128 distinct 8×8 patterns, the ten digits
  and a blank included; and screens that together overflow their 16 KiB bank
  ([limits](limits.md)).

Each character advances 4 pixels at scale 1. Lines that share a tile row
share patterns, so text in the same rows is cheaper than text spread down
the screen.
