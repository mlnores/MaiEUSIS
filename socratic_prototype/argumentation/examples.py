"""Build synthetic graph reasoning examples in a temporary store, with no LLM.

Run: .venv/bin/python -m socratic_prototype.argumentation.examples --output examples.json
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    os.environ['SOCRATIC_LLM']='offline';os.environ['SOCRATIC_LANGUAGE_MODE']='bounded'
    os.environ['SOCRATIC_INTERPRET_RESPONSES']='0'
    from . import analyse
    from ..store import Store
    from ..demo import evaluation
    result={'synthetic':True,'notice':'Constructed partial unassisted sessions; graph warrants are computed but condition A stays silent. Not human data.',
            'cases':{},'replay':{}}
    with tempfile.TemporaryDirectory(prefix='maieusis-argumentation-examples-') as temp:
        store=Store(Path(temp)/'sessions.sqlite3')
        for task in ['MAB','TBS']:
            session=store.create(dict(id='argumentation_example_'+task.lower(),participant_id='synthetic_argumentation',
                task=task,condition='A',phase='calibration',protocol='short',preference='standard'))
            result.setdefault('configurations',{})[task]=session['argumentation_configuration']
            if session['argumentation_configuration']['backend']=='unavailable':
                parser.error('RDFLib is unavailable. Use the environment with requirements-research.txt installed.')
            points=0
            for index in range(1,40 if task=='MAB' else 9):
                ev=evaluation(task,session['id'],index,points=points)
                if task=='TBS':
                    pair=[(180,.6),(260,.35)] if index==8 else [(100,.9),(265,.35)]
                    for option,(amount,probability) in zip(ev['options'],pair):option.update(amount=amount,probability=probability)
                event=store.event(session['id'],ev)
                if (task=='MAB' and index in {8,39}) or (task=='TBS' and index==8):
                    result['cases'][task.lower()+'_'+str(index)]=event['snapshot']['graph_argumentation']
                gain=100 if task=='TBS' and index<=2 else 0;points+=gain
                store.event(session['id'],dict(kind='feedback',trial_id=ev['trial_id'],index=index,
                    choice='blue1' if task=='MAB' else 'safe',outcome=gain,timed_out=False,response_ms=500,
                    **{'score_after' if task=='MAB' else 'points_after':points}))
            result['replay'][task]=store.replay(session['id'])
            # Warm discovery-only timing excludes model calculation, SHACL, SQLite,
            # HTTP, generation and browser display. Never persisted in session events.
            stored=store.get(session['id']);durations=[]
            for _ in range(5):
                start=time.perf_counter();analyse(stored,event);durations.append((time.perf_counter()-start)*1000)
            result.setdefault('local_discovery_benchmark',{})[task]={
                'median_ms':round(statistics.median(durations),3),'max_ms':round(max(durations),3),
                'samples':5,'scope':'Warm graph discovery only; excludes all other backend and display work.'}
    path=Path(args.output);path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Wrote',len(result['cases']),'synthetic reasoning cases to',path)
    for task,replay in result['replay'].items():print(task,'replay matches:',replay['matches'])
    print('Discovery benchmark:',json.dumps(result['local_discovery_benchmark']))


if __name__=='__main__':main()
