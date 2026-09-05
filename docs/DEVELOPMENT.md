# Development and playtesting

See [implementation status](OVERHAUL_IMPLEMENTATION.md) for rendering contracts and [Sable Outpost](SABLE_OUTPOST.md) for current art, wall fixtures and HUD allocation.

All project development takes place directly on `main`, without development
branches or Git worktrees. Temporary copies used for baseline comparisons and
clean-room packaging remain part of the verification workflow.

The owner has no physical Game Boy Color or flash cartridge. Validation uses
the project harness and pinned SameBoy CGB-0/E and mGBA cores. Physical testing
is unavailable and does not block development or emulator-qualified releases.

## Build and verify

```sh
python3 tools/dev_setup.py
make test
make playtest playtest-world playtest-art
make playthrough variants
make wall-reuse motion
make research-tail
python3 tools/release_check.py
```

Requirements: Python 3.10+, Pillow and make. `tools/dev_setup.py --offline` can use an already installed Pillow. The generated environment is local and excluded from releases.

The default ROM is `build/lupine3d.gb`. The builder also writes symbols, a listing and memory/configuration metadata. `make preview` regenerates real emulator captures, not illustrative mockups.

## Independent cores

Pin SameBoy to `213a12ce93d66b105a113debd9396306066a7cfc`:

```sh
git clone https://github.com/LIJI32/SameBoy.git /your/path/SameBoy
git -C /your/path/SameBoy checkout 213a12ce93d66b105a113debd9396306066a7cfc
make -C /your/path/SameBoy lib -j2 CONF=release DISABLE_DEBUGGER=1 DISABLE_CHEATS=1 DISABLE_REWIND=1
make sameboy SAMEBOY_DIR=/your/path/SameBoy
```

Pin mGBA to `507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6`:

```sh
git clone https://github.com/mgba-emu/mgba.git /your/path/mgba
git -C /your/path/mgba checkout 507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6
cmake -S /your/path/mgba -B /your/path/mgba/build \
  -DLIBMGBA_ONLY=ON -DBUILD_STATIC=ON -DBUILD_SHARED=OFF \
  -DBUILD_QT=OFF -DBUILD_SDL=OFF -DUSE_FFMPEG=OFF -DUSE_LIBZIP=OFF \
  -DUSE_SQLITE3=OFF -DUSE_LZMA=OFF -DUSE_PNG=OFF -DUSE_ELF=OFF \
  -DUSE_EDITLINE=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build /your/path/mgba/build -j2
make mgba MGBA_DIR=/your/path/mgba
```

Adapters require a C compiler. The mGBA adapter consumes the exact library build defines from `flags.make` because public struct layout is conditional. These cores are external, not vendored. Both lanes bind reports and screenshots to the exact ROM SHA and reject mismatched source/configuration.

SameBoy uses an original synthetic bootstrap; mGBA uses built-in skip-BIOS. Only SameBoy's adapter instruments GDMA writes/page flips. Neither constitutes physical CGB or Nintendo boot-ROM certification.

## Content

The active level is `levels/living_world.json`. Select another at build time with `LUPINE3D_LEVEL`. The compiler supports one to four Sentinel spawns and optional per-face records:

```json
{"surfaces": [{"x": 2, "y": 3, "side": "east", "profile": "machinery"}]}
```

Profiles: `structure`, `machinery`, `door`. Door colour is reserved for actual doors. These records affect palette selection, not collision or physical segment continuity. Faces are west/east/north/south. Existing spawn, reachability, door-cut, sightline and room-size validation remains active.

`levels/two_sentinels.json` is a bounded multi-actor acceptance scene, not the default difficulty.

## Pose diagnostics versus controller completion

`tools/playtest.py` drives the actual generated ROM. Each update ends at a completed presentation, which may retain its BG page. Every update validates pair/physical descriptors, depth/segments/profiles, exact tile bytes, all 384 tile-map and attribute bytes, cast/event counts, capacity, input overflow, actual published VRAM/OAM bank ownership and GDMA safety. Reports distinguish executed casts and BG flips from cached descriptor counts and sprite/HUD presentations.

```json
{
  "name": "example",
  "world_mode": "living",
  "actions": [
    {"pose": [2176, 2176, 0], "updates": 2, "capture": "encounter"},
    {"aim_at_sentinel": true, "buttons": ["a"], "updates": 2,
     "capture": "hit", "expect": {"sentinel_health": 2}}
  ]
}
```

Buttons: directions, A, B, Select, Start. Optional `pose` sets Q8 coordinates/angle; `aim_at_sentinel` adjusts only camera aim; `pose_at_drop` relocates only the camera to the defeated actor's actual drop. These are explicit diagnostic injections. Expectations apply at an action's final update because queued input affects the next snapshot, not the frame already rendering.

The coherence tour freezes nine reviewed raw-RGB hashes in `v070_sable_capture_pixels.json`. The combat diagnostic has state assertions but no frozen gameplay RGB oracle. Older fixtures remain historical.

`make playthrough` is separate: no teleporting or game-RAM writes. Its bot reads live state and generates controller input until combat, pickup and exit complete. It is functional verification, not a blind human readability test.

## Experiments and performance

`make variants` builds variants in memory without overwriting the playable ROM:

- two-Sentinel render/admission scene;
- folded versus unfolded rendering with frozen simulation, nine RGB matches;
- wall reuse enabled versus disabled, nine RGB matches;
- prepared ray records versus arithmetic setup, nine RGB matches;
- reprojection clamp, immutable published world X, fixed UI and map/attribute guards.

Default configuration is folding on, Q14 order on, fixed simulation on, wall reuse on, prepared rays on, full atlas and reprojection off. The accepted rendering additions enable compact strips, camera setup hoisting, narrow yield contexts and exact attribute padding. Other new kernels remain disabled. Research flags include `LUPINE3D_PREPARED_RAYS=0`, `LUPINE3D_FOLDED=0`, `LUPINE3D_WALL_REUSE=0`, `LUPINE3D_COMPACT_ATLAS=1` and `LUPINE3D_REPROJECTION=1`. These historical diagnostics adapt implicit defaults; explicit incompatible requests are rejected. Always use matching flags for the ROM and host validator. See the complete [rendering implementation ledger](RENDERING_IMPLEMENTATION.md).

`make wall-reuse` runs 53 frozen cached/full comparisons and LCD-timed idle, combat and turning trials. It needs no old ROM; optional archived-ROM arguments add a historical lane. See [wall reuse](WALL_REUSE.md) for key addresses, publication counts, latency definitions and the 1.31% fresh-render overhead.

`make motion` drives walking, turning, combined movement and a one-frame door tap for 144 LCD-frame-counter increments each. After diagnostic warmup it makes no game-RAM writes. Every presentation validates exact wall invalidation, descriptors, published packets and hardware budgets. Optional baseline ROM/symbol arguments enable A/B measurements; see [streaming performance](COLUMN_PERFORMANCE.md).

`make sustained` runs 60 emulated seconds per scenario with the same LCD-indexed
controller tape on both ROMs. It covers moving fire, open/closed doors and a
two-actor corner arena as well. Every five-second movement window must contain
real translation/turning. The arena uses setup-only diagnostic geometry; its
controller backs around pursuing actors and must put both into one admission
frame. `python tools/playthrough.py --restart` separately completes and restarts
the authored level with no game-RAM injection. `--rom`/`--symbols` select an
external ROM; reports preserve the actual controller replay hash.

Motion v2 reports use CPU T-cycles and partition engine, simulation, interrupts,
publication waits and DMA exactly. Nested casting scopes must not be summed
into that total. Full geometry, cached, refinement and foreground publications
are separate. Muzzle latency uses the first opaque row's estimated scanline
start, excluding variable mode-3 pixel timing. `tools/evaluate_quality_budget.py`
applies the mean/p95 half-gains rule; a partial gate can reject a candidate but
cannot qualify it for production. Immutable comparison artifacts belong in
`.render-baselines/`, outside generated build output.

`tools/quality_witnesses.py` recreates 51 complete-world witnesses using an
independent rational plane oracle. `tools/independent_witnesses.py` runs the same
frozen scenes on the pinned CGB-0, CGB-E and mGBA adapters; diagnostic writes are
explicitly labelled. Keep the historical nine-image oracle unchanged for exact
paths. Quality before/after stills and slow-motion pose sequences are a separate
versioned review, generated by `tools/quality_motion_review.py`.

`python3 tools/profile_rendering.py --output build/profile-beta.json` measures generated-code stages. Cooperative simulation yields receive a separate category; interrupt costs remain charged to the active category. Use the complete playtest reports for frame-rate claims.

`make research-tail` runs the full current host geometry scan on the retained benchmark map and writes `build/q14_tail.*`; it does not overwrite historical tail evidence. Other `research-*` targets retain the original atlas/geometry laboratories. Treat their versioned reports as archived unless freshly regenerated under a stated configuration.

`make research-v3` writes a fresh static-cell comparison to `build/static_geometry/`.
Both the current model and floating oracle use the same solid-cell geometry;
finite-door centre planes are covered by the dedicated door and frozen-world
tests. Release packaging retains historical research files and applies the
existing mean-error, segment-error and overflow gates to this fresh comparison.

`make atlas-check` validates both committed atlas profiles against their training
hashes, complete bucket directories and exact compositor bytes, then measures
each selected profile. Releases package these qualified inputs. The current
reference corpus differs from the historical training corpus, so running
`make research-atlas-all` retrains and changes the asset/ROM hashes; it is an
explicit research operation that requires fresh qualification. Its diagnostic route
writes camera state into both live and snapshot banks, disables wall reuse for
the measurement process, and validates complete presentations. Atlas-route v2
therefore measures full composition; use the motion tools for live cache and
controller throughput. Failed candidate subprocesses retain their diagnostic
error output.

## Packaging

`python3 tools/package_release.py --output-dir dist` runs gates, stages an allow-listed source tree, rebuilds, writes a deterministic ZIP, extracts into another clean directory, reruns all tests and compares ROM bytes.

After manually running the same gates, `--reuse-verified-working-tree` reuses current evidence but still performs clean-room rebuild/extraction/tests. Release checks reject playtest or available independent-emulator reports for a different ROM SHA. A test inventory alone is not test execution; the packager actually runs the suite.

Label releases as emulator-qualified and retain `physical_hardware_tested: false`.
The [physical checklist](HARDWARE_TEST_CHECKLIST.md) is optional future work if
hardware becomes available; it is not a current release requirement.
