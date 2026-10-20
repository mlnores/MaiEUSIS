"""Provider contract tests; no live model or network is required."""
import copy
import io
import json
import os
import unittest
from unittest.mock import patch, Mock

from socratic_prototype.language import realise, _NoRedirect


class LanguageProviderTest(unittest.TestCase):
    def setUp(self):
        self.action='ask'
        self.claims=['c1','c2']
        self.messages=['What evidence would change your choice?','What would you check next?']
        self.proposal={'action':self.action,'claim_ids':self.claims,'message':self.messages[1],'updates':[]}
        self.env=patch.dict(os.environ,{'SOCRATIC_LLM':'ollama','OLLAMA_MODEL':'qwen3:4b',
                            'OLLAMA_BASE_URL':'http://127.0.0.1:11434',
                            'OPENAI_API_KEY':'must-not-be-sent','OPENAI_MODEL':'must-not-be-used'})
        self.env.start();self.addCleanup(self.env.stop)
        self.opener=Mock()
        self.open_patch=patch('urllib.request.build_opener',return_value=self.opener)
        self.builder=self.open_patch.start();self.addCleanup(self.open_patch.stop)
        self.external=patch('urllib.request.urlopen',side_effect=AssertionError('External API called'))
        self.external.start();self.addCleanup(self.external.stop)

    def response(self,proposal=None,**extra):
        data={'done':True,'done_reason':'stop','message':{'content':json.dumps(self.proposal if proposal is None else proposal)}}
        data.update(extra)
        self.opener.open.return_value=io.BytesIO(json.dumps(data).encode())

    def run_provider(self,**kwargs):
        return realise(self.action,self.claims,self.messages,**kwargs)

    def test_ollama_request_is_local_bounded_and_nonstreaming(self):
        self.response();result=self.run_provider(timeout=2.5)
        self.assertEqual(result['mode'],'ollama-bounded')
        self.assertEqual(result['proposal'],self.proposal)
        self.assertEqual(result['model'],'qwen3:4b')
        request=self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'http://127.0.0.1:11434/api/chat')
        self.assertEqual(self.opener.open.call_args.kwargs['timeout'],2.5)
        self.assertFalse(request.has_header('Authorization'))
        payload=json.loads(request.data)
        self.assertFalse(payload['stream']);self.assertFalse(payload['think'])
        self.assertEqual(payload['options']['temperature'],0)
        self.assertEqual(payload['keep_alive'],'10m')
        self.assertEqual(payload['format']['properties']['message']['enum'],self.messages)
        self.assertEqual(json.loads(payload['messages'][1]['content'])['claim_ids'],self.claims)
        self.assertNotIn('must-not',request.data.decode())
        self.assertEqual(self.builder.call_args.args[0].proxies,{})
        self.assertIsInstance(self.builder.call_args.args[1],_NoRedirect)

    def test_invalid_proposals_fall_back_to_reviewed_template(self):
        invalid=[self.proposal|{'action':'advise'},self.proposal|{'claim_ids':['invented']},
                 self.proposal|{'claim_ids':list(reversed(self.claims))},
                 self.proposal|{'message':'A made-up probability'},
                 self.proposal|{'updates':[{'claim_id':'c1','status':'known'}]},
                 self.proposal|{'updates':[{'claim_id':'c1','status':'inferred'}]}]
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                self.response(candidate);result=self.run_provider()
                self.assertEqual(result['mode'],'reviewed-template')
                self.assertEqual(result['proposal']['message'],self.messages[0])
                self.assertIn('fallback_reason',result)

    def test_incomplete_truncated_and_malformed_responses_fall_back(self):
        for extra in [{'done':False},{'done_reason':'length'},{'message':{'content':'not JSON'}}]:
            with self.subTest(extra=extra):
                self.response(**extra)
                self.assertEqual(self.run_provider()['mode'],'reviewed-template')

    def test_timeout_and_provider_failure_do_not_expose_error_body(self):
        for error in [TimeoutError('secret body'),OSError('secret body')]:
            self.opener.open.side_effect=error;result=self.run_provider()
            self.assertEqual(result['mode'],'reviewed-template')
            self.assertNotIn('secret body',json.dumps(result))

    def test_remote_or_credentialled_urls_are_rejected_before_request(self):
        for url in ['http://example.com:11434','https://127.0.0.1:11434',
                    'http://user:password@localhost:11434','http://localhost:11434/api',
                    'http://localhost:11434?remote=1','http://localhost:99999']:
            with self.subTest(url=url),patch.dict(os.environ,{'OLLAMA_BASE_URL':url}):
                self.assertEqual(self.run_provider()['mode'],'reviewed-template')
                self.opener.open.assert_not_called()

    def test_localhost_and_ipv6_loopback_supported(self):
        for base in ['http://localhost:11434/','http://[::1]:11434']:
            with self.subTest(base=base),patch.dict(os.environ,{'OLLAMA_BASE_URL':base}):
                self.response();self.assertEqual(self.run_provider()['mode'],'ollama-bounded')

    def test_missing_or_cloud_model_makes_no_requests(self):
        for model in ['', '  ', 'model:cloud']:
            with self.subTest(model=model),patch.dict(os.environ,{'OLLAMA_MODEL':model}):
                self.assertEqual(self.run_provider()['mode'],'reviewed-template')
                self.opener.open.assert_not_called()

    def test_recorded_replay_bypasses_provider(self):
        recorded={'mode':'ollama-bounded','proposal':copy.deepcopy(self.proposal),
                  'model':'old-model','validation':'passed','generation_ms':42}
        self.assertEqual(self.run_provider(recorded=recorded),recorded)
        self.opener.open.assert_not_called();self.builder.assert_not_called()

    def test_redirects_cannot_leave_loopback(self):
        with self.assertRaises(ValueError):
            _NoRedirect().redirect_request(None,None,302,'redirect',{},'https://example.com')

    def test_openai_adapter_retains_validated_response_contract(self):
        data={'status':'completed','output':[{'type':'message','content':[
              {'type':'output_text','text':json.dumps(self.proposal)}]}]}
        with patch.dict(os.environ,{'SOCRATIC_LLM':'openai'}),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(data).encode())) as request:
            result=self.run_provider()
            self.assertEqual(result['mode'],'openai-bounded')
            self.assertEqual(result['proposal'],self.proposal)
            self.assertEqual(request.call_args.args[0].full_url,'https://api.openai.com/v1/responses')
        self.opener.open.assert_not_called()


if __name__=='__main__':
    unittest.main()
