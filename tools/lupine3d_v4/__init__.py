"""Stable implementation modules for the current Lupine 3D engine.

The top-level tools/build_rom.py module remains the compatibility facade used
by tests, research tools, and release scripts. This package separates memory
layout, generated resources, host references, and SM83 emission so a single
truncated file can no longer destroy every layer at once.
"""
