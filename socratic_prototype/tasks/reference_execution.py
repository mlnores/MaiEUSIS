"""Reference actor and private simulator; not an empirical participant model."""
from ..records import fields,require,number
from .execution import normalise,describe_adapter
from .reference import PROTOCOLS
VERSION='reference-execution-0.1'
METRICS={'decision_errors':{'direction':'minimize','unit':'choices'}}
def describe():return describe_adapter(VERSION,__file__,METRICS)
def validate_actor(p):
    fields(p,['right_bias']);require(number(p['right_bias'],0,1),'Invalid reference actor parameter')
def baseline(history,p,ev):
    beliefs={}
    for option in ['left','right']:
        sampled=[r for r in history if not r['timed_out'] and r['choice']==option]
        beliefs[option]=(1+sum(r['outcome'] for r in sampled))/(2+len(sampled))
    return normalise({'left':(1-p['right_bias'])*beliefs['left'],'right':p['right_bias']*beliefs['right']})
def reconsider(history,p,ev,intervention):return normalise({o['id']:o['probability'] for o in ev['options']})
def make_environment(protocol,seed,random_source):return Environment(protocol,seed,random_source)
class Environment:
    def __init__(self,protocol,seed,random_source):self.total=PROTOCOLS[protocol];self.seed=seed;self.random=random_source;self.points=0;self.index=0;self.errors=0;self.last_draw=None
    @property
    def done(self):return self.index>=self.total
    def evaluation(self,sid,index):
        ps=[.75,.25] if index%2 else [.25,.75]
        return {'kind':'evaluation','trial_id':sid+'_trial_'+str(index),'index':index,'points':self.points,
                'options':[{'id':name,'key':key,'probability':p} for name,key,p in zip(['left','right'],['1','9'],ps)]}
    def outcome(self,ev,choice):
        self.index=ev['index'];self.last_draw=self.random(self.seed,'outcome',self.index,choice)
        option=next((o for o in ev['options'] if o['id']==choice),None);gain=int(option is not None and self.last_draw<option['probability'])
        self.errors+=int(option is None or option['probability']<max(o['probability'] for o in ev['options']));self.points+=gain
        return {'kind':'feedback','trial_id':ev['trial_id'],'index':self.index,'choice':choice,'outcome':gain,'timed_out':choice=='NO_RESPONSE',
                'response_ms':5000 if choice=='NO_RESPONSE' else 700,'points_after':self.points}
    def metrics(self):return {'decision_errors':self.errors}
    def evaluator_state(self):return {'private_marker':'never-in-public-events','outcome_draw':self.last_draw}
