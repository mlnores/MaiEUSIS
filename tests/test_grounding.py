import importlib.util
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.grounding import (build_evidence_package,prompt_package,validate_question,
    realise_question,validate_response_proposal,interpret_response,reviewed_responses)
from socratic_prototype.shadow import fixtures,evaluate,write_report,cases_from_trace,main
from socratic_prototype.validation import ValidationError
from socratic_prototype.store import Store,configuration_fields,digest
from socratic_prototype.demo import run_scripted,evaluation


CONFIG={'version':'language-0.2','provider':'ollama','model':'fixture-local','mode':'generated',
        'base_url':'http://127.0.0.1:11434','interpret_responses':True}


def question(package):
    return {'action':package['action'],'evidence_refs':package['required_evidence_refs'],
            'uncertainty_refs':package['required_uncertainty_refs'],
            'question':'What evidence would justify reconsidering your current approach?','updates':[]}


def provider(instructions,data,schema,timeout,config):
    if 'text' in data:
        updates=[]
        if data['text'].startswith('I deliberately'):
            updates=[{'kind':'reported_strategy','quote':data['text'],'hypothesis':None}]
        return {'updates':updates},config['model']
    return question(data),config['model']


class GroundingTest(unittest.TestCase):
    def setUp(self):
        self.case=fixtures()[0];self.package=self.case['package']

    def test_generic_is_task_aware_without_a_person_model(self):
        package=next(c['package'] for c in fixtures() if c['id']=='conventional_boundary')
        self.assertEqual(package['task'],'TBS')
        self.assertTrue(package['environment']);self.assertFalse(package['participant'])

    def test_task_only_package_excludes_calibration_and_person_reports(self):
        for case in fixtures():
            if case['kind']!='question':continue
            p=case['package']
            if p['condition'] in {'C','D'}:self.assertEqual(p['participant'],{})
            if p['condition']=='F':self.assertIn('calibration',p['participant'])
            prompt=prompt_package(p)
            self.assertNotIn('synthetic_evidence',json.dumps(prompt))
            self.assertNotIn('synthetic_trial_',json.dumps(prompt))

    def test_projection_ignores_hidden_and_nested_unknown_fields(self):
        # Construct source objects with deliberately forbidden extra fields.
        p=self.package
        claims=[{'id':c['source_id'],'content':c['content'],'statuses':c['statuses'],'secret_schedule':'SECRET'} for c in p['claims']]
        snap={'claims':claims,'participant':{'calibration':{'task':'MAB','secret_schedule':'SECRET'}},
              'environment':{'arms':[{'arm':'blue1','samples':1,'estimated_value':0,'change':{'posterior':.15,'secret_schedule':'SECRET'},
                                      'true_probabilities':'SECRET'}],'unknown':[],'assumptions':[]},
              'arguments':[{'id':'s','reason':'Uncertain evidence'},{'id':'o','reason':'Noise is plausible'}]}
        selected={'action':'ask','name':'possible_change','claim_ids':[claims[0]['id']],
                  'supporting_argument':'s','opposing_argument':'o'}
        session={'condition':'D','task':'MAB','events':[],'policy':{'window_trials':12,'correction_expiry_trials':8},'hidden':'SECRET'}
        ev={'index':1,'trial_id':'current','probabilities':'SECRET','options':['SECRET']}
        output=build_evidence_package(session,ev,snap,selected,[])
        self.assertNotIn('SECRET',json.dumps(output))
        self.assertNotIn('options',output['environment'])

    def test_generated_question_has_checked_links_but_no_semantic_guarantee(self):
        checks=validate_question(question(self.package),self.package)
        self.assertEqual(checks['semantic_grounding'],'unverified')
        with patch('socratic_prototype.grounding.request_ollama',side_effect=provider) as request:
            result=realise_question(self.package,self.case['messages'],config=CONFIG)
        self.assertEqual(result['mode'],'ollama-generated')
        self.assertEqual(result['proposal']['claim_ids'],['synthetic_evidence'])
        self.assertTrue(result['proposal']['message'].startswith(self.package['display_context']))
        self.assertNotIn('source_id',json.dumps(request.call_args.args[1]))

    def test_native_transport_receives_new_schema_and_compact_evidence(self):
        data={'done':True,'done_reason':'stop','message':{'content':json.dumps(question(self.package))}}
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value=io.BytesIO(json.dumps(data).encode())
            result=realise_question(self.package,self.case['messages'],config=CONFIG)
        self.assertEqual(result['mode'],'ollama-generated')
        request=build.return_value.open.call_args.args[0];payload=json.loads(request.data)
        self.assertEqual(payload['model'],'fixture-local');self.assertFalse(request.has_header('Authorization'))
        self.assertIn('question',payload['format']['properties'])
        self.assertNotIn('enum',payload['format']['properties']['question'])
        package=json.loads(payload['messages'][1]['content'])
        self.assertIn('claims',package);self.assertNotIn('approved_messages',package)
        self.assertNotIn('synthetic_evidence',json.dumps(package))

    def test_malformed_or_ungrounded_proposals_fall_back_with_reason(self):
        good=question(self.package)
        changes=[{'action':'advise'},{'evidence_refs':['invented']},{'uncertainty_refs':[]},
                 {'updates':[{'status':'known'}]},{'question':'Choose blue now.'},
                 {'question':'What makes you overconfident about your current choice?'},
                 {'question':'What makes option 7 the best choice?'},
                 {'question':'Could you choose the blue option next?'},
                 {'question':'What evidence supports your current choice? Choose red.'},
                 {'question':'How could <script> alter your current choice?'},
                 {'question':'What evidence\nwould justify reconsidering your current approach?'}]
        for change in changes:
            with self.subTest(change=change),patch('socratic_prototype.grounding.request_ollama',return_value=(good|change,'fixture-local')):
                result=realise_question(self.package,self.case['messages'],config=CONFIG)
                self.assertEqual(result['mode'],'reviewed-template')
                self.assertEqual(result['proposal']['message'],self.case['messages'][0])
                self.assertIn('rejection',result);self.assertIn('rejected_generation',result)

    def test_conventional_conditions_make_no_question_request(self):
        with patch('socratic_prototype.grounding.request_ollama',side_effect=AssertionError('Provider called')):
            for case in fixtures():
                if case['kind']=='question' and case['package']['condition'] in {'C','E'}:
                    self.assertEqual(realise_question(case['package'],case['messages'],config=CONFIG)['mode'],'reviewed-template')

    def test_provider_failure_and_wall_deadline_fall_back(self):
        with patch('socratic_prototype.grounding.request_ollama',side_effect=TimeoutError('sensitive provider body')):
            r=realise_question(self.package,self.case['messages'],config=CONFIG)
            self.assertNotIn('sensitive provider body',json.dumps(r))
        with patch('socratic_prototype.grounding.request_ollama',side_effect=provider),patch('socratic_prototype.grounding.time.perf_counter',side_effect=[0,4,4.1]):
            r=realise_question(self.package,self.case['messages'],timeout=3,config=CONFIG)
            self.assertEqual(r['mode'],'reviewed-template');self.assertIn('deadline',r['rejection'])

    def test_generated_replay_rejects_changed_evidence_or_rendering(self):
        with patch('socratic_prototype.grounding.request_ollama',side_effect=provider):
            result=realise_question(self.package,self.case['messages'],config=CONFIG)
        with patch('socratic_prototype.grounding.request_ollama',side_effect=AssertionError('Replay called provider')):
            self.assertEqual(realise_question(self.package,self.case['messages'],recorded=result),result)
            changed=copy.deepcopy(self.package);changed['claims'][0]['content']='Different evidence'
            with self.assertRaises(ValidationError):realise_question(changed,self.case['messages'],recorded=result)
            changed=copy.deepcopy(result);changed['proposal']['message']='An unrecorded message'
            with self.assertRaises(ValidationError):realise_question(self.package,self.case['messages'],recorded=changed)

    def test_response_proposals_require_literal_quotes_and_delivered_hypothesis(self):
        response={'text':'I deliberately explore alternatives.','feedback':'dismiss'}
        proposal={'updates':[{'kind':'reported_strategy','quote':response['text'],'hypothesis':None}]}
        self.assertEqual(validate_response_proposal(proposal,response,'underexploration'),proposal)
        for update in [{'kind':'known','quote':response['text'],'hypothesis':None},
                       {'kind':'reported_strategy','quote':'An invented explanation','hypothesis':None},
                       {'kind':'contest_hypothesis','quote':response['text'],'hypothesis':'other'},
                       {'kind':'reported_strategy','quote':response['text'],'hypothesis':'underexploration'}]:
            with self.assertRaises(ValidationError):validate_response_proposal({'updates':[update]},response,'underexploration')
        decision={'hypothesis':'underexploration','message':'What evidence supports continuing?'}
        with patch('socratic_prototype.grounding.request_ollama',side_effect=provider):
            result=interpret_response(response,decision,CONFIG)
        self.assertEqual(result['status'],'pending-review')
        self.assertEqual(result['semantic_grounding'],'unverified')
        with patch('socratic_prototype.grounding.request_ollama',side_effect=AssertionError('Replay request')):
            self.assertEqual(interpret_response(response,decision,CONFIG,recorded=result),result)

    def test_shadow_report_is_separate_escaped_and_requires_human_review(self):
        cases=fixtures()
        with patch('socratic_prototype.grounding.request_ollama',side_effect=provider):
            report=evaluate(cases,CONFIG)
        self.assertEqual(report['summary']['generated_questions_passing_hard_checks'],6)
        self.assertEqual(report['summary']['successful_question_latency_samples'],6)
        self.assertFalse(report['summary']['human_review_complete'])
        for row in report['cases']:self.assertIsNone(row['human_review']['grounded'])
        report['cases'][0]['human_review']['notes']='<script>alert("unsafe")</script>'
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';write_report(report,path)
            self.assertEqual(json.loads(path.read_text()),report)
            page=path.with_suffix('.html').read_text()
            self.assertIn('&lt;script&gt;',page);self.assertNotIn('<script>',page)
        with patch('socratic_prototype.grounding.request_ollama',side_effect=TimeoutError('no provider')):
            failed=evaluate([self.case],CONFIG)
        self.assertIsNone(failed['summary']['median_generation_ms'])
        self.assertEqual(failed['summary']['successful_question_latency_samples'],0)

    def test_shadow_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'SOCRATIC_LLM':'ollama','OLLAMA_MODEL':'fixture-local'}),\
             patch('socratic_prototype.grounding.request_ollama',side_effect=provider),patch('sys.stdout',new_callable=io.StringIO):
            path=Path(td)/'review.json'
            with patch('sys.argv',['shadow','--fixtures','--limit','2','--output',str(path)]):self.assertEqual(main(),0)
            self.assertTrue(path.with_suffix('.html').exists())

    def test_shadow_cli_cannot_overwrite_source_via_hardlink(self):
        with tempfile.TemporaryDirectory() as td,patch('sys.stderr',new_callable=io.StringIO):
            source=Path(td)/'source.json';source.write_text('{"original":true}')
            output=Path(td)/'output.json';os.link(source,output)
            with patch('sys.argv',['shadow','--trace',str(source),'--output',str(output)]),self.assertRaises(SystemExit):main()
            self.assertEqual(source.read_text(),'{"original":true}')


HAS_RDF=importlib.util.find_spec("rdflib") is not None

@unittest.skipUnless(HAS_RDF,'Live generated assistance requires RDFLib')
class GeneratedSessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.store=Store(Path(cls.temp.name)/'sessions.sqlite3')
        with patch.dict(os.environ,{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded','SOCRATIC_INTERPRET_RESPONSES':'0'}):
            cls.calibrations={t:run_scripted(cls.store,t) for t in ['MAB','TBS']}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        env=patch.dict(os.environ,{'SOCRATIC_LLM':'ollama','SOCRATIC_LANGUAGE_MODE':'generated',
                        'OLLAMA_MODEL':'fixture-local','SOCRATIC_INTERPRET_RESPONSES':'1'})
        env.start();self.addCleanup(env.stop)
        request=patch('socratic_prototype.grounding.request_ollama',side_effect=provider)
        self.request=request.start();self.addCleanup(request.stop)

    def session_with_response(self):
        s=self.store.create({'participant_id':'synthetic_demo','task':'MAB','condition':'F','phase':'assisted',
            'protocol':'short','preference':'standard','calibration_ids':self.calibrations})
        for i in range(1,8):
            r=self.store.event(s['id'],evaluation('MAB',s['id'],i));d=r['snapshot']['decision']
            self.store.event(s['id'],{'kind':'delivery','decision_id':d['id'],'index':i,'delivered':d['action']!='silence',
                'generation_latency_ms':0,'reading_exposure_ms':3000 if d['action']!='silence' else 0,'early_attempts':0})
            if i<7:self.store.event(s['id'],self.feedback(s['id'],i))
        self.assertEqual(d['hypothesis'],'underexploration')
        text='I deliberately explore alternatives to compare the feedback.'
        def proposal(*args):
            return {'updates':[{'kind':'reported_strategy','quote':text,'hypothesis':None},
                               {'kind':'contest_hypothesis','quote':text,'hypothesis':'underexploration'}]},'fixture-local'
        with patch('socratic_prototype.grounding.request_ollama',side_effect=proposal):
            response=self.store.event(s['id'],{'kind':'response','decision_id':d['id'],'index':7,
                         'feedback':'dismiss','text':text,'hypothesis':d['hypothesis']})
        self.store.event(s['id'],self.feedback(s['id'],7))
        return s['id'],response

    @staticmethod
    def feedback(sid,index):
        return {'kind':'feedback','trial_id':sid+'_trial_'+str(index),'index':index,
                'choice':'blue1','outcome':0,'score_after':0,'timed_out':False,'response_ms':1000}

    def test_interpretation_is_pending_until_review_then_scoped_and_replayable(self):
        sid,response=self.session_with_response();before=self.store.get(sid)
        self.assertEqual(response['interpretation']['status'],'pending-review')
        self.assertEqual(reviewed_responses(before,{'index':8}),[])
        review=self.store.event(sid,{'kind':'interpretation-review','response_event_id':response['id'],'accept':True,'reviewer':'researcher'})
        r=self.store.event(sid,evaluation('MAB',sid,8));snap=r['snapshot']
        hyp=next(h for h in snap['participant']['hypotheses'] if h['name']=='underexploration')
        self.assertIn(review['id'],hyp['contested_by'])
        quoted=[c for c in snap['claims'] if 'Researcher-reviewed participant' in c['content']]
        self.assertEqual(len(quoted),2)
        self.assertTrue(all('known' not in c['statuses'] for c in quoted))
        self.assertTrue(any(c.get('contradicts') for c in quoted))
        self.assertEqual(self.store.get(sid)['events'][:len(before['events'])],before['events'])
        self.assertEqual(reviewed_responses(self.store.get(sid),{'index':16}),[])
        scoped=self.store.get(sid);scoped['task']='TBS'
        self.assertEqual(reviewed_responses(scoped,{'index':8,'block':2}),[])
        with patch('socratic_prototype.grounding.request_ollama',side_effect=AssertionError('Replay called model')),\
             patch('urllib.request.urlopen',side_effect=AssertionError('Replay called provider')),\
             patch.dict(os.environ,{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded'}):
            self.assertTrue(self.store.replay(sid)['matches'])
        source=self.store.export(sid);copy_before=copy.deepcopy(source)
        with patch('socratic_prototype.grounding.request_ollama',side_effect=provider):evaluate(cases_from_trace(source),CONFIG)
        self.assertEqual(source,copy_before)
        with self.assertRaises(ValidationError):self.store.event(sid,review['input']|{'reviewer':'another'})

    def test_rejected_interpretation_has_no_policy_effect(self):
        sid,response=self.session_with_response()
        self.store.event(sid,{'kind':'interpretation-review','response_event_id':response['id'],'accept':False,'reviewer':'researcher'})
        r=self.store.event(sid,evaluation('MAB',sid,8))
        self.assertFalse(any(h['contested_by'] for h in r['snapshot']['participant']['hypotheses']))
        self.assertFalse(any('Researcher-reviewed' in c['content'] for c in r['snapshot']['claims']))
        self.assertTrue(self.store.replay(sid)['matches'])

    def test_review_after_finish_only_appends_an_audit_event(self):
        sid,response=self.session_with_response();self.store.finish(sid,{'completed':False})
        before=copy.deepcopy(self.store.get(sid)['events'])
        self.store.event(sid,{'kind':'interpretation-review','response_event_id':response['id'],'accept':True,'reviewer':'researcher'})
        self.assertEqual(self.store.get(sid)['events'][:-1],before)
        self.assertTrue(self.store.replay(sid)['matches'])
        with self.assertRaises(ValidationError):self.store.event(sid,evaluation('MAB',sid,8))

    def test_generated_mab_and_tbs_complete_and_replay(self):
        for task in ['MAB','TBS']:
            with self.subTest(task=task):
                sid=run_scripted(self.store,task,'F','assisted',self.calibrations)
                s=self.store.get(sid);self.assertTrue(s['completed'])
                active=[e['snapshot']['decision'] for e in s['events']
                        if e.get('snapshot',{}).get('decision',{}).get('action','silence')!='silence']
                self.assertTrue(active)
                self.assertTrue(all(d['language']['mode']=='ollama-generated' for d in active))
                with patch('socratic_prototype.grounding.request_ollama',side_effect=AssertionError('Replay called model')):
                    self.assertTrue(self.store.replay(sid)['matches'])

    def test_configuration_is_frozen_and_hash_covers_language_settings(self):
        sid,response=self.session_with_response();s=self.store.get(sid)
        self.assertEqual(s['language_configuration']['mode'],'generated')
        s['language_configuration']['model']='different';self.store.save(s)
        with self.assertRaises(ValidationError):self.store.replay(sid)

    def test_legacy_bounded_trace_replay_still_works(self):
        with patch.dict(os.environ,{'SOCRATIC_LLM':'offline','SOCRATIC_LANGUAGE_MODE':'bounded','SOCRATIC_INTERPRET_RESPONSES':'0'}):
            s=self.store.create({'participant_id':'synthetic_demo','task':'MAB','condition':'F','phase':'assisted',
                                 'protocol':'short','preference':'standard','calibration_ids':self.calibrations})
            del s['language_configuration'];s['configuration_digest']=digest({k:s[k] for k in configuration_fields(s)})
            self.store.save(s)
            for i in range(1,8):
                self.store.event(s['id'],evaluation('MAB',s['id'],i))
                self.store.event(s['id'],self.feedback(s['id'],i))
            last=self.store.get(s['id'])['events'][-2]['snapshot']['decision']
            self.assertNotEqual(last['action'],'silence');self.assertNotIn('evidence_package',last)
            self.assertTrue(self.store.replay(s['id'])['matches'])


if __name__=='__main__':unittest.main()
