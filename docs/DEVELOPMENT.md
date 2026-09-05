# Development and releases

Lupine 3D v0.8 builds a deterministic Game Boy Color ROM from Python. Work directly on the existing `main` checkout; do not create development branches or worktrees. Temporary clean-room source copies are allowed. Hardware is unavailable, so qualification uses the project harness and pinned independent cores.

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

| Profile | World / HUD | Default art |
|---|---|---|
| `slim` | 160×120 / 160×24 | Sable animated |
| `compact` | 160×112 / 160×32 | Sable animated |
| `legacy` | 160×96 / 160×48 | Historical static |

```sh
LUPINE3D_DISPLAY=legacy make build
make build  # Restore the default after the comparison.
```

Flags are read at import time. Use a fresh process and matching flags for the ROM and validator. `LUPINE3D_ART` and `LUPINE3D_ART_ANIMATION` select art and animation; explicit incompatible combinations fail. Other rendering experiments remain disabled unless their documented gates pass. See [the experiment ledger](RENDERING_IMPLEMENTATION.md).

## Pinned independent cores

Both adapters need a C compiler. SameBoy also needs its `cppp` preprocessor available on PATH for generated public headers. The pinned sources are external, not vendored.

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
```

mGBA's adapter consumes `flags.make` to match the library ABI, hence the explicit Makefiles generator. SameBoy uses an original synthetic bootstrap; mGBA uses skip-BIOS. Only SameBoy instruments GDMA/page-flip writes. Neither proves physical CGB or Nintendo boot-ROM behaviour.

## Content and diagnostics

Author gameplay in `levels/living_world.json`; use `LUPINE3D_LEVEL` for a different level. The compiler validates spawn clearance, reachability, door gates, surface faces, sightlines and room sizes. `levels/two_sentinels.json` is the bounded multi-actor scene; `levels/renderer_benchmark.json` is the research corpus.

`tools/playtest.py` injects explicit diagnostic poses and validates the generated ROM, descriptors, complete map/attribute packets and published VRAM/OAM. Packet sizes are 480 bytes in slim, 448 compact and 384 legacy. The active nine-image oracle is `sable_objective_spaced_capture_pixels.json`; retain earlier oracles as historical evidence.

```sh
make playthrough variants wall-reuse motion
python tools/playthrough.py --restart
python tools/check_sable.py --output-dir build/v08/art-checks
python tools/check_display.py --output-dir build/v08/display
make preview
python tools/preview_sable.py --scene combat --output-dir build/v08/motion-preview
```

Controller completion uses no game-RAM writes, but reads live state to steer; it is functional verification, not blind human navigation. Variants cover two actors, folded/unfolded, wall reuse, prepared rays and reprojection diagnostics. Wall-reuse testing includes 53 frozen comparisons. Current capture previews are emulator output; generated masters are design references only.

## Measurement

```sh
make sustained
python tools/sable_sustained.py --workers 4 --output-dir build/v08/sustained
make research-v3 research-tail
make atlas-check
```

The first two commands are alternative ways to run the eight 60-second scenarios. The worker version parallelizes independent host emulators; only emulated CPU T-cycles count. After diagnostic setup, sustained scenarios use LCD-indexed controller input with no game-RAM writes and assert movement/turning in each window. CPU speed is 8,388,608 T-cycles/s; an LCD interval remains 70,224 PPU dots or 140,448 double-speed CPU cycles.

Engine, simulation, interrupts, waits and DMA form a mutually exclusive time partition. Nested casting phases must not be summed into that total. Full geometry, cached and foreground publications are distinct. Same-snapshot image comparisons are separate from live replay timing.

`make atlas-check` verifies the preserved atlas in its original legacy training domain, including source hashes and exact patterns. Current translated keys are separately verified by `check_sable.py`; never retrain an atlas as an incidental release step. Current geometry studies write to `build/` and retain historical `research/results` untouched.

The original B/P quality gate remains `Q <= (B + P) / 2` for mean and p95. v0.8's visual tradeoff was explicitly accepted despite failure of that criterion. Record the failure; do not change thresholds or generalize that exception to unrelated kernels.

## Releasing

Update `VERSION`, release notes and current documentation. Use the exact tag `v` plus `VERSION` (v0.8 for this release). Run the complete CI sequence and release-specific art/display, geometry, atlas, independent-witness and sustained checks. Regenerate previews from the candidate ROM. All reports must match its SHA and configuration.

```sh
python tools/run_tests.py > build/v08/tests.log 2>&1
python tools/release_check.py
python tools/qualify_sable_release.py --inputs build/v08 --tests build/v08/tests.log
python tools/package_release.py --output-dir dist --reuse-verified-working-tree
```

Run the art/display checks into `build/v08/art-checks` and `build/v08/display`, sustained scenarios into `build/v08/sustained`, and the budget into `build/v08/quality-budget.json` before assembling evidence. A failed budget returns exit status 1; retain that report and the explicit visual acceptance. Do not suppress failures from the safety/emulator checks.

Archive the resulting `build/rendering_qualification/` under `milestones/v<VERSION>/qualification/`. Release CI reruns short gates and clean-room tests, and may reuse that sustained/core evidence only after verifying the exact ROM/version and every evidence hash. Compressed motion JSON retains all raw samples; its uncompressed hash binds the budget. A changed ROM requires fresh qualification.

After manually running the same gates, `--reuse-verified-working-tree` can reuse current reports. The packager still stages allow-listed sources, rebuilds, writes a deterministic archive, extracts it, rebuilds again and executes the full test suite. It emits the ROM, complete source/evidence ZIP, previews, reports and checksums. Keep ROMs and archives out of Git.

Commit on `main`, push, and tag the reviewed commit. The release workflow validates the tag/version and packages it. Never replace an existing release's assets silently. Describe releases as emulator-qualified, with hardware and original-boot-ROM flags false. The [physical checklist](HARDWARE_TEST_CHECKLIST.md) is retained for possible future access.

The static geometry report compares the historical >20% mean-error improvement gate over the common central 96-pixel window. It also reports the complete current viewport separately, including newly exposed clipped edges. Both references use the appropriate horizon; neither the threshold nor the archived research is changed.
