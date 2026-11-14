#!/usr/bin/env python3
"""One bounded process pool for a matched MAB receptiveness sensitivity study."""
import argparse
import hashlib
import json
import math
import os
import resource
import signal
import sqlite3
import subprocess
import sys
import time
from collections import Counter, deque
from contextlib import ExitStack
from pathlib import Path
from statistics import mean, stdev

import pilot_parallel as parallel
from socratic_prototype import pilot
from socratic_prototype.records import require

VERSION='mab-receptiveness-sweep-0.1'
LEVELS=('0.25','0.5','0.75')
PROFILES=('MAB-specialised','TBS-specialised','Dual-regime','Low-expression')
VARIANTS=(('C','current'),('E','current'),('D','current'),('F','current'),('D','recent'),('F','recent'))


def identity():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),Path(parallel.__file__))}


def prepare(root,config_file=None):
    manifest_file=root/'manifest.json'
    if manifest_file.exists():
        manifest=pilot.read(manifest_file)
        require(pilot.fingerprint({k:v for k,v in manifest.items() if k!='sha256'})==manifest['sha256'],'Sweep manifest changed')
        require(manifest['implementation']==identity(),'Sweep scheduler changed while frozen')
    else:
        require(config_file is not None,'A new sweep requires --config')
        config_file=Path(config_file).resolve();config=pilot.read(config_file)
        reference=(config_file.parent/config['reference_dir']).resolve()
        levels={}
        for key,filename in {**config['levels'],'bridge':config['bridge']}.items():
            file=(config_file.parent/filename).resolve();directory=root/('bridge_050' if key=='bridge' else 'runs/r'+key.replace('.',''))
            with pilot.lock(directory):
                m,_,_=pilot.prepare(directory,file)
            levels[key]={'directory':str(directory.relative_to(root)),'manifest_sha256':m['sha256']}
        ref,actors,_=pilot.prepare(reference);results=pilot.finished_results(reference,ref)
        require(pilot.read(reference/'analysis.json')['complete'] or
                (config.get('engineering') is True and ref['configuration'].get('max_trials') and
                 len(results)==len(list(pilot.jobs(ref,actors)))), 'Reference pilot must be complete')
        manifest={'version':VERSION,'created_at_utc':parallel.timestamp(),'id':config['id'],
                  'reference_dir':str(reference),'reference_manifest_sha256':ref['sha256'],
                  'reference_reports':{r['job_id']:r['report_sha256'] for r in results},'levels':levels,
                  'implementation':identity(),'engineering':bool(config.get('engineering',False)),'assumptions':[
                      'MAB only: full configured protocol, task-specific MAB calibration, no TBS simulation.',
                      'All three processing mechanisms and five assistance conditions are retained.',
                      'The same actor, repeat and mechanism use identical random keys across receptiveness levels.',
                      'Responsiveness is fixed within runs and equal for direct/Socratic assistance and all actors.',
                      'The completed 0.5 MAB records are reused only after full-protocol MAB-only bridge verification.',
                      'No source cohort, original profile, fitted parameter or held-out evaluation split is changed.',
                      'Matched repetitions are averaged within actors; repeated runs are not new people.']}
        manifest['sha256']=pilot.fingerprint(manifest);pilot.write(manifest_file,manifest)
    reference=Path(manifest['reference_dir']);ref,actors,_=pilot.prepare(reference)
    require(ref['sha256']==manifest['reference_manifest_sha256'],'Reference manifest changed')
    reference_results=pilot.finished_results(reference,ref)
    require({r['job_id']:r['report_sha256'] for r in reference_results}==manifest['reference_reports'],'Reference reports changed')
    require(set(manifest['levels'])=={'0.25','0.75','bridge'},'Unexpected sweep levels')
    levels={}
    for key,item in manifest['levels'].items():
        directory=root/item['directory'];m,selected,_=pilot.prepare(directory)
        require(m['sha256']==item['manifest_sha256'],'Level manifest changed')
        c=m['configuration'];base=ref['configuration']
        require(set(c['study']['tasks'])=={'MAB'} and c['study']['tasks']['MAB']['calibration_tasks']==['MAB'],'Sweep must be MAB-only')
        require(c['seed']==base['seed'] and c['study']['tasks']['MAB']['protocol']==base['study']['tasks']['MAB']['protocol'],'Unmatched seed or protocol')
        require(c['response_parameters']=={**base['response_parameters'],'responsiveness':.5 if key=='bridge' else float(key)},'Unexpected response coefficients')
        require(all(a in actors for a in selected),'Sweep actors differ from reference')
        require(key=='bridge' or (selected==actors and c['repeats']==base['repeats']),'Unmatched actors/repetitions')
        levels[key]={'directory':directory,'manifest':m,'actors':selected,
                     'results':pilot.finished_results(directory,m)}
    return manifest,ref,actors,reference_results,levels


def bridge_check(reference,reference_results,bridge):
    if len(bridge['results'])!=len(list(pilot.jobs(bridge['manifest'],bridge['actors']))):
        return {'verified':False,'comparisons':0,'calibrations':0}
    signature=pilot.fingerprint(sorted((r['job_id'],r['report_sha256']) for r in bridge['results']))
    if bridge.get('_verification_signature')==signature:
        return bridge['_verification']
    originals={r['job_id']:r for r in reference_results};count=calibrations=0
    for result in bridge['results']:
        old=originals[result['job_id']];before={r['condition']:r for r in old['rows'] if r['task']=='MAB'}
        for row in result['rows']:
            require(all(row[k]==before[row['condition']][k] for k in
                        ('primary_value','trajectory_sha256','distribution_sha256','active_interventions','omissions')),
                    'MAB-only 0.5 bridge differs from the completed reference')
            count+=1
        profiles=[]
        for directory,record in [(reference,old),(bridge['directory'],result)]:
            report_file=directory/record['report_file'];full=pilot.read(report_file)
            session=next(c['session_id'] for c in full['calibrations'] if c['task']=='MAB')
            with sqlite3.connect(f'file:{report_file.parent/"sessions.sqlite3"}?mode=ro',uri=True) as connection:
                profile,events=connection.execute("SELECT json_extract(body,'$.profile'),json_extract(body,'$.events') FROM sessions WHERE id=?",(session,)).fetchone()
            profile=json.loads(profile)
            require(all(x.startswith(session+'_trial_') for x in profile['evidence']),'Unexpected calibration evidence scope')
            profile['evidence']=[int(x[len(session+'_trial_'):]) for x in profile['evidence']]
            feedback=[tuple(e['input'][k] for k in ('index','choice','outcome','timed_out','score_after'))
                      for e in json.loads(events) if e['input']['kind']=='feedback']
            profiles.append((profile,feedback))
        require(profiles[0]==profiles[1],'MAB-only calibration profile differs from reference')
        calibrations+=1
    result={'verified':True,'comparisons':count,'calibrations':calibrations}
    bridge['_verification_signature']=signature;bridge['_verification']=result
    return result


def analyse(root,manifest,reference_results,levels,actors):
    refrows=[{**row,'receptiveness':.5} for result in reference_results for row in result['rows'] if row['task']=='MAB']
    rows=refrows+[dict(row,receptiveness=float(level)) for level in ('0.25','0.75') for result in levels[level]['results'] for row in result['rows']]
    index={(r['participant'],r['repeat'],r['mechanism'],r['condition'],str(r['receptiveness'])):r for r in rows}
    cross=no_revision=matched_baselines=0
    for person,repeat in sorted({(r['participant'],r['repeat']) for r in rows}):
        for level in LEVELS:
            for condition in ('A','C','E'):
                matched=[index.get((person,repeat,m,condition,level)) for m in ('none','current','recent')]
                if all(matched):
                    require(len({(r['primary_value'],r['trajectory_sha256'],r['distribution_sha256']) for r in matched})==1,'Cross-mechanism control failed')
                    cross+=1
            baseline=index.get((person,repeat,'none','A',level))
            for condition in ('D','F'):
                row=index.get((person,repeat,'none',condition,level))
                if baseline and row:
                    require(all(row[k]==baseline[k] for k in ('primary_value','trajectory_sha256','distribution_sha256')),'No-revision control failed')
                    no_revision+=1
        for level in ('0.25','0.75'):
            for mechanism in ('none','current','recent'):
                row=index.get((person,repeat,mechanism,'A',level));base=index.get((person,repeat,mechanism,'A','0.5'))
                if row and base:
                    require(all(row[k]==base[k] for k in ('primary_value','trajectory_sha256','distribution_sha256')),'Unassisted baseline differs across receptiveness levels')
                    matched_baselines+=1
    bridge=bridge_check(Path(manifest['reference_dir']),reference_results,levels['bridge'])
    repeats=levels['0.25']['manifest']['configuration']['repeats']
    def summaries(repetitions):
        people=[a for a in actors if bridge['verified'] and all(
            index.get((a['id'],r,m,c,level),{}).get('completed',False)
            for r in repetitions for m in ('none','current','recent') for c in ('A','C','E','D','F') for level in LEVELS)]
        individual=[]
        for actor in people:
            for level in LEVELS:
                for condition,mechanism in VARIANTS:
                    chosen=[index[(actor['id'],r,mechanism,condition,level)] for r in repetitions]
                    base=[index[(actor['id'],r,mechanism,'A',level)] for r in repetitions]
                    deltas=[r['primary_value']-a['primary_value'] for r,a in zip(chosen,base)]
                    individual.append({'participant':actor['id'],'profile':actor['original_profile'],
                        'receptiveness':float(level),'condition':condition,'mechanism':mechanism,
                        'repetitions':len(repetitions),'mean_delta':mean(deltas),'mean_score':mean(r['primary_value'] for r in chosen),
                        'baseline':mean(r['primary_value'] for r in base),'repetition_deltas':deltas,
                        'monte_carlo_se':stdev(deltas)/len(deltas)**.5 if len(deltas)>1 else None,
                        'mean_interventions':mean(r['active_interventions'] for r in chosen)})
        groups=[]
        for profile in (*PROFILES,'all'):
            for level in LEVELS:
                for condition,mechanism in VARIANTS:
                    values=[r for r in individual if r['receptiveness']==float(level) and r['condition']==condition and
                            r['mechanism']==mechanism and (profile=='all' or r['profile']==profile)]
                    if values:
                        effects=[r['mean_delta'] for r in values]
                        groups.append({'profile':profile,'receptiveness':float(level),'condition':condition,'mechanism':mechanism,
                            'participants':len(values),'repetitions':len(repetitions),'mean_delta':mean(effects),
                            'better':sum(x>0 for x in effects),'same':sum(x==0 for x in effects),'worse':sum(x<0 for x in effects)})
        return {'participants':[a['id'] for a in people],'individual_results':individual,'groups':groups}
    main=summaries(range(repeats));preview=summaries([0])
    planned=sum(len(list(pilot.jobs(v['manifest'],v['actors']))) for v in levels.values())
    completed=sum(len(v['results']) for v in levels.values())
    report={'version':VERSION,'manifest_sha256':manifest['sha256'],'updated_at_utc':parallel.timestamp(),
        'new_jobs_completed':completed,'new_jobs_planned':planned,'reused_reference_jobs':len(reference_results),
        'execution_complete':completed==planned,'complete':completed==planned and len(main['participants'])==len(actors),
        'bridge':bridge,'controls':{'cross_mechanism':cross,'no_revision':no_revision,'cross_level_baseline':matched_baselines},
        'control_checks_passed':True,**main,'first_repetition':preview,
        'notice':'Conditional synthetic MAB sensitivity study. All three processing mechanisms are retained. '
                 'Matched repetitions are averaged within actors before group means. Responsiveness is a '
                 'fixed mixture weight, not measured trust or probability of following a question. '
                 'The 0.5 MAB data are an explicitly verified reuse of the completed guided pilot.'}
    pilot.write(root/'analysis.json',report)
    lines=['# MAB receptiveness sensitivity','',report['notice'],'',
           f'New jobs: {completed}/{planned}. Reference 0.5 jobs: {len(reference_results)}. Bridge verified: {bridge["verified"]}.',
           f'Actors with all levels, repetitions and mechanisms: {len(main["participants"])}/{len(actors)}.','',
           '| Profile | Support | Mechanism | Receptiveness | Actors | Mean change from A | Worse than A |',
           '| --- | --- | --- | ---: | ---: | ---: | ---: |']
    for row in main['groups']:
        lines.append(f"| {row['profile']} | {row['condition']} | {row['mechanism']} | {row['receptiveness']} | {row['participants']} | {row['mean_delta']:+.2f} | {row['worse']} |")
    (root/'analysis.md').write_text('\n'.join(lines)+'\n')
    return report


def execute(root,config_file,workers,report_python=None,poll=2):
    require(workers>0 and workers<=os.cpu_count(),'Use between one and the detected CPU count of workers')
    root.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        root_fd=stack.enter_context(parallel.lease(root/'.runner.lock'))
        manifest,reference,actors,reference_results,levels=prepare(root,config_file)
        fds={key:stack.enter_context(parallel.lease(v['directory']/'.runner.lock')) for key,v in levels.items()}
        pending=[]
        for case,_ in parallel.ordered_jobs(levels['bridge']['manifest'],levels['bridge']['actors']):pending.append(('bridge',case))
        ordered=parallel.ordered_jobs(levels['0.25']['manifest'],actors)
        for case,_ in ordered:
            for key in ('0.25','0.75'):pending.append((key,case))
        completed={(key,r['job_id']) for key,v in levels.items() for r in v['results']}
        pending=deque((key,case) for key,case in pending if (key,case['id']) not in completed)
        analysis=analyse(root,manifest,reference_results,levels,actors)
        start=time.monotonic();initial=len(completed);active={};failures=[];stopping=False;error_message=None
        launch={'pid':os.getpid(),'workers':workers,'started_at_utc':parallel.timestamp(),'manifest_sha256':manifest['sha256'],
                'jobs_already_complete':initial,'report_python':report_python}
        pilot.write(root/f'launch_{os.getpid()}.json',launch)
        def publish(state):
            entries=[]
            for (key,job),info in active.items():
                path=info['attempt']/'progress.json'
                entry=pilot.read(path) if path.exists() else {'job':info['case'],'pid':info['process'].pid,'attempt':str(info['attempt'].relative_to(levels[key]['directory']))}
                entries.append({**entry,'level':key,'directory':str(levels[key]['directory'].relative_to(root))})
            elapsed=time.monotonic()-start;done=len(completed)-initial
            pilot.write(root/'status.json',{'status':state,'pid':os.getpid(),'workers':workers,'active_jobs':entries,
                'completed_jobs':len(completed),'total_jobs':analysis['new_jobs_planned'],'reused_05_jobs':len(reference_results),
                'bridge':analysis['bridge'],'control_checks_passed':error_message is None,
                'controls':analysis['controls'],'failures':failures,'error':error_message,
                'updated_at_utc':parallel.timestamp(),'elapsed_seconds':elapsed,
                'jobs_per_hour':done/elapsed*3600 if done else None,
                'estimated_remaining_hours':(analysis['new_jobs_planned']-len(completed))*elapsed/done/3600 if done else None})
        try:
            while pending or active:
                stopping=stopping or (root/'stop-after-jobs.json').exists()
                while pending and len(active)<workers and not stopping:
                    require(identity()==manifest['implementation'],'Sweep scheduler changed')
                    key,case=pending.popleft();directory=levels[key]['directory'];attempt=parallel.next_attempt(directory,case)
                    with (attempt/'worker.log').open('ab',buffering=0) as log:
                        process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'--output-dir',str(root),
                            '--worker-level',key,'--worker-job',case['id'],'--worker-attempt',str(attempt),'--lease-fd',str(fds[key])],
                            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,pass_fds=(root_fd,fds[key]))
                    active[(key,case['id'])]={'process':process,'attempt':attempt,'case':case}
                    print(f'Start level={key} {case["participant"]} repeat={case["repeat"]} {case["mechanism"]} pid={process.pid}',flush=True)
                dirty=set()
                for item,info in list(active.items()):
                    code=info['process'].poll()
                    if code is None:continue
                    key,job=item;del active[item]
                    if code or not (levels[key]['directory']/'jobs'/job/'result.json').exists():
                        failures.append({'level':key,'job_id':job,'returncode':code,'attempt':str(info['attempt'].relative_to(root))});stopping=True
                    else:completed.add(item);dirty.add(key);print(f'Complete {key}/{job}: {len(completed)}/{analysis["new_jobs_planned"]}',flush=True)
                if dirty:
                    for key in dirty:levels[key]['results']=pilot.finished_results(levels[key]['directory'],levels[key]['manifest'])
                    analysis=analyse(root,manifest,reference_results,levels,actors)
                publish('stopping' if stopping else 'running')
                if stopping and not active:break
                if active:time.sleep(poll)
            require(not failures,'Worker failure: inspect worker.log before resuming')
        except BaseException as error:
            error_message=str(error) or type(error).__name__
            for info in active.values():
                if info['process'].poll() is None:info['process'].send_signal(signal.SIGINT)
            for info in active.values():info['process'].wait()
            active.clear()
            publish('interrupted' if isinstance(error,KeyboardInterrupt) else 'failed');raise
        # Verify the reference again at the end; never change its frozen data.
        ref_results=pilot.finished_results(Path(manifest['reference_dir']),reference)
        require({r['job_id']:r['report_sha256'] for r in ref_results}==manifest['reference_reports'],'Reference changed during sweep')
        analysis=analyse(root,manifest,reference_results,levels,actors)
        publish('complete' if analysis['execution_complete'] else 'incomplete')
        if analysis['complete'] and report_python:
            subprocess.run([report_python,str(Path(__file__).with_name('mab_receptiveness_report.py')),'--directory',str(root)],check=True)
        pilot.write(root/f'launch_{os.getpid()}.json',{**launch,'finished_at_utc':parallel.timestamp(),'elapsed_seconds':time.monotonic()-start})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--config',type=Path)
    parser.add_argument('--workers',type=int,default=os.cpu_count());parser.add_argument('--report-python')
    parser.add_argument('--worker-level');parser.add_argument('--worker-job');parser.add_argument('--worker-attempt',type=Path)
    parser.add_argument('--lease-fd',type=int);args=parser.parse_args();root=args.output_dir.resolve()
    if args.worker_level:
        manifest=pilot.read(root/'manifest.json');require(manifest['implementation']==identity(),'Worker scheduler changed')
        level=root/manifest['levels'][args.worker_level]['directory']
        parallel.worker(level,args.worker_job,args.worker_attempt.resolve(),args.lease_fd)
        pilot.write(args.worker_attempt/'resources.json',{'max_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                                                        'pid':os.getpid(),'platform':sys.platform})
    else:execute(root,args.config,args.workers,args.report_python)


if __name__=='__main__':main()
