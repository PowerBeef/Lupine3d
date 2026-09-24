# Scenario format

A scenario is a driven playtest: a list of actions `tools/playtest.py` plays
on the built ROM in the host harness, checking **every** frame the ROM
publishes against the engine's model (geometry, composition, publication
safety, the OBJ budget). A game names its scenarios in `game.json`
`playtests`; `lupine run` plays the tour.

```json
{
  "name": "starter_tour",
  "world_mode": "empty",
  "snapshot_suite": "tour",
  "actions": [
    {"pose": [640, 3456, 192], "updates": 1, "capture": "spawn_room"},
    {"pose": [640, 3072, 192], "updates": 1, "capture": "airlock_approach"},
    {"buttons": ["b"], "updates": 2, "capture": "airlock_open"}
  ]
}
```

## Keys

| Key | Value |
|---|---|
| `name` | the scenario's name, for its report |
| `world_mode` | `living` (enemies move and fight) or `empty` (a still world, for looking at walls and doors); default `living` |
| `snapshot_suite` | the golden-image suite its captures are checked against: `tour`, `world` or `art`, matching its role in `game.json`. Leave it out for a scenario without goldens |
| `actions` | the actions, in order |

## Actions

Each action runs `updates` full world updates (published frames) with the
buttons held, then optionally captures the last one.

| Key | Value |
|---|---|
| `pose` | `[x_q8, y_q8, angle]`: place the player first. Q8 is cells × 256 (the middle of cell 2 is 640); the angle byte is 0 east, 64 south, 128 west, 192 north |
| `buttons` | buttons held for the action: `up`, `down`, `left`, `right`, `a`, `b`, `select`, `start` |
| `updates` | how many updates to run, at least 1; default 1 |
| `capture` | a name: the last update's picture is saved as `NN_<name>.png` and, with a suite, compared with the golden of that name |
| `expect` | world state the last update must show: any of `player_health`, `sentinel_state`, `sentinel_health`, `sentinel_visible`, `pickup_active`, `pickup_collected`, `exit_active`, `level_complete` |
| `expect_doors` | door id → state the last update must show (0 closed, 1 opening, 2 open) |
| `pose_at_drop` | `true`: move the player onto the first enemy's position (where its drop lies) |
| `aim_at_sentinel` | `true`: turn the player to face the first enemy |

`pose`, `pose_at_drop` and `aim_at_sentinel` write the player's position
into the machine: they are diagnostics, which is why a scenario is a
*driven* playtest. The controller route (`tools/playthrough.py`) plays a
whole game on controller input alone, with no writes to game RAM.

## What a run writes

`lupine run` writes the captures, a contact sheet, a GIF and `report.json`
(every update's cycles, frame checks and budgets) to
`build/games/<id>/playtest/coherence_tour/` (the showcase's under
`build/playtest/`), and the snapshot evidence to the build's `snapshots/`
directory. A frame that fails a check fails the run and names the update.
