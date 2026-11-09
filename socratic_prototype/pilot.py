"""Frozen, resumable reconsideration sensitivity pilots; researcher-side only."""
import argparse
import copy
import fcntl
import hashlib
import importlib.metadata
import json
import os
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

from .agents import validate_participant
from .assistance_response import validate as validate_response
from .records import fields, identity, number, require
from .reconsideration import configuration as mechanism_configuration
from .simulation import run as simulate
from .study import validate_study
from .tasks import get_task

VERSION = 'reconsideration-pilot-0.1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


def implementation():
    root = Path(__file__).parent
    files = {}
    for path in sorted(root.rglob('*')):
        if 'data' in path.relative_to(root).parts or path.suffix not in {'.py', '.json', '.ttl', '.rq', '.sparql'}:
            continue
        files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    versions = {}
    for package in ('rdflib', 'pyshacl', 'pgmpy', 'numpy', 'scipy'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    import platform
    return {'files': files, 'python': platform.python_version(), 'packages': versions,
            'language': {'SOCRATIC_LLM': 'offline', 'SOCRATIC_LANGUAGE_MODE': 'bounded', 'SOCRATIC_INTERPRET_RESPONSES': '0'}}


def validate_config(config):
    fields(config, ['id', 'participants_file', 'expected_participants', 'cohort_split', 'study',
                    'mechanisms', 'response_parameters', 'seed', 'repeats', 'primary_outcomes'],
           ['source_ids', 'expected_profiles', 'max_trials'])
    require(identity(config['id']), 'Invalid pilot ID')
    require(isinstance(config['participants_file'], str) and bool(config['participants_file']), 'Pilot needs an actor export')
    require(type(config['expected_participants']) is int and config['expected_participants'] > 0, 'Invalid participant count')
    require(config['cohort_split'] in {'development', 'evaluation', 'all', 'engineering'}, 'Invalid cohort split')
    require(type(config['repeats']) is int and config['repeats'] > 0, 'Invalid repetition count')
    require(isinstance(config['seed'], str) and 0 < len(config['seed']) <= 100, 'Invalid pilot seed')
    mechanisms = config['mechanisms']
    require(isinstance(mechanisms, list) and len(mechanisms) == len(set(mechanisms)) and
            set(mechanisms) == {'none', 'current', 'recent'}, 'Pilot must retain all three reconsideration mechanisms')
    validate_response(config['response_parameters'])
    study = validate_study(config['study'], simulation=True)
    require(set(study['conditions']) == {'A', 'C', 'E', 'D', 'F'}, 'Pilot must include all five assistance conditions')
    outcomes = config['primary_outcomes']
    require(isinstance(outcomes, dict) and set(outcomes) == set(study['tasks']), 'Specify one primary outcome per task')
    for task, outcome in outcomes.items():
        fields(outcome, ['metric', 'divisor'])
        require(outcome['metric'] in study['execution'][task]['metrics'], 'Unknown primary outcome for ' + task)
        require(number(outcome['divisor']) and outcome['divisor'] > 0, 'Primary-outcome divisor must be positive')
        for mechanism in mechanisms:
            mechanism_configuration(get_task(task), mechanism)
    ids = config.get('source_ids', [])
    require(isinstance(ids, list) and len(ids) == len(set(ids)) and all(identity(x) for x in ids), 'Invalid source-ID selection')
    profiles = config.get('expected_profiles', {})
    require(isinstance(profiles, dict) and all(isinstance(k, str) and type(v) is int and v > 0 for k, v in profiles.items()), 'Invalid expected profile counts')
    cap = config.get('max_trials')
    require(cap is None or type(cap) is int and cap > 0, 'Invalid engineering trial cap')
    return copy.deepcopy(config), study


def select_actors(config, actors):
    require(isinstance(actors, list), 'Actor export must be a JSON array')
    selected_ids = set(config.get('source_ids', []))
    selected = [a for a in actors if not selected_ids or a.get('provenance', {}).get('source_id', a['id']) in selected_ids]
    found = {a.get('provenance', {}).get('source_id', a['id']) for a in selected}
    require(not selected_ids or found == selected_ids, 'Selected source IDs missing from actor export')
    require(len(selected) == config['expected_participants'] and len({a['id'] for a in selected}) == len(selected), 'Actor count or identities differ from pilot specification')
    for actor in selected:
        validate_participant(actor, config['study']['tasks'])
        if config['cohort_split'] in {'development', 'evaluation'}:
            require(actor.get('provenance', {}).get('split') == config['cohort_split'], 'Actor belongs to a different cohort split')
    profiles = config.get('expected_profiles')
    require(not profiles or dict(Counter(a.get('original_profile') for a in selected)) == profiles, 'Original profile counts differ from pilot specification')
    return copy.deepcopy(selected)


@contextmanager
def lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.runner.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another pilot runner is using this output directory') from None
        try:
            yield directory
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def prepare(directory, config_path=None):
    directory = Path(directory)
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists():
        manifest = read(manifest_path)
        expected_hash = manifest['sha256']
        require(fingerprint({k: v for k, v in manifest.items() if k != 'sha256'}) == expected_hash, 'Pilot manifest was altered')
        require(manifest['implementation'] == implementation(), 'Pilot software or dependencies changed; use a new output directory')
        actors = read(directory / 'participants.json')
        require(fingerprint(actors) == manifest['actors_sha256'], 'Frozen actor inputs were altered')
        config, study = validate_config(manifest['configuration'])
        if config_path is not None:
            supplied, _ = validate_config(read(config_path))
            require(supplied == config, 'Pilot configuration changed; use a new output directory')
        select_actors(config, actors)
        return manifest, actors, study
    require(config_path is not None, 'Provide --config for a new pilot')
    require(not any(p.name != '.runner.lock' for p in directory.iterdir()), 'Use an empty output directory for a new pilot')
    config_path = Path(config_path).resolve()
    config, study = validate_config(read(config_path))
    source = (config_path.parent / config['participants_file']).resolve()
    source_bytes = source.read_bytes()
    actors = select_actors(config, json.loads(source_bytes))
    manifest = {'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
                'configuration': config, 'study': study, 'actors_sha256': fingerprint(actors),
                'source_export': {'path': str(source), 'sha256': hashlib.sha256(source_bytes).hexdigest()},
                'implementation': implementation(),
                'mechanisms': {task: {m: mechanism_configuration(get_task(task), m) for m in config['mechanisms']} for task in study['tasks']},
                'assumptions': [
                    'All three processing mechanisms are retained; no mechanism is selected for favourable outcomes.',
                    'Configured response coefficients override any actor overrides and are identical across individuals, styles and mechanisms.',
                    'Fixed actor parameters persist; experience resets. Repetitions include new unassisted calibration; calibration trajectories match across mechanism variants.',
                    'Mechanism names, condition IDs and job IDs never enter random streams. Direct and baseline trajectories must be invariant across mechanisms.',
                    'The none mechanism suppresses strategic revision and directional reactance, retaining distraction and omission costs.',
                    'Recent MAB processing has six elapsed trials of memory. Recent TBS processing transfers same-option outcomes across changing offers, with four displayed-probability pseudo-observations.',
                    'These are structured processing assumptions, not natural-language comprehension or measured human responses.',
                    'Fitted actor point estimates, missing TBS offers, timing and response limitations of the source reconstruction remain applicable.',
                    'Original exported fits are frozen inputs; updated execution code does not refit the source cohort or change its historical validation results.',
                    'Repetitions are not extra participants. Cohort summaries are descriptive; Monte Carlo uncertainty is separate from uncertainty about people or mechanisms.'
                ]}
    manifest['sha256'] = fingerprint(manifest)
    write(directory / 'participants.json', actors)
    write(manifest_path, manifest)
    return manifest, actors, study


def jobs(manifest, actors):
    config = manifest['configuration']
    for actor in actors:
        for repeat in range(config['repeats']):
            for mechanism in config['mechanisms']:
                case = {'participant': actor['id'], 'repeat': repeat, 'mechanism': mechanism}
                case['id'] = 'job_' + fingerprint(case)[:16]
                yield case, actor


def summarise(report, case, manifest):
    config = manifest['configuration']
    rows = []
    for row in report['runs']:
        trials = row['trials']
        metric = config['primary_outcomes'][row['task']]
        descriptor = report['study']['execution'][row['task']]['metrics'][metric['metric']]
        rows.append({'participant': case['participant'], 'repeat': case['repeat'], 'mechanism': case['mechanism'],
                     'task': row['task'], 'condition': row['condition'], 'session_id': row['session_id'],
                     'completed': row['completed'], 'trials': len(trials),
                     'primary_metric': metric['metric'], 'primary_value': row['metrics'][metric['metric']] / metric['divisor'],
                     'direction': descriptor['direction'],
                     'trajectory_sha256': fingerprint([(t['index'], t['choice'], t['outcome']) for t in trials]),
                     'distribution_sha256': fingerprint([t['assisted_probabilities'] for t in trials]),
                     'active_interventions': sum(t['effect'].get('applied', False) for t in trials),
                     'omissions': sum(t['choice'] == 'NO_RESPONSE' for t in trials),
                     'processing_target_changes': sum(t['effect'].get('processing_target', t['baseline_probabilities']) != t['baseline_probabilities'] for t in trials)})
    return rows


def finished_results(directory, manifest):
    found = []
    expected = {case['id']: case for case, _ in jobs(manifest, read(directory / 'participants.json'))}
    for path in sorted((directory / 'jobs').glob('*/result.json')):
        result = read(path)
        require(result['manifest_sha256'] == manifest['sha256'], 'Job belongs to another pilot')
        require(result['case'] == expected.get(result['job_id']), 'Job is not in the frozen pilot')
        require(fingerprint(result['rows']) == result['summary_sha256'], 'Completed job summary changed')
        report_path = directory / result['report_file']
        require(hashlib.sha256(report_path.read_bytes()).hexdigest() == result['report_sha256'], 'Completed job report changed')
        found.append(result)
    require(len({r['job_id'] for r in found}) == len(found), 'Duplicate completed job records')
    return found


def analyse(directory, manifest, actors):
    config = manifest['configuration']
    results = finished_results(directory, manifest)
    rows = [row for result in results for row in result['rows']]
    groups = defaultdict(list)
    for row in rows:
        groups[(row['participant'], row['repeat'], row['task'], row['condition'])].append(row)
    controls = []
    null_response = not any(config['response_parameters'].values())
    for key, values in sorted(groups.items()):
        if len(values) != len(config['mechanisms']) or key[3] not in {'A', 'C', 'E'} and not null_response:
            continue
        identical = len({(v['trajectory_sha256'], v['distribution_sha256'], v['primary_value']) for v in values}) == 1
        controls.append({'participant': key[0], 'repeat': key[1], 'task': key[2], 'condition': key[3], 'identical': identical})
    null_checks = []
    if null_response or not any(config['response_parameters'][name] for name in ('distraction', 'omission_probability')):
        for result in results:
            for task in manifest['study']['tasks']:
                values = [r for r in result['rows'] if r['task'] == task]
                baseline = next(r for r in values if r['condition'] == 'A')
                targets = values if null_response else [r for r in values if r['mechanism'] == 'none' and r['condition'] in {'D', 'F'}]
                for row in targets:
                    null_checks.append({'participant': row['participant'], 'repeat': row['repeat'], 'task': task,
                                        'condition': row['condition'], 'mechanism': row['mechanism'],
                                        'identical_to_A': row['trajectory_sha256'] == baseline['trajectory_sha256'] and row['distribution_sha256'] == baseline['distribution_sha256']})
    # Compare only fully observed protocols and matched mechanism sets. A capped
    # engineering job is never converted into a full-protocol outcome estimate.
    pairs = []
    for key, values in sorted(groups.items()):
        if key[3] == 'A' or len(values) != len(config['mechanisms']) or not all(v['completed'] for v in values):
            continue
        baselines = groups[(key[0], key[1], key[2], 'A')]
        for row in values:
            baseline = next(v for v in baselines if v['mechanism'] == row['mechanism'])
            if not baseline['completed']:
                continue
            delta = row['primary_value'] - baseline['primary_value']
            pairs.append({**row, 'delta_from_A': delta,
                          'improvement_from_A': delta * (1 if row['direction'] == 'maximize' else -1)})
    by_person = defaultdict(list)
    for row in pairs:
        by_person[(row['participant'], row['task'], row['condition'], row['mechanism'])].append(row)
    individual = []
    profiles = {a['id']: a.get('original_profile', 'unclassified') for a in actors}
    for (person, task, condition, mechanism), values in sorted(by_person.items()):
        if len(values) != config['repeats']:
            continue
        deltas = [v['improvement_from_A'] for v in values]
        individual.append({'participant': person, 'original_profile': profiles[person], 'task': task,
                           'condition': condition, 'mechanism': mechanism, 'repetitions': len(values),
                           'mean_improvement_from_A': mean(deltas),
                           'monte_carlo_se': stdev(deltas) / len(deltas)**.5 if len(deltas) > 1 else None,
                           'mean_interventions': mean(v['active_interventions'] for v in values),
                           'mean_omissions': mean(v['omissions'] for v in values)})
    aggregates = []
    buckets = defaultdict(list)
    for row in individual:
        for profile in ('all', row['original_profile']):
            buckets[(row['task'], row['condition'], row['mechanism'], profile)].append(row)
    for (task, condition, mechanism, profile), values in sorted(buckets.items()):
        deltas = [v['mean_improvement_from_A'] for v in values]
        aggregates.append({'task': task, 'condition': condition, 'mechanism': mechanism, 'profile': profile,
                           'participants': len(values), 'mean_improvement_from_A': mean(deltas),
                           'min_individual_improvement': min(deltas), 'max_individual_improvement': max(deltas),
                           'participants_worse_than_A': sum(d < 0 for d in deltas),
                           'mean_interventions': mean(v['mean_interventions'] for v in values),
                           'mean_omissions': mean(v['mean_omissions'] for v in values)})
    sensitivity = []
    mechanism_groups = defaultdict(list)
    for row in individual:
        if row['condition'] in {'D', 'F'}:
            mechanism_groups[(row['participant'], row['task'], row['condition'])].append(row)
    for (person, task, condition), values in sorted(mechanism_groups.items()):
        if len(values) == len(config['mechanisms']):
            effects = {v['mechanism']: v['mean_improvement_from_A'] for v in values}
            sensitivity.append({'participant': person, 'task': task, 'condition': condition, 'effects': effects,
                                'range': max(effects.values()) - min(effects.values()),
                                'sign_reversal': min(effects.values()) < 0 < max(effects.values())})
    report = {'version': VERSION, 'manifest_sha256': manifest['sha256'],
              'completed_jobs': len(results), 'total_jobs': len(actors) * config['repeats'] * len(config['mechanisms']),
              'completed_protocol_sessions': sum(r['completed'] for r in rows), 'recorded_comparison_sessions': len(rows),
              'complete': len(results) == len(actors) * config['repeats'] * len(config['mechanisms']) and all(r['completed'] for r in rows),
              'controls': controls, 'null_and_no_revision_checks': null_checks,
              'control_checks_passed': all(r['identical'] for r in controls) and all(r['identical_to_A'] for r in null_checks),
              'individual_results': individual, 'aggregates': aggregates, 'mechanism_sensitivity': sensitivity,
              'compute_seconds_completed_jobs': sum(r['elapsed_seconds'] for r in results),
              'notice': 'Descriptive conditional simulation. Matched completed repetitions are averaged within people. Monte Carlo SE is not human/model uncertainty; no mechanism is selected as a winner.'}
    write(directory / 'analysis.json', report)
    lines = ['# Reconsideration pilot', '', report['notice'], '',
             f"Completed jobs: {report['completed_jobs']}/{report['total_jobs']}. Completed comparison protocols: {report['completed_protocol_sessions']}/{len(rows)}.",
             f"Matched control checks: {'passed so far' if report['control_checks_passed'] else 'FAILED'}. Checks become available as matched cases finish.", '',
             '| Task | Condition | Mechanism | People | Mean improvement from A | Worse than A | Interventions | Omissions |',
             '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in aggregates:
        if row['profile'] == 'all':
            lines.append(f"| {row['task']} | {row['condition']} | {row['mechanism']} | {row['participants']} | {row['mean_improvement_from_A']:.4f} | {row['participants_worse_than_A']} | {row['mean_interventions']:.2f} | {row['mean_omissions']:.2f} |")
    if not aggregates:
        lines.extend(['', 'No complete matched outcome estimates yet. Capped engineering comparisons are excluded.'])
    lines.extend(['', 'Positive improvement follows each declared metric direction. Original profiles are researcher-side descriptors. Repetitions are not additional participants. With one repetition, Monte Carlo SE is unavailable.', '',
                  'See analysis.json for individual effects, original-profile summaries, mechanism ranges/sign reversals and control checks.'])
    (directory / 'analysis.md').write_text('\n'.join(lines) + '\n')
    return report


def execute(directory, config_path=None, max_jobs=None, prepare_only=False, report_only=False, progress=print):
    require(max_jobs is None or type(max_jobs) is int and max_jobs > 0, 'max-jobs must be positive')
    with lock(directory) as directory:
        manifest, actors, study = prepare(directory, config_path)
        config = manifest['configuration']
        completed = {r['job_id'] for r in finished_results(directory, manifest)}
        completed_here = 0
        initial = analyse(directory, manifest, actors)
        require(initial['control_checks_passed'], 'Matched control check failed; inspect analysis.json before proceeding')
        write(directory / 'status.json', {'status': 'ready', 'manifest_sha256': manifest['sha256'],
                                         'completed_jobs': len(completed), 'total_jobs': len(list(jobs(manifest, actors)))})
        if not prepare_only and not report_only:
            from .store import Store
            for case, actor in jobs(manifest, actors):
                if case['id'] in completed:
                    continue
                if max_jobs is not None and completed_here >= max_jobs:
                    break
                require(manifest['implementation'] == implementation(), 'Pilot software changed; use a new output directory')
                job_dir = directory / 'jobs' / case['id']
                job_dir.mkdir(parents=True, exist_ok=True)
                attempts = job_dir / 'attempts'
                attempts.mkdir(exist_ok=True)
                attempt = attempts / f'{len(list(attempts.iterdir()))+1:03d}'
                attempt.mkdir()
                spec = copy.deepcopy(actor)
                spec['response_parameters'] = {task: {style: dict(config['response_parameters']) for style in ('direct', 'socratic')}
                                               for task in study['tasks']}
                scenario = 'null' if not any(config['response_parameters'].values()) else 'responsive'
                status = {'status': 'running', 'job': case, 'attempt': str(attempt.relative_to(directory)),
                          'completed_jobs': len(completed), 'manifest_sha256': manifest['sha256'], 'pid': os.getpid()}
                write(directory / 'status.json', status)
                started = time.monotonic()

                def on_progress(person, task, condition, repeat):
                    write(directory / 'status.json', {**status, 'last_completed_session': {'task': task, 'condition': condition},
                                                     'current_job_elapsed_seconds': time.monotonic()-started})
                    if progress:
                        progress(f"{case['id']} {person} {task} {condition} {case['mechanism']} complete")

                try:
                    report = simulate(Store(attempt / 'sessions.sqlite3'), [spec], scenario=scenario,
                                      seed=f"{config['seed']}:rep:{case['repeat']}", repeats=1,
                                      max_trials=config.get('max_trials'), on_progress=on_progress, study=study,
                                      reconsideration=case['mechanism'])
                    report_file = attempt / 'evaluator.json'
                    write(report_file, report)
                    require(manifest['implementation'] == implementation(), 'Pilot software changed during the job; use a new output directory')
                    summary = summarise(report, case, manifest)
                    result = {'job_id': case['id'], 'case': case, 'manifest_sha256': manifest['sha256'],
                              'report_file': str(report_file.relative_to(directory)),
                              'report_sha256': hashlib.sha256(report_file.read_bytes()).hexdigest(),
                              'elapsed_seconds': time.monotonic()-started, 'rows': summary, 'summary_sha256': fingerprint(summary)}
                    write(job_dir / 'result.json', result)
                    completed.add(case['id'])
                    completed_here += 1
                    analysis = analyse(directory, manifest, actors)
                    require(analysis['control_checks_passed'], 'Matched control check failed; inspect analysis.json before proceeding')
                except BaseException as error:
                    write(directory / 'status.json', {**status, 'status': 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                                                     'error': str(error), 'elapsed_seconds': time.monotonic()-started})
                    raise
        analysis = analyse(directory, manifest, actors)
        require(analysis['control_checks_passed'], 'Matched control check failed; inspect analysis.json before proceeding')
        write(directory / 'status.json', {'status': 'complete' if analysis['complete'] else 'incomplete',
                                         'completed_jobs': analysis['completed_jobs'], 'total_jobs': analysis['total_jobs'],
                                         'manifest_sha256': manifest['sha256'], 'control_checks_passed': analysis['control_checks_passed']})
        return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', help='Pilot JSON; required for a new output directory')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--max-jobs', type=int, help='Stop after this many additional completed jobs; rerun to resume')
    parser.add_argument('--prepare-only', action='store_true', help='Freeze and inspect the plan without running sessions')
    parser.add_argument('--report-only', action='store_true', help='Rebuild analysis from completed jobs')
    args = parser.parse_args()
    require(not (args.prepare_only and args.report_only), 'Choose prepare-only or report-only')
    os.environ.update(SOCRATIC_LLM='offline', SOCRATIC_LANGUAGE_MODE='bounded', SOCRATIC_INTERPRET_RESPONSES='0')
    report = execute(args.output_dir, args.config, args.max_jobs, args.prepare_only, args.report_only,
                     lambda message: print(message, flush=True))
    print(f"Saved pilot analysis: {report['completed_jobs']}/{report['total_jobs']} jobs", flush=True)


if __name__ == '__main__':
    main()
