"""Build synthetic ontology walkthroughs using the actual current backend.

Runs in a temporary store, forces offline wording and never reads participant
data. The generated files illustrate representation, not intervention effects.
Run from anywhere: python3 docs/ontology_examples/build_examples.py
"""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ['SOCRATIC_LLM']='offline'
os.environ['SOCRATIC_LANGUAGE_MODE']='bounded'
os.environ['SOCRATIC_INTERPRET_RESPONSES']='0'

from socratic_prototype.store import Store,RULES
from socratic_prototype.demo import run_scripted,evaluation
from socratic_prototype.validation import turtle

OUT=Path(__file__).resolve().parent


def create(store,task,calibrations):
    return store.create({'id':'ontology_'+task.lower(),'participant_id':'synthetic_ontology',
        'task':task,'condition':'F','phase':'assisted','protocol':'short','preference':'standard',
        'calibration_ids':calibrations,'seed':'synthetic-ontology-walkthrough'})['id']


def delivery(store,sid,record,visible):
    d=record['snapshot']['decision'];visible=visible and d['action']!='silence'
    store.event(sid,{'kind':'delivery','decision_id':d['id'],'index':record['input']['index'],
        'delivered':visible,'generation_latency_ms':0,'reading_exposure_ms':4000 if visible else 0,'early_attempts':0})


def save(store,sid,excerpt):
    session=store.get(sid)
    OUT.joinpath(session['task'].lower()+'.ttl').write_text(turtle(session))
    data={'synthetic':True,'notice':'Constructed backend walkthrough, not human data or a complete experimental session.',
          'task':session['task'],'condition':session['condition'],'model_version':session['model_version'],
          'policy_version':session['policy']['version'],'schema_version':session['schema_version'],
          'task_module':session['task_module'],
          **({'argumentation_configuration':session['argumentation_configuration']} if 'argumentation_configuration' in session else {}),**excerpt}
    OUT.joinpath(session['task'].lower()+'.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    return store.replay(sid)


def main():
    with tempfile.TemporaryDirectory(prefix='socratic-ontology-') as directory:
        store=Store(Path(directory)/'temporary.sqlite3')
        calibrations={t:run_scripted(store,t,participant='synthetic_ontology') for t in ['MAB','TBS']}
        sid=create(store,'MAB',calibrations);focus=None;response=None;revised=None
        for i in range(1,9):
            record=store.event(sid,evaluation('MAB',sid,i));delivery(store,sid,record,True)
            if i==7:
                focus=record
                d=record['snapshot']['decision'];assert d['hypothesis']=='underexploration'
                response=store.event(sid,{'kind':'response','decision_id':d['id'],'index':i,'feedback':'disagree',
                    'text':'I am keeping this option while collecting more feedback.','hypothesis':d['hypothesis']})
            if i==8:revised=record
            store.event(sid,{'kind':'feedback','trial_id':record['input']['trial_id'],'index':i,'choice':'blue1',
                'outcome':0,'score_after':0,'timed_out':False,'response_ms':1000})
        current=next(c for c in revised['snapshot']['claims'] if c['id'].endswith('_underexploration'))
        assert 'contested' in current['statuses'] and current['revises']
        print('MAB',save(store,sid,{'observed_history':'The first eight choices are blue1, each returning zero reward.',
            'intervention_at_trial_7':focus,'participant_response':response,'revised_state_at_trial_8':revised}))
        sid=create(store,'TBS',calibrations);points=0
        for i in range(1,9):
            ev=evaluation('TBS',sid,i,points=points)
            pair=RULES['options'][1 if i==8 else 0]
            ev['options']=[{'id':a,'key':key,'amount':p[0],'probability':p[1]}
                           for a,key,p in zip(['safe','risky'],['1','9'],pair)]
            record=store.event(sid,ev)
            # Earlier selected prompts are deliberately unexposed in this constructed
            # case, allowing the final dependency intervention without a cooldown.
            delivery(store,sid,record,i==8)
            choice='risky' if i==8 else 'safe';gain=260 if i==8 else 100 if i<=2 else 0
            points+=gain
            feedback=store.event(sid,{'kind':'feedback','trial_id':ev['trial_id'],'index':i,'choice':choice,
                'outcome':gain,'points_after':points,'timed_out':False,'response_ms':1000})
        env=record['snapshot']['environment'];safe,risky=env['options']
        assert env['target_gap']==730 and env['remaining']==1
        assert safe['expected_value']==108 and safe['final_trial_target_probability']==0
        assert risky['expected_value']==91 and risky['final_trial_target_probability']==.35
        assert record['snapshot']['decision']['action']=='highlight-dependency'
        assert feedback['snapshot']['environment']['after_feedback']['points']==1058
        print('TBS',save(store,sid,{'observed_history':'Two early safe wins of 100 points, followed by zero gains, leave 200 points before the final choice.',
            'exposure_note':'Earlier selected messages are intentionally recorded as unexposed in this synthetic example.',
            'final_trial_evaluation':record,'final_trial_feedback':feedback}))
    print('Wrote synthetic MAB/TBS JSON excerpts and RDF projections to',OUT)


if __name__=='__main__':main()
