# Command line

`python tools/lupine.py` is the one entry point for making, building, running
and verifying a game. Each command runs the tool that owns the work in a
fresh process with the build flags set from its options, because the engine
reads every flag once, when it is imported ([build flags](build-flags.md)).
`make` targets do the same work; both are listed.

Every command that builds or runs a game takes **`--game DIR`**: a game
directory, or a name under `games/` (`--game starter`). Without it the
command uses `LUPINE3D_GAME`, and without that the showcase,
`games/sable_outpost`. The showcase builds into `build/`; any other game into
`build/games/<id>/`. `make … GAME=DIR` selects a game for a `make` target.

Commands that build take **`--display slim|compact|legacy`** (only the
showcase builds the historical `compact` and `legacy` profiles) and
**`--sync`** (the synchronous publication tail, into a `sync/` directory
beside the default build).

### `lupine new-game`

```sh
python tools/lupine.py new-game DIR [--from GAME] [--id ID] [--title TITLE]
```

Copies a game (the starter, `games/starter`, unless `--from` names another)
into `DIR`, which must be new or empty, and gives the copy its own identity:
the id (from the directory's name unless `--id`), the title (from the id
unless `--title`), the cartridge header and version 0, and the `slim`
profile. The source's goldens are not copied: a golden is a picture of one
game. It prints the next commands.

### `lupine game`

```sh
python tools/lupine.py game check [--game GAME]
make game-check GAME=DIR
```

Loads the game's manifest (every file it names, every [limit](limits.md)),
prints what the game uses, and compiles every level, printing each one's
[certificate](level-certificate.md) or the compiler's reason for refusing
it. Exits non-zero if anything is refused. It does not build.

### `lupine build`

```sh
python tools/lupine.py build [--game GAME] [--display …] [--sync] [--output-dir DIR]
make build GAME=DIR
```

Builds the ROM (`lupine3d.gb`), its listing (`.lst`), debugger symbols
(`.sym`) and map (`.map`), and the [build manifest](build-manifest.md), into
the game's build directory unless `--output-dir`. `tools/build_rom.py
--game DIR` does the same.

### `lupine run`

```sh
python tools/lupine.py run [--game GAME] [--role tour|world|art] [--scenario FILE]
                           [--snapshot-mode check|record|none] [--playtest-output DIR]
make playtest GAME=DIR          # the tour; playtest-world and playtest-art the others
```

Plays one of the game's driven playtests on the built ROM with every frame
check ([scenario format](scenario-format.md)): the tour unless `--role` or
`--scenario` says otherwise. `--snapshot-mode check` (the default) fails if a
capture differs from its golden, `record` writes the evidence without
failing, `none` skips the goldens. Build first.

### `lupine snapshot`

```sh
python tools/lupine.py snapshot [--game GAME] run --suite SUITE [--mode check|record]
python tools/lupine.py snapshot [--game GAME] diff --suite SUITE
python tools/lupine.py snapshot [--game GAME] accept --suite SUITE [--scene NAME] --note "why"
python tools/lupine.py snapshot [--game GAME] list
```

Golden-image snapshots (`tools/snapshot.py`). A game's suites are the
playtests it declares (`tour`, `world`, `art`) and the controller `route`;
the showcase also has `sable` and `witnesses`. `run --suite all` runs the
fast ones. `accept` promotes the last run's captures to goldens under
`games/<id>/snapshots/`, recording the note, who, when and the ROM; it
refuses an empty note. Nothing in CI accepts.

### `lupine level`

```sh
python tools/lupine.py level check FILE...              # compile, print each certificate
python tools/lupine.py level info FILE                  # the level at a glance, as JSON
python tools/lupine.py level export-tmx SRC DST [--swatch]
python tools/lupine.py level import-tmx SRC DST
```

Compiles levels against the selected game's names (its kinds, themes and
fixture families), and converts to and from [Tiled](../how-to/use-tiled.md).
`import-tmx` compiles what it writes, so a refused map is reported at once.

### `lupine profile`

```sh
python tools/lupine.py profile [--sync]
```

CPU T-cycles by main-loop stage over the showcase's coherence tour
(`tools/profile_rendering.py`).

### `lupine test`

```sh
python tools/lupine.py test
make test
```

The engine's regression suite (`tools/run_tests.py`), on the showcase.

### `lupine witnesses`

```sh
python tools/lupine.py witnesses [--snapshot-mode …]
```

The showcase's frozen scenes in both pinned emulator cores, against the
host's images and the `witnesses` goldens (`tools/independent_witnesses.py`).
Needs the cores under `build/deps` ([development](../engine/development.md)).

### `lupine release-check`

```sh
python tools/lupine.py release-check
```

The release verification report for the showcase ROM
(`tools/release_check.py`); it unions the evidence the other lanes wrote.

### `lupine sable-check`

```sh
python tools/lupine.py sable-check [--snapshot-mode …]
make sable-check
```

The showcase's emitted-ROM art checks: its HUD pinned pixel by pixel, the
VRAM windows against the compiled sheets, the texture blocks, each episode's
texture set (`tools/check_sable.py`).

### `lupine symbols`

```sh
python tools/lupine.py symbols [--game GAME]
```

Where the build's debugger exports are and how to load them in BGB,
Emulicious or SameBoy ([debug a build](../how-to/debug-a-build.md)).

### `lupine ci`

```sh
python tools/lupine.py ci [--changed] [--lanes fast,starter] [--jobs N] [--list]
make ci-local
```

Runs CI's lanes locally in parallel, each in its own copy of the working
tree (`tools/ci_local.py`); `--changed` runs only the docs check for a
documentation-only change. Everything after `ci` goes to `ci_local.py`.

## `make` targets for games

| Target | Does |
|---|---|
| `make build GAME=DIR` | build the game |
| `make game-check GAME=DIR` | `lupine game check` |
| `make playtest GAME=DIR` | build, then the tour against its goldens |
| `make playthrough GAME=DIR [SECTORS=A-B] [RESTART=1] [ROUTE_DIR=…]` | the controller route: play levels A to B on controller input alone; `RESTART=1` plays the ending and restarts |
| `make sameboy GAME=DIR SAMEBOY_DIR=…` | the game in the pinned SameBoy core |
| `make limits` | build and walk the generated game at every content limit |
| `make scaffold-check` | a new game from the starter, checked, built and toured |
| `make preview GAME=DIR` | a still from the game's `preview` pose and a GIF of its first level, in its build directory (the showcase's still is also the README's hero image) |
