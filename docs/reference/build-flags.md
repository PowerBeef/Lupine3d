# Build flags

The engine reads its configuration from `LUPINE3D_*` environment variables
**once, when it is imported**, so a flag applies to a whole process: set it
on the command, and use a fresh process for each configuration
(`lupine` and `make` do this for you). Defaults are the production
configuration. A request the engine cannot honour is refused, never quietly
adapted; only an *implicit* default adapts to an explicit diagnostic flag.

Values are `0` or `1` unless stated. `tools/lupine3d_v4/configuration.py`
resolves the rendering flags and `tools/lupine3d_v4/layout.py` the rest; the
build manifest records the resolved configuration and its id.

## Choosing what to build

| Flag | Default | What it selects |
|---|---|---|
| `LUPINE3D_GAME` | `games/sable_outpost` | the game: a directory with a `game.json`, or a name under `games/`. `--game` and `make … GAME=` set it |
| `LUPINE3D_LEVEL` | the game's campaign | a single level file to build as a one-level campaign (engine fixtures in `tests/levels/` resolve by name) |
| `LUPINE3D_DISPLAY` | `slim` | `slim` (160×120 world, 24-pixel HUD), or the showcase's historical `compact` (112/32) and `legacy` (96/48) |
| `LUPINE3D_ART` | `sable-v2` (`legacy` on the legacy display) | `sable-v2`, the native art every game uses, or the showcase's historical `legacy` art |
| `LUPINE3D_ART_ANIMATION` | `1` with `sable-v2` art | animated sprites; requires `sable-v2` |

## Production rendering (on by default)

| Flag | Default | What it does |
|---|---|---|
| `LUPINE3D_TEXTURED_WALLS` | `1` on slim | textured walls, the slim renderer ([textured walls](../explanation/textured-walls.md)); `0` is refused on slim (the flat slim profile was removed) and `1` elsewhere |
| `LUPINE3D_HDMA_STREAMING` | `1` except on legacy | patterns and the hidden map stream to VRAM by HBlank DMA during composition ([streamed publication](../explanation/streamed-publication.md)); required by textured walls |
| `LUPINE3D_OVERLAP_PUBLICATION` | `1` on slim | the VBlank interrupt publishes the tail while the next update casts; `0` builds the synchronous tail (`make sync`) |
| `LUPINE3D_COMPACT_STRIPS` | `1` | nine stored microstrip states (eleven on slim) |
| `LUPINE3D_CAMERA_SETUP` | `1` | per-frame camera setup hoisted out of the ray loop; requires prepared rays |
| `LUPINE3D_NARROW_YIELDS` | `1` | cooperative yields at narrow points; off with reprojection |
| `LUPINE3D_ATTRIBUTE_PADDING` | `1` | padded attribute publication |
| `LUPINE3D_FOLDED` | `1` | the folded compositor (the lower half is the upper half flipped); `0` is the unfolded diagnostic, legacy and compact only |
| `LUPINE3D_PREPARED_RAYS` | `1` | prepared ray records; `0` is a diagnostic |
| `LUPINE3D_Q14` | `1` | certified Q14 crossing order |
| `LUPINE3D_WALL_REUSE` | `1` | exact wall-page reuse when nothing moved |
| `LUPINE3D_FIXED_SIM` | `1` | fixed-tick queued simulation; `0` is a historical diagnostic (legacy profile) |
| `LUPINE3D_PROJECTION_STORAGE` | `direct` | projection table layout: `direct`; `paged256`/`hybrid256` are research formats |

## Experiments (off by default)

Each is kept, gated and measured; none is part of the production ROM. Some
exclude others and the resolver refuses the combination.

| Flag | What it tries |
|---|---|
| `LUPINE3D_REPROJECTION` | micro-reprojection between full updates (legacy profile only) |
| `LUPINE3D_INCREMENTAL_CERTIFICATE` | incremental crossing certificates |
| `LUPINE3D_DYNAMIC_TILE_CACHE` | a dynamic-tile cache |
| `LUPINE3D_CACHE_KEY_MIX` | mixed cache keys; requires the tile cache |
| `LUPINE3D_ANCHOR_PACKETS` | anchor packets (records 241-250); excludes textured walls and overlap |
| `LUPINE3D_PACKET_BOUNDS_REUSE` | packet-bound reuse; requires anchor packets |
| `LUPINE3D_PHYSICAL_DEPTH` | physical per-column depth; excludes textured walls and overlap |
| `LUPINE3D_ACTOR_PRECISION` | actor projection precision |
| `LUPINE3D_SCANLINE_ADMISSION` | per-scanline OBJ admission |
| `LUPINE3D_DOOR_IDENTITY` | door identity keys |
| `LUPINE3D_NEAR_FIELD` | near-field projection corrections; requires Q14 |
| `LUPINE3D_FOREGROUND_PUBLICATION` | foreground event publication; requires scanline admission, legacy profile |

## Tools and research

| Flag | Used by |
|---|---|
| `LUPINE3D_TILE_ATLAS_DIR`, `LUPINE3D_ENTITY_ATLAS_DIR` | the historical atlas research: build from another atlas directory |
| `LUPINE3D_COMPACT_ATLAS` | the entity atlas research: the compact entity atlas |
| `LUPINE3D_POPULATION` | `shipped` (the default) or `evidence`: the engine's evidence tools, `tools/run_tests.py` and the evidence snapshot suites boot the showcase's first sector with its frozen v0.12 population (`tests/levels/living_world_v012.json`), and the route refuses it ([verification](../explanation/verification.md#the-evidence-population)); a build refuses it too, since a build writes the game as it ships |
| `LUPINE3D_ROUTE_DEBUG` | `tools/playthrough.py`: trace every combat exchange of the controller route |
| `LUPINE3D_SAMEBOY_SEED` | the SameBoy adapter: the seed for randomised power-on RAM, to reproduce a run |
| `LUPINE3D_DUMP_RAM` | the core adapters: a file to dump power-on RAM to, for replay in the harness |

`tools/run_tests.py` drops every `LUPINE3D_*` variable (the game included)
and runs the historical suites under explicit legacy settings, so the
regression suite always tests the engine on the showcase.
