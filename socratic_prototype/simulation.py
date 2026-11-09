"""Matched five-condition experiments under explicitly assumed assistance responses.

Evaluator truth is isolated here; only public evaluation/delivery/feedback enters
Store. This is a supported-model research harness, not a reconstruction of the
62 participants or evidence that either form of assistance benefits humans.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from .agents import Participant,validate_participant,VERSION as AGENT_VERSION
from .assistance_response import SCENARIOS,VERSION as RESPONSE_VERSION
from .study import CONDITIONS,default_study,validate_study
from .records import require
from .tasks import get_task
from .tasks.execution import simulation_adapter
from .reconsideration import MECHANISMS, configuration as reconsideration_configuration

VERSION='matched-simulation-0.4'


def uniform(seed,*keys):
    value=json.dumps([str(seed),*keys],sort_keys=True,separators=(',',':')).encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:8],'big')/2**64


def select(probabilities,u):
    cumulative=0
    for option,p in probabilities.items():
        cumulative+=p
        if u<cumulative:return option
    return next(reversed(probabilities))


def Environment(task,protocol,seed):
    module=get_task(task);require(protocol in module.PROTOCOLS,'Unsupported simulation protocol')
    # The callback resolves the shared random source dynamically (also testable).
    env=simulation_adapter(module).make_environment(protocol,seed,lambda *keys:uniform(*keys))
    require(all(callable(getattr(env,n,None)) for n in ['evaluation','outcome','metrics','evaluator_state']), 'Incomplete environment runtime')
    require(type(getattr(env,'done',None)) is bool and not env.done,'Environment must start unfinished')
    return env


def run(store,participants,scenario='null',protocol='short',seed='comparison',repeats=1,max_trials=None,on_progress=None,study=None,calibration_only=False,reconsideration='current'):
    require(scenario in SCENARIOS,'Unknown response scenario')
    study=validate_study(study or default_study(protocol),simulation=True)
    tasks=study['tasks']
    require(type(repeats) is int and repeats>0,'Repeats must be a positive integer')
    require(max_trials is None or type(max_trials) is int and max_trials>0,'max_trials must be positive')
    specs=[validate_participant(p,tasks) for p in participants]
    require(bool(specs) and len({p['id'] for p in specs})==len(specs),'Provide distinct participant pseudonyms')
    mechanisms={task:reconsideration_configuration(get_task(task),reconsideration) for task in tasks}
    report={'version':VERSION,'agent_version':AGENT_VERSION,'response_version':RESPONSE_VERSION,'scenario':scenario,
            'seed':seed,'study':study,'participants':specs,'runs':[],'calibrations':[],'reconsideration':mechanisms,
            'notice':'Synthetic scenario outcomes; not observed human assistance effects. Latent parameters and evaluator truth are excluded from assistant inputs.'}
    for spec in specs:
        calibrations={}
        for task,config in tasks.items():
            protocol=config['protocol']
            actor=Participant(spec,task,'null');env=Environment(task,protocol,f'{seed}:{spec["id"]}:calibration:{task}')
            s=store.create(dict(participant_id=spec['id'],task=task,condition='A',phase='calibration',protocol=protocol,preference='standard',seed=hashlib.sha256(env.seed.encode()).hexdigest()),
                synthetic_profile={'name':spec['id'],'version':VERSION,'description':'Generated calibration from a researcher-supplied synthetic task policy.',
                                   'notice':'Synthetic observations; source parameters require independent model validation.'},study=study)
            for index in range(1,s['total_trials']+1):
                ev=env.evaluation(s['id'],index);record=store.event(s['id'],ev);d=record['snapshot']['decision']
                store.event(s['id'],dict(kind='delivery',decision_id=d['id'],index=index,delivered=False,generation_latency_ms=0,reading_exposure_ms=0,early_attempts=0))
                _,probabilities,effect=actor.distribution(ev,None)
                choice=select(probabilities,uniform(env.seed,'choice',index))
                if uniform(env.seed,'omission',index)<effect['omission_probability']:choice='NO_RESPONSE'
                fb=env.outcome(ev,choice)
                store.event(s['id'],fb);actor.observe(ev,fb)
            require(env.done,'Calibration environment did not finish its protocol')
            store.finish(s['id'],{'completed':True});calibrations[task]=s['id']
            report['calibrations'].append({'participant':spec['id'],'task':task,'session_id':s['id']})
            if on_progress:on_progress(spec['id'],task,'calibration',0)
        if calibration_only:continue
        for repeat in range(repeats):
            for task,config in tasks.items():
                protocol=config['protocol']
                # No condition or session identifier enters environmental/choice streams.
                environment_seed=f'{seed}:{spec["id"]}:{repeat}:{task}'
                for condition in study['conditions']:
                    actor=Participant(spec,task,scenario,reconsideration);env=Environment(task,protocol,environment_seed)
                    s=store.create(dict(participant_id=spec['id'],task=task,condition=condition,phase='assisted',protocol=protocol,
                                        preference='standard',calibration_ids={k:calibrations[k] for k in config['calibration_tasks']},seed=hashlib.sha256(environment_seed.encode()).hexdigest()),
                        synthetic_run={'version':VERSION,'agent_version':AGENT_VERSION,'response_version':RESPONSE_VERSION},study=study)
                    trials=[];count=min(max_trials or s['total_trials'],s['total_trials'])
                    for index in range(1,count+1):
                        ev=env.evaluation(s['id'],index);record=store.event(s['id'],ev);d=record['snapshot']['decision']
                        active=d['action']!='silence'
                        store.event(s['id'],dict(kind='delivery',decision_id=d['id'],index=index,delivered=active,
                            generation_latency_ms=0,reading_exposure_ms=7000 if active else 0,early_attempts=0))
                        base,probabilities,effect=actor.distribution(ev,d.get('intervention') if active else None)
                        choice=select(probabilities,uniform(env.seed,'choice',index))
                        if uniform(env.seed,'omission',index)<effect['omission_probability']:choice='NO_RESPONSE'
                        fb=env.outcome(ev,choice);store.event(s['id'],fb);actor.observe(ev,fb)
                        trials.append({'index':index,'baseline_probabilities':base,'assisted_probabilities':probabilities,'effect':effect,
                            'choice':choice,'outcome':fb['outcome'],'decision_id':d['id'],'intervention':d.get('intervention'),
                            'evaluator_state':env.evaluator_state()})
                    completed=count==s['total_trials'];require(bool(env.done)==completed,'Environment completion disagrees with protocol')
                    metrics=env.metrics()
                    for name in study['execution'][task]['metrics']:
                        from .records import number
                        require(name in metrics and number(metrics[name]),'Environment omitted a declared numeric outcome metric')
                    store.finish(s['id'],{'completed':completed})
                    report['runs'].append({'participant':spec['id'],'repeat':repeat,'task':task,'condition':condition,'session_id':s['id'],
                        'environment_seed':environment_seed,'completed':completed,'metrics':metrics,'trials':trials})
                    if on_progress:on_progress(spec['id'],task,condition,repeat)
    report['paired_comparisons']=[]
    for row in report['runs']:
        if row['condition']=='A' or not row['completed']:continue
        baseline=next((b for b in report['runs'] if b['participant']==row['participant'] and b['task']==row['task'] and b['repeat']==row['repeat'] and b['condition']=='A'),None)
        if baseline is None:continue
        deltas={name:row['metrics'][name]-baseline['metrics'][name] for name in study['execution'][row['task']]['metrics']}
        report['paired_comparisons'].append({'participant':row['participant'],'task':row['task'],'repeat':row['repeat'],
            'condition':row['condition'],'metric_deltas_from_A':deltas,
            'notice':'Descriptive paired difference under the specified response assumptions; repetitions are not new participants.'})
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--participants',required=True,help='JSON array of supported task-policy parameter specifications')
    parser.add_argument('--data-dir',required=True);parser.add_argument('--output',required=True,help='Separate researcher/evaluator JSON; never serve as participant evidence')
    parser.add_argument('--study',help='JSON study configuration of registered environments, protocols, calibrations and conditions')
    parser.add_argument('--scenario',choices=SCENARIOS,default='null');parser.add_argument('--protocol',default='short')
    parser.add_argument('--seed',default='comparison');parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--max-trials',type=int)
    parser.add_argument('--calibration-only',action='store_true',help='Generate unassisted calibrations for the known-pseudonym selector without comparison runs')
    parser.add_argument('--reconsideration',choices=MECHANISMS,default='current',help='Researcher-side Socratic processing assumption; direct assistance is unaffected')
    args=parser.parse_args();os.environ.update(SOCRATIC_LLM='offline',SOCRATIC_LANGUAGE_MODE='bounded',SOCRATIC_INTERPRET_RESPONSES='0')
    from .store import Store
    participants=json.loads(Path(args.participants).read_text())
    study=json.loads(Path(args.study).read_text()) if args.study else None
    result=run(Store(Path(args.data_dir)/'sessions.sqlite3'),participants,args.scenario,args.protocol,args.seed,args.repeats,args.max_trials,
        lambda participant,task,condition,repeat:print(participant,task,condition,repeat,'ready',flush=True),study=study,calibration_only=args.calibration_only,reconsideration=args.reconsideration)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Wrote conditional simulation results to',path)

if __name__=='__main__':main()
