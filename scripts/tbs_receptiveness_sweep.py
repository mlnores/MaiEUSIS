#!/usr/bin/env python3
"""Fresh matched TBS receptiveness pilot with independent unassisted controls."""
import argparse
import copy
import hashlib
import json
import os
import resource
import signal
import sqlite3
import subprocess
import sys
import time
from collections import deque
from contextlib import ExitStack
from pathlib import Path
from statistics import mean, stdev

import pilot_parallel as parallel
from socratic_prototype import pilot
from socratic_prototype.agents import Participant
from socratic_prototype.simulation import Environment, select, uniform
from socratic_prototype.records import require

VERSION='tbs-receptiveness-sweep-0.1'
LEVELS=('0.25','0.5','0.75')
CONDITIONS=('A','C','E','D','F')
ASSISTED=('C','E','D','F')
PROFILES=('MAB-specialised','TBS-specialised','Dual-regime','Low-expression')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity():
    return {p.name:sha(p) for p in (Path(__file__),Path(parallel.__file__))}


def baseline_rollout(actor, seed, repeat, protocol):
    """Independent full A trajectory; no graph, language or assistance is invoked."""
    stream=f'{seed}:rep:{repeat}:{actor["id"]}:0:TBS'
    model=Participant(actor,'TBS','null');env=Environment('TBS',protocol,stream)
    choices=[];distributions=[];misses=0
    for index in range(1,env.total+1):
        ev=env.evaluation('baseline_audit',index)
        base,p,effect=model.distribution(ev,None)
        require(base==p,'Unassisted reconstruction changed baseline preferences')
        choice=select(p,uniform(stream,'choice',index))
        if uniform(stream,'omission',index)<effect['omission_probability']:choice='NO_RESPONSE';misses+=1
        fb=env.outcome(ev,choice);model.observe(ev,fb)
        choices.append((index,choice,fb['outcome']));distributions.append(p)
    require(env.done,'Incomplete independent baseline')
    return {'trajectory_sha256':pilot.fingerprint(choices),'distribution_sha256':pilot.fingerprint(distributions),
            'primary_value':env.metrics()['targets_attained']/24,
            'score':env.metrics()['score'],'targets_attained':env.metrics()['targets_attained'],
            'blocks_completed':len(env.metrics()['blocks']),'trials':env.total,'omissions':misses,'environment_seed':stream}


def check_baseline(actual,expected):
    for key in ('trajectory_sha256','distribution_sha256','primary_value','score','targets_attained','blocks_completed','trials','omissions'):
        require(actual[key]==expected[key],f'Matched A baseline differs: {key}')


def read_hashed_manifest(path):
    data=pilot.read(path)
    require(pilot.fingerprint({k:v for k,v in data.items() if k!='sha256'})==data['sha256'],'Reference manifest changed')
    return data


def audit_baselines(actors,config):
    """Replay each actor/repetition without invoking graph or intervention code."""
    expected=[{'participant':a['id'],'repeat':r,
               **baseline_rollout(a,config['seed'],r,config['study']['tasks']['TBS']['protocol'])}
              for a in actors for r in range(config['repeats'])]
    return {'verified':True,'independent_full_trajectories':len(expected),'expected':expected,
            'notice':'Independent unassisted controls only. No historical sessions are reused or pooled.'}


def prepare(root, config_path=None, verify_controls=False):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    path=root/'manifest.json'
    if not path.exists():
        require(config_path is not None,'A new sweep requires --config')
        require(not any(p.name!='.runner.lock' for p in root.iterdir()),'Use an empty directory for a new TBS sweep')
        config_path=Path(config_path).resolve();spec=pilot.read(config_path)
        template_path=(config_path.parent/spec['template']).resolve();template=pilot.read(template_path)
        template['participants_file']=str((template_path.parent/template['participants_file']).resolve())
        config,_=pilot.validate_config(template)
        require(set(config['study']['tasks'])=={'TBS'} and config['study']['tasks']['TBS']['calibration_tasks']==['TBS'],
                'TBS sweep must be TBS-only with TBS calibration')
        require(config['study']['tasks']['TBS']['protocol']=='full' and not config.get('max_trials'),
                'Scientific fair sweep requires the full protocol without a trial cap')
        require(tuple(map(str,spec['levels']))==LEVELS,'Use receptiveness 0.25, 0.5 and 0.75')
        actors=pilot.select_actors(config,pilot.read(config['participants_file']))
        require(config['primary_outcomes']=={'TBS':{'metric':'targets_attained','divisor':24}},
                'Primary outcome must be targets attained / 24 blocks')
        require(config['cohort_split']=='development' and config['expected_participants']==16 and
                config['repeats']==3 and config['expected_profiles']=={p:4 for p in PROFILES},
                'Use the 16 development actors, four per original group, and three repetitions')
        audit=audit_baselines(actors,config)
        pilot.write(root/'baseline_audit.json',audit)
        entries={}
        for level in LEVELS:
            c=copy.deepcopy(config);c['id']=spec['id']+'-r'+level.replace('.','')
            c['response_parameters']['responsiveness']=float(level)
            require(all(c['response_parameters'][k]==0 for k in ('reactance','distraction','omission_probability')),
                    'This sensitivity experiment requires zero extra interference costs')
            file=root/f'config_{level}.json';pilot.write(file,c)
            directory=root/'runs'/('r'+level.replace('.',''))
            with pilot.lock(directory):m,_,_=pilot.prepare(directory,file)
            entries[level]={'directory':str(directory.relative_to(root)),'manifest_sha256':m['sha256']}
        manifest={'version':VERSION,'id':spec['id'],'created_at_utc':parallel.timestamp(),'implementation':identity(),
                  'levels':entries,'baseline_audit_sha256':sha(root/'baseline_audit.json'),
                  'assumptions':['All A/C/E/D/F sessions and TBS calibrations are fresh; no assisted historical outcomes are reused.',
                    'Same 16 development actors, three matched repetitions, seeds and full TBS protocols at each level.',
                    'One response rule; responsiveness is fixed and identical across styles/actors; other response coefficients are zero.',
                    'Unassisted trajectories are independently reconstructed before execution and checked against every fresh A.',
                    'New calibration profiles and full feedback are checked for equality across levels within each actor/repetition.',
                    'Repetitions are averaged within actors; the first-repetition preview is separately labelled.',
                    'These are structured synthetic response assumptions, not measured human effects or language comprehension.',
                    'TBS uses the provisional seven-feature state/feedback actor; original historical offers remain unavailable.',
                    'Exported offer_sensitivity=0 is retained; fresh offers and targets are independently uniform as in the task generator.',
                    'Direct responses target the recommended option; Socratic responses reweight SAFE/RISKY using displayed task evidence and goals.',
                    'Primary outcome is targets attained / 24 blocks; completed-block multiplied score is secondary.',
                    'Synthetic exposure is 7000 ms; no explicit helpfulness/burden reports or language understanding are simulated.']}
        manifest['sha256']=pilot.fingerprint(manifest);pilot.write(path,manifest)
    manifest=read_hashed_manifest(path)
    require(manifest['implementation']==identity(),'TBS-sweep coordinator changed; retain the recorded runtime')
    require(sha(root/'baseline_audit.json')==manifest['baseline_audit_sha256'],'Frozen baseline audit changed')
    audit=pilot.read(root/'baseline_audit.json');require(audit['verified'],'Independent baseline audit failed')
    levels={};actors=None;base=None
    for level,item in manifest['levels'].items():
        directory=root/item['directory'];m,selected,_=pilot.prepare(directory)
        require(m['sha256']==item['manifest_sha256'],'Level manifest changed')
        c=m['configuration']
        if actors is None:actors=selected;base=copy.deepcopy(c);base['id']=None;base['response_parameters']['responsiveness']=None
        comparable=copy.deepcopy(c);comparable['id']=None;comparable['response_parameters']['responsiveness']=None
        require(comparable==base and selected==actors and c['response_parameters']['responsiveness']==float(level),
                'Unmatched level configuration or actor inputs')
        levels[level]={'directory':directory,'manifest':m,'actors':selected,'results':pilot.finished_results(directory,m)}
    require(set(levels)==set(LEVELS),'Incomplete receptiveness grid')
    if verify_controls:
        expected=audit_baselines(actors,next(iter(levels.values()))['manifest']['configuration'])
        require(expected==audit,'Independent baseline replay differs from the frozen audit')
    return manifest,audit,actors,levels


def calibration_signature(report,database):
    session=next(c['session_id'] for c in report['calibrations'] if c['task']=='TBS')
    with sqlite3.connect(f'file:{database}?mode=ro',uri=True) as connection:
        body=json.loads(connection.execute('SELECT body FROM sessions WHERE id=?',(session,)).fetchone()[0])
    profile=copy.deepcopy(body['profile'])
    evidence=profile['policy'].get('evidence',[])
    require(all(e.startswith(session+'_trial_') for e in evidence),'Unexpected calibration evidence scope')
    if evidence:
        profile['policy']['evidence']=[int(e[len(session+'_trial_'):]) for e in evidence]
    inputs=[]
    for event in body['events']:
        value=copy.deepcopy(event['input'])
        if value['kind'] not in {'evaluation','feedback'}:continue
        require(value['trial_id']==session+'_trial_'+str(value['index']),'Unexpected calibration trial ID')
        value['trial_id']=value['index'];inputs.append(value)
    evaluations=[e for e in inputs if e['kind']=='evaluation']
    feedback=[e for e in inputs if e['kind']=='feedback']
    indices=list(range(1,193))
    require([e['index'] for e in evaluations]==indices and [e['index'] for e in feedback]==indices,
            'Incomplete or reordered TBS calibration')
    samples=sum(not e['timed_out'] for e in feedback)
    require(profile['policy']['samples']==samples and len(evidence)==samples,'Calibration sample count disagrees with observations')
    return {'profile_sha256':pilot.fingerprint(profile),'inputs_sha256':pilot.fingerprint(inputs),
            'completed_trials':len(feedback),'samples':samples}


def summarise(report,case,manifest):
    rows=pilot.summarise(report,case,manifest)
    for row,run in zip(rows,report['runs']):
        row.update(score=run['metrics']['score'],targets_attained=run['metrics']['targets_attained'],
                   blocks_completed=len(run['metrics']['blocks']))
    return rows


def verify_report(report,spec,expected):
    """Replay recorded actor probabilities, random draws, outcomes and block metrics.

    This checks numerical execution; it does not independently rerun graph inference.
    """
    require(len(report['runs'])==5 and {r['condition'] for r in report['runs']}==set(CONDITIONS),
            'Evaluator report is missing a condition')
    for run in report['runs']:
        require(run['task']=='TBS' and run['completed'] and len(run['trials'])==192 and
                run['environment_seed']==expected['environment_seed'],'Incomplete or unmatched evaluator run')
        model=Participant(spec,'TBS','responsive')
        env=Environment('TBS','full',run['environment_seed'])
        for index,trial in enumerate(run['trials'],1):
            require(trial['index']==index,'Reordered evaluator trials')
            ev=env.evaluation(run['session_id'],index)
            base,probabilities,effect=model.distribution(ev,trial['intervention'])
            require(base==trial['baseline_probabilities'] and probabilities==trial['assisted_probabilities'] and
                    effect==trial['effect'],'Actor probability/effect replay differs')
            choice=select(probabilities,uniform(env.seed,'choice',index))
            if uniform(env.seed,'omission',index)<effect['omission_probability']:choice='NO_RESPONSE'
            fb=env.outcome(ev,choice);model.observe(ev,fb)
            require(choice==trial['choice'] and fb['outcome']==trial['outcome'],'Keyed choice/outcome replay differs')
        require(env.done and env.metrics()==run['metrics'],'TBS block or score metrics differ on replay')
    return {'trial_choices_outcomes_and_distributions':5*192,'full_condition_metrics':5}


def verify_result(result,expected,full_trials=192):
    require(pilot.fingerprint({k:v for k,v in result.items() if k!='result_sha256'})==result['result_sha256'],'Committed result changed')
    require(len(result['rows'])==5 and {r['condition'] for r in result['rows']}==set(CONDITIONS),'Missing assistance conditions')
    require(all(r['task']=='TBS' and r['completed'] and r['trials']==full_trials and
                r['blocks_completed']==24 for r in result['rows']),'Incomplete TBS condition')
    require(all(r['primary_value']==r['targets_attained']/24 and 0<=r['targets_attained']<=24
                for r in result['rows']),'Incorrect target-attainment rate')
    a=next(r for r in result['rows'] if r['condition']=='A')
    require(a['baseline_control_passed'],'Unassisted preferences were changed')
    check_baseline(a,expected)
    require(result['calibration']['completed_trials']==full_trials,'Incomplete TBS calibration')
    require(0<=result['calibration']['samples']<=full_trials,'Invalid calibration sample count')
    require(result['numerical_replay']=={'trial_choices_outcomes_and_distributions':960,'full_condition_metrics':5},
            'Completed TBS job lacks numerical replay checks')


def worker(root,level,job,attempt,root_fd,level_fd):
    require(os.fstat(root_fd).st_ino==(root/'.runner.lock').stat().st_ino and
            os.fstat(level_fd).st_ino==(root/'runs'/('r'+level.replace('.',''))/'.runner.lock').stat().st_ino,
            'Worker must inherit both runner leases')
    manifest,audit,actors,levels=prepare(root)
    entry=levels[level];directory=entry['directory'];m=entry['manifest'];config=m['configuration']
    case,actor=next(x for x in pilot.jobs(m,actors) if x[0]['id']==job)
    require(attempt.parent==directory/'jobs'/job/'attempts' and attempt.is_dir(),'Invalid worker attempt')
    require(not (directory/'jobs'/job/'result.json').exists(),'Job already committed')
    status={'status':'running','pid':os.getpid(),'level':level,'job':case,'started_at_utc':parallel.timestamp()}
    pilot.write(attempt/'progress.json',status);began=time.monotonic()
    def progress(person,task,condition,repeat):
        pilot.write(attempt/'progress.json',{**status,'last_completed_session':condition,'elapsed_seconds':time.monotonic()-began})
    try:
        from socratic_prototype.store import Store
        spec=copy.deepcopy(actor);spec['response_parameters']={'TBS':{s:dict(config['response_parameters']) for s in ('direct','socratic')}}
        report=pilot.simulate(Store(attempt/'sessions.sqlite3'),[spec],scenario='responsive',
            seed=f'{config["seed"]}:rep:{case["repeat"]}',repeats=1,study=m['study'],on_progress=progress)
        expected=next(r for r in audit['expected'] if (r['participant'],r['repeat'])==(case['participant'],case['repeat']))
        replay=verify_report(report,spec,expected)
        pilot.write(attempt/'evaluator.json',report)
        result={'job_id':job,'case':case,'level':level,'manifest_sha256':m['sha256'],
                'report_file':str((attempt/'evaluator.json').relative_to(directory)),
                'report_sha256':sha(attempt/'evaluator.json'),'elapsed_seconds':time.monotonic()-began,
                'rows':summarise(report,case,m),'calibration':calibration_signature(report,attempt/'sessions.sqlite3'),
                'numerical_replay':replay,
                'max_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)}
        result['summary_sha256']=pilot.fingerprint(result['rows']);result['result_sha256']=pilot.fingerprint(result)
        verify_result(result,expected)
        require(m['implementation']==pilot.implementation() and manifest['implementation']==identity(),'Frozen software changed during job')
        pilot.write(directory/'jobs'/job/'result.json',result)
        pilot.write(attempt/'progress.json',{**status,'status':'complete','elapsed_seconds':result['elapsed_seconds']})
    except BaseException as error:
        pilot.write(attempt/'progress.json',{**status,'status':'interrupted' if isinstance(error,KeyboardInterrupt) else 'failed','error':str(error)})
        raise


def analyse(root,manifest,audit,actors,levels):
    expected={(r['participant'],r['repeat']):r for r in audit['expected']};index={};calibrations={};checks=0
    for level,entry in levels.items():
        for result in entry['results']:
            case=result['case'];key=(case['participant'],case['repeat'])
            verify_result(result,expected[key]);checks+=1
            for row in result['rows']:index[(key[0],key[1],level,row['condition'])]=row
            if key in calibrations:require(calibrations[key]==result['calibration'],'Calibration differs across receptiveness levels')
            calibrations[key]=result['calibration']
    repeats=next(iter(levels.values()))['manifest']['configuration']['repeats']
    def summaries(repetitions):
        people=[a for a in actors if all((a['id'],r,level,c) in index for r in repetitions for level in LEVELS for c in CONDITIONS)]
        rows=[];groups=[]
        for actor in people:
            p=actor['id']
            for level in LEVELS:
                for c in ASSISTED:
                    chosen=[index[p,r,level,c] for r in repetitions];base=[index[p,r,level,'A'] for r in repetitions]
                    deltas=[a['primary_value']-b['primary_value'] for a,b in zip(chosen,base)]
                    rows.append({'participant':p,'profile':actor['original_profile'],'condition':c,'receptiveness':float(level),
                         'repetitions':len(deltas),'mean_delta':mean(deltas),'repetition_deltas':deltas,
                         'monte_carlo_se':stdev(deltas)/len(deltas)**.5 if len(deltas)>1 else None,
                         'mean_target_rate':mean(x['primary_value'] for x in chosen),'baseline':mean(x['primary_value'] for x in base),
                         'mean_delta_pp':100*mean(deltas),'mean_score':mean(x['score'] for x in chosen),
                         'baseline_score':mean(x['score'] for x in base),
                         'repetition_score_deltas':[a['score']-b['score'] for a,b in zip(chosen,base)],
                         'mean_score_delta':mean(a['score']-b['score'] for a,b in zip(chosen,base)),
                         'mean_interventions':mean(x['active_interventions'] for x in chosen)})
        for profile in (*PROFILES,'all'):
            for level in LEVELS:
                for c in ASSISTED:
                    values=[r['mean_delta'] for r in rows if r['condition']==c and r['receptiveness']==float(level) and
                            (profile=='all' or r['profile']==profile)]
                    selected=[r for r in rows if r['condition']==c and r['receptiveness']==float(level) and
                              (profile=='all' or r['profile']==profile)]
                    if values:groups.append({'profile':profile,'condition':c,'receptiveness':float(level),'participants':len(values),
                         'repetitions':len(repetitions),'mean_delta':mean(values),'mean_delta_pp':100*mean(values),'better':sum(v>0 for v in values),
                         'same':sum(v==0 for v in values),'worse':sum(v<0 for v in values),
                         'mean_target_rate':mean(r['mean_target_rate'] for r in selected),
                         'baseline':mean(r['baseline'] for r in selected),
                         'mean_score':mean(r['mean_score'] for r in selected),
                         'baseline_score':mean(r['baseline_score'] for r in selected),
                         'mean_score_delta':mean(r['mean_score_delta'] for r in selected),
                         'mean_interventions':mean(r['mean_interventions'] for r in selected)})
        return {'participants':[a['id'] for a in people],'individual_results':rows,'groups':groups}
    jobs=sum(len(v['results']) for v in levels.values());planned=len(actors)*repeats*len(LEVELS)
    report={'version':VERSION,'manifest_sha256':manifest['sha256'],'updated_at_utc':parallel.timestamp(),
            'task':'TBS','primary_outcome':{'metric':'targets_attained','divisor':24,'unit':'proportion',
                                          'display_delta_unit':'percentage-points','direction':'maximize'},
            'secondary_outcome':{'metric':'score','unit':'multiplied-points','direction':'maximize'},
            'completed_jobs':jobs,'total_jobs':planned,'execution_complete':jobs==planned,
            'baseline_checks_passed':checks,'calibration_cross_level_checks':jobs-len(calibrations),
            'independent_baseline_trajectories':audit['independent_full_trajectories'],'control_checks_passed':True,
            **summaries(range(repeats)),'first_repetition':summaries([0]),
            'notice':'Fresh A/C/E/D/F, one task-owned response rule, full 192-trial TBS protocols. Independent A controls; no historical outcomes are pooled. Primary outcome: target-attainment rate over 24 blocks; score is secondary. Repetitions are averaged within actors.'}
    report['complete']=report['execution_complete'] and len(report['participants'])==len(actors)
    pilot.write(root/'analysis.json',report)
    lines=['# TBS receptiveness comparison','',report['notice'],'',f'Jobs: {jobs}/{planned}; matched actors: {len(report["participants"])}/{len(actors)}.',
           f'Baseline checks: {checks}; cross-level calibration checks: {report["calibration_cross_level_checks"]}.','',
           '| Profile | Receptiveness | Condition | Actors | Target attainment change from A (pp) | Worse than A |',
           '| --- | ---: | --- | ---: | ---: | ---: |']
    for row in report['groups']:lines.append(f'| {row["profile"]} | {row["receptiveness"]} | {row["condition"]} | {row["participants"]} | {row["mean_delta_pp"]:+.2f} | {row["worse"]} |')
    (root/'analysis.md').write_text('\n'.join(lines)+'\n')
    return report


def execute(root,config_path,workers,poll=2,prepare_only=False):
    require(1<=workers<=(os.cpu_count() or 1),'Use at most the detected CPU count')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        root_fd=stack.enter_context(parallel.lease(root/'.runner.lock'))
        manifest,audit,actors,levels=prepare(root,config_path,verify_controls=True)
        fds={level:stack.enter_context(parallel.lease(entry['directory']/'.runner.lock')) for level,entry in levels.items()}
        analysis=analyse(root,manifest,audit,actors,levels)
        if prepare_only:return analysis
        ordered=parallel.ordered_jobs(levels['0.25']['manifest'],actors)
        complete={(level,r['job_id']) for level,v in levels.items() for r in v['results']}
        pending=deque((level,case) for case,_ in ordered for level in LEVELS if (level,case['id']) not in complete)
        active={};failures=[];stop=False;error=None;start=time.monotonic();initial=len(complete)
        launch={'pid':os.getpid(),'workers':workers,'started_at_utc':parallel.timestamp(),'manifest_sha256':manifest['sha256']}
        pilot.write(root/f'launch_{os.getpid()}.json',launch)
        def publish(state):
            entries=[]
            for (level,job),info in active.items():
                path=info['attempt']/'progress.json'
                entries.append(pilot.read(path) if path.exists() else {'status':'starting','level':level,'job':info['case'],'pid':info['process'].pid})
            elapsed=time.monotonic()-start;done=len(complete)-initial
            pilot.write(root/'status.json',{'status':state,'pid':os.getpid(),'workers':workers,'active_jobs':entries,
                'completed_jobs':len(complete),'total_jobs':analysis['total_jobs'],'per_level':{k:len(v['results']) for k,v in levels.items()},
                'baseline_checks_passed':analysis['baseline_checks_passed'],'independent_baseline_trajectories':audit['independent_full_trajectories'],
                'calibration_cross_level_checks':analysis['calibration_cross_level_checks'],'control_checks_passed':error is None and not failures,
                'updated_at_utc':parallel.timestamp(),'failures':failures,'error':error,'elapsed_seconds':elapsed,
                'observed_jobs_per_hour':done/elapsed*3600 if done else None,
                'estimated_remaining_hours':(analysis['total_jobs']-len(complete))*elapsed/done/3600 if done else None})
        try:
            while pending or active:
                stop=stop or (root/'stop-after-jobs.json').exists()
                while pending and len(active)<workers and not stop:
                    require(identity()==manifest['implementation'],'Coordinator source changed')
                    level,case=pending.popleft();directory=levels[level]['directory'];attempt=parallel.next_attempt(directory,case)
                    with (attempt/'worker.log').open('ab',buffering=0) as log:
                        process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'--output-dir',str(root),
                            '--worker-level',level,'--worker-job',case['id'],'--worker-attempt',str(attempt),
                            '--root-fd',str(root_fd),'--level-fd',str(fds[level])],stdin=subprocess.DEVNULL,stdout=log,
                            stderr=subprocess.STDOUT,pass_fds=(root_fd,fds[level]))
                    active[level,case['id']]={'case':case,'attempt':attempt,'process':process}
                    print(f'Start rho={level} {case["participant"]} repeat={case["repeat"]} pid={process.pid}',flush=True)
                dirty=set()
                for key,info in list(active.items()):
                    code=info['process'].poll()
                    if code is None:continue
                    del active[key];level,job=key
                    if code or not (levels[level]['directory']/'jobs'/job/'result.json').exists():
                        failures.append({'level':level,'job_id':job,'returncode':code,'attempt':str(info['attempt'].relative_to(root))});stop=True
                    else:complete.add(key);dirty.add(level);print(f'Complete rho={level} {job}; {len(complete)}/{analysis["total_jobs"]}',flush=True)
                if dirty:
                    for level in dirty:levels[level]['results']=pilot.finished_results(levels[level]['directory'],levels[level]['manifest'])
                    analysis=analyse(root,manifest,audit,actors,levels)
                publish('stopping' if stop else 'running')
                if stop and not active:break
                if active:time.sleep(poll)
            require(not failures,'Worker failed; inspect worker.log before resuming')
            analysis=analyse(root,manifest,audit,actors,levels)
            publish('complete' if analysis['complete'] else 'incomplete')
        except BaseException as exc:
            error=str(exc) or type(exc).__name__
            for info in active.values():
                if info['process'].poll() is None:info['process'].send_signal(signal.SIGINT)
            for info in active.values():info['process'].wait()
            active.clear();publish('interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed');raise
        pilot.write(root/f'launch_{os.getpid()}.json',{**launch,'finished_at_utc':parallel.timestamp(),'elapsed_seconds':time.monotonic()-start})
        return analysis


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=os.cpu_count() or 1);parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--worker-level');parser.add_argument('--worker-job');parser.add_argument('--worker-attempt',type=Path)
    parser.add_argument('--root-fd',type=int);parser.add_argument('--level-fd',type=int)
    args=parser.parse_args();root=args.output_dir.resolve()
    if args.worker_level:worker(root,args.worker_level,args.worker_job,args.worker_attempt.resolve(),args.root_fd,args.level_fd)
    else:execute(root,args.config,args.workers,prepare_only=args.prepare_only)


if __name__=='__main__':main()
