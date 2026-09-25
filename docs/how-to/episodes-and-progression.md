# Episodes and progression

A game is a campaign: its episodes' levels, played in order. This page is
how the order, the episodes, the weapons the player owns and the continue
codes fit together.

## The campaign

`game.json` `episodes` lists one to three episodes; each lists its level
files. The campaign is every episode's levels in order, at most 20. Death
retries the current level; clearing one shows the intermission (the level's
kills, time and continue code), or that level's debrief if the game has
debriefs ([screens](screens.md)), and loads the next; the last level shows
the ending, and START there returns to the title.

```json
"episodes": [
  {"name": "Surface", "levels": ["levels/gate.json", "levels/yard.json"], "closing": "surface_done"},
  {"name": "Below", "levels": ["levels/stair.json", "levels/vault.json"], "opening": "below_begins"}
]
```

## Episode screens

Every episode but the first has an `opening` screen, shown before its first
level; every episode but the last has a `closing` screen, shown on the
intermission after its last level. The first episode may have an `opening`
too: a prologue, shown after the title's START. The ending closes the last. The names are yours; author each one in
`screens.json` ([screens](screens.md)). A continue code into an episode's
first level shows that episode's opening.

## Weapons the player owns

Each weapon's `from_level` is the first level (1-based) that owns it, or
`null` for never:

```json
"weapons": [
  {"name": "pistol", "sprite": "pistol", "damage": 1, "recovery_ticks": 0, "from_level": 1},
  {"name": "rifle", "sprite": "rifle", "damage": 2, "recovery_ticks": 15, "from_level": 1},
  {"name": "cannon", "sprite": "cannon", "damage": 4, "recovery_ticks": 40, "from_level": 3},
  {"name": "spare", "sprite": "spare", "damage": 2, "recovery_ticks": 6, "from_level": null}
]
```

The first weapon's is always 1, and the list never goes back down: list the
weapons in the order the player gets them, never-owned ones last. The
engine derives what is owned from the level index when a level loads, so a
continue code restores the arsenal, and a code for an earlier level takes a
later weapon away.

## Continue codes

There is no cartridge RAM, so progress is a four-digit code the player
writes down. The build generates one code per level and skill, distinct and
never starting with a zero; SELECT on the title opens code entry. Adding,
removing or reordering levels changes the codes, so treat them as content:
a code published for one build does not open another.

## Checks

```sh
python tools/lupine.py game check --game games/my_game
make playthrough GAME=games/my_game RESTART=1
```

`game check` refuses an episode without the screens it needs, a level listed
twice, and a campaign past the limits. The controller route plays the whole
campaign through every intermission and episode screen and restarts it;
`SECTORS=A-B` plays a range, entered by its continue code.
