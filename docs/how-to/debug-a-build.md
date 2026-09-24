# Debug a build

A build's outputs are in its build directory: `build/` for the showcase,
`build/games/<id>/` for any other game. Every command below takes
`--game DIR` (or `make … GAME=DIR`).

## Symbols and the map

Every build writes `lupine3d.sym` in the RGBDS `BB:AAAA name` form that BGB,
Emulicious and SameBoy's debugger read, and `lupine3d.map` with the
assembler's sections and the allocation ledger:

```sh
python tools/lupine.py symbols --game games/my_game
```

prints where they are and how to load them. RAM variables are exported with
their WRAM bank, so a watch on `PLAYER_HEALTH` or `GAME_MODE` works by name.
The [memory map](../reference/memory-map.md) says what every address holds.

## The host harness

`tools/sm83emu.py` runs the ROM on the host with exact instruction timing, a
DMA model and per-frame validation. Every driven playtest, the controller
route and the checks use it, so a problem seen in an emulator can usually be
reduced to a harness run:

```sh
python tools/lupine.py run --game games/my_game --snapshot-mode none
python tools/lupine.py run --game games/my_game --scenario my_scenario.json --snapshot-mode none
```

`validate_frame` (`tools/playtest.py`) refuses a frame whose descriptors,
patterns, maps, masks or DMA timing disagree with the host model, and names
the check. A run writes its captures, a contact sheet and `report.json`
under the build directory's `playtest/`. Write a short
[scenario](../reference/scenario-format.md) that poses the player where the
problem shows.

## The controller route

```sh
make playthrough GAME=games/my_game SECTORS=2-2
LUPINE3D_ROUTE_DEBUG=1 make playthrough GAME=games/my_game SECTORS=2-2
```

plays one level from its continue code on controller input alone; the debug
flag traces every combat exchange. When the route stalls or the player dies,
its report names the level, the pose, the actors and the last exchanges.

## Reproducing a core failure

The pinned SameBoy and mGBA adapters (`tools/sameboy_smoke.c`,
`tools/mgba_smoke.c`) drive a short controller script, check publication
safety on every frame and compare the start image with the host's. SameBoy
randomises power-on RAM from the clock, so a failure can depend on the seed:

```sh
LUPINE3D_SAMEBOY_SEED=12345 make sameboy GAME=games/my_game SAMEBOY_DIR=build/deps/SameBoy
LUPINE3D_DUMP_RAM=build/ram.bin make sameboy GAME=games/my_game SAMEBOY_DIR=build/deps/SameBoy
```

The dump can be loaded into the harness to replay the same power-on state
([development](../engine/development.md), "Power-on RAM in the core
adapters").

## Pictures

A visual difference is a golden-image diff:

```sh
python tools/lupine.py snapshot --game games/my_game diff --suite tour
```

writes `report.html` beside the run's evidence under the build directory's
`snapshots/`, with the expected and actual images and the changed pixels in
red. `make preview GAME=DIR` renders a still and a GIF from the ROM.

## When something is refused

[Troubleshooting](troubleshooting.md) lists the loader's, the compiler's and
the build's messages with what each means and how to fix it.
