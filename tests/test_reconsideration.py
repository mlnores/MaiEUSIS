"""Mechanism effects, matched controls, information boundaries and pilot resume."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.agents import Participant
from socratic_prototype.assistance_response import apply
from socratic_prototype.pilot import execute, read, write
from socratic_prototype.records import ValidationError
from socratic_prototype.tasks import mab_execution, tbs_execution, reference_execution

SPEC = {'id': 'mechanism_fixture', 'source': 'Assumed mechanism fixture',
        'task_models': {'MAB': {'alpha_plus': .4, 'alpha_minus': .3, 'beta': 2},
                        'TBS': {'intercept': 0, 'slope': 1}},
        'baseline_omission': {'MAB': .01, 'TBS': .02}}
RESPONSE = {'responsiveness': .5, 'reactance': 0, 'distraction': 0, 'omission_probability': 0}


def intervention(style='socratic', focus='value_revision'):
    return {'style': style, 'focus': focus,
            'recommendation': {'option_id': 'risky'} if style == 'direct' else None}


class MechanismTest(unittest.TestCase):
    def test_equal_strength_different_targets_and_no_revision_costs(self):
        base = {'safe': .6, 'risky': .4}
        direct = apply(base, intervention('direct'), RESPONSE, {})[0]
        socratic = apply(base, intervention(), RESPONSE, {'safe': .3, 'risky': .7})[0]
        self.assertAlmostEqual(direct['risky'], .7)
        self.assertAlmostEqual(socratic['risky'], .55)
        costs = {**RESPONSE, 'reactance': 1., 'distraction': .2, 'omission_probability': .1}
        result, effect = apply(base, intervention(), costs, {}, strategic_revision=False)
        self.assertAlmostEqual(result['safe'], .8*.6+.1)
        self.assertEqual(effect['parameters'], costs)
        self.assertEqual(effect['omission_probability'], .1)
        self.assertEqual(effect['processing_target'], base)

    def test_no_revision_retains_baseline_learning_and_direct_never_calls_processor(self):
        ev = {'options': [{'id': arm} for arm in mab_execution.ARMS]}
        actor = Participant(SPEC, 'MAB', 'responsive', 'none')
        before = actor.baseline(ev)
        actor.observe({}, {'trial_id': 'fixture_trial_1', 'choice': 'blue1', 'outcome': 100, 'timed_out': False})
        baseline, result, effect = actor.distribution(ev, intervention())
        self.assertNotEqual(before, baseline)
        self.assertEqual(result, baseline)
        self.assertEqual(effect['reconsideration_mechanism'], 'none')
        self.assertEqual(effect['omission_probability'], .01)
        recommendation = {'style': 'direct', 'focus': 'value_revision', 'recommendation': {'option_id': 'blue1'}}
        with patch.object(actor, 'reconsider', side_effect=AssertionError('direct invoked Socratic processor')):
            actor.distribution(ev, recommendation)

    def test_mab_recent_memory_is_distinct_without_scaling_responsiveness(self):
        p = SPEC['task_models']['MAB']
        history = [{'choice': 'red1', 'outcome': 200, 'timed_out': False} for _ in range(12)]
        history += [{'choice': 'blue1', 'outcome': 100, 'timed_out': False} for _ in range(6)]
        history = [{**row, 'trial_id': f'fixture_trial_{i}'} for i, row in enumerate(history)]
        ev = {'options': [{'id': a} for a in mab_execution.ARMS]}
        current = mab_execution.reconsider(history, p, ev, intervention())
        recent = mab_execution.reconsider_recent(history, p, ev, intervention())
        self.assertGreater(current['red1'], recent['red1'])
        self.assertGreater(recent['blue1'], current['blue1'])
        poisoned = {**ev, 'hidden_probabilities': [1, 0, 0], 'future_outcomes': [999999]}
        self.assertEqual(recent, mab_execution.reconsider_recent(history, p, poisoned, intervention()))
        # Six elapsed misses crowd out evidence; they are not six losses.
        misses = [{'choice': 'NO_RESPONSE', 'outcome': -200, 'timed_out': True} for _ in range(6)]
        empty = mab_execution.reconsider([], p, ev, intervention())
        self.assertEqual(mab_execution.reconsider_recent(history+misses, p, ev, intervention()), empty)

    def test_tbs_recent_uses_perception_without_modifying_real_offer_or_crossing_blocks(self):
        ev = {'points': 100, 'target': 930, 'remaining': 4, 'multiplier': 2.3, 'block': 2,
              'options': [{'id': 'safe', 'amount': 180, 'probability': .6},
                          {'id': 'risky', 'amount': 260, 'probability': .35}]}
        history = [{'block': 2, 'choice': 'risky', 'outcome': 260, 'timed_out': False} for _ in range(6)]
        original = copy.deepcopy(ev)
        current = tbs_execution.reconsider(history, {}, ev, intervention())
        recent = tbs_execution.reconsider_recent(history, {}, ev, intervention())
        self.assertGreater(recent['risky'], current['risky'])
        self.assertEqual(ev, original)
        old_block = [{**r, 'block': 1} for r in history]
        self.assertEqual(tbs_execution.reconsider_recent(old_block, {}, ev, intervention()), current)
        with patch.object(tbs_execution, 'reconsider', return_value={'safe': .5, 'risky': .5}) as processor:
            tbs_execution.reconsider_recent(history, {}, ev, intervention())
            perceived = processor.call_args.args[2]
            self.assertAlmostEqual(perceived['options'][1]['probability'], (4*.35+6)/10)
        unknown = [{'block': 2, 'choice': None, 'outcome': 260, 'timed_out': False}]
        self.assertEqual(tbs_execution.reconsider_recent(unknown, {}, ev, intervention()), current)

    def test_null_and_direct_are_invariant_across_processors(self):
        ev = {'points': 0, 'target': 930, 'remaining': 4, 'multiplier': 2.3, 'block': 1,
              'options': [{'id': 'safe', 'amount': 180, 'probability': .6},
                          {'id': 'risky', 'amount': 260, 'probability': .35}]}
        direct = []; null = []
        for mechanism in ('none', 'current', 'recent'):
            a = Participant(SPEC, 'TBS', 'responsive', mechanism)
            direct.append(a.distribution(ev, intervention('direct'))[1])
            null.append(Participant(SPEC, 'TBS', 'null', mechanism).distribution(ev, intervention())[1])
        self.assertTrue(all(v == direct[0] for v in direct))
        self.assertTrue(all(v == null[0] for v in null))
        self.assertEqual(null[0], Participant(SPEC, 'TBS').baseline(ev))


class PilotTest(unittest.TestCase):
    def configuration(self, directory, cap=None):
        actors = [{'id': 'pilot_reference', 'source': 'Engineering fixture', 'task_models': {'REFERENCE': {'right_bias': .5}}}]
        write(directory/'actors.json', actors)
        config = {'id': 'pilot-test', 'participants_file': 'actors.json', 'expected_participants': 1,
                  'cohort_split': 'engineering', 'study': {'id': 'pilot-test',
                  'tasks': {'REFERENCE': {'protocol': 'mini', 'calibration_tasks': ['REFERENCE']}},
                  'conditions': ['A', 'C', 'E', 'D', 'F']},
                  'mechanisms': ['none', 'current', 'recent'], 'response_parameters': RESPONSE,
                  'seed': 'pilot-test', 'repeats': 1,
                  'primary_outcomes': {'REFERENCE': {'metric': 'decision_errors', 'divisor': 1}}}
        if cap is not None:
            config['max_trials'] = cap
        write(directory/'config.json', config)
        return directory/'config.json'

    def test_resume_matched_controls_private_parameters_and_frozen_inputs(self):
        # Exercise the optional adapter contract without adding a fake empirical
        # environment or changing reference runtime behaviour outside this test.
        def recent(history, parameters, evaluation, intervention):
            return {o['id']: 1-o['probability'] for o in evaluation['options']}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(reference_execution, 'reconsider_recent', recent, create=True), \
             patch.object(reference_execution, 'RECENT_RECONSIDERATION', {'fixture': 'recent'}, create=True), \
             patch('socratic_prototype.engine.shacl_report', return_value={'conforms': True, 'engine': 'fixture', 'report': 'Covered by real integration'}), \
             patch.dict('os.environ', {'SOCRATIC_LLM': 'offline', 'SOCRATIC_LANGUAGE_MODE': 'bounded'}):
            directory = Path(temp);config = self.configuration(directory);out = directory/'output'
            first = execute(out, config, max_jobs=1, progress=None)
            self.assertEqual(first['completed_jobs'], 1)
            self.assertFalse(first['complete']);self.assertEqual(first['aggregates'], [])
            completed_file = next((out/'jobs').glob('*/result.json'))
            first_bytes = completed_file.read_bytes()
            report = execute(out, progress=None)
            self.assertTrue(report['complete']);self.assertEqual(report['completed_jobs'], 3)
            self.assertTrue(report['control_checks_passed'])
            self.assertEqual(completed_file.read_bytes(), first_bytes)
            self.assertEqual(report['completed_protocol_sessions'], 15)
            self.assertTrue(report['mechanism_sensitivity'])
            from socratic_prototype.store import Store
            for result in (out/'jobs').glob('*/result.json'):
                job = read(result);path = out/job['report_file']
                full = read(path);store = Store(path.parent/'sessions.sqlite3')
                for row in full['runs']:
                    public = json.dumps(store.get(row['session_id']))
                    for name in ('response_parameters', 'reconsideration_mechanism', 'right_bias', 'processing_target'):
                        self.assertNotIn(name, public)
                    self.assertTrue(store.replay(row['session_id'])['matches'])
                    for trial in row['trials']:
                        if trial['effect'].get('applied'):
                            self.assertEqual(trial['effect']['parameters'], RESPONSE)
            unchanged = read(config);unchanged['response_parameters']['responsiveness'] = .8;write(config, unchanged)
            with self.assertRaisesRegex(ValidationError, 'configuration changed'):
                execute(out, config, prepare_only=True, progress=None)
            frozen = read(out/'participants.json');frozen[0]['id'] = 'tampered';write(out/'participants.json', frozen)
            with self.assertRaisesRegex(ValidationError, 'actor inputs were altered'):
                execute(out, prepare_only=True, progress=None)

    def test_unsupported_recent_extension_fails_before_session_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp);config = self.configuration(directory)
            with self.assertRaisesRegex(ValidationError, 'not implemented'):
                execute(directory/'output', config, progress=None)
            self.assertEqual(list((directory/'output').glob('**/sessions.sqlite3')), [])

    def test_capped_jobs_are_not_outcome_estimates_and_failed_attempts_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(reference_execution, 'reconsider_recent', reference_execution.reconsider, create=True), \
             patch.object(reference_execution, 'RECENT_RECONSIDERATION', {'fixture': True}, create=True), \
             patch('socratic_prototype.engine.shacl_report', return_value={'conforms': True, 'engine': 'fixture', 'report': 'Covered separately'}), \
             patch.dict('os.environ', {'SOCRATIC_LLM': 'offline', 'SOCRATIC_LANGUAGE_MODE': 'bounded'}):
            directory = Path(temp);config = self.configuration(directory, cap=2);out = directory/'output'
            with patch('socratic_prototype.pilot.simulate', side_effect=RuntimeError('fixture interruption')):
                with self.assertRaisesRegex(RuntimeError, 'fixture interruption'):
                    execute(out, config, progress=None)
            self.assertEqual(read(out/'status.json')['status'], 'failed')
            report = execute(out, progress=None)
            self.assertEqual(report['completed_jobs'], 3)
            self.assertFalse(report['complete']);self.assertEqual(report['aggregates'], [])
            self.assertEqual(report['completed_protocol_sessions'], 0)
            self.assertEqual(len(list((out/'jobs').glob('*/attempts/*'))), 4)
            self.assertEqual(len(list((out/'jobs').glob('*/result.json'))), 3)


if __name__ == '__main__':
    unittest.main()
