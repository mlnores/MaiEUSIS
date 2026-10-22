"""Create labelled synthetic calibration personas for local comparisons.

These deterministic fixtures exercise models; they are not human measurements,
validated cognitive types, or samples from the original experimental schedules.
Existing participant sessions are never replaced.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random

VERSION='synthetic-profiles-0.1'
PROFILES={
    'synthetic_broad_sampling':{
        'description':'MAB: cycles through all six options. TBS: alternates SAFE and RISKY without a pressure rule.',
        'mab':'broad','tbs':'alternating'},
    'synthetic_persistent':{
        'description':'MAB: repeatedly chooses red2 despite mixed feedback. TBS: always chooses SAFE.',
        'mab':'persistent','tbs':'safe'},
    'synthetic_fast_updates':{
        'description':'MAB: generated with fast value updates and strong value sensitivity. TBS: risk increases moderately with pressure.',
        'mab':'fast','tbs':'moderate'},
    'synthetic_pressure_up':{
        'description':'MAB: moderate value updating. TBS: likelihood of RISKY increases with target pressure.',
        'mab':'moderate','tbs':'up'},
    'synthetic_pressure_down':{
        'description':'MAB: the same baseline as pressure_up. TBS: likelihood of RISKY decreases with target pressure.',
        'mab':'moderate','tbs':'down'},
}


def random_source(seed):
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest(),16))


def trial_inputs(name,task,sid,protocol='short'):
    """Yield only the public evaluation/feedback envelopes accepted by the store."""
    from .demo import evaluation
    from .models import ARMS,rl,softmax
    from .tasks import get_task
    spec=PROFILES[name]
    # Hold the MAB baseline equal for the two pressure personas.
    seed=VERSION+':'+task+':'+(spec['mab'] if task=='MAB' else name)+':'+protocol
    rng=random_source(seed);score=points=0;history=[]
    for index in range(1,get_task(task).PROTOCOLS[protocol]+1):
        if task=='TBS' and (index-1)%8==0:points=0
        ev=evaluation(task,sid,index,score,points)
        if task=='MAB':
            style=spec['mab']
            if style=='broad':choice=ARMS[(index-1)%len(ARMS)]
            elif style=='persistent':choice='red2'
            else:
                alpha=.75 if style=='fast' else .45;beta=5 if style=='fast' else 2
                q,_=rl(history,alpha,alpha,beta);probabilities=softmax(q,beta)
                choice=rng.choices(ARMS,weights=[probabilities[a] for a in ARMS])[0]
            # Permitted scripted outcomes, not claimed original hidden schedules.
            preferred=ARMS[0 if index<=20 else 3]
            weights=[.75,.15,.10] if choice==preferred else [.20,.35,.45]
            magnitude=100 if choice.startswith('blue') else 200
            outcome=rng.choices([magnitude,0,-magnitude],weights=weights)[0]
            score+=outcome;feedback={'choice':choice,'outcome':outcome,'score_after':score}
            history.append({'choice':choice,'outcome':outcome,'timed_out':False,'trial_id':ev['trial_id']})
        else:
            target=[595,930,1105][(ev['block']-1)%3]
            ev['target']=target;ev['multiplier']=get_task(task).RULES['multipliers'][get_task(task).RULES['targets'].index(target)]
            style=spec['tbs']
            if style=='safe':choice='safe'
            elif style=='alternating':choice='safe' if index%2 else 'risky'
            else:
                pressure=max(0,target-points)/ev['remaining'];x=max(-2,min(2,(pressure-150)/150))
                slope={'up':3,'down':-3,'moderate':1.5}[style]
                chance=1/(1+math.exp(-slope*x));choice='risky' if rng.random()<chance else 'safe'
            option=next(o for o in ev['options'] if o['id']==choice)
            outcome=option['amount'] if rng.random()<option['probability'] else 0
            points+=outcome;feedback={'choice':choice,'outcome':outcome,'points_after':points}
        yield ev,{'kind':'feedback','trial_id':ev['trial_id'],'index':index,'timed_out':False,
                  'response_ms':700,**feedback}


def session_id(name,task,protocol):
    from .argumentation import configuration
    from .engine import POLICY,NETWORK
    from .grounding import VERSION as GROUNDING_VERSION
    from .language import configuration as language_configuration
    from .tasks import get_task
    from .tasks.base import MODEL_VERSION
    module=get_task(task)
    descriptor=[VERSION,name,task,protocol,MODEL_VERSION,GROUNDING_VERSION,module.describe(),POLICY,
                NETWORK.describe(),configuration(module),language_configuration()]
    return 'prototype_'+hashlib.sha256(json.dumps(descriptor,sort_keys=True).encode()).hexdigest()[:24]


def seed_profiles(store,protocol='short',names=None,on_progress=None):
    """Resume our own deterministic fixtures and reuse completed ones idempotently."""
    results={}
    for name in names or PROFILES:
        if name not in PROFILES:raise ValueError('Unknown prototype profile: '+name)
        results[name]={}
        for task in ['MAB','TBS']:
            sid=session_id(name,task,protocol)
            metadata={'name':name,'version':VERSION,'description':PROFILES[name]['description'],
                      'notice':'Synthetic scripted calibration, not human data. Fitted estimates need not equal generating parameters.'}
            try:s=store.get(sid)
            except KeyError:
                s=store.create(dict(id=sid,participant_id=name,task=task,condition='A',phase='calibration',
                    protocol=protocol,preference='standard',seed=VERSION+':'+name),synthetic_profile=metadata)
            if not s.get('synthetic') or s.get('synthetic_profile')!=metadata:
                raise ValueError('Existing session is not this synthetic fixture; refusing to replace it: '+sid)
            if not s['completed']:
                if s['finished']:raise ValueError('Synthetic fixture was ended early; refusing to overwrite it: '+sid)
                # Exact events are idempotent in Store.event. Explicitly compare
                # the saved prefix before resuming, rather than modifying it.
                inputs=[]
                for ev,feedback in trial_inputs(name,task,sid,protocol):
                    decision_id=sid+'_event_'+str(len(inputs)+1)+'_decision'
                    inputs.extend([ev,dict(kind='delivery',decision_id=decision_id,index=ev['index'],delivered=False,
                        generation_latency_ms=0,reading_exposure_ms=0,early_attempts=0),feedback])
                recorded=[e['input'] for e in s['events']]
                if recorded!=inputs[:len(recorded)]:raise ValueError('Synthetic fixture prefix differs; refusing to overwrite it: '+sid)
                for event in inputs[len(recorded):]:store.event(sid,event)
                store.finish(sid,{'completed':True})
            results[name][task]=sid
            if on_progress:on_progress(name,task,sid)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',default=str(Path(__file__).parent/'data'))
    parser.add_argument('--protocol',choices=['short','full'],default='short')
    parser.add_argument('--profile',choices=list(PROFILES),action='append',help='Repeat to select specific profiles; default: all five.')
    args=parser.parse_args()
    os.environ.update(SOCRATIC_LLM='offline',SOCRATIC_LANGUAGE_MODE='bounded',SOCRATIC_INTERPRET_RESPONSES='0')
    from .store import Store
    store=Store(Path(args.data_dir)/'sessions.sqlite3')
    print('Creating synthetic calibrations in',store.path,flush=True)
    def progress(name,task,sid):print(name,task,'ready:',sid,flush=True)
    result=seed_profiles(store,args.protocol,args.profile,progress)
    print('Ready:',len(result),'synthetic pseudonyms. Reload the task page and choose one under Known pseudonyms.',flush=True)


if __name__=='__main__':main()
