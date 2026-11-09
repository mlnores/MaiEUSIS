"""Read-only handover import and explicit canonical observation projection."""
import csv
import hashlib
import math
from collections import Counter,defaultdict
from pathlib import Path
from .xlsx import Workbook
from ..records import require,number
from ..tasks.mab import ARMS
from ..tasks.mab_empirical import MODEL as MAB_MODEL,probabilities,update
from ..tasks.tbs import RULES

PROFILES={'MAB-specialised','TBS-specialised','Dual-regime','Low-expression'}


def locate(root,prefix):
    matches=list(Path(root).glob(prefix+'*.xlsx'))
    require(len(matches)==1,'Expected one handover workbook starting '+prefix)
    return matches[0]


def keyed(rows):
    result={r['ID_Subject']:r for r in rows}
    require(len(result)==len(rows),'Duplicate participant IDs')
    return result


def optional_number(value):return value if number(value) else None


def observation(task,row):
    """Never copy fitted states, future-linked diagnostics or EEG/trait fields."""
    choice=row['BEH_ChosenOption'];missed=bool(row['BEH_NoResponseThisTrial'])
    known=choice in (ARMS if task=='MAB' else ('safe','risky'))
    rt=row.get('EEG_RT_s')
    result={'index':row['ID_OverallTrial'],'trial_id':row['ID_TrialKey'],
            'choice':choice if known else 'NO_RESPONSE' if missed else None,
            'timed_out':missed,'choice_eligible':bool(row['ANL_ValidChoiceTrial']) and known,
            'model_eligible':bool(row['ANL_ValidChoiceTrial'] and row['ANL_ValidOutcomeTrial']) and known,
            'response_ms':rt*1000 if row.get('ANL_ValidChoiceRTTrial') and number(rt,0,60) else None,
            'unknown_choice_reason':None if known or missed else 'documented_logging_bug' if row.get('BEH_ChoiceMissingDueToKnownBug') else 'unknown'}
    if task=='MAB':
        result.update(outcome=row['BEH_OutcomeValue'],score_after=row['BEH_CurrentTotalPoints'],phase=row['BEH_Phase'])
    else:
        result.update(block=row['BEH_Block'],remaining=row['BEH_RemainingTrials'],target=row['BEH_BlockTarget'],
                      multiplier=row['BEH_BlockMultiplier'],points_before=row['BEH_BlockScoreBeforeTrial_PreMultiplier'],
                      points_after=row['BEH_BlockScoreAfterTrial_PreMultiplier'],outcome=row['BEH_TrialPointsGained_PreMultiplier'],
                      adjusted_after=row['BEH_ScoreAfterTrial_MultiplierAdjusted'],historical_offer=None)
    require(number(result['outcome']),'Missing observed outcome')
    return result


def evaluation(task,row):
    """Historical TBS evaluation intentionally has no offers; never invent a pair."""
    if task=='MAB':return {'index':row['index'],'options':[{'id':a} for a in ARMS]}
    return {'index':row['index'],'block':row['block'],'points':row['points_before'],
            'target':row['target'],'remaining':row['remaining'],'multiplier':row['multiplier']}


def load_handover(root):
    root=Path(root);main_path=locate(root,'Chapter5_Step03_');profile_path=locate(root,'Chapter6_Step06A_')
    spec_path=locate(root,'Prototype_Behavioural_')
    with (root/'Development16.csv').open(newline='',encoding='utf-8-sig') as stream:development=list(csv.DictReader(stream))
    dev=keyed(development);require(len(dev)==16,'Development split must have 16 unique IDs')
    require(set(Counter(r['Profile'] for r in dev.values()).values())=={4},'Expected four development participants per profile')
    with Workbook(profile_path) as book:
        profiles=keyed(list(book.records('Participant_Profiles')))
        classification=list(book.records('Classification_Settings'))
    require(len(profiles)==62,'Expected the supplied 62-person cohort')
    require(set(dev)<=profiles.keys(),'Development IDs missing from profiles')
    require({p['Profile'] for p in profiles.values()}==PROFILES,'Unexpected profile definitions')
    for sid,row in dev.items():
        require(row['Profile']==profiles[sid]['Profile'],'Development/profile classification mismatch')
        require(float(row['ProfileMargin'])>=.1,'Development member falls below supplied clarity margin')
        for column in ['MAB_CoreProfile_Z','TBS_CoreProfile_Z']:
            require(abs(float(row[column])-profiles[sid][column])<1e-9,'Development/profile score mismatch')
    with Workbook(spec_path) as book:
        variables=list(book.records('Participant variables'));trial_definitions=list(book.records('Trial calculations'))
    require(len(variables)==200 and len({r['Exact variable name'] for r in variables})==200,'Expected 200 unique documented measures')
    sources={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
             for p in sorted(root.iterdir()) if p.is_file() and p.suffix in {'.xlsx','.m','.csv','.docx','.md'}}
    observations={'MAB':defaultdict(list),'TBS':defaultdict(list)};audit={};people={}
    with Workbook(main_path) as book:
        params=keyed(list(book.records('RetainedParameters')))
        references=keyed(list(book.records('ParticipantSummary')))
        retained=list(book.records('RetainedModel'))
        require(len(retained)==1 and retained[0]['RetainedModel']=='dual','Handover retained model is not dual RW')
        require(set(profiles)==set(params)==set(references),'Participant tables do not join exactly')
        for sid in sorted(profiles):
            p=params[sid];require(p['Converged'],'Nonconverged supplied MAB fit for '+sid)
            actor={'model':MAB_MODEL,'reward_scale':100,'alpha_plus':p['AlphaPositive'],'alpha_minus':p['AlphaNegative'],'beta':p['Beta']}
            require(all(number(actor[k]) for k in ['alpha_plus','alpha_minus','beta']),'Nonfinite supplied MAB parameters')
            people[sid]={'id':'reconstructed_'+sid,'source_id':sid,'split':'development' if sid in dev else 'evaluation',
                         'original_profile':profiles[sid]['Profile'],
                         'core_profile_scores':{k:profiles[sid][k] for k in ['MAB_CoreProfile_Z','TBS_CoreProfile_Z']},
                         'development_margin':float(dev[sid]['ProfileMargin']) if sid in dev else None,
                         'mab_supplied':actor,'mab_fit_diagnostics':{k:p.get(k) for k in ['N_ModelTrials','NLL','AIC','BIC','BoundaryFlag','Converged']}}
        for task,total in [('MAB',200),('TBS',192)]:
            counts=Counter();seen=set();unknown=missed=0;maxq=maxp=maxpe=maxnll=0.
            q={sid:dict.fromkeys(ARMS,0.) for sid in people};nll=Counter();n=Counter()
            scoring_errors=0
            for row in book.records(task):
                sid=row['ID_Subject'];require(sid in profiles,'Unknown trial participant')
                require(row['ID_TrialKey'] not in seen,'Duplicate trial key');seen.add(row['ID_TrialKey'])
                expected=counts[sid]+1;require(row['ID_OverallTrial']==expected,'Nonconsecutive historical trial order')
                counts[sid]+=1;obs=observation(task,row);observations[task][sid].append(obs)
                unknown+=obs['choice'] is None;missed+=obs['timed_out']
                if task=='MAB':
                    p=people[sid]['mab_supplied'];pred=probabilities(q[sid],p['beta'])
                    for a in ARMS:
                        value=row.get('MAB_Q_'+a+'_PreChoice')
                        if number(value):maxq=max(maxq,abs(q[sid][a]-value))
                    if obs['model_eligible']:
                        probability=pred[obs['choice']];nll[sid]-=math.log(max(probability,1e-300));n[sid]+=1
                        maxp=max(maxp,abs(probability-row['MAB_ChoiceProbability']))
                        pe=obs['outcome']/100-q[sid][obs['choice']]
                        maxpe=max(maxpe,abs(pe-row['MAB_PredictionErrorSigned']))
                        update(q[sid],obs,p['alpha_plus'],p['alpha_minus'])
                else:
                    raw=obs['points_before']+obs['outcome'];adjusted=raw*(obs['multiplier'] if obs['remaining']==1 and obs['outcome']>0 else 1)
                    scoring_errors+=abs(raw-obs['points_after'])>1e-8 or abs(adjusted-obs['adjusted_after'])>1e-8
                    require((obs['target'],obs['multiplier']) in zip(RULES['targets'],RULES['multipliers']),'Unexpected TBS target rule')
            require(set(counts)==set(profiles) and all(v==total for v in counts.values()),'Incomplete historical task sequences')
            if task=='MAB':
                require(all(n[sid]==params[sid]['N_ModelTrials'] for sid in people),'MAB fitted trial counts disagree')
                maxnll=max(abs(nll[sid]-params[sid]['NLL']) for sid in people)
                require(maxnll<1e-6 and maxq<1e-9 and maxp<1e-9 and maxpe<1e-9,'MAB forward pass disagrees with supplied calculations')
            require(not scoring_errors,'TBS score arithmetic disagrees')
            audit[task]={'participants':len(counts),'trials':sum(counts.values()),'missed_responses':missed,'unknown_choices':unknown,
                         'max_mab_nll_difference':maxnll if task=='MAB' else None,'max_mab_q_difference':maxq if task=='MAB' else None,
                         'max_mab_probability_difference':maxp if task=='MAB' else None,'scoring_errors':scoring_errors}
    return {'people':people,'observations':{task:dict(rows) for task,rows in observations.items()},
            'reference_measures':{sid:{k:optional_number(v) for k,v in row.items() if k!='ID_Subject'} for sid,row in references.items()},
            'variables':variables,'trial_definitions':trial_definitions,'sources':sources,'audit':audit,
            'classification_settings':classification,'profile_counts':dict(Counter(p['original_profile'] for p in people.values()))}
