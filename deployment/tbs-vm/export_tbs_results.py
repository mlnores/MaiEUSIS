#!/usr/bin/env python3
"""Validate a completed TBS pilot on its original runtime and export report inputs.

The original run is read only. Full SQLite stores stay on the server; normalised
calibration profiles and public task inputs are exported for independent checks.
"""
import argparse
import copy
import hashlib
import io
import json
import sqlite3
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def calibration_payload(report, database):
    sessions = [c['session_id'] for c in report['calibrations'] if c['task'] == 'TBS']
    check(len(sessions) == 1, 'Expected one TBS calibration per job')
    session = sessions[0]
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT body FROM sessions WHERE id=?', (session,)).fetchone()
    check(row is not None, 'Missing actual calibration session')
    body = json.loads(row[0])
    profile = copy.deepcopy(body['profile'])
    evidence = profile['policy'].get('evidence', [])
    prefix = session + '_trial_'
    check(all(e.startswith(prefix) for e in evidence), 'Unexpected calibration evidence scope')
    if evidence:
        profile['policy']['evidence'] = [int(e[len(prefix):]) for e in evidence]
    inputs = []
    for event in body['events']:
        value = copy.deepcopy(event['input'])
        if value['kind'] not in {'evaluation', 'feedback'}:
            continue
        check(value['trial_id'] == prefix + str(value['index']), 'Unexpected calibration trial ID')
        value['trial_id'] = value['index']
        inputs.append(value)
    evaluations = [e for e in inputs if e['kind'] == 'evaluation']
    feedback = [e for e in inputs if e['kind'] == 'feedback']
    indices = list(range(1, 193))
    check([e['index'] for e in evaluations] == indices and
          [e['index'] for e in feedback] == indices, 'Incomplete or reordered calibration')
    samples = sum(not e['timed_out'] for e in feedback)
    check(profile['policy']['samples'] == samples and len(evidence) == samples,
          'Calibration sample count differs')
    signature = {'profile_sha256': fingerprint(profile), 'inputs_sha256': fingerprint(inputs),
                 'completed_trials': len(feedback), 'samples': samples}
    return {'profile': profile, 'inputs': inputs, 'signature': signature}


def export(project, root, output):
    project = project.resolve()
    root = root.resolve()
    output = output.resolve()
    check(not output.is_relative_to(root), 'Write the export outside the frozen pilot directory')
    status = read(root / 'status.json')
    analysis = read(root / 'analysis.json')
    check(status['status'] == 'complete' and not status['active_jobs'] and not status['failures']
          and status.get('error') is None, 'The runner has not completed cleanly')
    check(analysis['complete'] and analysis['execution_complete'] and analysis['control_checks_passed'],
          'Analysis is incomplete or failed controls')
    check((analysis['completed_jobs'], analysis['total_jobs'], len(analysis['participants'])) == (144, 144, 16),
          'Expected the complete 144-job, 16-actor TBS pilot')

    sys.path.insert(0, str(project / 'scripts'))
    sys.path.insert(0, str(project))
    import tbs_receptiveness_sweep as sweep

    # This verifies the original Python/package/source fingerprints. It must run
    # on the VM's original .venv, not by changing manifests to suit another host.
    manifest, audit, actors, levels = sweep.prepare(root, verify_controls=True)
    check(analysis['manifest_sha256'] == manifest['sha256'], 'Analysis belongs to another manifest')
    check(set(levels) == {'0.25', '0.5', '0.75'}, 'Unexpected receptiveness levels')
    expected = {(r['participant'], r['repeat']): r for r in audit['expected']}
    check(len(expected) == 48, 'Expected 48 independent baseline trajectories')
    actors_by_id = {a['id']: a for a in actors}
    sums = {}
    seen = set()
    calibrations = {}
    count = trials = 0
    prefix = root.name
    temporary = output.with_name(output.name + '.part')
    output.parent.mkdir(parents=True, exist_ok=True)
    analysis_bytes = (root / 'analysis.json').read_bytes()

    try:
        with tarfile.open(temporary, 'w:gz') as archive:
            def add_bytes(name, data):
                check(name not in seen, 'Duplicate export member: ' + name)
                seen.add(name)
                info = tarfile.TarInfo(prefix + '/' + name)
                info.size = len(data)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(data))
                sums[name] = digest(data)

            def add_file(path, name=None):
                add_bytes(name or path.relative_to(root).as_posix(), path.read_bytes())

            for pattern in ('*.json', '*.md', '*.log', '*.txt'):
                for path in sorted(root.glob(pattern)):
                    if path.is_file():
                        add_file(path)

            for level, entry in levels.items():
                directory = entry['directory']
                check(len(entry['results']) == 48, 'Missing completed jobs at level ' + level)
                for name in ('manifest.json', 'participants.json'):
                    add_file(directory / name)
                for record in entry['results']:
                    case = record['case']
                    key = (case['participant'], case['repeat'])
                    sweep.verify_result(record, expected[key])
                    report_path = (directory / record['report_file']).resolve()
                    check(report_path.is_relative_to(directory.resolve()), 'Report path escapes its level')
                    check(digest(report_path.read_bytes()) == record['report_sha256'], 'Evaluator checksum differs')
                    report = read(report_path)
                    spec = copy.deepcopy(actors_by_id[case['participant']])
                    spec['response_parameters'] = {'TBS': {
                        style: dict(entry['manifest']['configuration']['response_parameters'])
                        for style in ('direct', 'socratic')}}
                    check(report['participants'] == [spec], 'Evaluator actor/response inputs differ')
                    replay = sweep.verify_report(report, spec, expected[key])
                    trials += replay['trial_choices_outcomes_and_distributions']
                    payload = calibration_payload(report, report_path.parent / 'sessions.sqlite3')
                    check(payload['signature'] == record['calibration'], 'Actual calibration differs from committed signature')
                    if key in calibrations:
                        check(calibrations[key] == payload['signature'], 'Calibration differs across levels')
                    calibrations[key] = payload['signature']
                    add_file(directory / 'jobs' / record['job_id'] / 'result.json')
                    add_file(report_path)
                    add_bytes((report_path.parent / 'calibration-inputs.json').relative_to(root).as_posix(),
                              (json.dumps(payload, indent=2, allow_nan=False) + '\n').encode())
                    for name in ('progress.json', 'worker.log'):
                        path = report_path.parent / name
                        if path.is_file():
                            add_file(path)
                    count += 1
                    if count % 24 == 0:
                        print(f'Validated and exported {count}/144 jobs', flush=True)

            check(count == 144 and trials == 138240 and len(calibrations) == 48,
                  'Incomplete numerical replay/calibration audit')
            check(analysis['baseline_checks_passed'] == 144 and
                  analysis['calibration_cross_level_checks'] == 96 and
                  analysis['independent_baseline_trajectories'] == 48, 'Unexpected analysis control counts')
            check((root / 'analysis.json').read_bytes() == analysis_bytes, 'Source analysis changed during export')
            implementation = next(iter(levels.values()))['manifest']['implementation']
            for name, expected_sha in implementation['files'].items():
                path = project / 'socratic_prototype' / name
                check(digest(path.read_bytes()) == expected_sha, 'Runtime source changed: ' + name)
                add_file(path, 'provenance/source/socratic_prototype/' + name)
            for name, expected_sha in manifest['implementation'].items():
                path = project / 'scripts' / name
                check(digest(path.read_bytes()) == expected_sha, 'Coordinator source changed: ' + name)
                add_file(path, 'provenance/source/scripts/' + name)
            add_file(Path(__file__).resolve(), 'provenance/export_tbs_results.py')
            for name in ('environment-linux.freeze.txt', 'preflight.log', 'bundle-metadata.json',
                         'SHA256SUMS', 'requirements-vm.txt'):
                path = project / name
                if path.is_file():
                    add_file(path, 'provenance/' + name)
            exported_audit = {
                'exported_at_utc': datetime.now(timezone.utc).isoformat(),
                'source_run': str(root), 'manifest_sha256': manifest['sha256'],
                'analysis_sha256': digest(analysis_bytes), 'verified': True,
                'completed_jobs': count, 'comparison_trials_numerically_replayed': trials,
                'independent_baseline_trajectories': len(expected),
                'actual_calibrations_read_from_sqlite': count, 'calibration_cross_level_checks': 96,
                'original_runtime_fingerprints_verified': True,
                'scope': 'Numerical actor/choice/outcome/metric replay and actual calibration signatures; graph reasoning and SHACL were not rerun.',
                'omitted': 'Full SQLite stores and uncommitted attempts remain on the VM.'}
            add_bytes('export_audit.json', (json.dumps(exported_audit, indent=2) + '\n').encode())
            checksum_data = ''.join(f'{value}  {name}\n' for name, value in sorted(sums.items())).encode()
            info = tarfile.TarInfo(prefix + '/EXPORT_SHA256SUMS')
            info.size = len(checksum_data)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(checksum_data))
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    hasher = hashlib.sha256()
    with output.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(chunk)
    checksum = output.with_name(output.name + '.sha256')
    checksum.write_text(f'{hasher.hexdigest()}  {output.name}\n')
    print(f'Export ready: {output} ({output.stat().st_size / 1024**2:.1f} MiB)', flush=True)
    print(f'Checksum file: {checksum}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, default=Path.cwd())
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--output', type=Path, default=Path.home() / 'tbs-results-for-report.tar.gz')
    args = parser.parse_args()
    project = args.project_dir.resolve()
    root = args.run_dir or Path((project / '.tbs-output').read_text().strip())
    export(project, root, args.output)


if __name__ == '__main__':
    main()
