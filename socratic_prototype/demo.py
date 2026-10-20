"""Generate clearly labelled synthetic calibration and intervention traces.

No outcomes are asserted to be participant data. Scripted outcomes are just
permitted task outcomes for exercising policy branches, never hidden schedules.
"""
import argparse
from pathlib import Path
from .store import Store,RULES
from .models import ARMS,KEYS


def evaluation(task,sid,index,score=0,points=0):
    base={'kind':'evaluation','trial_id':sid+'_trial_'+str(index),'index':index}
    if task=='MAB':return base|{'score':score,'options':[{'id':a,'key':KEYS[a],'outcomes':[100,0,-100] if a.startswith('blue') else [200,0,-200]} for a in ARMS]}
    pair=RULES['options'][(index-1)%8]
    return base|{'points':points,'target':930,'multiplier':2.3,'remaining':8-(index-1)%8,'block':(index-1)//8+1,
                'options':[{'id':a,'key':key,'amount':o[0],'probability':o[1]} for a,key,o in zip(['safe','risky'],['1','9'],pair)]}


def run_scripted(store,task,condition='A',phase='calibration',calibration_ids=None,protocol='short',participant='synthetic_demo'):
    s=store.create({'participant_id':participant,'task':task,'condition':condition,'phase':phase,'protocol':protocol,'preference':'standard',
                    'calibration_ids':calibration_ids or {},'seed':'synthetic-scripted-outcomes'})
    sid=s['id'];score=0;points=0
    for index in range(1,s['total_trials']+1):
        if task=='TBS' and (index-1)%8==0:points=0
        ev=evaluation(task,sid,index,score,points)
        result=store.event(sid,ev);d=result['snapshot']['decision']
        store.event(sid,{'kind':'delivery','decision_id':d['id'],'index':index,'delivered':d['action']!='silence',
                         'generation_latency_ms':0,'reading_exposure_ms':4000 if d['action']!='silence' else 0,'early_attempts':0})
        if task=='MAB':
            choice=ARMS[(index-1)%6] if phase=='calibration' else 'blue1'
            outcome=(100 if choice.startswith('blue') else 200) if index%4==0 else 0 if index%3 else (-100 if choice.startswith('blue') else -200)
            score+=outcome;feedback={'choice':choice,'outcome':outcome,'score_after':score}
        else:
            choice='risky' if index%3 else 'safe';o=next(o for o in ev['options'] if o['id']==choice)
            outcome=o['amount'] if index%2 else 0;points+=outcome
            feedback={'choice':choice,'outcome':outcome,'points_after':points}
        store.event(sid,{'kind':'feedback','trial_id':ev['trial_id'],'index':index,'timed_out':False,'response_ms':700,**feedback})
    store.finish(sid,{'completed':True})
    return sid


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data-dir',default=str(Path(__file__).parent/'data'));args=parser.parse_args()
    store=Store(Path(args.data_dir)/'sessions.sqlite3')
    ids={task:run_scripted(store,task) for task in ['MAB','TBS']}
    for task in ['MAB','TBS']:
        sid=run_scripted(store,task,'F','assisted',ids)
        print(task,sid,store.replay(sid))
    print('Synthetic sessions are now available in the researcher inspector. Use participant pseudonym synthetic_demo to try assisted tasks with these synthetic calibrations.')

if __name__=='__main__':main()
