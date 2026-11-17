"""Assistant's uncertain MAB observer; no access to an actor or evaluator."""
import math
from itertools import product
from ..learning import prior,condition,prediction,posterior,summary
from ..assistance_response import conditional_preferences

VERSION='mab-observer-0.1'


def grid():
    return [dict(alpha_plus=a,alpha_minus=b,beta=c)
            for a,b,c in product([.15,.45,.75],[.15,.45,.75],[.5,2,5])]


class Observer:
    def __init__(self,profile):
        from .mab import ARMS
        self.rows=grid();self.weights,self.transferred=prior(self.rows,profile.get('choice_posterior'))
        self.q=[{a:0. for a in ARMS} for _ in self.rows]
        self.updates=0;self.outcomes=0;self.last=None

    def distributions(self,ev):
        result=[]
        for row,q in zip(self.rows,self.q):
            values={o['id']:row['beta']*q[o['id']] for o in ev['options']}
            top=max(values.values());exps={a:math.exp(v-top) for a,v in values.items()}
            total=sum(exps.values());result.append({a:v/total for a,v in exps.items()})
        return result

    def predict(self,ev):return prediction(self.distributions(ev),self.weights)

    def observe(self,ev,fb,unaided):
        if fb['timed_out']:return
        a=fb['choice']
        probabilities=self.distributions(ev)
        self.last={'trial_id':ev['trial_id'],'prediction_error':sum(w*(fb['outcome']/200-q[a]) for w,q in zip(self.weights,self.q)),
                   'choice_probability':sum(w*p[a] for w,p in zip(self.weights,probabilities))}
        if unaided:
            self.weights=condition(self.weights,[p[a] for p in probabilities]);self.updates+=1
        for row,q in zip(self.rows,self.q):
            error=fb['outcome']/200-q[a]
            q[a]+=(row['alpha_plus'] if error>=0 else row['alpha_minus'])*error
        self.outcomes+=1

    def describe(self):
        return {'version':VERSION,'parameter_posterior':posterior(self.rows,self.weights),
                'learned_values':{a:sum(w*q[a] for w,q in zip(self.weights,self.q)) for a in self.q[0]},
                'last_update':self.last,
                'parameters':{k:summary([r[k] for r in self.rows],self.weights) for k in self.rows[0]},
                'choice_updates':self.updates,'outcome_updates':self.outcomes,
                'calibration_posterior_transferred':self.transferred,
                'assumptions':['27 dual-learning-rate/softmax hypotheses; task values reset each run.',
                    'Only demonstrably unaided choices fit task parameters; all completed rewards update learned values.',
                    'Intervals describe this coarse model grid, not measured beliefs or calibrated predictive coverage.']}


def assistance_target(ev,base,intervention):
    if intervention['style']=='direct':return conditional_preferences(base,[intervention['recommendation']['option_id']])
    options=[c['option_id'] for c in intervention.get('comparisons',[])]
    return conditional_preferences(base,options) if len(options)>=2 else None
