"""Causal-order assistant estimates from public events, never private actor state."""
from .tasks import get_task
from .learning import condition,summary

VERSION='participant-model-0.2'
RHO=[i/20 for i in range(21)]


def exposure(deliveries):
    return any(d['delivered'] and d['reading_exposure_ms']>0 for d in deliveries)


def _learn(session):
    """Replay public prefixes: predict, observe delivery, then observe choice.

    Task parameters use demonstrably unaided choices. All completed outcomes
    update task learning. Uptake uses the forecast made BEFORE the choice,
    conditional on acknowledged exposure, with independent style posteriors.
    """
    module=get_task(session['task']);factory=getattr(module,'participant_observer',None)
    observer=factory(session.get('calibration_profile') or {}) if factory else None
    target_hook=getattr(module,'assistance_target',None)
    states={style:{'weights':[1/len(RHO)]*len(RHO),'observations':0,'informative':0,
                   'evidence':[],'uninformative':0} for style in ['direct','socratic']}
    trials={};choice_evidence=[];outcome_evidence=[];latest=None
    for record in session['events']:
        inp=record['input'];kind=inp.get('kind')
        if kind=='evaluation':
            latest=inp
            forecasts=observer.distributions(inp) if observer else None
            weights=list(observer.weights) if observer else None
            forecast=observer.predict(inp) if observer else None
            trials[inp['trial_id']]={'evaluation':inp,'forecast':forecast,'hypotheses':forecasts,'weights':weights,
                'decision':record.get('snapshot',{}).get('decision'), 'deliveries':[]}
        elif kind=='delivery':
            for trial in reversed(list(trials.values())):
                if trial['decision'] and trial['decision']['id']==inp['decision_id']:
                    trial['deliveries'].append(inp);break
        elif kind=='feedback' and observer:
            trial=trials[inp['trial_id']];decision=trial['decision']
            intervention=decision.get('intervention') if decision else None
            exposed=exposure(trial['deliveries'])
            # Missing/zero-exposure acknowledgements of an active prompt are
            # ambiguous, not automatically unaided preference observations.
            unaided=bool(not intervention or (trial['deliveries'] and not any(d['delivered'] for d in trial['deliveries'])))
            if not inp['timed_out']:
                outcome_evidence.append(record['id'])
                if unaided:choice_evidence.append(record['id'])
                if intervention and exposed and target_hook:
                    base={a:p['mean'] for a,p in trial['forecast'].items()}
                    targets=[target_hook(trial['evaluation'],p,intervention) for p in trial['hypotheses']]
                    if all(q is not None for q in targets):
                        target={a:sum(w*q[a] for w,q in zip(trial['weights'],targets)) for a in base}
                        state=states[intervention['style']];state['observations']+=1
                        change=.5*sum(abs(base[a]-target[a]) for a in base)
                        if change>=.05:
                            a=inp['choice']
                            state['weights']=condition(state['weights'],[(1-r)*base[a]+r*target[a] for r in RHO])
                            state['informative']+=1;state['evidence'].append(record['id'])
                        else:state['uninformative']+=1
            observer.observe(trial['evaluation'],inp,unaided)
    if observer is None:
        task={'status':'unknown','reason':'This environment has no public participant-observer hook.'}
    else:
        task={'status':'estimated',**observer.describe(),'choice_evidence':choice_evidence,'outcome_evidence':outcome_evidence,
              'prediction':{},'prediction_for_trial':None,'choice_hypotheses':[]}
        if latest and session['events'][-1]['input']['kind']=='evaluation':
            forecast=trials[latest['trial_id']]
            task.update(prediction=forecast['forecast'],prediction_for_trial=latest['trial_id'],
                choice_hypotheses=[{'probabilities':d,'weight':w} for d,w in zip(forecast['hypotheses'],forecast['weights'])])
    uptake={}
    for style,state in states.items():
        uptake[style]={'status':'estimated' if state['informative'] else 'unknown',
            **summary(RHO,state['weights']),'prior':'Uniform discrete grid 0, .05, ..., 1; independent by style.',
            'observations':state['observations'],'informative':state['informative'],
            'uninformative':state['uninformative'],'evidence':state['evidence'],
            'posterior':[{'rho':r,'weight':w} for r,w in zip(RHO,state['weights'])],
            'meaning':'Approximate behavioural uptake conditional on the observer\'s unaided forecast and task-owned processing hypothesis; not trust, comprehension or benefit.'}
    return task,uptake


def _reports(session):
    counts={k:0 for k in ['helpful','disagree','fewer','dismiss','reply']};evidence=[];seen=set()
    by_style={s:{k:0 for k in counts} for s in ['direct','socratic']}
    decisions={e['snapshot']['decision']['id']:e['snapshot']['decision'] for e in session['events']
               if e.get('snapshot',{}).get('decision')}
    for record in session['events']:
        inp=record['input']
        if inp.get('kind')!='response':continue
        key=(inp.get('decision_id',record['id']),inp['feedback'])
        if key in seen:continue
        seen.add(key);counts[inp['feedback']]+=1;evidence.append(record['id'])
        intervention=decisions.get(inp.get('decision_id'),{}).get('intervention')
        if intervention:by_style[intervention['style']][inp['feedback']]+=1
    return {'feedback_counts':counts,'reports_by_style':by_style,'evidence':evidence,
            'reported_burden':{'requests_for_fewer':counts['fewer'],'samples':counts['fewer'],
                'status':'reported' if counts['fewer'] else 'unknown',
                'meaning':'Explicit requests for fewer prompts only. No response or dismissal is ambiguous.'}}


def interaction_estimate(session,uptake=None):
    if session['condition'] not in {'E','F'}:
        return {'status':'withheld','reason':'This condition uses common delivery defaults.'}
    if uptake is None:
        if session.get('task'):_,uptake=_learn(session)
        else:
            uptake={s:{'status':'unknown',**summary(RHO,[1/len(RHO)]*len(RHO)),
                       'informative':0,'evidence':[]} for s in ['direct','socratic']}
    reports=_reports(session)
    return {'status':'estimated' if reports['evidence'] or any(u['informative'] for u in uptake.values()) else 'unknown',
            **uptake,**reports,'limits':[
                'Agreement is evaluated against an estimated unaided choice distribution; it is not raw compliance.',
                'The task observer and processing hypothesis can be wrong; intervals are conditional on those assumptions.',
                'Helpful reports perceived usefulness, not causal benefit; disagreement contests an interpretation.',
                'Dismissal, missing replies and reading time do not identify rejection or burden.',
                'Reward updates task learning, never a success/failure label for assistance.']}


def estimate(session,history):
    profile=session.get('calibration_profile') or {};module=get_task(session['task'])
    person=module.participant(history,profile)
    person['calibration']=profile or {'status':'unknown','reason':'No calibrated task-specific model in this condition.'}
    if session['condition'] in {'E','F'}:
        person['online_task'],uptake=_learn(session)
        person['interaction']=interaction_estimate(session,uptake)
        online=person['online_task']
        if 'learned_values' in online:
            person.update(q=online['learned_values'],last_rl_update=online['last_update'],
                          parameters={k:v['mean'] for k,v in online['parameters'].items()})
        if 'pressure_policy' in online:person['pressure_policy']=online['pressure_policy']
    else:
        person['online_task']={'status':'withheld','reason':'This condition uses common delivery defaults.'}
        person['interaction']=interaction_estimate(session)
    person['model_version']=VERSION
    from .personalisation import settings
    person['delivery_settings']=settings(session.get('policy',{}))
    person['unknown']=['Intent','Subjective confidence','Trust, comprehension and causal assistance benefit',
        'Overconfidence (confidence not elicited)','Hesitation (response time alone is insufficient)']
    return person


def selection_cost(base_cost,person):
    reports=person.get('interaction',{}).get('reported_burden',{})
    return round(base_cost*(1.5 if reports.get('requests_for_fewer',0) else 1),6)
