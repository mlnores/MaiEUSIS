"""Parallel scheduling preserves frozen experiments and sequential trajectories."""
import copy
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pilot_parallel as scheduler
from socratic_prototype import pilot
from socratic_prototype.records import ValidationError


RESPONSE = {'responsiveness': .5, 'reactance': 0, 'distraction': 0, 'omission_probability': 0}


def configuration(directory):
    actors = [{'id': 'parallel_fixture', 'source': 'Authored engineering fixture',
               'task_models': {'MAB': {'alpha_plus': .4, 'alpha_minus': .3, 'beta': 2},
                               'TBS': {'intercept': 0, 'slope': 1}}}]
    pilot.write(directory/'actors.json', actors)
    config = {'id': 'parallel-check', 'participants_file': 'actors.json', 'expected_participants': 1,
              'cohort_split': 'engineering', 'study': {'id': 'parallel-check',
                  'tasks': {task: {'protocol': 'short', 'calibration_tasks': ['MAB', 'TBS']} for task in ('MAB', 'TBS')},
                  'conditions': ['A', 'C', 'E', 'D', 'F']},
              'mechanisms': ['none', 'current', 'recent'], 'response_parameters': RESPONSE,
              'seed': 'parallel-equivalence', 'repeats': 1, 'max_trials': 8,
              'primary_outcomes': {'MAB': {'metric': 'score', 'divisor': 1},
                                   'TBS': {'metric': 'targets_attained', 'divisor': 3}}}
    pilot.write(directory/'config.json', config)
    return directory/'config.json'


class SchedulingTest(unittest.TestCase):
    def test_repetition_first_profile_balance_preserves_every_job_and_seed(self):
        actors = [{'id': f'person{i}', 'original_profile': profile}
                  for i, profile in enumerate(['MAB', 'MAB', 'TBS', 'TBS', 'dual', 'low'])]
        manifest = {'configuration': {'mechanisms': ['none', 'current', 'recent'], 'repeats': 3}}
        original = list(pilot.jobs(manifest, actors))
        ordered = scheduler.ordered_jobs(manifest, actors)
        self.assertEqual({c['id'] for c, _ in ordered}, {c['id'] for c, _ in original})
        self.assertEqual([c['repeat'] for c, _ in ordered], sorted(c['repeat'] for c, _ in original))
        self.assertEqual([actor['original_profile'] for _, actor in ordered[:12:3]], ['MAB', 'TBS', 'dual', 'low'])
        self.assertEqual({c['mechanism'] for c, _ in ordered}, {'none', 'current', 'recent'})

    def test_first_repetition_requires_all_mechanisms_and_full_trials(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            manifest = {'sha256': 'fixture', 'configuration': {'mechanisms': ['none', 'current', 'recent']}}
            actors = [{'id': 'person', 'original_profile': 'low'}]
            results = []
            for mechanism in ('none', 'current', 'recent'):
                results.append({'case': {'participant': 'person', 'repeat': 0, 'mechanism': mechanism},
                                'rows': [{'participant': 'person', 'task': 'TBS', 'condition': condition,
                                          'mechanism': mechanism, 'completed': True,
                                          'primary_value': value, 'direction': 'maximize'}
                                         for condition, value in [('A', .5), ('D', .75)]]})
            self.assertFalse(scheduler.first_repetition(directory, manifest, actors, results[:2])['participants'])
            incomplete = copy.deepcopy(results); incomplete[2]['rows'][0]['completed'] = False
            self.assertFalse(scheduler.first_repetition(directory, manifest, actors, incomplete)['participants'])
            complete = scheduler.first_repetition(directory, manifest, actors, results)
            self.assertTrue(complete['complete_cohort'])
            self.assertEqual(complete['participants'], ['person'])
            self.assertTrue(all(r['improvement_from_A'] == .25 for r in complete['individual_results']))

    def test_attempt_numbering_preserves_existing_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); case = {'id': 'job_fixture'}
            attempts = directory/'jobs'/case['id']/'attempts'
            (attempts/'001').mkdir(parents=True); (attempts/'003').mkdir()
            (attempts/'notes.txt').write_text('retained')
            self.assertEqual(scheduler.next_attempt(directory, case).name, '004')
            self.assertTrue((attempts/'001').is_dir()); self.assertTrue((attempts/'notes.txt').exists())

    def test_inherited_lease_prevents_a_second_runner_after_parent_closes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'.runner.lock'
            child = None
            try:
                with scheduler.lease(path) as fd:
                    self.assertTrue(scheduler.lock_held(path))
                    with self.assertRaisesRegex(ValueError, 'Another runner'):
                        with scheduler.lease(path): pass
                    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'], pass_fds=(fd,))
                self.assertTrue(scheduler.lock_held(path))
            finally:
                if child is not None:
                    child.terminate(); child.wait()
            self.assertFalse(scheduler.lock_held(path))

    def test_handover_waits_for_boundary_and_reports_denied_signal(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); (directory/'jobs'/'job_fixture').mkdir(parents=True)
            pilot.write(directory/'status.json', {'pid': 123, 'job': {'id': 'job_fixture'}})
            sleeps = []
            def tick(_):
                sleeps.append(True)
                pilot.write(directory/'jobs'/'job_fixture'/'result.json', {'committed': True})
            with patch.object(scheduler, 'lock_held', side_effect=[True, True, True, False]), \
                 patch.object(scheduler.time, 'sleep', side_effect=tick), \
                 patch.object(scheduler.os, 'kill', side_effect=PermissionError('fixture denied')) as kill:
                scheduler.await_handover(directory, 123, poll=0)
            self.assertEqual(len(sleeps), 2)
            kill.assert_called_once_with(123, scheduler.signal.SIGINT)
            handover = pilot.read(directory/'handover.json')
            self.assertEqual(handover['terminal_command'], 'kill -INT 123')
            self.assertEqual(handover['status'], 'runner_released')
            with patch.object(scheduler, 'lock_held', return_value=True):
                with self.assertRaisesRegex(ValidationError, 'PID does not match'):
                    scheduler.await_handover(directory, 456, poll=0)

    def test_failed_worker_is_recorded_and_attempt_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); config = configuration(directory); out = directory/'run'
            class FailedProcess:
                pid = 12345
                def poll(self): return 1
            with patch.object(scheduler.subprocess, 'Popen', return_value=FailedProcess()):
                with self.assertRaisesRegex(ValidationError, 'Worker failed'):
                    scheduler.execute(out, workers=1, config_path=config, poll=0)
            status = pilot.read(out/'status.json')
            self.assertEqual(status['status'], 'failed'); self.assertEqual(len(status['failures']), 1)
            self.assertEqual(len(list((out/'jobs').glob('*/attempts/*'))), 1)
            self.assertFalse(list((out/'jobs').glob('*/result.json')))
            self.assertFalse(scheduler.lock_held(out/'.runner.lock'))

    def test_worker_bound_and_failure_prevent_dispatching_the_rest(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); config = configuration(directory); out = directory/'run'
            value = pilot.read(config); value['repeats'] = 2; pilot.write(config, value)
            class FailedProcess:
                pid = 12345
                def poll(self): return 1
            with patch.object(scheduler.subprocess, 'Popen', return_value=FailedProcess()) as launch:
                with self.assertRaisesRegex(ValidationError, 'Worker failed'):
                    scheduler.execute(out, workers=4, config_path=config, poll=0)
            self.assertEqual(launch.call_count, 4)
            self.assertEqual(len(list((out/'jobs').glob('*/attempts/*'))), 4)
            self.assertEqual(len(pilot.read(out/'status.json')['failures']), 4)

    def test_stop_request_dispatches_nothing_and_preserves_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); config = configuration(directory); out = directory/'run'
            pilot.execute(out, config, prepare_only=True, progress=None)
            before = (out/'manifest.json').read_bytes()
            (out/'parallel-stop.json').touch()
            with patch.object(scheduler.subprocess, 'Popen') as launch:
                result = scheduler.execute(out, workers=4, poll=0)
            launch.assert_not_called(); self.assertEqual(result['completed_jobs'], 0)
            self.assertEqual((out/'manifest.json').read_bytes(), before)
            self.assertEqual(pilot.read(out/'status.json')['status'], 'incomplete')


class ParallelIntegrationTest(unittest.TestCase):
    def test_sequential_parallel_equivalence_resume_and_replay(self):
        # Real MAB/TBS, real SHACL/graph policy and subprocesses. Calibrations run
        # their entire short protocols; comparisons stop after 8 trials, so this
        # checks execution rather than estimating experimental performance.
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); config = configuration(directory)
            serial, parallel = directory/'serial', directory/'parallel'
            began = time.monotonic()
            sequential = pilot.execute(serial, config, progress=None)
            sequential_seconds = time.monotonic()-began
            manifest, actors, _ = pilot.prepare(serial)
            parallel.mkdir()
            for name in ('manifest.json', 'participants.json'):
                shutil.copy2(serial/name, parallel/name)
            # Reuse one committed sequential job and an interrupted attempt for
            # another. Neither the completed bytes nor the failed attempt moves.
            existing = next((serial/'jobs').glob('*/result.json'))
            relative = existing.parent.relative_to(serial)
            shutil.copytree(existing.parent, parallel/relative)
            retained_bytes = (parallel/relative/'result.json').read_bytes()
            remaining_case = next(c for c, _ in pilot.jobs(manifest, actors) if c['id'] != existing.parent.name)
            interrupted = parallel/'jobs'/remaining_case['id']/'attempts'/'001'
            interrupted.mkdir(parents=True); (interrupted/'retained.txt').write_text('interrupted')
            began = time.monotonic()
            result = scheduler.execute(parallel, workers=4, poll=.05)
            parallel_seconds = time.monotonic()-began
            self.assertEqual((parallel/relative/'result.json').read_bytes(), retained_bytes)
            self.assertTrue((interrupted/'retained.txt').exists())
            self.assertTrue((interrupted.parent/'002'/'evaluator.json').exists())
            self.assertEqual(result['completed_jobs'], 3)
            self.assertTrue(result['control_checks_passed']); self.assertFalse(result['complete'])
            self.assertEqual(result['aggregates'], [])
            self.assertEqual(pilot.read(parallel/'first_repetition.json')['participants'], [])
            self.assertEqual((serial/'manifest.json').read_bytes(), (parallel/'manifest.json').read_bytes())
            def normalised_rows(output):
                values = {}
                for job in pilot.finished_results(output, manifest):
                    for row in job['rows']:
                        values[(row['task'], row['condition'], row['mechanism'])] = {k:v for k,v in row.items() if k != 'session_id'}
                return values
            self.assertEqual(normalised_rows(serial), normalised_rows(parallel))
            from socratic_prototype.store import Store
            serial_reports = {r['job_id']: pilot.read(serial/r['report_file']) for r in pilot.finished_results(serial, manifest)}
            compared = guided = replays = 0
            for job in pilot.finished_results(parallel, manifest):
                full = pilot.read(parallel/job['report_file']); old = serial_reports[job['job_id']]
                store = Store((parallel/job['report_file']).parent/'sessions.sqlite3')
                for run, original in zip(full['runs'], old['runs']):
                    self.assertEqual((run['task'],run['condition']), (original['task'],original['condition']))
                    for trial, before in zip(run['trials'], original['trials']):
                        for field in ('baseline_probabilities', 'assisted_probabilities', 'choice', 'outcome', 'effect'):
                            self.assertEqual(trial[field], before[field])
                        if (trial.get('intervention') or {}).get('comparisons'):
                            guided += 1
                        compared += 1
                    if run['condition'] == 'F':
                        self.assertTrue(store.replay(run['session_id'])['matches']); replays += 1
            self.assertGreater(guided, 0); self.assertEqual(compared, 240); self.assertEqual(replays, 6)
            saved = {p: p.read_bytes() for p in (parallel/'jobs').glob('*/result.json')}
            again = scheduler.execute(parallel, workers=4, poll=0)
            self.assertEqual(again['completed_jobs'], 3)
            self.assertTrue(all(p.read_bytes() == data for p,data in saved.items()))
            print(json.dumps({'serial_three_jobs_seconds': sequential_seconds,
                              'parallel_two_remaining_jobs_seconds': parallel_seconds,
                              'trial_comparisons': compared, 'guided_decisions': guided,
                              'exact_F_replays': replays}), flush=True)


if __name__ == '__main__':
    unittest.main()
