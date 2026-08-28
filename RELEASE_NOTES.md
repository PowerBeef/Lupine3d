# Lupine 3D 0.6.0 — Living World

This release turns the renderer core into a playable vertical slice while preserving the accepted empty-world pixels exactly.

### Geometry and rendering

- Added corrected-perpendicular `RAY_DEPTH[80]` and build-time `RAY_SEGMENT[80]` certificates.
- Made adaptive interpolation segment-aware and added exact physical recasts at ambiguous surface boundaries.
- Added renderer-heavy (121 patterns) and entity-heavy (80 patterns) level-selectable VRAM profiles. The entity profile frees 41 tile IDs and remains overflow-free across 24,384 corpus views.
- Added a hybrid OAM billboard path with 8×16 far and 16×32 near LODs plus per-strip wall-depth clipping.
- Added atomic 160-byte shadow-OAM publication, permanent weapon/UI reservations, and budget-aware deferral beside worst-case GDMA.
- Added an optional compile-time ±4-pixel VBlank turn-reprojection experiment with guard tiles and a scanline-96 HUD reset.

### Living World slice

- Added an authored JSON level pipeline with map materials, spawn points, doors, pickups, triggers, exit, palette and VRAM profiles.
- Added one original Sentinel with dormant, patrol, chase, attack, hurt and dead states.
- Added exact-grid line of sight, low-frequency AI, hitscan damage, player damage, death, medkit drop, exit activation and level completion.
- Added axis-separated radius collision and an eight-step door that remains solid until its projected panel fully retracts.

### Verification and tooling

- Expanded the suite to 34 tests, including both VRAM profiles, depth/segment identity, OAM limits, clipping, AI/combat, door timing and the reprojection build.
- Added a second driven playtest that completes the Sentinel combat/drop/pickup/exit loop.
- Preserved all nine frozen empty-world RGB captures byte-for-byte.
- Retained the 41-pixel exceptional-tail certificate after a full 3.9-million-column correction experiment improved only one column and did not justify runtime complexity.
- Updated clean-room packaging, CI evidence, preview generation and documentation for the current implementation.

Original Game Boy Color and independent-emulator certification remain pending.

## 0.5.0 — Responsive, inspectable engine core

v0.5.0 preserves every accepted v0.3 RGB capture and the v0.4 rendering
architecture while making input, research, and maintenance safer.

### Engine changes

- Added a minimal VBlank interrupt sampler. It records the latest held state
  and OR-latches rising edges, while all movement and pose mutation remain in
  the main loop.
- Main-loop input consumption is atomic and uses a stable held-state snapshot.
  A short press that begins and ends during a long render is therefore acted
  on at the next simulation boundary instead of being lost.
- Extended the project emulator with VBlank IF generation, interrupt dispatch,
  EI delay, RETI behavior, and live joypad sampling.
- Split the 90 KB ROM builder into layout, resources, reference-model, emitter,
  and linker modules while preserving the public `build_rom` API.

### Research and verification changes

- Added a full tail-failure corpus with pose, physical column, expected/actual
  face, top error, map neighborhood, CSV/JSON evidence, and a visual sheet.
- Added an emitted-ROM exact-atlas Pareto study. The full 121-pattern cache is
  retained because it remains fastest; the 80-pattern option frees 41 tile IDs
  at a measured 2.28% mean-cycle cost.
- Added regression certificates for the known 41-pixel tail case and for a
  one-frame A-button pulse captured during rendering.
- Expanded the suite from 25 to 27 tests. All nine RGB captures remain exact;
  the driven mean is 910,156 cycles/update with zero unsafe GDMA starts.

## v0.4.0 exact-fidelity performance architecture

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
