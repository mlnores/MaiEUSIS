"""Frozen researcher-side cohort bundles with distinct fit/evaluation roles."""
import copy
import json
import platform
from pathlib import Path
from collections import defaultdict
from statistics import mean
from . import VERSION
from .assumptions import procedure,assumptions,fingerprint,implementation_hashes
from .data import load_handover
from .fitting import fit_mab,fit_tbs
from .evaluation import predict,metrics,omission_rate,free_runs,recovery
from ..agents import validate_participant
from ..records import require


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n');temporary.replace(path)


def aggregate(rows):
    groups=defaultdict(list)
    for row in rows:groups[(row['task'],row['split'])].append(row)
    result=[]
    for (task,split),values in sorted(groups.items()):
        result.append({'task':task,'split':split,'participants':len(values),
            'test_choices':sum(v['eligible_test_choices'] for v in values),
            **{key:mean(v[key] for v in values if v[key] is not None) for key in ['mean_log_loss','mean_brier','uniform_log_loss','frequency_log_loss']},
            'participants_beating_frequency':sum(v['mean_log_loss']<v['frequency_log_loss'] for v in values),
            'test_missed_responses':sum(v['test_missed_responses'] for v in values),
            'test_unknown_choices':sum(v['test_unknown_choices'] for v in values)})
    return result


def actor_spec(person,models,omissions,role,freeze):
    return validate_participant({'id':person['id'],'source':'Empirical handover reconstruction; '+role+' parameters; TBS state/feedback policy is provisional.',
        'original_profile':person['original_profile'],'task_models':models,'baseline_omission':omissions,
        'provenance':{'version':VERSION,'source_id':person['source_id'],'split':person['split'],'parameter_role':role,
                      'frozen_procedure_sha256':freeze['sha256'],'assumptions_sha256':freeze['assumptions_sha256']}})


def build(source_dir,output_dir,random_starts=24,progress=print):
    import numpy,scipy
    output=Path(output_dir)
    require(not output.exists() or not any(output.iterdir()),'Use an empty output directory to preserve frozen bundles')
    require(type(random_starts) is int and random_starts>=0,'Random starts must be a nonnegative integer')
    output.mkdir(parents=True,exist_ok=True);write(output/'build_status.json',{'status':'importing','version':VERSION})
    handover=load_handover(source_dir);config=procedure(random_starts);decisions=assumptions()
    freeze={'procedure':config,'implementation':implementation_hashes(),'sources':handover['sources'],
            'assumptions_sha256':fingerprint(decisions),'development_ids':sorted(sid for sid,p in handover['people'].items() if p['split']=='development'),
            'runtime':{'python':platform.python_version(),'numpy':numpy.__version__,'scipy':scipy.__version__}}
    freeze['sha256']=fingerprint(freeze)
    # Persist the fixed procedure before fitting or scoring the evaluation cohort.
    write(output/'frozen_procedure.json',freeze);write(output/'assumptions.json',decisions)
    write(output/'observations.json',handover['observations'])
    write(output/'source_measures.json',handover['reference_measures'])
    write(output/'variable_registry.json',{'participant_measures':handover['variables'],'trial_definitions':handover['trial_definitions']})
    write(output/'import_audit.json',{'tasks':handover['audit'],'profile_counts':handover['profile_counts'],'classification_settings':handover['classification_settings']})
    people=handover['people'];full=[];training=[];results=[];observed={};crosschecks=[]
    order=sorted(people,key=lambda sid:(people[sid]['split']!='development',sid))
    with (output/'heldout_predictions.jsonl').open('w') as stream:
        for sid in order:
            person=people[sid];histories={task:handover['observations'][task][sid] for task in ['MAB','TBS']}
            train_history={'MAB':[r for r in histories['MAB'] if r['index']<=config['mab']['training_last_trial']],
                           'TBS':[r for r in histories['TBS'] if r['block']<=config['tbs']['training_last_block']]}
            mab_train,mab_fit=fit_mab(train_history['MAB'],config['mab'])
            tbs_train,tbs_fit=fit_tbs(train_history['TBS'],config['tbs'])
            tbs_full,tbs_full_fit=fit_tbs(histories['TBS'],config['tbs'])
            models_train={'MAB':mab_train,'TBS':tbs_train};models_full={'MAB':person['mab_supplied'],'TBS':tbs_full}
            person['training_fit_diagnostics']={'MAB':mab_fit,'TBS':tbs_fit};person['tbs_full_fit_diagnostics']=tbs_full_fit
            person['training_omission']={task:omission_rate(h) for task,h in train_history.items()}
            person['full_omission']={task:omission_rate(h) for task,h in histories.items()}
            full.append(actor_spec(person,models_full,person['full_omission'],'full_data_reconstruction',freeze))
            training.append(actor_spec(person,models_train,person['training_omission'],'training_only_validation',freeze))
            observed[sid]={}
            for task in ['MAB','TBS']:
                cutoff=config['mab']['training_last_trial'] if task=='MAB' else config['tbs']['training_last_block']*8
                summary,trial_predictions=predict(task,histories[task],models_train[task],cutoff)
                results.append({'source_id':sid,'participant':person['id'],'task':task,'split':person['split'],**summary})
                for row in trial_predictions:stream.write(json.dumps({'source_id':sid,'task':task,'split':person['split'],**row},allow_nan=False)+'\n')
                observed[sid][task]=metrics(task,histories[task],models_full[task])
                for name,value in observed[sid][task].items():
                    reference=handover['reference_measures'][sid].get(name)
                    if value is not None and reference is not None:
                        crosschecks.append({'source_id':sid,'metric':name,'computed':value,'supplied':reference,'absolute_difference':abs(value-reference)})
            write(output/'fits'/f'{sid}.json',{'frozen_procedure_sha256':freeze['sha256'],'full':full[-1],'training':training[-1],
                  'diagnostics':{'MAB_training':mab_fit,'TBS_training':tbs_fit,'TBS_full':tbs_full_fit}})
            write(output/'build_status.json',{'status':'fitting','completed_participants':len(full),'total_participants':len(people),'frozen_procedure_sha256':freeze['sha256']})
            if progress:progress(sid+' '+person['split']+' fitted and evaluated')
    for name,actors in [('full',full),('training',training)]:
        for split in ['all','development','evaluation']:
            selected=[a for a in actors if split=='all' or a['provenance']['split']==split]
            filename='participants.'+split+('' if name=='full' else '.training')+'.json'
            write(output/filename,selected)
    registry={'version':VERSION,'researcher_only':True,'frozen_procedure_sha256':freeze['sha256'],
              'people':[people[sid] for sid in sorted(people)],'profile_counts':handover['profile_counts'],
              'notice':'Original exploratory profile labels and core scores are evaluator metadata, not actor features or assistant inputs.'}
    write(output/'cohort.json',registry);write(output/'observed_metrics.json',observed)
    write(output/'heldout_report.json',{'version':VERSION,'frozen_procedure_sha256':freeze['sha256'],
        'notice':'Training-only sequential predictions conditioned on observed earlier feedback. TBS predictions are offer-marginal. Original profile/model selection used this cohort; this is not external validation.',
        'participant_results':results,'groups':aggregate(results)})
    write(output/'source_metric_crosscheck.json',{'checks':crosschecks,'max_absolute_difference':max((c['absolute_difference'] for c in crosschecks),default=None)})
    # Bind the final artefacts to the frozen model specification without hashing this mutable status file.
    files={str(p.relative_to(output)):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*.json*')) if p.name!='build_status.json'}
    write(output/'bundle_manifest.json',{'frozen_procedure_sha256':freeze['sha256'],'files':files})
    write(output/'build_status.json',{'status':'complete','participants':len(full),'frozen_procedure_sha256':freeze['sha256']})
    return registry


def verify_bundle(directory):
    import hashlib
    directory=Path(directory);status=json.loads((directory/'build_status.json').read_text())
    require(status['status']=='complete','Cohort build is incomplete')
    manifest=json.loads((directory/'bundle_manifest.json').read_text())
    freeze=json.loads((directory/'frozen_procedure.json').read_text())
    require(freeze['implementation']==implementation_hashes(),'Empirical implementation changed; create a new cohort bundle')
    for name,digest in manifest['files'].items():
        require(hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest,'Frozen bundle file changed: '+name)
    return directory


def export(directory,split='development',source_ids=None,role='full',offer_sensitivity=0.):
    directory=verify_bundle(directory)
    require(split in {'all','development','evaluation'} and role in {'full','training'},'Unknown cohort split or parameter role')
    filename='participants.'+split+('' if role=='full' else '.training')+'.json'
    actors=json.loads((directory/filename).read_text());source_ids=set(source_ids or [])
    if source_ids:
        found={a['provenance']['source_id'] for a in actors}&source_ids
        require(found==source_ids,'Selected source ID is not in this split')
        actors=[a for a in actors if a['provenance']['source_id'] in source_ids]
    for actor in actors:
        actor['task_models']['TBS']['offer_sensitivity']=offer_sensitivity
        actor['provenance']['assumed_offer_sensitivity']=offer_sensitivity
        validate_participant(actor)
    return actors


def simulate_baseline(directory,split,repeats,seed,offer_sensitivity=0.,progress=print):
    require(type(repeats) is int and repeats>0,'Replicates must be positive')
    actors=export(directory,split=split,offer_sensitivity=offer_sensitivity)
    observed=json.loads((Path(directory)/'observed_metrics.json').read_text())
    result=free_runs(actors,observed,repeats,seed,lambda p,t:progress(p+' '+t+' fresh runs complete') if progress else None)
    result.update(split=split,offer_sensitivity=offer_sensitivity,participants=len(actors),version=VERSION)
    return result


def check_recovery(directory,split,repeats,seed,source_ids=None,progress=print):
    require(type(repeats) is int and repeats>0,'Replicates must be positive')
    actors=export(directory,split=split,source_ids=source_ids)
    config=json.loads((Path(directory)/'frozen_procedure.json').read_text())['procedure']
    return recovery(actors,config,repeats,seed,progress)
