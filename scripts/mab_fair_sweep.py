#!/usr/bin/env python3
"""Fresh, matched MAB assistance comparisons with audited historical A controls."""
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

VERSION='mab-fair-sweep-0.1'
LEVELS=('0.25','0.5','0.75')
CONDITIONS=('A','C','E','D','F')
ASSISTED=('C','E','D','F')
PROFILES=('MAB-specialised','TBS-specialised','Dual-regime','Low-expression')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity():
    return {p.name:sha(p) for p in (Path(__file__),Path(parallel.__file__))}


def baseline_rollout(actor, seed, repeat, protocol):
    """Independent full A trajectory; no graph, language or assistance is invoked."""
    stream=f'{seed}:rep:{repeat}:{actor["id"]}:0:MAB'
    model=Participant(actor,'MAB','null');env=Environment('MAB',protocol,stream)
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
            'primary_value':env.metrics()['score'],'trials':env.total,'omissions':misses,'environment_seed':stream}


def check_baseline(actual,expected):
    for key in ('trajectory_sha256','distribution_sha256','primary_value','trials','omissions'):
        require(actual[key]==expected[key],f'Matched A baseline differs: {key}')


def read_hashed_manifest(path):
    data=pilot.read(path)
    require(pilot.fingerprint({k:v for k,v in data.items() if k!='sha256'})==data['sha256'],'Reference manifest changed')
    return data


def audit_reference(source, actors, config):
    """Verify old files read-only, then match every old A against a current rollout."""
    source=Path(source).resolve();grid=read_hashed_manifest(source/'manifest.json')
    require(pilot.read(source/'analysis.json')['complete'],'Historical sweep is incomplete')
    directories={'0.25':source/'runs/r025','0.5':Path(grid['reference_dir']),'0.75':source/'runs/r075'}
    expected={(a['id'],r):baseline_rollout(a,config['seed'],r,config['study']['tasks']['MAB']['protocol'])
              for a in actors for r in range(config['repeats'])}
    refs=[];seen=set()
    for level,directory in directories.items():
        m=read_hashed_manifest(directory/'manifest.json');old=pilot.read(directory/'participants.json')
        require(pilot.fingerprint(old)==m['actors_sha256'] and old==actors,'Historical actor inputs differ')
        c=m['configuration']
        require(c['seed']==config['seed'] and c['repeats']==config['repeats'] and
                c['study']['tasks']['MAB']['protocol']==config['study']['tasks']['MAB']['protocol'],'Historical seed/protocol/repetitions differ')
        for path in sorted((directory/'jobs').glob('*/result.json')):
            record=pilot.read(path);case=record['case']
            if case['mechanism']!='current':continue
            key=(case['participant'],case['repeat'])
            require(key in expected and (level,*key) not in seen,'Unexpected or duplicate historical baseline')
            require(record['manifest_sha256']==m['sha256'] and
                    pilot.fingerprint(record['rows'])==record['summary_sha256'],'Historical job summary changed')
            report=directory/record['report_file']
            require(sha(report)==record['report_sha256'],'Historical evaluator report changed')
            full=pilot.read(report);run=next(r for r in full['runs'] if r['task']=='MAB' and r['condition']=='A')
            row=next(r for r in record['rows'] if r['task']=='MAB' and r['condition']=='A')
            require(run['completed'] and row['completed'] and run['environment_seed']==expected[key]['environment_seed'],
                    'Incomplete or unmatched historical A stream')
            require(all(not t['effect'].get('applied',False) and t.get('intervention') is None and
                        t['baseline_probabilities']==t['assisted_probabilities'] for t in run['trials']),'Historical A contains assistance')
            require(row['trajectory_sha256']==pilot.fingerprint([(t['index'],t['choice'],t['outcome']) for t in run['trials']]) and
                    row['distribution_sha256']==pilot.fingerprint([t['assisted_probabilities'] for t in run['trials']]) and
                    row['primary_value']==run['metrics']['score'],'Historical A summary disagrees with its report')
            check_baseline(row,expected[key]);seen.add((level,*key))
            refs.append({'level':level,'participant':key[0],'repeat':key[1],
                         'manifest_file':str(directory/'manifest.json'),'manifest_sha256':sha(directory/'manifest.json'),
                         'result_file':str(path),'result_sha256':sha(path),'report_file':str(report),'report_sha256':sha(report)})
    require(len(seen)==len(expected)*len(LEVELS),'Missing historical baseline cases')
    return {'verified':True,'independent_full_trajectories':len(expected),'historical_A_checks':len(seen),
            'expected':[{'participant':p,'repeat':r,**value} for (p,r),value in sorted(expected.items())],
            'sources':refs,'notice':'Historical A is validation only. Every condition is executed fresh under the current software.'}


def verify_sources(audit):
    cache={}
    for item in audit['sources']:
        for kind in ('manifest','result','report'):
            path=item[kind+'_file']
            if path not in cache:cache[path]=sha(path)
            require(cache[path]==item[kind+'_sha256'],'Historical baseline source changed: '+path)


def prepare(root, config_path=None, verify_old=False):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    path=root/'manifest.json'
    if not path.exists():
        require(config_path is not None,'A new sweep requires --config')
        config_path=Path(config_path).resolve();spec=pilot.read(config_path)
        template_path=(config_path.parent/spec['template']).resolve();template=pilot.read(template_path)
        template['participants_file']=str((template_path.parent/template['participants_file']).resolve())
        config,_=pilot.validate_config(template)
        require(set(config['study']['tasks'])=={'MAB'} and config['study']['tasks']['MAB']['calibration_tasks']==['MAB'],
                'Fair sweep must be MAB-only with MAB calibration')
        require(config['study']['tasks']['MAB']['protocol']=='full' and not config.get('max_trials'),
                'Scientific fair sweep requires the full protocol without a trial cap')
        require(tuple(map(str,spec['levels']))==LEVELS,'Use receptiveness 0.25, 0.5 and 0.75')
        actors=pilot.select_actors(config,pilot.read(config['participants_file']))
        audit=audit_reference(config_path.parent/spec['historical_baselines'],actors,config)
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
                  'assumptions':['All A/C/E/D/F sessions and MAB calibrations are fresh; no assisted historical outcomes are reused.',
                    'Same 16 development actors, three matched repetitions, seeds and full MAB protocols at each level.',
                    'One response rule; responsiveness is fixed and identical across styles/actors; other response coefficients are zero.',
                    'Historical A trajectories are matched independently before execution and compared against every new A.',
                    'New calibration profiles and full feedback are checked for equality across levels within each actor/repetition.',
                    'Repetitions are averaged within actors; the first-repetition preview is separately labelled.',
                    'These are structured synthetic response assumptions, not measured human effects or language comprehension.']}
        manifest['sha256']=pilot.fingerprint(manifest);pilot.write(path,manifest)
    manifest=read_hashed_manifest(path)
    require(manifest['implementation']==identity(),'Fair-sweep coordinator changed; retain the recorded runtime')
    require(sha(root/'baseline_audit.json')==manifest['baseline_audit_sha256'],'Frozen baseline audit changed')
    audit=pilot.read(root/'baseline_audit.json');require(audit['verified'],'Historical baseline audit failed')
    if verify_old:verify_sources(audit)
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
    return manifest,audit,actors,levels


def calibration_signature(report,database):
    session=next(c['session_id'] for c in report['calibrations'] if c['task']=='MAB')
    with sqlite3.connect(f'file:{database}?mode=ro',uri=True) as connection:
        profile=json.loads(connection.execute("SELECT json_extract(body,'$.profile') FROM sessions WHERE id=?",(session,)).fetchone()[0])
        rows=connection.execute("SELECT json_extract(e.value,'$.input') FROM sessions s,json_each(s.body,'$.events') e "
             "WHERE s.id=? AND json_extract(e.value,'$.input.kind')='feedback'",(session,)).fetchall()
    require(all(e.startswith(session+'_trial_') for e in profile['evidence']),'Unexpected calibration evidence scope')
    profile['evidence']=[int(e[len(session+'_trial_'):]) for e in profile['evidence']]
    feedback=[tuple(json.loads(row[0])[k] for k in ('index','choice','outcome','timed_out','score_after')) for row in rows]
    return {'profile_sha256':pilot.fingerprint(profile),'feedback_sha256':pilot.fingerprint(feedback),
            'completed_trials':len(feedback),'samples':profile['samples']}


def verify_result(result,expected,full_trials=200):
    require(pilot.fingerprint({k:v for k,v in result.items() if k!='result_sha256'})==result['result_sha256'],'Committed result changed')
    require(len(result['rows'])==5 and {r['condition'] for r in result['rows']}==set(CONDITIONS),'Missing assistance conditions')
    require(all(r['task']=='MAB' and r['completed'] and r['trials']==full_trials for r in result['rows']),'Incomplete MAB condition')
    a=next(r for r in result['rows'] if r['condition']=='A')
    require(a['baseline_control_passed'],'Unassisted preferences were changed')
    check_baseline(a,expected)
    require(result['calibration']['completed_trials']==full_trials,'Incomplete MAB calibration')


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
        spec=copy.deepcopy(actor);spec['response_parameters']={'MAB':{s:dict(config['response_parameters']) for s in ('direct','socratic')}}
        report=pilot.simulate(Store(attempt/'sessions.sqlite3'),[spec],scenario='responsive',
            seed=f'{config["seed"]}:rep:{case["repeat"]}',repeats=1,study=m['study'],on_progress=progress)
        pilot.write(attempt/'evaluator.json',report)
        result={'job_id':job,'case':case,'level':level,'manifest_sha256':m['sha256'],
                'report_file':str((attempt/'evaluator.json').relative_to(directory)),
                'report_sha256':sha(attempt/'evaluator.json'),'elapsed_seconds':time.monotonic()-began,
                'rows':pilot.summarise(report,case,m),'calibration':calibration_signature(report,attempt/'sessions.sqlite3'),
                'max_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)}
        result['summary_sha256']=pilot.fingerprint(result['rows']);result['result_sha256']=pilot.fingerprint(result)
        expected=next(r for r in audit['expected'] if (r['participant'],r['repeat'])==(case['participant'],case['repeat']))
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
                         'mean_score':mean(x['primary_value'] for x in chosen),'baseline':mean(x['primary_value'] for x in base),
                         'mean_interventions':mean(x['active_interventions'] for x in chosen)})
        for profile in (*PROFILES,'all'):
            for level in LEVELS:
                for c in ASSISTED:
                    values=[r['mean_delta'] for r in rows if r['condition']==c and r['receptiveness']==float(level) and
                            (profile=='all' or r['profile']==profile)]
                    if values:groups.append({'profile':profile,'condition':c,'receptiveness':float(level),'participants':len(values),
                         'repetitions':len(repetitions),'mean_delta':mean(values),'better':sum(v>0 for v in values),
                         'same':sum(v==0 for v in values),'worse':sum(v<0 for v in values)})
        return {'participants':[a['id'] for a in people],'individual_results':rows,'groups':groups}
    jobs=sum(len(v['results']) for v in levels.values());planned=len(actors)*repeats*len(LEVELS)
    report={'version':VERSION,'manifest_sha256':manifest['sha256'],'updated_at_utc':parallel.timestamp(),
            'completed_jobs':jobs,'total_jobs':planned,'execution_complete':jobs==planned,
            'baseline_checks_passed':checks,'calibration_cross_level_checks':jobs-len(calibrations),
            'historical_baseline_checks':audit['historical_A_checks'],'control_checks_passed':True,
            **summaries(range(repeats)),'first_repetition':summaries([0]),
            'notice':'Fresh A/C/E/D/F, one response rule, full matched MAB protocols. Historical A validates baseline equivalence; historical assisted outcomes are not pooled. Repetitions are averaged within actors.'}
    report['complete']=report['execution_complete'] and len(report['participants'])==len(actors)
    pilot.write(root/'analysis.json',report)
    lines=['# Fair MAB receptiveness comparison','',report['notice'],'',f'Jobs: {jobs}/{planned}; matched actors: {len(report["participants"])}/{len(actors)}.',
           f'Baseline checks: {checks}; cross-level calibration checks: {report["calibration_cross_level_checks"]}.','',
           '| Profile | Receptiveness | Condition | Actors | Mean change from A | Worse than A |',
           '| --- | ---: | --- | ---: | ---: | ---: |']
    for row in report['groups']:lines.append(f'| {row["profile"]} | {row["receptiveness"]} | {row["condition"]} | {row["participants"]} | {row["mean_delta"]:+.2f} | {row["worse"]} |')
    (root/'analysis.md').write_text('\n'.join(lines)+'\n')
    return report


def execute(root,config_path,workers,poll=2,prepare_only=False):
    require(1<=workers<=(os.cpu_count() or 1),'Use at most the detected CPU count')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        root_fd=stack.enter_context(parallel.lease(root/'.runner.lock'))
        manifest,audit,actors,levels=prepare(root,config_path,verify_old=True)
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
                'baseline_checks_passed':analysis['baseline_checks_passed'],'historical_baseline_checks':audit['historical_A_checks'],
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
            verify_sources(audit)
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
