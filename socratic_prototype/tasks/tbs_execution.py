"""TBS actor and simulator implementation, owned by the TBS task module."""
import copy
import math
from ..records import fields,require,number
from .tbs import RULES,PROTOCOLS
from .execution import normalise,describe_adapter

VERSION='tbs-execution-0.1'
METRICS={'score':{'direction':'maximize','unit':'multiplied-points'},'targets_attained':{'direction':'maximize','unit':'blocks'}}

def describe():return describe_adapter(VERSION,__file__,METRICS)
def validate_actor(p):
    fields(p,['intercept','slope']);require(all(number(p[k],-20,20) for k in p),'Invalid TBS actor parameters')

def baseline(history,p,ev):
    x=max(-2,min(2,(max(0,ev['target']-ev['points'])/ev['remaining']-150)/150))
    z=max(-50,min(50,p['intercept']+p['slope']*x));r=1/(1+math.exp(-z));return {'safe':1-r,'risky':r}

def reconsider(history,p,ev,intervention):
    if ev['remaining']==1:
        values={o['id']:o['probability']*float((ev['points']+o['amount'])*ev['multiplier']>=ev['target'])+
            (1-o['probability'])*float(ev['points']>=ev['target']) for o in ev['options']}
        if sum(values.values())>0:return normalise(values)
    need=max(0,ev['target']-ev['points'])/ev['remaining']
    return normalise({o['id']:o['probability']*max(1,o['amount'])/(1+abs(o['amount']-need)) for o in ev['options']})

def make_environment(protocol,seed,random_source):return Environment(protocol,seed,random_source)

class Environment:
    def __init__(self,protocol,seed,random_source):
        self.protocol=protocol;self.seed=seed;self.random=random_source;self.total=PROTOCOLS[protocol];self.index=0
        self.points=0;self.blocks=[]
    @property
    def done(self):return self.index>=self.total
    def evaluation(self,sid,index):
        block=(index-1)//8+1;remaining=8-(index-1)%8
        if remaining==8:self.points=0
        target_index=int(self.random(self.seed,'target',block)*len(RULES['targets']))
        pair=RULES['options'][int(self.random(self.seed,'pair',index)*len(RULES['options']))]
        return {'kind':'evaluation','trial_id':sid+'_trial_'+str(index),'index':index,'points':self.points,
                'target':RULES['targets'][target_index],'remaining':remaining,'block':block,'multiplier':RULES['multipliers'][target_index],
                'options':[{'id':a,'key':key,'amount':o[0],'probability':o[1]} for a,key,o in zip(['safe','risky'],['1','9'],pair)]}
    def outcome(self,ev,choice):
        missed=choice=='NO_RESPONSE';self.index=ev['index'];u=self.random(self.seed,'outcome',self.index,choice)
        option=next((o for o in ev['options'] if o['id']==choice),None)
        gain=option['amount'] if option and u<option['probability'] else 0;self.points+=gain
        if ev['remaining']==1:
            total=self.points*(ev['multiplier'] if gain>0 else 1)
            self.blocks.append({'score':total,'target':ev['target'],'attained':total>=ev['target']})
        return {'kind':'feedback','trial_id':ev['trial_id'],'index':self.index,'choice':choice,'outcome':gain,
                'timed_out':missed,'response_ms':5000 if missed else 700,'points_after':self.points}
    def metrics(self):return {'score':sum(b['score'] for b in self.blocks),'targets_attained':sum(b['attained'] for b in self.blocks),'blocks':copy.deepcopy(self.blocks)}
    def evaluator_state(self):return {}
