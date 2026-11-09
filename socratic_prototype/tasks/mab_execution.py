"""MAB actor and simulator implementation, owned by the MAB task module."""
import copy
import hashlib
from pathlib import Path
from ..records import fields,require,number
from .mab import ARMS,KEYS,PROTOCOLS,rl,softmax,mab_environment
from .execution import normalise,describe_adapter

VERSION='mab-execution-0.3'
RECENT_RECONSIDERATION={'window_elapsed_trials':6,'rule':'Apply the existing issue-specific heuristic to only the last six elapsed trials. Misses consume memory positions but supply no outcome evidence.'}
METRICS={'score':{'direction':'maximize','unit':'reward-points'}}
INITIAL=[[.7,.2,.1],[.5,.3,.2],[.34,.33,.33],[.5,.3,.2],[.34,.33,.33],[.7,.2,.1]]

def describe():
    from . import mab_empirical
    return {**describe_adapter(VERSION,__file__,METRICS),
            'actor_dependencies':{'mab_empirical.py':hashlib.sha256(Path(mab_empirical.__file__).read_bytes()).hexdigest()}}
def validate_actor(p):
    fields(p,['alpha_plus','alpha_minus','beta'],['model','reward_scale'])
    require(all(number(p[k],0,1) for k in ['alpha_plus','alpha_minus']) and number(p['beta'],0,50),'Invalid MAB actor parameters')
    if 'model' in p or 'reward_scale' in p:
        from .mab_empirical import MODEL
        require(p.get('model')==MODEL and p.get('reward_scale')==100,'Empirical MAB requires the versioned points/100 convention')

def baseline(history,p,ev):
    if 'model' in p:
        from .mab_empirical import values,probabilities
        return probabilities(values(history,p),p['beta'])
    q,_=rl(history,p['alpha_plus'],p['alpha_minus'],p['beta']);return softmax(q,p['beta'])

def reconsider(history,p,ev,intervention):
    env=mab_environment(history,.15)
    if intervention['focus']=='exploration':return normalise({a['arm']:1/(1+a['samples']) for a in env['arms']})
    return softmax({a['arm']:a['estimated_value']/p.get('reward_scale',200) for a in env['arms']},p['beta'])

def reconsider_recent(history,p,ev,intervention):
    return reconsider(history[-RECENT_RECONSIDERATION['window_elapsed_trials']:],p,ev,intervention)

def make_environment(protocol,seed,random_source):return Environment(protocol,seed,random_source)

class Environment:
    def __init__(self,protocol,seed,random_source):
        self.protocol=protocol;self.seed=seed;self.random=random_source;self.total=PROTOCOLS[protocol];self.index=0
        self.score=0;self.probabilities=copy.deepcopy(INITIAL)
    @property
    def done(self):return self.index>=self.total
    def evaluation(self,sid,index):
        stable=10 if self.protocol=='short' else 50
        if index>stable:
            for color,chance in [('blue',1/16),('red',1/4)]:
                if self.random(self.seed,'jump',index,color)<chance:
                    for a,p in zip(ARMS,self.probabilities):
                        if a.startswith(color):p[0],p[1]=p[1],p[0]
        return {'kind':'evaluation','trial_id':sid+'_trial_'+str(index),'index':index,'score':self.score,
                'options':[{'id':a,'key':KEYS[a],'outcomes':[100,0,-100] if a.startswith('blue') else [200,0,-200]} for a in ARMS]}
    def outcome(self,ev,choice):
        missed=choice=='NO_RESPONSE';self.index=ev['index'];u=self.random(self.seed,'outcome',self.index,choice)
        if missed:gain=-200
        else:
            i=ARMS.index(choice);p=self.probabilities[i];values=ev['options'][i]['outcomes']
            gain=values[0 if u<p[0] else 1 if u<p[0]+p[1] else 2]
        self.score+=gain
        return {'kind':'feedback','trial_id':ev['trial_id'],'index':self.index,'choice':choice,'outcome':gain,
                'timed_out':missed,'response_ms':5000 if missed else 700,'score_after':self.score}
    def metrics(self):return {'score':self.score}
    def evaluator_state(self):return {'probabilities':copy.deepcopy(self.probabilities)}
