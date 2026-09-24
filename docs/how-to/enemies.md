# Enemies

An enemy kind is data: stats, a palette and what it drops. Every kind uses
the same sprite frames (the `actor_*` roles) in its own palette, so a kind
costs a few bytes of ROM and no VRAM.

## Define a kind

In `game.json`:

```json
"actor_palettes": ["drone", "carrier"],
"kinds": [
  {"name": "drone", "contact_damage": 6, "recovery_ticks": 8, "step_q8": 8, "palette": "drone", "drop": "medkit"},
  {"name": "carrier", "contact_damage": 4, "recovery_ticks": 8, "step_q8": 12, "palette": "carrier", "drop": "keycard"}
]
```

| Field | Meaning |
|---|---|
| `contact_damage` | health one touch takes at the authored skill (0..170); easy halves it, hard adds half again |
| `recovery_ticks` | simulation ticks between two touches |
| `step_q8` | speed: distance per step in 1/256 cell (8 walks, 15 sprints) |
| `palette` | one of `actor_palettes`; each theme gives it four colours |
| `drop` | `medkit` (restores the health the level's pickup says) or `keycard` (opens the level's keycard doors) |

A game has up to four kinds and three enemy palettes: two kinds may share a
palette (the showcase's boss wears the Sentinel's colours with the heaviest
contact damage). Give each palette its colours in every theme's `actors`.

## Field them

A level's `entities` place up to six enemies:

```json
{"kind": "carrier", "x_q8": 1408, "y_q8": 1920, "health": 2, "activation_radius_q4": 96}
```

`health` is hit points, 1..255 (a hit takes the weapon's `damage`).
`activation_radius_q4` is how near the player must come, in sixteenths of a
cell, before a dormant enemy wakes; today the engine folds the level's
first enemy's radius to whole cells and uses it for every enemy in the level.
A level declares the drops its enemies leave in `pickups`, and the compiler
refuses a keycard carried only by an enemy behind the door it opens.

## How they behave

A dormant enemy wakes inside its radius, then chases while it can see the
player and patrols when it cannot, turning a quarter turn when a step is
refused. It hits by touching: an adjacent cell with a clear line of sight,
and across a diagonal only when both side cells are open. Six are simulated;
the OBJ budget admits four on screen at once, so keep at most four on any
one sightline.

## Check

```sh
python tools/lupine.py game check --game games/my_game
make playthrough GAME=games/my_game RESTART=1
```

The controller route fights every enemy with the weapons the player owns;
if its report shows the player dying, the level is too hard for the
route's plain tactics, and probably for a first-time player.
