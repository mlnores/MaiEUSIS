"""TBS model, public-event boundary and task-specific checks. No shared policy decisions."""
import copy
import math
from collections import Counter
from itertools import product
from ..records import fields,require,identity,number
from .base import MODEL_VERSION as VERSION, validate_envelope, describe_task, common_observation

ID = 'TBS'
NAMESPACE = 'https://example.org/socratic/tbs/'
MODULE_VERSION = 'tbs-0.1'
ONTOLOGY_VERSION = 'tbs-ontology-0.1'
ELIGIBLE_POINT = 'options-visible preparation'
PROTOCOLS={'short':24,'full':192}
RULES={'targets':[595,930,1035,1105],'multipliers':[1.1,2.3,3.3,4.2],
       'options':[[[100,.9],[265,.35]],[[180,.6],[260,.35]],[[145,.75],[245,.35]],[[145,.55],[350,.2]],
                  [[115,.9],[240,.45]],[[150,.6],[190,.45]],[[170,.75],[245,.4]],[[120,.8],[210,.3]]]}


def documents():
    from .base import document_paths
    paths=document_paths(ID)
    return paths[:3],paths[3:]

def describe():return describe_task(ID,NAMESPACE,MODULE_VERSION,ONTOLOGY_VERSION,documents())

evidence_observation=common_observation

def argumentation_documents():
    from ..argumentation import ROOT
    return (ROOT/'schemes/tbs.ttl',)

def task_rules():return copy.deepcopy(RULES)

def history_context(ev):
    return {'points_before':ev['points'],'target':ev['target'],'remaining':ev['remaining'],'block':ev['block']}

def same_scope(event,evaluation):return event.get('block')==evaluation.get('block')

def scope_suffix(evaluation):return ':block-'+str(evaluation['block'])

def environment(h,ev,policy,event):
    env=tbs_context(ev)
    if event['kind']=='feedback':
        after=event['points_after']*(ev['multiplier'] if ev['remaining']==1 and event['outcome']>0 else 1)
        env['after_feedback']={'points':after,'target_gap':ev['target']-after,'remaining':ev['remaining']-1,
                               'multiplier_applied':ev['remaining']==1 and event['outcome']>0}
    return env

def participant(h,profile):return {'pressure_policy':tbs_pressure_model(h)}

def environment_claim(env):
    return f'Target gap {env["target_gap"]}; {env["remaining"]} choices remain. Immediate EV does not determine final attainment.',['known']

def evidence_environment(env):
    from .base import pick
    return ({**pick(env,['target_gap','remaining','multiplier','required_raw_gain_on_final_win','unknown','assumptions']),
             'options':[pick(o,['id','amount','probability','expected_value','final_trial_win_score',
                                'final_trial_target_probability']) for o in env['options']]},
            f'Target gap: {env["target_gap"]:g}; choices remaining: {env["remaining"]}.')

def evidence_participant(person):
    from .base import pick
    result=pick(person,['unknown'])
    result['calibration']=pick(person['calibration'],['task','samples','model_version','assumptions','policy'])
    if 'policy' in result['calibration']:
        result['calibration']['policy']=pick(person['calibration']['policy'],
            ['samples','status','sensitivity_mean','sensitivity_interval','p_positive_sensitivity','assumptions'])
    return result

def project_rdf(writer,session,event,state,evaluation,previous):
    from .tbs_rdf import project
    project(writer,session,event,state,evaluation,previous)

def tbs_context(evaluation):
    points = evaluation['points']; target=evaluation['target']; remaining=evaluation['remaining']
    gap = target-points
    options=[]
    for o in evaluation['options']:
        win_score = (points+o['amount'])*(evaluation['multiplier'] if remaining==1 else 1)
        loss_score=points
        chance = (o['probability'] if win_score>=target else 0)+(1-o['probability'] if loss_score>=target else 0)
        options.append({**o, 'expected_value':o['probability']*o['amount'],
                        'final_trial_win_score':win_score if remaining==1 else None,
                        'final_trial_target_probability':chance if remaining==1 else None})
    return {'target_gap':gap, 'target_pressure':max(0,gap)/remaining,
            'remaining':remaining, 'multiplier':evaluation['multiplier'], 'options':options,
            'required_raw_gain_on_final_win':max(0,target/evaluation['multiplier']-points) if remaining==1 else None,
            'unknown':['Future option pairs','Future outcomes','Participant intent'],
            'assumptions':['Immediate expected value is not final target-attainment probability.',
                           'Multiplier applies to the whole accumulated score only on a final-trial win.']}

def tbs_pressure_model(history):
    """Discrete-grid Bayesian logistic choice model; exploratory new extension.
    Parameters have equal grid priors, not empirically fitted population priors.
    """
    valid=[h for h in history if not h['timed_out']]
    if not valid:
        return {'samples':0, 'status':'unknown', 'sensitivity_mean':0, 'sensitivity_interval':[-3,3], 'p_positive_sensitivity':.4}
    grid=[]
    for intercept,slope in product([-2,-1,0,1,2],[-3,-1.5,0,1.5,3]):
        lp=0
        for h in valid:
            x=max(-2,min(2,(max(0,h['target']-h['points_before'])/h['remaining']-150)/150))
            p=1/(1+math.exp(-(intercept+slope*x)))
            lp+=math.log(p if h['choice']=='risky' else 1-p)
        grid.append((intercept,slope,lp))
    top=max(g[2] for g in grid); weights=[math.exp(g[2]-top) for g in grid]; total=sum(weights)
    weights=[w/total for w in weights]
    def quantile(q):
        acc=0
        for value,weight in sorted((g[1],w) for g,w in zip(grid,weights)):
            acc+=weight
            if acc>=q:return value
        return 3
    return {'samples':len(valid), 'status':'inferred', 'sensitivity_mean':round(sum(g[1]*w for g,w in zip(grid,weights)),5),
            'sensitivity_interval':[quantile(.025),quantile(.975)],
            'p_positive_sensitivity':round(sum(w for g,w in zip(grid,weights) if g[1]>0),6),
            'assumptions':['Equal prior on 25 intercept/slope pairs; normalized target pressure only.',
                           'Option-value effects and horizon effects are not separately identified.',
                           'This proposed extension is not the original fitted TBS analysis.'],
            'evidence':[h['trial_id'] for h in valid]}

def calibrate(history):
    return {'task': 'TBS', 'model_version': VERSION, 'policy': tbs_pressure_model(history)}
def validate_event(event):
    fields(event, ['kind', 'trial_id', 'index'], ['options', 'score', 'points', 'target', 'remaining', 'block', 'multiplier', 'choice', 'outcome', 'timed_out', 'response_ms', 'score_after', 'points_after'])
    require(identity(event['trial_id']), 'Invalid trial identifier')
    require(type(event['index']) is int and 1 <= event['index'] <= 10000, 'Invalid trial index')
    require(event['kind'] in {'evaluation', 'feedback'}, 'Unknown event kind')
    common = ['kind', 'trial_id', 'index']
    if event['kind'] == 'evaluation':
        allowed = common + ['options', 'points', 'target', 'remaining', 'block', 'multiplier']
        fields(event, allowed)
        opts = event['options']
        require(isinstance(opts, list), 'Options must be a list')
        require(len(opts) == 2, 'Wrong number of options')
        ids = []
        for o in opts:
            fields(o, ['id', 'key', 'amount', 'probability'])
            require(o['id'] in {'safe', 'risky'}, 'Unknown TBS alternative')
            require(number(o['amount'], 1, 10000), 'Invalid amount')
            require(number(o['probability'], 0, 1), 'Invalid displayed probability')
            require(isinstance(o['key'], str) and o['key'] in {'1', '2', '3', '7', '8', '9'}, 'Invalid response key')
            ids.append(o['id'])
        require(len(set(ids)) == len(opts), 'Duplicate option')
        require(len({o['key'] for o in opts}) == len(opts), 'Duplicate key')
        require(ids == ['safe', 'risky'], 'TBS alternatives must retain their published labels and ordering')
        require([o['key'] for o in opts] == ['1', '9'], 'Incorrect TBS key mapping')
        for k in ['points', 'target', 'multiplier']:
            require(number(event[k], 0, 100000), 'Invalid ' + k)
        require(event['target'] > 0 and event['multiplier'] >= 1, 'Invalid target or multiplier')
        require(type(event['remaining']) is int and 1 <= event['remaining'] <= 8, 'Invalid horizon')
        require(type(event['block']) is int and event['block'] >= 1, 'Invalid block')
        require(event['remaining'] == 8 - (event['index'] - 1) % 8, 'Horizon inconsistent with trial')
        require(event['block'] == (event['index'] - 1) // 8 + 1, 'Block inconsistent with trial')
    else:
        fields(event, common + ['choice', 'outcome', 'timed_out', 'response_ms'] + ['points_after'])
        require(type(event['timed_out']) is bool, 'timed_out must be boolean')
        require(event['choice'] in {'safe', 'risky'} | {'NO_RESPONSE'}, 'Invalid choice')
        require((event['choice'] == 'NO_RESPONSE') == event['timed_out'], 'Timeout inconsistent with choice')
        require(event['response_ms'] is None or number(event['response_ms'], 0, 60000), 'Invalid response time')
        require(number(event['outcome']), 'Invalid outcome')
        require(number(event['points_after']), 'Invalid resulting score')

def validate_transition(session,event,h,evaluations):
    if event['kind']=='evaluation':
        expected_points = h[-1]['points_after'] if h and h[-1]['block'] == event['block'] else 0
        require(event['points'] == expected_points, 'Points inconsistent with prior feedback')
        pairs = session['task_rules']['options']
        pair = [[o['amount'], o['probability']] for o in event['options']]
        require(pair in pairs, 'Options outside the published TBS table')
        ti = session['task_rules']['targets'].index(event['target']) if event['target'] in session['task_rules']['targets'] else -1
        require(ti >= 0 and event['multiplier'] == session['task_rules']['multipliers'][ti], 'Target/multiplier mismatch')
        if evaluations and evaluations[-1].get('block') == event['block']:
            require(event['target'] == evaluations[-1]['target'], 'Target changed within block')
    else:
        ev = evaluations[-1]
        option = next((o for o in ev['options'] if o['id'] == event['choice']), None)
        require(event['timed_out'] and event['outcome'] == 0 or (option and event['outcome'] in [0, option['amount']]), 'Impossible gain')
        require(event['points_after'] == ev['points'] + event['outcome'], 'Points arithmetic mismatch')

def hypothesis_inputs(session,evaluation,environment,h):
    p=session['policy']
    window=[x for x in h[-p['window_trials']:] if same_scope(x,evaluation)]
    valid=[x for x in window if not x['timed_out']]
    evidence=[x['trial_id'] for x in valid]
    choices = [x['choice'] for x in valid]
    repeated = len(choices) >= 3 and len(set(choices[-3:])) == 1
    sensitivity = tbs_pressure_model(h)
    calibrated = (session.get('calibration_profile') or {}).get('policy', {})
    weak_sensitivity = calibrated.get('samples', 0) >= 6 and calibrated.get('p_positive_sensitivity', 0.5) < 0.4
    definitions = [('constraint_neglect', environment['remaining'] <= 2, repeated and weak_sensitivity, environment['remaining'] <= 2, 'A repeated choice pattern may warrant checking the shrinking horizon.', ['The same option can still be appropriate after the context changes.', 'The final-win multiplier can preserve feasibility.', 'A policy estimate cannot establish that the participant ignored a constraint.'], ['A context-sensitive adjustment or an explicit constraint-aware explanation revises this account.'])]
    stats = {'recent_choices': choices, 'pressure_policy': sensitivity, 'calibrated_weak_pressure_sensitivity': weak_sensitivity, 'evidence_window': evidence}
    return definitions,stats

def contribute_candidates(session,ev,env,h,stats,estimated,socratic,existing,candidate):
    p=session['policy']
    if env['remaining'] == 1:
        candidate('final_multiplier', 'highlight-dependency' if socratic else 'explain', ['The multiplier applies only if this final choice wins. How does that affect your chance of meeting the target?'] if socratic else ['On the final trial, compare target attainment after a win and after no gain. The multiplier applies only after a win.'], [estimated['id']], 'The published final-win rule changes target attainment.', 'Neither immediate EV nor the nominal gap alone determines attainment.', 0.88)
    elif env['remaining'] <= 2:
        candidate('shrinking_horizon', 'ask' if socratic else 'explain', ['Can your current approach still close the target gap with the choices remaining?'] if socratic else ['Review the target gap against the remaining choices and the conditional final multiplier.'], [estimated['id']], 'The target gap must be assessed against a short horizon.', 'Future option pairs and outcomes are unknown; do not declare the target unreachable.', 0.78)
    if h and h[-1].get('block') == ev['block'] and (h[-1]['outcome'] > 0):
        candidate('gap_after_gain', 'ask' if socratic else 'explain', ['The last gain reduced the target gap. Does the same level of risk still serve your goal?'] if socratic else ['Reconsider the level of risk after the last gain reduced the target gap.'], [estimated['id']], 'A recorded gain changed target progress.', 'A smaller gap alone does not imply that less risk is better.', 0.63)
    if not existing and ev['index'] % p['fixed_prompt_interval'] == 0:
        candidate('expected_value_limit', 'compare' if socratic else 'explain', ['How do the expected gains compare with the chance of reaching your target?'] if socratic else ['Immediate expected gain and final target attainment are different objectives. Consider both.'], [estimated['id']], 'Displayed probabilities and gains support an EV comparison.', 'No future outcome or optimal multi-trial policy is known.', 0.6)

HYPOTHESIS_WORDING = {'constraint_neglect': 'Your recent choice pattern has stayed similar as the horizon shrinks. How are you accounting for the remaining chances?'}

def hypothesis_message(name,socratic):
    wording=HYPOTHESIS_WORDING[name]
    if not socratic:wording=wording.split('. What')[0].split('. How')[0]+'. Consider reviewing this pattern against the available task evidence.'
    return wording

def summarize(session,h,valid):
    result={}
    blocks = [x for x in h if x['remaining'] == 1]
    scores = [x['points_after'] * (session['task_rules']['multipliers'][session['task_rules']['targets'].index(x['target'])] if x['outcome'] > 0 else 1) for x in blocks]
    result.update({'completed_blocks': len(blocks), 'targets_met': sum((score >= b['target'] for score, b in zip(scores, blocks))), 'final_block_scores': scores, 'risky_choice_rate': sum((x['choice'] == 'risky' for x in valid)) / len(valid) if valid else None})
    return result

