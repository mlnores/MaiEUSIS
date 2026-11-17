"""One profile response rule, retired-mode guards and resumable pilot checks."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.agents import Participant
from socratic_prototype.assistance_response import apply, conditional_preferences
from socratic_prototype.pilot import execute, read, write
from socratic_prototype.records import ValidationError
from socratic_prototype.tasks import mab_execution, tbs_execution, reference_execution

SPEC={'id':'single_fixture','source':'Authored engineering fixture',
      'task_models':{'MAB':{'alpha_plus':.4,'alpha_minus':.3,'beta':2},
                     'TBS':{'intercept':0,'slope':1}},'baseline_omission':{'MAB':.01,'TBS':.02}}
RESPONSE={'responsiveness':.5,'reactance':0,'distraction':0,'omission_probability':0}


def intervention(style='socratic'):
    return {'style':style,'focus':'value_revision',
            'recommendation':{'option_id':'risky'} if style=='direct' else None}


class SingleResponseTest(unittest.TestCase):
    def test_retired_modes_are_rejected_and_no_recent_hook_remains(self):
        for task in ('MAB','TBS'):
            for mode in ('none','recent'):
                with self.assertRaisesRegex(ValidationError,'retired'):Participant(SPEC,task,'responsive',mode)
        self.assertFalse(hasattr(mab_execution,'reconsider_recent'))
        self.assertFalse(hasattr(tbs_execution,'reconsider_recent'))

    def test_direct_singleton_and_pair_share_conditioning_and_receptiveness(self):
        base={'a':.5,'b':.3,'c':.2}
        direct={'style':'direct','recommendation':{'option_id':'b'}}
        pair={'style':'socratic'}
        for rho in (0.,.25,.5,.75,1.):
            parameters={**RESPONSE,'responsiveness':rho}
            for offered,question in ((['b'],direct),(['a','b'],pair)):
                target=conditional_preferences(base,offered)
                result,effect=apply(base,question,parameters,target)
                for a in base:self.assertAlmostEqual(result[a],(1-rho)*base[a]+rho*target[a])
                self.assertEqual(effect['parameters'],parameters)
        self.assertEqual(conditional_preferences({'a':1.,'b':0.},['b']),{'a':0.,'b':1.})

    def test_silent_actor_still_learns_and_direct_never_calls_socratic_processor(self):
        ev={'options':[{'id':a} for a in mab_execution.ARMS]}
        actor=Participant(SPEC,'MAB','responsive');before=actor.baseline(ev)
        actor.observe({},dict(trial_id='fixture_trial_1',choice='blue1',outcome=100,timed_out=False))
        base,result,effect=actor.distribution(ev,None)
        self.assertNotEqual(before,base);self.assertEqual(base,result)
        self.assertEqual(effect['omission_probability'],.01)
        recommendation={'style':'direct','recommendation':{'option_id':'blue1'}}
        with patch.object(actor,'reconsider',side_effect=AssertionError('direct invoked Socratic processor')):
            actor.distribution(ev,recommendation)

    def test_tbs_keeps_one_displayed_evidence_response_without_memory_distortion(self):
        ev={'points':100,'target':930,'remaining':4,'multiplier':2.3,'block':2,
            'options':[{'id':'safe','amount':180,'probability':.6},{'id':'risky','amount':260,'probability':.35}]}
        original=copy.deepcopy(ev)
        h=[{'block':2,'choice':'risky','outcome':260,'timed_out':False} for _ in range(6)]
        self.assertEqual(tbs_execution.reconsider([],{},ev,intervention()),
                         tbs_execution.reconsider(h,{},ev,intervention()))
        self.assertEqual(ev,original)
        target=tbs_execution.reconsider(h,{},ev,intervention())
        base,actual,_=Participant(SPEC,'TBS','responsive').distribution(ev,intervention())
        for a in base:self.assertAlmostEqual(actual[a],.5*base[a]+.5*target[a])


class PilotTest(unittest.TestCase):
    def configuration(self, directory, cap=None):
        actors = [{'id': 'pilot_reference', 'source': 'Engineering fixture', 'task_models': {'REFERENCE': {'right_bias': .5}}}]
        write(directory/'actors.json', actors)
        config = {'id': 'pilot-test', 'participants_file': 'actors.json', 'expected_participants': 1,
                  'cohort_split': 'engineering', 'study': {'id': 'pilot-test',
                  'tasks': {'REFERENCE': {'protocol': 'mini', 'calibration_tasks': ['REFERENCE']}},
                  'conditions': ['A', 'C', 'E', 'D', 'F']},
                  'response_parameters': RESPONSE,
                  'seed': 'pilot-test', 'repeats': 2,
                  'primary_outcomes': {'REFERENCE': {'metric': 'decision_errors', 'divisor': 1}}}
        if cap is not None:
            config['max_trials'] = cap
        write(directory/'config.json', config)
        return directory/'config.json'

    def test_resume_matched_controls_private_parameters_and_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch('socratic_prototype.engine.shacl_report', return_value={'conforms': True, 'engine': 'fixture', 'report': 'Covered by real integration'}), \
             patch.dict('os.environ', {'SOCRATIC_LLM': 'offline', 'SOCRATIC_LANGUAGE_MODE': 'bounded'}):
            directory = Path(temp);config = self.configuration(directory);out = directory/'output'
            first = execute(out, config, max_jobs=1, progress=None)
            self.assertEqual(first['completed_jobs'], 1)
            self.assertFalse(first['complete']);self.assertEqual(first['aggregates'], [])
            completed_file = next((out/'jobs').glob('*/result.json'))
            first_bytes = completed_file.read_bytes()
            report = execute(out, progress=None)
            self.assertTrue(report['complete']);self.assertEqual(report['completed_jobs'], 2)
            self.assertTrue(report['control_checks_passed'])
            self.assertEqual(completed_file.read_bytes(), first_bytes)
            self.assertEqual(report['completed_protocol_sessions'], 10)
            self.assertEqual(report['mechanism_sensitivity'], [])
            self.assertEqual(len(report['controls']), 2)
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

    def test_retired_modes_fail_before_session_creation(self):
        for modes in (['none'], ['recent'], ['none','current','recent']):
            with tempfile.TemporaryDirectory() as temp:
                directory=Path(temp);config=self.configuration(directory)
                data=read(config);data['mechanisms']=modes;write(config,data)
                with self.assertRaisesRegex(ValidationError,'retired'):
                    execute(directory/'output',config,progress=None)
                self.assertEqual(list((directory/'output').glob('**/sessions.sqlite3')),[])

    def test_zero_receptiveness_is_the_control_without_a_separate_socratic_mode(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch('socratic_prototype.engine.shacl_report',return_value={'conforms':True,'report':'Covered separately'}), \
             patch.dict('os.environ',{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'}):
            root=Path(temp);config=self.configuration(root)
            data=read(config);data['repeats']=1
            data['response_parameters']={k:0 for k in RESPONSE};write(config,data)
            result=execute(root/'output',config,progress=None)
            self.assertTrue(result['control_checks_passed'])
            self.assertEqual(len(result['null_response_checks']),5)
            self.assertTrue(all(r['identical_to_A'] for r in result['null_response_checks']))

    def test_unassisted_control_detects_a_changed_distribution(self):
        from socratic_prototype.pilot import summarise
        report={'study':{'execution':{'REFERENCE':{'metrics':{'decision_errors':{'direction':'minimize'}}}}},
                'runs':[{'task':'REFERENCE','condition':'A','session_id':'fixture','completed':False,
                         'metrics':{'decision_errors':0},'trials':[{'index':1,'choice':'left','outcome':1,
                             'baseline_probabilities':{'left':.5,'right':.5},
                             'assisted_probabilities':{'left':1.,'right':0.},'effect':{'applied':False},'intervention':None}]}]}
        rows=summarise(report,{'participant':'fixture','repeat':0,'mechanism':'current'},
                       {'configuration':{'primary_outcomes':{'REFERENCE':{'metric':'decision_errors','divisor':1}}}})
        self.assertFalse(rows[0]['baseline_control_passed'])

    def test_capped_jobs_are_not_outcome_estimates_and_failed_attempts_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch('socratic_prototype.engine.shacl_report', return_value={'conforms': True, 'engine': 'fixture', 'report': 'Covered separately'}), \
             patch.dict('os.environ', {'SOCRATIC_LLM': 'offline', 'SOCRATIC_LANGUAGE_MODE': 'bounded'}):
            directory = Path(temp);config = self.configuration(directory, cap=2);out = directory/'output'
            with patch('socratic_prototype.pilot.simulate', side_effect=RuntimeError('fixture interruption')):
                with self.assertRaisesRegex(RuntimeError, 'fixture interruption'):
                    execute(out, config, progress=None)
            self.assertEqual(read(out/'status.json')['status'], 'failed')
            report = execute(out, progress=None)
            self.assertEqual(report['completed_jobs'], 2)
            self.assertFalse(report['complete']);self.assertEqual(report['aggregates'], [])
            self.assertEqual(report['completed_protocol_sessions'], 0)
            self.assertEqual(len(list((out/'jobs').glob('*/attempts/*'))), 3)
            self.assertEqual(len(list((out/'jobs').glob('*/result.json'))), 2)


if __name__ == '__main__':
    unittest.main()
