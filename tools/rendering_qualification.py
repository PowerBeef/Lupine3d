#!/usr/bin/env python3
"""Assemble ROM-bound rendering evidence after running the documented lanes.

This consumes results; it does not replace their execution. A failed quality
budget is retained as a disabled experiment, never converted to a passing gate.
"""
import hashlib
import json
from pathlib import Path
import shutil

import build_rom as br
from archive_baseline import BASELINE_COMMIT, BASELINE_SHA256


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble():
    root, build = br.ROOT, br.BUILD
    output = build / "rendering_qualification"
    output.mkdir(parents=True, exist_ok=True)
    evidence = {}

    def collect(name, relative, *, expected_rom=None, hash_field="rom_sha256", require_pass=True):
        source = root / relative
        data = json.loads(source.read_text())
        if expected_rom is not None:
            assert data[hash_field] == expected_rom, (relative, "wrong ROM")
        if require_pass:
            assert data.get("passed") is True, (relative, "failed evidence")
        destination = output / "evidence" / (name + ".json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        evidence[name] = dict(path=str(destination.relative_to(output)),
                              source=str(relative), sha256=digest(destination))
        return data

    manifest = json.loads((build / "build_manifest.json").read_text())
    sha = digest(build / "lupine3d.gb")
    assert sha == manifest["sha256"]
    first, _, _ = br.make_rom()
    second, _, _ = br.make_rom()
    assert first == second == (build / "lupine3d.gb").read_bytes()
    assert manifest["configuration"]["reprojection"] is False
    assert manifest["memory_budget"]["resident_free_bytes"] >= 3000
    assert manifest["memory_budget"]["fixed_code_end"] < 0x4000
    verification = json.loads((build / "verification_report.json").read_text())
    assert verification["rom"]["sha256"] == sha and all(verification["checks"].values())
    collect("release-checks", "build/verification_report.json", require_pass=False)
    collect("production-manifest", "build/build_manifest.json", require_pass=False)
    baseline = collect("baseline-motion", ".render-baselines/strips-sustained-v2.json",
                       expected_rom=BASELINE_SHA256, hash_field="baseline_sha256")
    performance = collect("performance-motion", "build/experiments/performance-sustained/motion_benchmark.json",
                          expected_rom=sha, hash_field="candidate_sha256")
    frozen = collect("performance-frozen", "build/experiments/refined/no-cache/frozen.json",
                     expected_rom=sha, hash_field="candidate_sha256")
    assert frozen["scene_count"] == 53
    scenes = collect("performance-independent", "build/independent-performance-witnesses/report.json", expected_rom=sha)
    assert len(scenes["scenes"]) == 51
    for name in ("sameboy_cgb0", "sameboy_cgbe", "mgba_cgb"):
        collect(name, f"build/{name}.json", expected_rom=sha)
    for name, expected in (("baseline", BASELINE_SHA256), ("performance", sha)):
        completion = collect(name + "-completion-restart", f"build/{name}-controller-restart/report.json", expected_rom=expected)
        assert completion["controller_only"] and completion["game_ram_injections"] == 0
        assert completion["restart_verified"]
        replay = build / (name + "-controller-restart") / "controller_replay.bin"
        assert digest(replay) == completion["input_replay_sha256"]
        target = output / (name + "-completion-replay.bin")
        shutil.copyfile(replay, target)
        evidence[name + "-completion-replay"] = dict(path=target.name, source=str(replay.relative_to(root)), sha256=digest(target))

    lanes = {name: (baseline["cases"][name]["baseline"], result["candidate"])
             for name, result in performance["cases"].items()}
    for name, folder in (("two_actor_corner", "contention-visible"), ("opening_door", "door-interaction-sustained")):
        data = collect(name, f"build/experiments/{folder}/motion_benchmark.json", expected_rom=sha, hash_field="candidate_sha256")
        assert data["baseline_sha256"] == BASELINE_SHA256
        lanes[name] = (data["cases"][name]["baseline"], data["cases"][name]["candidate"])
    timing = {}
    for name, (old, new) in lanes.items():
        assert old["input_replay_sha256"] == new["input_replay_sha256"]
        assert old["lcd_frame_counter_delta"] == new["lcd_frame_counter_delta"] == 3584
        for lane in (old, new):
            observation = lane["observation"]
            assert observation["timing_reconciled"] and observation["game_ram_writes_after_trial_start"] == 0
            assert lane["input_queue_overflow"] == lane["unsafe_gdma_starts"] == 0
        timing[name] = dict(baseline=old["full_frame_cycles"], performance=new["full_frame_cycles"],
                            full_geometry_hz=new["full_geometry_updates_hz"],
                            improvement_percent=100 * (1 - new["full_frame_cycles"]["mean"] / old["full_frame_cycles"]["mean"]),
                            input_replay_sha256=new["input_replay_sha256"])

    rejected = {}
    for name in ("quality-final", "near-field-sustained", "foreground-final"):
        budget = collect(name + "-budget", f"build/experiments/{name}/budget.json", require_pass=False)
        assert budget["performance_sha256"] == sha and not budget["passed"]
        data = collect(name + "-motion", f"build/experiments/{name}/motion_benchmark.json",
                       expected_rom=budget["quality_sha256"], hash_field="candidate_sha256")
        rejected[name] = dict(rom_sha256=budget["quality_sha256"], enabled=False,
                              reason="mean/p95 half-gains gate failed", cases=list(budget["cases"]),
                              partial_gate=budget["partial_gate"])
        if name == "foreground-final":
            feedback = data["cases"]["moving_fire"]["candidate"]["observation"]["feedback_latency"]
            rejected[name]["feedback"] = {k:v for k,v in feedback.items() if k != "samples"}
    for name, folder in (("quality", "independent-quality-witnesses"), ("near-field", "independent-near-witnesses")):
        data = collect(name + "-independent", f"build/{folder}/report.json")
        assert len(data["scenes"]) == 51
        expected = rejected["quality-final" if name == "quality" else "near-field-sustained"]["rom_sha256"]
        assert data["rom_sha256"] == expected

    references = {}
    for name in ("scalar-reference", "unfolded-reference", "packets-reference", "paged-reference", "hybrid-reference", "foreground-final"):
        folder = build / "experiments" / name
        metadata = collect(name + "-manifest", str((folder / "build_manifest.json").relative_to(root)), require_pass=False)
        reference_sha = metadata["sha256"]
        assert digest(folder / "lupine3d.gb") == reference_sha
        for core in ("sameboy-cgb0", "sameboy-cgbe", "mgba"):
            data = collect(name + "-" + core, str((folder / (core + ".json")).relative_to(root)), expected_rom=reference_sha)
            if name == "foreground-final":
                assert data["foreground_publications"] > 0 and data["mixed_world_oam"] == 0
        references[name] = dict(rom_sha256=reference_sha, configuration=metadata["configuration"], independent_cores=3)

    for name, path in (("packets", "packets-frozen.json"), ("packets-reuse", "packets-reuse-frozen.json"),
                       ("paged256", "projection-paged256-frozen.json"), ("hybrid256", "projection-hybrid256-frozen.json")):
        data = collect(name + "-frozen", "build/experiments/" + path)
        rejected[name] = dict(rom_sha256=data["candidate_sha256"], enabled=False,
                              reason="exact frozen output; slower integrated frame time", cycles=data["cycles"])
    for name in ("certificate", "cache", "camera", "strips", "padding", "yields", "combined"):
        collect("isolated-" + name, f"build/experiments/isolated/{name}/frozen.json")
    collect("cache-mixed", "build/experiments/refined/cache-mixed/frozen.json")
    review = collect("quality-motion-review", "build/quality-motion-review/report.json", require_pass=False)
    assert review["before_rom_sha256"] == sha
    assert review["after_rom_sha256"] == rejected["quality-final"]["rom_sha256"]
    for path in (build / "quality-motion-review").glob("*.gif"):
        target = output / path.name
        shutil.copyfile(path, target)
        evidence[path.stem + "-motion"] = dict(path=target.name, source=str(path.relative_to(root)), sha256=digest(target))
    log = build / "final-tests.log"
    assert "\nOK\n" in log.read_text()
    shutil.copyfile(log, output / "tests.log")
    evidence["tests"] = dict(path="tests.log", source="build/final-tests.log", sha256=digest(log))
    report = dict(schema="lupine3d.rendering-qualification.v1", passed=True,
                  rom_sha256=sha, baseline_commit=BASELINE_COMMIT, baseline_sha256=BASELINE_SHA256,
                  configuration=manifest["configuration"], configuration_id=manifest["configuration_id"],
                  timing_unit="cpu_t_cycles", performance=timing, target_full_geometry_hz=10,
                  target_met=all(row["full_geometry_hz"] >= 10 for name,row in timing.items() if name != "opening_door"),
                  deterministic_rebuilds=2, memory=manifest["memory_budget"],
                  references=references, rejected_experiments=rejected, evidence=evidence,
                  qualification="emulator-qualified; clean-room package evidence is separate",
                  physical_hardware_tested=False)
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Bound {len(evidence)} evidence files to production ROM {sha}")
    return report


if __name__ == "__main__":
    assemble()
