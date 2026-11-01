"""Separation, information boundaries, matched environments and response assumptions."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from socratic_prototype.agents import Participant,validate_participant
from socratic_prototype.assistance_response import apply,SCENARIOS
from socratic_prototype.participant_model import interaction_estimate,selection_cost
from socratic_prototype.simulation import Environment,run
from socratic_prototype.store import Store
from socratic_prototype.demo import evaluation
from socratic_prototype.records import ValidationError,CONDITIONS
from socratic_prototype.recommendations import from_graph
from socratic_prototype.intervention_policy import decide,validate_decision

SPEC={'id':'synthetic_model_test','source':'Assumed test parameters, not human data',
      'task_models':{'MAB':{'alpha_plus':.45,'alpha_minus':.45,'beta':2},'TBS':{'intercept':0,'slope':1.5}}}

class SeparationTest(unittest.TestCase):
    def test_response_null_reactance_and_distraction_do_not_assume_benefit(self):
        base={'safe':.8,'risky':.2};i={'style':'direct','recommendation':{'option_id':'risky'}}
        result,_=apply(base,i,SCENARIOS['null']['direct'],base);self.assertEqual(result,base)
        p={**SCENARIOS['null']['direct'],'responsiveness':1}
        self.assertEqual(apply(base,i,p,base)[0],{'safe':0,'risky':1})
        self.assertEqual(apply(base,i,{**p,'reactance':1},base)[0],{'safe':1,'risky':0})
        self.assertEqual(apply(base,i,{**p,'distraction':1},base)[0],{'safe':.5,'risky':.5})
        q={'style':'socratic','focus':'target_pressure','recommendation':None}
        self.assertEqual(apply(base,q,p,base)[0],base,'Reconsidering can reaffirm the existing choice')

    def test_invalid_parameters_and_independent_actor_resets(self):
        with self.assertRaises(ValidationError):validate_participant({**SPEC,'hidden_truth':{}})
        with self.assertRaises(ValidationError):validate_participant({**SPEC,'task_models':{'MAB':{'alpha_plus':2,'alpha_minus':.4,'beta':2},'TBS':{'intercept':0,'slope':0}}})
        ev=evaluation('MAB','test',1);a=Participant(SPEC,'MAB');b=Participant(SPEC,'MAB')
        before=b.baseline(ev);a.observe(ev,dict(choice='blue1',outcome=100,timed_out=False,trial_id='t'))
        self.assertNotEqual(a.baseline(ev),before);self.assertEqual(b.baseline(ev),before)

    def test_personalisation_has_no_automatic_bonus_or_oracle(self):
        s={'condition':'F','events':[]};person={'interaction':interaction_estimate(s)}
        self.assertEqual(selection_cost(.12,person),.12)
        self.assertNotIn('responsiveness',str(person));self.assertEqual(person['interaction']['status'],'unknown')
        s['events']=[{'id':'report','input':{'kind':'response','feedback':'fewer'}}]
        self.assertGreater(selection_cost(.12,{'interaction':interaction_estimate(s)}),.12)
        self.assertEqual(interaction_estimate({**s,'condition':'D'})['status'],'withheld')

    def test_participant_model_version_is_frozen_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'s.sqlite3')
            session=store.create(dict(participant_id='version',task='MAB',condition='A',phase='calibration',protocol='short',preference='standard'))
            session['participant_model_version']='older';store.save(session)
            with self.assertRaisesRegex(ValidationError,'Participant model changed'):
                store.event(session['id'],evaluation('MAB',session['id'],1))
            self.assertEqual(store.get(session['id'])['events'],[])

    def test_environment_common_streams_targets_and_final_multiplier(self):
        for task in ['MAB','TBS']:
            a=Environment(task,'short','paired');b=Environment(task,'short','paired')
            for n in range(1,25):
                ea=a.evaluation('a',n);eb=b.evaluation('b',n)
                self.assertEqual({k:v for k,v in ea.items() if k!='trial_id'},{k:v for k,v in eb.items() if k!='trial_id'})
                option=ea['options'][0]['id'];fa=a.outcome(ea,option);fb=b.outcome(eb,option)
                self.assertEqual(fa['outcome'],fb['outcome'])
        env=Environment('TBS','short','final');ev=evaluation('TBS','final',8,points=200);ev['multiplier']=2.3
        env.points=200
        with patch('socratic_prototype.simulation.uniform',return_value=0):result=env.outcome(ev,'safe')
        self.assertEqual(result['points_after'],result['outcome']+200)
        self.assertEqual(env.blocks[0]['score'],result['points_after']*2.3)

class GraphRecommendationTest(unittest.TestCase):
    def test_mab_comparison_and_tbs_direct_vs_socratic_and_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'s.sqlite3')
            for task in ['MAB','TBS']:
                s=store.create(dict(participant_id='recommendation',task=task,condition='A',phase='calibration',protocol='short',preference='standard'))
                score=points=0
                for index in range(1,7):
                    ev=evaluation(task,s['id'],index,score=score,points=points);store.event(s['id'],ev)
                    gain=100 if task=='MAB' else 0;score+=gain;points+=gain
                    store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=index,choice='blue1' if task=='MAB' else 'safe',outcome=gain,
                        score_after=score, timed_out=False,response_ms=700) if task=='MAB' else dict(kind='feedback',trial_id=ev['trial_id'],index=index,choice='safe',outcome=0,points_after=points,timed_out=False,response_ms=700))
                ev=evaluation(task,s['id'],7,score=score,points=points);record=store.event(s['id'],ev);snap=record['snapshot']
                self.assertIsNotNone(from_graph(task,ev,snap['graph_argumentation']))
                snap['decision']=decide({**s,'condition':'C','phase':'assisted'},ev,snap,record['id']);validate_decision(snap)
                d=snap['decision'];self.assertEqual(d['action'],'advise');self.assertIsNotNone(d['intervention']['recommendation'])
                candidate=next(c for c in d['candidates'] if c['id']==d['selected_candidate'])
                bad=copy.deepcopy(snap);bad['decision']['candidates'][0]['recommendation']['option_id']='invented'
                with self.assertRaises(ValidationError):validate_decision(bad)
                snap['decision']=decide({**s,'condition':'D','phase':'assisted'},ev,snap,record['id']);validate_decision(snap)
                self.assertIsNone(snap['decision']['intervention']['recommendation'])
            self.assertEqual(CONDITIONS,{'A','C','D','E','F'})

    def test_null_runner_preserves_choices_and_outcomes_across_five_conditions(self):
        # Numerical and graph checks remain real. Full SHACL integration is covered
        # by the task/argumentation suites, rather than repeated for every fixture.
        with tempfile.TemporaryDirectory() as td,patch.dict('os.environ',{'SOCRATIC_LLM':'offline'}),patch('socratic_prototype.engine.shacl_report',return_value={'conforms':True,'engine':'test-fixture','report':'SHACL covered in separate integration tests'}):
            store=Store(Path(td)/'s.sqlite3');report=run(store,[SPEC],max_trials=2)
            self.assertEqual(len(report['runs']),10)
            for task in ['MAB','TBS']:
                runs=[r for r in report['runs'] if r['task']==task]
                self.assertEqual({r['condition'] for r in runs},CONDITIONS)
                baseline=[(t['choice'],t['outcome']) for t in runs[0]['trials']]
                for row in runs:
                    self.assertEqual([(t['choice'],t['outcome']) for t in row['trials']],baseline)
                    s=store.get(row['session_id']);self.assertTrue(s['synthetic']);self.assertIn('synthetic_run',s)
                    self.assertNotIn('task_models',s);self.assertNotIn('response_parameters',str(s))
                    self.assertTrue(store.replay(s['id'])['matches'])
