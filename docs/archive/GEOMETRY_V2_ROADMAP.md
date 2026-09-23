# Lupine 3D v0.2.0 — Wall Geometry Renderer Roadmap

## Objective

Replace the v0.1.0 quarter-tile, forty-column framebuffer renderer with a geometry-first engine that produces substantially smoother and more stable walls on a real Game Boy Color while reducing traversal waste and VRAM traffic.

## Completion contract

The v0.2.0 roadmap is complete only when:

- every mandatory phase below passes its exit gate;
- the 32 KiB CGB-only ROM builds deterministically;
- the frozen v0.1.0 ROM remains reproducible;
- the complete automated suite passes;
- research results are regenerated from final code;
- release artifacts survive a clean-room extraction and byte-identical rebuild;
- the project clearly distinguishes software evidence from pending physical-hardware certification.

**Roadmap state: all mandatory software phases complete.**

Original Game Boy Color testing remains a separate external acceptance gate.

---

## Phase 0 — Freeze and measure v0.1.0

**Status: complete**

### Work

- [x] Preserve the original v0.1.0 ROM generator.
- [x] Record the expected ROM SHA-256.
- [x] Preserve the original seven gameplay/cartridge tests.
- [x] Record engine size, ray count, framebuffer payload, page cadence, and harness rate.

### Evidence

```text
SHA-256:          0b5794c93b43b38a0dd2a76cf4e289f0317dd9b10314632ff366402ecd37fa00
Geometry:         40 rays × 4 pixels
Framebuffer:      3,840 bytes
Commit:           two 120-block VBlanks
Engine:           24,240 bytes
Stationary rate:  10.123 harness updates/s
```

### Exit gate

- [x] Clean v0.1.0 generator reproduces the frozen hash.
- [x] All seven v0.1.0 regressions pass.

---

## Phase 1 — Geometry reference and differential tests

**Status: complete**

### Work

- [x] Add an independent exact cross-product traversal reference.
- [x] Add a signed-error integer DDA model matching the SM83 algorithm.
- [x] Compare hit cell, hit axis, axis distance, material, and crossing count.
- [x] Add a floating camera-plane reference at all 160 physical columns.
- [x] Preserve before/after/reference comparison images.

### Evidence

- 243,840 quantized integer rays;
- zero signed-error traversal mismatches;
- 487,680 floating physical-column references;
- `research/results/geometry_v2_results.json`;
- `research/results/geometry_v2_comparison.png`.

### Exit gate

- [x] Zero integer hit-cell and hit-axis mismatches.

---

## Phase 2 — Exact signed-error grid DDA in the ROM

**Status: complete**

### Work

- [x] Replace quarter-tile sampling with cell-boundary traversal.
- [x] Initialize signed error from player fractions and absolute ray components.
- [x] Traverse one X or Y boundary per iteration.
- [x] Return exact crossed axis, map cell, material, crossing count, and axis distance.
- [x] Add a 32-crossing hard bound and deterministic fallback.
- [x] Add ROM-vs-host subroutine probes.

### Evidence

ROM probes compare:

- map X/Y;
- crossed side;
- Q8.8 distance;
- material;
- crossing count;
- projected top;
- visual style;
- face key;
- along-plane cell.

### Exit gate

- [x] ROM DDA probes match the host model field-for-field.
- [x] Movement, collision, and door behavior remain unchanged.

---

## Phase 3 — Camera-plane sampling and continuous projection

**Status: complete**

### Work

- [x] Generate camera-plane-derived offsets rather than linearly spaced angles.
- [x] Increase geometry to 80 two-pixel columns.
- [x] Add 1,024-direction signed render vectors at scale 127.
- [x] Compute corrected perpendicular distance in sixteenth-tile units.
- [x] Add a 256-entry wall-height table.
- [x] Store 80 compact top/style/face/along descriptors.
- [x] Add table-symmetry tests.

### Evidence

- mean wall-top error: 0.255 px for full exact v0.2.0;
- wrong visible wall segment: 0.344%;
- v0.1.0 equivalents: 3.307 px and 7.808%.

### Exit gate

- [x] All 80 descriptors remain valid.
- [x] left/right offset and correction symmetry passes.
- [x] geometry accuracy materially exceeds v0.1.0.

---

## Phase 4 — Correct wall-face materials and lighting

**Status: complete**

### Work

- [x] Select X/Y variants from the real DDA crossing side.
- [x] Add ordinary-wall light/shadow styles.
- [x] Add technology-wall light/shadow styles.
- [x] Preserve a distinct door style.
- [x] Add orientation/material probes.

### Exit gate

- [x] All five expected styles are observed in ROM probes.
- [x] Door visuals and interaction remain distinct.

---

## Phase 5 — Validated adaptive spans

**Status: complete; promoted from follow-on research into v0.2.0**

### Work

- [x] Cast 41 mandatory anchors: all even columns plus column 79.
- [x] Pack a compact axis/material/plane face key.
- [x] Track along-plane cells.
- [x] Interpolate only when keys match, cells are adjacent, and anchor slope is at most two pixels.
- [x] Cast every unsafe midpoint exactly.
- [x] Track exact-cast count per frame.

### Evidence

```text
Mean exact casts/view:          44.494 of 80
Maximum exact casts/view:       60
Face-key mismatches:            0
Style mismatches:               0
Mean top difference vs full:    0.056 px
p99 / maximum top difference:   1 px / 1 px
```

### Exit gate

- [x] Adaptive face identity matches full exact casting.
- [x] Top error remains bounded.
- [x] Mean cast count remains materially below 80.

---

## Phase 6 — Boundary-only tile compositor

**Status: complete**

### Work

- [x] Remove the 3,840-byte software framebuffer from the frame path.
- [x] Preload static ceiling, floor, and five wall-interior tiles.
- [x] Classify each 20×12 viewport cell.
- [x] Allocate dynamic tile IDs only for edges and material transitions.
- [x] Add a 96-tile WRAM buffer and high-water/overflow instrumentation.
- [x] Add a 6,080-byte precomputed two-pixel edge-microstrip library.
- [x] Build a complete 12×32 hidden tile map.
- [x] Explicitly initialize hidden padding cells.
- [x] Add byte-exact ROM-vs-host compositor tests.
- [x] Unroll fixed 16-byte copy/OR kernels.

### Evidence

```text
Mean dynamic tiles:      25.93
p95:                     50
Maximum:                 58 of 96
Overflow views:          0
Mean commit payload:     798.9 bytes
Mean payload reduction:  79.2%
```

### Exit gate

- [x] Every visible viewport cell receives a valid tile ID.
- [x] Full staged map and dynamic bytes match the host model.
- [x] Deterministic corpus stays below capacity.
- [x] No frame depends on WRAM power-on contents.

---

## Phase 7 — Single-VBlank hidden-page commit

**Status: complete**

### Work

- [x] Upload dynamic pixels to the hidden page’s tile-data bank.
- [x] Upload the 384-byte tile-number map under `VBK = 0`.
- [x] Preserve permanent CGB attribute maps in VRAM bank 1.
- [x] Bound the complete page to 120 blocks / 1,920 bytes.
- [x] Flip LCDC map selection only after both transfers.
- [x] Add commit-event and GDMA timing instrumentation.
- [x] Add a forced maximum-capacity test.
- [x] Add repeated page-alternation and coherence tests.

### Evidence

- forced 96 dynamic tiles + 24 map blocks;
- both transfers start in one modeled VBlank;
- no unsafe GDMA events;
- no attribute-map corruption;
- correct alternating `$9800/$9C00` destinations.

### Exit gate

- [x] One fresh VBlank per visual commit.
- [x] No partial page is exposed by the harness.
- [x] Maximum 120-block path passes.

---

## Phase 8 — Performance and quality gates

**Status: complete**

### Work

- [x] Measure cast and render routines.
- [x] Measure stationary and scripted ten-update runs.
- [x] Compare v0.2.0 against the frozen baseline.
- [x] Add deterministic cycle and update-rate floors.
- [x] Generate machine-readable geometry, bandwidth, and verification reports.
- [x] Generate visual comparison images.

### Final measurements

| Metric | v0.1.0 | v0.2.0 |
|---|---:|---:|
| Geometry columns | 40 | 80 |
| Mean top error | 3.307 px | 0.257 px |
| Wrong wall segment | 7.808% | 0.344% |
| Mean traversal iterations | 6.389 | 2.225 |
| Mean visual payload | 3,840 B | 798.9 B |
| Commit VBlanks | 2 | 1 |
| Stationary harness cadence | 10.123/s | 10.123/s |
| Scripted v0.2 cadence | — | 9.955/s |
| Engine bytes | 24,240 | 17,530 |

### Exit gate

- [x] All 21 tests pass.
- [x] Geometry and VRAM improvements are material.
- [x] Stationary cadence retains 100% of the v0.1.0 harness estimate.
- [x] Scripted cadence remains above the release floor.

---

## Phase 9 — Documentation and release packaging

**Status: complete**

### Work

- [x] Update README.
- [x] Update architecture and research decisions.
- [x] Update test report and hardware checklist.
- [x] Update release notes and roadmap.
- [x] Regenerate ROM, manifest, listing, symbols, research outputs, verification JSON, and previews.
- [x] Create final named release artifacts.
- [x] Extract the complete source archive into a clean directory.
- [x] Rebuild and compare the ROM byte-for-byte.
- [x] Publish final SHA-256 manifest.

### Exit gate

`tools/package_release.py` builds and names the release artifacts, validates a freshly staged source tree, extracts the deterministic complete-source ZIP into another empty directory, reruns the complete software suite, compares the ROM byte-for-byte, and writes both the clean-room JSON and SHA-256 manifest. The release refuses to publish on any mismatch.

---

## External hardware-certification gate

**Status: pending by design**

The software roadmap does not substitute for:

- independent strict emulator testing;
- original Game Boy Color boot and control tests;
- maximum-complexity page-flip stress;
- audio and LCD review;
- flash-cartridge compatibility;
- long-duration soak testing.

Use `docs/HARDWARE_TEST_CHECKLIST.md`. Do not describe v0.2.0 as hardware-certified until those checks are recorded.

---

## Follow-on experiments

These are intentionally outside the v0.2.0 release contract:

- recursively certified wider affine spans;
- wall-plane continuation prediction;
- rotational ray cache;
- dynamic tile deduplication;
- flip-aware static microtile reuse;
- projected geometry-event rendering;
- precomputed heading packets;
- compact wall depth for enemies;
- animated subcell doors;
- mixed geometry and texture resolution.
