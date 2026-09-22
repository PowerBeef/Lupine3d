# Lupine 3D v0.2.2 — Material and Shading Redesign

## Objective

Remove the full-width horizontal wall bands that visually joined unrelated surfaces, overpowered wall silhouettes, and produced a shimmering or “trippy” presentation during movement—without changing the exact geometry, VRAM publication protocol, cartridge layout, or measured update cadence.

This is a presentation redesign built directly on the frozen v0.2.0 geometry renderer. The exact signed-error DDA, camera tables, adaptive spans, wall descriptors, dynamic-tile capacity, and one-VBlank hidden-page commit are unchanged.

## Diagnosis

The v0.2.0 material function depended only on the row inside an 8×8 tile. Every wall pixel on the same screen row therefore received the same colour. When the tile repeated, a one- or two-row material accent became a continuous line across every visible wall, even when those rays belonged to different planes, depths, and map cells.

That caused three perception failures:

1. **Texture overruled silhouette.** The eye followed the horizontal bands before it followed the wall boundaries.
2. **Different planes appeared connected.** Matching stripe phases made separate faces read as one ribbon-like surface.
3. **Motion amplified aliasing.** Quantized wall heights moved beneath a stationary high-contrast screen-space pattern.

The geometry itself was not the problem. The material vocabulary was fighting it.

## Redesign rules

### 1. Silhouette first

The ordinary wall is deliberately flat. Its shape and exact wall-side lighting carry the depth information. Texture detail is reserved for secondary materials.

### 2. No full-width contrast bands

A row may be uniformly filled with its material’s base colour because that is visually flat. A complete row may never switch to the contrasting wall colour. This rule is enforced by the builder and an automated regression test.

### 3. Native two-pixel authoring

The compositor works with four two-pixel strips per 8×8 tile. Materials are therefore authored as an **8-row × 4-pair** matrix rather than as arbitrary per-pixel art. Static wall tiles and generated edge tiles consume the same pattern source, so wall interiors and silhouettes remain byte-consistent.

### 4. Exact-side lighting, not decorative striping

Styles 0/1 and 2/3 remain X/Y orientation variants selected from the actual DDA crossing axis. Light and shadow faces use different average luminance, making corners and adjacent surfaces readable without screen-wide pattern cues.

### 5. Lower palette contrast

The two wall colours retain a warm copper/terracotta identity, but the shadow colour is raised from the very dark v0.2.0 brown. This preserves directional separation while reducing visual vibration on the CGB-sized image.

### 6. Zero runtime tax

All patterns are still precomputed into the existing static tile set and 6,080-byte edge-microstrip library. The DDA, descriptor count, dynamic tile count, DMA payload, and runtime instruction paths are unchanged.

## Implemented material set

### Material 1 — Warm plaster

**Styles:** 0 light/front, 1 shadow/side  
**Role:** primary world surface

The material is completely flat in each orientation:

- light face: colour index 2;
- shadow face: colour index 3.

This is intentional. It gives the wall silhouette maximum authority and creates a clean visual baseline for the rest of the scene.

### Material 2 — Vertical service panel

**Styles:** 2 light/front, 3 shadow/side  
**Role:** technology, machinery, structural walls

The material uses a vertical frame plus sparse rivets. Its strongest feature runs vertically, so it reinforces face orientation instead of joining walls across the screen. The light variant is mostly colour 2 with a dark structural edge; the shadow variant is mostly colour 3 with a narrow lit rim.

### Material 3 — Reinforced door

**Style:** 4  
**Role:** interaction point

The door uses a bright plate with a dark vertical spine and asymmetric fasteners. It is visually distinct from both ordinary plaster and service panels while avoiding horizontal rails.

## Source representation

```python
WALL_PATTERNS[style][row][pair]
```

Dimensions:

```text
5 runtime styles × 8 rows × 4 two-pixel pairs
```

The lookup function is:

```python
wall_color(style, pair, y)
```

Static tiles call it with `pair = x // 2`. Dynamic microstrips already know their pair position and use the same lookup. The host compositor model uses the same function, preserving byte-exact ROM-versus-reference verification.

## Palette change

Viewport palette 0 remains:

| Index | Purpose | v0.2.2 RGB5 |
|---:|---|---:|
| 0 | ceiling | `(2, 4, 10)` |
| 1 | floor | `(7, 8, 11)` |
| 2 | wall midtone | `(26, 17, 8)` |
| 3 | wall structural shadow | `(16, 9, 5)` |

The HUD continues using palette 1 and is unchanged.

## Files changed

- `tools/build_rom.py`
  - replaced row-only `wall_color(style, y)` with pair-aware pattern tables;
  - added pattern validation and material metadata;
  - updated the viewport wall palette;
  - advanced the cartridge version byte to `$02`.
- `tests/test_engine.py`
  - added a low-noise material regression gate;
  - updated the expected cartridge version byte.
- `tools/release_check.py`
  - made release verification version-aware;
  - records material names, pattern resolution, and the zero-band gate.
- `tools/make_preview.py`
  - updated preview labels for v0.2.2.

## Verification result

Software verification completed successfully:

- **22 automated tests pass**;
- 32 KiB CGB-only ROM builds deterministically;
- engine body remains **17,530 bytes**, ending at `$45CA`;
- `cast_all` remains **378,628 modeled cycles** at the starting pose;
- `render_view` remains **435,288 modeled cycles**;
- stationary cadence remains **10.123 updates/s** in the project harness;
- scripted movement cadence remains **9.955 updates/s**;
- **243,840** integer DDA comparisons retain zero hit mismatches;
- **3,048** corpus views retain zero dynamic-tile overflows;
- maximum commit remains **1,920 bytes / 120 blocks**;
- the material gate reports **zero full-width contrasting bands**.

These are mathematical and project-harness results. Original Game Boy Color validation is still pending.

## Acceptance criteria for future materials

Any new wall material must satisfy all of the following:

1. No full-width row may use the non-base wall colour.
2. Light and shadow orientation variants must retain ordered average luminance.
3. Static tiles and dynamic edge tiles must derive from one shared pattern source.
4. No geometry descriptor, face key, wall top, cast count, or map identity may change.
5. Dynamic-tile and one-VBlank publication limits must remain unchanged.
6. The complete test, research, preview, and clean-room package gates must pass.
7. Final palettes must be inspected on an original reflective CGB LCD before hardware certification.

## Follow-on visual work

The next safe presentation experiments are deliberately separated from this release:

- per-face texture phase derived from stable wall identity;
- distance-based material simplification with hysteresis;
- palette-authored bevel/coverage pixels in a certified edge atlas;
- a fourth map material after face-key format and adaptive-style validation are explicitly extended;
- entity occlusion using CGB BG priority and colour-index-zero transparency behaviour.

None of those are required to solve the v0.2.0 banding problem. v0.2.2 fixes it at the material source with no runtime or geometry regression.
