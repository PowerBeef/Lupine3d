#!/usr/bin/env python3
"""Compile the smoke adapter and bind independent evidence to this ROM SHA."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image
import build_rom as br
from sm83emu import CGB

PINNED_CORE = "213a12ce93d66b105a113debd9396306066a7cfc"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    args = parser.parse_args()
    core = args.core.resolve()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=core, text=True).strip()
    if revision != PINNED_CORE:
        raise SystemExit(f"expected pinned SameBoy {PINNED_CORE}, got {revision}")
    executable = br.BUILD / "sameboy_smoke"
    subprocess.run(["cc", f"-I{core}", str(br.ROOT / "tools/sameboy_smoke.c"),
                    str(core / "build/lib/libsameboy.a"), "-lm", "-ldl", "-o", str(executable)], check=True)
    executable.with_suffix(".provenance.json").write_text(json.dumps(dict(core="SameBoy",core_commit=revision,
        adapter_sha256=hashlib.sha256(executable.read_bytes()).hexdigest()),indent=2)+"\n")
    rom = br.BUILD / "lupine3d.gb"
    sha = hashlib.sha256(rom.read_bytes()).hexdigest()
    expected_rom, asm, _ = br.make_rom()
    if hashlib.sha256(expected_rom).hexdigest() != sha:
        raise SystemExit("ROM differs from active build configuration")
    host = CGB(expected_rom, asm.labels)
    host.run(until_pc=asm.labels["main_loop"], max_steps=2_000_000)
    expected_pixels = host.render_screen().tobytes()
    for name, model in (("cgbe", "205"), ("cgb0", "200")):
        prefix = br.BUILD / f"sameboy_{name}"
        result = subprocess.run([str(executable), str(rom), str(prefix), model], text=True, capture_output=True)
        if result.stderr:
            print(result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        report.update(rom_sha256=sha, core="SameBoy", core_commit=revision,
                      physical_hardware_tested=False, original_boot_rom_tested=False,
                      color_conversion="linear RGB15, channel*255//31",
                      startup_rgb_matches_host=Image.open(str(prefix) + "_start.ppm").tobytes() == expected_pixels)
        report["passed"] = report["passed"] and report["startup_rgb_matches_host"]
        prefix.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        for capture in br.BUILD.glob(f"sameboy_{name}_*.ppm"):
            Image.open(capture).save(capture.with_suffix(".png"))
        print(json.dumps(report))
        result.check_returncode()
        if not report["passed"]:
            raise SystemExit("independent startup RGB differs from host")


if __name__ == "__main__":
    main()
