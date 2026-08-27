# Lupine 3D v0.2.0 Research and Engineering Decisions

## 1. Research question

The v0.1.0 engine proved that a Wolfenstein-like first-person view could run as a real 32 KiB Game Boy Color ROM. Its wall geometry, however, was limited by three coupled choices:

1. forty rays, each covering four physical pixels;
2. quarter-tile ray marching;
3. a 3,840-byte tile-native software framebuffer uploaded in two VBlanks.

The v0.2.0 investigation asked whether the renderer could produce much more stable wall geometry without requiring a mapper, a larger cartridge, or a lower practical frame cadence.

The answer was yes, but not by simply casting more rays. The successful design combines exact grid traversal, conservative adaptive reconstruction, and tile-native boundary composition.

## 2. Baseline observations

Across the deterministic comparison corpus, the v0.1.0 marcher averaged 6.389 quarter-tile iterations per ray. Its four-pixel expansion produced:

- 3.307 px mean wall-top error against a floating 160-column reference;
- 8.140 px p95 error;
- 7.808% wrong visible wall segments;
- 3,840 bytes of tile-pixel traffic per rendered page;
- two VBlanks per visual commit.

These are not defects in the original proof of concept. They identify where a second-generation engine could obtain the largest gains.

## 3. Decision: signed-error DDA instead of fixed-step marching

### Chosen

Traverse one X or Y grid boundary at a time using a signed 16-bit ordering error:

```text
error = nextX × absY − nextY × absX
```

The traversal loop updates only the chosen axis distance and the high-order error term.

### Why

- visits only meaningful cell boundaries;
- returns the exact crossed wall side;
- returns a precise axis distance;
- removes wall-cell overshoot;
- avoids general multiplication and division inside the loop;
- maps well to SM83 byte arithmetic;
- creates a stable wall-face identity for adaptive spans.

### Evidence

The research corpus compared 243,840 quantized rays against independent exact cross-product traversal and found **zero hit mismatches**. Mean traversal work fell from 6.389 marcher iterations to 2.225 cell crossings, a 65.2% reduction per exact ray.

## 4. Decision: 80 two-pixel geometry columns

### Chosen

Double horizontal geometry from forty four-pixel slices to eighty two-pixel columns.

### Why not 160 exact rays

A full per-pixel cast path is possible in principle, but it would spend most of its work repeatedly confirming the same planar walls. Two-pixel geometry removes the most visible four-pixel stepping while preserving room for gameplay, audio, composition, and one-VBlank publication.

### Evidence

The full 80-ray exact path reduced mean wall-top error to roughly 0.255 px and wrong wall segments to 0.344% in the sampled corpus.

## 5. Decision: 1,024-direction vectors with camera-plane offsets

### Chosen

Use 1/1024-turn render directions with signed magnitude 127. Generate each screen offset from the camera plane rather than linearly spacing angles.

### Why

- quarter-angle-unit resolution reduces visible directional quantization;
- camera-plane spacing avoids an incorrect angular distribution across the screen;
- magnitude 127 improves precision over the original 64-scale vectors;
- 256×127 remains inside the signed 16-bit setup-product budget.

### Rejected alternative: full heading×column packet table

A 64-heading ×80-column interleaved ray table could remove some runtime pointer arithmetic and make the camera-plane vector direct. It would cost about 10 KiB and tightly couple rendering to four-unit headings. The current 1,024-direction representation supports all byte angles, fits comfortably, and meets the frame-rate target after compositor optimization. The packet design remains a future option if more cast-side performance is needed.

## 6. Decision: adaptive anchors with exact fallback

### Chosen

Cast every even column and the final column, then reconstruct an odd midpoint only when:

- both anchors have the same axis/material/plane key;
- their along-plane cells differ by no more than one;
- their projected top edges differ by no more than two pixels.

Otherwise cast the odd column exactly.

### Why this is novel and useful

For a continuous axis-aligned wall plane under a camera-plane projection, ideal projected height is affine across screen X. The engine exploits that coherence, but it does not trust geometry alone: quantized vectors, rounded distance, projection-table steps, and near-wall clipping can break exact integer affinity. The slope guard creates a conservative hybrid instead of an optimistic interpolation scheme.

### Evidence

Research corpus:

- 41 mandatory anchors;
- 44.494 mean exact casts per 80-column view;
- 60 maximum;
- zero wall-key mismatches against the full exact path;
- zero style mismatches;
- 0.056 px mean top difference;
- one-pixel p99 and maximum difference.

The renderer therefore obtains an 80-column silhouette for only modestly more exact casts than v0.1.0’s forty-ray path.

### Rejected alternative: unvalidated interpolation

Using only matching endpoints can hide a narrow nearer occluder or amplify projection-table clipping near the camera. The exact fallback is mandatory whenever identity or slope validation fails.

## 7. Decision: real wall-side lighting

### Chosen

Choose X/Y light variants from the actual DDA crossing axis.

### Why

The old angle-bit approximation was not a reliable description of the visible wall orientation. Exact DDA already returns the side, so directional shading becomes nearly free and materially improves depth readability.

## 8. Decision: eliminate the software framebuffer

### Chosen

Represent the frame as:

- 320 bytes of wall descriptors;
- static tile IDs for uniform cells;
- generated tiles only for edge/material-transition cells;
- one 384-byte hidden tile-number map.

### Why

The CGB is a tile renderer. Treating every viewport tile location as unique framebuffer memory discards the hardware’s strongest compression mechanism: tile reuse.

Most view cells are entirely ceiling, floor, or wall interior. Only boundaries require geometry-specific pixels.

### Evidence

Research corpus:

- mean dynamic tiles: 25.93;
- median: 30;
- p95: 50;
- maximum: 58 of 96;
- zero overflows;
- mean commit payload: 798.9 bytes;
- maximum observed payload: 1,312 bytes;
- mean reduction from the old 3,840-byte page: 79.2%.

## 9. Decision: precomputed two-pixel edge microstrips

### Chosen

Store a ROM library indexed by style, vertical state, and two-pixel pair position. Compose a dynamic 8×8 tile from four strips.

### Why

A wall boundary inside a tile has a small discrete state space. Precomputing its 2bpp contribution replaces runtime per-pixel decisions with table lookup and fixed-size copy/OR operations.

The microstrip library costs 6,080 ROM bytes but dramatically simplifies generated-tile rasterization. ROM space is plentiful relative to per-frame CPU and VRAM bandwidth.

### Rejected alternative: draw every dynamic pixel procedurally

A procedural 64-pixel tile generator would reduce ROM data but add branches, masks, row calculations, and bit packing to the hottest frame path.

## 10. Decision: unroll the 16-byte compositor kernels

### Chosen

Fully unroll the fixed 16-byte copy and OR routines used by each dynamic tile.

### Why

Profiling showed that loop-counter updates and taken branches consumed a significant portion of compositor time. The transfer length never varies, so the generic loop provided no runtime value.

### Result

Starting-pose `render_view` fell from 494,616 to 435,288 modeled cycles. The ten-update stationary harness run returned from 69 frames to 59 frames, matching v0.1.0’s estimated **10.123 updates/s** while retaining the new geometry and one-VBlank commit.

This is an example of a measured assembly specialization: small ROM growth, no algorithmic risk, and a frame-visible gain.

## 11. Decision: no per-frame tile deduplication in v0.2.0

### Considered

Hash or compare generated boundary tiles and reuse duplicate IDs.

### Why deferred

The measured maximum is already only 58 of 96. Deduplication would reduce transfer payload further but add comparison or hash work to every generated tile and complicate deterministic allocation. Current capacity and one-VBlank timing are already safe in the corpus.

A future implementation should be adopted only if measured gameplay scenes approach the cap or if the CPU cost is demonstrably lower than the saved DMA cost.

## 12. Decision: do not globally canonicalize X-flipped tiles

CGB background attributes can flip tiles, but global mirror canonicalization requires an attribute-map update for every frame. The small reduction in unique dynamic tiles did not justify the extra 384-byte attribute payload and publication complexity.

Static microtile libraries may still use flip symmetry where attributes are fixed in advance.

## 13. Decision: one full hidden map upload

### Chosen

Upload twelve complete 32-byte rows, not twenty short visible spans.

### Why

- one contiguous 384-byte GDMA command;
- no twelve-command setup overhead;
- deterministic page state;
- simple proof that the map is complete before the flip.

Padding columns are explicitly initialized to the ceiling tile so real hardware never depends on undefined WRAM power-on contents.

## 14. Decision: preserve CGB attribute maps permanently

Tile-number maps are always written in VRAM bank 0. VRAM bank 1 retains per-page attributes selecting the corresponding dynamic tile-data bank.

This invariant was made explicit after validation exposed the failure mode: a map upload under `VBK = 1` replaces attributes with tile IDs, producing page-dependent corruption. Tests now inspect both maps, both attribute maps, and repeated alternating commits.

## 15. Decision: hard maximum of 120 GDMA blocks

### Chosen

```text
96 dynamic tile blocks
24 tile-map blocks
120 total blocks = 1,920 bytes
```

### Why

The old renderer already used 120-block half-frame transfers. Keeping the new complete-page publication within the same per-VBlank transfer count creates a conservative, easy-to-audit upper bound.

The project harness forces the full 120-block path and checks that both transfers start in one VBlank before the display map changes.

### Remaining uncertainty

The eight-microsecond-per-block figure and harness timing model are strong engineering guidance, not a substitute for original CGB validation. The hardware checklist explicitly stress-tests maximum-complexity views and offers conservative fallback strategies.

## 16. Decision: keep v0.1.0 as an executable oracle

The original generator lives in `tools/build_rom_v1.py`, and its seven gameplay tests remain runnable. The expected SHA-256 is:

```text
0b5794c93b43b38a0dd2a76cf4e289f0317dd9b10314632ff366402ecd37fa00
```

This protects movement, collision, doors, firing, header behavior, and deterministic construction while permitting a complete renderer rewrite.

## 17. Verification hierarchy

No single test proves hardware correctness. v0.2.0 uses layered evidence:

1. exact mathematical references;
2. ROM-vs-host differential probes;
3. byte-exact compositor comparisons;
4. project-specific SM83/CGB execution;
5. forced worst-case DMA and page-coherence tests;
6. visual comparison images;
7. independent emulator and physical-hardware checklist.

Only layers 1–6 are complete in this release environment.

## 18. Quantitative summary

| Metric | v0.1.0 | v0.2.0 |
|---|---:|---:|
| Geometry columns | 40 | 80 |
| Mean top error | 3.307 px | 0.257 px |
| Wrong wall segment | 7.808% | 0.344% |
| Mean traversal iterations | 6.389 | 2.225 |
| Mean exact casts/view | 40 | 44.494 |
| Fixed framebuffer | 3,840 B | 0 B |
| Mean commit | 3,840 B | 798.9 B |
| Commit VBlanks | 2 | 1 |
| Stationary harness cadence | 10.123/s | 10.123/s |
| Engine body | 24,240 B | 17,530 B |

## 19. Follow-on research

The following ideas remain promising but were intentionally excluded from the v0.2.0 release gate:

- wider recursively certified affine spans;
- wall-plane continuation prediction;
- rotational ray-result reuse;
- compact depth representation for billboard sprites;
- dynamic tile deduplication;
- static full-edge microtile vocabulary;
- geometry-event / portal-like visible-span rendering;
- precomputed heading packets;
- animated subcell doors;
- mixed geometry/texture resolution.

Each should be introduced behind differential tests and measured independently rather than stacked into an unauditable optimization bundle.
