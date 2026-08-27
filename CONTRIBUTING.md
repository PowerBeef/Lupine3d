# Contributing to Lupine 3D

Thanks for helping improve the engine. Lupine 3D targets real Game Boy Color
constraints, so renderer changes must preserve both correctness and hardware
safety.

## Development setup

```sh
python3 tools/dev_setup.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/playtest.py
```

Or use `make test` and `make playtest` with an interpreter that has the
requirements installed.

## Change requirements

- Keep the ROM deterministic.
- Preserve the frozen v0.1.0 regression ROM hash.
- Run all 25 tests.
- Run the driven playtest; all nine v0.3.0 RGB capture hashes must remain exact
  unless a deliberate fidelity change includes an explicitly reviewed oracle
  update.
- Preserve the 120-block single-VBlank commit bound and zero unsafe GDMA
  starts.
- Include measurements for performance claims.
- Document any cartridge-layout or real-hardware compatibility change.

Do not commit `build/`, `dist/`, virtual environments, ROMs, or generated
release archives. CI publishes short-lived ROM/playtest artifacts for each
revision, while version tags create verified GitHub releases.

## Pull requests

Explain the problem, the hardware-aware design, verification performed, and
before/after measurements. Keep unrelated changes in separate pull requests.
