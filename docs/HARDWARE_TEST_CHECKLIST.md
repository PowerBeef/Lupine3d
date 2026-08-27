# Lupine 3D v0.4.0 — Independent Emulator and Original Hardware Checklist

The automated project harness is strong regression evidence, but it is not independent hardware certification. Complete this checklist before claiming the ROM is validated on original Game Boy Color hardware.

## Test record

| Field | Value |
|---|---|
| ROM version | 0.4.0 |
| ROM SHA-256 | Copy from `dist/Lupine3D_v0.4.0_SHA256SUMS.txt` |
| Emulator(s) and version(s) | |
| Console model / board revision | |
| Flash cartridge / firmware | |
| Power source / battery condition | |
| Date | |
| Tester | |

Recalculate the SHA after any source change; do not rely on this table if the distributed ROM differs.

## Gate A — independent emulation

Use at least two maintained CGB-capable emulators. Configure one for strict timing or detailed diagnostics where available.

- [ ] Nintendo logo and title boot without header errors.
- [ ] ROM is recognized as CGB-only, MBC5, 4 MiB, with no cartridge RAM.
- [ ] No MBC5 bank-switch warnings; projection/DDA remain stable while turning.
- [ ] First view appears without a white screen or hang.
- [ ] No invalid-opcode or unmapped-memory warnings.
- [ ] No prohibited VRAM/OAM access warnings.
- [ ] No HDMA/GDMA timing warnings.
- [ ] D-pad movement and turning work.
- [ ] Collision blocks every outer wall.
- [ ] A produces shot sound and visible muzzle flash.
- [ ] B opens the door when directly ahead.
- [ ] Weapon/crosshair remain stable.
- [ ] Page flips show no tearing or mixed old/new tiles.
- [ ] Run for at least 30 minutes without lockup.

Inspect where possible:

- VRAM bank 0/1 tile data at `$8000`;
- tile-number maps at `$9800/$9C00` in bank 0;
- attribute maps at `$9800/$9C00` in bank 1;
- `VBK`, `HDMA1-5`, LY, and LCDC bit 3 around a page commit;
- OAM line limits;
- CGB double-speed state.

Expected page protocol:

```text
hidden tile bank: dynamic tiles → $8000
VBK = 0:         tile IDs      → hidden $9800/$9C00
same VBlank:     LCDC map bit flips after both transfers
```

## Gate B — original CGB smoke test

- [ ] Verify the flash-cartridge copy’s exact SHA-256.
- [ ] Cold boot five times.
- [ ] Power-cycle five additional times.
- [ ] Confirm immediate transition to the first view.
- [ ] Verify every control.
- [ ] Verify both sounds through the internal speaker and headphones if available.
- [ ] Walk while turning continuously for five minutes.
- [ ] Walk into north, west, south, and east outer boundaries.
- [ ] Open the door and walk through its former cell.
- [ ] Fire repeatedly while moving/turning.
- [ ] Observe for transient tiles, alternating attributes, or page tearing.
- [ ] Leave the ROM running for at least 60 minutes.
- [ ] Repeat on a second CGB or flash cartridge when available.

## Gate C — worst-case geometry and transfer stress

Visit or create views with:

- [ ] several near wall edges in the same frame;
- [ ] a door edge and technology-wall edge together;
- [ ] rapid rotation near a corner;
- [ ] long diagonal corridor views;
- [ ] movement directly toward a wall;
- [ ] repeated map flips while firing.

Watch for:

- [ ] a boundary tile replaced by a plain wall tile, which may indicate dynamic overflow;
- [ ] old tile pixels with a new map;
- [ ] new tile pixels with an old map;
- [ ] attributes turning into tile IDs on page 1;
- [ ] corruption only every other frame;
- [ ] lower-screen corruption near the end of VBlank;
- [ ] weapon or muzzle OAM instability.

The measured research maximum is 58 dynamic tiles; the hard cap is 96. Any apparent overflow on hardware is a release blocker even if the host corpus passes.

## Gate D — timing-sensitive observations

The absolute worst-case commit is 120 blocks, approximately 960 microseconds by the documented rough transfer figure, versus roughly 1,087 microseconds of VBlank.

- [ ] No corruption at maximum visual complexity.
- [ ] No one-frame corruption when changing direction quickly.
- [ ] No behavior difference between fresh batteries and stable external power.
- [ ] No behavior difference after 30–60 minutes warm.
- [ ] No audio anomaly synchronized with page flips.

If this gate fails, conservative fallbacks include reducing the dynamic-tile cap, splitting map publication over a second VBlank with explicit page readiness, or replacing GDMA with a measured HBlank/CPU-copy strategy. Do not silently widen the timing assumption.

## Gate E — original LCD visual acceptance

- [ ] Ceiling, floor, and all wall styles remain distinguishable.
- [ ] Ordinary wall planes read as clean surfaces with no continuous horizontal contrast bands.
- [ ] Adjacent light/shadow faces remain visibly separate at corners and deep junctions.
- [ ] Service-panel details read vertically and do not visually reconnect unrelated walls.
- [ ] X/Y side lighting is visible but not excessively dark.
- [ ] Door remains visually distinct.
- [ ] Far wall edges do not disappear into the background.
- [ ] HUD digits are legible.
- [ ] Crosshair and muzzle flash are visible.
- [ ] Weapon highlights remain distinct.
- [ ] Motion does not create objectionable temporal flicker on the original LCD.

Palette changes require a new ROM SHA and complete retest.

## Failure report

```text
ROM SHA-256:
Emulator or console / board:
Cartridge / firmware:
Power source:
Failure frequency:
Exact pose and controls:
Expected:
Observed:
Photo / video / trace:
Independent emulator comparison:
Relevant VRAM/HDMA/OAM diagnostics:
```
