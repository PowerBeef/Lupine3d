The display/publication contract below remains active. Its art and timing

> Viewport implementation history. v0.8 ships the 24-pixel steel HUD with 94/96 patterns and the spaced GOAL caption; later sections record earlier candidates. See [the current HUD contract](STEEL_HUD.md).
figures describe the initial 24-pixel HUD qualification. The current default
uses the [steel-console artwork](STEEL_HUD.md), with85 HUD patterns and a
separately versioned visual oracle; the packet, viewport and memory reserve
remain the same.

# Slim HUD and production art defaults

The default development ROM now uses the generated Sable sprites, accepted-tick
animation, a 160×120 world and a 160×24 HUD. The owner explicitly accepted the
visual/performance tradeoff, including the additional viewport expansion. The
original quality-budget failures remain recorded; this decision does not
change those measurements or enable unrelated rendering experiments. The
published beta.6 release and historical fixtures remain unchanged.

## Build profiles

`make build` writes the current ROM to `build/lupine3d.gb`.

| `LUPINE3D_DISPLAY` | World | HUD | Default art |
| --- | --- | --- | --- |
| `slim` (default) | 160×120 | 160×24 | `sable-v2`, animation on |
| `compact` | 160×112 | 160×32 | `sable-v2`, animation on |
| `legacy` | 160×96 | 160×48 | `legacy`, animation off |

`LUPINE3D_ART=legacy` and `LUPINE3D_ART_ANIMATION=0` remain independent overrides.
Historical reprojection, foreground and non-fixed-simulation diagnostics use
implicit legacy defaults; explicitly requesting an incompatible display/art
combination fails. `make sable-build` is an alias for the slim profile with an
alternate output directory. No release is published by these commands.

## HUD design

Health keeps its large digits and cross on the left. The 16×16 animated helmet
sits in the centre, with its dark steel outline restored. On the right, a
separate hostile icon precedes smaller 5×7 digits; an EXIT label gives the
LOCK/OPEN state an explicit subject. DEAD/DONE retain their literal status, with the EXIT caption cleared.
The portrait has four pixels of padding above and below. All elements fit three tile rows, without a controls footer or contextual button
instructions. Controls remain documented in the README.

The icon occupies its own tile at x104 and the count begins at x112. The old
count tile erased the icon's rightmost column. Tests now protect the static
icon and separately published EXIT caption while publishing every possible actor count from 0–4.
The health font remains 6×10; status letters use 5×7 ink within their original
24-pixel slot. The generated sprite masters and animation cels are unchanged.

The HUD packet shrinks from the original 22 bytes to 16: four health tile IDs,
one hostile digit, two caption IDs, three status IDs and six portrait IDs. HUD preparation
no longer casts a door-interaction probe or prepares hint tiles. Both BG maps
receive the same immutable packet. No OBJ slots or additional runtime pattern
uploads are introduced. Every dynamic tile touching the top row includes
the divider, so digit, portrait and status changes cannot punch gaps in it.
HUD art occupies 69 of 96 permitted patterns.

## Viewport and publication

Slim mode uses horizon60, fifteen world tile rows, eight folded rows and the
STAT addressing switch at line120. Projection scale and horizontal FOV are
unchanged. Atlas metadata translates upper signature rows/tops by8 and lower rows by16;
checked-in pattern payloads remain untouched and unmatched tiles compose
exactly. Unclipped wall tops move down12 pixels and retain the legacy projection scale.
The central96-pixel region remains exact except for the established one-pixel
wall accent at boundaries that move onto or off an eight-pixel tile boundary.
The display comparison explicitly enumerates these accent changes; it does not
claim complete RGB equality for the four-pixel tile phase change.

The odd row count places both wall edges in the centre tile for far walls.
Slim mode adds stored states19/20 for these six-/four-pixel wall strips, with
independent pixel-coverage and emitted-compositor tests. Other profiles retain
the historical19 logical/nine stored states. Slim uses21 logical/11 stored
states,4,224 resident table bytes (3,072 fewer than the review baseline).

Map staging is480 bytes at $C600–$C7DF; attributes are480 bytes at
$DC00–$DDDF. Diagnostic strip scratch moves to $C8E0–$C8EF, outside OAM,
input clocks and snapshot-copy spans. The HUD packet occupies $D3D8–$D3E7.
Allocation assertions enforce these boundaries and preserve the3,000-byte
resident reserve. The current ROM retains3,123 resident bytes and1,808
fixed-ROM bytes free.

The total GDMA ceiling remains176 blocks:96 dynamic patterns,32 masked
patterns,24 original map blocks and24 original attribute blocks. The three
additional rows of each plane use bounded CPU copies into hidden maps:

1. Upload dynamic patterns. If dynamic+masked patterns exceed48, wait for
   another VBlank before the next stage.
2. Copy all96 extra map bytes, upload masked patterns and copy the first32
   extra attribute bytes.
3. In the final VBlank, upload the original map/attribute spans, copy the last64
   extra attribute bytes, and commit the HUD, OAM and page ownership together.

Small full packets take two VBlanks; larger packets take three. Cached world
presentations retain their separate path. The extra CPU copies total192 bytes
per full packet, with no visible-map writes and no transfer-limit increase.
Tests include both sides of the48-pattern threshold and the maximal176-block
packet, requiring all CPU writes and publication to finish before line153.

## Verification and evidence

`make test` uses `tools/run_tests.py`: historical arithmetic/image regressions
run under explicit legacy settings, while `test_sable_v2.py` launches clean
processes to test the production defaults, emitted art, publication and display
geometry. To run an individual historical test directly, set
`LUPINE3D_DISPLAY=legacy LUPINE3D_ART=legacy LUPINE3D_ART_ANIMATION=0`.
This preserves the original fixtures instead of changing them to fit the new
viewport. Production art has its own versioned oracle,
`playtests/sable_slim_capture_pixels.json`.

The local qualification output is under `build/hud24/`: emitted checks, display
comparisons, SameBoy CGB-0/E and mGBA reports,87 frozen independent witnesses,
controller-driven completion/restart, variants and sustained timing. Reports
are bound to their ROM hashes. Hardware testing is unavailable; qualification
is emulator-only. See the retained [slim evidence](../milestones/slim-hud/).

The original32-pixel candidate and its failed performance budget remain in
[SABLE_V2.md](SABLE_V2.md) and `milestones/sable-v2/`. They are historical
measurements, not timing claims for the120-line world. The viewport expansion
has a cost even though the HUD's own packet and preparation became smaller.

The current moving scenarios measure5.50–7.92 full geometry updates/s. All
eight scenarios exceed the original half-gains budget; the owner-authorized
default promotion is explicit in the retained report. The divider correction
adds no runtime drawing instructions or transfers. Its protected-start capture
changes exactly48 pixels on scanline120, with the world image unchanged.
