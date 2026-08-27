#!/usr/bin/env python3
"""Generate the exact-signature v0.4.0 boundary-tile atlas.

The emitted assets contain only byte-exact patterns produced by the reference
compositor.  Runtime lookup verifies all ten signature bytes, so the hash is
never part of the correctness contract.
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "research")]

import build_rom as br  # noqa: E402
import geometry_v2_lab as geometry  # noqa: E402

ASSETS = ROOT / "assets"
RESULT = ROOT / "research" / "results" / "tile_atlas_v4.json"
ATLAS_TILE_BASE = br.WALL_TILE_BASE + len(br.STATIC_WALL_MASKS)
MAX_PATTERNS = 240 - ATLAS_TILE_BASE
MAX_SIGNATURES = 255


def signature_hash(signature: bytes) -> int:
    value = 0
    for code in signature:
        value = ((value << 1) | (value >> 7)) & 0xFF
        value ^= code
    return value


def tile_signature_and_bytes(tops: list[int], styles: list[int], y0: int) -> tuple[bytes, bytes]:
    dark_mask = sum((style & 1) << (7 - pixel) for pixel, style in enumerate(styles))
    signature = bytearray((y0, dark_mask, *tops))
    tile = bytearray(16)
    for pixel, (top, style) in enumerate(zip(tops, styles)):
        state = br.reference_strip_state(top, y0)
        mask = 0x80 >> pixel
        for row in range(8):
            region = br.microstrip_region(state, row)
            color = 0 if region == "ceiling" else 1 if region == "floor" else br.wall_color(style, pixel, row)
            top_edge = 3 <= state <= 10 and row == state - 3
            bottom_edge = 11 <= state <= 18 and row == state - 11
            if region == "wall" and (top_edge or bottom_edge):
                color = 3
            if color & 1:
                tile[row * 2] |= mask
            if color & 2:
                tile[row * 2 + 1] |= mask
    return bytes(signature), bytes(tile)


def dynamic_tiles(tops: list[int], styles: list[int]):
    seam_lookup = br.make_seam_tile_lookup()
    for tile_col in range(20):
        first = tile_col * 8
        col_tops = tops[first:first + 8]
        col_styles = styles[first:first + 8]
        min_top, max_top = min(col_tops), max(col_tops)
        dark_mask = sum((style & 1) << (7 - pixel) for pixel, style in enumerate(col_styles))
        static_wall_tile = seam_lookup[dark_mask]
        for tile_row in range(12):
            y0 = tile_row * 8
            if y0 + 7 < min_top or y0 >= 96 - min_top:
                continue
            if y0 >= max_top and y0 + 7 < 96 - max_top and static_wall_tile:
                continue
            yield tile_signature_and_bytes(col_tops, col_styles, y0)


def generate() -> dict[str, object]:
    signature_counts: collections.Counter[bytes] = collections.Counter()
    signature_tiles: dict[bytes, bytes] = {}
    total_instances = 0
    views = 0
    started = time.monotonic()

    for x_q8, y_q8 in geometry.corpus_positions():
        for angle in range(0, 256, 4):
            tops, styles, *_ = br.reference_pixel_descriptor_view(x_q8, y_q8, angle)
            for signature, tile in dynamic_tiles(tops, styles):
                previous = signature_tiles.setdefault(signature, tile)
                if previous != tile:
                    raise AssertionError("signature does not uniquely identify exact tile bytes")
                signature_counts[signature] += 1
                total_instances += 1
            views += 1

    selected_signatures: list[bytes] = []
    selected_patterns: list[bytes] = []
    selected_pattern_set: set[bytes] = set()
    for signature, _count in signature_counts.most_common():
        tile = signature_tiles[signature]
        if tile not in selected_pattern_set and len(selected_patterns) >= MAX_PATTERNS:
            continue
        if tile not in selected_pattern_set:
            selected_pattern_set.add(tile)
            selected_patterns.append(tile)
        selected_signatures.append(signature)
        if len(selected_signatures) == MAX_SIGNATURES:
            break

    pattern_ids = {tile: ATLAS_TILE_BASE + index for index, tile in enumerate(selected_patterns)}
    buckets: list[list[bytes]] = [[] for _ in range(256)]
    for signature in selected_signatures:
        buckets[signature_hash(signature)].append(signature)
    for bucket in buckets:
        bucket.sort(key=signature_counts.__getitem__, reverse=True)

    starts = bytearray()
    counts = bytearray()
    entries = bytearray()
    ordered_signatures: list[bytes] = []
    for bucket in buckets:
        starts.append(len(ordered_signatures))
        counts.append(len(bucket))
        for signature in bucket:
            ordered_signatures.append(signature)
            entries.extend(signature)
            entries.append(pattern_ids[signature_tiles[signature]])

    atlas_tiles = b"".join(selected_patterns)
    covered_instances = sum(signature_counts[signature] for signature in selected_signatures)
    payloads = {
        "tile_atlas_tiles.bin": atlas_tiles,
        "tile_atlas_bucket_start.bin": bytes(starts),
        "tile_atlas_bucket_count.bin": bytes(counts),
        "tile_atlas_entries.bin": bytes(entries),
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (ASSETS / name).write_bytes(payload)

    result: dict[str, object] = {
        "corpus_views": views,
        "dynamic_tile_instances": total_instances,
        "unique_signatures": len(signature_counts),
        "atlas_tile_base": ATLAS_TILE_BASE,
        "atlas_patterns": len(selected_patterns),
        "signature_entries": len(selected_signatures),
        "covered_instances": covered_instances,
        "coverage_pct": 100.0 * covered_instances / total_instances,
        "max_bucket_entries": max(map(len, buckets)),
        "elapsed_seconds": time.monotonic() - started,
        "assets": {
            name: {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in payloads.items()
        },
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
