#!/usr/bin/env python3
"""Build and Pareto-test Lupine 3D's byte-exact boundary-tile cache.

The cache is an optimization only: a miss falls through to the exact dynamic
compositor. Pareto mode emits real candidate assets, builds the real 4 MiB
ROM, and drives the 27-update coherence tour for every candidate. Final pixels
remain invariant while VRAM cost and SM83 cycles can be traded.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "research")]

import build_rom as br  # noqa: E402
import geometry_v2_lab as geometry  # noqa: E402

ASSETS = ROOT / "assets"
RESULT = ROOT / "research" / "results" / "tile_atlas_v4.json"
PARETO_RESULT = ROOT / "research" / "results" / "tile_atlas_pareto_v5.json"
ATLAS_TILE_BASE = br.WALL_TILE_BASE + len(br.STATIC_WALL_MASKS)
MAX_PATTERNS = 240 - ATLAS_TILE_BASE
MAX_SIGNATURES = 255
ASSET_NAMES = (
    "tile_atlas_tiles.bin",
    "tile_atlas_bucket_start.bin",
    "tile_atlas_bucket_count.bin",
    "tile_atlas_entries.bin",
)


@dataclass(frozen=True)
class Corpus:
    signature_counts: collections.Counter[bytes]
    signature_tiles: dict[bytes, bytes]
    view_signatures: tuple[tuple[bytes, ...], ...]
    instances: int
    views: int
    elapsed_seconds: float


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


def collect_corpus() -> Corpus:
    signature_counts: collections.Counter[bytes] = collections.Counter()
    signature_tiles: dict[bytes, bytes] = {}
    view_signatures: list[tuple[bytes, ...]] = []
    total_instances = 0
    started = time.monotonic()
    for x_q8, y_q8 in geometry.corpus_positions():
        for angle in range(0, 256, 4):
            tops, styles, *_ = br.reference_pixel_descriptor_view(x_q8, y_q8, angle)
            signatures: list[bytes] = []
            for signature, tile in dynamic_tiles(tops, styles):
                previous = signature_tiles.setdefault(signature, tile)
                if previous != tile:
                    raise AssertionError("signature does not uniquely identify exact tile bytes")
                signature_counts[signature] += 1
                signatures.append(signature)
                total_instances += 1
            view_signatures.append(tuple(signatures))
    return Corpus(
        signature_counts=signature_counts,
        signature_tiles=signature_tiles,
        view_signatures=tuple(view_signatures),
        instances=total_instances,
        views=len(view_signatures),
        elapsed_seconds=time.monotonic() - started,
    )


def select_signatures(corpus: Corpus, max_patterns: int,
                      max_signatures: int = MAX_SIGNATURES) -> tuple[list[bytes], list[bytes]]:
    if not 0 <= max_patterns <= MAX_PATTERNS:
        raise ValueError(f"pattern count must be between 0 and {MAX_PATTERNS}")
    selected_signatures: list[bytes] = []
    selected_patterns: list[bytes] = []
    selected_pattern_set: set[bytes] = set()
    for signature, _count in corpus.signature_counts.most_common():
        tile = corpus.signature_tiles[signature]
        if tile not in selected_pattern_set and len(selected_patterns) >= max_patterns:
            continue
        if tile not in selected_pattern_set:
            selected_pattern_set.add(tile)
            selected_patterns.append(tile)
        selected_signatures.append(signature)
        if len(selected_signatures) == max_signatures:
            break
    return selected_signatures, selected_patterns


def make_payloads(corpus: Corpus, max_patterns: int,
                  max_signatures: int = MAX_SIGNATURES) -> tuple[dict[str, bytes], dict[str, object]]:
    signatures, patterns = select_signatures(corpus, max_patterns, max_signatures)
    pattern_ids = {tile: ATLAS_TILE_BASE + index for index, tile in enumerate(patterns)}
    buckets: list[list[bytes]] = [[] for _ in range(256)]
    for signature in signatures:
        buckets[signature_hash(signature)].append(signature)
    for bucket in buckets:
        bucket.sort(key=corpus.signature_counts.__getitem__, reverse=True)

    starts = bytearray()
    counts = bytearray()
    entries = bytearray()
    ordered: list[bytes] = []
    for bucket in buckets:
        starts.append(len(ordered))
        counts.append(len(bucket))
        for signature in bucket:
            ordered.append(signature)
            entries.extend(signature)
            entries.append(pattern_ids[corpus.signature_tiles[signature]])

    selected = set(signatures)
    misses = [sum(signature not in selected for signature in view) for view in corpus.view_signatures]
    covered = corpus.instances - sum(misses)
    payloads = {
        "tile_atlas_tiles.bin": b"".join(patterns),
        "tile_atlas_bucket_start.bin": bytes(starts),
        "tile_atlas_bucket_count.bin": bytes(counts),
        "tile_atlas_entries.bin": bytes(entries),
    }
    result: dict[str, object] = {
        "atlas_patterns": len(patterns),
        "vram_tile_ids": len(patterns),
        "freed_tile_ids": MAX_PATTERNS - len(patterns),
        "signature_entries": len(signatures),
        "covered_instances": covered,
        "coverage_pct": 100.0 * covered / corpus.instances,
        "corpus_mean_dynamic_tiles": statistics.fmean(misses),
        "corpus_max_dynamic_tiles": max(misses),
        "corpus_overflow_views": sum(count > br.DYNAMIC_TILE_CAPACITY for count in misses),
        "max_bucket_entries": max(map(len, buckets)),
        "asset_bytes": sum(map(len, payloads.values())),
        "assets": {
            name: {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in payloads.items()
        },
    }
    return payloads, result


def write_payloads(payloads: dict[str, bytes], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ASSET_NAMES:
        (output_dir / name).write_bytes(payloads[name])


def measure_candidate(payloads: dict[str, bytes]) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="lupine-atlas-") as temporary:
        candidate = Path(temporary)
        write_payloads(payloads, candidate)
        process = subprocess.run(
            [sys.executable, str(ROOT / "research" / "measure_atlas_candidate.py"), str(candidate)],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        return json.loads(process.stdout)


def base_report(corpus: Corpus) -> dict[str, object]:
    return {
        "corpus_views": corpus.views,
        "dynamic_tile_instances": corpus.instances,
        "unique_signatures": len(corpus.signature_counts),
        "atlas_tile_base": ATLAS_TILE_BASE,
        "available_atlas_tile_ids": MAX_PATTERNS,
        "elapsed_seconds": corpus.elapsed_seconds,
    }


def generate(max_patterns: int = MAX_PATTERNS, *, output_dir: Path = ASSETS,
             result_path: Path = RESULT, measure_cycles: bool = False) -> dict[str, object]:
    corpus = collect_corpus()
    payloads, candidate = make_payloads(corpus, max_patterns)
    if measure_cycles:
        candidate["driven_route"] = measure_candidate(payloads)
    write_payloads(payloads, output_dir)
    result = {**base_report(corpus), **candidate}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def pareto(pattern_counts: list[int], *, measure_cycles: bool = True) -> dict[str, object]:
    corpus = collect_corpus()
    candidates: list[dict[str, object]] = []
    for count in sorted(set(pattern_counts)):
        payloads, candidate = make_payloads(corpus, count)
        if measure_cycles:
            candidate["driven_route"] = measure_candidate(payloads)
        candidates.append(candidate)
        print(json.dumps(candidate), flush=True)
    report = {
        **base_report(corpus),
        "correctness_contract": "all atlas hits are byte-exact; every miss uses the unchanged exact compositor",
        "candidates": candidates,
    }
    PARETO_RESULT.parent.mkdir(parents=True, exist_ok=True)
    PARETO_RESULT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def parse_counts(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pareto", action="store_true", help="benchmark cache sizes without changing production assets")
    parser.add_argument("--pattern-counts", type=parse_counts, default=[0, 32, 64, 80, 96, 121])
    parser.add_argument("--apply-patterns", type=int, help="replace production assets with this pattern budget")
    parser.add_argument("--no-cycle-measure", action="store_true", help="skip emitted-ROM route measurements")
    args = parser.parse_args()
    if args.pareto:
        result = pareto(args.pattern_counts, measure_cycles=not args.no_cycle_measure)
    else:
        count = MAX_PATTERNS if args.apply_patterns is None else args.apply_patterns
        result = generate(count, measure_cycles=not args.no_cycle_measure)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
