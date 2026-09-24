# Add a check

Two kinds of check keep the engine honest, and they are never confused:

- **Hard gates** state an invariant: model equality, publication safety, the
  bank contract, the memory reserves, A/B equality between configurations,
  agreement between cores. A hard gate is a test or a tool that fails.
- **Golden snapshots** state what a frame looked like when a person approved
  it. A snapshot changes by acceptance, with a note; a hard gate never does.

A check is never weakened to pass. The archived hash oracles
(`games/sable_outpost/playtests/archive/oracles/`) show what that policy
replaced.

## A hard gate

Put it in `tests/`. `tools/run_tests.py` runs the historical suites under
explicit legacy settings (`LUPINE3D_DISPLAY=legacy LUPINE3D_ART=legacy
LUPINE3D_ART_ANIMATION=0`), because the engine reads its flags once at
import; a test that needs the production configuration spawns a fresh
process with the flags it wants, as `tests/test_textured_walls.py` does. A
test that needs a game other than the showcase loads it with
`game.load_game(path)` (pure, no build) or builds it in a subprocess with
`LUPINE3D_GAME` set.

For a focused run:

```sh
LUPINE3D_DISPLAY=legacy LUPINE3D_ART=legacy LUPINE3D_ART_ANIMATION=0 \
  .venv/bin/python -m unittest discover -s tests -p 'test_game_loader.py' -v
```

Checks that need a built ROM and a qualification report go in
`tools/check_sable.py` (the showcase's art and publication windows) or
`tools/release_check.py` (the release report). A check of every CI lane
belongs in `tools/ci_lanes.py`, which the workflow, the local runner and the
release packager share (`tests/test_ci_lanes.py` holds them together).

## A golden scene

Add a capture to a scenario that names a snapshot suite
([scenario format](../reference/scenario-format.md)), run it in record mode,
look at it, and accept it with a note:

```sh
python tools/lupine.py run --snapshot-mode record
python tools/lupine.py snapshot accept --suite tour --scene 10_new_view --note "why this view"
```

Commit the PNG and the manifest with the change, so the pull request shows
the picture.

## A limit

A new content limit goes in `tools/lupine3d_v4/limits.py` with the engine
fact that sets it; the loader or compiler enforces it through `refuse`,
`tests/test_game_loader.py` pins the message, `docs/reference/limits.md`
states it, and `tools/make_limits_game.py` must still build a game at every
maximum at once.
