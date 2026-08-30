PYTHON ?= python3

.PHONY: all setup build test research research-v3 research-atlas research-atlas-entity research-atlas-all research-atlas-pareto research-tail verify playtest playtest-world qa preview package clean

all: build

setup:
	$(PYTHON) tools/dev_setup.py

build:
	$(PYTHON) tools/build_rom.py

test: build
	$(PYTHON) -m unittest discover -s tests -v

research:
	$(PYTHON) research/geometry_v2_lab.py

research-v3:
	LUPINE3D_LEVEL=$(CURDIR)/levels/renderer_benchmark.json $(PYTHON) research/rendering_v3_lab.py

research-atlas:
	$(PYTHON) research/build_tile_atlas_v4.py

research-atlas-entity:
	$(PYTHON) research/build_tile_atlas_v4.py --apply-patterns 80 \
		--output-dir assets/entity_atlas_80 \
		--result-path research/results/tile_atlas_entity_80_v6.json \
		--measure-profile entity-heavy

research-atlas-all: research-atlas research-atlas-entity

research-atlas-pareto:
	$(PYTHON) research/build_tile_atlas_v4.py --pareto

research-tail:
	$(PYTHON) research/tail_failure_lab.py

verify: build test research
	$(PYTHON) tools/release_check.py

playtest:
	$(PYTHON) tools/build_rom.py
	$(PYTHON) tools/playtest.py

playtest-world:
	$(PYTHON) tools/build_rom.py
	$(PYTHON) tools/playtest.py --scenario playtests/living_world.json --output-dir build/playtest/living_world

qa: build test playtest playtest-world research-v3

preview: build
	$(PYTHON) tools/make_preview.py

package:
	$(PYTHON) tools/package_release.py --output-dir dist

clean:
	rm -rf build __pycache__ tools/__pycache__ tests/__pycache__ research/__pycache__ .pytest_cache
