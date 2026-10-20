"""Bounded language realisation. The policy owns the action and evidence.

The optional LLM selects among reviewed, grounded wording variants. Arbitrary
prose is deliberately not accepted by this first validator. No API calls occur
unless SOCRATIC_LLM=openai and OPENAI_API_KEY and OPENAI_MODEL are set.
"""
import json
import os
import time
import urllib.request
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


def realise(action, claims, messages, timeout=.8, recorded=None):
    if recorded is not None:
        p=validate_proposal(recorded['proposal'],action,claims,messages)
        return {**recorded,'proposal':p}
    proposal={'action':action,'claim_ids':claims,'message':messages[0],'updates':[]}
    result={'mode':'reviewed-template','proposal':proposal,'validation':'passed','generation_ms':0}
    if os.environ.get('SOCRATIC_LLM')!='openai':return result
    if not os.environ.get('OPENAI_API_KEY') or not os.environ.get('OPENAI_MODEL'):
        result['fallback_reason']='Missing server-side API key or model; reviewed template used.'
        return result
    schema={'type':'object','additionalProperties':False,'properties':{
        'action':{'type':'string','enum':[action]},
        'claim_ids':{'type':'array','items':{'type':'string','enum':claims}},
        'message':{'type':'string','enum':messages},
        'updates':{'type':'array','items':{'type':'object','additionalProperties':False,'properties':{
            'claim_id':{'type':'string','enum':claims},'status':{'type':'string','enum':['inferred']}},'required':['claim_id','status']}}
    },'required':['action','claim_ids','message','updates']}
    payload={'model':os.environ['OPENAI_MODEL'],'store':False,
             'instructions':'Express the selected intervention by choosing one approved message verbatim. Preserve exactly the provided action and ordered claim IDs. Return updates as an empty list. Do not add claims.',
             'input':json.dumps({'action':action,'claim_ids':claims,'approved_messages':messages}),
             'text':{'format':{'type':'json_schema','name':'grounded_intervention','strict':True,'schema':schema}}}
    request=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={
        'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
    generation_start=time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:data=json.load(response)
        require(data.get('status')=='completed','Incomplete or refused generation')
        output=''.join(c['text'] for o in data.get('output',[]) if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
        candidate=validate_proposal(json.loads(output),action,claims,messages)
        require(not candidate['updates'],'Phase 1 language realisation cannot alter model claims')
        result={'mode':'openai-bounded','proposal':candidate,'validation':'passed','model':os.environ['OPENAI_MODEL']}
    except Exception as error:
        # Do not persist provider bodies, keys or request headers.
        result['fallback_reason']='Provider or validation failure: '+type(error).__name__
    result['generation_ms']=round((time.perf_counter()-generation_start)*1000,3)
    return result
