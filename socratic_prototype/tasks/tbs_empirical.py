"""Provisional offer-marginal state/feedback policy, not the original TBS model.

Historical offers are unavailable. Offer sensitivity in prospective simulations
is an explicit assumption that preserves the fitted marginal risky probability.
"""
import math
from ..records import fields,require,number

VERSION='tbs-state-feedback-0.1'
MODEL='tbs_state_feedback_v1'
FEATURES=('pressure','remaining','is_final','final_required_gain','previous_risky',
          'previous_choice_known','previous_gain')


def sigmoid(z):
    return 1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))


def features(evaluation,history):
    target=evaluation['target'];points=evaluation['points'];remaining=evaluation['remaining']
    previous=history[-1] if history and history[-1].get('block')==evaluation['block'] else {}
    known=previous.get('choice') in {'safe','risky'} and not previous.get('timed_out',False)
    final=remaining==1
    return [max(0,target-points)/remaining,remaining,float(final),
            target/evaluation['multiplier']-points if final else 0.,
            float(known and previous['choice']=='risky'),float(known),float(previous.get('outcome',0)>0)]


def marginal_probability(raw,parameters):
    z=[(v-m)/s for v,m,s in zip(raw,parameters['means'],parameters['scales'])]
    return sigmoid(parameters['intercept']+sum(c*v for c,v in zip(parameters['coefficients'],z)))


def offer_cue(pair):
    return (pair[1][0]*pair[1][1]-pair[0][0]*pair[0][1])/100.


def conditional_probability(marginal,cues,current_cue,sensitivity):
    if sensitivity==0 or marginal<=0 or marginal>=1:return marginal
    logit=math.log(marginal)-math.log1p(-marginal)
    span=abs(sensitivity)*max(abs(c) for c in [*cues,current_cue])+2
    lo,hi=logit-span,logit+span
    for _ in range(48):
        mid=(lo+hi)/2
        if sum(sigmoid(mid+sensitivity*c) for c in cues)/len(cues)<marginal:lo=mid
        else:hi=mid
    return sigmoid((lo+hi)/2+sensitivity*current_cue)


def baseline(history,parameters,evaluation,offer_pairs):
    p=marginal_probability(features(evaluation,history),parameters)
    sensitivity=parameters['offer_sensitivity']
    if sensitivity:
        options={o['id']:o for o in evaluation['options']}
        cue=(options['risky']['amount']*options['risky']['probability']-
             options['safe']['amount']*options['safe']['probability'])/100.
        p=conditional_probability(p,[offer_cue(pair) for pair in offer_pairs],cue,sensitivity)
    return {'safe':1-p,'risky':p}


def validate_actor(p):
    fields(p,['model','features','intercept','coefficients','means','scales','offer_sensitivity'])
    require(p['model']==MODEL and p['features']==list(FEATURES),'Unsupported empirical TBS model or feature order')
    require(number(p['intercept'],-10000,10000),'Invalid TBS intercept')
    for key in ['coefficients','means','scales']:
        require(isinstance(p[key],list) and len(p[key])==len(FEATURES) and all(number(v) for v in p[key]),'Invalid TBS '+key)
    require(all(v>0 for v in p['scales']),'TBS scales must be positive')
    require(number(p['offer_sensitivity'],-5,5),'Invalid assumed offer sensitivity')
