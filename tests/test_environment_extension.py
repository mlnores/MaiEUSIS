"""A third environment through the real study, actor, graph, store and UI manifest."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from socratic_prototype.agents import Participant
from socratic_prototype.simulation import run
from socratic_prototype.store import Store
from socratic_prototype.study import validate_study
from socratic_prototype.tasks import get_task
from socratic_prototype.records import ValidationError
from socratic_prototype.server import render_index,browser_assets
from socratic_prototype.validation import turtle,shacl_report

STUDY={'id':'extension-test','tasks':{'REFERENCE':{'protocol':'mini','calibration_tasks':['REFERENCE']}},'conditions':['A','C','E','D','F']}
SPEC={'id':'extension_actor','source':'Assumed engineering fixture','task_models':{'REFERENCE':{'right_bias':.5}}}

class EnvironmentExtensionTest(unittest.TestCase):
    def test_reference_runs_all_conditions_without_other_task_models(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'s.sqlite3');report=run(store,[SPEC],study=STUDY,repeats=2,seed='extension')
            self.assertEqual(len(report['runs']),10);self.assertEqual(len(report['paired_comparisons']),8)
            for repeat in [0,1]:
                rows=[r for r in report['runs'] if r['repeat']==repeat]
                self.assertEqual({r['condition'] for r in rows},{'A','C','E','D','F'})
                history=[(t['choice'],t['outcome']) for t in rows[0]['trials']]
                for row in rows:
                    self.assertTrue(row['completed']);self.assertEqual(len(row['trials']),4)
                    self.assertEqual([(t['choice'],t['outcome']) for t in row['trials']],history)
                    self.assertEqual(row['trials'][0]['baseline_probabilities'],{'left':.5,'right':.5})
                    self.assertNotEqual(row['trials'][1]['baseline_probabilities'],row['trials'][0]['baseline_probabilities'])
                    self.assertIn('decision_errors',row['metrics']);self.assertNotIn('score',row['metrics'])
                    s=store.get(row['session_id']);self.assertEqual(set(s['calibration_sources']),{'REFERENCE'})
                    self.assertEqual(s['study_configuration']['tasks']['REFERENCE']['protocol'],'mini')
                    public=json.dumps(s);self.assertNotIn('never-in-public-events',public);self.assertNotIn('right_bias',public)
                    self.assertTrue(store.replay(s['id'])['matches'])
                    decisions=[e['snapshot']['decision'] for e in s['events'] if e.get('snapshot',{}).get('decision')]
                    active=[d for d in decisions if d['action']!='silence']
                    if row['condition']=='A':self.assertFalse(active)
                    else:
                        self.assertTrue(active)
                        for d in active:
                            intervention=d['intervention'];self.assertEqual(intervention['focus'],'public_evidence_review')
                            if row['condition'] in {'C','E'}:
                                self.assertEqual(d['action'],'advise');self.assertEqual(intervention['recommendation']['criterion'],'public_expected_gain')
                            else:self.assertIsNone(intervention['recommendation']);self.assertTrue(d['message'].endswith('?'))
                self.assertTrue(all(c['metric_deltas_from_A']['decision_errors']==0 for c in report['paired_comparisons'] if c['repeat']==repeat))
            self.assertNotEqual(report['runs'][0]['environment_seed'],report['runs'][5]['environment_seed'])
            graph=turtle(store.get(report['runs'][0]['session_id']))
            self.assertIn('@prefix reference:',graph);self.assertNotIn('@prefix mab:',graph);self.assertNotIn('@prefix tbs:',graph)
            self.assertTrue(shacl_report(store.get(report['runs'][0]['session_id']))['conforms'])

    def test_study_preflight_and_fresh_actor_state(self):
        ev={'options':[{'id':'left'},{'id':'right'}]}
        a=Participant(SPEC,'REFERENCE');b=Participant(SPEC,'REFERENCE');before=b.baseline(ev)
        a.observe({'points':0},{'choice':'left','outcome':1,'timed_out':False})
        self.assertNotEqual(a.baseline(ev),before);self.assertEqual(b.baseline(ev),before)
        bad=copy.deepcopy(STUDY);bad['tasks']['REFERENCE']['protocol']='short'
        with self.assertRaises(ValidationError):validate_study(bad,simulation=True)
        bad=copy.deepcopy(STUDY);bad['tasks']['REFERENCE']['calibration_tasks']=['MAB']
        with self.assertRaises(ValidationError):validate_study(bad,simulation=True)
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'s.sqlite3')
            with self.assertRaises(ValidationError):run(store,[{**SPEC,'task_models':{'MAB':{'alpha_plus':.3,'alpha_minus':.3,'beta':2}}}],study=STUDY)
            self.assertEqual(store.list(),[])

    def test_server_manifest_selects_only_study_adapters_and_controls(self):
        page=render_index(STUDY)
        self.assertIn('id="startReference"',page);self.assertIn('id="referenceCalibration"',page)
        self.assertIn('src="/task-adapters/reference.js"',page);self.assertIn('"mini"',page)
        for task in ['mab','tbs']:
            self.assertNotIn('/task-adapters/'+task+'.js',page)
        self.assertNotIn('id="mabCalibration"',page);self.assertNotIn('id="tbsCalibration"',page)
        self.assertTrue(browser_assets()['/task-adapters/reference.js'].is_file())
        self.assertEqual(get_task('REFERENCE').browser_adapter()['start_id'],'startReference')

    def test_http_routes_apply_the_selected_study(self):
        import io
        from types import SimpleNamespace
        from socratic_prototype.server import Handler
        class Transport:
            def __init__(self,data):self.reader=io.BytesIO(data);self.output=bytearray()
            def makefile(self,*args,**kwargs):return self.reader
            def sendall(self,data):self.output.extend(data)
        with tempfile.TemporaryDirectory() as td:
            study=copy.deepcopy(STUDY);study['conditions']=['F']
            server=SimpleNamespace(store=Store(Path(td)/'s.sqlite3'),study=study)
            def request(path,body=None):
                payload=json.dumps(body).encode() if body is not None else b''
                headers=f'Host: 127.0.0.1:8765\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n'
                transport=Transport((('POST' if body is not None else 'GET')+' '+path+' HTTP/1.0\r\n'+headers+'\r\n').encode()+payload)
                Handler(transport,('127.0.0.1',1),server)
                head,response=bytes(transport.output).split(b'\r\n\r\n',1)
                return int(head.split()[1]),response
            code,page=request('/');self.assertEqual(code,200);self.assertIn(b'startReference',page);self.assertNotIn(b'id="startMab"',page)
            code,script=request('/task-adapters/reference.js');self.assertEqual(code,200);self.assertIn(b'registerBrowserTask',script)
            code,config=request('/api/study');self.assertEqual(code,200);self.assertEqual(json.loads(config)['conditions'],['F'])
            base=dict(participant_id='http_extension',task='REFERENCE',condition='A',phase='calibration',protocol='mini',preference='standard')
            self.assertEqual(request('/api/sessions',{**base,'task':'MAB'})[0],422)
            self.assertEqual(request('/api/sessions',{**base,'protocol':'short'})[0],422)
            self.assertEqual(request('/api/sessions',{**base,'phase':'assisted','condition':'C'})[0],422)
            self.assertEqual(server.store.list(),[])
            code,created=request('/api/sessions',base);self.assertEqual(code,201)
            self.assertEqual(server.store.get(json.loads(created)['id'])['study_configuration']['tasks'],study['tasks'])
