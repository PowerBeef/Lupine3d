# Skull, objective and text spacing

ROM SHA-256:
`a5f3d54eb7d9be446d2d6ca36c010e9be264792c14c73f9691d6027871057ccb`.

The skull counts remaining enemies. GOAL/HUNT becomes GOAL/EXIT when all
Sentinels are defeated; DEAD and DONE clear the caption. Both text lines now
sit one pixel lower, at HUD y=4 and y=10, with blank rows below the top bevel
and between the lines. The existing helmet is unchanged, as requested.

The lower text crosses a tile boundary. Three preloaded vertical tile pairs
let the publisher derive the bottom tile as ID+1, retaining the 16-byte HUD
packet. This adds six map writes and exactly 108 CPU T-cycles (12.9 us at
8,388,608 Hz) per HUD publication. Preparation timing is unchanged.

The HUD uses 94/96 patterns ($8200–$87DF in bank 0), with no additional runtime
pattern uploads or DMA blocks. Fixed-ROM free space is 1,776 bytes; resident
reserve remains 3,123 bytes. The maximal packet remains 176 DMA blocks.

- `qualification.json`: all 140 automated tests pass on the final ROM.
- `checks.json`: emitted-ROM asset, snapshot, both-map, raster and publication
  checks. Objective transitions verify all five packet IDs and the derived
  bottom tiles; spacing and chassis pixels remain correct in every state.
- `comparison.json`: six frozen worlds remain image-exact; five state probes
  confirm unchanged preparation and the exact 108-T-cycle publication delta.
- `pixel-diff.json`: relative to the unspaced objective capture, only the
  right-hand text rectangle changes. The helmet asset hash is unchanged.
- `routes.json`: coherence, world and art routes pass, including nine exact
  captures in the separately versioned spaced-objective oracle.
- `cores.json`: pinned SameBoy CGB-0/E and mGBA safety/startup checks pass.
- `status-captures.json`: ROM-bound diagnostic captures of HUNT, EXIT, DEAD
  and DONE. [View the states](../../docs/images/sable_objective_spaced_states_4x.png).

Historical fixtures and the byte-exact beta.6 legacy configuration remain
intact. These are direct subroutine timing measurements, not a new sustained
benchmark. Qualification is emulator-only; no release was published.
