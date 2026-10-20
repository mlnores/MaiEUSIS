"""Task separation, numerical RDF provenance and independent extension checks."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from socratic_prototype.analysis import summarize
from socratic_prototype.demo import evaluation
from socratic_prototype.records import ValidationError,fields,require
from socratic_prototype.semantics import CORE,DATA,TASK
from socratic_prototype.store import Store,configuration_fields,digest
from socratic_prototype.tasks import get_task,register_task,_TASKS
from socratic_prototype.tasks.base import describe_task,document_paths,MODEL_VERSION
from socratic_prototype.validation import turtle,shacl_report,_projection,graph_documents

try:
    from rdflib import Graph,Namespace,RDF,OWL,Literal,URIRef
    import pyshacl
    HAS_RDF=True
except ImportError:
    HAS_RDF=False


class TaskModuleTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'sessions.sqlite3')

    def create(self,task):
        return self.store.create(dict(participant_id='synthetic_modules',task=task,condition='A',
            phase='calibration',protocol='short',preference='standard'))

    def test_version_and_document_drift_rejected_before_mutation(self):
        module=get_task('MAB');s=self.create('MAB');changed=module.describe()|{'version':'changed'}
        with patch.object(module,'describe',return_value=changed):
            with self.assertRaisesRegex(ValidationError,'changed'):self.store.event(s['id'],evaluation('MAB',s['id'],1))
            with self.assertRaisesRegex(ValidationError,'task_module'):self.store.replay(s['id'])
        self.assertEqual(self.store.get(s['id'])['events'],[])
        changed=copy.deepcopy(module.describe());changed['document_digests']['mab.ttl']='changed'
        with patch.object(module,'describe',return_value=changed):
            with self.assertRaises(ValidationError):self.store.event(s['id'],evaluation('MAB',s['id'],1))

    def test_legacy_configuration_and_projection_remain_supported(self):
        s=self.create('MAB');s.pop('task_module');s.pop('argumentation_configuration');s['schema_version']='ontology-0.1'
        s['configuration_digest']=digest({k:s[k] for k in configuration_fields(s)});self.store.save(s)
        self.store.event(s['id'],evaluation('MAB',s['id'],1))
        self.assertTrue(self.store.replay(s['id'])['matches'])
        graph=turtle(self.store.get(s['id']))
        self.assertNotIn('@prefix task:',graph)
        self.assertIn('<'+CORE+s['id']+'> a s:Session',graph)

    def test_new_task_uses_shared_pipeline_without_domain_branches(self):
        # A genuinely different two-step task: only the shared ontologies apply.
        get_task('MAB')
        paths=document_paths('MAB');docs=((paths[0],paths[1]),(paths[3],paths[4]))
        def validate(e):
            keys=['kind','trial_id','index']
            fields(e,keys+(['counter'] if e['kind']=='evaluation' else ['choice','outcome','timed_out','response_ms','counter_after']))
            require(e['kind'] in {'evaluation','feedback'},'Unknown toy event')
            require(type(e['index']) is int and e['index']>0,'Invalid index')
        def transition(s,e,h,evals):
            if e['kind']=='evaluation':require(e['counter']==len(h),'Counter changed')
            else:require(e['choice']=='advance' and e['outcome']==1 and e['counter_after']==len(h)+1,'Invalid advance')
        def candidates(s,ev,env,h,stats,claim,socratic,existing,add):
            add('counter_check','explain',['Review the recorded counter.'],[claim['id']],
                'The counter is public.','Further observations may be useful.',.9)
        def project(w,s,e,state,ev,previous):w.state(s,e,state,'task:TaskState',previous)
        module=SimpleNamespace(ID='TOY',NAMESPACE=CORE+'toy/',MODULE_VERSION='toy-0.1',
            ONTOLOGY_VERSION='toy-ontology-0.1',PROTOCOLS={'short':2},ELIGIBLE_POINT='before advance',
            documents=lambda:docs,task_rules=lambda:{'increment':1},validate_event=validate,validate_transition=transition,
            calibrate=lambda h:{'task':'TOY','model_version':MODEL_VERSION,'samples':len(h)},
            environment=lambda h,ev,p,e:{'counter':e.get('counter_after',ev['counter']),'unknown':['Next observation']},
            participant=lambda h,p:{},hypothesis_inputs=lambda *args:([],{}),contribute_candidates=candidates,
            hypothesis_message=lambda *args:'Review the evidence.',same_scope=lambda *args:True,scope_suffix=lambda e:'',
            environment_claim=lambda e:(f"Counter is {e['counter']}.",['known']),history_context=lambda ev:{'counter_before':ev['counter']},
            evidence_environment=lambda env:({'counter':env['counter']},'The counter is recorded.'),
            evidence_participant=lambda p:{},evidence_observation=lambda o:{'trial_id':o['trial_id']},
            summarize=lambda s,h,v:{'final_counter':h[-1]['counter_after'] if h else 0},project_rdf=project)
        module.describe=lambda:describe_task(module.ID,module.NAMESPACE,module.MODULE_VERSION,module.ONTOLOGY_VERSION,docs)
        register_task(module);self.addCleanup(lambda:_TASKS.pop('TOY'))
        def run(s):
            for i in [1,2]:
                ev=dict(kind='evaluation',trial_id=s['id']+'_trial_'+str(i),index=i,counter=i-1)
                record=self.store.event(s['id'],ev)
                self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=i,choice='advance',
                    outcome=1,timed_out=False,response_ms=100,counter_after=i))
            return self.store.finish(s['id'],{'completed':True}),record
        calibration,_=run(self.create('TOY'))
        s=self.store.create(dict(participant_id='synthetic_modules',task='TOY',condition='C',phase='assisted',
            protocol='short',preference='standard',calibration_ids={'TOY':calibration['id']}))
        result,record=run(s)
        self.assertEqual(record['snapshot']['decision']['action'],'explain')
        self.assertEqual(record['snapshot']['decision']['evidence_package']['environment'],{'counter':1})
        self.assertEqual(summarize(result)['final_counter'],2)
        self.assertTrue(self.store.replay(s['id'])['matches'])
        self.assertIn('task:TaskState',turtle(result))
        self.assertNotIn('@prefix mab:',turtle(result))
        self.assertNotIn('@prefix tbs:',turtle(result))
        if HAS_RDF:self.assertTrue(shacl_report(result)['conforms'])


@unittest.skipUnless(HAS_RDF,'Research RDF dependencies not installed')
class TaskGraphTest(TaskModuleTest):
    # Do not inherit the contract tests a second time.
    test_version_and_document_drift_rejected_before_mutation=None
    test_legacy_configuration_and_projection_remain_supported=None
    test_new_task_uses_shared_pipeline_without_domain_branches=None

    def graph(self,s):return Graph().parse(data=turtle(s),format='turtle')

    def test_local_module_imports_and_declared_projection_terms(self):
        for identifier in ['MAB','TBS']:
            s=self.create(identifier);self.store.event(s['id'],evaluation(identifier,s['id'],1));s=self.store.get(s['id'])
            module=get_task(identifier);ont=Graph()
            for path in graph_documents(s)[0]:ont.parse(path,format='turtle')
            graph=self.graph(s)
            declared=set(ont.subjects(RDF.type,OWL.ObjectProperty))|set(ont.subjects(RDF.type,OWL.DatatypeProperty))|set(ont.subjects(RDF.type,RDF.Property))
            used={p for p in graph.predicates() if str(p).startswith(CORE)}
            self.assertEqual(used-declared,set())
            opposite=CORE+('tbs/' if identifier=='MAB' else 'mab/')
            self.assertFalse(any(str(x).startswith(opposite) for triple in ont for x in triple))
            self.assertTrue(shacl_report(s)['conforms'])

    def test_mab_distinguishes_observed_reward_and_two_value_models(self):
        s=self.create('MAB');ev=evaluation('MAB',s['id'],1);self.store.event(s['id'],ev)
        event=self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=1,
            choice='blue1',outcome=100,score_after=100,timed_out=False,response_ms=1000))
        s=self.store.get(s['id']);g=self.graph(s);task=Namespace(TASK);mab=Namespace(CORE+'mab/')
        state=DATA+event['id']+'/state';reward=URIRef(state+'/reward/blue1');q=URIRef(state+'/learned/blue1')
        self.assertEqual(float(g.value(reward,task.value)),25)
        self.assertAlmostEqual(float(g.value(q,task.value)),.15)
        self.assertEqual(str(g.value(reward,task.unit)),'reward-points')
        self.assertEqual(str(g.value(q,task.unit)),'reward/200')
        observation=URIRef(DATA+ev['trial_id']+'/outcome')
        self.assertEqual(float(g.value(observation,task.value)),100)
        self.assertIn((reward,task.basedOnObservation,observation),g)
        self.assertIn((reward,RDF.type,task.Estimate),g)
        self.assertNotIn((observation,RDF.type,task.Estimate),g)
        self.assertTrue(list(g.objects(reward,task.usesRule)))
        self.assertFalse(any('actualProbability' in str(p) or 'shift_time' in str(p) for p in g.predicates()))
        # Nested numeric shape must run on literals in incremental validation too.
        bad=copy.deepcopy(s);bad['events'][-1]['snapshot']['environment']['arms'][0]['estimated_value']='25'
        for incremental in [False,True]:self.assertFalse(shacl_report(bad,incremental)['conforms'])
        self.assertTrue(shacl_report(s,True)['conforms'])

    def final_tbs(self,win=True):
        s=self.create('TBS');points=0
        for i in range(1,9):
            ev=evaluation('TBS',s['id'],i,points=points)
            pair=get_task('TBS').RULES['options'][1 if i==8 else 0]
            for option,p in zip(ev['options'],pair):option.update(amount=p[0],probability=p[1])
            before=self.store.event(s['id'],ev)
            gain=260 if i==8 and win else 100 if i<=2 else 0;points+=gain
            after=self.store.event(s['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=i,
                choice='risky' if i==8 else 'safe',outcome=gain,points_after=points,timed_out=False,response_ms=1000))
        return self.store.get(s['id']),before,after

    def test_tbs_ev_attainment_and_conditional_final_win_have_provenance(self):
        s,before,after=self.final_tbs();g=self.graph(s);task=Namespace(TASK);tbs=Namespace(CORE+'tbs/')
        state=DATA+before['id']+'/state'
        for option,ev,win,chance in [('safe',108,874,0),('risky',91,1058,.35)]:
            for kind,value in [('expected-gain',ev),('win-score',win),('attainment',chance)]:
                calc=URIRef(state+'/'+kind+'/'+option)
                self.assertAlmostEqual(float(g.value(calc,task.value)),value)
                self.assertIn((calc,task.inputState,URIRef(state)),g)
                self.assertTrue(list(g.objects(calc,task.usesRule)))
        post=URIRef(DATA+after['id']+'/state');total=URIRef(str(post)+'/final-total')
        self.assertEqual(float(g.value(post,tbs.points)),1058)
        self.assertEqual(g.value(post,tbs.multiplierApplied).toPython(),True)
        self.assertIn((total,task.inputState,URIRef(state)),g)
        self.assertTrue(shacl_report(s,True)['conforms'])
        self.assertTrue(shacl_report(s)['conforms'])
        # Invalid previous-state horizon must fail the nested final-total condition.
        for incremental in [False,True]:
            text,focus=_projection(s,incremental)
            text=text.replace('<'+state+'> tbs:remainingChoices "1"','<'+state+'> tbs:remainingChoices "2"')
            with patch('socratic_prototype.validation._projection',return_value=(text,focus)):
                self.assertFalse(shacl_report(s,incremental)['conforms'])
        # Losing the final choice must leave the multiplier unapplied.
        losing,_,last=self.final_tbs(False);graph=self.graph(losing);post=URIRef(DATA+last['id']+'/state')
        self.assertEqual(float(graph.value(post,tbs.points)),200)
        self.assertFalse(graph.value(post,tbs.multiplierApplied).toPython())
        self.assertNotIn((URIRef(str(post)+'/final-total'),RDF.type,tbs.FinalTotalCalculation),graph)

    def test_shapes_reject_probability_bounds_and_missing_calculation_rule(self):
        s=self.create('TBS');self.store.event(s['id'],evaluation('TBS',s['id'],1));s=self.store.get(s['id'])
        for incremental in [False,True]:
            text,focus=_projection(s,incremental)
            bad=text.replace('tbs:displayedWinProbability "0.9"','tbs:displayedWinProbability "1.2"')
            self.assertNotEqual(bad,text)
            with patch('socratic_prototype.validation._projection',return_value=(bad,focus)):
                self.assertFalse(shacl_report(s,incremental)['conforms'])
            bad='\n'.join(line for line in text.splitlines() if ' task:usesRule ' not in line)
            with patch('socratic_prototype.validation._projection',return_value=(bad,focus)):
                self.assertFalse(shacl_report(s,incremental)['conforms'])
