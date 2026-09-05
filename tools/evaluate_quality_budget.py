#!/usr/bin/env python3
"""Apply the agreed per-scenario mean/p95 Q <= (B + P) / 2 budget exactly."""
import argparse
import hashlib
import json
from pathlib import Path


def lane(report,name,which):
    result = report["cases"][name][which]
    if not report.get("schema","").startswith("lupine3d.motion.v2"):
        raise ValueError("A versioned LCD-replay report is required")
    observation = result["observation"]
    if observation["timing_unit"] != "cpu_t_cycles" or not observation["timing_reconciled"]:
        raise ValueError("Unreconciled or incompatible timing")
    if observation["game_ram_writes_after_trial_start"]:
        raise ValueError("Diagnostic writes occurred during the trial")
    return result


def evaluate(baseline,performance,quality,baseline_lane="baseline"):
    rows = {}
    if set(baseline["cases"]) != set(performance["cases"]) or set(performance["cases"]) != set(quality["cases"]):
        raise ValueError("Scenario coverage must match; missing cases cannot pass")
    for name in baseline["cases"]:
        b,p,q = lane(baseline,name,baseline_lane),lane(performance,name,"candidate"),lane(quality,name,"candidate")
        if len({r["input_replay_sha256"] for r in (b,p,q)}) != 1:
            raise ValueError(f"Controller replays differ for {name}")
        if len({r["lcd_frame_counter_delta"] for r in (b,p,q)}) != 1:
            raise ValueError(f"Trial lengths differ for {name}")
        metrics = {}
        for metric in ("mean","p95"):
            values = [r["full_frame_cycles"][metric] for r in (b,p,q)]
            if any(v is None for v in values):
                raise ValueError(f"No full geometry timing available: {name}/{metric}")
            old,fast,new = values
            limit = (old+fast)/2
            metrics[metric] = dict(baseline=old,performance=fast,quality=new,limit=limit,
                                   remaining_cycles=limit-new,passed=new <= limit)
        rows[name] = dict(metrics=metrics,passed=all(v["passed"] for v in metrics.values()),
                          input_replay_sha256=b["input_replay_sha256"],
                          sample_counts={k:r["full_frame_cycles"]["count"] for k,r in (("baseline",b),("performance",p),("quality",q))},
                          full_geometry_hz=q["full_geometry_updates_hz"],
                          ten_hz_target_reached=q["full_geometry_updates_hz"] >= 10)
    return dict(schema="lupine3d.quality-budget.v1",timing_unit="cpu_t_cycles",formula="Q <= (B + P) / 2",
                baseline_sha256=baseline[baseline_lane+"_sha256"],performance_sha256=performance["candidate_sha256"],
                quality_sha256=quality["candidate_sha256"],cases=rows,
                passed=all(row["passed"] for row in rows.values()),
                scope="Timing budget only; correctness, resource, visual and publication gates remain separate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline",type=Path,required=True)
    parser.add_argument("--baseline-lane",choices=("baseline","candidate"),default="baseline")
    parser.add_argument("--performance",type=Path,required=True)
    parser.add_argument("--quality",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--scenario",action="append",help="Explicit partial gate; cannot qualify a production configuration")
    args = parser.parse_args()
    paths = (args.baseline,args.performance,args.quality)
    inputs=[json.loads(p.read_text()) for p in paths]
    if args.scenario:
        for data in inputs:
            if any(name not in data['cases'] for name in args.scenario):parser.error('Selected scenario missing from a report')
            data['cases']={name:data['cases'][name] for name in args.scenario}
    report = evaluate(*inputs,baseline_lane=args.baseline_lane)
    report['partial_gate']=bool(args.scenario)
    report['eligible_for_promotion']=report['passed'] and not report['partial_gate']
    report["report_sha256"] = {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in zip(("baseline","performance","quality"),paths)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__": main()
