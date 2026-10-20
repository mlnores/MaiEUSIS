"""Bounded language realisation. The policy owns the action and evidence.

The default adapter selects reviewed wording. The generated-question contract
and its explicit semantic limitations live in grounding.py. Providers are opt-in
through SOCRATIC_LLM=ollama or SOCRATIC_LLM=openai.
"""
import json
import os
import time
import urllib.request
from urllib.parse import urlsplit
from .validation import fields, require


def validate_proposal(proposal, action, claims, messages):
    fields(proposal,['action','claim_ids','message','updates'])
    require(proposal['action']==action,'Language output changed policy action')
    require(proposal['claim_ids']==claims,'Language output changed evidence')
    require(proposal['message'] in messages,'Unreviewed or ungrounded wording')
    require(isinstance(proposal['updates'],list),'Updates must be a list')
    for u in proposal['updates']:
        fields(u,['claim_id','status'])
        require(u['claim_id'] in claims and u['status']=='inferred','Cannot promote an interpretation to a fact')
    return proposal


def proposal_schema(action, claims, messages):
    return {'type':'object','additionalProperties':False,'properties':{
        'action':{'type':'string','enum':[action]},
        'claim_ids':{'type':'array','items':{'type':'string','enum':claims}},
        'message':{'type':'string','enum':messages},
        'updates':{'type':'array','items':{'type':'object','additionalProperties':False,'properties':{
            'claim_id':{'type':'string','enum':claims},'status':{'type':'string','enum':['inferred']}},'required':['claim_id','status']}}
    },'required':['action','claim_ids','message','updates']}


INSTRUCTIONS = ('Express the selected intervention by choosing one approved message verbatim. '
                'Preserve exactly the provided action and ordered claim IDs. '
                'Return updates as an empty list. Do not add claims. Return only a JSON object.')


def configuration():
    """Non-secret settings frozen into new sessions; replay never reads credentials."""
    provider=os.environ.get('SOCRATIC_LLM','offline')
    mode=os.environ.get('SOCRATIC_LANGUAGE_MODE','bounded')
    require(mode in {'bounded','generated'},'SOCRATIC_LANGUAGE_MODE must be bounded or generated')
    return {'version':'language-0.2','provider':provider,'mode':mode,
            'model':os.environ.get('OLLAMA_MODEL' if provider=='ollama' else 'OPENAI_MODEL','') if provider in {'ollama','openai'} else '',
            'base_url':_local_base_url(os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11434')) if provider=='ollama' else '',
            'interpret_responses':os.environ.get('SOCRATIC_INTERPRET_RESPONSES','0')=='1'}


def _openai(action, claims, messages, schema, timeout, config=None):
    model=config['model'] if config else os.environ['OPENAI_MODEL']
    payload={'model':model,'store':False,
             'instructions':INSTRUCTIONS,
             'input':json.dumps({'action':action,'claim_ids':claims,'approved_messages':messages}),
             'text':{'format':{'type':'json_schema','name':'grounded_intervention','strict':True,'schema':schema}}}
    request=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={
        'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:data=json.load(response)
    require(data.get('status')=='completed','Incomplete or refused generation')
    output=''.join(c['text'] for o in data.get('output',[]) if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
    return json.loads(output), model


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Local Ollama requests cannot redirect')


def _local_base_url(base):
    base=base.rstrip('/')
    parsed=urlsplit(base)
    require(parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'}
            and parsed.username is None and parsed.password is None and not parsed.path
            and not parsed.query and not parsed.fragment,'Ollama must use a loopback HTTP URL')
    require(parsed.port is None or 1<=parsed.port<=65535,'Invalid Ollama port')
    return base


def request_ollama(instructions, data, schema, timeout, config=None):
    """Shared local transport for bounded wording, questions and response proposals."""
    config=config or configuration()
    require(config['provider']=='ollama','Generated language currently requires local Ollama')
    model=config['model'].strip()
    require(model and not model.lower().endswith(':cloud'),'Set OLLAMA_MODEL to a local model')
    base=_local_base_url(config['base_url'])
    payload={'model':model,'stream':False,'think':False,'keep_alive':'10m',
             'options':{'temperature':0},'format':schema,
             'messages':[{'role':'system','content':instructions},
                         {'role':'user','content':json.dumps(data)}]}
    request=urllib.request.Request(base+'/api/chat',data=json.dumps(payload).encode(),
                                   headers={'Content-Type':'application/json'})
    # Neither environment HTTP proxies nor redirects can move these requests off-device.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    with opener.open(request,timeout=timeout) as response:data=json.load(response)
    require(data.get('done') is True and data.get('done_reason')=='stop','Incomplete or truncated generation')
    return json.loads(data['message']['content']), model


def _ollama(action, claims, messages, schema, timeout, config=None):
    return request_ollama(INSTRUCTIONS,{'action':action,'claim_ids':claims,
                          'approved_messages':messages,'response_schema':schema},schema,timeout,config)


def realise(action, claims, messages, timeout=.8, recorded=None, config=None):
    if recorded is not None:
        p=validate_proposal(recorded['proposal'],action,claims,messages)
        require(not p['updates'],'Phase 1 language realisation cannot alter model claims')
        return {**recorded,'proposal':p}
    proposal={'action':action,'claim_ids':claims,'message':messages[0],'updates':[]}
    result={'mode':'reviewed-template','proposal':proposal,'validation':'passed','generation_ms':0}
    provider=config['provider'] if config else os.environ.get('SOCRATIC_LLM','offline')
    if provider in {'','offline','template'}:return result
    if provider not in {'openai','ollama'}:
        result['fallback_reason']='Unknown language provider; reviewed template used.'
        return result
    model=config['model'] if config else os.environ.get('OPENAI_MODEL' if provider=='openai' else 'OLLAMA_MODEL','')
    if provider=='openai' and (not os.environ.get('OPENAI_API_KEY') or not model):
        result['fallback_reason']='Missing server-side API key or model; reviewed template used.'
        return result
    if provider=='ollama' and not model.strip():
        result['fallback_reason']='Missing OLLAMA_MODEL; reviewed template used.'
        return result
    generation_start=time.perf_counter()
    try:
        adapter=_ollama if provider=='ollama' else _openai
        proposal,model=adapter(action,claims,messages,proposal_schema(action,claims,messages),timeout,config)
        candidate=validate_proposal(proposal,action,claims,messages)
        require(not candidate['updates'],'Phase 1 language realisation cannot alter model claims')
        result={'mode':provider+'-bounded','proposal':candidate,'validation':'passed','model':model}
    except Exception as error:
        # Do not persist provider bodies, keys or request headers.
        result['fallback_reason']='Provider or validation failure: '+type(error).__name__
    result['generation_ms']=round((time.perf_counter()-generation_start)*1000,3)
    return result


def main():
    import argparse
    import math
    parser=argparse.ArgumentParser(description='Check and warm up the configured language provider without creating a session.')
    parser.add_argument('--check',action='store_true',required=True)
    parser.add_argument('--timeout',type=float,default=60,help='Setup-only timeout in seconds; does not change trial timing.')
    args=parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout<=0:parser.error('--timeout must be positive and finite')
    config=configuration()
    if config['mode']=='generated':
        from .grounding import realise_question
        from .shadow import fixtures
        case=fixtures()[0]
        result=realise_question(case['package'],case['messages'],timeout=args.timeout,config=config)
    else:
        result=realise('ask',['setup-check'],['What evidence would make you revise your choice?'],timeout=args.timeout,config=config)
    print(json.dumps(result,indent=2))
    return 0 if result['mode'] in {'ollama-bounded','openai-bounded','ollama-generated'} else 1


if __name__=='__main__':
    raise SystemExit(main())
