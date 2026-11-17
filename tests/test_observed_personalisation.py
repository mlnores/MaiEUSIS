"""Observable behaviour learning, causal ordering and conservative delivery policy."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from socratic_prototype.demo import evaluation
from socratic_prototype.engine import POLICY
from socratic_prototype.learning import summary
from socratic_prototype.participant_model import estimate,interaction_estimate,selection_cost,RHO
from socratic_prototype.personalisation import assess,forecast_source
from socratic_prototype.tasks import get_task
from socratic_prototype.argumentation import ARG


def session(task='MAB',condition='F'):
    return {'task':task,'condition':condition,'policy':copy.deepcopy(POLICY),'events':[],
            'calibration_profile':None}


def append_trial(s,index,style=None,choice='blue1',reward=0,delivered=True,exposure=500,timeout=False,late=False):
    ev=evaluation(s['task'],'observed',index)
    if s['task']=='TBS':choice='safe' if choice=='blue1' else choice
    intervention=None
    if style:
        intervention={'style':style,'issue':'expected_value_limit','comparisons':[{'option_id':o['id']} for o in ev['options'][:2]],
                      'recommendation':{'option_id':ev['options'][0]['id']} if style=='direct' else None}
    d={'id':'d'+str(index),'intervention':intervention}
    s['events'].append({'id':'eval'+str(index),'input':ev,'snapshot':{'decision':d}})
    delivery={'id':'delivery'+str(index),'input':{'kind':'delivery','decision_id':d['id'],'delivered':delivered,'reading_exposure_ms':exposure}}
    if not late:s['events'].append(delivery)
    fb={'kind':'feedback','trial_id':ev['trial_id'],'index':index,'choice':'NO_RESPONSE' if timeout else choice,
        'outcome':reward,'timed_out':timeout}
    s['events'].append({'id':'outcome'+str(index),'input':fb})
    if late:s['events'].append(delivery)
    return ev


def pending(s,index):
    ev=evaluation(s['task'],'observed',index)
    s['events'].append({'id':'eval'+str(index),'input':ev})
    return estimate(s,[])


class LearningTest(unittest.TestCase):
    def test_task_learning_and_grid_transfer_reset(self):
        s=session();append_trial(s,1,reward=100)
        p=pending(s,2)['online_task']
        self.assertEqual(p['choice_updates'],1);self.assertEqual(p['outcome_updates'],1)
        self.assertGreater(p['prediction']['blue1']['mean'],p['prediction']['blue2']['mean'])
        self.assertAlmostEqual(sum(a['mean'] for a in p['prediction'].values()),1)
        for task in ['MAB','TBS']:
            profile=get_task(task).calibrate([])
            observer=get_task(task).participant_observer(profile)
            self.assertTrue(observer.transferred)
            self.assertEqual(observer.updates,0)
            if task=='MAB':self.assertTrue(all(v==0 for q in observer.q for v in q.values()))
            s=session(task);s['calibration_profile']=profile
            p=pending(s,1)
            self.assertTrue(p['online_task']['calibration_posterior_transferred'])

    def test_assisted_choices_do_not_fit_unaided_parameters_but_outcomes_update(self):
        s=session();append_trial(s,1,'direct',reward=100)
        p=pending(s,2)
        self.assertEqual(p['online_task']['choice_updates'],0)
        self.assertEqual(p['online_task']['outcome_updates'],1)
        self.assertGreater(p['online_task']['prediction']['blue1']['mean'],1/6)
        self.assertEqual(p['interaction']['direct']['informative'],1)
        self.assertEqual(p['interaction']['socratic']['informative'],0)

    def test_exposure_timeout_and_acknowledgement_boundaries(self):
        for delivered,ms,timeout,late,updates,observations in [
                (True,0,False,False,0,0),(False,0,False,False,1,0),
                (True,100,True,False,0,0),(True,100,False,True,0,0),
                (True,100,False,False,0,1)]:
            with self.subTest(delivered=delivered,ms=ms,timeout=timeout,late=late):
                s=session();append_trial(s,1,'direct',delivered=delivered,exposure=ms,timeout=timeout,late=late)
                p=pending(s,2)
                self.assertEqual(p['online_task']['choice_updates'],updates)
                self.assertEqual(p['interaction']['direct']['observations'],observations)
                self.assertEqual(p['online_task']['outcome_updates'],int(not timeout))

    def test_uptake_likelihoods_learn_both_styles_without_true_responsiveness(self):
        for style in ['direct','socratic']:
            yes=session();no=session()
            for i in range(1,25):
                append_trial(yes,i,style,choice='blue1')
                append_trial(no,i,style,choice='red3')
            a=pending(yes,25)['interaction'];b=pending(no,25)['interaction']
            self.assertGreater(a[style]['mean'],.85)
            self.assertLess(b[style]['interval'][1],.25)
            other='socratic' if style=='direct' else 'direct'
            self.assertAlmostEqual(a[other]['mean'],.5)
            self.assertEqual(a[other]['status'],'unknown')
            self.assertEqual(a[style]['informative'],24)

    def test_reward_is_not_an_assistance_success_label(self):
        yes=session();no=session()
        append_trial(yes,1,'direct',reward=100);append_trial(no,1,'direct',reward=-100)
        self.assertEqual(pending(yes,2)['interaction']['direct'],pending(no,2)['interaction']['direct'])

    def test_tbs_online_pressure_posterior_updates(self):
        s=session('TBS');append_trial(s,1,choice='risky')
        p=pending(s,2)['online_task']
        self.assertEqual(p['choice_updates'],1)
        prior=[r['weight'] for r in get_task('TBS').participant_observer({}).describe()['parameter_posterior']]
        self.assertNotEqual([r['weight'] for r in p['parameter_posterior']],prior)
        self.assertIn('Option-value',str(p['assumptions']))

    def test_private_actor_data_are_never_read_and_generic_models_are_withheld(self):
        s=session();append_trial(s,1);p=pending(s,2)
        poisoned=copy.deepcopy(s)
        poisoned.update(task_models={'MAB':{'beta':999}},responsiveness=1,evaluator_state={'future':[200]*10})
        self.assertEqual(estimate(poisoned,[]),p)
        for c in ['A','C','D']:
            p=estimate({**s,'condition':c},[])
            self.assertEqual(p['online_task']['status'],'withheld')
            self.assertEqual(p['interaction']['status'],'withheld')

    def test_agreement_already_likely_is_uninformative(self):
        class Observer:
            weights=[1.]
            def distributions(self,ev):return [{'blue1':.99,'blue2':.01}]
            def predict(self,ev):return {a:{'mean':p,'interval':[p,p]} for a,p in self.distributions(ev)[0].items()}
            def observe(self,*args):pass
            def describe(self):return {'version':'fixture'}
        s=session();append_trial(s,1,'direct')
        with patch.object(get_task('MAB'),'participant_observer',return_value=Observer()):
            p=pending(s,2)['interaction']['direct']
        self.assertEqual(p['uninformative'],1);self.assertEqual(p['informative'],0)
        self.assertAlmostEqual(p['mean'],.5)


class ReportTest(unittest.TestCase):
    def test_reports_have_distinct_meanings_and_duplicate_clicks_are_not_new_evidence(self):
        s=session()
        for i,feedback in enumerate(['helpful','dismiss','disagree','reply']):
            s['events'].append({'id':str(i),'input':{'kind':'response','decision_id':'d','feedback':feedback,'text':''}})
        p=interaction_estimate(s)
        self.assertEqual(selection_cost(.12,{'interaction':p}),.12)
        self.assertEqual(p['reported_burden']['status'],'unknown')
        self.assertEqual(p['direct']['status'],'unknown')
        r={'id':'fewer','input':{'kind':'response','decision_id':'d','feedback':'fewer','text':''}}
        s['events'] += [r,copy.deepcopy(r)]
        p=interaction_estimate(s)
        self.assertEqual(p['feedback_counts']['fewer'],1)
        self.assertEqual(selection_cost(.12,{'interaction':p}),.18)
        self.assertEqual(p['direct']['status'],'unknown')


class DeliveryTest(unittest.TestCase):
    def seal(self,snap):
        snap['graph_argumentation']['assertions'][0]['source']=forecast_source('urn:state',snap['participant'])

    def fixture(self,task='MAB',probabilities=None,informative=0,upper=1.):
        s=session(task);ev=evaluation(task,'observed',7);p=pending(s,1)
        p['calibration']['samples']=40
        p['online_task']['calibration_posterior_transferred']=True
        probs=probabilities or {o['id']:1/len(ev['options']) for o in ev['options']}
        p['online_task']['prediction']={a:{'mean':v,'interval':[v,v]} for a,v in probs.items()}
        p['online_task']['choice_hypotheses']=[{'probabilities':probs,'weight':1.}]
        for style in ['direct','socratic']:
            p['interaction'][style].update(informative=informative,mean=.1,interval=[0,upper])
        report={'status':'complete','scope':'urn:state',
                'assertions':[{'id':'forecast','source':'pending','proposition':{'predicate':ARG+'hasBehaviouralForecast'}},
                              {'id':'fact','proposition':{'predicate':ARG+'mayPersonaliseDelivery'}}],
                'arguments':[{'id':'proof','conclusion':'fact','label':'accepted','rule':ARG+'forecastScheduling','premises':['forecast']}]}
        snap={'participant':p,'graph_argumentation':report}
        self.seal(snap)
        candidate={'name':'expected_value_limit','recommendation':{'option_id':ev['options'][0]['id']},
            'comparisons':[{'option_id':o['id']} for o in ev['options'][:2]],'supporting_arguments':[], 'opposing_arguments':[]}
        return ev,snap,candidate

    def test_redundancy_suppresses_both_styles_and_generic_uses_common_defaults(self):
        probs={'blue1':.95,**{a:.01 for a in ['blue2','blue3','red1','red2','red3']}}
        ev,snap,candidate=self.fixture(probabilities=probs)
        for c in ['E','F']:
            adapted=assess('MAB',c,ev,snap,candidate)
            self.assertTrue(adapted['redundant']);self.assertLess(adapted['relevance_factor'],1)
            self.assertEqual(adapted['argument_ids'],['proof'])
        for c in ['C','D']:
            adapted=assess('MAB',c,ev,snap,candidate)
            self.assertFalse(adapted['enabled']);self.assertEqual(adapted['relevance_factor'],1)

    def test_low_uptake_waits_for_evidence_and_high_uptake_gives_no_bonus(self):
        ev,snap,candidate=self.fixture(informative=5,upper=.2)
        self.assertEqual(assess('MAB','E',ev,snap,candidate)['uptake_factor'],1)
        snap['participant']['interaction']['direct']['informative']=6
        self.seal(snap)
        adapted=assess('MAB','E',ev,snap,candidate)
        self.assertEqual(adapted['extra_cooldown'],3);self.assertEqual(adapted['uptake_factor'],.85)
        snap['participant']['interaction']['direct']['interval']=[.9,1]
        self.seal(snap)
        self.assertEqual(assess('MAB','E',ev,snap,candidate)['uptake_factor'],1)

    def test_no_suppression_from_uncertain_task_model_or_missing_graph_proof(self):
        ev,snap,candidate=self.fixture()
        probs=snap['participant']['online_task']['choice_hypotheses'][0]['probabilities']
        snap['participant']['online_task']['choice_hypotheses'] += [
            {'probabilities':{a:float(a=='blue1') for a in probs},'weight':1.}]
        for h in snap['participant']['online_task']['choice_hypotheses']:h['weight']=.5
        self.seal(snap)
        self.assertFalse(assess('MAB','E',ev,snap,candidate)['redundant'])
        snap['graph_argumentation']['arguments'][0]['label']='undecided'
        self.assertFalse(assess('MAB','E',ev,snap,candidate)['enabled'])

    def test_tbs_comparing_both_options_is_not_automatically_redundant(self):
        ev,snap,candidate=self.fixture('TBS',{'safe':.95,'risky':.05})
        adapted=assess('TBS','F',ev,snap,candidate)
        self.assertFalse(adapted['redundant'])
        self.assertGreater(adapted['response_distance']['mean'],.15)


class StoreIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from socratic_prototype.store import Store
        from socratic_prototype.demo import run_scripted
        cls.temp=tempfile.TemporaryDirectory();cls.store=Store(Path(cls.temp.name)/'sessions.sqlite3')
        # Full independent SHACL checks follow below; avoid rechecking every
        # fixture entity while generating the common calibration histories.
        with patch.dict('os.environ',{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'}),patch(
                'socratic_prototype.engine.shacl_report',return_value={'conforms':True,'engine':'fixture','report':'Full SHACL checked below'}):
            cls.ids={t:run_scripted(cls.store,t) for t in ['MAB','TBS']}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def trace(self,task,condition,count,report_fewer=False):
        s=self.store.create(dict(participant_id='synthetic_demo',task=task,condition=condition,phase='assisted',
            protocol='short',preference='frequent',calibration_ids=self.ids))
        active=[];fewer_sent=False
        for index in range(1,count+1):
            ev=evaluation(task,s['id'],index,score=-100*(index-1),points=0)
            record=self.store.event(s['id'],ev);snap=record['snapshot'];d=snap['decision']
            self.assertEqual(snap['participant']['online_task']['prediction_for_trial'],ev['trial_id'])
            self.assertIn('BehaviouralForecast',snap['graph_argumentation']['facts_turtle'])
            if d['action']!='silence':active.append(d)
            self.store.event(s['id'],dict(kind='delivery',decision_id=d['id'],index=index,delivered=d['action']!='silence',
                reading_exposure_ms=1000 if d['action']!='silence' else 0,generation_latency_ms=0,early_attempts=0))
            if active and report_fewer and not fewer_sent:
                self.store.event(s['id'],dict(kind='response',decision_id=d['id'],index=index,feedback='fewer',text='',
                    hypothesis=d['hypothesis'],**({'block':ev['block']} if task=='TBS' else {})))
                self.assertEqual(self.store.get(s['id'])['preference'],'infrequent');fewer_sent=True
            self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=index,choice='blue1' if task=='MAB' else 'safe',
                outcome=-100 if task=='MAB' else 0,timed_out=False,response_ms=700,
                **({'score_after':-100*index} if task=='MAB' else {'points_after':0})))
        return self.store.get(s['id']),active

    def test_real_graph_delivery_scores_explicit_frequency_replay_and_shacl(self):
        from socratic_prototype.validation import shacl_report,turtle
        from socratic_prototype.intervention_policy import validate_decision
        from socratic_prototype.records import ValidationError
        with patch.dict('os.environ',{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'}),patch(
                'socratic_prototype.engine.shacl_report',return_value={'conforms':True,'engine':'fixture','report':'Full SHACL checked below'}):
            for task in ['MAB','TBS']:
                with self.subTest(task=task):
                    s,active=self.trace(task,'F',16,report_fewer=True)
                    self.assertTrue(active)
                    self.assertTrue(self.store.replay(s['id'])['matches'])
                    validation=shacl_report(s)
                    self.assertTrue(validation['conforms'],validation['report'])
                    graph=turtle(s);self.assertIn('modelDigest',graph)
                    self.assertIn('forecastScheduling',graph)
                    self.assertIn('socratic_prototype.tasks.'+task.lower()+'_participant.Observer',graph)
                    snap=next(e['snapshot'] for e in s['events'] if e.get('snapshot',{}).get('decision',{}).get('candidates'))
                    self.assertTrue(snap['decision']['candidates'][0]['personalisation']['enabled'])
                    bad=copy.deepcopy(snap)
                    first=next(iter(bad['participant']['online_task']['prediction']))
                    bad['participant']['online_task']['prediction'][first]['mean']+=.001
                    with self.assertRaisesRegex(ValidationError,'Delivery adaptation differs'):validate_decision(bad)

    def test_observed_ignoring_can_change_actual_personalised_schedule(self):
        with patch.dict('os.environ',{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'}),patch(
                'socratic_prototype.engine.shacl_report',return_value={'conforms':True,'engine':'fixture','report':'Covered independently'}):
            for condition in ['E','F']:
                s,active=self.trace('MAB',condition,40)
                estimates=[e['snapshot']['participant']['interaction'] for e in s['events'] if e.get('snapshot')]
                style='direct' if condition=='E' else 'socratic'
                self.assertGreaterEqual(estimates[-1][style]['informative'],6)
                self.assertLess(estimates[-1][style]['interval'][1],.5)
                decisions=[e['snapshot']['decision'] for e in s['events'] if e.get('snapshot',{}).get('decision')]
                self.assertTrue(any(d['personalisation'] and d['personalisation']['uptake_factor']<1 for d in decisions))
                self.assertTrue(any(d['cooldown']>POLICY['cooldown']['frequent'] for d in decisions))
                self.assertTrue(self.store.replay(s['id'])['matches'])
                # Neither the actor's true rho nor a response generator was used.
                self.assertFalse(any(e['input']['kind']=='response' for e in s['events']))

    def test_incremental_shacl_accepts_live_personalised_events(self):
        with patch.dict('os.environ',{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'}):
            for task in ['MAB','TBS']:
                with self.subTest(task=task):
                    s,active=self.trace(task,'F',8)
                    self.assertTrue(active)
                    for event in s['events']:
                        if event.get('snapshot'):
                            report=event['snapshot']['shacl']
                            self.assertTrue(report['conforms'],report['report'])


@unittest.skipUnless(importlib.util.find_spec('pyshacl'),'Forecast SHACL checks require the optional research dependencies')
class ForecastShapeTest(unittest.TestCase):
    def test_forecast_shapes_reject_invalid_probabilities_intervals_and_styles(self):
        from rdflib import Graph,Namespace,Literal
        from pyshacl import validate
        from socratic_prototype.argumentation import ROOT
        arg=Namespace(ARG)
        shapes=Graph().parse(ROOT/'shapes.ttl',format='turtle')
        text='''@prefix arg: <https://example.org/socratic/argumentation/> .
@prefix core: <https://example.org/socratic/> .
@prefix task: <https://example.org/socratic/task/> .
<urn:state> a task:TaskState .
<urn:model> a arg:BehaviouralForecast ; arg:version "fixture" ; core:status "inferred" ;
 arg:modelDigest "DIGEST" ; arg:inState <urn:state> .
<urn:forecast> a arg:ChoiceForecast ; arg:optionID "blue1" ; arg:source <urn:model> ;
 arg:probabilityMean .5 ; arg:probabilityLower .1 ; arg:probabilityUpper .9 .
<urn:uptake> a arg:UptakeEstimate ; arg:style "direct" ; core:status "assumed" ;
 arg:informativeExposures 0 ; arg:probabilityMean .5 ; arg:probabilityLower 0 ; arg:probabilityUpper 1 .
'''.replace('DIGEST','a'*64)
        data=Graph().parse(data=text,format='turtle')
        self.assertTrue(validate(data,shacl_graph=shapes,inference='none')[0])
        from rdflib import URIRef
        for node,predicate,value in [('urn:forecast','probabilityMean',1.1),
                ('urn:forecast','probabilityLower',.95),('urn:uptake','style','unknown'),
                ('urn:uptake','informativeExposures',-1),('urn:model','modelDigest','bad')]:
            with self.subTest(predicate=predicate):
                bad=Graph().parse(data=text,format='turtle')
                bad.set((URIRef(node),arg[predicate],Literal(value)))
                self.assertFalse(validate(bad,shacl_graph=shapes,inference='none')[0])
