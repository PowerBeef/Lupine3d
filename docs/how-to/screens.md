# Screens

The title, game over, ending, intermission and code-entry screens, and each
episode's opening and closing, are text in your game's `screens.json`
([screen format](../reference/screen-format.md)). The engine draws them in
its 3×5 font inside a steel frame, in the shared HUD palette.

## Rewrite a screen

```json
"gameover": [
  {"text": "DOWN", "y": 48, "colour": 3, "scale": 2},
  {"text": "THE DRONES WIN THIS ONE", "y": 84, "colour": 1},
  {"text": "PRESS START", "y": 110, "colour": 2}
]
```

- A line is centred; `y` is its top pixel, `colour` one of the HUD palette's
  four, `scale` 1 to 4.
- Use upper-case letters, digits, space and `- / . , ! ? : '`. The loader
  refuses anything else, rather than draw nothing.
- A line fits 152 pixels: 38 characters at scale 1, 19 at scale 2, 12 at
  scale 3.

## The numbers a screen shows

Some screens have fields the engine writes at run time: the title's skill,
the intermission's code, kills and time, the ending's kills and time, and
the code entry's code. A field line is a label:

```json
{"field": "code", "label": "CODE", "y": 58, "colour": 3}
```

The engine places the digits on whole 8×8 cells after the label; keep the
fields in the order the [screen format](../reference/screen-format.md)
table gives, and keep a field's label on one tile row (a `y` whose line of
text does not cross a multiple of 8).

## Episode screens

Name them in `game.json` (`opening` and `closing` on episodes) and author
each under that name. A screen no episode names is refused as never shown.

## Check

```sh
python tools/lupine.py game check --game games/my_game
python tools/lupine.py build --game games/my_game
make playthrough GAME=games/my_game RESTART=1
```

The build refuses a screen that needs more than 128 distinct patterns or a
field that runs into its label; the controller route's contact sheet shows
the intermission and the ending as the player sees them.
