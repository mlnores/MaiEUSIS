#!/usr/bin/env python3
"""Audit observed-personalisation results without changing frozen pilot outputs."""
import argparse
import hashlib
import json
import math
import copy
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean,stdev

import mab_fair_sweep as sweep
from socratic_prototype.agents import Participant


def check(condition,message):
    if not condition:raise ValueError(message)


def close(a,b):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-9)


def audit(root):
    root=Path(root).resolve();analysis_path=root/'analysis.json'
    original_sha=sweep.sha(analysis_path);analysis=sweep.pilot.read(analysis_path)
    check(analysis['complete'] and analysis['execution_complete'] and analysis['control_checks_passed'],'Sweep is incomplete or failed')
    manifest,reference,actors,levels=sweep.prepare(root,verify_old=True)
    check(analysis['manifest_sha256']==manifest['sha256'],'Analysis uses another manifest')
    check(manifest['id']=='observed-mab-development16-r3-v1','Wrong experiment for this report')
    profiles={a['id']:a['original_profile'] for a in actors}
    check(Counter(profiles.values())=={g:4 for g in sweep.PROFILES},'Wrong archetype membership')
    status=sweep.pilot.read(root/'status.json')
    check(status['status']=='complete' and not status['failures'] and status['error'] is None,'Runner did not complete cleanly')
    prior=sweep.pilot.read(root/'previous_policy_reference.json')
    check(all(sweep.sha(r['path'])==r['sha256'] for r in prior['files']),'Previous policy reference changed')
    previous_root=Path(prior['directory'])
    previous_manifest=sweep.read_hashed_manifest(previous_root/'manifest.json')
    expected={(r['participant'],r['repeat']):r for r in reference['expected']}
    base_config=levels['0.25']['manifest']['configuration']
    for actor in actors:
        for repeat in range(3):
            fresh=sweep.baseline_rollout(actor,base_config['seed'],repeat,'full')
            sweep.check_baseline(fresh,expected[actor['id'],repeat])
    print('Frozen sources and 48 independently regenerated baselines verified.',flush=True)
    index={};calibrations={};rows=[];count=0;pair_checks={'C_E':0,'D_F':0};outcomes=0;response_checks=0
    pair_totals={'C_E':0,'D_F':0};prior_generic={'checked':0,'identical':0,'changed_cases':[]}
    versions=set()
    for level,entry in levels.items():
        check(len(entry['results'])==48,'Missing completed jobs')
        for record in entry['results']:
            case=record['case'];person=case['participant'];rep=case['repeat']
            sweep.verify_result(record,expected[person,rep])
            path=entry['directory']/record['report_file'];report=sweep.pilot.read(path)
            spec=copy.deepcopy(next(a for a in actors if a['id']==person))
            spec['response_parameters']={'MAB':{s:dict(entry['manifest']['configuration']['response_parameters']) for s in ('direct','socratic')}}
            check(report['participants']==[spec],'Actor/response inputs differ from frozen configuration')
            versions.add((report['version'],report['agent_version'],report['response_version']))
            check(report['study']['conditions']==list(sweep.CONDITIONS),'Unexpected condition order')
            check(set(report['study']['tasks'])=={'MAB'},'Unexpected task')
            runs={r['condition']:r for r in report['runs']}
            check(len(report['runs'])==5 and set(runs)==set(sweep.CONDITIONS),'Missing condition session')
            saved={r['condition']:r for r in record['rows']}
            for condition,run in runs.items():
                trials=run['trials'];s=saved[condition]
                check(run['completed'] and len(trials)==200,'Incomplete condition protocol')
                check([t['index'] for t in trials]==list(range(1,201)),'Missing/duplicate trial')
                trajectory=sweep.pilot.fingerprint([(t['index'],t['choice'],t['outcome']) for t in trials])
                distribution=sweep.pilot.fingerprint([t['assisted_probabilities'] for t in trials])
                check((trajectory,distribution)==(s['trajectory_sha256'],s['distribution_sha256']),'Summary differs from raw trials')
                check(run['environment_seed']==expected[person,rep]['environment_seed'],'Unmatched choice/outcome stream')
                env=sweep.Environment('MAB','full',run['environment_seed']);actor=Participant(spec,'MAB','responsive');total=0;active=0
                for t in trials:
                    ev=env.evaluation('audit',t['index'])
                    base,probabilities,replayed_effect=actor.distribution(ev,t.get('intervention'))
                    check(base==t['baseline_probabilities'] and probabilities==t['assisted_probabilities'],
                          'Choice probabilities differ from actor replay')
                    check(replayed_effect==t['effect'],'Recorded response effect differs from actor replay')
                    choice=sweep.select(probabilities,sweep.uniform(env.seed,'choice',t['index']))
                    if sweep.uniform(env.seed,'omission',t['index'])<replayed_effect['omission_probability']:choice='NO_RESPONSE'
                    check(choice==t['choice'],'Choice differs from keyed sampling')
                    feedback=env.outcome(ev,choice);actor.observe(ev,feedback)
                    check(feedback['outcome']==t['outcome'],'Outcome differs from keyed task mechanics')
                    check(env.evaluator_state()==t['evaluator_state'],'Task transition/evaluator state differs')
                    outcomes+=1;total+=t['outcome']
                    b=t['baseline_probabilities'];p=t['assisted_probabilities'];effect=t['effect'];intervention=t.get('intervention')
                    check(set(b)==set(p) and all(math.isfinite(x) and 0<=x<=1 for x in p.values()) and close(sum(p.values()),1),'Invalid choice distribution')
                    if effect.get('applied'):
                        active+=1
                        check(condition!='A' and intervention is not None,'A contains assistance')
                        params=effect['parameters'];check(params==entry['manifest']['configuration']['response_parameters'],'Wrong response coefficients')
                        if condition in ('C','E'):
                            offered=[intervention['recommendation']['option_id']]
                            check(intervention['style']=='direct','Wrong direct style')
                        else:
                            offered=[c['option_id'] for c in intervention['comparisons']]
                            check(len(set(offered))==2 and [c['details']['rank'] for c in intervention['comparisons']]==[1,2],'Invalid shared top-two guidance')
                            check(intervention['style']=='socratic' and intervention['recommendation'] is None,'Wrong Socratic style')
                        mass=sum(b[a] for a in offered)
                        q={a:(b[a]/mass if mass else 1/len(offered)) if a in offered else 0 for a in b}
                        check(all(close(effect['processing_target'][a],q[a]) for a in b),'Processing target differs from profile-conditioned offer')
                        check(all(close(p[a],(1-float(level))*b[a]+float(level)*q[a]) for a in b),'Receptiveness mixture differs')
                        response_checks+=1
                    else:check(b==p and intervention is None,'Silent trial changed baseline preferences')
                check(env.done and total==run['metrics']['score']==s['primary_value'],'Score arithmetic differs')
                check(active==s['active_interventions'] and sum(t['choice']=='NO_RESPONSE' for t in trials)==s['omissions'],'Count differs')
                check((person,rep,float(level),condition) not in index,'Duplicate matched case')
                reduced={'participant':person,'repeat':rep,'receptiveness':float(level),'condition':condition,
                         'score':total,'interventions':active,'omissions':s['omissions'],
                         'trajectory_sha256':trajectory,'distribution_sha256':distribution}
                index[person,rep,float(level),condition]=reduced;rows.append(reduced)
            for c,d in (('C','E'),('D','F')):
                a=saved[c];b=saved[d]
                pair_totals[c+'_'+d]+=1
                pair_checks[c+'_'+d]+=int(all(a[k]==b[k] for k in ('trajectory_sha256','distribution_sha256','primary_value','active_interventions','omissions')))
            old=sweep.pilot.read(previous_root/previous_manifest['levels'][level]['directory']/'jobs'/record['job_id']/'result.json')
            old_rows={r['condition']:r for r in old['rows']}
            check(sweep.pilot.fingerprint(old['rows'])==old['summary_sha256'],'Old generic summary changed')
            for condition in ('C','D'):
                same=all(saved[condition][k]==old_rows[condition][k] for k in ('trajectory_sha256','distribution_sha256','primary_value','active_interventions','omissions'))
                prior_generic['checked']+=1;prior_generic['identical']+=int(same)
                if not same:prior_generic['changed_cases'].append({'participant':person,'repeat':rep,'level':level,'condition':condition})
            actual=sweep.calibration_signature(report,path.parent/'sessions.sqlite3')
            check(actual==record['calibration'],'Actual calibration differs from committed signature')
            if (person,rep) in calibrations:check(calibrations[person,rep]==actual,'Calibration differs across levels')
            calibrations[person,rep]=actual
            count+=1
            if count%24==0:print(f'Raw scores, response mixtures and calibrations verified: {count}/144 jobs.',flush=True)
    check(len(index)==720 and outcomes==144000,'Incomplete matched data')
    expected_keys={(a['id'],rep,rho,c) for a in actors for rep in range(3) for rho in (.25,.5,.75) for c in sweep.CONDITIONS}
    check(set(index)==expected_keys,'Missing comparison keys')
    individual={}
    for r in analysis['individual_results']:
        p=r['participant'];rho=r['receptiveness'];c=r['condition']
        check(r['profile']==profiles[p] and (p,rho,c) not in individual,'Wrong/duplicate individual archetype')
        chosen=[index[p,rep,rho,c] for rep in range(3)];base=[index[p,rep,rho,'A'] for rep in range(3)]
        deltas=[a['score']-b['score'] for a,b in zip(chosen,base)]
        check(r['repetitions']==3 and r['repetition_deltas']==deltas,'Wrong repetition deltas')
        values={'mean_delta':mean(deltas),'mean_score':mean(t['score'] for t in chosen),'baseline':mean(t['score'] for t in base),
                'monte_carlo_se':stdev(deltas)/math.sqrt(3),'mean_interventions':mean(t['interventions'] for t in chosen)}
        check(all(close(r[k],v) for k,v in values.items()),'Individual summary differs')
        individual[p,rho,c]=r
    check(len(individual)==192,'Missing individual summaries')
    check(set(individual)=={(p,r,c) for p in profiles for r in (.25,.5,.75) for c in sweep.ASSISTED},'Wrong individual summary keys')
    for g in analysis['groups']:
        values=[r['mean_delta'] for r in individual.values() if r['receptiveness']==g['receptiveness'] and r['condition']==g['condition'] and
                (g['profile']=='all' or r['profile']==g['profile'])]
        check(g['participants']==len(values)==(16 if g['profile']=='all' else 4),'Wrong group sample size')
        check(close(g['mean_delta'],mean(values)),'Group mean differs')
        check(tuple(g[k] for k in ('better','same','worse'))==(sum(v>0 for v in values),sum(v==0 for v in values),sum(v<0 for v in values)),
              'Group harm counts differ')
    check(len(analysis['groups'])==60,'Missing group summaries')
    check(sweep.sha(analysis_path)==original_sha,'Frozen analysis was changed')
    result={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'manifest_sha256':manifest['sha256'],'analysis_sha256':original_sha,
            'verified':True,'completed_jobs':count,'fresh_condition_sessions':len(index),'calibrations':count,'trial_outcomes_checked':outcomes,
            'active_response_mixtures_checked':response_checks,'independent_baseline_trajectories':len(expected),
            'historical_baseline_checks':reference['historical_A_checks'],'fresh_baseline_checks':count,
            'actual_calibrations_rechecked':count,'calibration_cross_level_checks':count-len(calibrations),
            'individual_summaries_checked':len(individual),'group_summaries_checked':len(analysis['groups']),
            'actor_choice_distributions_and_draws_checked':outcomes,'source_versions':[list(v) for v in sorted(versions)],
            'personalisation_pairs_checked':pair_totals,'identical_personalisation_pairs':pair_checks,
            'prior_generic_comparison':prior_generic,'prior_reference_hashes_unchanged':True,'analysis_unchanged':True,
            'script_sha256':sweep.sha(__file__),
            'limits':'Numerical replay and source/provenance audit; no new full graph/SHACL replay or language-model evaluation.'}
    sweep.pilot.write(root/'report_audit.json',result)
    sweep.pilot.write(root/'report_trial_summaries.json',{'manifest_sha256':manifest['sha256'],'rows':rows})
    print(json.dumps(result,indent=2),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    audit(parser.parse_args().directory)


if __name__=='__main__':main()
