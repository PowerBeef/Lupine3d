#!/usr/bin/env python3
"""Bind executed Sable release evidence to one exact ROM, without rerunning it.

The original B/P quality failure is retained alongside the owner's explicit
visual tradeoff. Safety, replay provenance and emulator checks must all pass.
Large raw motion evidence is stored with deterministic gzip compression.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil

import build_rom as br


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assemble(inputs: Path, output: Path, tests: Path) -> dict:
    rom, _, manifest = br.make_rom()
    sha = digest(rom)
    assert rom == (br.BUILD / 'lupine3d.gb').read_bytes()
    assert rom == br.make_rom()[0], 'nondeterministic rebuild'
    assert manifest['memory_budget']['resident_free_bytes'] >= 3000
    assert manifest['memory_budget']['fixed_code_end'] < 0x4000
    assert manifest['configuration']['display'] == 'slim'
    output.mkdir(parents=True, exist_ok=True)
    evidence = {}

    def collect(name, source, *, field=None, passed=True, compressed=False):
        raw = Path(source).read_bytes()
        data = json.loads(raw)
        if field:
            assert data[field] == sha, (source, 'different ROM')
        if passed:
            assert data.get('passed') is True, (source, 'failed evidence')
        target = output / 'evidence' / (name + ('.json.gz' if compressed else '.json'))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
        evidence[name] = dict(path=str(target.relative_to(output)),
                              sha256=digest(target.read_bytes()),
                              uncompressed_sha256=digest(raw))
        return data

    release = collect('release-checks', br.BUILD / 'verification_report.json', passed=False)
    assert release['rom']['sha256'] == sha and all(release['checks'].values())
    version = (br.ROOT / 'VERSION').read_text().strip()
    assert release['version'] == version and release['physical_hardware_tested'] is False
    collect('manifest', br.BUILD / 'build_manifest.json', field='sha256', passed=False)
    art = collect('art-checks', inputs / 'art-checks/checks.json', field='rom_sha256')
    assert all(art['checks'].values())
    collect('display', inputs / 'display/report.json')
    collect('atlas', br.BUILD / 'atlas_verification.json', passed=False)
    collect('static-geometry', br.BUILD / 'static_geometry/rendering_v3_results.json', passed=False)
    collect('geometry-tail', br.BUILD / 'q14_tail.json', passed=False)
    for name in ('sameboy_cgb0', 'sameboy_cgbe', 'mgba_cgb'):
        collect(name, br.BUILD / (name + '.json'), field='rom_sha256')
    scenes = collect('independent-scenes', br.BUILD / 'independent-witnesses/report.json', field='rom_sha256')
    assert len(scenes['scenes']) == 87
    assert all(core['passed'] and core['rgb_matches_host']
               for scene in scenes['scenes'] for core in scene['cores'].values())
    controller = collect('controller-restart', br.BUILD / 'playthrough/report.json', field='rom_sha256')
    assert controller['controller_only'] and controller['game_ram_injections'] == 0
    assert controller['restart_verified']
    replay = (br.BUILD / 'playthrough/controller_replay.bin').read_bytes()
    assert digest(replay) == controller['input_replay_sha256']
    (output / 'controller_replay.bin').write_bytes(replay)
    evidence['controller-replay'] = dict(path='controller_replay.bin', sha256=digest(replay))
    motion = collect('sustained-motion', inputs / 'sustained/motion_benchmark.json',
                     field='candidate_sha256', compressed=True)
    assert motion['requested_duration_seconds'] == 60 and len(motion['cases']) == 8
    timing = {}
    for name, result in motion['cases'].items():
        row = result['candidate']
        assert row['lcd_frame_counter_delta'] == 3584
        assert row['observation']['timing_reconciled']
        assert row['observation']['game_ram_writes_after_trial_start'] == 0
        assert row['input_queue_overflow'] == row['unsafe_gdma_starts'] == 0
        for window in row['motion_windows']:
            if name not in ('opening_door', 'turning'):
                assert window['unique_positions'] > 1, (name, 'stationary movement trial')
            if name in ('turning', 'walking_turning', 'moving_fire', 'two_actor_corner'):
                assert window['unique_angles'] > 1, (name, 'missing turn')
        timing[name] = dict(full_geometry_hz=row['full_geometry_updates_hz'],
                           full_frame_cycles=row['full_frame_cycles'],
                           input_replay_sha256=row['input_replay_sha256'])
    budget = collect('quality-budget', inputs / 'quality-budget.json', field='quality_sha256', passed=False)
    assert budget['quality_report_sha256'] == evidence['sustained-motion']['uncompressed_sha256']
    assert budget['default_enabled'] and budget['promotion_basis']
    collect('immutable-budget-inputs', br.ROOT / 'milestones/sable-v2/performance-inputs.json', passed=False)
    log = tests.read_text()
    match = re.search(r'Ran (\d+) tests in', log)
    assert match and int(match[1]) >= 140 and '\nOK\n' in log
    shutil.copyfile(tests, output / 'tests.log')
    evidence['tests'] = dict(path='tests.log', sha256=digest((output / 'tests.log').read_bytes()))
    report = dict(schema='lupine3d.sable-release.v1', version=version, passed=True,
                  rom_sha256=sha, configuration=manifest['configuration'],
                  configuration_id=manifest['configuration_id'],
                  qualification='emulator-qualified; archive extraction/rebuild is checked separately',
                  physical_hardware_tested=False, original_boot_rom_tested=False,
                  independent_scene_count=87, test_count=int(match[1]),
                  deterministic_rebuilds=2, memory=manifest['memory_budget'],
                  timing_unit='cpu_t_cycles', performance=timing,
                  target_full_geometry_hz=10,
                  target_met=all(r['full_geometry_hz'] >= 10 for n, r in timing.items() if n != 'opening_door'),
                  original_quality_budget_passed=budget['passed'],
                  visual_tradeoff_accepted=True, acceptance_basis=budget['promotion_basis'],
                  evidence=evidence)
    (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'Bound {len(evidence)} evidence files to {sha}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=br.BUILD / 'v08')
    parser.add_argument('--output-dir', type=Path, default=br.BUILD / 'rendering_qualification')
    parser.add_argument('--tests', type=Path, default=br.BUILD / 'v08/tests.log')
    args = parser.parse_args()
    assemble(args.inputs, args.output_dir, args.tests)


if __name__ == '__main__':
    main()
