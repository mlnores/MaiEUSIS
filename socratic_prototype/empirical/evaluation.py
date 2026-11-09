"""Descriptive researcher-side prediction, free runs and recovery checks."""
import hashlib
import json
import math
from collections import Counter,defaultdict
from statistics import mean,stdev
from .data import evaluation
from ..tasks import mab_empirical as mab,tbs_empirical as tbs
from ..tasks.mab import ARMS
from ..agents import Participant
from ..simulation import Environment,uniform,select


def omission_rate(history):return (sum(r['timed_out'] for r in history)+.5)/(len(history)+1)


def predict(task,history,parameters,cutoff):
    rows=[];past=[];q=dict.fromkeys(ARMS,0.)
    train=[r for r in history if r['index']<=cutoff and r['choice_eligible'] and not r['timed_out']]
    options=ARMS if task=='MAB' else ('safe','risky')
    counts=Counter(r['choice'] for r in train);frequency={a:(counts[a]+1)/(len(train)+len(options)) for a in options}
    for row in history:
        if task=='MAB':distribution=mab.probabilities(q,parameters['beta'])
        else:
            probability=tbs.marginal_probability(tbs.features(evaluation(task,row),past),parameters)
            distribution={'safe':1-probability,'risky':probability}
        if row['index']>cutoff and row['choice_eligible'] and not row['timed_out']:
            choice=row['choice'];p=max(2.2250738585072014e-308,distribution[choice])
            brier=(distribution['risky']-float(choice=='risky'))**2 if task=='TBS' else sum((v-float(a==choice))**2 for a,v in distribution.items())
            rows.append({'index':row['index'],'choice':choice,'probabilities':distribution,'log_loss':-math.log(p),
                         'brier':brier,'uniform_log_loss':math.log(len(options)),'frequency_log_loss':-math.log(frequency[choice])})
        if task=='MAB':mab.update(q,row,parameters['alpha_plus'],parameters['alpha_minus'])
        past.append(row)
    return {'eligible_test_choices':len(rows),'mean_log_loss':mean(r['log_loss'] for r in rows) if rows else None,
            'mean_brier':mean(r['brier'] for r in rows) if rows else None,
            'uniform_log_loss':math.log(len(options)),
            'frequency_log_loss':mean(r['frequency_log_loss'] for r in rows) if rows else None,
            'test_missed_responses':sum(r['timed_out'] for r in history if r['index']>cutoff),
            'test_unknown_choices':sum(r['choice'] is None for r in history if r['index']>cutoff)},rows


def logistic_slope(x,y):
    """Source-compatible descriptive one-predictor slope, not the actor model."""
    import numpy as np
    from scipy.optimize import minimize
    if len(y)<5 or len(set(y))<2 or len(set(x))<2:return None
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float);z=(x-x.mean())/x.std(ddof=1)
    start=[math.log((y.mean()+.5/len(y))/(1-y.mean()+.5/len(y))),0]
    def objective(b):
        logits=b[0]+b[1]*z
        return float(np.logaddexp(0,logits).sum()-y@logits)
    result=minimize(objective,start,method='Nelder-Mead',options={'maxiter':2000,'maxfev':10000,'xatol':1e-10,'fatol':1e-10})
    return float(result.x[1]) if result.success else None


def metrics(task,history,parameters):
    valid=[r for r in history if r['choice_eligible'] and not r['timed_out']]
    pairs=[(a,b) for a,b in zip(valid,valid[1:]) if task=='MAB' or a['block']==b['block']]
    result={'missed_response_rate':sum(r['timed_out'] for r in history)/len(history)}
    def rate(values):return mean(values) if values else None
    if task=='MAB':
        q=dict.fromkeys(ARMS,0.);exploration={'stable':[],'volatile':[]}
        for row in history:
            if mab.eligible(row):exploration['stable' if row['index']<=50 else 'volatile'].append(float(q[row['choice']]<max(q.values())-1e-10))
            mab.update(q,row,parameters['alpha_plus'],parameters['alpha_minus'])
        stable=rate(exploration['stable']);volatile=rate(exploration['volatile'])
        result.update(MAB_FinalAccumulatedPoints=history[-1]['score_after'],
            MAB_SwitchRate_Overall=rate([a['choice']!=b['choice'] for a,b in pairs if b['index']==a['index']+1]),
            MAB_PostPositiveStayRate_Overall=rate([a['choice']==b['choice'] for a,b in pairs if a['outcome']>0]),
            MAB_PostNonPositiveSwitchRate_Overall=rate([a['choice']!=b['choice'] for a,b in pairs if a['outcome']<=0]),
            MAB_ExplorationRate_Stable=stable,MAB_ExplorationRate_Volatile=volatile,
            MAB_ExplorationRate_Difference_VolatileMinusStable=volatile-stable if stable is not None and volatile is not None else None)
    else:
        finals=[r for r in history if r['remaining']==1];rf=rate([r['choice']=='risky' for r in valid if r['remaining']==1]);rp=rate([r['choice']=='risky' for r in valid if r['remaining']>1])
        result.update(TBS_TargetAttainmentRate_MultiplierAdjusted=rate([r['adjusted_after']>=r['target'] for r in finals]),
            TBS_MeanFinalBlockScore_MultiplierAdjusted=rate([r['adjusted_after'] for r in finals]),
            TBS_RiskyChoiceRate_Overall=rate([r['choice']=='risky' for r in valid]),
            TBS_PostGainStayRate_Overall=rate([a['choice']==b['choice'] for a,b in pairs if a['outcome']>0]),
            TBS_PostNoGainSwitchRate_Overall=rate([a['choice']!=b['choice'] for a,b in pairs if a['outcome']==0]),
            TBS_FinalTrialRiskShift_FinalMinusPreFinal=rf-rp if rf is not None and rp is not None else None,
            TBS_PressureRiskSlope_ZPressure=logistic_slope([max(0,r['target']-r['points_before'])/r['remaining'] for r in valid],[float(r['choice']=='risky') for r in valid]),
            TBS_HorizonRiskSlope_ZRemainingTrials=logistic_slope([r['remaining'] for r in valid],[float(r['choice']=='risky') for r in valid]))
    return result


def free_history(spec,task,repeat,seed):
    actor=Participant(spec,task,'null');environment=Environment(task,'full',f'{seed}:{spec["id"]}:{repeat}:{task}')
    history=[]
    for index in range(1,environment.total+1):
        ev=environment.evaluation('free_run',index);_,probabilities,effect=actor.distribution(ev,None)
        choice=select(probabilities,uniform(environment.seed,'choice',index))
        if uniform(environment.seed,'omission',index)<effect['omission_probability']:choice='NO_RESPONSE'
        feedback=environment.outcome(ev,choice);actor.observe(ev,feedback)
        row={'index':index,'trial_id':ev['trial_id'],'choice':choice,'timed_out':feedback['timed_out'],
             'choice_eligible':not feedback['timed_out'],'model_eligible':not feedback['timed_out'],'outcome':feedback['outcome']}
        if task=='MAB':row['score_after']=feedback['score_after']
        else:row.update(block=ev['block'],remaining=ev['remaining'],target=ev['target'],multiplier=ev['multiplier'],
                        points_before=ev['points'],points_after=feedback['points_after'],
                        adjusted_after=feedback['points_after']*(ev['multiplier'] if ev['remaining']==1 and feedback['outcome']>0 else 1))
        history.append(row)
    return history


def free_runs(specs,reference_measures,repeats,seed,progress=None):
    rows=[];summaries=[]
    for spec in specs:
        for task in spec['task_models']:
            measurements=[]
            for repeat in range(repeats):
                h=free_history(spec,task,repeat,seed);values=metrics(task,h,spec['task_models'][task]);measurements.append(values)
                signature=hashlib.sha256(json.dumps([(r['choice'],r['outcome']) for r in h]).encode()).hexdigest()
                rows.append({'participant':spec['id'],'task':task,'repeat':repeat,'metrics':values,'trajectory_sha256':signature})
            for name in measurements[0]:
                values=[m[name] for m in measurements if m[name] is not None]
                reference=reference_measures[spec['provenance']['source_id']][task].get(name)
                summaries.append({'participant':spec['id'],'task':task,'metric':name,'observed_reference':reference,
                    'simulation_mean':mean(values) if values else None,'simulation_sd':stdev(values) if len(values)>1 else None,
                    'difference':mean(values)-reference if values and reference is not None else None,'replicates':len(values)})
            if progress:progress(spec['id'],task)
    return {'notice':'Descriptive fresh-run checks; repeated simulations are not independent people. Score agreement is not sufficient validation.',
            'repeats':repeats,'seed':seed,'runs':rows,'comparisons':summaries}


def recovery(specs,config,repeats,seed,progress=None):
    from .fitting import fit_mab,fit_tbs
    results=[]
    for spec in specs:
        for task in ['MAB','TBS']:
            for repeat in range(repeats):
                history=free_history(spec,task,repeat,seed)
                recovered,diagnostics=(fit_mab(history,config['mab']) if task=='MAB' else fit_tbs(history,config['tbs']))
                original=spec['task_models'][task];past=[];squared=[]
                qo=dict.fromkeys(ARMS,0.);qr=dict.fromkeys(ARMS,0.)
                for row in history:
                    if task=='MAB':
                        a=mab.probabilities(qo,original['beta']);b=mab.probabilities(qr,recovered['beta'])
                        squared.append(sum((a[k]-b[k])**2 for k in ARMS)/len(ARMS))
                        mab.update(qo,row,original['alpha_plus'],original['alpha_minus']);mab.update(qr,row,recovered['alpha_plus'],recovered['alpha_minus'])
                    else:
                        features=tbs.features(evaluation(task,row),past)
                        squared.append((tbs.marginal_probability(features,original)-tbs.marginal_probability(features,recovered))**2)
                    past.append(row)
                results.append({'participant':spec['id'],'task':task,'repeat':repeat,'recovered':recovered,'diagnostics':diagnostics,
                    'policy_probability_rmse':math.sqrt(mean(squared)),
                    'mab_parameter_absolute_errors':{k:abs(recovered[k]-original[k]) for k in ['alpha_plus','alpha_minus','beta']} if task=='MAB' else None})
            if progress:progress(spec['id']+' '+task+' recovery complete')
    return {'notice':'Internal recovery under the assumed generating model; not human validation or uncertainty intervals. TBS coefficient/scaling parameterisations differ across fits; compare probabilities on common states.',
            'repeats':repeats,'seed':seed,'results':results}
