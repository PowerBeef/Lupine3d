# Approved helmet restored

Candidate ROM SHA-256:
`fd7c95e7f3237ca130d0fabe763190a1622d51dc7d49ff0c1fa7e704fb873f4c`.

The portrait returns to the [approved helmet concept](../../docs/design/hud-steel/concept.png):
an armoured shell, recessed brow, narrow visor and central respirator. The
uncovered human portrait was rejected. The surrounding steel HUD layout stays
unchanged. Native pixels live in `tools/lupine3d_v4/steel_hud.py`; builds load
the deterministic `helmet_steel` PNG, without invoking image generation.

Only the `helmet_steel` asset record differs from the preceding ROM
`2915cb06207620e4553f3af4f811fd94c13c8407ea358c27b5da9cb424111942`.
The final HUD uses 82 of 96 patterns (three fewer), within $8200–$871F in
bank 0. The 16-byte packet, animation clocks, runtime routines, 176-block DMA
ceiling and 3,123-byte resident reserve are unchanged.

- `portrait-diff.json`: the startup capture's 156 changed pixels all lie
  within the 16×16 portrait rectangle. Every surrounding pixel matches.
- `comparison.json`: six frozen worlds match, and direct HUD preparation
  and publication take exactly the same CPU T-cycles in five tested states.
- `qualification.json`: all 140 automated tests pass on this revision.
- `checks.json`: final-ROM art, four portrait states, snapshot packets,
  raster split, both maps, chassis and maximal publication checks.
- `routes.json`: coherence, world and art routes pass; nine captures match
  the new `sable_steel_helmet_capture_pixels.json` oracle. Historical steel,
  slim and beta.6 oracles remain intact.
- `cores.json`: pinned SameBoy CGB-0/E and mGBA controller smoke and frozen
  startup RGB comparisons pass for this ROM.

See the [current capture](../../docs/images/sable_steel_helmet_4x.png) and
[four native cels](../../assets/sable_v2/previews/helmet_steel-sheet.png).
ROM-driven motion previews are under `build/steel-helmet/motion/`.

These targeted subroutine comparisons do not constitute a new sustained
benchmark. Previous live timing and B/P budget results remain bound to their
original ROMs. Qualification is emulator-only; no release was published.
