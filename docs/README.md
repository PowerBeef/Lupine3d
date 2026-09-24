# Documentation

These guides describe **main after v0.11** (unreleased): the eighteen-sector
campaign on the 160×120 Sable build with a 24-pixel HUD, textured walls as the
only slim renderer, and HBlank-streamed publication whose tail the VBlank
interrupt runs (overlapped publication). The test report is the v0.11
release's qualification. `python tools/check_docs.py` (in the fast CI lane)
keeps every link and command on these pages valid.

## Using the engine

| Guide | Purpose |
|---|---|
| [Developer guide](tutorials/README.md) | Start here to build a first-person game on the engine: the hardware primer, an engine tour, the generated memory map, how-tos and debugging |
| [Level format](reference/level-format.md) | The JSON level format, its units and limits, the compiled payload, and the Tiled (TMX) round trip |
| [Level certificate](reference/level-certificate.md) | What the compiler measures and refuses, and why |
| [Art pipeline](reference/asset-formats.md) | Indexed-PNG conventions, every asset kind, the sixteen palettes and their owners, wall textures |
| [Development](engine/development.md) | Build, test, the `lupine` CLI, debugger exports, pinned cores, content and releases |
| [Verification](explanation/verification.md) | Hard gates versus golden-image snapshots, reviewing and accepting a visual change, the CI lanes |

## How the engine works

| Guide | Purpose |
|---|---|
| [Architecture](explanation/architecture.md) | Memory, renderer, simulation and publication contracts |
| [Streamed publication](explanation/streamed-publication.md) | How a full update publishes in one VBlank, its contracts and measurements |
| [Textured walls](explanation/textured-walls.md) | Texture-mapped walls with depth shading: the exact host reference, the prototype gate, the emitted row-window kernel and ring (the engine's renderer on every slim build), and its measured cost |
| [Campaign](../games/sable_outpost/docs/campaign.md) | What turned the demo into a game, and what each decision cost |
| [Sable Outpost](../games/sable_outpost/docs/art.md) | Art direction, source assets and animation budgets |
| [Steel HUD](../games/sable_outpost/docs/steel-hud.md) | Health, helmet, skull and objective implementation |
| [Performance after textures](evidence/PERFORMANCE_PHASE5.md) | Phase 5: sustained rates of the textured ROM before and after the exact round and with overlapped publication (the default), where an update goes, the exact savings taken and what the rest would need |
| [Performance audit](archive/PERFORMANCE_AUDIT_V08.md) | Where a v0.8 update spends its cycles, and the ranked remaining headroom |
| [Test report](evidence/TEST_REPORT.md) | ROM-bound v0.11 qualification and performance |
| [Release notes](../RELEASE_NOTES.md) | Changes by version |
| [Agent guidance](../AGENTS.md) | Implementation map, invariants and checks |

## Evidence and history

- [Archived documents](archive/README.md): earlier test reports, design documents and research, kept verbatim with an index of what each one measures.
- [Milestones](../milestones/): immutable results bound to their recorded ROMs.
- [Generated HUD concept](../games/sable_outpost/docs/design/hud-steel/README.md): design references, distinct from native ROM captures.
- [Physical checklist](engine/hardware-checklist.md): optional future work; hardware is unavailable and is not a release prerequisite.

Use the current build manifest, source and tests to resolve conflicts with older documents. Never treat an archived benchmark as a measurement of a different ROM.
