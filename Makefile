PYTHON ?= python3

.PHONY: all setup build test research research-v3 research-atlas research-atlas-pareto research-tail verify playtest qa preview package clean

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
	$(PYTHON) research/rendering_v3_lab.py

research-atlas:
	$(PYTHON) research/build_tile_atlas_v4.py

research-atlas-pareto:
	$(PYTHON) research/build_tile_atlas_v4.py --pareto

research-tail:
	$(PYTHON) research/tail_failure_lab.py

verify: build test research
	$(PYTHON) tools/release_check.py

playtest: build
	$(PYTHON) tools/playtest.py

qa: build test playtest research-v3

preview: build
	$(PYTHON) tools/make_preview.py

package:
	$(PYTHON) tools/package_release.py --output-dir dist

clean:
	rm -rf build __pycache__ tools/__pycache__ tests/__pycache__ research/__pycache__ .pytest_cache
