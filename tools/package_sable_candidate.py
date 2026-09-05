#!/usr/bin/env python3
"""Package a local Sable development build and its ROM-bound evidence.

This does not publish, create a release, change VERSION, or claim hardware
qualification. The historical command name remains for local tooling.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from package_release import ROOT, TOP_LEVEL_FILES, TOP_LEVEL_DIRS, include_path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    build = ROOT / 'build'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path, default=build/'steel-hud')
    args = parser.parse_args()
    evidence = args.evidence_dir
    rom = build / 'lupine3d.gb'
    digest = sha(rom)
    required = ((evidence/'checks/checks.json', 'rom_sha256'),
                (evidence/'independent/report.json', 'rom_sha256'),
                (evidence/'playthrough/report.json', 'rom_sha256'))
    for path, key in required:
        report = json.loads(path.read_text())
        assert report[key] == digest and report['passed'], (path, key)
    timing_path = evidence/'quality-budget.json'
    if timing_path.exists():
        timing = json.loads(timing_path.read_text())
        assert timing['quality_sha256'] == digest
        timing_files = ('quality-budget.json', 'sustained/motion_benchmark.json')
    else:
        timing_path = evidence/'performance/motion_benchmark.json'
        timing = json.loads(timing_path.read_text())
        assert timing['candidate_sha256'] == digest and timing['passed']
        timing_files = ('performance/motion_benchmark.json', 'comparison/report.json')
    sources = [(ROOT/name, Path(name)) for name in TOP_LEVEL_FILES]
    for name in TOP_LEVEL_DIRS:
        for path in sorted((ROOT/name).rglob('*')):
            relative = path.relative_to(ROOT)
            if path.is_file() and not path.is_symlink() and include_path(relative):
                sources.append((path, relative))
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('LUPINE3D_')}
    with tempfile.TemporaryDirectory(prefix='sable-development-') as directory:
        stage = Path(directory)
        for source, relative in sources:
            target = stage/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        subprocess.run([sys.executable, 'tools/build_rom.py'], cwd=stage,
                       env=env, check=True)
        assert (stage/'build/lupine3d.gb').read_bytes() == rom.read_bytes()
        legacy = dict(env, LUPINE3D_DISPLAY='legacy', LUPINE3D_ART='legacy',
                      LUPINE3D_ART_ANIMATION='0')
        subprocess.run([sys.executable, 'tools/build_rom.py'], cwd=stage,
                       env=legacy, check=True)
        assert sha(stage/'build/lupine3d.gb') == '48c80fcd588365a38eb08c7ce1cc4ce2439c432127e4f389651b8e0bdafe2e99'
    entries = list(sources)
    for name in ('lupine3d.gb', 'lupine3d.sym', 'lupine3d.lst', 'build_manifest.json'):
        entries.append((build/name, Path('development')/name))
    for folder in ('checks', 'display', 'cores', 'motion', 'independent', 'playtest', 'world', 'art', 'playthrough'):
        for path in sorted((evidence/folder).rglob('*')):
            if path.is_file() and path.suffix in ('.json', '.png', '.gif'):
                entries.append((path, Path('development/evidence')/path.relative_to(evidence)))
    for name in timing_files:
        entries.append((evidence/name, Path('development/evidence')/name))
    manifest = dict(schema='sable.development-package.v2', rom_sha256=digest,
                    default_enabled=True, published_release=False,
                    physical_hardware_tested=False,
                    clean_source_legacy_and_default_rebuilds_exact=True,
                    timing_report_schema=timing['schema'],
                    files={str(relative): sha(source) for source, relative in entries})
    output = ROOT/'dist'
    output.mkdir(exist_ok=True)
    archive = output/f'SableOutpost-development-{digest[:12]}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for source, relative in sorted(entries, key=lambda row: str(row[1])):
            info = zipfile.ZipInfo('SableOutpost-development/'+relative.as_posix(), (1980,1,1,0,0,0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, source.read_bytes())
        info = zipfile.ZipInfo('SableOutpost-development/DEVELOPMENT_MANIFEST.json', (1980,1,1,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, json.dumps(manifest, indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:
        for relative, expected in manifest['files'].items():
            assert hashlib.sha256(z.read('SableOutpost-development/'+relative)).hexdigest() == expected
    report = {key: value for key, value in manifest.items() if key != 'files'}
    report.update(archive=str(archive.relative_to(ROOT)), archive_sha256=sha(archive), file_count=len(entries))
    (evidence/'package-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
