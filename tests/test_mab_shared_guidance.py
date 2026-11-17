"""Shared public rankings, performance gating and private two-option responses."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.agents import Participant
from socratic_prototype.comparisons import from_graph
from socratic_prototype.demo import evaluation
from socratic_prototype.intervention_policy import decide, validate_decision
from socratic_prototype.records import ValidationError
from socratic_prototype.store import Store
from socratic_prototype.tasks import mab, mab_execution
from socratic_prototype.tasks.mab_guidance import DEFAULTS, assess, ranking


def history(choices):
    return [dict(trial_id=f'fixture_trial_{i}',choice=a,outcome=r,timed_out=False)
            for i,(a,r) in enumerate(choices,1)]


class PerformanceTest(unittest.TestCase):
    def assess(self,h,remaining=20,environment=None):
        return assess(h,environment or mab.mab_environment(h,.15),remaining,DEFAULTS)['performance']

    def test_successful_persistence_and_one_loss_are_silent_but_sustained_losses_qualify(self):
        wins=history([('blue1',100)]*12)
        self.assertFalse(self.assess(wins)['eligible'])
        one_loss=history([('blue1',100)]*11+[('blue1',-100)])
        self.assertFalse(self.assess(one_loss)['eligible'])
        losses=history([('blue1',-100)]*6)
        self.assertTrue(self.assess(losses)['eligible'])
        self.assertFalse(self.assess(losses[:5])['eligible'])
        self.assertFalse(self.assess(losses,2)['eligible'])
        # No opportunity headroom: zero returns alone do not justify a prompt.
        self.assertFalse(self.assess(history([('blue1',0)]*6))['eligible'])

    def test_misses_consume_window_positions_but_are_not_observed_losses(self):
        h=history([('blue1',-100)]*12)
        misses=[dict(trial_id=f'miss_{i}',choice='NO_RESPONSE',outcome=-200,timed_out=True) for i in range(7)]
        result=self.assess(h+misses)
        self.assertEqual(result['observations'],5)
        self.assertEqual(result['elapsed_trials'],12)
        self.assertFalse(result['eligible'])

    def test_positive_returns_can_underperform_a_supported_alternative(self):
        h=history([('blue1',100)]*12)
        env=mab.mab_environment(h,.15)
        arm=next(a for a in env['arms'] if a['arm']=='red1')
        arm.update(estimated_value=150,samples=24,approximate_95_interval=[130,170])
        result=self.assess(h,environment=env)
        self.assertTrue(result['eligible'])
        self.assertIn('below_supported_alternative',result['signals'])

    def test_tied_ranking_is_stable_and_does_not_claim_unique_superiority(self):
        env=mab.mab_environment([],.15)
        ordered=ranking(env)
        self.assertEqual([r['option_id'] for r in ordered],list(mab.ARMS))
        self.assertTrue(all(r['tie_count']==6 for r in ordered))
        env['arms'].reverse()
        self.assertEqual(ranking(env),ordered)


class ProfileResponseTest(unittest.TestCase):
    def setUp(self):
        self.ev={'options':[{'id':a} for a in mab.ARMS]}
        self.h=history([('blue1',100)]*6+[('red2',-200)]*6)
        self.question={'style':'socratic','focus':'exploration','recommendation':None,
                       'comparisons':[{'option_id':a,'criteria':['public_ranked_reward']} for a in ('blue1','red2')]}
        self.spec={'id':'pair_actor','source':'Authored engineering fixture',
                   'task_models':{'MAB':{'alpha_plus':.4,'alpha_minus':.3,'beta':2}}}

    def test_pair_weights_use_the_individuals_learning_and_choice_parameters(self):
        p=self.spec['task_models']['MAB'];base=mab_execution.baseline(self.h,p,self.ev)
        target=mab_execution.reconsider(self.h,p,self.ev,self.question)
        for a in ('blue1','red2'):
            self.assertAlmostEqual(target[a],base[a]/(base['blue1']+base['red2']))
        self.assertTrue(all(target[a]==0 for a in mab.ARMS if a not in ('blue1','red2')))
        other=mab_execution.reconsider(self.h,{**p,'beta':.1},self.ev,self.question)
        self.assertNotEqual(target,other)
        empirical={**p,'model':'handover_dual_rw_v1','reward_scale':100}
        eb=mab_execution.baseline(self.h,empirical,self.ev)
        et=mab_execution.reconsider(self.h,empirical,self.ev,self.question)
        self.assertAlmostEqual(et['blue1'],eb['blue1']/(eb['blue1']+eb['red2']))

    def test_receptiveness_mixes_the_pair_with_baseline(self):
        for rho in (0.,.25,.5,.75,1.):
            spec=copy.deepcopy(self.spec)
            params={'responsiveness':rho,'reactance':0,'distraction':0,'omission_probability':0}
            spec['response_parameters']={'MAB':{'direct':params,'socratic':params}}
            for mechanism in ('current',):
                actor=Participant(spec,'MAB','responsive',mechanism);actor.history=self.h
                base,result,effect=actor.distribution(self.ev,self.question)
                target=actor.reconsider(self.ev,self.question,base)
                for a in mab.ARMS:self.assertAlmostEqual(result[a],(1-rho)*base[a]+rho*target[a])
                if rho==1:self.assertTrue(all(result[a]==0 for a in mab.ARMS if a not in ('blue1','red2')))
                self.assertEqual(effect['parameters']['responsiveness'],rho)

    def test_recent_trials_do_not_erase_earlier_profile_learning(self):
        p=self.spec['task_models']['MAB']
        before=mab_execution.reconsider(self.h,p,self.ev,self.question)
        misses=[dict(trial_id=f'miss_{i}',choice='NO_RESPONSE',outcome=-200,timed_out=True) for i in range(6)]
        after=mab_execution.reconsider(self.h+misses,p,self.ev,self.question)
        self.assertEqual(before,after)
        poisoned={**self.ev,'hidden_probabilities':[1,0,0],'future_outcomes':[999999]}
        self.assertEqual(before,mab_execution.reconsider(self.h,p,poisoned,self.question))


class SharedGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.store=Store(Path(cls.temp.name)/'sessions.sqlite3')
        cls.env=patch.dict('os.environ',{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'})
        cls.env.start();cls.addClassCleanup(cls.env.stop)
        # Real numerical models, graph reasoning and record validation. The full
        # SHACL boundary is exercised once below instead of for every prefix.
        cls.shacl=patch('socratic_prototype.engine.shacl_report',return_value={'conforms':True,'report':'Separate real SHACL check'})
        cls.shacl.start();cls.addClassCleanup(cls.shacl.stop)
        cls.bad=cls.case([('blue1',100)]*3+[('red1',-200)]*6)
        cls.good=cls.case([('blue1',100)]*9)

    @classmethod
    def case(cls,choices):
        s=cls.store.create(dict(participant_id='shared_fixture',task='MAB',condition='A',phase='calibration',protocol='short',preference='standard'))
        score=0
        for i,(option,gain) in enumerate(choices,1):
            ev=evaluation('MAB',s['id'],i,score=score);cls.store.event(s['id'],ev);score+=gain
            cls.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=i,choice=option,outcome=gain,
                                       score_after=score,timed_out=False,response_ms=500))
        record=cls.store.event(s['id'],evaluation('MAB',s['id'],len(choices)+1,score=score))
        return cls.store.get(s['id']),record

    def decision(self,case,condition='D',snapshot=None,session=None):
        s,record=case;snapshot=copy.deepcopy(snapshot or record['snapshot'])
        snapshot['decision']=decide({**(session or s),'condition':condition,'phase':'assisted'},record['input'],snapshot,record['id'])
        validate_decision(snapshot)
        return snapshot

    def test_direct_and_socratic_use_the_same_first_and_second_ranked_options(self):
        expected=[r['option_id'] for r in self.bad[1]['snapshot']['environment']['guidance']['ranking'][:2]]
        for direct,socratic in (('C','D'),('E','F')):
            d=self.decision(self.bad,direct)['decision'];q=self.decision(self.bad,socratic)['decision']
            self.assertNotEqual(d['action'],'silence');self.assertNotEqual(q['action'],'silence')
            self.assertEqual(d['intervention']['recommendation']['option_id'],expected[0])
            self.assertEqual([c['option_id'] for c in q['intervention']['comparisons']],expected)
            self.assertEqual([c['details']['rank'] for c in q['intervention']['comparisons']],[1,2])
            self.assertIsNone(q['intervention']['recommendation'])
            self.assertEqual(d['assistance_gate'],q['assistance_gate'])
            self.assertTrue(set(q['assistance_gate']['argument_ids'])<=set(q['argument_ids']))

    def test_good_performance_suppresses_all_four_conditions_despite_underexploration(self):
        snap=self.good[1]['snapshot']
        self.assertTrue(any(h['name']=='underexploration' and h['eligible'] for h in snap['participant']['hypotheses']))
        for c in ('C','D','E','F'):
            d=self.decision(self.good,c)['decision']
            self.assertEqual(d['action'],'silence');self.assertEqual(d['candidates'],[])
            self.assertIn('Performance gate',d['rationale'])

    def test_missing_gate_or_pair_proofs_cannot_be_bypassed(self):
        snapshot=copy.deepcopy(self.bad[1]['snapshot'])
        gate=self.decision(self.bad)['decision']['assistance_gate']
        for a in snapshot['graph_argumentation']['arguments']:
            if a['id'] in gate['argument_ids']:a['label']='rejected'
        self.assertEqual(self.decision(self.bad,snapshot=snapshot)['decision']['action'],'silence')
        snapshot=copy.deepcopy(self.bad[1]['snapshot'])
        for a in snapshot['graph_argumentation']['arguments']:
            if a['rule']==mab.NAMESPACE+'rankedRewardComparison':a['label']='rejected'
        self.assertEqual(from_graph('MAB',self.bad[1]['input'],snapshot),[])
        self.assertEqual(self.decision(self.bad,snapshot=snapshot)['decision']['action'],'silence')
        active=self.decision(self.bad)
        active['decision']['assistance_gate']['eligible']=False
        with self.assertRaisesRegex(ValidationError,'Assistance gate'):validate_decision(active)
        active=self.decision(self.bad)
        active['environment']['guidance']['ranking'].reverse()
        with self.assertRaisesRegex(ValidationError,'shared ranking'):validate_decision(active)

    def test_delivery_cooldown_still_applies_after_the_gate_passes(self):
        s,record=self.bad;s=copy.deepcopy(s)
        s['events'].append({'input':{'kind':'delivery','delivered':True,'index':record['input']['index']-1}})
        d=self.decision(self.bad,session=s)['decision']
        self.assertTrue(d['assistance_gate']['eligible']);self.assertEqual(d['action'],'silence')
        self.assertIn('Cooldown',d['rationale'])

    def test_gate_and_comparison_strategy_can_be_varied_independently(self):
        for gate in (False,True):
            for strategy in ('legacy_uncertainty','shared_top_two'):
                snap=copy.deepcopy(self.good[1]['snapshot'])
                snap['environment']['guidance']['settings'].update(performance_gate=gate,comparison_strategy=strategy)
                result=self.decision(self.good,snapshot=snap)['decision']
                self.assertEqual(result['action']=='silence',gate)
                if not gate:
                    options=result['intervention']['comparisons']
                    if strategy=='shared_top_two':
                        self.assertEqual(len(options),2)
                        self.assertTrue(all('public_ranked_reward' in c['criteria'] for c in options))
                    else:
                        self.assertTrue(2<=len(options)<=3)
                        self.assertTrue(all('public_ranked_reward' not in c['criteria'] for c in options))

    def test_explicit_ungated_ablation_still_provides_two_options_for_horizon_clarification(self):
        case=self.case([('blue1',-100)]*38)
        snapshot=copy.deepcopy(case[1]['snapshot'])
        snapshot['environment']['guidance']['settings']['performance_gate']=False
        for condition in ('D','F'):
            d=self.decision(case,condition,snapshot=snapshot)['decision']
            self.assertEqual(d['action'],'ask')
            self.assertEqual(len(d['intervention']['comparisons']),2)
            self.assertIn('so few decisions',next(c for c in d['candidates'] if c['id']==d['selected_candidate'])['messages'][0])

    def test_real_shacl_export_and_replay_and_no_private_parameters_in_guidance(self):
        from rdflib import Graph, RDF, OWL
        from socratic_prototype.validation import shacl_report, turtle, graph_documents
        for case in (self.bad,self.good):
            self.assertTrue(self.store.replay(case[0]['id'])['matches'])
            # Validate the complete exported graph as well as the incremental
            # delivery boundary, including the initial unknown performance gap.
            for incremental in (False,True):
                report=shacl_report(case[0],incremental=incremental)
                self.assertTrue(report['conforms'],report['report'])
        ont=Graph()
        for path in graph_documents(self.bad[0])[0]:ont.parse(path,format='turtle')
        graph=Graph().parse(data=turtle(self.bad[0]),format='turtle')
        declared=set(ont.subjects(RDF.type,OWL.ObjectProperty))|set(ont.subjects(RDF.type,OWL.DatatypeProperty))|set(ont.subjects(RDF.type,RDF.Property))
        used={p for p in graph.predicates() if str(p).startswith('https://example.org/socratic/')}
        self.assertEqual(used-declared,set())
        public=json_string(mab.evidence_environment(self.bad[1]['snapshot']['environment'])[0])
        for private in ('response_parameters','alpha_plus','alpha_minus','processing_target','fixture_trial_'):
            self.assertNotIn(private,public)


def json_string(value):
    import json
    return json.dumps(value)


if __name__=='__main__':unittest.main()
