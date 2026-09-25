# Screens

The title, game over, ending, intermission and code-entry screens, each
episode's opening and closing, and optionally a debrief after every level,
are authored in your game's `screens.json`
([screen format](../reference/screen-format.md)). They draw in the shared HUD
palette's four colours, inside a steel frame unless a screen turns it off.

## Write a page of story

The reading face puts one character in each 8×8 tile, so a line sits on a
tile row and reads cleanly at the console's size. A framed page has rows 1
to 16 and 18 characters a row:

```json
"gameover": [
  {"say": "DOWN", "row": 4, "colour": 3},
  {"say": "THE DRONES WIN", "row": 6, "colour": 2},
  {"say": "THIS ONE.", "row": 7, "colour": 2},
  {"say": "PRESS START", "row": 15, "colour": 1}
]
```

- A line is centred unless it gives a `column`; `colour` is one of the HUD
  palette's four.
- Use upper-case letters, digits, space and `- / . , ! ? : '`. The loader
  refuses anything else, rather than draw nothing.
- Pages of reading text share their patterns, so a story costs about its
  maps, 360 bytes a page.

The 3×5 face with `text`, `y` and `scale` still works: it is what the
starter's screens use.

## Put a picture on the title

An `image` line draws an indexed PNG on the tile grid: whole 8×8 tiles,
palette indices 0 to 3 in the HUD palette's colours. Turn the frame off to
use the whole screen:

```json
"title": {"frame": false, "lines": [
  {"image": "art/title/wordmark.png", "row": 1},
  {"say": "PRESS START", "row": 14, "colour": 2},
  {"field": "skill", "label": "SKILL", "row": 15, "colour": 1}
]}
```

Make the PNG with a committed script, as the showcase does
(`games/sable_outpost/art/tools/make_title_art.py`), or draw it by hand; the
build only reads it. A screen holds 128 distinct patterns in all.

## The numbers a screen shows

Some screens have fields the engine writes at run time: the title's skill,
the intermission's (or a debrief's) code, kills and time, the ending's kills
and time, and the code entry's code. A field is a label; the engine puts its
digits after it:

```json
{"field": "code", "label": "CODE ", "row": 8, "colour": 2, "column": 4}
```

Keep the fields in the order the [screen format](../reference/screen-format.md)
table gives, and give a screen's fields one colour. Pad labels to one width
and give them one `column` to line their digits up.

## Tell the story between levels

A `debriefs` list replaces the intermission with a page after each level but
the last. `{sector}` and `{next}` become the level names:

```json
"debriefs": [
  [{"say": "{sector}", "row": 1, "colour": 3},
   {"say": "THE LIGHTS ARE OUT.", "row": 4, "colour": 2},
   {"field": "code", "label": "CODE ", "row": 8, "colour": 2, "column": 4},
   {"field": "kills", "label": "KILLS", "row": 9, "colour": 2, "column": 4},
   {"field": "time", "label": "TIME ", "row": 10, "colour": 2, "column": 4},
   {"say": "NEXT: {next}", "row": 13, "colour": 3}]
]
```

## Episode screens and a prologue

Name them in `game.json` (`opening` and `closing` on episodes) and author
each under that name. An `opening` on the first episode is a prologue,
shown after the title. A screen no episode names is refused as never shown.
Every screen but the title also passes when START is held for a second.

## Check

```sh
python tools/lupine.py game check --game games/my_game
python tools/lupine.py build --game games/my_game
make playthrough GAME=games/my_game RESTART=1
```

The build refuses a screen that needs more than 128 distinct patterns, an
image it cannot draw or lines that overlap. The controller route's contact
sheet shows the intermission or debriefs and the ending as the player sees
them.
