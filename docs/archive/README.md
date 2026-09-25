# Archived documents

These documents describe earlier releases and the research that led to the
current engine. They are kept verbatim as evidence, with their links
rewritten to this directory: numbers in them measure the ROM they name, not
the current one, and commands in them may name tooling that has since
changed. `docs/README.md` lists the current guides; use source, the build
manifest and `docs/evidence/TEST_REPORT.md` to resolve any conflict with a page here.

| Document | Release | What it records |
|---|---|---|
| [Test report v0.12](TEST_REPORT_V12.md) | v0.12 | The first release under the showcase's own name: the engine and its game separated, before the overhaul |
| [Test report v0.11](TEST_REPORT_V11.md) | v0.11 | The three-episode, eighteen-sector campaign, before the engine and its game separated |
| [Test report v0.10](TEST_REPORT_V10.md) | v0.10 | HBlank-streamed publication and the six-sector campaign |
| [Test report v0.9](TEST_REPORT_V09.md) | v0.9 | ROM-bound qualification and performance of the v0.9 campaign build |
| [Test report v0.8](TEST_REPORT_V08.md) | v0.8 | The first steel-HUD, six-cel-weapon release |
| [Test report beta.6](TEST_REPORT_BETA6.md) | beta.6 | The exact-output rendering milestone |
| [Test report beta.5](TEST_REPORT_BETA5.md) | beta.5 | Prepared rays and the first playable beta |
| [Rendering implementation](RENDERING_IMPLEMENTATION.md) | beta.6 | Exact-output kernels, gated experiments and the original B/P measurements |
| [Wall reuse](WALL_REUSE.md) | beta.5 | The exact wall-key cache and its 53-scene verification |
| [Column performance](COLUMN_PERFORMANCE.md) | beta.5 | Prepared rays, physical columns and their measurements |
| [Runtime performance](RUNTIME_PERFORMANCE.md) | beta.4 | Fixed-point arithmetic and the product/projection tables |
| [Performance v4](PERFORMANCE_V4.md) | v0.4 | Checkpoint data for the fourth renderer |
| [Overhaul implementation](OVERHAUL_IMPLEMENTATION.md) | beta.3 | Fixed-rate simulation, masked entities and sliding doors |
| [Living world v6](LIVING_WORLD_V6.md) | v0.6 | Doors, the first Sentinel and the runtime level loader |
| [Renderer v3](RENDERER_V3.md) | v0.3 | The third renderer's design |
| [Geometry v2 roadmap](GEOMETRY_V2_ROADMAP.md) | v0.2 | The Q14 traversal plan |
| [Material and shading redesign](MATERIAL_AND_SHADING_REDESIGN.md) | v0.7 | Why contrast bands and a palette depth ladder were rejected |
| [Research and decisions](RESEARCH_AND_DECISIONS.md) | early | The original research log |
| [Sable Outpost beta.6 art contract](SABLE_OUTPOST_BETA6.md) | beta.6 | The art checks before the steel HUD |
| [Initial Sable sprites](SABLE_V2.md) | v0.7 | The 112-line candidate and its performance decision |
| [Slim display contract](SLIM_HUD.md) | v0.8 | Viewport expansion and publication design for the 160×120 profile |

Milestone evidence bound to specific ROMs lives in [`milestones/`](../../milestones/),
and the retired pixel-hash oracles in [`playtests/archive/oracles/`](../../games/sable_outpost/playtests/archive/oracles/).
