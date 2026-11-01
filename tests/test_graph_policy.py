"""Graph-only intervention provenance, condition boundaries and uncertain delivery."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.argumentation import ARG,configuration
from socratic_prototype.demo import evaluation
from socratic_prototype.grounding import build_evidence_package,prompt_package
from socratic_prototype.intervention_policy import decide,validate_decision
from socratic_prototype.records import ValidationError
from socratic_prototype.semantics import CORE
from socratic_prototype.store import Store
from socratic_prototype.tasks import get_task

try:
    import rdflib
    HAS_RDF=True
except ImportError:HAS_RDF=False


class UnavailableTest(unittest.TestCase):
    def test_unavailable_reasoning_cannot_fall_back_to_independent_triggers(self):
        config=configuration(get_task('MAB'));config['backend']='unavailable'
        with tempfile.TemporaryDirectory() as td,patch('socratic_prototype.store.argumentation_configuration',return_value=config):
            store=Store(Path(td)/'s.sqlite3')
            session=store.create(dict(participant_id='unavailable',task='MAB',condition='A',phase='calibration',protocol='short',preference='standard'))
            record=store.event(session['id'],evaluation('MAB',session['id'],1))
            for condition in ['C','D','E','F']:
                projected={**session,'condition':condition,'phase':'assisted'}
                d=decide(projected,record['input'],record['snapshot'],record['id'])
                self.assertEqual(d['action'],'silence');self.assertEqual(d['candidates'],[])
                self.assertIn('unavailable',d['rationale'])
            self.assertTrue(store.replay(session['id'])['matches'])


@unittest.skipUnless(HAS_RDF,'Graph intervention integration requires RDFLib')
class GraphPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'s.sqlite3')

    def create(self,task='MAB'):
        return self.store.create(dict(participant_id='graph_policy',task=task,condition='A',phase='calibration',protocol='short',preference='standard'))

    def emit(self,s,ev,choice,outcome):
        self.store.event(s['id'],ev)
        self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=ev['index'],choice=choice,
            outcome=outcome,timed_out=False,response_ms=500,
            **{'points_after' if s['task']=='TBS' else 'score_after':ev.get('points',ev.get('score',0))+outcome}))

    def mab(self,index=7,arms=None,reward=0):
        s=self.create()
        for i in range(1,index):self.emit(s,evaluation('MAB',s['id'],i,score=(i-1)*reward),(arms or ['blue1'])[(i-1)%len(arms or ['blue1'])],reward)
        record=self.store.event(s['id'],evaluation('MAB',s['id'],index,score=(index-1)*reward))
        return self.store.get(s['id']),record

    def choice(self,s,e,condition='D'):
        projected={**s,'condition':condition,'phase':'assisted'}
        snap=copy.deepcopy(e['snapshot']);snap['decision']=decide(projected,e['input'],snap,e['id'])
        validate_decision(snap)
        return projected,snap

    def test_one_history_five_conditions_and_graph_proof_language_boundary(self):
        s,e=self.mab(9,reward=100)
        expected={'A':'silence','C':'advise','D':'request-evidence','E':'advise','F':'challenge'}
        for condition,action in expected.items():
            session,snap=self.choice(s,e,condition);d=snap['decision']
            self.assertEqual(d['action'],action,condition)
            if action=='silence':continue
            selected=next(c for c in d['candidates'] if c['id']==d['selected_candidate'])
            package=build_evidence_package(session,e['input'],snap,selected,[])
            self.assertTrue(package['arguments']['proofs'])
            self.assertEqual(package['arguments']['opposition'],'')
            if condition in {'C','D'}:
                self.assertEqual(package['participant'],{})
                self.assertNotIn('possiblePattern',str(package['arguments']))
                self.assertNotIn('underexploration',str(package['arguments']))
            self.assertNotIn(e['id'],str(prompt_package(package)))
            self.assertEqual(snap['arguments'],[])
        # Every label may remain accepted while A still forbids assistance.
        _,a=self.choice(s,e,'A');self.assertTrue(a['graph_argumentation']['arguments'])

    def test_condition_b_is_removed_from_sessions_studies_and_interface(self):
        import re
        from socratic_prototype.server import render_index
        from socratic_prototype.study import default_study,validate_study
        for phase in ['calibration','assisted']:
            with self.subTest(phase=phase),self.assertRaisesRegex(ValidationError,'Unknown condition'):
                self.store.create(dict(participant_id='removed',task='MAB',condition='B',phase=phase,protocol='short',preference='standard'))
        self.assertEqual(self.store.list(),[])
        study=default_study();study['conditions'].append('B')
        with self.assertRaisesRegex(ValidationError,'Invalid study conditions'):validate_study(study)
        selector=re.search(r'<select id="condition">(.*?)</select>',render_index(),re.S).group(1)
        self.assertEqual(set(re.findall(r'value="([^"]+)"',selector)),{'A','C','D','E','F'})

    def test_task_unaware_guidance_schemes_are_rejected(self):
        from socratic_prototype.argumentation import ROOT
        from socratic_prototype.argumentation.discovery import load_schemes
        contents=(ROOT/'schemes/shared.ttl').read_text().replace('arg:audience "personalised"','arg:audience "generic"')
        with self.assertRaisesRegex(ValidationError,'Invalid intervention audience'):load_schemes((contents,))

    def test_removing_graph_premises_removes_live_exploration_candidate(self):
        s,e=self.mab()
        from socratic_prototype.argumentation import discovery,analyse
        from socratic_prototype.argumentation.graph import build_input
        graph,assertions,facts=build_input(s,e)
        removed=next(a for a in assertions if a['proposition']['predicate']==CORE+'mab/sampledArmCount')
        graph.remove((rdflib.URIRef(removed['id']),None,None))
        with patch.object(discovery,'build_input',return_value=(graph,assertions,facts)):report=analyse(s,e)
        altered=copy.deepcopy(e);altered['snapshot']['graph_argumentation']=report
        _,snap=self.choice(s,altered)
        self.assertNotIn('unsampled_alternatives',[c['name'] for c in snap['decision']['candidates']])
        self.assertEqual(snap['decision']['action'],'support')

    def test_short_horizon_clarifies_conflict_and_does_not_challenge_persistence(self):
        s,e=self.mab(39)
        for condition in ['D','F']:
            _,snap=self.choice(s,e,condition);d=snap['decision']
            self.assertEqual(d['action'],'ask');self.assertIsNone(d['hypothesis'])
            c=next(c for c in d['candidates'] if c['id']==d['selected_candidate'])
            self.assertEqual(c['argument_evaluation'],'unresolved-clarification')
            self.assertTrue(c['opposing_arguments']);self.assertIn('so few decisions',c['messages'][0])
        for condition in ['C','E']:
            _,snap=self.choice(s,e,condition);self.assertEqual(snap['decision']['action'],'silence')
        g=e['snapshot']['graph_argumentation']
        model=next(a for a in g['arguments'] if a['rule']==ARG+'modelChallenge')
        self.assertEqual(model['label'],'rejected')

    def test_explicit_contestation_blocks_only_the_personalised_warrant(self):
        s,e=self.mab();hyp=next(h for h in e['snapshot']['participant']['hypotheses'] if h['name']=='underexploration')
        response={'id':'synthetic_contest','input':{'kind':'response','feedback':'disagree','text':'I have a deliberate strategy.',
            'index':6,'hypothesis':'underexploration'}}
        s['events'].insert(-1,response);hyp['contested_by']=[response['id']]
        from socratic_prototype.argumentation import analyse
        e['snapshot']['graph_argumentation']=analyse(s,e)
        _,snap=self.choice(s,e,'F');d=snap['decision']
        self.assertNotIn('underexploration',[c['name'] for c in d['candidates']])
        self.assertEqual(d['action'],'request-evidence')
        self.assertEqual(hyp['inference']['posterior'],.72)

    def test_limited_graph_is_silent_even_if_it_contains_accepted_warrants(self):
        s,e=self.mab();e=copy.deepcopy(e);e['snapshot']['graph_argumentation']['status']='limited'
        _,snap=self.choice(s,e,'F')
        self.assertEqual(snap['decision']['action'],'silence');self.assertEqual(snap['decision']['candidates'],[])

    def test_tbs_criteria_chain_drives_objective_question_and_provenance(self):
        s=self.create('TBS');points=0
        for i in range(1,8):
            ev=evaluation('TBS',s['id'],i,points=points)
            for option,pair in zip(ev['options'],get_task('TBS').RULES['options'][0]):option.update(amount=pair[0],probability=pair[1])
            gain=100 if i<=2 else 0;self.emit(s,ev,'safe',gain);points+=gain
        ev=evaluation('TBS',s['id'],8,points=points)
        for option,pair in zip(ev['options'],get_task('TBS').RULES['options'][1]):option.update(amount=pair[0],probability=pair[1])
        e=self.store.event(s['id'],ev);session,snap=self.choice(self.store.get(s['id']),e,'D');d=snap['decision']
        self.assertEqual(d['action'],'compare')
        selected=next(c for c in d['candidates'] if c['id']==d['selected_candidate'])
        self.assertEqual(selected['name'],'criteria_divergence')
        package=build_evidence_package(session,ev,snap,selected,[])
        rules={p['rule'] for p in package['arguments']['proofs']}
        for rule in ['expectedGainArgument','attainmentArgument','criteriaDivergenceArgument','objectiveQuestionArgument']:
            self.assertIn(CORE+'tbs/'+rule,rules)
        self.assertEqual(package['arguments']['opposition'],'')
        from socratic_prototype.recommendations import from_graph
        recommendation=from_graph('TBS',ev,snap['graph_argumentation'])
        self.assertEqual(recommendation['criterion'],'final_target_attainment')
        self.assertEqual(recommendation['option_id'],'risky')

    def test_tbs_gain_reason_does_not_leak_across_blocks(self):
        s=self.create('TBS');points=0
        for i in range(1,9):
            ev=evaluation('TBS',s['id'],i,points=points)
            for option,pair in zip(ev['options'],get_task('TBS').RULES['options'][0]):option.update(amount=pair[0],probability=pair[1])
            self.emit(s,ev,'safe',100);points+=100
        e=self.store.event(s['id'],evaluation('TBS',s['id'],9))
        _,snap=self.choice(self.store.get(s['id']),e)
        self.assertNotIn('gap_after_gain',[c['name'] for c in snap['decision']['candidates']])

    def test_boundary_rejects_tampered_proof_links(self):
        s,e=self.mab();_,snap=self.choice(s,e)
        bad=copy.deepcopy(snap);bad['decision']['argument_ids']=['urn:invented']
        with self.assertRaisesRegex(ValidationError,'proof differs'):validate_decision(bad)
        bad=copy.deepcopy(snap);c=bad['decision']['candidates'][0]
        target=next(a for a in bad['graph_argumentation']['arguments'] if a['id']==c['supporting_arguments'][0])
        target['label']='rejected'
        with self.assertRaisesRegex(ValidationError,'rejected'):validate_decision(bad)
