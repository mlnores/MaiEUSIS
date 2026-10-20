"""Strict public-event validation and optional real SHACL validation."""
import json
import math
import re
from pathlib import Path
from .models import ARMS

STATUSES = {'known','unknown','assumed','inferred','contested','probable','low-confidence','source-dependent','requires-verification'}
ACTIONS = {'ask','challenge','support','explain','compare','highlight-dependency','request-evidence','advise','silence'}
CONDITIONS = {'A','B','C','D','E','F'}

class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:raise ValidationError(message)


def fields(data, required, optional=()):
    require(isinstance(data,dict),'Expected an object')
    require(set(required)<=data.keys(),f'Missing fields: {sorted(set(required)-data.keys())}')
    require(not data.keys()-set(required)-set(optional),f'Forbidden or unrecognized fields: {sorted(data.keys()-set(required)-set(optional))}')


def number(x, low=-1e9, high=1e9):
    return type(x) in (int,float) and math.isfinite(x) and low<=x<=high


def identity(x):
    return isinstance(x,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',x))


def validate_event(task, event):
    fields(event, ['kind','trial_id','index'], ['options','score','points','target','remaining','block','multiplier',
                                            'choice','outcome','timed_out','response_ms','score_after','points_after'])
    require(identity(event['trial_id']), 'Invalid trial identifier')
    require(type(event['index']) is int and 1<=event['index']<=10000,'Invalid trial index')
    require(event['kind'] in {'evaluation','feedback'},'Unknown event kind')
    common=['kind','trial_id','index']
    if event['kind']=='evaluation':
        allowed=common+(['options','score'] if task=='MAB' else ['options','points','target','remaining','block','multiplier'])
        fields(event,allowed)
        opts=event['options'];require(isinstance(opts,list),'Options must be a list')
        require(len(opts)==(6 if task=='MAB' else 2),'Wrong number of options')
        ids=[]
        for o in opts:
            if task=='MAB':
                fields(o,['id','key','outcomes'])
                require(o['id'] in ARMS,'Unknown arm')
                require(o['outcomes']==([100,0,-100] if o['id'].startswith('blue') else [200,0,-200]),'Invalid displayed outcomes')
            else:
                fields(o,['id','key','amount','probability'])
                require(o['id'] in {'safe','risky'},'Unknown TBS alternative')
                require(number(o['amount'],1,10000),'Invalid amount')
                require(number(o['probability'],0,1),'Invalid displayed probability')
            require(isinstance(o['key'],str) and o['key'] in {'1','2','3','7','8','9'},'Invalid response key')
            ids.append(o['id'])
        require(len(set(ids))==len(opts),'Duplicate option')
        require(len({o['key'] for o in opts})==len(opts),'Duplicate key')
        if task=='TBS':
            require(ids==['safe','risky'],'TBS alternatives must retain their published labels and ordering')
            require([o['key'] for o in opts]==['1','9'],'Incorrect TBS key mapping')
        if task=='MAB':require(number(event['score']), 'Invalid score')
        else:
            for k in ['points','target','multiplier']:require(number(event[k],0,100000),'Invalid '+k)
            require(event['target']>0 and event['multiplier']>=1,'Invalid target or multiplier')
            require(type(event['remaining']) is int and 1<=event['remaining']<=8,'Invalid horizon')
            require(type(event['block']) is int and event['block']>=1,'Invalid block')
            require(event['remaining']==8-(event['index']-1)%8,'Horizon inconsistent with trial')
            require(event['block']==(event['index']-1)//8+1,'Block inconsistent with trial')
    else:
        fields(event,common+['choice','outcome','timed_out','response_ms']+(['score_after'] if task=='MAB' else ['points_after']))
        require(type(event['timed_out']) is bool,'timed_out must be boolean')
        require(event['choice'] in (set(ARMS) if task=='MAB' else {'safe','risky'})|{'NO_RESPONSE'},'Invalid choice')
        require((event['choice']=='NO_RESPONSE')==event['timed_out'],'Timeout inconsistent with choice')
        require(event['response_ms'] is None or number(event['response_ms'],0,60000),'Invalid response time')
        require(number(event['outcome']), 'Invalid outcome')
        require(number(event['score_after'] if task=='MAB' else event['points_after']), 'Invalid resulting score')


def validate_claim(claim, trial_ids):
    required=['id','type','content','statuses','evidence','scope','timestamp','provenance','model_version']
    fields(claim, required, ['confidence','confidence_interpretation','alternatives','revision_conditions','depends_on','revises','contradicts'])
    require(identity(claim['id']),'Invalid claim ID')
    require(claim['type'] in {'Claim','Hypothesis'},'Invalid claim type')
    require(isinstance(claim['content'],str) and bool(claim['content']), 'Claim lacks content')
    statuses=claim['statuses']
    require(isinstance(statuses,list) and bool(statuses) and set(statuses)<=STATUSES,'Invalid epistemic statuses')
    for k in ['scope','timestamp','provenance','model_version']:require(isinstance(claim[k],str) and bool(claim[k]),'Missing '+k)
    require(isinstance(claim['evidence'],list),'Evidence must be a list')
    require(set(claim['evidence'])<=trial_ids, 'Dangling trial evidence')
    if claim['type']=='Hypothesis':
        require('inferred' in statuses,'Hypothesis must remain inferred')
        require(bool(claim['evidence']),'Hypothesis lacks supporting trials')
        require(bool(claim.get('revision_conditions')),'Hypothesis lacks revision conditions')
        require(bool(claim.get('alternatives')),'Hypothesis lacks alternative interpretations')
    if 'confidence' in claim:
        require(number(claim['confidence'],0,1),'Confidence outside [0,1]')
        require(bool(claim.get('confidence_interpretation')),'Confidence lacks interpretation')


def validate_snapshot(snapshot, trial_ids):
    claims=snapshot['claims']; ids={c['id'] for c in claims}
    require(len(ids)==len(claims),'Duplicate claim IDs')
    for c in claims:
        validate_claim(c,trial_ids)
        for relation in ['depends_on','revises','contradicts']:
            require(set(c.get(relation,[]))<=ids|set(snapshot.get('previous_claim_ids',[])),'Dangling claim relation')
    decision=snapshot.get('decision')
    if decision:
        require(decision['action'] in ACTIONS,'Invalid policy action')
        require(bool(decision['rationale']),'Decision lacks rationale, including silence')
        require(bool(decision['claim_ids']) and set(decision['claim_ids'])<=ids,'Decision lacks grounded claims')
        require(decision['action']=='silence' or bool(decision['message']),'Active decision lacks validated message')
    for a in snapshot['arguments']:
        require(bool(a['evidence']) and set(a['evidence'])<=ids,'Argument lacks claims')
        require(a['status'] in {'supported','opposed','unresolved'},'Invalid argument status')
    return {'conforms':True,'engine':'python-record-validator','report':'Required metadata, evidence links, epistemic status and policy grounding passed.'}


PREFIX='https://example.org/socratic/'

def turtle(session):
    """Inspectable RDF representation; evaluator state is never serialized here."""
    lit=lambda x:json.dumps(str(x),ensure_ascii=False)
    ref=lambda x:'<'+PREFIX+x+'>'
    lines=['@prefix s: <'+PREFIX+'> .','@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .']
    sid=session['id']; participant=session['participant_id']
    lines.append(f'{ref("participant-"+participant)} a s:Participant .')
    lines.append(f'{ref(sid)} a s:Session ; s:participant {ref("participant-"+participant)} ; s:task {lit(session["task"])} .')
    for e in session['events']:
        inp=e['input']
        if inp.get('kind')=='evaluation':
            lines.append(f'{ref(inp["trial_id"])} a s:Trial ; s:session {ref(sid)} ; s:participant {ref("participant-"+participant)} ; s:trialIndex {inp["index"]} .')
        snap=e.get('snapshot')
        if not snap:continue
        for c in snap['claims']:
            triples=[f'a s:{c["type"]}',f's:content {lit(c["content"])}']
            for k in ['scope','timestamp','provenance','model_version']:
                triples.append(f's:{k} {lit(c[k])}')
            for status in c['statuses']:triples.append(f's:status {lit(status)}')
            for t in c['evidence']:triples.append(f's:supportedBy {ref(t)}')
            for relation,prop in [('depends_on','dependsOn'),('revises','revises'),('contradicts','contradicts')]:
                for t in c.get(relation,[]):triples.append(f's:{prop} {ref(t)}')
            if 'confidence' in c:
                triples += [f's:confidence "{c["confidence"]}"^^xsd:double', f's:confidenceInterpretation {lit(c["confidence_interpretation"])}']
            for a in c.get('alternatives',[]):triples.append(f's:alternative {lit(a)}')
            for a in c.get('revision_conditions',[]):triples.append(f's:revisionCondition {lit(a)}')
            lines.append(ref(c['id'])+' '+' ; '.join(triples)+' .')
        for a in snap['arguments']:
            triples=['a s:Argument',f's:conclusion {lit(a["conclusion"])}',f's:scope {lit(session["task"])}',f's:status {lit(a["status"])}',f's:reason {lit(a["reason"])}']
            triples += [f's:supportedBy {ref(t)}' for t in a['evidence']]
            if a.get('opposes'):triples.append(f's:opposes {ref(a["opposes"])}')
            lines.append(ref(a['id'])+' '+' ; '.join(triples)+' .')
        d=snap.get('decision')
        if d:
            triples=['a s:Intervention',f's:action {lit(d["action"])}',f's:rationale {lit(d["rationale"])}',f's:message {lit(d["message"] or "")}',f's:observedIn {ref(inp["trial_id"])}']
            triples += [f's:supportedBy {ref(c)}' for c in d['claim_ids']]
            lines.append(ref(d['id'])+' '+' ; '.join(triples)+' .')
    return '\n'.join(lines)+'\n'


def shacl_report(session):
    try:
        from rdflib import Graph
        from pyshacl import validate
    except ImportError:
        return {'conforms':None,'engine':'pyshacl-unavailable','report':'SHACL not executed; Python record validation is active. Install requirements-research.txt to enable SHACL.'}
    g=Graph().parse(data=turtle(session),format='turtle')
    shapes=Graph().parse(str(Path(__file__).parent/'ontology'/'shapes.ttl'),format='turtle')
    ok,_,report=validate(g,shacl_graph=shapes,inference='none')
    return {'conforms':bool(ok),'engine':'pyshacl','report':report}
