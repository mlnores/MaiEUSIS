#!/usr/bin/env python3
"""Process scheduler for frozen pilots, outside the fingerprinted simulation package.

The original manifest, seeds, job/result formats and analysis remain unchanged.
Only the coordinator writes shared status/analysis; workers have separate stores.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Set before importing NumPy/pgmpy through the simulation package. Concurrency is
# between processes; nested numerical-library pools would oversubscribe the Mac.
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
             'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'
os.environ.update(SOCRATIC_LLM='offline', SOCRATIC_LANGUAGE_MODE='bounded',
                  SOCRATIC_INTERPRET_RESPONSES='0')

from socratic_prototype import pilot
from socratic_prototype.records import require

VERSION = 'parallel-pilot-scheduler-0.1'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def scheduler_identity():
    return {'version': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'order': 'repetition-first; profile-interleaved; all mechanisms',
            'numerical_threads_per_worker': 1}


@contextmanager
def lease(path):
    """Close rather than explicitly unlock: inherited worker FDs retain the lease
    if the coordinator is killed, preventing a second writer until workers exit.
    """
    with Path(path).open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another runner is using ' + str(path)) from None
        yield handle.fileno()


def lock_held(path):
    with Path(path).open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def ordered_jobs(manifest, actors):
    profiles = defaultdict(deque)
    for actor in actors:
        profiles[actor.get('original_profile', 'unclassified')].append(actor)
    balanced = []
    while any(profiles.values()):
        for group in profiles.values():
            if group:
                balanced.append(group.popleft())
    actor_order = {actor['id']: i for i, actor in enumerate(balanced)}
    mechanisms = manifest['configuration']['mechanisms']
    return sorted(pilot.jobs(manifest, actors),
                  key=lambda item: (item[0]['repeat'], actor_order[item[0]['participant']],
                                    mechanisms.index(item[0]['mechanism'])))


def first_repetition(directory, manifest, actors, results):
    """Separate descriptive preview; never relax the primary analysis criteria."""
    expected = set(manifest['configuration']['mechanisms'])
    grouped = defaultdict(list)
    for result in results:
        if result['case']['repeat'] == 0:
            grouped[result['case']['participant']].append(result)
    rows, people = [], []
    profiles = {a['id']: a.get('original_profile', 'unclassified') for a in actors}
    for person, values in sorted(grouped.items()):
        if {v['case']['mechanism'] for v in values} != expected:
            continue
        if not all(r['completed'] for v in values for r in v['rows']):
            continue
        people.append(person)
        for result in values:
            for row in result['rows']:
                if row['condition'] == 'A':
                    continue
                baseline = next(r for r in result['rows'] if r['task'] == row['task'] and r['condition'] == 'A')
                rows.append({**row, 'original_profile': profiles[person],
                             'improvement_from_A': (row['primary_value']-baseline['primary_value']) *
                             (1 if row['direction'] == 'maximize' else -1)})
    buckets = defaultdict(list)
    for row in rows:
        for profile in ('all', row['original_profile']):
            buckets[(row['task'], row['condition'], row['mechanism'], profile)].append(row)
    aggregates = [{'task': key[0], 'condition': key[1], 'mechanism': key[2], 'profile': key[3],
                   'participants': len(values),
                   'mean_improvement_from_A': mean(v['improvement_from_A'] for v in values),
                   'participants_worse_than_A': sum(v['improvement_from_A'] < 0 for v in values)}
                  for key, values in sorted(buckets.items())]
    report = {'manifest_sha256': manifest['sha256'], 'repeat': 0, 'participants': people,
              'complete_cohort': len(people) == len(actors), 'individual_results': rows, 'aggregates': aggregates,
              'notice': 'Preliminary first-repetition view, restricted to complete protocols and all three mechanisms. '
                        'One repetition per person; no Monte Carlo SE. Not the primary three-repetition analysis, '
                        'not human assistance effects and not additional participants.'}
    pilot.write(directory/'first_repetition.json', report)
    lines = ['# First matched repetition (preliminary)', '', report['notice'], '',
             f'People with all mechanisms: {len(people)}/{len(actors)}.', '',
             '| Task | Condition | Mechanism | People | Mean improvement from A | Worse than A |',
             '| --- | --- | --- | ---: | ---: | ---: |']
    for row in aggregates:
        if row['profile'] == 'all':
            lines.append(f"| {row['task']} | {row['condition']} | {row['mechanism']} | {row['participants']} | "
                         f"{row['mean_improvement_from_A']:.4f} | {row['participants_worse_than_A']} |")
    (directory/'first_repetition.md').write_text('\n'.join(lines)+'\n')
    return report


def next_attempt(directory, case):
    attempts = directory/'jobs'/case['id']/'attempts'
    attempts.mkdir(parents=True, exist_ok=True)
    numbers = [int(p.name) for p in attempts.iterdir() if p.is_dir() and p.name.isdigit()]
    attempt = attempts/f'{max(numbers, default=0)+1:03d}'
    attempt.mkdir()
    return attempt


def worker(directory, job_id, attempt, lease_fd):
    # Only coordinator-launched workers inherit this FD. Keep it open until exit.
    require(os.fstat(lease_fd).st_ino == (directory/'.runner.lock').stat().st_ino,
            'Worker must inherit the coordinator runner lease')
    manifest, actors, study = pilot.prepare(directory)
    case, actor = next(item for item in pilot.jobs(manifest, actors) if item[0]['id'] == job_id)
    require(attempt.parent == directory/'jobs'/job_id/'attempts' and attempt.is_dir(), 'Invalid worker attempt')
    require(not (directory/'jobs'/job_id/'result.json').exists(), 'Job already completed')
    config = manifest['configuration']
    spec = copy.deepcopy(actor)
    spec['response_parameters'] = {task: {style: dict(config['response_parameters']) for style in ('direct', 'socratic')}
                                   for task in study['tasks']}
    scenario = 'null' if not any(config['response_parameters'].values()) else 'responsive'
    started = time.monotonic()
    status = {'status': 'running', 'job': case, 'attempt': str(attempt.relative_to(directory)),
              'pid': os.getpid(), 'started_at_utc': timestamp(), 'scheduler': scheduler_identity()}
    pilot.write(attempt/'progress.json', status)

    def progress(person, task, condition, repeat):
        pilot.write(attempt/'progress.json', {**status, 'last_completed_session': {'task': task, 'condition': condition},
                                             'current_job_elapsed_seconds': time.monotonic()-started})

    try:
        from socratic_prototype.store import Store
        report = pilot.simulate(Store(attempt/'sessions.sqlite3'), [spec], scenario=scenario,
                                seed=f"{config['seed']}:rep:{case['repeat']}", repeats=1,
                                max_trials=config.get('max_trials'), on_progress=progress,
                                study=study, reconsideration=case['mechanism'])
        report_file = attempt/'evaluator.json'
        pilot.write(report_file, report)
        require(manifest['implementation'] == pilot.implementation(), 'Pilot software changed during the job')
        rows = pilot.summarise(report, case, manifest)
        result = {'job_id': case['id'], 'case': case, 'manifest_sha256': manifest['sha256'],
                  'report_file': str(report_file.relative_to(directory)),
                  'report_sha256': hashlib.sha256(report_file.read_bytes()).hexdigest(),
                  'elapsed_seconds': time.monotonic()-started, 'rows': rows,
                  'summary_sha256': pilot.fingerprint(rows), 'scheduler': scheduler_identity()}
        pilot.write(directory/'jobs'/job_id/'result.json', result)
        pilot.write(attempt/'progress.json', {**status, 'status': 'complete', 'elapsed_seconds': result['elapsed_seconds']})
    except BaseException as error:
        pilot.write(attempt/'progress.json', {**status, 'status': 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                                             'error': str(error), 'elapsed_seconds': time.monotonic()-started})
        raise


def await_handover(directory, pid, poll=2):
    """Stop the original runner just after its current result is committed.

    A denied signal leaves a waiting coordinator; the user can signal from their
    own Terminal. Never edit the frozen package to force a source-drift failure.
    """
    require(type(pid) is int and pid > 0, 'Handover requires a positive PID')
    if not lock_held(directory/'.runner.lock'):
        return
    status = pilot.read(directory/'status.json')
    require(status.get('pid') == pid and status.get('job'), 'Handover PID does not match the active sequential job')
    current = status['job']['id']
    handover = {'status': 'waiting_for_job_boundary', 'previous_pid': pid, 'previous_job': current,
                'coordinator_pid': os.getpid(), 'requested_at_utc': timestamp(), 'scheduler': scheduler_identity()}
    pilot.write(directory/'handover.json', handover)
    print(f'Waiting for {current} to finish before handing over from PID {pid}', flush=True)
    signalled = False
    while lock_held(directory/'.runner.lock'):
        if (directory/'parallel-stop.json').exists():
            raise ValueError('Handover cancelled by parallel-stop.json; sequential runner left alone')
        if not signalled and (directory/'jobs'/current/'result.json').exists():
            latest = pilot.read(directory/'status.json')
            require(latest.get('pid') == pid, 'Active runner changed during handover')
            try:
                os.kill(pid, signal.SIGINT)
                handover.update(status='waiting_for_runner_exit', signal_sent_at_utc=timestamp())
                print(f'Current job complete; sent SIGINT to original runner {pid}', flush=True)
            except ProcessLookupError:
                pass
            except PermissionError as error:
                handover.update(status='manual_signal_required', error=str(error),
                                terminal_command=f'kill -INT {pid}')
                print(f'Signal permission denied. Run in your Terminal: kill -INT {pid}', flush=True)
            pilot.write(directory/'handover.json', handover)
            signalled = True
        time.sleep(poll)
    handover.update(status='runner_released', released_at_utc=timestamp())
    pilot.write(directory/'handover.json', handover)


def execute(directory, workers=4, config_path=None, max_jobs=None, handover_pid=None, poll=2):
    require(type(workers) is int and workers > 0, 'workers must be positive')
    require(max_jobs is None or type(max_jobs) is int and max_jobs > 0, 'max-jobs must be positive')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not (directory/'manifest.json').exists():
        # Use the original creation path before adding our extra lock file, so
        # its empty-directory and frozen-input checks apply without exceptions.
        with pilot.lock(directory):
            pilot.prepare(directory, config_path)
    with lease(directory/'.parallel-controller.lock'):
        if handover_pid is not None:
            await_handover(directory, handover_pid, poll)
        # The extra controller lock prevents duplicate waiting schedulers. It is
        # outside implementation(); the original exclusive runner lock still
        # excludes sequential runners and other coordinators from this dataset.
        with lease(directory/'.runner.lock') as lease_fd:
            manifest, actors, study = pilot.prepare(directory, config_path)
            results = pilot.finished_results(directory, manifest)
            completed = {r['job_id'] for r in results}
            pending = deque(item for item in ordered_jobs(manifest, actors) if item[0]['id'] not in completed)
            if max_jobs is not None:
                pending = deque(list(pending)[:max_jobs])
            analysis = pilot.analyse(directory, manifest, actors)
            require(analysis['control_checks_passed'], 'Matched control check failed')
            first_repetition(directory, manifest, actors, results)
            started = time.monotonic()
            start_count = len(completed)
            identity = scheduler_identity()
            run_record = {'started_at_utc': timestamp(), 'pid': os.getpid(), 'workers': workers,
                          'manifest_sha256': manifest['sha256'], 'completed_jobs_at_start': start_count,
                          'scheduler': identity}
            run_file = directory/f'parallel_launch_{os.getpid()}.json'
            pilot.write(run_file, run_record)
            active, failures = {}, []
            stopping = False

            def publish(state='running'):
                entries = []
                for job_id, info in active.items():
                    progress_file = info['attempt']/'progress.json'
                    entries.append(pilot.read(progress_file) if progress_file.exists() else
                                   {'status': 'starting', 'job': info['case'], 'pid': info['process'].pid,
                                    'attempt': str(info['attempt'].relative_to(directory))})
                elapsed = time.monotonic()-started
                newly_done = len(completed)-start_count
                pilot.write(directory/'status.json', {'status': state, 'pid': os.getpid(), 'workers': workers,
                    'active_jobs': entries, 'completed_jobs': len(completed), 'total_jobs': analysis['total_jobs'],
                    'manifest_sha256': manifest['sha256'], 'scheduler': identity, 'updated_at_utc': timestamp(),
                    'control_checks_passed': analysis['control_checks_passed'], 'failures': failures,
                    'elapsed_seconds': elapsed, 'new_jobs_completed': newly_done,
                    'observed_jobs_per_hour': newly_done/elapsed*3600 if newly_done else None,
                    'remaining_hours_at_observed_rate': (analysis['total_jobs']-len(completed))*elapsed/newly_done/3600 if newly_done else None})

            try:
                while pending or active:
                    if (directory/'parallel-stop.json').exists():
                        stopping = True
                    while pending and len(active) < workers and not stopping:
                        require(identity == scheduler_identity(), 'Scheduler changed while running')
                        require(manifest['implementation'] == pilot.implementation(), 'Frozen simulation changed')
                        case, actor = pending.popleft()
                        attempt = next_attempt(directory, case)
                        log = (attempt/'worker.log').open('ab', buffering=0)
                        try:
                            process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()),
                                '--output-dir', str(directory), '--worker-job', case['id'],
                                '--worker-attempt', str(attempt), '--lease-fd', str(lease_fd)],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                pass_fds=(lease_fd,))
                        finally:
                            log.close()
                        active[case['id']] = {'case': case, 'attempt': attempt, 'process': process}
                        print(f'Start {case["id"]} {case["participant"]} repeat={case["repeat"]} {case["mechanism"]} pid={process.pid}', flush=True)
                    changed = False
                    for job_id, info in list(active.items()):
                        code = info['process'].poll()
                        if code is None:
                            continue
                        del active[job_id]
                        result_file = directory/'jobs'/job_id/'result.json'
                        if code != 0 or not result_file.exists():
                            failures.append({'job_id': job_id, 'returncode': code,
                                             'attempt': str(info['attempt'].relative_to(directory))})
                            stopping = True
                            print(f'FAILED {job_id}; draining other active jobs without dispatching more', flush=True)
                        else:
                            completed.add(job_id)
                            print(f'Complete {job_id}; {len(completed)}/{analysis["total_jobs"]}', flush=True)
                            changed = True
                    if changed:
                        results = pilot.finished_results(directory, manifest)
                        analysis = pilot.analyse(directory, manifest, actors)
                        first_repetition(directory, manifest, actors, results)
                        require(analysis['control_checks_passed'], 'Matched control check failed')
                    publish('stopping' if stopping else 'running')
                    if stopping and not active:
                        break
                    if active:
                        time.sleep(poll)
                require(not failures, 'Worker failed; inspect attempt worker.log before resuming')
            except BaseException as error:
                # Never release the runner lease while workers still write. On
                # an interactive Ctrl-C, completed jobs survive and interrupted
                # attempts are retained. SIGKILL is covered by inherited leases.
                for info in active.values():
                    if info['process'].poll() is None:
                        info['process'].send_signal(signal.SIGINT)
                for info in active.values():
                    info['process'].wait()
                publish('interrupted' if isinstance(error, KeyboardInterrupt) else 'failed')
                raise
            analysis = pilot.analyse(directory, manifest, actors)
            first_repetition(directory, manifest, actors, pilot.finished_results(directory, manifest))
            publish('complete' if analysis['complete'] else 'incomplete')
            pilot.write(run_file, {**run_record, 'finished_at_utc': timestamp(),
                                  'elapsed_seconds': time.monotonic()-started, 'completed_jobs_at_end': len(completed)})
            return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--config', help='Required only when creating a new frozen pilot')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--max-jobs', type=int, help='Maximum additional jobs to dispatch; resume reuses completed results')
    parser.add_argument('--handover-pid', type=int, help='Wait for this sequential runner to complete its current job, then request its exit')
    parser.add_argument('--worker-job', help=argparse.SUPPRESS)
    parser.add_argument('--worker-attempt', help=argparse.SUPPRESS)
    parser.add_argument('--lease-fd', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    directory = Path(args.output_dir).resolve()
    if args.worker_job:
        require(args.worker_attempt is not None and args.lease_fd is not None, 'Worker requires an attempt and inherited lease')
        worker(directory, args.worker_job, Path(args.worker_attempt).resolve(), args.lease_fd)
    else:
        result = execute(directory, args.workers, args.config, args.max_jobs, args.handover_pid)
        print(f'Saved analysis: {result["completed_jobs"]}/{result["total_jobs"]} jobs', flush=True)


if __name__ == '__main__':
    main()
