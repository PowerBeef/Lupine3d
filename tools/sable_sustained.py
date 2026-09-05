#!/usr/bin/env python3
"""Run independent deterministic 60-second scenarios concurrently on the host.

Only emulated CPU T-cycles enter reports. Host wall time and host contention
are never performance measurements. Each worker owns its emulator and output.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
import sys
import build_rom as b
from benchmark_motion import EXTENDED_CASES


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=4);p.add_argument('--output-dir',type=Path,default=b.BUILD/'sable-v2/sustained');args=p.parse_args()
    if not 1<=args.workers<=8:p.error('workers must be between 1 and 8')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    def run(name):
        folder=args.output_dir/name;folder.mkdir(exist_ok=True)
        with (folder/'run.log').open('w') as log:
            subprocess.run([sys.executable,str(b.ROOT/'tools/benchmark_motion.py'),'--duration','60','--scenario',name,'--output-dir',str(folder)],stdout=log,stderr=subprocess.STDOUT,check=True)
        return name,json.loads((folder/'motion_benchmark.json').read_text())
    reports={}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(run,name):name for name in EXTENDED_CASES}
        for future in as_completed(futures):
            name,report=future.result();reports[name]=report;print('Completed '+name,flush=True)
    merged=dict(reports[EXTENDED_CASES[0]]);merged['cases']={}
    for name in EXTENDED_CASES:
        report=reports[name]
        for key in ('candidate_sha256','configuration_id','timing_unit','requested_duration_seconds'):
            assert report[key]==merged[key],(key,name)
        merged['cases'].update(report['cases'])
    merged['host_execution']='independent emulators; up to '+str(args.workers)+' concurrent scenarios'
    (args.output_dir/'motion_benchmark.json').write_text(json.dumps(merged,indent=2)+'\n')

if __name__=='__main__':main()
