import copy
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from socratic_prototype.store import Store, RULES
from socratic_prototype.demo import evaluation, run_scripted
from socratic_prototype.validation import ValidationError, validate_claim, turtle, shacl_report
from socratic_prototype.language import validate_proposal, realise
from socratic_prototype.models import tbs_context, change_belief, calibration_profile
from socratic_prototype.bayes import EpistemicNetwork, CPTS
from socratic_prototype.server import make_server


class PrototypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.store=Store(Path(cls.temp.name)/'sessions.sqlite3')
        cls.calibrations={task:run_scripted(cls.store,task) for task in ['MAB','TBS']}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def create(self,task='MAB',condition='F',phase='assisted',**extras):
        return self.store.create({'participant_id':'synthetic_demo','task':task,'condition':condition,'phase':phase,
                                 'protocol':'short','preference':'standard','calibration_ids':self.calibrations,**extras})

    def first(self,task='MAB',condition='F'):
        s=self.create(task,condition);ev=evaluation(task,s['id'],1)
        self.store.event(s['id'],ev);return s['id'],ev

    def feedback(self,sid,ev,choice='blue1',outcome=0):
        e={'kind':'feedback','trial_id':ev['trial_id'],'index':ev['index'],'choice':choice,'outcome':outcome,'timed_out':False,'response_ms':1000}
        e['score_after' if 'score' in ev else 'points_after']=ev.get('score',ev.get('points',0))+outcome
        return self.store.event(sid,e)

    def test_hidden_mab_fields_rejected_atomically(self):
        s=self.create();ev=evaluation('MAB',s['id'],1)
        for key,value in [('stage','volatile'),('shift_time',4),('volatility_checks',{}),('random_draw',.4)]:
            with self.subTest(key=key):
                with self.assertRaises(ValidationError):self.store.event(s['id'],ev|{key:value})
                self.assertEqual(self.store.get(s['id'])['events'],[])
        bad=copy.deepcopy(ev);bad['options'][0]['probabilities']=[.7,.2,.1]
        with self.assertRaises(ValidationError):self.store.event(s['id'],bad)
        self.assertEqual(self.store.get(s['id'])['events'],[])

    def test_unknown_future_tbs_state_rejected(self):
        s=self.create('TBS');ev=evaluation('TBS',s['id'],1)
        with self.assertRaises(ValidationError):self.store.event(s['id'],ev|{'future_outcomes':[100,0]})

    def test_out_of_order_and_invalid_feedback_dont_commit(self):
        sid,ev=self.first();before=self.store.get(sid)
        with self.assertRaises(ValidationError):self.store.event(sid,evaluation('MAB',sid,2))
        with self.assertRaises(ValidationError):self.feedback(sid,ev,outcome=999)
        self.assertEqual(self.store.get(sid),before)

    def test_exact_retry_is_idempotent(self):
        sid,ev=self.first();r=self.store.event(sid,ev)
        self.assertEqual(r,self.store.get(sid)['events'][0]);self.assertEqual(len(self.store.get(sid)['events']),1)

    def test_reward_arithmetic_and_timeout(self):
        sid,ev=self.first()
        with self.assertRaises(ValidationError):self.store.event(sid,{'kind':'feedback','trial_id':ev['trial_id'],'index':1,
            'choice':'NO_RESPONSE','outcome':-200,'timed_out':True,'response_ms':None,'score_after':0})
        r=self.store.event(sid,{'kind':'feedback','trial_id':ev['trial_id'],'index':1,
            'choice':'NO_RESPONSE','outcome':-200,'timed_out':True,'response_ms':None,'score_after':-200})
        self.assertTrue(all(a['samples']==0 for a in r['snapshot']['environment']['arms']))

    def test_final_trial_multiplier_feasibility(self):
        e={'points':450,'target':930,'remaining':1,'multiplier':2.3,'options':[
            {'id':'safe','key':'1','amount':100,'probability':.8}, {'id':'risky','key':'9','amount':265,'probability':.35}]}
        c=tbs_context(e)
        self.assertEqual([o['final_trial_target_probability'] for o in c['options']],[.8,.35])
        self.assertEqual(c['required_raw_gain_on_final_win'],0)
        e['points']=300;c=tbs_context(e)
        self.assertEqual([o['final_trial_target_probability'] for o in c['options']],[0,.35])
        e['points']=1000;c=tbs_context(e)
        self.assertEqual([o['final_trial_target_probability'] for o in c['options']],[1,1])

    def test_change_estimate_uses_observations_and_keeps_noise(self):
        self.assertEqual(change_belief([-1])['evidence'],'insufficient')
        steady=change_belief([1,-1,0]*6);shift=change_belief([1]*9+[-1]*9)
        self.assertGreater(shift['posterior'],steady['posterior']);self.assertLess(shift['posterior'],1)

    def test_bn_exact_conditional_probability(self):
        n=EpistemicNetwork();q=n.query(True,True,True)
        self.assertAlmostEqual(q['posterior'],.72)
        self.assertAlmostEqual(q['usefulness'],(1-.72)*.35+.72*.8)

    def test_missing_evidence_cannot_become_hypothesis(self):
        c={'id':'claim','type':'Hypothesis','content':'A possible pattern','statuses':['inferred'],'evidence':[],
           'scope':'MAB','timestamp':'2026-10-13','provenance':'test','model_version':'0.1',
           'alternatives':['planned exploration'],'revision_conditions':['more evidence']}
        with self.assertRaises(ValidationError):validate_claim(c,set())
        c['evidence']=['trial'];c['confidence']=1.2;c['confidence_interpretation']='provisional'
        with self.assertRaises(ValidationError):validate_claim(c,{'trial'})

    def test_language_cannot_change_action_evidence_or_add_facts(self):
        good={'action':'ask','claim_ids':['c'],'message':'What would change your mind?','updates':[]}
        self.assertEqual(validate_proposal(good,'ask',['c'],[good['message']]),good)
        for bad in [good|{'action':'advise'},good|{'claim_ids':['invented']},good|{'message':'Arm 1 has the best true probability.'},
                    good|{'updates':[{'claim_id':'c','status':'known'}]}]:
            with self.assertRaises(ValidationError):validate_proposal(bad,'ask',['c'],[good['message']])

    def test_offline_language_makes_no_requests(self):
        with patch.dict('os.environ',{'SOCRATIC_LLM':'offline'}),patch('urllib.request.urlopen',side_effect=AssertionError('API called')):
            r=realise('ask',['c'],['What matters?']);self.assertEqual(r['mode'],'reviewed-template')

    def test_all_six_conditions_complete_replay_and_respect_calibration_access(self):
        for condition in ['A','B','C','D','E','F']:
            for task in ['MAB','TBS']:
                with self.subTest(condition=condition,task=task):
                    sid=run_scripted(self.store,task,condition,'assisted',self.calibrations)
                    s=self.store.get(sid);self.assertTrue(s['completed']);self.assertTrue(self.store.replay(sid)['matches'])
                    self.assertEqual(s['calibration_profile'] is not None,condition in {'E','F'})
                    decisions=[e['snapshot']['decision'] for e in s['events'] if e.get('snapshot',{}).get('decision')]
                    self.assertTrue(all(d['rationale'] for d in decisions))
                    if condition=='A':self.assertTrue(all(d['action']=='silence' for d in decisions))
                    if condition in {'B','C','E'}:self.assertFalse(any(d['action'] in {'challenge','request-evidence'} for d in decisions))
                    if condition in {'C','D'}:self.assertTrue(all(c['hypothesis'] is None for d in decisions for c in d['candidates']))

    def test_common_calibration_mandatory_and_task_scoped(self):
        with self.assertRaises(ValidationError):self.create(calibration_ids={})
        with self.assertRaises(ValidationError):self.create(participant_id='different_person')
        s=self.create('TBS');self.assertEqual(s['calibration_profile']['task'],'TBS')
        self.assertNotIn('alpha_plus',s['calibration_profile'])

    def test_delivery_exposure_and_cooldown_use_actual_exposure(self):
        sid,ev=self.first('TBS');self.feedback(sid,ev,'safe',100)
        ev2=evaluation('TBS',sid,2,points=100);r=self.store.event(sid,ev2);d=r['snapshot']['decision']
        self.assertNotEqual(d['action'],'silence')
        self.store.event(sid,{'kind':'delivery','decision_id':d['id'],'index':2,'delivered':True,'generation_latency_ms':1,'reading_exposure_ms':3900,'early_attempts':2})
        self.feedback(sid,ev2,'safe',180)
        r3=self.store.event(sid,evaluation('TBS',sid,3,points=280));self.assertEqual(r3['snapshot']['decision']['action'],'silence')
        self.assertIn('Cooldown',r3['snapshot']['decision']['rationale'])
        self.assertTrue(self.store.replay(sid)['matches'])

    def test_participant_correction_and_frequency_recorded_as_attributed_evidence(self):
        sid,ev=self.first('TBS');self.feedback(sid,ev,'safe',100)
        ev2=evaluation('TBS',sid,2,points=100);r=self.store.event(sid,ev2);d=r['snapshot']['decision']
        self.store.event(sid,{'kind':'delivery','decision_id':d['id'],'index':2,'delivered':True,'generation_latency_ms':1,'reading_exposure_ms':3500,'early_attempts':0})
        response=self.store.event(sid,{'kind':'response','decision_id':d['id'],'index':2,'feedback':'fewer','text':'I already considered the target.','hypothesis':d['hypothesis'],'block':1})
        self.assertEqual(self.store.get(sid)['preference'],'infrequent')
        self.assertIn('not established fact',response['attribution'])
        self.assertTrue(self.store.replay(sid)['matches'])

    def test_nonexposed_message_cannot_receive_correction(self):
        sid,ev=self.first('TBS');d=self.store.get(sid)['events'][-1]['snapshot']['decision']
        with self.assertRaises(ValidationError):self.store.event(sid,{'kind':'response','decision_id':d['id'],'index':1,'feedback':'disagree','text':'No','hypothesis':d['hypothesis'],'block':1})

    def test_replay_detects_model_drift(self):
        sid,ev=self.first();s=self.store.get(sid);s['policy']['threshold']=.99;self.store.save(s)
        with self.assertRaises(ValidationError):self.store.replay(sid)

    def test_persistence_survives_store_restart_and_rdf_has_no_hidden_state(self):
        sid,ev=self.first();again=Store(self.store.path);self.assertEqual(again.get(sid),self.store.get(sid))
        graph=turtle(again.get(sid));self.assertIn('s:Trial',graph);self.assertIn('s:Intervention',graph)
        self.assertNotIn('volatility_checks',graph);self.assertNotIn('random_draw',graph)

    def test_full_protocol_counts_and_completion_checks(self):
        s=self.store.create({'participant_id':'synthetic_full','task':'MAB','condition':'A','phase':'calibration','protocol':'full','preference':'standard'})
        self.assertEqual(s['total_trials'],200)
        with self.assertRaises(ValidationError):self.store.finish(s['id'],{'completed':True})
        t=self.store.create({'participant_id':'synthetic_full','task':'TBS','condition':'A','phase':'calibration','protocol':'full','preference':'standard'})
        self.assertEqual(t['total_trials'],192)

    def test_calibrated_model_not_claimed_as_observed_mind(self):
        p=calibration_profile('MAB',[])
        self.assertEqual(p['samples'],0);self.assertEqual(p['alpha_plus_interval'],[.15,.75])
        sid,ev=self.first();snapshot=self.store.get(sid)['events'][-1]['snapshot']
        self.assertTrue(any('Overconfidence' in x for x in snapshot['participant']['unknown']))

    def test_pyshacl_adapter_when_available(self):
        try:import pyshacl
        except ImportError:self.skipTest('Optional pySHACL not installed in offline environment')
        sid,ev=self.first();report=shacl_report(self.store.get(sid));self.assertTrue(report['conforms'])


class HTTPTest(unittest.TestCase):
    def test_health_mutation_origin_and_static_routes(self):
        with tempfile.TemporaryDirectory() as td:
            try:server=make_server(0,td)
            except PermissionError:self.skipTest('Environment forbids local socket binding; routes are tested with an in-memory HTTP transport')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with urllib.request.urlopen(base+'/api/health') as r:self.assertEqual(json.load(r)['status'],'ok')
                with urllib.request.urlopen(base+'/inspector.html') as r:self.assertIn(b'Evidence and intervention trace',r.read())
                request=urllib.request.Request(base+'/api/sessions',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://unrelated.example'})
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'/../store.py')
            finally:server.shutdown();server.server_close();thread.join()


class InMemoryHTTPTest(unittest.TestCase):
    def test_actual_http_handler_routes_without_socket_binding(self):
        import io
        from types import SimpleNamespace
        from socratic_prototype.server import Handler
        class Transport:
            def __init__(self,data):self.reader=io.BytesIO(data);self.output=bytearray()
            def makefile(self,*args,**kwargs):return self.reader
            def sendall(self,data):self.output.extend(data)
        with tempfile.TemporaryDirectory() as td:
            server=SimpleNamespace(store=Store(Path(td)/'sessions.sqlite3'))
            def request(path,body=None,origin=None):
                payload=json.dumps(body).encode() if body is not None else b''
                headers=f'Host: 127.0.0.1:8765\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n'
                if origin:headers+='Origin: '+origin+'\r\n'
                raw=(('POST' if body is not None else 'GET')+' '+path+' HTTP/1.0\r\n'+headers+'\r\n').encode()+payload
                t=Transport(raw);Handler(t,('127.0.0.1',1),server)
                head,response=bytes(t.output).split(b'\r\n\r\n',1)
                return int(head.split()[1]),response
            code,data=request('/api/health');self.assertEqual(code,200);self.assertEqual(json.loads(data)['status'],'ok')
            code,data=request('/api/sessions',{'participant_id':'test_http','task':'MAB','condition':'A','phase':'calibration','protocol':'short','preference':'standard'})
            self.assertEqual(code,201);sid=json.loads(data)['id']
            ev=evaluation('MAB',sid,1);code,data=request('/api/sessions/'+sid+'/events',ev);self.assertEqual(code,200)
            code,data=request('/api/sessions/'+sid+'/replay');self.assertTrue(json.loads(data)['matches'])
            code,data=request('/api/sessions/'+sid+'/knowledge.ttl');self.assertIn(b's:Intervention',data)
            code,data=request('/api/sessions',{},'https://unrelated.example');self.assertEqual(code,403)
            code,data=request('/../store.py');self.assertEqual(code,404)
            code,data=request('/inspector.html');self.assertEqual(code,200);self.assertIn(b'Event history',data)

class CorrectionTest(unittest.TestCase):
    def test_disagreement_contests_hypothesis_and_replays(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'sessions.sqlite3')
            ids={t:run_scripted(store,t) for t in ['MAB','TBS']}
            s=store.create({'participant_id':'synthetic_demo','task':'MAB','condition':'F','phase':'assisted','protocol':'short',
                            'preference':'frequent','calibration_ids':ids})
            for index in range(1,8):
                ev=evaluation('MAB',s['id'],index);r=store.event(s['id'],ev);d=r['snapshot']['decision']
                if index==7:
                    self.assertEqual(d['hypothesis'],'underexploration')
                    store.event(s['id'],{'kind':'delivery','decision_id':d['id'],'index':7,'delivered':True,'generation_latency_ms':1,'reading_exposure_ms':3900,'early_attempts':0})
                    store.event(s['id'],{'kind':'response','decision_id':d['id'],'index':7,'feedback':'disagree','text':'I am deliberately establishing a baseline.','hypothesis':d['hypothesis']})
                store.event(s['id'],{'kind':'feedback','trial_id':ev['trial_id'],'index':index,'choice':'blue1','outcome':0,'score_after':0,'timed_out':False,'response_ms':1000})
            result=store.event(s['id'],evaluation('MAB',s['id'],8))
            claims=result['snapshot']['claims']
            self.assertIn('contested',next(c for c in claims if c['id'].endswith('_underexploration'))['statuses'])
            report=next(c for c in claims if 'Participant feedback' in c['content'])
            self.assertNotIn('known',report['statuses']);self.assertIn('participant-self-report',report['provenance'])
            self.assertTrue(store.replay(s['id'])['matches'])

    def test_same_behaviour_different_calibration_changes_interpretation(self):
        from socratic_prototype.engine import hypotheses,POLICY
        from socratic_prototype.models import mab_environment
        h=[{'choice':'red1','outcome':200,'timed_out':False,'trial_id':'t0'}]
        h += [{'choice':'blue1','outcome':100 if i<6 else 0,'timed_out':False,'trial_id':'t'+str(i+1)} for i in range(12)]
        ev={'index':14};env=mab_environment(h,.15)
        answers=[]
        for rate in [.15,.75]:
            s={'task':'MAB','policy':POLICY,'events':[],'calibration_profile':{'alpha_plus':rate,'alpha_minus':rate,'beta':2}}
            hs,stats=hypotheses(s,ev,env,h)
            answers.append(next(x['inference']['posterior'] for x in hs if x['name']=='premature_exploitation'))
        self.assertNotEqual(*answers)

class SummaryTest(unittest.TestCase):
    def test_descriptive_summary_keeps_unmeasured_endpoints_explicit(self):
        from socratic_prototype.analysis import summarize
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'sessions.sqlite3')
            sid=run_scripted(store,'TBS')
            result=summarize(store.get(sid))
            self.assertEqual(result['completed_trials'],24)
            self.assertEqual(result['completed_blocks'],3)
            self.assertEqual(result['silence_decisions'],24)
            self.assertEqual(result['prompts_delivered'],0)
            self.assertIn('Reasoning quality',result['unmeasured'])
            self.assertEqual(store.export(sid)['summary'],result)

    def test_configuration_hash_covers_condition_and_seed(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'sessions.sqlite3')
            s=store.create({'participant_id':'hash_test','task':'MAB','condition':'A','phase':'calibration','protocol':'short','preference':'standard'})
            changed=copy.deepcopy(s);changed['seed']='altered';store.save(changed)
            with self.assertRaises(ValidationError):store.replay(s['id'])

    def test_reviewed_support_is_a_reachable_policy_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'sessions.sqlite3')
            ids={t:run_scripted(store,t) for t in ['MAB','TBS']}
            s=store.create({'participant_id':'synthetic_demo','task':'MAB','condition':'D','phase':'assisted','protocol':'short','preference':'standard','calibration_ids':ids})
            for i,arm in enumerate(['blue1','blue2','blue3','red1','red2','red3'],1):
                ev=evaluation('MAB',s['id'],i);store.event(s['id'],ev)
                store.event(s['id'],{'kind':'feedback','trial_id':ev['trial_id'],'index':i,'choice':arm,'outcome':0,'score_after':0,'timed_out':False,'response_ms':1000})
            r=store.event(s['id'],evaluation('MAB',s['id'],7))
            self.assertEqual(r['snapshot']['decision']['action'],'support')

if __name__=='__main__':unittest.main()
