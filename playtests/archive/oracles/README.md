# Archived pixel-hash oracles

These files pinned nine RGB SHA-256 hashes per driven tour from v0.3 to v0.10.
Since v0.11 visual verification uses golden-image snapshots
(`tools/snapshot.py`, goldens under `snapshots/`), which are reviewable as
images and accepted with a note rather than edited as hashes. No tool reads
the files here any more; they are retained as the evidence each release
bound, so a historical ROM can still be checked against its own oracle by
hashing `image.convert("RGB").tobytes()` of a capture.

| File | ROM / release it bound |
| --- | --- |
| `v030_capture_pixels.json` | v0.3.0 (legacy 96-line profile) |
| `v062_capture_pixels.json`, `v063_capture_pixels.json` | v0.6.2 / v0.6.3 |
| `v070_capture_pixels.json`, `v070_sable_capture_pixels.json` | v0.7.0 (legacy and first Sable art) |
| `sable_v2_capture_pixels.json` | Sable v2 candidate (112-line compact) |
| `sable_hud_capture_pixels.json` | compact profile with the Sable HUD |
| `sable_slim_capture_pixels.json` | first slim (120-line) profile |
| `sable_steel_capture_pixels.json`, `sable_steel_helmet_capture_pixels.json` | steel HUD, then the helmet portrait |
| `sable_objective_capture_pixels.json`, `sable_objective_spaced_capture_pixels.json` | objective text, then its spacing fix |
| `sable_v09_capture_pixels.json` | v0.9 (`e59f722b…`) |
| `sable_v10_capture_pixels.json` | v0.10 (`76bc716f…`); the first accepted `tour` goldens equal these hashes |

The scenario files in `playtests/` no longer carry a `pixel_oracle` key; the
three production routes carry `snapshot_suite` instead.
