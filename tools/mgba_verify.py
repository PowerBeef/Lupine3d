"""Build the mGBA adapter and bind all independent evidence to a ROM hash."""
import argparse
import hashlib
import json
import subprocess
import shlex
import sys
from pathlib import Path
from PIL import Image
import build_rom as br
from sm83emu import CGB

PINNED_CORE = "507061afd70489a0c2ffc8ba26d8f9b53d6cf7d6"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--rom",type=Path,default=br.BUILD/"lupine3d.gb")
    parser.add_argument("--output-dir",type=Path,default=br.BUILD)
    args=parser.parse_args();core=args.core.resolve()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=core, text=True).strip()
    if revision != PINNED_CORE:
        raise SystemExit(f"expected mGBA {PINNED_CORE}, got {revision}")
    executable = br.BUILD / "mgba_smoke"
    # mCore's public ABI contains conditional members. Consume the exact
    # compiled library defines: LIBMGBA_ONLY's generated flags.h alone omits
    # ENABLE_DIRECTORIES in this pinned revision and would shift the ABI.
    flags = (core / "build/CMakeFiles/mgba.dir/flags.make").read_text()
    defines = shlex.split(next(line.partition("=")[2] for line in flags.splitlines() if line.startswith("C_DEFINES =")))
    if not all(flag.startswith("-D") for flag in defines): raise SystemExit("unexpected compiler defines")
    # The macOS core uses CoreFoundation to locate its portable configuration.
    platform_libs = ["-framework", "CoreFoundation"] if sys.platform == "darwin" else []
    subprocess.run(["cc", *defines, f"-I{core / 'include'}", f"-I{core / 'build/include'}",
                    str(br.ROOT / "tools/mgba_smoke.c"), str(core / "build/libmgba.a"), "-lm", "-lpthread", *platform_libs, "-o", str(executable)], check=True)
    executable.with_suffix(".provenance.json").write_text(json.dumps(dict(core="mGBA",core_commit=revision,
        adapter_sha256=hashlib.sha256(executable.read_bytes()).hexdigest()),indent=2)+"\n")
    rom, asm, _ = br.make_rom()
    if args.rom.read_bytes() != rom:
        raise SystemExit("ROM does not match active source/configuration")
    prefix = args.output_dir / "mgba_cgb"
    result = subprocess.run([str(executable), str(args.rom), str(prefix)], capture_output=True, text=True)
    if result.stderr: print(result.stderr)
    if not result.stdout.strip():
        raise SystemExit(f"mGBA adapter exited {result.returncode} without a report")
    report = json.loads(result.stdout.strip().splitlines()[-1])
    host = CGB(rom, asm.labels); host.run(until_pc=asm.labels["main_loop"])
    report.update(core="mGBA", core_commit=revision, rom_sha256=hashlib.sha256(rom).hexdigest(),
                  physical_hardware_tested=False, original_boot_rom_tested=False,
                  startup_rgb_matches_host=Image.open(str(prefix) + "_start.ppm").tobytes() == host.render_screen().tobytes())
    if br.SABLE_ART or br.COMPACT_DISPLAY:
        from independent_startup import frozen_startup
        report['startup_rgb_matches_host']=frozen_startup(executable,args.rom,args.output_dir/'mgba_frozen')
        report['startup_rgb_scope']='separate frozen snapshot; controller smoke remains unpatched'
    report["passed"] = report["passed"] and report["startup_rgb_matches_host"]
    prefix.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    for path in args.output_dir.glob("mgba_cgb_*.ppm"): Image.open(path).save(path.with_suffix(".png"))
    print(json.dumps(report, indent=2))
    result.check_returncode()
    if not report["passed"]: raise SystemExit("independent mGBA validation failed")


if __name__ == "__main__": main()
