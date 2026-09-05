# Documentation

These guides describe **v0.8**, the 160×120 Sable build with a 24-pixel HUD.

| Guide | Purpose |
|---|---|
| [Development](DEVELOPMENT.md) | Build, test, pinned cores, content and releases |
| [Architecture](ARCHITECTURE.md) | Current memory, renderer and publication contracts |
| [Sable Outpost](SABLE_OUTPOST.md) | Art direction, source assets and animation budgets |
| [Steel HUD](STEEL_HUD.md) | Current health, helmet, skull and objective implementation |
| [Test report](TEST_REPORT.md) | ROM-bound v0.8 qualification and performance |
| [Release notes](../RELEASE_NOTES.md) | Changes by version |
| [Agent guidance](../AGENTS.md) | Implementation map, invariants and checks |

## Design and historical evidence

- [Slim display contract](SLIM_HUD.md): viewport expansion and publication design; original art/timing figures are historical where marked.
- [Initial Sable sprites](SABLE_V2.md): the earlier 112-line candidate and its performance decision.
- [Rendering experiments](RENDERING_IMPLEMENTATION.md): beta.6 exact-output milestone, gated kernels and original B/P measurements.
- [Beta.6 test report](TEST_REPORT_BETA6.md) and [beta.6 art contract](SABLE_OUTPOST_BETA6.md): retained release evidence.
- [Beta.5 test report](TEST_REPORT_BETA5.md), [prepared rays](COLUMN_PERFORMANCE.md), [wall reuse](WALL_REUSE.md), [arithmetic](RUNTIME_PERFORMANCE.md), and the numbered research documents: version-specific development history.
- [Milestones](../milestones/): immutable results bound to their recorded ROMs.
- [Generated HUD concept](design/hud-steel/README.md): design references, distinct from native ROM captures.
- [Physical checklist](HARDWARE_TEST_CHECKLIST.md): optional future work; hardware is unavailable and is not a release prerequisite.

Use the current build manifest, source and tests to resolve conflicts with older documents. Never treat an archived benchmark as a measurement of a different ROM.
