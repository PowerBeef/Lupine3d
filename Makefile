PYTHON ?= python3

# The game to build and run: a directory with a game.json, or a name under
# games/ (make build GAME=games/starter). The showcase, games/sable_outpost,
# is the default. Every tool reads it as LUPINE3D_GAME; a game other than the
# showcase builds into build/games/<id>/.
ifdef GAME
export LUPINE3D_GAME := $(GAME)
endif

.PHONY: all setup build test docs-check memory-map lupine ci-local identity game-check research research-v3 research-atlas research-atlas-entity research-atlas-all research-atlas-pareto research-tail verify playtest playtest-world playtest-art qa preview package clean

all: build

setup:
	$(PYTHON) tools/dev_setup.py

build:
	$(PYTHON) tools/build_rom.py

test: build
	$(PYTHON) tools/run_tests.py

# Documentation: links, commands and the generated memory map (docs/guide/MEMORY_MAP.md).
docs-check: build
	$(PYTHON) tools/check_docs.py --require-build

memory-map: build
	$(PYTHON) tools/memory_map.py

# Every configuration's ROM against the record taken before the game/engine
# separation (tools/rom_identity.py): a refactor that changes no behaviour
# changes no ROM byte.
IDENTITY_RECORD ?= tests/fixtures/rom_identity_pre_separation.json
identity:
	$(PYTHON) tools/rom_identity.py check $(IDENTITY_RECORD)

# CI's jobs locally, each lane in its own copy of the working tree, in
# parallel (tools/ci_local.py): make ci-local ARGS="--changed"
ci-local:
	$(PYTHON) tools/ci_local.py $(ARGS)

# The selected game's content without a build: its manifest and every level's
# certificate (make game-check GAME=games/starter).
game-check:
	$(PYTHON) tools/lupine.py game check

# The `lupine` CLI: make lupine ARGS="level check games/sable_outpost/levels/*.json"
lupine:
	$(PYTHON) tools/lupine.py $(ARGS)

research:
	$(PYTHON) research/geometry_v2_lab.py

research-v3:
	LUPINE3D_LEVEL=$(CURDIR)/tests/levels/renderer_benchmark.json $(PYTHON) research/rendering_v3_lab.py --output-dir build/static_geometry --accuracy-only

research-atlas:
	$(PYTHON) research/build_tile_atlas_v4.py

research-atlas-entity:
	$(PYTHON) research/build_tile_atlas_v4.py --apply-patterns 80 \
		--output-dir assets/entity_atlas_80 \
		--result-path research/results/tile_atlas_entity_80_v6.json \
		--measure-profile entity-heavy

research-atlas-all: research-atlas research-atlas-entity

.PHONY: atlas-check
atlas-check:
	LUPINE3D_DISPLAY=legacy LUPINE3D_ART=legacy LUPINE3D_ART_ANIMATION=0 $(PYTHON) research/build_tile_atlas_v4.py --verify-assets

research-atlas-pareto:
	$(PYTHON) research/build_tile_atlas_v4.py --pareto

research-tail:
	LUPINE3D_LEVEL=$(CURDIR)/tests/levels/renderer_benchmark.json $(PYTHON) research/tail_failure_lab.py --output-prefix build/q14_tail --angle-step 4

verify: build test research research-v3
	$(PYTHON) tools/release_check.py

playtest:
	$(PYTHON) tools/build_rom.py
	$(PYTHON) tools/playtest.py

playtest-art: build
	$(PYTHON) tools/playtest.py --role art

playtest-world:
	$(PYTHON) tools/build_rom.py
	$(PYTHON) tools/playtest.py --role world

.PHONY: playthrough sameboy mgba variants wall-reuse motion snapshot snapshot-diff snapshot-accept
# The whole campaign by default; SECTORS=A-B plays one range (an episode in
# CI's matrix, one sector to reproduce a failure) into ROUTE_DIR.
ROUTE_DIR ?= build/playthrough
playthrough: build
	$(PYTHON) tools/playthrough.py --output-dir $(ROUTE_DIR) $(if $(SECTORS),--sectors $(SECTORS)) $(if $(RESTART),--restart)

# Golden-image snapshots (tools/snapshot.py). `snapshot` runs the fast suites
# in check mode; `snapshot-diff` summarises the last run; `snapshot-accept`
# promotes a deliberate change with a note, e.g.
#   make snapshot-accept SUITE=tour SCENE=09_exit_approach NOTE="helmet blink phase"
snapshot: build
	$(PYTHON) tools/snapshot.py run --suite all

snapshot-diff:
	$(PYTHON) tools/snapshot.py diff --suite tour --suite world --suite art --suite sable --suite witnesses

snapshot-accept:
	test -n "$(SUITE)" && test -n "$(NOTE)"
	$(PYTHON) tools/snapshot.py accept --suite "$(SUITE)" $(if $(SCENE),--scene "$(SCENE)",) --note "$(NOTE)"

# Overlapped publication (docs/PERFORMANCE_PHASE5.md) is the slim default:
# the VBlank interrupt publishes the streamed tail while the next update
# casts. The synchronous tail it replaced (LUPINE3D_OVERLAP_PUBLICATION=0)
# builds into build/sync and keeps its frame checks and a motion replay;
# its captures land on other ticks than the default goldens, so the tour
# checks frames, not snapshots.
SYNC := LUPINE3D_OVERLAP_PUBLICATION=0
SYNC_ROM := --rom build/sync/lupine3d.gb --symbols build/sync/lupine3d.sym

sync:
	$(SYNC) $(PYTHON) tools/build_rom.py --output-dir build/sync

playtest-sync: sync
	$(SYNC) $(PYTHON) tools/playtest.py $(SYNC_ROM) --snapshot-mode none --output-dir build/playtest/sync/coherence_tour
	$(SYNC) $(PYTHON) tools/benchmark_motion.py --duration 10 --scenario walking --scenario turning --output-dir build/sync/motion

# Build SameBoy's lib target first. The core is external and revision-pinned
# by CI; it is not vendored into the source/release bundle.
sameboy: build
	test -n "$(SAMEBOY_DIR)"
	$(PYTHON) tools/sameboy_verify.py --core "$(SAMEBOY_DIR)"

mgba: build
	test -n "$(MGBA_DIR)"
	$(PYTHON) tools/mgba_verify.py --core "$(MGBA_DIR)"

# Differential CPU conformance: every instruction form the emitter can
# produce, in seeded micro-programs, compared register-for-register and
# byte-for-byte between the host harness and pinned SameBoy.
.PHONY: conformance
conformance:
	test -n "$(SAMEBOY_DIR)"
	$(PYTHON) tools/harness_conformance.py --core "$(SAMEBOY_DIR)"

variants:
	LUPINE3D_REPROJECTION=1 LUPINE3D_NARROW_YIELDS=0 $(PYTHON) tools/verify_variants.py reprojection --output build/reprojection.json
	LUPINE3D_LEVEL=tests/levels/two_sentinels.json $(PYTHON) tools/verify_variants.py two-actors --output build/two_sentinels.json
	$(PYTHON) tools/verify_variants.py folding --output build/folded_pixels.json
	# Folding is a property of the flat microstrip compositor, which only the
	# historical compact and legacy profiles keep: the unfolded oracle has no
	# textured kernel, so the fold identity is proven on compact.
	LUPINE3D_DISPLAY=compact $(PYTHON) tools/verify_variants.py folding --output build/folded_compact_pixels.json
	LUPINE3D_DISPLAY=compact LUPINE3D_FOLDED=0 LUPINE3D_COMPACT_STRIPS=0 $(PYTHON) tools/verify_variants.py folding --output build/unfolded_pixels.json
	$(PYTHON) -c 'import json; from pathlib import Path; a,b=(json.loads(Path("build/"+n+"_pixels.json").read_text())["checks"] for n in ("folded_compact","unfolded")); assert len(a)==9 and a==b'
	LUPINE3D_WALL_REUSE=0 $(PYTHON) tools/verify_variants.py folding --output build/reuse_disabled_pixels.json
	$(PYTHON) -c 'import json; from pathlib import Path; a,b=(json.loads(Path("build/"+n+"_pixels.json").read_text())["checks"] for n in ("folded","reuse_disabled")); assert a==b'
	LUPINE3D_PREPARED_RAYS=0 LUPINE3D_CAMERA_SETUP=0 $(PYTHON) tools/verify_variants.py folding --output build/prepared_disabled_pixels.json
	$(PYTHON) -c 'import json; from pathlib import Path; a,b=(json.loads(Path("build/"+n+"_pixels.json").read_text())["checks"] for n in ("folded","prepared_disabled")); assert a==b'

wall-reuse:
	$(PYTHON) tools/benchmark_wall_reuse.py

motion:
	$(PYTHON) tools/benchmark_motion.py

.PHONY: sustained
sustained:
	$(PYTHON) tools/benchmark_motion.py --duration 60 --scenario walking --scenario turning \
		--scenario walking_turning --scenario moving_fire --scenario open_door --scenario closed_door \
		--scenario opening_door --scenario two_actor_corner \
		--output-dir build/sustained $(MOTION_ARGS)

qa: build test playtest playtest-world research-v3

preview: build
	$(PYTHON) tools/make_preview.py

package:
	$(PYTHON) tools/package_release.py --output-dir dist

clean:
	rm -rf build __pycache__ tools/__pycache__ tests/__pycache__ research/__pycache__ .pytest_cache

.PHONY: sable-build sable-check sable-sustained
# Alternate output directory for the production art profile.
sable-build:
	LUPINE3D_DISPLAY=slim LUPINE3D_ART=sable-v2 $(PYTHON) tools/build_rom.py --output-dir build/sable-v2/rom

sable-check:
	$(PYTHON) tools/check_display.py
	LUPINE3D_DISPLAY=slim LUPINE3D_ART=sable-v2 $(PYTHON) tools/check_sable.py

sable-sustained:
	LUPINE3D_DISPLAY=slim LUPINE3D_ART=sable-v2 $(PYTHON) tools/sable_sustained.py
