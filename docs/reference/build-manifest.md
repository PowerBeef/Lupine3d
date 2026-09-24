# Build manifest

Every build writes `build_manifest.json` beside the ROM (in `build/` for the
showcase, `build/games/<id>/` otherwise). It says what the ROM is, what it was
built from and how its memory is spent; tools and reports read it instead of
rebuilding. It is large; these are the parts a game maker and a reviewer
use.

## Identity

| Key | Value |
|---|---|
| `sha256` | the ROM's SHA-256: the name every report, golden and qualification uses for it |
| `configuration` | the resolved [build flags](build-flags.md) and content hashes the ROM was built with |
| `configuration_id` | a hash of `configuration`: two builds with the same id were built the same way |
| `game` | `id`, `title`, `directory` and `files`: every file of the game the build read, with its SHA-256 |
| `title`, `header_checksum`, `global_checksum`, `rom_size_bytes`, `cgb_flag` | the cartridge header as written |
| `exports` | the debugger exports' format, symbol counts, and the SHA-256 of the `.sym` and `.map` files |

## Content

| Key | Value |
|---|---|
| `campaign` | per level: its index, name, ROM bank and slot page, doors, actors, fixtures, the medkit's value and its certificate numbers |
| `campaign_levels`, `campaign_level_bank_base`, `campaign_levels_per_bank`, `campaign_level_slot_pitch` | where the levels are packed |
| `palette_sets`, `palette_set_names` | the themes, in order |
| `art_direction` | the game's title |
| `level_format`, `vram_profile` | the level format and the resident atlas profile |

## Memory

| Key | Value |
|---|---|
| `memory_budget` | the budgets that fill first: `fixed_code_end` (where resident code ends in bank 0; it must stay at or below `$4000`), `resident_free_bytes`, the stack reserve, HRAM, and the HUD and OBJ pattern counts |
| `allocation_ledger` | every ROM, WRAM, HRAM and VRAM range the engine allocates, with its owner and lifetime; the build asserts they never overlap. [Memory map](memory-map.md) is generated from it |
| `engine_size`, `engine_origin`, `engine_end` | the resident engine's extent |
| `bank_bound_labels` | labels that live in a switched ROM bank, with the bank |
| `symbols` | every label and its address (also in the `.sym` file) |

## The renderer

Most other keys record the renderer's contracts as built (rays, columns,
projection format, publication limits, streaming, the wall cache, the
simulation clock): `publication`, `hblank_streaming`,
`maximum_commit_blocks`, `maximum_publication_vblanks`, `dynamic_tile_capacity`,
`rays`, `physical_columns`, `simulation_tick_hz` and their neighbours.
[Architecture](../explanation/architecture.md) explains them; tests read
them to hold the ROM to its own claims.
