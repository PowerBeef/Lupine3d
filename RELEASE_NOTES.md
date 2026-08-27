# Lupine 3D 0.4.0

## Exact-fidelity performance architecture

v0.4.0 preserves the v0.3.0 hybrid 160-column image byte-for-byte while
reducing the driven tour's mean update cost by 18.61%.

### Engine changes

- Moved hot scalar DDA, projection, and compositor state into a stable HRAM
  ABI so the v0.4 assembler emits shorter/faster `LDH` accesses.
- Packed 1,024 ray directions as sequential `{absX, absY, stepX, stepY}`
  records and shared player-fraction boundary preparation across each cast.
- Added a corpus-trained exact boundary atlas: 255 signatures, 121 VRAM tile
  patterns, and 41.377% corpus coverage. Hash collisions are resolved by a
  full ten-byte comparison.
- Converted the ROM from 32 KiB ROM-only to 4 MiB MBC5, with no cartridge RAM.
- Added a 2,359,296-byte exhaustive projection-result LUT and a 65,536-byte
  exact DDA product LUT. The executable remains in fixed bank 0 and restores
  ordinary data bank 1 after each lookup.
- Removed the now-unused runtime projection divider and resident height table.

### Validation changes

- Expanded the project harness with MBC5 ROM-bank behavior.
- Added atlas reconstruction and banked-LUT layout tests.
- Tightened hot-path and full-update cycle ceilings.
- Added a frozen nine-capture RGB-pixel oracle from v0.3.0 to the driven
  playtest; any visible change now fails the run.
- Preserved the frozen v0.1.0 ROM SHA-256 oracle.

### Measured results

- driven mean: 1,118,243 → **910,143 cycles/update** (-18.61%);
- driven maximum: 1,264,820 → **1,124,736 cycles** (-11.08%);
- minimum driven rate: 6.632 → **7.458 updates/s** (+12.45%);
- isolated six-pose cast+render mean: 1,008,489 → **899,372 cycles** (-10.82%);
- exact capture pixels: **9/9**;
- unsafe GDMA starts and dynamic-tile overflows: **0**.

The VBlank ISR/staging and residual signature-cache ideas were investigated
but not retained because the measured workload did not benefit. Details and
checkpoint data are in `docs/PERFORMANCE_V4.md`.

Original Game Boy Color and independent-emulator certification remain pending.
