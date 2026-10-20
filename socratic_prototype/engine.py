"""Models → annotated claims → opposing reasons → policy → validated language."""
import copy
import json
from pathlib import Path
from collections import Counter
from .tasks import get_task
from .tasks.base import MODEL_VERSION as VERSION
from .bayes import EpistemicNetwork
from .validation import require, validate_event, validate_snapshot, shacl_report
from .language import realise
from .grounding import build_evidence_package, realise_question, interpret_response, reviewed_responses

POLICY=json.loads((Path(__file__).parent/'policy.json').read_text())
NETWORK=EpistemicNetwork()


def history(session):
    evaluations={}
    result=[]
    for event in session['events']:
        e=event['input']
        if e.get('kind')=='evaluation':evaluations[e['trial_id']]=e
        if e.get('kind')=='feedback':
            ev=evaluations[e['trial_id']]
            result.append({**e, **get_task(session['task']).history_context(ev)})
    return result


def hypotheses(session, evaluation, environment, h):
    task=get_task(session['task']); p=session['policy']
    window=[x for x in h[-p['window_trials']:] if task.same_scope(x,evaluation)]
    valid=[x for x in window if not x['timed_out']]
    evidence=[x['trial_id'] for x in valid]
    definitions,stats=task.hypothesis_inputs(session,evaluation,environment,h)
    results=[]
    for name,adverse,pattern,relevant,text,alternatives,revisions in definitions:
        inference=NETWORK.query(adverse,pattern,relevant)
        contest=[e for e in session['events'] if e['input'].get('kind')=='response' and e['input'].get('hypothesis')==name and
                 e['input'].get('feedback')=='disagree' and evaluation['index']-e['input']['index']<=p['correction_expiry_trials'] and
                 task.same_scope(e['input'],evaluation)]
        if session.get('language_configuration'):
            contest += [r['review'] for r in reviewed_responses(session,evaluation)
                        if any(u['kind']=='contest_hypothesis' and u['hypothesis']==name for u in r['updates'])]
        results.append({'name':name,'content':text,'alternatives':alternatives,'revision_conditions':revisions,
                        'evidence':evidence,'inference':inference,'contested_by':[e['id'] for e in contest],
                        'eligible':len(valid)>=p['min_evidence'] and bool(adverse or pattern) and bool(relevant),
                        'pattern':bool(pattern),'adverse':bool(adverse)})
    return results,stats


def make_snapshot(session, event, event_id, timestamp, recorded_language=None):
    p=session['policy']; task=session['task']; h=history(session)
    ev=event if event['kind']=='evaluation' else next(e['input'] for e in reversed(session['events']) if e['input'].get('kind')=='evaluation')
    module=get_task(task)
    env=module.environment(h,ev,p,event)
    profile=session.get('calibration_profile') or {}
    participant=module.participant(h,profile)
    participant['calibration']=profile or {'status':'unknown','reason':'No calibrated task-specific model in this condition.'}
    participant['unknown']=['Intent','Subjective confidence','Overconfidence (confidence not elicited)','Hesitation (response time alone is insufficient)']
    hypothesis_records,stats=hypotheses(session,ev,env,h)
    participant['behaviour']=stats
    participant['hypotheses']=hypothesis_records
    prior_claims=[c['id'] for e in session['events'] for c in e.get('snapshot',{}).get('claims',[])]
    claims=[]
    def claim(name,content,statuses,evidence,kind='Claim',**extra):
        c={'id':event_id+'_'+name,'type':kind,'content':content,'statuses':statuses,'evidence':evidence,
           'scope':task+':'+session['id']+module.scope_suffix(ev),
           'timestamp':timestamp,'provenance':'participant-visible task events' if 'known' in statuses else 'bounded-models-and-provisional-assumptions',
           'model_version':VERSION,**extra}
        claims.append(c);return c
    context=claim('context','The participant-visible task state and current options are recorded.', ['known'],[ev['trial_id']])
    unknown=claim('unknown','; '.join(env['unknown']+participant['unknown']), ['unknown'],[ev['trial_id']])
    description,statuses=module.environment_claim(env)
    estimated=claim('environment',description,statuses,[x['trial_id'] for x in h[-p['window_trials']:]] or [ev['trial_id']], depends_on=[context['id']])
    for response_event in session['events']:
        response=response_event['input']
        if response.get('kind')!='response' or ev['index']-response['index']>p['correction_expiry_trials']:continue
        if not module.same_scope(response,ev):continue
        response_trial=next(e['input']['trial_id'] for e in session['events'] if e.get('snapshot',{}).get('decision',{}).get('id')==response['decision_id'])
        response_claim=claim('response_'+str(response['index'])+'_'+str(session['events'].index(response_event)),
              'Participant feedback ('+response['feedback']+'): '+(response['text'] or '(no text supplied)'),
              ['source-dependent','contested'] if response['feedback']=='disagree' else ['source-dependent'],[response_trial])
        response_claim['provenance']='participant-self-report:'+response_event['id']
    hypothesis_claims={}
    for hyp in hypothesis_records:
        if not hyp['evidence']:continue
        statuses=['inferred','source-dependent','requires-verification']
        statuses+=['probable'] if hyp['inference']['posterior']>=.6 else ['low-confidence']
        if hyp['contested_by']:statuses+=['contested']
        prev=next((c for e in reversed(session['events']) for c in e.get('snapshot',{}).get('claims',[]) if c['id'].endswith('_'+hyp['name']) and c['scope']==context['scope']),None)
        c=claim(hyp['name'],hyp['content'],statuses,hyp['evidence'],'Hypothesis',
                confidence=hyp['inference']['posterior'],confidence_interpretation=hyp['inference']['interpretation'],
                alternatives=hyp['alternatives'],revision_conditions=hyp['revision_conditions'],depends_on=[estimated['id']],
                revises=[prev['id']] if prev else [])
        hyp['claim_id']=c['id'];hypothesis_claims[hyp['name']]=c
    if session.get('language_configuration'):
        for reviewed in reviewed_responses(session,ev):
            response=reviewed['response'];review=reviewed['review']
            response_trial=next(e['input']['trial_id'] for e in session['events']
                                if e.get('snapshot',{}).get('decision',{}).get('id')==response['input']['decision_id'])
            for i,update in enumerate(reviewed['updates']):
                target=hypothesis_claims.get(update['hypothesis'])
                c=claim('review_'+str(session['events'].index(review))+'_'+str(i),
                    'Researcher-reviewed participant '+update['kind']+' (verbatim): '+update['quote'],
                    ['source-dependent','requires-verification'],[response_trial],
                    contradicts=[target['id']] if update['kind']=='contest_hypothesis' and target else [])
                c['provenance']='participant-self-report:'+response['id']+'; researcher-review:'+review['id']
    snapshot={'environment':env,'participant':participant,'claims':claims,'previous_claim_ids':sorted({r for c in claims for r in c.get('revises',[]) if r in prior_claims}),
              'arguments':[],'model_version':VERSION,'policy_version':p['version'],'event_kind':event['kind']}
    if event['kind']=='feedback':
        snapshot['policy_status']='Not an eligible intervention point; model update only.'
        snapshot['validation']=validate_snapshot(snapshot,{e['input']['trial_id'] for e in session['events'] if 'trial_id' in e['input']})
        return snapshot
    condition=session['condition']; personalised=condition in {'E','F'}; socratic=condition in {'D','F'}
    candidates=[]
    def candidate(name,action,messages,evidence,reasons,opposition,usefulness=.65,hypothesis=None):
        score=usefulness-p['interruption_cost']
        if hypothesis and hypothesis['contested_by']:score-=.5
        n=len(candidates);support=event_id+'_argument_'+str(n)
        snapshot['arguments'] += [
            {'id':support,'conclusion':name,'evidence':evidence,'status':'supported','reason':reasons,'premises':evidence},
            {'id':support+'_opposition','conclusion':name,'evidence':evidence,'status':'opposed','reason':opposition,'opposes':support,'premises':evidence}]
        candidates.append({'name':name,'action':action,'messages':messages,'claim_ids':evidence,'usefulness':usefulness,
                           'score':round(score,6),'supporting_argument':support,'opposing_argument':support+'_opposition',
                           'hypothesis':hypothesis['name'] if hypothesis else None,
                           'argument_evaluation':'unresolved' if hypothesis and hypothesis['contested_by'] else 'supported-with-unresolved-objections'})
    if condition=='B':
        candidate('general_guidance','ask' if socratic else 'explain',
                  ['Consider your goal, the available evidence, and the costs of each alternative.'],[context['id']],
                  'A scheduled generic reminder is available.','Generic support may add cognitive burden without relevance.')
    if condition in {'C','D','E','F'}:
        module.contribute_candidates(session,ev,env,h,stats,estimated,socratic,candidates,candidate)
        if personalised:
            for hyp in hypothesis_records:
                if not hyp['eligible'] or not hyp.get('claim_id'):continue
                c=hypothesis_claims[hyp['name']]
                wording=module.hypothesis_message(hyp['name'],socratic)
                candidate(hyp['name'],'challenge' if socratic else 'advise',[wording],
                          [c['id'],estimated['id']],hyp['content'],' '.join(hyp['alternatives'])+(' Participant disputed this interpretation.' if hyp['contested_by'] else ''),
                          hyp['inference']['usefulness']+p['personalisation_bonus'],hyp)
    delivered=[e['input'] for e in session['events'] if e['input'].get('kind')=='delivery' and e['input']['delivered']]
    last=delivered[-1]['index'] if delivered else None
    pref=session['preference']
    since=ev['index']-last if last is not None else None
    cooldown=p['cooldown'][pref]
    selected=max(candidates,key=lambda x:x['score'],default=None)
    rationale='No candidate exceeds the evidence, relevance and interruption threshold.'
    silence=True
    if session['phase']=='calibration' or condition=='A':rationale='Unassisted condition: neutral preparation window; no assistance delivered.'
    elif since is not None and since<cooldown:rationale=f'Cooldown: {since} trials since the last delivered prompt; {cooldown} required for {pref} frequency.'
    elif condition=='B' and ev['index']%p['fixed_prompt_interval']!=0:rationale='Generic guidance is scheduled every '+str(p['fixed_prompt_interval'])+' trials.'
    elif selected and selected['score']>=p['threshold']:
        silence=False;rationale=f'{selected["name"]}: provisional usefulness {selected["usefulness"]:.3f} minus interruption cost {p["interruption_cost"]:.3f}; score {selected["score"]:.3f} exceeds threshold {p["threshold"]:.3f}. Opposing reasons retained.'
    d={'id':event_id+'_decision','action':'silence' if silence else selected['action'],'rationale':rationale,
       'claim_ids':[context['id'],unknown['id']] if silence else selected['claim_ids'],'message':None,
       'candidates':candidates,'threshold':p['threshold'],'interruption_cost':p['interruption_cost'],
       'cooldown':cooldown,'frequency_preference':pref,'eligible_point':module.ELIGIBLE_POINT,
       'hypothesis':None if silence else selected['hypothesis'],'language':None}
    if not silence:
        config=session.get('language_configuration')
        if config:
            package=build_evidence_package(session,ev,snapshot,selected,h)
            d['evidence_package']=package
        if config and config['mode']=='generated':
            lang=realise_question(package,selected['messages'],p['generation_timeout_seconds'],recorded_language,config)
        else:
            lang=realise(d['action'],d['claim_ids'],selected['messages'],p['generation_timeout_seconds'],recorded_language,config)
        d['language']=lang;d['message']=lang['proposal']['message']
    snapshot['decision']=d
    snapshot['validation']=validate_snapshot(snapshot,{e['input']['trial_id'] for e in session['events'] if 'trial_id' in e['input']})
    return snapshot


def ingest(session, event, timestamp, recorded_language=None, recorded_interpretation=None, replaying=False):
    """Validate and compute on a copy. No invalid partial updates are committed."""
    candidate=copy.deepcopy(session)
    kind=event.get('kind')
    require(not candidate['finished'] or kind=='interpretation-review','Session has finished')
    if kind in {'evaluation','feedback'}:
        validate_event(candidate['task'],event)
        h=history(candidate); evaluations=[e['input'] for e in candidate['events'] if e['input'].get('kind')=='evaluation']
        require(event['index']<=candidate['total_trials'],'Trial exceeds the configured protocol')
        if kind=='evaluation':
            require(len(evaluations)==len(h),'Prior trial has no feedback')
            require(event['index']==len(h)+1,'Out-of-order trial')
            require(not any(e['trial_id']==event['trial_id'] for e in evaluations),'Repeated trial ID')
            get_task(candidate['task']).validate_transition(candidate,event,h,evaluations)
        else:
            require(len(evaluations)==len(h)+1,'Feedback has no pending evaluation')
            ev=evaluations[-1];require(event['trial_id']==ev['trial_id'] and event['index']==ev['index'],'Feedback does not match pending trial')
            get_task(candidate['task']).validate_transition(candidate,event,h,evaluations)
    elif kind=='delivery':
        from .validation import fields
        fields(event,['kind','decision_id','index','delivered','generation_latency_ms','reading_exposure_ms','early_attempts'])
        require(type(event['delivered']) is bool,'Invalid delivery acknowledgement')
        from .validation import number
        for k in ['generation_latency_ms','reading_exposure_ms']:require(number(event[k],0,60000),'Invalid exposure timing')
        require(type(event['early_attempts']) is int and event['early_attempts']>=0,'Invalid attempts')
        decisions=[e['snapshot']['decision'] for e in candidate['events'] if e.get('snapshot',{}).get('decision')]
        require(bool(decisions) and decisions[-1]['id']==event['decision_id'],'Unknown or stale decision')
        require(not any(e['input'].get('decision_id')==event['decision_id'] for e in candidate['events'] if e['input'].get('kind')=='delivery'),'Repeated delivery')
        require(event['index']==len(decisions),'Delivery trial mismatch')
        require(not event['delivered'] or decisions[-1]['action']!='silence','Cannot deliver silence as assistance')
        require(event['delivered'] or event['reading_exposure_ms']==0,'Undelivered message has exposure')
    elif kind=='response':
        from .validation import fields
        fields(event,['kind','decision_id','index','feedback','text'],['hypothesis','block'])
        require(event['feedback'] in {'helpful','disagree','fewer','dismiss'},'Invalid feedback')
        require(isinstance(event['text'],str) and len(event['text'])<=2000,'Response too long')
        decision_event=next((e for e in candidate['events'] if e.get('snapshot',{}).get('decision',{}).get('id')==event['decision_id']),None)
        require(decision_event is not None,'Unknown decision')
        d=decision_event['snapshot']['decision']
        require(any(e['input'].get('kind')=='delivery' and e['input']['decision_id']==d['id'] and e['input']['delivered'] for e in candidate['events']),'Cannot respond to unexposed assistance')
        require(event.get('hypothesis')==d['hypothesis'],'Response hypothesis mismatch')
        require(event['index']==decision_event['input']['index'],'Response trial mismatch')
        require(get_task(candidate['task']).same_scope(event,decision_event['input']),'Response scope mismatch')
        if event['feedback']=='fewer':candidate['preference']='infrequent'
    elif kind=='interpretation-review':
        from .validation import fields, identity
        fields(event,['kind','response_event_id','accept','reviewer'])
        require(type(event['accept']) is bool and identity(event['reviewer']),'Invalid researcher review')
        response=next((e for e in candidate['events'] if e['id']==event['response_event_id'] and e['input'].get('kind')=='response'),None)
        require(response is not None and response.get('interpretation',{}).get('status')=='pending-review','No pending response proposal')
        require(not any(e['input'].get('kind')=='interpretation-review' and e['input']['response_event_id']==response['id']
                        for e in candidate['events']),'Response proposal already reviewed')
    else:raise ValueError('Unsupported input event')
    event_id=candidate['id']+'_event_'+str(len(candidate['events'])+1)
    record={'id':event_id,'timestamp':timestamp,'input':copy.deepcopy(event)}
    if kind=='response':record['attribution']='participant self-report; not established fact'
    config=candidate.get('language_configuration')
    if kind=='response' and config and config['interpret_responses'] and candidate['condition'] in {'E','F'}:
        if replaying:require(recorded_interpretation is not None,'Replay is missing a recorded response interpretation')
        record['interpretation']=interpret_response(event,d,config,candidate['policy']['generation_timeout_seconds'],recorded_interpretation)
    candidate['events'].append(record)
    if kind in {'evaluation','feedback'}:
        record['snapshot']=make_snapshot(candidate,event,event_id,timestamp,recorded_language)
        report=shacl_report(candidate,incremental='task_module' in candidate)
        record['snapshot']['shacl']=report
        require(report['conforms'] is not False,'SHACL rejected the candidate graph: '+report['report'])
    return candidate,record
