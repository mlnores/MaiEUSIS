"""Models → annotated claims → opposing reasons → policy → validated language."""
import copy
import json
from pathlib import Path
from collections import Counter
from .models import VERSION, ARMS, KEYS, rl, mab_environment, tbs_context, tbs_pressure_model
from .bayes import EpistemicNetwork
from .validation import require, validate_event, validate_snapshot, shacl_report
from .language import realise

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
            result.append({**e, 'points_before':ev.get('points'), 'target':ev.get('target'),
                           'remaining':ev.get('remaining'), 'block':ev.get('block')})
    return result


def hypotheses(session, evaluation, environment, h):
    task=session['task']; p=session['policy']; window=h[-p['window_trials']:]
    if task=='TBS':window=[x for x in window if x['block']==evaluation['block']]
    valid=[x for x in window if not x['timed_out']]
    evidence=[x['trial_id'] for x in valid]
    definitions=[]
    if task=='MAB':
        choices=[x['choice'] for x in valid]
        last=choices[-1] if choices else None
        sampled=set(x['choice'] for x in h if not x['timed_out'])
        stay=sum(a==b for a,b in zip(choices,choices[1:]))/max(1,len(choices)-1)
        profile=session.get('calibration_profile') or {}
        q, updates=rl(h,profile.get('alpha_plus',.3),profile.get('alpha_minus',.3),profile.get('beta',2))
        model_mismatch=bool(last and q[last]<max(q.values())-.1)
        choice_compatibility=updates[-1]['choice_probability'] if updates else None
        arm=next((a for a in environment['arms'] if a['arm']==last),None)
        rewards=[x['outcome']/200 for x in valid if x['choice']==last]
        decline=len(rewards)>=6 and sum(rewards[:3])/3-sum(rewards[-3:])/3>=p['decline_threshold']
        change=bool(arm and arm['change']['posterior']>=.3)
        switches_after_loss=sum(valid[i-1]['outcome']<0 and valid[i]['choice']!=valid[i-1]['choice'] for i in range(1,len(valid)))
        definitions=[
            ('underexploration',len(sampled)<=2, stay>=.75, len(h)>=p['min_evidence'],
             'Limited sampling may leave useful alternatives unexplored.', ['Persistence may be justified by rewards or an intentional strategy.','The cost of exploration depends on the remaining horizon.'],
             ['Sampling additional alternatives weakens this interpretation.','An attributed participant explanation can contest this account.']),
            ('premature_exploitation',decline and change, stay>=.75 and model_mismatch, bool(decline),
             'Persistence may merit reconsideration after declining feedback.', ['Noisy rewards can explain the apparent decline.','Estimated values may not match the participant’s own beliefs.'],
             ['A recovered reward pattern weakens change evidence.','Switching or an explicit rationale revises the persistence interpretation.']),
            ('feedback_overweighting',switches_after_loss>=2, stay<.5, len(valid)>=6,
             'Recent switching after losses may over-weight individual outcomes.', ['Switching may be planned exploration.','Several outcomes may contain valid evidence of change.'],
             ['Sustained sampling or an explanation of planned exploration weakens this interpretation.'])]
        stats={'sampled_arms':sorted(sampled),'stay_rate':round(stay,4),'switches_after_loss':switches_after_loss,
               'evidence_window':evidence,'rl_choice_compatibility':choice_compatibility,'rl_value_mismatch':model_mismatch}
    else:
        choices=[x['choice'] for x in valid]; repeated=len(choices)>=3 and len(set(choices[-3:]))==1
        sensitivity=tbs_pressure_model(h)
        calibrated=(session.get('calibration_profile') or {}).get('policy',{})
        weak_sensitivity=calibrated.get('samples',0)>=6 and calibrated.get('p_positive_sensitivity',.5)<.4
        definitions=[('constraint_neglect',environment['remaining']<=2, repeated and weak_sensitivity, environment['remaining']<=2,
            'A repeated choice pattern may warrant checking the shrinking horizon.',
            ['The same option can still be appropriate after the context changes.','The final-win multiplier can preserve feasibility.','A policy estimate cannot establish that the participant ignored a constraint.'],
            ['A context-sensitive adjustment or an explicit constraint-aware explanation revises this account.'])]
        stats={'recent_choices':choices,'pressure_policy':sensitivity,'calibrated_weak_pressure_sensitivity':weak_sensitivity,'evidence_window':evidence}
    results=[]
    for name,adverse,pattern,relevant,text,alternatives,revisions in definitions:
        inference=NETWORK.query(adverse,pattern,relevant)
        contest=[e for e in session['events'] if e['input'].get('kind')=='response' and e['input'].get('hypothesis')==name and
                 e['input'].get('feedback')=='disagree' and evaluation['index']-e['input']['index']<=p['correction_expiry_trials'] and
                 (task=='MAB' or e['input'].get('block')==evaluation['block'])]
        results.append({'name':name,'content':text,'alternatives':alternatives,'revision_conditions':revisions,
                        'evidence':evidence,'inference':inference,'contested_by':[e['id'] for e in contest],
                        'eligible':len(valid)>=p['min_evidence'] and bool(adverse or pattern) and bool(relevant),
                        'pattern':bool(pattern),'adverse':bool(adverse)})
    return results,stats


def make_snapshot(session, event, event_id, timestamp, recorded_language=None):
    p=session['policy']; task=session['task']; h=history(session)
    ev=event if event['kind']=='evaluation' else next(e['input'] for e in reversed(session['events']) if e['input'].get('kind')=='evaluation')
    env=mab_environment(h,p['change_prior']) if task=='MAB' else tbs_context(ev)
    if event['kind']=='feedback' and task=='TBS':
        after=event['points_after']*(ev['multiplier'] if ev['remaining']==1 and event['outcome']>0 else 1)
        env['after_feedback']={'points':after,'target_gap':ev['target']-after,'remaining':ev['remaining']-1,
                               'multiplier_applied':ev['remaining']==1 and event['outcome']>0}
    profile=session.get('calibration_profile') or {}
    if task=='MAB':
        q,obs=rl(h,profile.get('alpha_plus',.3),profile.get('alpha_minus',.3),profile.get('beta',2))
        participant={'q':q,'q_units':'reward / 200; model estimates, not participant beliefs',
                     'last_rl_update':obs[-1] if obs else None,'parameters':{k:profile.get(k,v) for k,v in [('alpha_plus',.3),('alpha_minus',.3),('beta',2)]}}
    else:participant={'pressure_policy':tbs_pressure_model(h)}
    participant['calibration']=profile or {'status':'unknown','reason':'No calibrated task-specific model in this condition.'}
    participant['unknown']=['Intent','Subjective confidence','Overconfidence (confidence not elicited)','Hesitation (response time alone is insufficient)']
    hypothesis_records,stats=hypotheses(session,ev,env,h)
    participant['behaviour']=stats
    participant['hypotheses']=hypothesis_records
    prior_claims=[c['id'] for e in session['events'] for c in e.get('snapshot',{}).get('claims',[])]
    claims=[]
    def claim(name,content,statuses,evidence,kind='Claim',**extra):
        c={'id':event_id+'_'+name,'type':kind,'content':content,'statuses':statuses,'evidence':evidence,
           'scope':task+':'+session['id']+((':block-'+str(ev['block'])) if task=='TBS' else ''),
           'timestamp':timestamp,'provenance':'participant-visible task events' if 'known' in statuses else 'bounded-models-and-provisional-assumptions',
           'model_version':VERSION,**extra}
        claims.append(c);return c
    context=claim('context','The participant-visible task state and current options are recorded.', ['known'],[ev['trial_id']])
    unknown=claim('unknown','; '.join(env['unknown']+participant['unknown']), ['unknown'],[ev['trial_id']])
    estimated=claim('environment','Reward-value and change estimates from sampled outcomes.' if task=='MAB' else
                    f'Target gap {env["target_gap"]}; {env["remaining"]} choices remain. Immediate EV does not determine final attainment.',
                    ['inferred','source-dependent'] if task=='MAB' else ['known'],[x['trial_id'] for x in h[-p['window_trials']:]] or [ev['trial_id']], depends_on=[context['id']])
    for response_event in session['events']:
        response=response_event['input']
        if response.get('kind')!='response' or ev['index']-response['index']>p['correction_expiry_trials']:continue
        if task=='TBS' and response.get('block')!=ev['block']:continue
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
        if task=='MAB':
            sampled=stats['sampled_arms']; shift=max((a['change']['posterior'] for a in env['arms'] if a['samples']>=6),default=0)
            if shift>=.3:
                candidate('possible_change','ask' if socratic else 'explain',
                          ['Recent feedback may differ from earlier feedback. What evidence would justify checking another option?',
                           'Noise and a change are both plausible. What further feedback would help you distinguish them?'] if socratic else
                          ['Recent feedback may differ from earlier feedback. Compare alternatives while accounting for reward noise.'],
                          [estimated['id']], 'Observed outcome history raises uncertain evidence of change.', 'Ordinary reward noise remains a competing explanation.',.72)
            if len(h)>=p['min_evidence'] and len(sampled)<6:
                candidate('unsampled_alternatives','request-evidence' if socratic else 'explain',
                          ['Some alternatives remain lightly sampled. What remains unknown, and how much exploration is worthwhile?'] if socratic else
                          ['Some alternatives remain lightly sampled. Consider gathering more evidence about them.'],
                          [estimated['id']], 'Observed choices leave some reward estimates uncertain.', 'Further exploration has a cost and persistence may be justified.',.61)
            if socratic and len(h)>=p['min_evidence'] and not candidates:
                candidate('support_revision','support',
                          ['Your approach may be reasonable given uncertain feedback. What evidence would make you revise it?'],
                          [estimated['id']], 'No strong case for challenging the current pattern.', 'Support can still interrupt useful deliberation.',.56)
        else:
            if env['remaining']==1:
                candidate('final_multiplier','highlight-dependency' if socratic else 'explain',
                          ['The multiplier applies only if this final choice wins. How does that affect your chance of meeting the target?'] if socratic else
                          ['On the final trial, compare target attainment after a win and after no gain. The multiplier applies only after a win.'],
                          [estimated['id']], 'The published final-win rule changes target attainment.', 'Neither immediate EV nor the nominal gap alone determines attainment.',.88)
            elif env['remaining']<=2:
                candidate('shrinking_horizon','ask' if socratic else 'explain',
                          ['Can your current approach still close the target gap with the choices remaining?'] if socratic else
                          ['Review the target gap against the remaining choices and the conditional final multiplier.'],
                          [estimated['id']], 'The target gap must be assessed against a short horizon.', 'Future option pairs and outcomes are unknown; do not declare the target unreachable.',.78)
            if h and h[-1].get('block')==ev['block'] and h[-1]['outcome']>0:
                candidate('gap_after_gain','ask' if socratic else 'explain',
                          ['The last gain reduced the target gap. Does the same level of risk still serve your goal?'] if socratic else
                          ['Reconsider the level of risk after the last gain reduced the target gap.'],
                          [estimated['id']], 'A recorded gain changed target progress.', 'A smaller gap alone does not imply that less risk is better.',.63)
            if not candidates and ev['index']%p['fixed_prompt_interval']==0:
                candidate('expected_value_limit','compare' if socratic else 'explain',
                          ['How do the expected gains compare with the chance of reaching your target?'] if socratic else
                          ['Immediate expected gain and final target attainment are different objectives. Consider both.'],
                          [estimated['id']], 'Displayed probabilities and gains support an EV comparison.', 'No future outcome or optimal multi-trial policy is known.',.60)
        if personalised:
            for hyp in hypothesis_records:
                if not hyp['eligible'] or not hyp.get('claim_id'):continue
                c=hypothesis_claims[hyp['name']]
                wording={
                    'underexploration':'You have sampled few alternatives recently. What evidence supports continuing with the same option?',
                    'premature_exploitation':'Your recent feedback has declined while your choice has persisted. What would justify revisiting another option?',
                    'feedback_overweighting':'You have switched after recent losses. What would distinguish a useful switch from reacting to reward noise?',
                    'constraint_neglect':'Your recent choice pattern has stayed similar as the horizon shrinks. How are you accounting for the remaining chances?'}[hyp['name']]
                if not socratic:wording=wording.split('. What')[0].split('. How')[0]+'. Consider reviewing this pattern against the available task evidence.'
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
       'cooldown':cooldown,'frequency_preference':pref,'eligible_point':'post-feedback preparation' if task=='MAB' else 'options-visible preparation',
       'hypothesis':None if silence else selected['hypothesis'],'language':None}
    if not silence:
        lang=realise(d['action'],d['claim_ids'],selected['messages'],p['generation_timeout_seconds'],recorded_language)
        d['language']=lang;d['message']=lang['proposal']['message']
    snapshot['decision']=d
    snapshot['validation']=validate_snapshot(snapshot,{e['input']['trial_id'] for e in session['events'] if 'trial_id' in e['input']})
    return snapshot


def ingest(session, event, timestamp, recorded_language=None):
    """Validate and compute on a copy. No invalid partial updates are committed."""
    candidate=copy.deepcopy(session)
    require(not candidate['finished'],'Session has finished')
    kind=event.get('kind')
    if kind in {'evaluation','feedback'}:
        validate_event(candidate['task'],event)
        h=history(candidate); evaluations=[e['input'] for e in candidate['events'] if e['input'].get('kind')=='evaluation']
        require(event['index']<=candidate['total_trials'],'Trial exceeds the configured protocol')
        if kind=='evaluation':
            require(len(evaluations)==len(h),'Prior trial has no feedback')
            require(event['index']==len(h)+1,'Out-of-order trial')
            require(not any(e['trial_id']==event['trial_id'] for e in evaluations),'Repeated trial ID')
            if candidate['task']=='MAB':
                require(all(o['key']==KEYS[o['id']] for o in event['options']),'Incorrect arm/key mapping')
                require(event['score']==(h[-1]['score_after'] if h else 0),'Score inconsistent with prior feedback')
            else:
                expected_points=h[-1]['points_after'] if h and h[-1]['block']==event['block'] else 0
                require(event['points']==expected_points,'Points inconsistent with prior feedback')
                pairs=candidate['task_rules']['options']; pair=[[o['amount'],o['probability']] for o in event['options']]
                require(pair in pairs,'Options outside the published TBS table')
                ti=candidate['task_rules']['targets'].index(event['target']) if event['target'] in candidate['task_rules']['targets'] else -1
                require(ti>=0 and event['multiplier']==candidate['task_rules']['multipliers'][ti],'Target/multiplier mismatch')
                if evaluations and evaluations[-1].get('block')==event['block']:
                    require(event['target']==evaluations[-1]['target'],'Target changed within block')
        else:
            require(len(evaluations)==len(h)+1,'Feedback has no pending evaluation')
            ev=evaluations[-1];require(event['trial_id']==ev['trial_id'] and event['index']==ev['index'],'Feedback does not match pending trial')
            if candidate['task']=='MAB':
                outcome=-200 if event['timed_out'] else event['outcome']
                option=next((o for o in ev['options'] if o['id']==event['choice']),None)
                require((event['timed_out'] and event['outcome']==-200) or (option and event['outcome'] in option['outcomes']),'Impossible reward')
                require(event['score_after']==ev['score']+outcome,'Score arithmetic mismatch')
            else:
                option=next((o for o in ev['options'] if o['id']==event['choice']),None)
                require((event['timed_out'] and event['outcome']==0) or (option and event['outcome'] in [0,option['amount']]),'Impossible gain')
                require(event['points_after']==ev['points']+event['outcome'],'Points arithmetic mismatch')
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
        require(candidate['task']!='TBS' or event.get('block')==decision_event['input']['block'],'Response scope mismatch')
        if event['feedback']=='fewer':candidate['preference']='infrequent'
    else:raise ValueError('Unsupported input event')
    event_id=candidate['id']+'_event_'+str(len(candidate['events'])+1)
    record={'id':event_id,'timestamp':timestamp,'input':copy.deepcopy(event)}
    if kind=='response':record['attribution']='participant self-report; not established fact'
    candidate['events'].append(record)
    if kind in {'evaluation','feedback'}:
        record['snapshot']=make_snapshot(candidate,event,event_id,timestamp,recorded_language)
        report=shacl_report(candidate)
        record['snapshot']['shacl']=report
        require(report['conforms'] is not False,'SHACL rejected the candidate graph: '+report['report'])
    return candidate,record
