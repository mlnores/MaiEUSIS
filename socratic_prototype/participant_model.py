"""Assistant estimates from public observations, separate from synthetic actor state."""
import math
from .tasks import get_task

VERSION='participant-model-0.1'


def interaction_estimate(session):
    """Explicit feedback describes reported burden, not trust or causal benefit."""
    if session['condition'] not in {'E','F'}:
        return {'status':'withheld','reason':'This condition has no personalised participant model.'}
    counts={key:0 for key in ['helpful','disagree','fewer','dismiss','reply']}
    evidence=[]
    for record in session['events']:
        inp=record['input']
        if inp.get('kind')=='response':
            counts[inp['feedback']]+=1;evidence.append(record['id'])
    a=1+counts['fewer']+counts['dismiss'];b=1+counts['helpful'];mean=a/(a+b)
    sd=math.sqrt(a*b/((a+b)**2*(a+b+1)))
    concordant=discordant=0
    for record in session['events']:
        inp=record['input']
        if inp.get('kind')!='feedback' or inp['timed_out']:continue
        decision=next((e['snapshot']['decision'] for e in session['events'] if e['input'].get('kind')=='evaluation' and e['input']['index']==inp['index']),None)
        structured=decision.get('intervention') if decision else None
        if not structured or structured['style']!='direct':continue
        if not any(e['input'].get('kind')=='delivery' and e['input']['decision_id']==decision['id'] and e['input']['delivered'] for e in session['events']):continue
        if inp['choice']==structured['recommendation']['option_id']:concordant+=1
        else:discordant+=1
    return {'direct':{'observed_concordance':concordant,'observed_discordance':discordant,
                     'posterior_mean':(1+concordant)/(2+concordant+discordant),
                     'status':'estimated' if concordant+discordant else 'unknown',
                     'meaning':'Choice agreement after delivery, not causal acceptance or benefit.'},
            'socratic':{'status':'unknown','reason':'Reconsideration is unobserved without explicit reports.'},
            'status':'estimated' if evidence or concordant+discordant else 'unknown','feedback_counts':counts,'evidence':evidence,
            'reported_burden':{'mean':mean,'approximate_95_interval':[max(0,mean-1.96*sd),min(1,mean+1.96*sd)],
                'prior':[1,1],'samples':a+b-2},
            'limits':['Explicit reports are not measured trust, compliance, or intervention effectiveness.',
                      'Disagreement contests an interpretation; it is not evidence of a general aversion to assistance.']}


def estimate(session,history):
    profile=session.get('calibration_profile') or {}
    person=get_task(session['task']).participant(history,profile)
    person['calibration']=profile or {'status':'unknown','reason':'No calibrated task-specific model in this condition.'}
    person['interaction']=interaction_estimate(session)
    person['model_version']=VERSION
    person['unknown']=['Intent','Subjective confidence','Responsiveness to advice or questions without interaction evidence',
        'Overconfidence (confidence not elicited)','Hesitation (response time alone is insufficient)']
    return person


def selection_cost(base_cost,person):
    model=person.get('interaction',{}).get('reported_burden',{})
    # No personalisation bonus. An unobserved/withheld model has exactly the common cost.
    if not model.get('samples'):return base_cost
    return round(base_cost*(.5+model['mean']),6)
