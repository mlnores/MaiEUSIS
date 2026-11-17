#!/usr/bin/env python3
"""Audit the VM export and reconstruct TBS report data without altering it."""
import argparse
import copy
import hashlib
import json
import math
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from statistics import mean, stdev

PROFILES = ('MAB-specialised', 'TBS-specialised', 'Dual-regime', 'Low-expression')
LEVELS = (.25, .5, .75)
CONDITIONS = ('C', 'E', 'D', 'F')
ALL_CONDITIONS = ('A', 'C', 'E', 'D', 'F')
FLOAT_CHECKS = {'different_float_values': 0, 'max_absolute_difference': 0.0}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def manifest(path):
    data = read(path)
    check(fingerprint({k: v for k, v in data.items() if k != 'sha256'}) == data['sha256'], 'Manifest checksum differs')
    return data


def sign_counts(values):
    return dict(better=sum(v > 0 for v in values), same=sum(v == 0 for v in values), worse=sum(v < 0 for v in values))


def numeric_match(actual, saved, label):
    """Cross-platform replay tolerance; integer observations and choices stay exact."""
    if isinstance(actual, dict):
        check(isinstance(saved, dict) and actual.keys() == saved.keys(), 'Replay keys differ: ' + label)
        for key in actual:
            numeric_match(actual[key], saved[key], label + '.' + str(key))
    elif isinstance(actual, (list, tuple)):
        check(isinstance(saved, (list, tuple)) and len(actual) == len(saved), 'Replay length differs: ' + label)
        for i, (x, y) in enumerate(zip(actual, saved)):
            numeric_match(x, y, label + '[' + str(i) + ']')
    elif isinstance(actual, float) or isinstance(saved, float):
        check(isinstance(actual, (int, float)) and isinstance(saved, (int, float)) and
              math.isclose(actual, saved, rel_tol=1e-12, abs_tol=1e-12), 'Replay numeric value differs: ' + label)
        if actual != saved:
            FLOAT_CHECKS['different_float_values'] += 1
            FLOAT_CHECKS['max_absolute_difference'] = max(FLOAT_CHECKS['max_absolute_difference'], abs(actual - saved))
    else:
        check(actual == saved, 'Replay discrete value differs: ' + label)


def replay_report(frozen, report, spec, expected):
    check(len(report['runs']) == 5 and {r['condition'] for r in report['runs']} == set(ALL_CONDITIONS),
          'Wrong replay condition grid')
    for run in report['runs']:
        check(run['task'] == 'TBS' and run['completed'] and len(run['trials']) == 192 and
              run['environment_seed'] == expected['environment_seed'], 'Incomplete or unmatched replay')
        model = frozen.Participant(spec, 'TBS', 'responsive')
        env = frozen.Environment('TBS', 'full', run['environment_seed'])
        for i, trial in enumerate(run['trials'], 1):
            check(trial['index'] == i, 'Reordered trial')
            ev = env.evaluation(run['session_id'], i)
            base, probabilities, effect = model.distribution(ev, trial['intervention'])
            numeric_match(base, trial['baseline_probabilities'], 'baseline probability')
            numeric_match(probabilities, trial['assisted_probabilities'], 'assisted probability')
            numeric_match(effect, trial['effect'], 'response effect')
            choice = frozen.select(probabilities, frozen.uniform(env.seed, 'choice', i))
            if frozen.uniform(env.seed, 'omission', i) < effect['omission_probability']:
                choice = 'NO_RESPONSE'
            feedback = env.outcome(ev, choice)
            model.observe(ev, feedback)
            check(choice == trial['choice'] and feedback['outcome'] == trial['outcome'],
                  'Discrete choice/outcome differs on cross-platform replay')
        check(env.done, 'Incomplete replay environment')
        numeric_match(env.metrics(), run['metrics'], 'task metrics')
    return 5 * 192


def audit(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    check(not output.is_relative_to(root), 'Keep derived report outputs outside the imported frozen run')
    original_hash = sha(root / 'analysis.json')
    verified_files = 0
    for line in (root / 'EXPORT_SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (root / name).resolve()
        check(path.is_relative_to(root) and sha(path) == expected, 'Export checksum differs: ' + name)
        verified_files += 1
    a = read(root / 'analysis.json')
    m = manifest(root / 'manifest.json')
    status, exported = read(root / 'status.json'), read(root / 'export_audit.json')
    check(a['complete'] and a['execution_complete'] and a['control_checks_passed'], 'Incomplete or failed analysis')
    check((a['completed_jobs'], a['total_jobs']) == (144, 144), 'Wrong job count')
    check(status['status'] == 'complete' and not status['failures'] and not status['active_jobs'] and status['error'] is None,
          'Unclean runner completion')
    check(a['manifest_sha256'] == exported['manifest_sha256'] == m['sha256'] and
          exported['analysis_sha256'] == original_hash and exported['verified'], 'Export audit refers to other inputs')

    source = root / 'provenance/source'
    sys.path[:0] = [str(source), str(source / 'scripts')]
    import tbs_receptiveness_sweep as frozen
    levels = {}
    actors = None
    implementation = None
    for text, item in m['levels'].items():
        directory = root / item['directory']
        lm = manifest(directory / 'manifest.json')
        check(lm['sha256'] == item['manifest_sha256'], 'Level manifest differs')
        people = read(directory / 'participants.json')
        check(fingerprint(people) == lm['actors_sha256'], 'Frozen actors differ')
        if actors is None:
            actors, implementation = people, lm['implementation']
        check(people == actors and lm['implementation'] == implementation, 'Level actors or implementations differ')
        levels[text] = directory, lm
    check(set(levels) == {'0.25', '0.5', '0.75'}, 'Wrong receptiveness grid')
    check(len(actors) == 16 and Counter(p['original_profile'] for p in actors) == {p: 4 for p in PROFILES}, 'Wrong cohort')
    check(implementation['files'] == frozen.pilot.implementation()['files'], 'Replay source snapshot differs')
    for name, expected in m['implementation'].items():
        check(sha(source / 'scripts' / name) == expected, 'Frozen coordinator differs')
    source_config = levels['0.25'][1]['configuration']
    baseline_audit = read(root / 'baseline_audit.json')
    expected = {(r['participant'], r['repeat']): r for r in baseline_audit['expected']}
    check(len(expected) == 48, 'Wrong independent baseline count')
    baseline_distribution_hash_differences = 0
    for actor in actors:
        for repeat in range(3):
            actual = frozen.baseline_rollout(actor, source_config['seed'], repeat, 'full')
            saved = expected[actor['id'], repeat]
            for field in ('trajectory_sha256', 'primary_value', 'score', 'targets_attained', 'blocks_completed', 'trials', 'omissions'):
                check(actual[field] == saved[field], 'Discrete independent baseline differs: ' + field)
            baseline_distribution_hash_differences += actual['distribution_sha256'] != saved['distribution_sha256']
            check(actual['environment_seed'] == expected[actor['id'], repeat]['environment_seed'], 'Baseline stream differs')
    print('Export checksums, frozen sources and 48 independent baselines verified.', flush=True)

    index, calibration_index, rows, job_stats = {}, {}, [], []
    pairs = {name: {'pairs': 0, 'trajectory_identical': 0, 'probabilities_identical': 0,
                    'prompt_count_identical': 0, 'all_records_identical': 0} for name in ('C_E', 'D_F')}
    count = replayed = baseline_checks = 0
    actor_index = {p['id']: p for p in actors}
    for text, (directory, lm) in levels.items():
        result_paths = sorted((directory / 'jobs').glob('*/result.json'))
        check(len(result_paths) == 48, 'Missing completed level jobs')
        for path in result_paths:
            record = read(path)
            case = record['case']
            key = case['participant'], case['repeat']
            check(record['manifest_sha256'] == lm['sha256'], 'Job manifest differs')
            frozen.verify_result(record, expected[key])
            report_path = directory / record['report_file']
            check(sha(report_path) == record['report_sha256'], 'Evaluator report differs')
            report = read(report_path)
            spec = copy.deepcopy(actor_index[key[0]])
            spec['response_parameters'] = {'TBS': {s: dict(lm['configuration']['response_parameters']) for s in ('direct', 'socratic')}}
            check(report['participants'] == [spec], 'Actor input differs')
            replayed += replay_report(frozen, report, spec, expected[key])
            saved = {r['condition']: r for r in record['rows']}
            for run in report['runs']:
                condition, trials = run['condition'], run['trials']
                s = saved[condition]
                check(fingerprint([(t['index'], t['choice'], t['outcome']) for t in trials]) == s['trajectory_sha256'],
                      'Trajectory summary differs')
                check(fingerprint([t['assisted_probabilities'] for t in trials]) == s['distribution_sha256'],
                      'Distribution summary differs')
                targets = run['metrics']['targets_attained']
                active = sum(t['intervention'] is not None for t in trials)
                omissions = sum(t['choice'] == 'NO_RESPONSE' for t in trials)
                check(targets == s['targets_attained'] and run['metrics']['score'] == s['score'] and
                      len(run['metrics']['blocks']) == s['blocks_completed'] == 24 and
                      active == s['active_interventions'] and omissions == s['omissions'], 'Trial metrics differ')
                check(s['primary_value'] == targets / 24, 'Wrong primary units')
                idx = key[0], key[1], float(text), condition
                check(idx not in index, 'Duplicate matched session')
                row = {'participant': key[0], 'repeat': key[1], 'receptiveness': float(text), 'condition': condition,
                       'targets_attained': targets, 'target_rate': targets / 24, 'score': s['score'],
                       'interventions': active, 'omissions': omissions, 'trajectory_sha256': s['trajectory_sha256'],
                       'distribution_sha256': s['distribution_sha256']}
                rows.append(row)
                index[idx] = row
                baseline_checks += condition == 'A'
            cal = read(report_path.parent / 'calibration-inputs.json')
            signature = {'profile_sha256': fingerprint(cal['profile']), 'inputs_sha256': fingerprint(cal['inputs']),
                         'completed_trials': 192, 'samples': sum(e['kind'] == 'feedback' and not e['timed_out'] for e in cal['inputs'])}
            for kind in ('evaluation', 'feedback'):
                entries = [v for v in cal['inputs'] if v['kind'] == kind]
                check([v['index'] for v in entries] == list(range(1, 193)) and
                      all(v['trial_id'] == v['index'] for v in entries), 'Incomplete normalised calibration')
            check(signature == cal['signature'] == record['calibration'], 'Calibration signature differs')
            check(cal['profile']['policy']['samples'] == signature['samples'] == len(cal['profile']['policy']['evidence']),
                  'Calibration evidence count differs')
            if key in calibration_index:
                check(calibration_index[key] == signature, 'Cross-level calibration mismatch')
            calibration_index[key] = signature
            for left, right in (('C', 'E'), ('D', 'F')):
                p = pairs[left + '_' + right]
                x, y = saved[left], saved[right]
                p['pairs'] += 1
                p['trajectory_identical'] += x['trajectory_sha256'] == y['trajectory_sha256']
                p['probabilities_identical'] += x['distribution_sha256'] == y['distribution_sha256']
                p['prompt_count_identical'] += x['active_interventions'] == y['active_interventions']
                p['all_records_identical'] += all(x[k] == y[k] for k in
                    ('trajectory_sha256', 'distribution_sha256', 'primary_value', 'active_interventions', 'omissions'))
            job_stats.append({'participant': key[0], 'repeat': key[1], 'receptiveness': float(text),
                              'elapsed_seconds': record['elapsed_seconds'], 'max_rss_bytes': record['max_rss_bytes']})
            count += 1
            if count % 24 == 0:
                print(f'Comparison replay and calibration validation: {count}/144 jobs', flush=True)
    check(len(index) == 720 and replayed == 138240 and baseline_checks == 144 and len(calibration_index) == 48,
          'Incomplete matched data')
    expected_keys = {(p['id'], r, rho, c) for p in actors for r in range(3) for rho in LEVELS for c in ALL_CONDITIONS}
    check(set(index) == expected_keys, 'Wrong matched-session grid')

    individuals = []
    for actor in actors:
        p = actor['id']
        for rho in LEVELS:
            for condition in CONDITIONS:
                chosen = [index[p, r, rho, condition] for r in range(3)]
                base = [index[p, r, rho, 'A'] for r in range(3)]
                diffs = [x['targets_attained'] - b['targets_attained'] for x, b in zip(chosen, base)]
                deltas = [float(Fraction(v, 24)) for v in diffs]
                score_diffs = [x['score'] - b['score'] for x, b in zip(chosen, base)]
                primary = float(Fraction(sum(diffs), 72))
                individuals.append({'participant': p, 'profile': actor['original_profile'], 'condition': condition,
                    'receptiveness': rho, 'repetitions': 3, 'net_target_difference_total': sum(diffs),
                    'repetition_target_differences': diffs, 'repetition_deltas': deltas,
                    'mean_delta': primary, 'mean_delta_pp': 100 * primary,
                    'monte_carlo_se': stdev(deltas) / math.sqrt(3),
                    'mean_target_rate': float(Fraction(sum(v['targets_attained'] for v in chosen), 72)),
                    'baseline': float(Fraction(sum(v['targets_attained'] for v in base), 72)),
                    'mean_score': mean(v['score'] for v in chosen), 'baseline_score': mean(v['score'] for v in base),
                    'mean_score_delta': mean(score_diffs), 'repetition_score_deltas': score_diffs,
                    'mean_interventions': mean(v['interventions'] for v in chosen)})
    original = {(r['participant'], r['receptiveness'], r['condition']): r for r in a['individual_results']}
    corrections = []
    for row in individuals:
        old = original[row['participant'], row['receptiveness'], row['condition']]
        for field in ('mean_delta', 'mean_delta_pp', 'monte_carlo_se', 'mean_target_rate', 'baseline',
                      'mean_score', 'baseline_score', 'mean_score_delta', 'mean_interventions'):
            check(close(row[field], old[field]), 'Individual mean/uncertainty differs: ' + field)
        for field in ('repetition_deltas', 'repetition_score_deltas'):
            check(len(old[field]) == 3 and all(close(x, y) for x, y in zip(row[field], old[field])), 'Repetition summary differs')
        if row['net_target_difference_total'] == 0 and old['mean_delta'] != 0:
            corrections.append({'participant': row['participant'], 'condition': row['condition'],
                                'receptiveness': row['receptiveness'], 'frozen_mean_delta': old['mean_delta'],
                                'exact_net_target_difference': 0, 'report_classification': 'same'})
    check(len(original) == len(individuals) == 192, 'Incomplete individual summary grid')
    groups = []
    group_corrections = []
    for profile in (*PROFILES, 'all'):
        for rho in LEVELS:
            for condition in CONDITIONS:
                selected = [r for r in individuals if r['receptiveness'] == rho and r['condition'] == condition and
                            (profile == 'all' or r['profile'] == profile)]
                net = [r['net_target_difference_total'] for r in selected]
                value = float(Fraction(sum(net), 72 * len(net)))
                group = {'profile': profile, 'receptiveness': rho, 'condition': condition,
                         'participants': len(selected), 'repetitions': 3, 'mean_delta': value,
                         'mean_delta_pp': 100 * value, **sign_counts(net)}
                for field in ('mean_target_rate', 'baseline', 'mean_score', 'baseline_score', 'mean_score_delta', 'mean_interventions'):
                    group[field] = mean(r[field] for r in selected)
                old = next(g for g in a['groups'] if (g['profile'], g['receptiveness'], g['condition']) == (profile, rho, condition))
                check(old['participants'] == len(selected) == (16 if profile == 'all' else 4), 'Wrong group denominator')
                for field in ('mean_delta', 'mean_delta_pp', 'mean_target_rate', 'baseline', 'mean_score',
                              'baseline_score', 'mean_score_delta', 'mean_interventions'):
                    check(close(group[field], old[field]), 'Group average differs: ' + field)
                float_values = [original[r['participant'], rho, condition]['mean_delta'] for r in selected]
                check(all(old[k] == v for k, v in sign_counts(float_values).items()), 'Frozen sign counts do not reproduce')
                if any(old[k] != group[k] for k in ('better', 'same', 'worse')):
                    group_corrections.append({'profile': profile, 'receptiveness': rho, 'condition': condition,
                        'frozen': {k: old[k] for k in ('better', 'same', 'worse')},
                        'report': {k: group[k] for k in ('better', 'same', 'worse')}})
                groups.append(group)
    check(len(groups) == len(a['groups']) == 60, 'Wrong group grid')
    check(sha(root / 'analysis.json') == original_hash, 'Original analysis was modified')

    output.mkdir(parents=True, exist_ok=True)
    if (output / 'report_data.json').exists():
        check(read(output / 'report_data.json')['manifest_sha256'] == m['sha256'], 'Output belongs to another experiment')
    data = {'task': 'TBS', 'manifest_sha256': m['sha256'], 'original_analysis_sha256': original_hash,
            'complete': True, 'participants': [p['id'] for p in actors], 'individual_results': individuals,
            'groups': groups, 'jobs': job_stats, 'status': status,
            'primary_unit': 'percentage points of target attainment versus matched A',
            'secondary_unit': 'multiplied block-score points versus matched A',
            'tie_rule': 'The sign of the integer target-count difference summed over three repetitions; means divide by 72.'}
    write(output / 'report_data.json', data)
    write(output / 'report_trial_summaries.json', {'manifest_sha256': m['sha256'], 'rows': rows})
    audit_result = {'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'verified': True,
        'manifest_sha256': m['sha256'], 'analysis_sha256': original_hash,
        'report_data_sha256': sha(output / 'report_data.json'),
        'trial_summaries_sha256': sha(output / 'report_trial_summaries.json'),
        'export_files_verified': verified_files, 'completed_jobs': count, 'comparison_sessions': len(index),
        'trial_outcomes_and_probabilities_replayed': replayed, 'independent_baselines_regenerated': len(expected),
        'fresh_A_checks': baseline_checks, 'calibration_payloads_verified': count,
        'cross_level_calibration_checks': count - len(calibration_index),
        'individual_summaries_verified': len(individuals), 'group_summaries_verified': len(groups),
        'personalisation_pairs': pairs, 'exact_tie_corrections': corrections,
        'affected_group_count_cells': group_corrections, 'original_analysis_unchanged': True,
        'original_runtime': {'python': implementation['python'], 'packages': implementation['packages']},
        'local_replay_runtime': {'python': platform.python_version(), 'packages': {
            name: version(name) for name in implementation['packages']}},
        'audit_source_sha256': sha(__file__),
        'cross_platform_floating_checks': {**FLOAT_CHECKS, 'relative_tolerance': 1e-12, 'absolute_tolerance': 1e-12,
            'independent_baseline_probability_hashes_differing': baseline_distribution_hash_differences,
            'discrete_choices_outcomes_and_targets_match_exactly': True},
        'scope': 'Frozen VM source used for local numerical replay with explicit 1e-12 float tolerance across Linux/macOS; all discrete choices/outcomes/target counts match exactly. Summary arithmetic independently reconstructed from integer target counts. Exact original-runtime replay and SQLite reads were verified by the VM exporter. Local checks use its normalised calibration payloads. Graph inference/SHACL and language quality were not rerun.'}
    write(output / 'report_audit.json', audit_result)
    for src, dst in (('analysis.json', 'source_analysis.json'), ('manifest.json', 'source_manifest.json'),
                     ('export_audit.json', 'vm_export_audit.json'), ('status.json', 'source_status.json')):
        (output / dst).write_bytes((root / src).read_bytes())
    print(json.dumps({k: v for k, v in audit_result.items() if k not in
          ('exact_tie_corrections', 'affected_group_count_cells', 'original_runtime', 'local_replay_runtime')}, indent=2), flush=True)
    print(f'Exact ties corrected in the derived report: {len(corrections)} individual cells; source analysis preserved.', flush=True)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    audit(args.directory, args.output_dir)
