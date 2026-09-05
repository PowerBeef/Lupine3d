# 24-pixel HUD qualification

Candidate SHA-256: `b261d21913255efc9a74d7be4c0b5f46b40f9cf1fec5bf3bb50dd5785c7142a0`. Default development configuration:
160×120 world, 160×24 HUD, Sable sprites and accepted-tick animations.
The continuous divider is preserved in every dynamic tile touching its row.

The owner explicitly accepted the visual/performance tradeoff. The original
mean/p95 half-gains budget remains unchanged; `quality-budget.json` records
the actual outcome. No release was published and no hardware was available.

140 regressions passed, followed by three final art/default/display tests.
Current ROM checks include complete strip selector domains, centre-row coverage,
all HUD states, all 36 enemy cels, maximum176-block publication, nine reviewed
image captures, world/art routes, controller completion/restart, folded/unfolded
and scalar/forced-full variants, SameBoy CGB-0/E, mGBA, and87 independent scenes.
The legacy image/build contract remains byte-exact. Display comparisons retain
explicit evidence for the120-line viewport's one-pixel tile-boundary accents.

Eight60-second controller scenarios use no post-setup diagnostic RAM writes.
Times below are full geometry updates, including waits, in milliseconds;
CPU T-cycles at8,388,608Hz are the stored canonical unit. Cached presentations
are reported separately in `timing-summary.json`.

| Scenario | Full geometry Hz | Mean ms | p95 ms |
| --- | ---: | ---: | ---: |
| walking | 6.22 | 160.7 | 167.4 |
| turning | 7.92 | 126.2 | 150.7 |
| walking_turning | 7.47 | 133.8 | 150.7 |
| opening_door | 0.08 | 167.5 | 200.9 |
| moving_fire | 7.45 | 134.1 | 150.7 |
| open_door | 5.90 | 169.3 | 184.2 |
| closed_door | 6.83 | 146.1 | 150.7 |
| two_actor_corner | 5.50 | 181.5 | 234.4 |

The gameplay controller watchdog now uses LCD time for combat, so cached
presentation speed cannot shorten its firing opportunity. The wall-reuse
benchmark retains its72-LCD timing window and observes pending final flashes
for at most48 further intervals; that drain is excluded from throughput.

Detailed transient captures, replay tapes and logs are under `build/hud24/`.
Source/report hashes bind the retained summaries to their original reports.
