# Contributing to Lupine 3D

Develop directly in the existing `main` checkout. Do not create development branches or worktrees for this project. Preserve unrelated edits and historical evidence. The owner has no physical hardware; use emulator qualification.

## Setup

```sh
python3 tools/dev_setup.py
source .venv/bin/activate
make build test
```

Use `make test`, which runs the historical regression profile and fresh-process production-art checks. Running the entire legacy suite under the new default display is not equivalent. See [Development](docs/DEVELOPMENT.md) for pinned SameBoy/mGBA builds and diagnostic profiles.

## Change requirements

- Preserve deterministic output and the frozen v1 regression hash.
- Exercise emitted machine code and published VRAM/OAM for runtime changes.
- Run coherence/world routes, plus the art route for visual changes. Intentional image changes need reviewed captures and a separately versioned oracle; retain historical fixtures.
- Respect 96 dynamic BG patterns, 96 HUD patterns, 32 masked OBJ patterns, 16 admitted world objects, four world objects per line and ten hardware objects per line. A maximal 176-block DMA packet is staged across VBlanks, never transferred in one VBlank.
- Retain the 3,000-byte resident reserve, fixed-ROM bank-switching code and immutable snapshot/publication ownership.
- Bind performance claims to a ROM hash, configuration and input replay. Separate full geometry updates from cached or foreground presentations.
- Document changed interfaces, allocations and timing contracts.

The v0.8 visual/performance tradeoff was explicitly accepted. This does not relax safety limits or enable unrelated experimental kernels. Keep failed performance-gate evidence and the original baseline comparisons intact.

Do not commit `build/`, `dist/`, virtual environments, downloaded cores, ROMs, credentials or release archives. Follow [AGENTS.md](AGENTS.md) for the code map and [Development](docs/DEVELOPMENT.md#releasing) for verified packaging.
