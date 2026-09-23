# The level certificate

Every `lupine-level-v2` level compiles with a certificate: a set of measured
properties the compiler refuses to ship without. It exists because the
renderer has a legible envelope (a 16×16 map seen through 80 rays at
160×120 with four actors) and because the controller route that plays the
whole campaign in CI has to be able to finish every sector. `release_check.py`
gates every campaign level on it, not only the first.

`python tools/lupine.py level check levels/<file>.json` prints it:

```
levels/living_world.json: ok - Sable Outpost: 16x16, 4 doors, 1 actors, 1 drops, 16 fixtures, 52 segments
  certificate: 70 walkable, 0 unreachable, critical path 15 steps/5 turns, sightline 6, room 4x3,
  door separation 11, seams 2, singleton runs 2
```

`lupine level info` prints the same as JSON, and the build manifest carries
the first level's numbers (`walkable_level_cells`, `critical_path_steps`, ...).

## Hard rules (every format)

| Rule | Why |
|---|---|
| Outer ring solid; doors and fixtures off the boundary | the DDA never has to bounds-check a ray |
| Every material-3 cell has one door record and vice versa | door geometry is finite and shared by rays, hitscan, line of sight and collision |
| Spawn cell walkable with `0x38` Q8 clearance at all four corners | the player must not start inside a wall |
| Every actor at least `safe_radius_cells` walking steps from the spawn with doors closed, or unreachable | no contact damage before the first frame |
| Every actor on a walkable cell the spawn reaches with the Sentinel-locked doors shut | those doors open only once every actor is dead, so an actor behind one, or inside a wall, could never be engaged and the route would deadlock |
| Exit reachable from the spawn with doors open | the level can be finished |
| Declared drops are ones the level's actors leave; a keycard door has a card an actor drops on the player's side of every keycard door | the route clears every actor and takes every drop before it walks to the exit, so an unreachable card would deadlock it |
| One to six actors of known kinds, one to six doors, at most sixteen fixtures | actor slots, the wall key and the world OBJ budget are fixed engine limits; the renderer admits four actors per frame, so at most four share a sightline |

## Readability (v2 only)

| Measure | Default limit | Definition |
|---|---|---|
| `unreachable_cells` | must be 0 | walkable cells not connected to the spawn with doors open |
| `minimum_door_separation` | ≥ 4 | for each door, walkable cells cut off when that door is treated as a wall (the smallest such count) |
| `critical_path_steps` | ≥ 12 | shortest walk from the spawn to the first entity's cell |
| `critical_path_turns` | ≥ 2 | fewest direction changes among all shortest paths |
| `maximum_sightline` | ≤ 6 | longest straight walkable run in either axis |
| `maximum_open_rectangle` | no 5×4 or 4×5 open window | rooms must fit the 4×4 envelope the renderer keeps legible; long 1..3-wide corridors are fine |
| `material_singleton_runs` | ≤ 16 | one-cell paint islands on exposed faces, which read as noise |
| `material_seams`, `physical_segments`, `walkable_cells` | reported | not gated |

A level tightens a limit with its `readability` block; it cannot loosen the
room envelope or the reachability rule, and there is no override for a
failing measure. When a level is refused, the message names the measure and
the values (`readability: sightline is too long (8 > 6)`).

## What the certificate does not cover

- **Playability by the route.** `tools/playthrough.py` plays every sector with
  controller input only. A level that certifies but that the route cannot
  clear (an actor the route cannot engage, a door it cannot reach) fails the
  slow CI lane, which is the intended second gate.
- **Frame budget.** The certificate bounds sightlines and rooms, which bounds
  wall-heavy views, but the measured cost of a level's views is a matter for
  `make sustained` and the snapshot suites.
- **Art.** Fixture placement is checked for geometry (an exposed interior
  face), not for how it reads on screen; use `make preview` and the goldens.
