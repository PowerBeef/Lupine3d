# Lupine 3D 0.7.0-beta.2 — Sable Outpost

- Original gunmetal/green environment, illuminated teal doors, amber utility lighting and coherent functional colours.
- Sixteen map-authored wall fixtures: vents, caged lights, sector signs and moving door access emblems. Physical segment/cell masks prevent decoration leaking across corners or openings; at most four fixture objects share the existing bounded world pool after actors.
- New shotgun and gloved hands, red-armoured Sentinel animation, medical crate, exit beacon palette, clear reticle and muzzle flash.
- A 78-pattern instrument-panel HUD with large health/hostile counts, visor portrait, controls and LOCK/OPEN/DEAD/DONE text. A verified line-96 addressing switch uses spare bank-0 VRAM without reducing the wall atlas.
- HUD preparation runs before VBlank. Publication uses a measured 24-pattern single-window budget and the documented 160-M-cycle OAM wait. Default large packets remain atomic over two VBlanks; the optional reprojection stress case can use three.
- 72 tests, reviewed RGB fixtures, close-up art tour, controller-only completion and independent SameBoy CGB-0/CGB-E plus mGBA checks.

The protected room/corridor topology and wall mathematics remain intact. This visual pass adds measurable rendering work; original CGB/flash-cartridge validation remains pending. See [visual implementation](docs/SABLE_OUTPOST.md) and [test report](docs/TEST_REPORT.md).

---

# Lupine 3D 0.7.0-beta.1 — Living Renderer

Implements the software items deferred by the foundation alpha:

- Certified selective Q14 crossing order removes all ≥8-pixel top errors in the full retained 24,384-view corpus; maximum is 4.489522 pixels. Historical evidence remains unchanged.
- True sliding centre-plane doors share geometry across rendering, LOS, hitscan and radius collision.
- A 16-bit timestamped input queue drives fixed-tick simulation. Rendering yields cooperatively while preserving a separate immutable WRAM snapshot.
- Masked hardware 8×16 billboards, three size LODs with hysteresis, four bounded actor slots, nearest-first submission and scanline admission.
- Per-face colour metadata separates neutral steel, muted-green machinery and recognizable cyan/white doors. No eye-height rail returns.
- Matched dynamic patterns, masked sprites, attributes, map, HUD and OAM publish atomically, with bounded two-VBlank staging for large packets.
- Optional turning reprojection shifts published world objects with the BG while retaining fixed UI; remains disabled by default.
- Pinned SameBoy CGB-0/CGB-E and mGBA lanes, two-Sentinel acceptance scene, folded/unfolded RGB equivalence and controller-only level completion.

This is a playable beta, not a blanket speedup or original-hardware certification. The combat diagnostic reaches 4.26 visual updates/s in its slowest view even though controls/simulation use fixed ticks. Pixel masks retain two-pixel conservative wall-depth precision. See [implementation status](docs/OVERHAUL_IMPLEMENTATION.md) and [test report](docs/TEST_REPORT.md).

---

# Lupine 3D 0.7.0-alpha.1 — Renderer Foundation

First implemented milestone of the overhaul, not completion of the full roadmap.

- Paired projection records retain actual cast depth in the same 2.25 MiB ROM budget.
- Latent door-jamb faces have physical IDs in all 16 door-state combinations.
- Current-pose hitscan ignores cached visibility; entities share the wall camera focal length and project their feet from depth.
- Signed BG addressing separates OBJ art from world patterns; the full 121-pattern atlas coexists with entities.
- Folded composition reuses upper patterns through CGB Y-flip and a paired palette; unfolded A/B remains available.
- Cold boot assets move to bank 152; the stack moves to fixed WRAM; generated memory budgets enforce fixed-bank hot code.
- Large packets stage hidden patterns, then publish BG/HUD/OAM together.
- Joypad polling no longer advances the VBlank clock; bounded AI catch-up retains tick remainder.
- 47 tests, controller-only level completion, and pinned SameBoy CGB-0/CGB-E smoke lanes.

The opened-airlock RGB fixture intentionally removes 50 false-crease pixels after inspection. The other eight legacy captures are unchanged; all nine folded/unfolded captures match each other.

High-precision tail fallback, fully fixed-rate simulation, masked multi-entity rendering, real sliding apertures and original-hardware validation remain unfinished. See [implementation status](docs/OVERHAUL_IMPLEMENTATION.md).

---

# Lupine 3D 0.6.3 — Spatial Clarity

This revision makes the authored world read as geometry rather than a collection of decorative screen marks.

### Rendering grammar

- Removed the eye-height machinery rail and its horizon-locked row-48 presentation path.
- Decoupled physical surface segments from material paint; adjacent static materials now share one segment across a continuous exposed plane.
- Added `PIXEL_SEGMENT[160]` so the emitted ROM and host oracle classify physical breaks from the same authoritative certificate.
- Reduced true corners to a one-pixel dark crease, removed full-height cell ribs, and retained a wider run-centred door signal.

### Level and tooling

- Rebuilt Hangar Breach as a tighter room-and-corridor graph with meaningful door cuts, staged turns and a partitioned combat room.
- Added compiler gates for unreachable walkable cells, weak doors, critical-path length/turns, sightline length, open-room span and material fragmentation.
- Added a nine-frame spatial-coherence tour and refreshed the exact RGB oracle only after inspecting the generated contact sheet.
- Expanded the suite to 37 tests and added exact 160-column segment checks to both the ROM differential tests and driven harness.

The accepted map certificate is: 70 walkable cells, zero unreachable cells, 15 steps/five turns to the Sentinel, six-cell maximum sightline, 4×3 maximum open rectangle, an 11-cell minimum door cut, and zero paint seams/singleton runs on continuous surfaces.

Original Game Boy Color and independent-emulator certification remain pending.

---

# Lupine 3D 0.6.2 — Iron & Ash

This release gives Hangar Breach an original industrial-horror presentation pass while keeping the renderer-heavy timing contract intact.

### Original art and interface

- Rebuilt the CGB palettes around soot, concrete, oxidized metal, bone highlights and warning red.
- Replaced the foreground art with an original twin-bore weapon, visible gloves, asymmetric muzzle bloom and corner reticle.
- Redrew every Sentinel LOD/frame with a horned sensor crown, skull mask, layered armour, reactor core and clearer attack/hurt silhouettes.
- Reworked the medkit into a medical crate and refined the pulsing world-space exit beacon.
- Added a dark-metal status plate with original health/objective icons, Lupine badge and live two-digit fields mirrored across both BG pages.

### Surface grammar and performance

- Authored machinery-panel cells throughout Hangar Breach without changing its collision or progression topology.
- Added world-cell double ribs and a world-height machinery rail that never repeats in screen-tile space.
- Made the rail an entity-heavy profile feature: two rare seam IDs become light/shadow rail tiles, while renderer-heavy scenes retain those seams and omit all rail hot-path work.
- Conservatively remove the rail from mixed material/rib boundary tiles, preventing visual leakage and retaining exact-atlas hits.
- Deferred live-HUD VRAM writes beside publications above the established 72-block threshold, preserving the forced 120-block VBlank guarantee.
- Relocated cold palette data after the aligned hot tables, avoiding a wasted 1 KiB alignment page.

### Verification

- Added a 0.6.2 nine-capture RGB oracle for the intentional presentation change.
- Expanded the suite to 36 tests with exact surface-rail tiles, UI payload, status-map and emitted HUD-routine checks.
- Renderer-heavy route: 972,658.815 mean cycles, 1,124,756 maximum, 54 dynamic tiles, and nine of nine RGB captures exact.
- Living World route: 831,711.077 mean cycles, 1,125,776 maximum, 42 dynamic tiles, zero unsafe GDMA starts, and all combat/door/exit state assertions passing.

All art and interface assets in this release are original to Lupine 3D; no artwork or game data was imported from another title.

Original Game Boy Color and independent-emulator certification remain pending.

---

## 0.6.1 — Hangar Breach

This revision replaces the research maze with a compact E1M1-inspired level and promotes doors, spawning and exiting into explicit engine systems.

### Level and progression

- Added the original 16×16 Hangar Breach layout: protected southern start, staged approach, central zig-zag tech hall, optional courtyard branch and separate exit wing.
- Moved the Sentinel onto the mandatory route so the first enemy encounter cannot be bypassed accidentally.
- Added compiler-enforced player-radius clearance, minimum actor separation and open-door reachability for the authored start/exit contract.
- Added a two-phase projected exit beacon that is 8×8 at distance and mirrors into a 16×16 near panel.

### Door system

- Replaced the single global door with four independently stateful six-byte WRAM records.
- Added named authored doors, validated frame orientation, exact interaction selection and independent eight-step animation.
- Added a Sentinel-locked exit door with distinct blocked audio. Sentinel death unlocks the interaction but does not open the door automatically.
- Extended the host oracle and driven harness to validate partially retracted door geometry and per-door state/fraction telemetry.

### Verification

- Isolated the frozen renderer benchmark from the active gameplay level so deliberate map revisions cannot weaken the nine-capture pixel contract.
- Expanded the suite to 35 tests, including unsafe-spawn, malformed-door and missing-exit-lock rejection.
- Expanded the Living World route to cover safe spawn, normal opening, locked rejection, combat, pickup, exit unlocking, beacon visibility and completion.

Original Game Boy Color and independent-emulator certification remain pending.

---

## 0.6.0 — Living World

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
