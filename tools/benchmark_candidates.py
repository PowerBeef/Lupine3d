#!/usr/bin/env python3
"""Isolated exact-performance experiments; no candidate is promoted by this tool."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from lupine3d_v4.configuration import FLAGS

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = {
    "strips": {},
    "certificate": {"INCREMENTAL_CERTIFICATE": "1"},
    "camera": {"CAMERA_SETUP": "1"},
    "cache": {"DYNAMIC_TILE_CACHE": "1"},
    "cache-mixed": {"DYNAMIC_TILE_CACHE": "1", "CACHE_KEY_MIX": "1"},
    "no-cache": {"CAMERA_SETUP": "1", "ATTRIBUTE_PADDING": "1", "NARROW_YIELDS": "1"},
    "padding": {"ATTRIBUTE_PADDING": "1"},
    "yields": {"NARROW_YIELDS": "1"},
    "combined": {"CAMERA_SETUP": "1", "DYNAMIC_TILE_CACHE": "1", "ATTRIBUTE_PADDING": "1", "NARROW_YIELDS": "1"},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", choices=CANDIDATES)
    parser.add_argument("--output-dir",type=Path,default=ROOT/"build/experiments/isolated")
    parser.add_argument("--baseline-rom",type=Path,required=True)
    parser.add_argument("--baseline-symbols",type=Path,required=True)
    parser.add_argument("--baseline-report",type=Path)
    parser.add_argument("--duration",type=float)
    args = parser.parse_args()
    results = {}
    for name in args.candidate or CANDIDATES:
        output = args.output_dir/name; output.mkdir(parents=True,exist_ok=True)
        env = {k:v for k,v in os.environ.items() if not k.startswith("LUPINE3D_")}
        env.update({"LUPINE3D_"+flag:"0" for flag in FLAGS.values()})
        env["LUPINE3D_PROJECTION_STORAGE"]="direct"
        env.update({"LUPINE3D_COMPACT_STRIPS":"1",**{"LUPINE3D_"+k:v for k,v in CANDIDATES[name].items()}})
        print(f"Isolated experiment: {name}",flush=True)
        commands = [
            ["tools/build_rom.py","--output-dir",str(output)],
            ["tools/benchmark_runtime.py","--baseline-rom",str(args.baseline_rom),
             "--baseline-symbols",str(args.baseline_symbols),"--output",str(output/"frozen.json")],
            ["tools/benchmark_motion.py","--scenario","walking","--scenario","turning",
             "--scenario","walking_turning","--scenario","moving_fire","--output-dir",str(output)],
        ]
        if args.baseline_report: commands[1] += ["--baseline-report",str(args.baseline_report)]
        if args.duration: commands[2] += ["--duration",str(args.duration)]
        with (output/"run.log").open("w") as log:
            for command in commands:
                subprocess.run([sys.executable,*command],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        manifest = json.loads((output/"build_manifest.json").read_text())
        frozen = json.loads((output/"frozen.json").read_text())
        motion = json.loads((output/"motion_benchmark.json").read_text())
        results[name] = dict(flags=manifest["configuration"],sha256=manifest["sha256"],
                             configuration_id=manifest["configuration_id"],memory=manifest["memory_budget"],
                             frozen=frozen["cycles"],cast=frozen["cast_cycles"],
                             motion={n:case["candidate"]["full_frame_cycles"] for n,case in motion["cases"].items()},
                             default_promotion="not evaluated")
        (args.output_dir/"summary.json").write_text(json.dumps(results,indent=2)+"\n")
    print(json.dumps(results,indent=2))


if __name__ == "__main__": main()
