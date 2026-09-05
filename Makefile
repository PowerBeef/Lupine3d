PYTHON ?= python3

.PHONY: all setup build test research research-v3 research-atlas research-atlas-entity research-atlas-all research-atlas-pareto research-tail verify playtest playtest-world playtest-art qa preview package clean

all: build

setup:
	$(PYTHON) tools/dev_setup.py

build:
	$(PYTHON) tools/build_rom.py

test: build
	$(PYTHON) tools/run_tests.py

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

.PHONY: playthrough sameboy mgba variants wall-reuse motion
playthrough: build
	$(PYTHON) tools/playthrough.py

# Build SameBoy's lib target first. The core is external and revision-pinned
# by CI; it is not vendored into the source/release bundle.
sameboy: build
	test -n "$(SAMEBOY_DIR)"
	$(PYTHON) tools/sameboy_verify.py --core "$(SAMEBOY_DIR)"

mgba: build
	test -n "$(MGBA_DIR)"
	$(PYTHON) tools/mgba_verify.py --core "$(MGBA_DIR)"

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
