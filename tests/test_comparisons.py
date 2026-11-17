"""Evidence-backed human guidance and distinct participant processing assumptions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.agents import Participant
from socratic_prototype.argumentation import ARG
from socratic_prototype.comparisons import from_graph
from socratic_prototype.demo import evaluation
from socratic_prototype.grounding import build_evidence_package, prompt_package, realise_question
from socratic_prototype.intervention_policy import decide, validate_decision
from socratic_prototype.records import ValidationError
from socratic_prototype.store import Store
from socratic_prototype.tasks import mab, mab_execution, tbs_execution
from socratic_prototype.recommendations import structured

SPEC={'id':'comparison_actor','source':'Authored engineering fixture',
      'task_models':{'MAB':{'alpha_plus':.4,'alpha_minus':.3,'beta':2},'TBS':{'intercept':0,'slope':1}}}


class ComparisonTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'sessions.sqlite3')
        self.env=patch.dict('os.environ',{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'})
        self.env.start();self.addCleanup(self.env.stop)

    def mab_case(self):
        s=self.store.create(dict(participant_id='comparison',task='MAB',condition='A',phase='calibration',protocol='short',preference='standard'))
        score=0
        for i in range(1,10):
            ev=evaluation('MAB',s['id'],i,score=score);self.store.event(s['id'],ev)
            option,gain=('blue1',100) if i<=3 else ('red1',-200);score+=gain
            self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=i,
                choice=option,outcome=gain,score_after=score,timed_out=False,response_ms=500))
        record=self.store.event(s['id'],evaluation('MAB',s['id'],10,score=score))
        return self.store.get(s['id']),record

    def decision(self,s,record,condition='D'):
        snapshot=copy.deepcopy(record['snapshot'])
        session={**s,'condition':condition,'phase':'assisted'}
        snapshot['decision']=decide(session,record['input'],snapshot,record['id'])
        validate_decision(snapshot)
        return session,snapshot

    def test_mab_guidance_has_multiple_proven_alternatives_and_cannot_be_tampered(self):
        s,record=self.mab_case()
        for condition in ('D','F'):
            session,snapshot=self.decision(s,record,condition)
            d=snapshot['decision'];options=d['intervention']['comparisons']
            self.assertGreaterEqual(len(options),2);self.assertLessEqual(len(options),3)
            self.assertIsNone(d['intervention']['recommendation'])
            self.assertIn('prior-based uncertainty',d['comparison_context'])
            self.assertIn('BLUE1',d['comparison_context'])
            self.assertNotIn('demonstrated good',d['comparison_context'])
            arguments={a['id']:a for a in snapshot['graph_argumentation']['arguments']}
            for option in options:
                self.assertEqual(option['key'],mab.KEYS[option['option_id']])
                for aid in option['argument_ids']:
                    self.assertEqual(arguments[aid]['label'],'accepted')
                    self.assertIn(aid,d['argument_ids'])
            selected=next(c for c in d['candidates'] if c['id']==d['selected_candidate'])
            package=build_evidence_package(session,record['input'],snapshot,selected,[])
            self.assertEqual(package['comparisons'],options)
            self.assertNotIn(record['id'],str(prompt_package(package)))
            bad=copy.deepcopy(snapshot)
            candidate=next(c for c in bad['decision']['candidates'] if c['comparisons'])
            candidate['comparisons'][0]['details']['estimated_value']=99999
            with self.assertRaisesRegex(ValidationError,'Comparison differs'):validate_decision(bad)
            bad=copy.deepcopy(snapshot);bad['decision']['comparison_context']='Choose RED3 now.'
            with self.assertRaisesRegex(ValidationError,'Delivered comparison differs'):validate_decision(bad)
            # Generated wording cannot remove or rewrite the independently rendered guidance.
            config={**s['language_configuration'],'provider':'ollama','mode':'generated','model':'fixture'}
            proposal={'action':package['action'],'evidence_refs':package['required_evidence_refs'],
                      'uncertainty_refs':['u0'],'question':'What evidence would help compare these alternatives?','updates':[]}
            with patch('socratic_prototype.grounding.request_ollama',return_value=(proposal,'fixture')):
                language=realise_question(package,selected['messages'],config=config)
            self.assertEqual(language['mode'],'ollama-generated')
            self.assertEqual(language,realise_question(package,selected['messages'],recorded=language,config=config))
        for condition in ('C','E'):
            _,snapshot=self.decision(s,record,condition)
            self.assertFalse(snapshot['decision']['intervention']['comparisons'])
            self.assertIsNotNone(snapshot['decision']['intervention']['recommendation'])
        self.assertTrue(self.store.replay(s['id'])['matches'])

    def test_missing_or_rejected_comparison_proofs_do_not_create_a_shortlist(self):
        s,record=self.mab_case();snapshot=copy.deepcopy(record['snapshot'])
        report=snapshot['graph_argumentation'];assertions={a['id']:a for a in report['assertions']}
        proofs=[a for a in report['arguments'] if assertions[a['conclusion']]['proposition']['predicate']==ARG+'worthComparingFor']
        for proof in proofs:proof['label']='rejected'
        self.assertEqual(from_graph('MAB',record['input'],snapshot),[])
        for proof in proofs[:1]:proof['label']='accepted'
        self.assertEqual(from_graph('MAB',record['input'],snapshot),[])
        report['status']='limited'
        self.assertEqual(from_graph('MAB',record['input'],snapshot),[])

    def test_tbs_guidance_compares_both_displayed_options_with_no_invented_attainment(self):
        s=self.store.create(dict(participant_id='comparison',task='TBS',condition='A',phase='calibration',protocol='short',preference='standard'))
        points=0
        for i in range(1,9):
            ev=evaluation('TBS',s['id'],i,points=points);record=self.store.event(s['id'],ev)
            _,snapshot=self.decision(self.store.get(s['id']),record)
            d=snapshot['decision'];options=from_graph('TBS',ev,snapshot)
            self.assertEqual([c['option_id'] for c in options],['safe','risky'])
            if d['action']!='silence':
                self.assertIn('SAFE',d['comparison_context']);self.assertIn('RISKY',d['comparison_context'])
                if i<8:self.assertNotIn('final target-attainment chance',d['comparison_context'])
                else:self.assertIn('final target-attainment chance',d['comparison_context'])
            self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=i,
                choice='safe',outcome=0,points_after=points,timed_out=False,response_ms=500))
        self.assertTrue(self.store.replay(s['id'])['matches'])

    def test_guided_processing_uses_the_comparison_set_without_an_automatic_bonus(self):
        history=[{'trial_id':f't{i}','choice':'blue1' if i<12 else 'red2',
                  'outcome':100 if i<12 else -200,'timed_out':False} for i in range(18)]
        ev={'options':[{'id':a} for a in mab.ARMS]}
        question={'style':'socratic','focus':'exploration','recommendation':None,
                  'comparisons':[{'option_id':'blue1'},{'option_id':'red2'}]}
        p=SPEC['task_models']['MAB']
        current=mab_execution.reconsider(history,p,ev,question)
        self.assertGreater(current['blue1'],current['red2'])
        self.assertTrue(all(current[a]==0 for a in mab.ARMS if a not in ('blue1','red2')))
        for mechanism in ('current',):
            actor=Participant(SPEC,'MAB','null',mechanism);actor.history=history
            base,assisted,_=actor.distribution(ev,question);self.assertEqual(base,assisted)
            actor=Participant(SPEC,'MAB','responsive',mechanism);actor.history=history
            base,assisted,_=actor.distribution(ev,{**question,'comparisons':[]})
            self.assertEqual(base,assisted)

    def test_task_without_comparison_hooks_retains_its_existing_processor(self):
        candidate={'name':'reference_values','supporting_arguments':[],'opposing_arguments':[]}
        intervention=structured('REFERENCE','D',candidate)
        self.assertNotIn('comparisons',intervention)

    def test_under_sampled_but_unpromising_reward_does_not_enter_the_comparison(self):
        s=self.store.create(dict(participant_id='unpromising',task='MAB',condition='A',phase='calibration',protocol='short',preference='standard'))
        score=0
        for i in range(1,17):
            ev=evaluation('MAB',s['id'],i,score=score);self.store.event(s['id'],ev)
            option,gain=('red3',-200) if i<=4 else ('blue1',100)
            score+=gain
            self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=i,
                choice=option,outcome=gain,score_after=score,timed_out=False,response_ms=500))
        record=self.store.event(s['id'],evaluation('MAB',s['id'],17,score=score))
        choices=from_graph('MAB',record['input'],record['snapshot'])
        self.assertGreaterEqual(len(choices),2)
        self.assertNotIn('red3',[c['option_id'] for c in choices])


if __name__=='__main__':unittest.main()
