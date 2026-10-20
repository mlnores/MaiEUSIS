"""Graph discovery, structured attacks, uncertainty and shadow-only integration."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.argumentation import ARG,analyse,configuration
from socratic_prototype.argumentation.evaluation import grounded,evaluate
from socratic_prototype.argumentation.validation import validate_analysis
from socratic_prototype.demo import evaluation
from socratic_prototype.records import ValidationError
from socratic_prototype.semantics import CORE,DATA
from socratic_prototype.store import Store,configuration_fields,digest
from socratic_prototype.tasks import get_task
from socratic_prototype.validation import turtle,shacl_report

try:
    import rdflib
    HAS_RDF=True
except ImportError:HAS_RDF=False
try:
    import pyshacl
    HAS_SHACL=True
except ImportError:HAS_SHACL=False


def assertion(identifier,polarity='positive',kind='assumption',predicate=ARG+'test',scope='urn:state',subject='urn:subject',obj=None):
    return {'id':identifier,'proposition':{'scope':scope,'subject':subject,'predicate':predicate,
        'object':obj or {'type':'literal','value':True},'polarity':polarity},'kind':kind,
        'source':'urn:source','content':'Synthetic premise','statuses':['assumed']}


def argument(identifier,conclusion,rule='urn:rule',kind='defeasible',subs=(),premises=None,priority=0):
    return {'id':identifier,'conclusion':conclusion,'premises':premises or [conclusion],
            'subarguments':list(subs),'rule':rule,'rule_kind':kind,'priority':priority}


class EvaluationTest(unittest.TestCase):
    def test_grounded_cycles_and_defence(self):
        self.assertEqual(grounded(['a','b'],[('a','b'),('b','a')]),{'a':'undecided','b':'undecided'})
        self.assertEqual(grounded(['a','b','c'],[('a','b'),('b','c')]),{'a':'accepted','b':'rejected','c':'accepted'})
        self.assertEqual(grounded(['a'],[('a','a')]),{'a':'undecided'})

    def test_rebuttal_preferences_and_distinct_scopes(self):
        facts=[assertion('p'),assertion('notp','negative')]
        args=[argument('a','p'),argument('b','notp')]
        attacks,_=evaluate(facts,args)
        self.assertEqual({a['label'] for a in args},{'undecided'})
        self.assertEqual({a['kind'] for a in attacks},{'rebutting'})
        args[0]['priority']=1;evaluate(facts,args)
        self.assertEqual([a['label'] for a in args],['accepted','rejected'])
        facts[1]['proposition']['scope']='urn:later-state'
        self.assertEqual(evaluate(facts,args)[0],[])

    def test_undercut_rejects_dependent_strict_arguments(self):
        facts=[assertion('p'),assertion('q',predicate=ARG+'next'),
               assertion('u',predicate=ARG+'inapplicable',obj={'type':'iri','value':'urn:rule'})]
        args=[argument('a','p',priority=100),argument('b','q',kind='strict',subs=['a'],premises=['p']),
              argument('c','u',kind='strict')]
        attacks,_=evaluate(facts,args)
        self.assertEqual([a['label'] for a in args],['rejected','rejected','accepted'])
        self.assertEqual(attacks[0]['kind'],'undercutting');self.assertIn('b',attacks[0]['affected'])

    def test_undermining_an_ordinary_premise_propagates(self):
        facts=[assertion('p'),assertion('notp','negative'),assertion('q',predicate=ARG+'next')]
        args=[argument('a','p',rule=None,kind='premise'),argument('b','notp',kind='strict'),
              argument('c','q',kind='strict',subs=['a'],premises=['p'])]
        attacks,_=evaluate(facts,args)
        self.assertEqual([a['label'] for a in args],['rejected','accepted','rejected'])
        self.assertEqual(attacks[0]['kind'],'undermining')

    def test_different_criteria_are_not_contradictions(self):
        facts=[assertion('p',predicate='urn:higherEV'),assertion('q',predicate='urn:higherAttainment')]
        args=[argument('a','p'),argument('b','q')]
        self.assertEqual(evaluate(facts,args)[0],[])
        self.assertTrue(all(a['label']=='accepted' for a in args))

    def test_inconsistent_strict_rules_are_rejected(self):
        with self.assertRaisesRegex(ValidationError,'Inconsistent'):
            evaluate([assertion('p'),assertion('notp','negative')],
                     [argument('a','p',kind='strict'),argument('b','notp',kind='strict')])


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'sessions.sqlite3')

    def create(self,task='MAB'):
        return self.store.create(dict(participant_id='synthetic_argumentation',task=task,condition='A',
            phase='calibration',protocol='short',preference='standard'))

    def test_frozen_reasoner_drift_rejected_before_event_or_replay(self):
        s=self.create();bad=copy.deepcopy(s['argumentation_configuration']);bad['documents']['shared.ttl']='changed'
        with patch('socratic_prototype.store.argumentation_configuration',return_value=bad):
            with self.assertRaisesRegex(ValidationError,'Argumentation'):self.store.event(s['id'],evaluation('MAB',s['id'],1))
            with self.assertRaisesRegex(ValidationError,'argumentation_configuration'):self.store.replay(s['id'])
        self.assertEqual(self.store.get(s['id'])['events'],[])

    def test_old_sessions_do_not_gain_shadow_records(self):
        s=self.create();s.pop('argumentation_configuration')
        s['configuration_digest']=digest({k:s[k] for k in configuration_fields(s)});self.store.save(s)
        e=self.store.event(s['id'],evaluation('MAB',s['id'],1))
        self.assertNotIn('graph_argumentation',e['snapshot'])
        self.assertNotIn('@prefix arg:',turtle(self.store.get(s['id'])))
        self.assertTrue(self.store.replay(s['id'])['matches'])

    def test_dependency_absence_is_recorded_without_claiming_inference(self):
        s=self.create();s['argumentation_configuration']['backend']='unavailable'
        event={'id':'synthetic_event_1','input':evaluation('MAB',s['id'],1),'snapshot':{}}
        report=analyse(s,event)
        self.assertEqual(report['status'],'unavailable');self.assertEqual(report['arguments'],[])
        self.assertTrue(validate_analysis(report)['conforms'])


@unittest.skipUnless(HAS_RDF,'RDFLib research dependency not installed')
class DiscoveryTest(ConfigurationTest):
    test_frozen_reasoner_drift_rejected_before_event_or_replay=None
    test_old_sessions_do_not_gain_shadow_records=None
    test_dependency_absence_is_recorded_without_claiming_inference=None

    def emit(self,s,ev,choice,outcome):
        record=self.store.event(s['id'],ev)
        after=ev.get('points',ev.get('score',0))+outcome
        self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=ev['index'],choice=choice,
            outcome=outcome,timed_out=False,response_ms=500,**{'points_after' if s['task']=='TBS' else 'score_after':after}))
        return record

    def mab(self,index=8):
        s=self.create()
        for i in range(1,index):self.emit(s,evaluation('MAB',s['id'],i),'blue1',0)
        return s,self.store.event(s['id'],evaluation('MAB',s['id'],index))

    def test_mab_multistep_proofs_and_unanswered_questions(self):
        s,e=self.mab();r=e['snapshot']['graph_argumentation'];self.assertEqual(r['status'],'complete')
        coverage=next(a for a in r['arguments'] if a['rule']==CORE+'mab/coverageArgument')
        exploration=next(a for a in r['arguments'] if a['rule']==CORE+'mab/explorationArgument')
        self.assertIn(coverage['id'],exploration['subarguments']);self.assertEqual(exploration['label'],'accepted')
        self.assertEqual(r['attacks'],[],'Missing intent must not fabricate a counterargument')
        self.assertTrue(r['critical_questions'])
        facts={a['id']:a for a in r['assertions']}
        self.assertEqual(facts[exploration['conclusion']]['statuses'],['inferred'])
        self.assertEqual(facts[coverage['conclusion']]['statuses'],['known'])
        # Re-querying after removing a necessary premise removes that argument.
        from socratic_prototype.argumentation import discovery
        from socratic_prototype.argumentation.graph import build_input
        graph,claims,extra=build_input(self.store.get(s['id']),e)
        removed=next(a for a in claims if a['proposition']['predicate']==CORE+'mab/sampledArmCount')
        graph.remove((rdflib.URIRef(removed['id']),None,None))
        with patch.object(discovery,'build_input',return_value=(graph,claims,extra)):
            result=analyse(self.store.get(s['id']),e)
        self.assertFalse(any(a['rule']==CORE+'mab/coverageArgument' for a in result['arguments']))

    def test_short_horizon_discovers_independent_objection(self):
        s,e=self.mab(39);r=e['snapshot']['graph_argumentation']
        positive=next(a for a in r['arguments'] if a['rule']==CORE+'mab/explorationArgument')
        negative=next(a for a in r['arguments'] if a['rule']==CORE+'mab/shortHorizonObjection')
        self.assertNotEqual(positive['premises'],negative['premises'])
        self.assertEqual(positive['label'],'undecided');self.assertEqual(negative['label'],'undecided')
        self.assertTrue(any(a['kind']=='rebutting' for a in r['attacks']))
        bad=copy.deepcopy(r);bad['defeats']=[]
        for a in bad['arguments']:a['label']='accepted'
        with self.assertRaisesRegex(ValidationError,'defeats'):validate_analysis(bad)

    def test_attributed_contestation_undercuts_challenge_without_changing_model(self):
        s,e=self.mab();session=self.store.get(s['id']);snap=e['snapshot']
        hyp=next(h for h in snap['participant']['hypotheses'] if h['name']=='underexploration')
        posterior=hyp['inference']['posterior']
        # Unit fixture: an explicit disagreement, already validated by the dialogue
        # layer in integration tests. No free-text interpretation is performed here.
        response={'id':'synthetic_disagreement','input':{'kind':'response','feedback':'disagree',
            'text':'I am following a deliberate strategy.','index':7,'hypothesis':'underexploration'}}
        session['events'].insert(-1,response);hyp['contested_by']=[response['id']]
        r=analyse(session,e);validate_analysis(r)
        target=next(a for a in r['arguments'] if a['rule']==ARG+'modelChallenge')
        self.assertEqual(target['label'],'rejected')
        self.assertTrue(any(a['kind']=='undercutting' for a in r['attacks']))
        self.assertEqual(hyp['inference']['posterior'],posterior)
        reports=[a for a in r['assertions'] if a['kind']=='report'];self.assertTrue(reports)
        self.assertTrue(all('known' not in a['statuses'] for a in reports))
        hyp['contested_by']=[]
        revised=analyse(session,e)
        self.assertEqual(next(a for a in revised['arguments'] if a['rule']==ARG+'modelChallenge')['label'],'accepted')

    def test_tbs_criteria_divergence_is_a_chain_not_a_false_conflict(self):
        s=self.create('TBS');points=0
        for i in range(1,8):
            ev=evaluation('TBS',s['id'],i,points=points)
            pair=get_task('TBS').RULES['options'][0]
            for opt,pair_opt in zip(ev['options'],pair):opt.update(amount=pair_opt[0],probability=pair_opt[1])
            gain=100 if i<=2 else 0;self.emit(s,ev,'safe',gain);points+=gain
        e=self.store.event(s['id'],evaluation('TBS',s['id'],8,points=points)|{
            'options':[{'id':'safe','key':'1','amount':180,'probability':.6},{'id':'risky','key':'9','amount':260,'probability':.35}]})
        r=e['snapshot']['graph_argumentation'];self.assertEqual(r['status'],'complete')
        conclusion=next(a for a in r['arguments'] if a['rule']==CORE+'tbs/criteriaDivergenceArgument')
        self.assertEqual(conclusion['rule_kind'],'strict');self.assertEqual(len(conclusion['subarguments']),2)
        self.assertEqual(conclusion['label'],'accepted');self.assertEqual(r['attacks'],[])
        self.assertTrue(any(a['rule']==CORE+'tbs/objectiveQuestionArgument' for a in r['arguments']))
        facts={a['id']:a for a in r['assertions']}
        values=[a['proposition']['object']['value'] for a in r['assertions'] if a['proposition']['predicate']==CORE+'task/value']
        for value in [108.,91.,0.,.35]:self.assertIn(value,values)
        self.assertTrue(self.store.replay(s['id'])['matches'])
        self.assertIsNot(shacl_report(self.store.get(s['id']))['conforms'],False)

    def test_shadow_leaves_decision_and_language_package_unchanged(self):
        s,e=self.mab();session=self.store.get(s['id'])
        from socratic_prototype.engine import make_snapshot
        original=copy.deepcopy(e['snapshot']['decision'])
        session.pop('argumentation_configuration')
        self.assertEqual(make_snapshot(session,e['input'],e['id'],e['timestamp'])['decision'],original)
        self.assertTrue(self.store.replay(s['id'])['matches'])
        g=rdflib.Graph().parse(data=turtle(self.store.get(s['id'])),format='turtle')
        self.assertTrue(list(g.subjects(rdflib.RDF.type,rdflib.URIRef(ARG+'Assertion'))))

    def test_historical_analysis_cannot_see_later_feedback(self):
        s,e=self.mab();original=analyse(self.store.get(s['id']),e)
        self.store.event(s['id'],dict(kind='feedback',trial_id=e['input']['trial_id'],index=8,
            choice='red1',outcome=200,score_after=200,timed_out=False,response_ms=500))
        self.store.event(s['id'],evaluation('MAB',s['id'],9,score=200))
        self.assertEqual(analyse(self.store.get(s['id']),e),original)

    def test_limits_do_not_report_acceptance_from_an_incomplete_graph(self):
        s,e=self.mab();session=self.store.get(s['id']);session['argumentation_configuration']['limits']['max_arguments']=1
        r=analyse(session,e);self.assertEqual(r['status'],'limited')
        self.assertTrue(all(a['label']=='undecided' for a in r['arguments']))
        self.assertTrue(validate_analysis(r)['conforms'])

    def test_malformed_proof_and_epistemic_promotion_rejected(self):
        _,e=self.mab();r=e['snapshot']['graph_argumentation'];bad=copy.deepcopy(r)
        derived=next(a for a in bad['arguments'] if a['rule_kind']=='defeasible');derived['premises']=['urn:missing']
        with self.assertRaises(ValidationError):validate_analysis(bad)
        bad=copy.deepcopy(r);estimate=next(a for a in bad['assertions'] if a['kind']=='estimate');estimate['statuses']=['known']
        with self.assertRaises(ValidationError):validate_analysis(bad)
        from socratic_prototype.argumentation.discovery import prepared
        with self.assertRaises(ValidationError):prepared('SELECT * WHERE { SERVICE<https://example.org/> { ?s ?p ?o } }')

    @unittest.skipUnless(HAS_SHACL,'pySHACL research dependency not installed')
    def test_argument_shapes_reject_bad_labels_and_inconsistent_indexes(self):
        s,e=self.mab();session=self.store.get(s['id'])
        from socratic_prototype.validation import _projection
        for incremental in [False,True]:
            text,focus=_projection(session,incremental)
            bad=text.replace('arg:label "accepted"','arg:label "certain"')
            self.assertNotEqual(bad,text)
            with patch('socratic_prototype.validation._projection',return_value=(bad,focus)):
                self.assertFalse(shacl_report(session,incremental)['conforms'])
            a=e['snapshot']['graph_argumentation']['assertions'][0]
            original='<'+a['id']+'> arg:subject <'+a['proposition']['subject']+'> .'
            self.assertIn(original,text)
            bad=text.replace(original,'<'+a['id']+'> arg:subject <urn:tampered> .')
            with patch('socratic_prototype.validation._projection',return_value=(bad,focus)):
                self.assertFalse(shacl_report(session,incremental)['conforms'])
