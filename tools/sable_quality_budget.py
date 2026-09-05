#!/usr/bin/env python3
"""Assemble the immutable pre-viewport B/P lanes, then apply the original gate."""
import argparse
import hashlib
import json
from pathlib import Path
from evaluate_quality_budget import evaluate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,default=Path('milestones/sable-v2/performance-inputs.json'))
    p.add_argument('--quality',type=Path,default=Path('build/hud24/sustained/motion_benchmark.json'))
    p.add_argument('--output',type=Path,default=Path('build/hud24/quality-budget.json'));args=p.parse_args()
    inputs=json.loads(args.inputs.read_text())
    if inputs['schema']!='sable.quality-inputs.v1':raise ValueError('unsupported baseline summary')
    b=inputs['baseline'];perf=inputs['performance'];source=inputs['source_report_sha256']
    assert b['baseline_sha256']=='8f0425f07220d7649ff419c9c3fb0a212c4a234b40463ab431c1f97e1b7b3cd3'
    assert perf['candidate_sha256']=='48c80fcd588365a38eb08c7ce1cc4ce2439c432127e4f389651b8e0bdafe2e99'
    q=json.loads(args.quality.read_text());result=evaluate(b,perf,q)
    result.update(eligible_for_promotion=result['passed'],default_enabled=True,
                  promotion_basis='Owner explicitly accepted the art and enlarged-viewport performance tradeoff; the mathematical gate is unchanged',original_report_sha256=source,
                  quality_report_sha256=hashlib.sha256(args.quality.read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)

if __name__=='__main__':main()
