"""Exploratory public TBS observer and explicit assistance-processing hypothesis."""
import math
from itertools import product
from ..learning import prior,condition,prediction,posterior,summary
from ..assistance_response import conditional_preferences

VERSION='tbs-observer-0.1'


def grid():return [dict(intercept=a,slope=b) for a,b in product([-2,-1,0,1,2],[-3,-1.5,0,1.5,3])]


class Observer:
    def __init__(self,profile):
        self.rows=grid();self.weights,self.transferred=prior(self.rows,profile.get('policy',{}).get('choice_posterior'))
        self.updates=0;self.outcomes=0
        self.calibration_samples=profile.get('policy',{}).get('samples',0) if self.transferred else 0
        self.evidence=[]
        self.calibration_evidence=list(profile.get('policy',{}).get('evidence',[])) if self.transferred else []

    def distributions(self,ev):
        x=max(-2,min(2,(max(0,ev['target']-ev['points'])/ev['remaining']-150)/150))
        result=[]
        for row in self.rows:
            p=1/(1+math.exp(-(row['intercept']+row['slope']*x)))
            result.append({'safe':1-p,'risky':p})
        return result

    def predict(self,ev):return prediction(self.distributions(ev),self.weights)

    def observe(self,ev,fb,unaided):
        if fb['timed_out']:return
        if unaided:
            self.weights=condition(self.weights,[p[fb['choice']] for p in self.distributions(ev)]);self.updates+=1
            self.evidence.append(ev['trial_id'])
        self.outcomes+=1

    def describe(self):
        sensitivity=summary([r['slope'] for r in self.rows],self.weights)
        return {'version':VERSION,'parameter_posterior':posterior(self.rows,self.weights),
                'parameters':{k:summary([r[k] for r in self.rows],self.weights) for k in self.rows[0]},
                'pressure_policy':{'samples':self.calibration_samples+self.updates,'status':'inferred',
                    'sensitivity_mean':sensitivity['mean'],'sensitivity_interval':sensitivity['interval'],
                    'p_positive_sensitivity':sum(w for r,w in zip(self.rows,self.weights) if r['slope']>0),
                    'evidence':list(self.evidence),'calibration_evidence':list(self.calibration_evidence)},
                'choice_updates':self.updates,'outcome_updates':self.outcomes,
                'calibration_posterior_transferred':self.transferred,
                'assumptions':['25 pressure-logistic hypotheses; this is an exploratory observer, not the original empirical TBS fit.',
                    'Option-value and separate horizon effects are omitted; systematic misspecification remains possible.',
                    'Only demonstrably unaided choices fit task parameters.']}


def assistance_target(ev,base,intervention):
    """Assistant-side processing assumption, not knowledge of the actor's response."""
    if intervention['style']=='direct':return conditional_preferences(base,[intervention['recommendation']['option_id']])
    if len(intervention.get('comparisons',[]))<2:return None
    def norm(values):
        total=sum(values.values());return {a:v/total for a,v in values.items()}
    if intervention.get('issue')=='expected_value_limit' and ev['remaining']>1:
        return norm({o['id']:o['probability']*o['amount'] for o in ev['options']})
    if ev['remaining']==1:
        values={o['id']:o['probability']*float((ev['points']+o['amount'])*ev['multiplier']>=ev['target'])+
                (1-o['probability'])*float(ev['points']>=ev['target']) for o in ev['options']}
        if sum(values.values())>0:return norm(values)
    need=max(0,ev['target']-ev['points'])/ev['remaining']
    return norm({o['id']:o['probability']*max(1,o['amount'])/(1+abs(o['amount']-need)) for o in ev['options']})
