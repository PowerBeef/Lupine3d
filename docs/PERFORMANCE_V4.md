# Lupine 3D v0.4.0 performance engineering

## Objective and non-negotiable contract

v0.4.0 optimizes the v0.3.0 high-fidelity renderer without changing its
visible result. The acceptance contract is stricter than visual similarity:

- all 80 adaptive ray descriptors and 160 physical-pixel descriptors match
  the integer host model;
- generated tile bytes and the 384-byte view map match the host compositor;
- all nine driven-tour captures match the frozen v0.3.0 RGB-pixel SHA-256
  oracle;
- GDMA begins in VBlank and the page flips only after both transfers;
- the frozen v0.1.0 ROM hash remains unchanged.

## Implementation sequence

1. Reproduce v0.3.0 tests, captures, and driven cycle telemetry.
2. Move frequently accessed scalar state from WRAM to a stable HRAM ABI.
3. Pack each ray direction as `{absX, absY, stepX, stepY}` and calculate the
   four player-fraction boundary distances once per cast batch.
4. Mine the 24,384-view corpus for exact boundary-tile signatures, upload the
   most useful 121 patterns to both VRAM banks at boot, and use exact
   hash-bucket comparison before accepting a hit.
5. Convert the cartridge to MBC5 and place an exhaustive projection-result
   table in banked ROM.
6. Place all DDA setup products in a second exact banked-ROM table.
7. Retain only checkpoints that improve measured execution while preserving
   the exact-output contract.
8. Run unit, exhaustive host, driven playtest, DMA, deterministic-build, and
   clean-room archive gates.

## Retained optimizations

### HRAM hot-state ABI

The SM83 has single-byte `LDH` transfers for `$FF00`-page data. DDA,
projection, compositor, counters, and pointer scratch now occupy an allocated
HRAM range rather than scattered WRAM bytes. Bulk arrays remain in WRAM. The
assembler enables this shortening only for the v0.4 builder, preserving the
frozen v0.1.0 output.

### Packed DDA data and shared fractional boundaries

The old setup fetched signed X/Y vectors separately and decoded their signs
for every cast. The new 4-byte record is fetched sequentially. Player-relative
distances to positive and negative X/Y cell boundaries are computed once per
visual cast batch and copied into each ray's setup.

### Exact static boundary atlas

The atlas signature is ten bytes: tile Y, the eight-pixel dark mask, and eight
absolute top values. It uniquely determines the emitted 16-byte 2bpp tile.
The runtime hash only selects a bucket; every field is compared before a tile
ID is accepted, so collisions affect speed but never pixels.

Corpus mining selected 255 signatures backed by 121 unique tiles. They cover
41.377% of dynamic boundary-tile instances in the 24,384-view corpus. Tile IDs
119–239 are mirrored in both VRAM banks, avoiding per-frame attribute-map DMA.
The profitable runtime design hashes and compares the source descriptors in
place; an earlier staging-buffer design was rejected after it regressed the
six-pose render corpus.

### MBC5 ROM as an arithmetic accelerator

All executable routines fit in fixed bank 0 below `$4000`; ordinary engine
data stays in bank 1. That makes bank switching safe inside hot routines.

The 2,359,296-byte projection table contains the final top edge for every
live tuple:

`component[0..255] × correction[110..127] × D32[0..511]`.

It exactly replaces correction multiplication, rounded division, saturation,
and the final projection-table read. A 65,536-byte product table contains
every `multiplicand[0..255] × multiplier[0..127]` result used by initial DDA
error setup. Both paths restore bank 1 before conventional switchable-bank
data is accessed.

The release is therefore a 4 MiB CGB-only MBC5 image (`$0147=$19`,
`$0148=$07`) with no cartridge RAM. This trades inexpensive ROM capacity for
scarce SM83 cycles while retaining exact integer behavior.

## Measurements

The driven coherence tour contains 27 updates, movement, turns, a door,
weapon feedback, and difficult material junctions. Cycle totals include
input, gameplay, casting, composition, VBlank wait, GDMA, and page publication.

| Checkpoint | Mean cycles/update | Incremental gain | Gain vs v0.3.0 |
|---|---:|---:|---:|
| v0.3.0 exact baseline | 1,118,243 | — | — |
| HRAM hot state | 1,029,813 | 7.91% | 7.91% |
| Packed/shared DDA setup | 1,024,610 | 0.51% | 8.37% |
| Direct exact tile atlas | 1,008,976 | 1.53% | 9.77% |
| Exact projection LUT | 962,160 | 4.64% | 13.96% |
| Exact DDA product LUT | **910,143** | 5.41% | **18.61%** |

Final driven results:

- maximum update: 1,124,736 cycles, 11.08% below v0.3.0;
- minimum update rate: 7.458 updates/s, 12.45% above v0.3.0;
- maximum dynamic tiles: 54;
- maximum total casts: 59;
- unsafe GDMA starts: 0;
- exact v0.3.0 capture pixels: 9 of 9.

The six-pose isolated cast+render corpus averages 899,372 cycles, 10.82% below
the optimized v0.3.0 pipeline. The driven result improves more because several
updates cross a complete LCD-frame scheduling boundary.

## Investigated but not retained

### Staged VBlank interrupt commit

Instrumentation places the stationary render's `upload_hidden_page` entry at
LCD line 129, before VBlank, on every steady update. The existing fresh-VBlank
poll therefore reaches the earliest safe full-payload commit. A VBlank ISR
would add register-save and input-sampling work during each of roughly seven
LCD frames spent rendering, but would not publish the single staging buffer
earlier. Asynchronous HBlank DMA would require a second 1,920-byte staging
buffer and still stalls the CPU for each block. Neither path offers a measured
throughput win for this workload, so v0.4 keeps the simpler proven commit.

### Residual per-frame signature cache

After the static atlas, the representative residual signatures were unique
within each frame. A cache would add lookup and clearing cost without avoiding
composition. It was not integrated.

## Hardware caveat

The project harness now models the MBC5 nine-bit ROM-bank register and runs all
ROM-vs-host probes through real bank switches. Original Game Boy Color and an
independent cycle-accurate emulator remain required for hardware certification.
Use `docs/HARDWARE_TEST_CHECKLIST.md`.
