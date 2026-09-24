# Contributing to Lupine 3D

Develop directly in the existing `main` checkout. Do not create development branches or worktrees for this project. Preserve unrelated edits and historical evidence. The owner has no physical hardware; use emulator qualification.

## Setup

```sh
python3 tools/dev_setup.py
source .venv/bin/activate
make build test
```

Use `make test`, which runs the historical regression profile and fresh-process production-art checks. Running the entire legacy suite under the new default display is not equivalent. See [Development](docs/engine/development.md) for pinned SameBoy/mGBA builds and diagnostic profiles, and [engine development](docs/engine/README.md) for where the code is and [your first engine change](docs/tutorials/first-engine-change.md) for the workflow.

## Engine and games

Lupine 3D is an engine; games are data under `games/` (the showcase,
`games/sable_outpost`, and the starter, `games/starter`). The build never
imports from a game directory. Content changes go in a game; engine changes
go in `tools/`, and a change that should not move a ROM byte is proven with
`make identity BASE=origin/main`. A new content limit goes in
`tools/lupine3d_v4/limits.py`, with its message pinned in
`tests/test_game_loader.py`.

## Change requirements

- Preserve deterministic output and the frozen v1 regression hash.
- Exercise emitted machine code and published VRAM/OAM for runtime changes.
- Run coherence/world routes, plus the art route for visual changes. An intentional image change is accepted as a golden snapshot with a note (`python tools/snapshot.py accept --suite … --scene … --note "why"`) and committed with its PNG; link the `visual-diff` CI artifact in the PR. Engine invariants are hard gates and are never accepted around (see `docs/explanation/verification.md`).
- Respect 96 dynamic BG patterns (legacy/compact; slim composes 238 pattern ids through a 96-slot ring), 96 HUD patterns, 32 masked OBJ patterns, 16 admitted world objects, four world objects per line and ten hardware objects per line. Compact/slim packets stream patterns and the map by HBlank DMA during composition and commit at most 62 banked GDMA blocks in one VBlank; the legacy profile's maximal 176-block packet is staged across VBlanks, never transferred in one VBlank.
- Retain the 3,000-byte resident reserve, fixed-ROM bank-switching code and immutable snapshot/publication ownership.
- Bind performance claims to a ROM hash, configuration and input replay. Separate full geometry updates from cached or foreground presentations.
- Document changed interfaces, allocations and timing contracts, in the handbook page that owns them: `make docs-check` holds the reference pages (CLI, build flags, manifest keys, limits) to the code.

The v0.8 visual/performance tradeoff was explicitly accepted, and later releases inherit it unchanged; the textured renderer's cost was accepted the same way (`docs/explanation/textured-walls.md`). This does not relax safety limits or enable unrelated experimental kernels. Keep failed performance-gate evidence and the original baseline comparisons intact.

Do not commit `build/`, `dist/`, virtual environments, downloaded cores, ROMs, credentials or release archives. Follow [AGENTS.md](AGENTS.md) for the code map and [Development](docs/engine/development.md#releasing) for verified packaging.
