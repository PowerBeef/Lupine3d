# Steel HUD qualification

Candidate ROM SHA-256:
`2915cb06207620e4553f3af4f811fd94c13c8407ea358c27b5da9cb424111942`.

This implements the approved industrial panel and the subsequent open-face
human portrait correction. The 160×120 world and 24-pixel HUD layout remain
unchanged. EXIT LOCK means living Sentinels prevent level completion; EXIT
OPEN means the exit is unlocked, independent of the sliding door position.

The HUD uses 85 of 96 patterns and the existing 16-byte snapshot packet.
There are no extra runtime pattern uploads, OAM objects or DMA blocks.
Resident reserve remains 3,123 bytes; fixed-ROM free space is 1,808 bytes.
See [design and implementation](../../docs/STEEL_HUD.md) and the
[before/after capture](../../docs/images/steel_hud_before_after_3x.png).

## Evidence

- `checks.json`: final-ROM asset, animation, chassis, raster and publication
  checks, including both maps and the maximal 176-block packet.
- `comparison.json`: six frozen scenes have identical world/foreground RGB;
  five HUD-state probes have identical preparation and publication T-cycles.
- `timing-summary.json`: four 10-second controller A/B scenarios against
  prior HUD ROM `b261d21913255efc9a74d7be4c0b5f46b40f9cf1fec5bf3bb50dd5785c7142a0`.
  Mean and p95 full-frame times match exactly for walking, turning, moving
  fire and two-actor corner contention. No post-setup game-RAM writes occurred.
- `routes.json`: coherence, world and art routes; all nine captures match the
  separately versioned steel oracle. Historical oracles remain intact.
- `controller.json`: controller-only completion and restart, without game-RAM
  injection.
- `cores.json`, `independent.json`: pinned SameBoy CGB-0/E and mGBA lanes,
  plus 87 independent witness scenes.
- `qualification.json`: configuration and resource summary. The full 140-test
  suite passed before the final portrait pixel/blink-phase revision; the
  three focused Sable tests and final emitted-ROM checks passed afterward.

Summaries retain hashes of their full transient reports under
`build/steel-hud/`. Timing uses CPU T-cycles at 8,388,608 Hz. This targeted HUD
comparison does not replace the original eight-scenario sustained B/P budget.
That earlier visual upgrade failed the budget and was enabled by the owner's
explicit preference for the visual improvement; its evidence remains intact.

Qualification is emulator-only. Hardware was unavailable and no release was
published. The local development packager checks clean-source default and
historical legacy rebuilds, then verifies archive file hashes.
