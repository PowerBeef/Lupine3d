# Performance

The Game Boy Color's CPU runs at 8,388,608 T-cycles a second in double speed,
and a full geometry update (recasting and recomposing the whole world view)
is most of a frame's work. This page says what an update costs, where the
cycles go, and what a game's content changes about it. Every number is
emulated T-cycles in the harness over LCD-indexed controller replays, never
host time.

## What the showcase measures

Sixty-second replays of the showcase's first level on the default slim ROM
(textured walls, overlapped publication), every frame checked
([evidence](../evidence/PERFORMANCE_PHASE5.md)):

| Scenario | Full updates/s | Mean update |
|---|---:|---:|
| walking | 7.45 | 1,124k T |
| turning | 9.89 | 848k T |
| walking and turning | 9.58 | 874k T |
| moving and firing | 9.55 | 876k T |
| facing an open door | 8.08 | 1,026k T |
| facing a closed door | 7.23 | 1,151k T |
| two actors at a corner | 7.12 | 1,178k T |

Sprite and HUD presentations between full updates run at the display's
rate; the numbers above are full geometry only. The project's target of ten
sustained full updates a second is not met in any scenario: textured walls
cost more per update than the flat walls they replaced, and the owner chose
them for the picture.

## Where an update goes

A call-tree profile of the textured build (inclusive T per update, before the
last round of savings):

| | walking | turning | two actors |
|---|---:|---:|---:|
| the whole update | 1,235k | 954k | 1,680k |
| ray casts | 485k | 317k | 848k |
| of which door panels | 182k | 25k | - |
| the texture kernel | 234k | | |
| simulation ticks | 67k | 38k | 173k |

Casting is the largest part and grows with how far rays travel and how many
door panels they test; the texture kernel is next. Since then, overlapped
publication hands the VBlank tail to the interrupt, so an update no longer
waits for the display: it is bound by its own work.
[Textured walls](textured-walls.md), "Cost", and the
[evidence](../evidence/PERFORMANCE_PHASE5.md) break it down by routine.

## What content changes

- **Long views cost more than close walls.** A ray's cost grows with the
  cells it crosses and the door panels it tests; the two-actor arena, where
  every ray crosses about fourteen cells, is the heaviest measured scene.
  The certificate's six-cell sightline keeps a level's views bounded.
- **Doors in view cost casts.** Every ray that meets a door cell tests its
  panel: the walking replay starts facing a door, and its panels are 182k of
  its 485k T of casting.
- **Enemies on screen cost projection and masking.** The OBJ budget admits
  four at once; two at a corner is the heaviest measured scenario.
- **Doors in motion force full updates.** A still view reuses the published
  wall page exactly; a moving door or a turning player cannot.
- **Textures, themes, songs and screens cost ROM, not frame time.** A texture
  is 20 KiB whether it is drawn or not.

## Measuring your game

```sh
python tools/lupine.py run --game games/my_game --snapshot-mode none
```

records every update's T-cycles in the run's `report.json`, so the tour
doubles as a benchmark: pose it where your levels are heaviest.
`python tools/lupine.py profile` breaks the showcase's tour down by
main-loop stage; `tools/benchmark_motion.py` and `tools/sable_sustained.py`
are the timed controller replays behind the table above. Compare like with
like: the same replay, the same ROM configuration, and full updates separate
from cached presentations.
