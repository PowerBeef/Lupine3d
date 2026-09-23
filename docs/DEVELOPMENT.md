# Development and releases

Lupine 3D builds a deterministic Game Boy Color ROM from Python (`VERSION` names the release). Work directly on the existing `main` checkout; do not create development branches or worktrees. Temporary clean-room source copies are allowed. Hardware is unavailable, so qualification uses the project harness and pinned independent cores.

## Setup and everyday work

```sh
python3 tools/dev_setup.py
source .venv/bin/activate
make build test
make playtest playtest-world playtest-art
```

Python 3.10+, Pillow and Make are required; CI uses Python 3.12. Setup creates `.venv` but does not activate it. Alternatively, pass `PYTHON=.venv/bin/python` to Make. RGBDS is not needed. `build/local-env.sh`, if present, is only an ignored local convenience.

Outputs are `build/lupine3d.gb`, `.sym`, `.lst` and `build/build_manifest.json`. The manifest records configuration, source hashes, table formats, memory allocation and publication limits. `make clean` deletes all of `build/`, including locally downloaded cores; comparison archives belong in `.render-baselines/`.

`make test` runs the historical engine suite under explicit legacy settings and production art/display checks in fresh processes. Do not run historical image/arithmetic tests under the slim default by accident.

`python tools/lupine.py` is one entry point for the everyday commands, each run in a fresh process with the right flags: `build [--sync] [--display …]`, `run [--scenario …]`, `snapshot …`, `level check|info|export-tmx|import-tmx`, `profile`, `test`, `witnesses`, `ci`, `release-check`, `sable-check` and `symbols`. `make lupine ARGS="…"` is the same through Make. The [developer guide](guide/README.md) is the reading order for someone new to the engine; `make docs-check` verifies every documentation link and command and that the generated [memory map](guide/MEMORY_MAP.md) matches the build (`make memory-map` regenerates it).

| Profile | World / HUD | Default art |
|---|---|---|
| `slim` | 160×120 / 160×24 | Sable animated |
| `compact` | 160×112 / 160×32 | Sable animated |
| `legacy` | 160×96 / 160×48 | Historical static |

```sh
LUPINE3D_DISPLAY=legacy make build
make build  # Restore the default after the comparison.
```

Flags are read at import time. Use a fresh process and matching flags for the ROM and validator. `LUPINE3D_ART` and `LUPINE3D_ART_ANIMATION` select art and animation; explicit incompatible combinations fail. Other rendering experiments remain disabled unless their documented gates pass. See [the experiment ledger](archive/RENDERING_IMPLEMENTATION.md).

### Debugger exports

Every build writes `build/lupine3d.sym` in the bank-prefixed `BB:AAAA name`
form that RGBDS emits and BGB, Emulicious and SameBoy's debugger load: every
code and data label, and every named RAM variable of the layout with its
WRAM bank, under a comment naming the ROM's SHA-256. `build/lupine3d.map`
lists the assembler's sections with sizes and kinds and then the allocation
ledger. `build_manifest.json` records both files' hashes under `exports`.
The host tools read either form (`sm83emu.parse_symbols`).

## Pinned independent cores

Both adapters need a C compiler. SameBoy's `cppp` preprocessor is needed only for its generated public headers, which the `lib` target below does not build and the adapter does not use — it includes `Core/gb.h` from the core tree. The pinned sources are external, not vendored.

```sh
git clone https://github.com/LIJI32/SameBoy.git /your/path/SameBoy
git -C /your/path/SameBoy checkout 213a12ce93d66b105a113debd9396306066a7cfc
make -C /your/path/SameBoy lib -j2 CONF=release DISABLE_DEBUGGER=1 DISABLE_CHEATS=1 DISABLE_REWIND=1
make sameboy SAMEBOY_DIR=/your/path/SameBoy

git clone https://github.com/mgba-emu/mgba.git /your/path/mgba
git -C /your/path/mgba checkout 507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6
cmake -G "Unix Makefiles" -S /your/path/mgba -B /your/path/mgba/build \
  -DLIBMGBA_ONLY=ON -DBUILD_STATIC=ON -DBUILD_SHARED=OFF \
  -DBUILD_QT=OFF -DBUILD_SDL=OFF -DUSE_FFMPEG=OFF -DUSE_LIBZIP=OFF \
  -DUSE_SQLITE3=OFF -DUSE_LZMA=OFF -DUSE_PNG=OFF -DUSE_ELF=OFF \
  -DUSE_EDITLINE=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build /your/path/mgba/build -j2
make mgba MGBA_DIR=/your/path/mgba
python tools/independent_witnesses.py
make conformance SAMEBOY_DIR=/your/path/SameBoy   # harness CPU model vs SameBoy, every emitted instruction form
```

Both adapters press START before anything else: the campaign holds the world behind a title screen, and an adapter that does not reach `MODE_PLAYING` exits 3 rather than reporting a pass. mGBA's adapter consumes `flags.make` to match the library ABI, hence the explicit Makefiles generator. SameBoy uses an original synthetic bootstrap; mGBA uses skip-BIOS. Only SameBoy instruments GDMA/page-flip writes. Neither proves physical CGB or Nintendo boot-ROM behaviour.

### Power-on RAM in the core adapters

SameBoy randomises power-on RAM from a time seed. Both adapters therefore
treat world entry as an event, not a value: SameBoy's waits for the ROM's
own write of `MODE_PLAYING` through its memory hook, mGBA's for the title to
be seen before the mode reads playing. Before this rule a random image that
happened to hold the playing value at `GAME_MODE` made an adapter release
START on the title screen and time out (about one run in 150). For
reproduction, `LUPINE3D_SAMEBOY_SEED=<n>` fixes the seed and
`LUPINE3D_DUMP_RAM=<path>` writes the power-on image (WRAM, HRAM, VRAM,
OAM) that the host harness can replay; every adapter failure reports its seed.

## Content and diagnostics

Author gameplay in the eighteen campaign levels `levels.py:CAMPAIGN_ORDER` names (sector 1 is `levels/living_world.json`; [campaign](CAMPAIGN.md)); use `LUPINE3D_LEVEL` for a different level. The compiler validates spawn clearance, reachability, door gates, surface faces, sightlines and room sizes. `levels/two_sentinels.json` is the bounded multi-actor scene; `levels/renderer_benchmark.json` is the research corpus.

`tools/playtest.py` injects explicit diagnostic poses and validates the generated ROM, descriptors, complete map/attribute packets and published VRAM/OAM. Packet sizes are 480 bytes in slim, 448 compact and 384 legacy. Its captures are checked against the golden snapshots under `snapshots/` (suites `tour`, `world`, `art`); a changed frame fails naming the scene and writes `build/snapshots/<profile>/<suite>/report.html` for review. Accept a deliberate change with a note:

```sh
python tools/snapshot.py diff --suite tour
python tools/snapshot.py accept --suite tour --scene 09_exit_approach --note "why the frame changed"
```

See [Verification](VERIFICATION.md) for what is a hard gate and what is a snapshot. The retired hash oracles are archived under `playtests/archive/oracles/`.

```sh
make playthrough variants wall-reuse motion
python tools/playthrough.py --restart
python tools/playthrough.py --sectors 3-3 --output-dir build/playthrough_s3  # one sector, entered by its continue code
python tools/check_sable.py --output-dir build/v011/art-checks
python tools/check_display.py --output-dir build/v011/display
make preview
python tools/preview_sable.py --scene combat --output-dir build/v011/motion-preview
```

Controller completion uses no game-RAM writes, but reads live state to steer; it is functional verification, not blind human navigation. Variants cover two actors, folded/unfolded, wall reuse, prepared rays and reprojection diagnostics. Wall-reuse testing includes 53 frozen comparisons. Current capture previews are emulator output; generated masters are design references only.

### Textured walls

The engine and its showcase are textured: every slim Sable build composes its
walls with the row-window kernel of `docs/TEXTURED_WALLS.md`, and its goldens
live under `snapshots/slim-sable-v2-textured/`. The flat slim profile was
removed; the flat microstrip compositor is kept only as the renderer of the
historical legacy and compact profiles, whose research lanes (the unfolded
oracle, physical depth, anchor packets) run there. `tests/test_textured_walls.py`
runs the Sable checks in a fresh process.

The slim build also publishes each frame's tail from the VBlank interrupt
(overlapped publication, `docs/PERFORMANCE_PHASE5.md`).
`LUPINE3D_OVERLAP_PUBLICATION=0` builds the synchronous tail:

```sh
make sync                  # build/sync/lupine3d.gb, .sym, manifest
make playtest-sync         # the coherence tour's frame checks and a motion replay
```

### Before you push

Work lands on `main`, and every push to `main` runs CI to completion (a newer
push supersedes a running CI only on a pull request), so verify a batch
locally and push it once:

```sh
python tools/ci_local.py --changed   # the lanes this change needs
python tools/ci_local.py             # every CI lane
python tools/ci_local.py --list      # the lanes and their commands
```

`tools/ci_lanes.py` is the one definition of CI's lanes: the `fast`,
`profiles` and `slow` jobs command for command, and the controller route in
chunks sized by measured route updates, one CI runner each (the first from
the title, the rest from their continue codes, the last restarting the
campaign). `tools/ci_local.py` runs every lane in its own copy of the working
tree, one per CPU by default, longest first; it drops the caller's
`LUPINE3D_*` flags, needs the pinned cores under `build/deps` for the slow
lane (a missing core is reported, never passed), checks that every lane
built the same ROM, and copies the route reports back into `build/` for
`tools/release_check.py`. A change to documentation alone runs only
`make docs-check` under `--changed`. `tests/test_ci_lanes.py` holds the
workflow's matrix and commands to the table.

## Measurement

```sh
make sustained
python tools/sable_sustained.py --workers 4 --output-dir build/v011/sustained
make research-v3 research-tail
make atlas-check
```

The first two commands are alternative ways to run the eight 60-second scenarios. The worker version parallelizes independent host emulators; only emulated CPU T-cycles count. After diagnostic setup, sustained scenarios use LCD-indexed controller input with no game-RAM writes and assert movement/turning in each window. CPU speed is 8,388,608 T-cycles/s; an LCD interval remains 70,224 PPU dots or 140,448 double-speed CPU cycles.

Engine, simulation, interrupts, waits and DMA form a mutually exclusive time partition. Nested casting phases must not be summed into that total. Full geometry, cached and foreground publications are distinct. Same-snapshot image comparisons are separate from live replay timing.

`make atlas-check` verifies the preserved atlas in its original legacy training domain, including source hashes and exact patterns. Current translated keys are separately verified by `check_sable.py`; never retrain an atlas as an incidental release step. Current geometry studies write to `build/` and retain historical `research/results` untouched.

The original B/P quality gate remains `Q <= (B + P) / 2` for mean and p95. v0.8's visual tradeoff was explicitly accepted despite failure of that criterion, and later releases inherit it unchanged. Record the failure; do not change thresholds or generalize that exception to unrelated kernels.

## Releasing

Update `VERSION`, release notes and current documentation. Use the exact tag `v` plus `VERSION` (v0.11 for this release). Evidence directories follow `VERSION` too, so `build/v011` here and `build/v012` next time; the tooling derives them rather than pinning one. Run the complete CI sequence and release-specific art/display, geometry, atlas, independent-witness and sustained checks. Regenerate previews from the candidate ROM. All reports must match its SHA and configuration.

```sh
python tools/run_tests.py > build/v011/tests.log 2>&1
python tools/release_check.py
python tools/qualify_sable_release.py --inputs build/v011 --tests build/v011/tests.log
python tools/package_release.py --output-dir dist --reuse-verified-working-tree
```

Run the art/display checks into `build/v011/art-checks` and `build/v011/display`, sustained scenarios into `build/v011/sustained`, and the budget into `build/v011/quality-budget.json` before assembling evidence. A failed budget returns exit status 1; retain that report and the explicit visual acceptance. Do not suppress failures from the safety/emulator checks.

Archive the resulting `build/rendering_qualification/` under `milestones/v<VERSION>/qualification/`. Release CI reruns short gates and clean-room tests, and may reuse that sustained/core evidence only after verifying the exact ROM/version and every evidence hash. Compressed motion JSON retains all raw samples; its uncompressed hash binds the budget. A changed ROM requires fresh qualification.

After manually running the same gates, `--reuse-verified-working-tree` can reuse current reports. The packager still stages allow-listed sources, rebuilds, writes a deterministic archive, extracts it, rebuilds again and executes the full test suite. It emits the ROM, complete source/evidence ZIP, previews, reports and checksums. Keep ROMs and archives out of Git.

Commit on `main`, push, and tag the reviewed commit. The release workflow validates the tag/version and packages it. Never replace an existing release's assets silently. Describe releases as emulator-qualified, with hardware and original-boot-ROM flags false. The [physical checklist](HARDWARE_TEST_CHECKLIST.md) is retained for possible future access.

The static geometry report compares the historical >20% mean-error improvement gate over the common central 96-pixel window. It also reports the complete current viewport separately, including newly exposed clipped edges. Both references use the appropriate horizon; neither the threshold nor the archived research is changed.
