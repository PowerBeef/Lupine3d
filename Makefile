PYTHON ?= python3

.PHONY: all setup build test docs-check memory-map lupine research research-v3 research-atlas research-atlas-entity research-atlas-all research-atlas-pareto research-tail verify playtest playtest-world playtest-art qa preview package clean

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

# The `lupine` CLI: make lupine ARGS="level check levels/*.json"
lupine:
	$(PYTHON) tools/lupine.py $(ARGS)

research:
	$(PYTHON) research/geometry_v2_lab.py

research-v3:
	LUPINE3D_LEVEL=$(CURDIR)/levels/renderer_benchmark.json $(PYTHON) research/rendering_v3_lab.py --output-dir build/static_geometry --accuracy-only

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
	LUPINE3D_LEVEL=$(CURDIR)/levels/renderer_benchmark.json $(PYTHON) research/tail_failure_lab.py --output-prefix build/q14_tail --angle-step 4

verify: build test research research-v3
	$(PYTHON) tools/release_check.py

playtest:
	$(PYTHON) tools/build_rom.py
	$(PYTHON) tools/playtest.py

playtest-art: build
	$(PYTHON) tools/playtest.py --scenario playtests/sable_art_tour.json --output-dir build/playtest/sable_art_tour

playtest-world:
	$(PYTHON) tools/build_rom.py
	$(PYTHON) tools/playtest.py --scenario playtests/living_world.json --output-dir build/playtest/living_world

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

# The textured profile (docs/TEXTURED_WALLS.md) is opt-in: its ROM builds into
# build/textured and is verified by the same driven tours, the Sable checks
# and its own golden snapshots under snapshots/slim-sable-v2-textured/.
TEXTURED := LUPINE3D_TEXTURED_WALLS=1
TEXTURED_ROM := --rom build/textured/lupine3d.gb --symbols build/textured/lupine3d.sym

textured:
	$(TEXTURED) $(PYTHON) tools/build_rom.py --output-dir build/textured

playtest-textured: textured
	$(TEXTURED) $(PYTHON) tools/playtest.py $(TEXTURED_ROM) --output-dir build/playtest/textured/coherence_tour
	$(TEXTURED) $(PYTHON) tools/playtest.py $(TEXTURED_ROM) --scenario playtests/living_world.json --output-dir build/playtest/textured/living_world
	$(TEXTURED) $(PYTHON) tools/playtest.py $(TEXTURED_ROM) --scenario playtests/sable_art_tour.json --output-dir build/playtest/textured/sable_art_tour

sable-check-textured:
	$(TEXTURED) $(PYTHON) tools/check_sable.py --output-dir build/sable-v2/textured-checks

snapshot-diff-textured:
	$(TEXTURED) $(PYTHON) tools/snapshot.py diff --suite tour --suite world --suite art --suite sable

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
	LUPINE3D_LEVEL=levels/two_sentinels.json $(PYTHON) tools/verify_variants.py two-actors --output build/two_sentinels.json
	$(PYTHON) tools/verify_variants.py folding --output build/folded_pixels.json
	LUPINE3D_FOLDED=0 LUPINE3D_COMPACT_STRIPS=0 $(PYTHON) tools/verify_variants.py folding --output build/unfolded_pixels.json
	$(PYTHON) -c 'import json; from pathlib import Path; a,b=(json.loads(Path("build/"+n+"_pixels.json").read_text())["checks"] for n in ("folded","unfolded")); assert len(a)==9 and a==b'
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
