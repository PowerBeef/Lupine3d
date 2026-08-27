# Renderer v0.3 engineering notes

## Implemented pipeline

1. Cast the existing 41 mandatory pair-centre anchors.
2. Reconstruct guarded odd pair columns exactly as v0.2.2 did.
3. Project in Q5 with a 512-entry height table and a saturated 9-bit divider.
4. Synthesize left/right physical tops at quarter intervals around each pair.
5. Recast only the two physical samples beside a pair-level face break.
6. Convert face-key, along-cell, and contiguous-door events into render styles.
7. Apply projected-height LOD to seams, frames, and door spines.
8. Collapse identical physical pairs onto the two-pixel microstrip fast path.
9. Reuse a static dark-mask seam atlas for full-interior tile rows.
10. Generate only silhouette/material-transition tiles and commit once in a
    fresh VBlank, preserving the v0.2 page protocol.

## Material grammar

- Base wall fills have no screen-space texture phase.
- Exact X/Y DDA side identity still provides large-scale light/shadow.
- A change of wall face creates a narrow structural crease.
- A change of along-face cell coordinate creates a world-anchored panel seam.
- Technology seams use the same narrow vertical grammar rather than a repeated
  full-tile matrix.
- Door frames derive from the projected run boundaries; the spine derives from
  its run centre.
- Dynamic silhouette tiles receive a one-row top lip and floor-contact shadow.
- Features disappear below 16 projected pixels; the door spine requires at
  least 32 projected pixels.

## Rejected during implementation

The proposed per-tile-row palette ladder was implemented and ROM-playtested.
Although it cost no frame DMA, it recreated visible horizontal ceiling/floor
bands. The final attribute maps therefore keep one phase-free viewport palette.
Additional CGB palettes remain initialized for future world/material selection,
not screen-row gradients.

## Budgets

- 32 KiB ROM-only image; renderer ends well below `$8000`.
- 96 dynamic tiles / 1,536 bytes maximum.
- 384-byte hidden view map.
- 120-block absolute GDMA cap, unchanged from v0.2.2.
- No software framebuffer.
- No per-frame attribute upload.
- No wall sprites and therefore no new per-scanline OBJ pressure.
