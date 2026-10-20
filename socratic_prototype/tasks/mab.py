"""MAB model, public-event boundary and task-specific checks. No shared policy decisions."""
import copy
import math
from collections import Counter
from itertools import product
from ..records import fields,require,identity,number
from .base import MODEL_VERSION as VERSION, validate_envelope, describe_task, common_observation

ID = 'MAB'
NAMESPACE = 'https://example.org/socratic/mab/'
MODULE_VERSION = 'mab-0.1'
ONTOLOGY_VERSION = 'mab-ontology-0.1'
ELIGIBLE_POINT = 'post-feedback preparation'
PROTOCOLS={'short':40,'full':200}

ARMS = ('blue1','blue2','blue3','red1','red2','red3')
KEYS = {'blue1':'8','blue2':'1','blue3':'3','red1':'2','red2':'7','red3':'9'}


def documents():
    from .base import document_paths
    paths=document_paths(ID)
    return paths[:3],paths[3:]

def describe():return describe_task(ID,NAMESPACE,MODULE_VERSION,ONTOLOGY_VERSION,documents())

evidence_observation=common_observation

def task_rules():
    return {'arms':list(ARMS),'keys':dict(KEYS),'blue_outcomes':[100,0,-100],
            'red_outcomes':[200,0,-200],'timeout_penalty':-200,'reward_scale':200}

def history_context(ev):
    return {'points_before':None,'target':None,'remaining':None,'block':None}

def same_scope(event,evaluation):return True

def scope_suffix(evaluation):return ''

def environment(h,ev,policy,event):return mab_environment(h,policy['change_prior'])

def participant(h,profile):
    q,obs=rl(h,profile.get('alpha_plus',.3),profile.get('alpha_minus',.3),profile.get('beta',2))
    return {'q':q,'q_units':'reward / 200; model estimates, not participant beliefs',
            'last_rl_update':obs[-1] if obs else None,
            'parameters':{k:profile.get(k,v) for k,v in [('alpha_plus',.3),('alpha_minus',.3),('beta',2)]}}

def environment_claim(env):
    return 'Reward-value and change estimates from sampled outcomes.',['inferred','source-dependent']

def evidence_environment(env):
    from .base import pick
    return ({'arms':[{**pick(a,['arm','samples','estimated_value','approximate_95_interval']),
                     'change':pick(a['change'],['posterior','log_bayes_factor','samples','evidence'])} for a in env['arms']],
             **pick(env,['unknown','assumptions'])},'Reward values and possible changes remain uncertain.')

def evidence_participant(person):
    from .base import pick
    result=pick(person,['q','q_units','last_rl_update','parameters','unknown'])
    result['calibration']=pick(person['calibration'],['task','samples','model_version','assumptions',
        'alpha_plus','alpha_minus','beta','alpha_plus_interval','alpha_minus_interval','beta_interval'])
    return result

def project_rdf(writer,session,event,state,evaluation,previous):
    from .mab_rdf import project
    project(writer,session,event,state,evaluation,previous)


def softmax(q, beta):
    vals = [beta*q[a] for a in ARMS]
    top = max(vals)
    exp = [math.exp(x-top) for x in vals]
    return dict(zip(ARMS, [x/sum(exp) for x in exp]))

def rl(history, alpha_plus=.3, alpha_minus=.3, beta=2.):
    q = {a: 0. for a in ARMS}
    observations = []
    for h in history:
        if h['timed_out']:
            continue
        a = h['choice']; reward = h['outcome']/200
        probs = softmax(q, beta)
        pe = reward-q[a]
        observations.append({'trial_id':h['trial_id'], 'prediction_error':pe, 'choice_probability':probs[a]})
        q[a] += (alpha_plus if pe>=0 else alpha_minus)*pe
    return q, observations

def log_dm(outcomes):
    counts = Counter(outcomes); n = len(outcomes)
    return math.lgamma(3)-math.lgamma(3+n)+sum(math.lgamma(1+counts[k]) for k in [-1,0,1])

def change_belief(outcomes, prior=.15):
    """Bayes factor for one unspecified split vs a stationary categorical arm.
    Integrates all splits with >=3 samples either side and symmetric Dirichlet
    priors; knows no initial reward probabilities or actual shift events.
    """
    if len(outcomes)<6:
        return {'posterior':prior, 'evidence':'insufficient', 'samples':len(outcomes)}
    splits = [log_dm(outcomes[:k])+log_dm(outcomes[k:]) for k in range(3,len(outcomes)-2)]
    top = max(splits)
    log_changed = top+math.log(sum(math.exp(x-top) for x in splits)/len(splits))
    log_bf = max(-50,min(50,log_changed-log_dm(outcomes)))
    p = 1/(1+(1-prior)/prior*math.exp(-log_bf))
    return {'posterior':round(p,6), 'log_bayes_factor':round(log_bf,6), 'samples':len(outcomes),
            'evidence':'high' if p>=.6 else 'medium' if p>=.3 else 'low'}

def mab_environment(history, prior):
    estimates = []
    for a in ARMS:
        obs = [h for h in history if h['choice']==a and not h['timed_out']][-24:]
        rewards = [h['outcome'] for h in obs]
        outcomes = [1 if x>0 else -1 if x<0 else 0 for x in rewards]
        counts = Counter(outcomes); n = len(outcomes)
        probs = {str(k):round((counts[k]+1)/(n+3),6) for k in [-1,0,1]}
        mag = 100 if a.startswith('blue') else 200
        mean = mag*(probs['1']-probs['-1'])
        variance = max(0, mag*mag*(probs['1']+probs['-1'])-mean*mean)/(n+4)
        estimates.append({'arm':a, 'samples':n, 'reward_distribution':probs,
                          'estimated_value':round(mean,3), 'approximate_95_interval':[round(max(-mag,mean-1.96*math.sqrt(variance)),3),round(min(mag,mean+1.96*math.sqrt(variance)),3)],
                          'change':change_belief(outcomes,prior), 'evidence':[h['trial_id'] for h in obs]})
    return {'arms':estimates, 'unknown':['True reward probabilities','Actual change times','Unobserved outcomes'],
            'assumptions':['Symmetric Dirichlet(1,1,1) reward prior; rolling 24 observations per arm.',
                           'Change belief compares stationary vs one unknown split; it is not a recovered original/swapped state.',
                           'Intervals are approximate posterior intervals and reward noise is expected.']}

def calibrate(history):
    grid = []
    valid = [h for h in history if not h['timed_out']]
    for ap, am, b in product([0.15, 0.45, 0.75], [0.15, 0.45, 0.75], [0.5, 2, 5]):
        _, obs = rl(valid, ap, am, b)
        lp = sum((math.log(max(1e-12, x['choice_probability'])) for x in obs))
        grid.append((ap, am, b, lp))
    top = max((x[3] for x in grid))
    weights = [math.exp(x[3] - top) for x in grid]
    total = sum(weights)
    weights = [w / total for w in weights]
    result = {'task': 'MAB', 'samples': len(valid), 'model_version': VERSION, 'assumptions': ['Equal prior on 27 dual-learning-rate / softmax parameter combinations.', 'A coarse exploratory calibration; parameter estimates may be weakly identified.', 'Q values reset for the new task session; fitted parameters transfer only within MAB.']}
    for i, name in enumerate(['alpha_plus', 'alpha_minus', 'beta']):
        result[name] = sum((g[i] * w for g, w in zip(grid, weights)))
        vals = sorted(((g[i], w) for g, w in zip(grid, weights)))
        qs = []
        for cutoff in [0.025, 0.975]:
            acc = 0
            for v, w in vals:
                acc += w
                if acc >= cutoff:
                    qs.append(v)
                    break
        result[name + '_interval'] = qs
    result['evidence'] = [h['trial_id'] for h in valid]
    return result

def validate_event(event):
    fields(event, ['kind', 'trial_id', 'index'], ['options', 'score', 'points', 'target', 'remaining', 'block', 'multiplier', 'choice', 'outcome', 'timed_out', 'response_ms', 'score_after', 'points_after'])
    require(identity(event['trial_id']), 'Invalid trial identifier')
    require(type(event['index']) is int and 1 <= event['index'] <= 10000, 'Invalid trial index')
    require(event['kind'] in {'evaluation', 'feedback'}, 'Unknown event kind')
    common = ['kind', 'trial_id', 'index']
    if event['kind'] == 'evaluation':
        allowed = common + ['options', 'score']
        fields(event, allowed)
        opts = event['options']
        require(isinstance(opts, list), 'Options must be a list')
        require(len(opts) == 6, 'Wrong number of options')
        ids = []
        for o in opts:
            fields(o, ['id', 'key', 'outcomes'])
            require(o['id'] in ARMS, 'Unknown arm')
            require(o['outcomes'] == ([100, 0, -100] if o['id'].startswith('blue') else [200, 0, -200]), 'Invalid displayed outcomes')
            require(isinstance(o['key'], str) and o['key'] in {'1', '2', '3', '7', '8', '9'}, 'Invalid response key')
            ids.append(o['id'])
        require(len(set(ids)) == len(opts), 'Duplicate option')
        require(len({o['key'] for o in opts}) == len(opts), 'Duplicate key')
        require(number(event['score']), 'Invalid score')
    else:
        fields(event, common + ['choice', 'outcome', 'timed_out', 'response_ms'] + ['score_after'])
        require(type(event['timed_out']) is bool, 'timed_out must be boolean')
        require(event['choice'] in set(ARMS) | {'NO_RESPONSE'}, 'Invalid choice')
        require((event['choice'] == 'NO_RESPONSE') == event['timed_out'], 'Timeout inconsistent with choice')
        require(event['response_ms'] is None or number(event['response_ms'], 0, 60000), 'Invalid response time')
        require(number(event['outcome']), 'Invalid outcome')
        require(number(event['score_after']), 'Invalid resulting score')

def validate_transition(session,event,h,evaluations):
    if event['kind']=='evaluation':
        require(all((o['key'] == KEYS[o['id']] for o in event['options'])), 'Incorrect arm/key mapping')
        require(event['score'] == (h[-1]['score_after'] if h else 0), 'Score inconsistent with prior feedback')
    else:
        ev = evaluations[-1]
        outcome = -200 if event['timed_out'] else event['outcome']
        option = next((o for o in ev['options'] if o['id'] == event['choice']), None)
        require(event['timed_out'] and event['outcome'] == -200 or (option and event['outcome'] in option['outcomes']), 'Impossible reward')
        require(event['score_after'] == ev['score'] + outcome, 'Score arithmetic mismatch')

def hypothesis_inputs(session,evaluation,environment,h):
    p=session['policy']
    window=[x for x in h[-p['window_trials']:] if same_scope(x,evaluation)]
    valid=[x for x in window if not x['timed_out']]
    evidence=[x['trial_id'] for x in valid]
    choices = [x['choice'] for x in valid]
    last = choices[-1] if choices else None
    sampled = set((x['choice'] for x in h if not x['timed_out']))
    stay = sum((a == b for a, b in zip(choices, choices[1:]))) / max(1, len(choices) - 1)
    profile = session.get('calibration_profile') or {}
    q, updates = rl(h, profile.get('alpha_plus', 0.3), profile.get('alpha_minus', 0.3), profile.get('beta', 2))
    model_mismatch = bool(last and q[last] < max(q.values()) - 0.1)
    choice_compatibility = updates[-1]['choice_probability'] if updates else None
    arm = next((a for a in environment['arms'] if a['arm'] == last), None)
    rewards = [x['outcome'] / 200 for x in valid if x['choice'] == last]
    decline = len(rewards) >= 6 and sum(rewards[:3]) / 3 - sum(rewards[-3:]) / 3 >= p['decline_threshold']
    change = bool(arm and arm['change']['posterior'] >= 0.3)
    switches_after_loss = sum((valid[i - 1]['outcome'] < 0 and valid[i]['choice'] != valid[i - 1]['choice'] for i in range(1, len(valid))))
    definitions = [('underexploration', len(sampled) <= 2, stay >= 0.75, len(h) >= p['min_evidence'], 'Limited sampling may leave useful alternatives unexplored.', ['Persistence may be justified by rewards or an intentional strategy.', 'The cost of exploration depends on the remaining horizon.'], ['Sampling additional alternatives weakens this interpretation.', 'An attributed participant explanation can contest this account.']), ('premature_exploitation', decline and change, stay >= 0.75 and model_mismatch, bool(decline), 'Persistence may merit reconsideration after declining feedback.', ['Noisy rewards can explain the apparent decline.', 'Estimated values may not match the participant’s own beliefs.'], ['A recovered reward pattern weakens change evidence.', 'Switching or an explicit rationale revises the persistence interpretation.']), ('feedback_overweighting', switches_after_loss >= 2, stay < 0.5, len(valid) >= 6, 'Recent switching after losses may over-weight individual outcomes.', ['Switching may be planned exploration.', 'Several outcomes may contain valid evidence of change.'], ['Sustained sampling or an explanation of planned exploration weakens this interpretation.'])]
    stats = {'sampled_arms': sorted(sampled), 'stay_rate': round(stay, 4), 'switches_after_loss': switches_after_loss, 'evidence_window': evidence, 'rl_choice_compatibility': choice_compatibility, 'rl_value_mismatch': model_mismatch}
    return definitions,stats

def contribute_candidates(session,ev,env,h,stats,estimated,socratic,existing,candidate):
    p=session['policy']
    sampled = stats['sampled_arms']
    shift = max((a['change']['posterior'] for a in env['arms'] if a['samples'] >= 6), default=0)
    if shift >= 0.3:
        candidate('possible_change', 'ask' if socratic else 'explain', ['Recent feedback may differ from earlier feedback. What evidence would justify checking another option?', 'Noise and a change are both plausible. What further feedback would help you distinguish them?'] if socratic else ['Recent feedback may differ from earlier feedback. Compare alternatives while accounting for reward noise.'], [estimated['id']], 'Observed outcome history raises uncertain evidence of change.', 'Ordinary reward noise remains a competing explanation.', 0.72)
    if len(h) >= p['min_evidence'] and len(sampled) < 6:
        candidate('unsampled_alternatives', 'request-evidence' if socratic else 'explain', ['Some alternatives remain lightly sampled. What remains unknown, and how much exploration is worthwhile?'] if socratic else ['Some alternatives remain lightly sampled. Consider gathering more evidence about them.'], [estimated['id']], 'Observed choices leave some reward estimates uncertain.', 'Further exploration has a cost and persistence may be justified.', 0.61)
    if socratic and len(h) >= p['min_evidence'] and (not existing):
        candidate('support_revision', 'support', ['Your approach may be reasonable given uncertain feedback. What evidence would make you revise it?'], [estimated['id']], 'No strong case for challenging the current pattern.', 'Support can still interrupt useful deliberation.', 0.56)

HYPOTHESIS_WORDING = {'underexploration': 'You have sampled few alternatives recently. What evidence supports continuing with the same option?', 'premature_exploitation': 'Your recent feedback has declined while your choice has persisted. What would justify revisiting another option?', 'feedback_overweighting': 'You have switched after recent losses. What would distinguish a useful switch from reacting to reward noise?'}

def hypothesis_message(name,socratic):
    wording=HYPOTHESIS_WORDING[name]
    if not socratic:wording=wording.split('. What')[0].split('. How')[0]+'. Consider reviewing this pattern against the available task evidence.'
    return wording

def summarize(session,h,valid):
    result={}
    choices = [x['choice'] for x in valid]
    result.update({'final_score': h[-1]['score_after'] if h else 0, 'sampled_arms': len(set(choices)), 'switch_rate': sum((a != b for a, b in zip(choices, choices[1:]))) / (len(choices) - 1) if len(choices) > 1 else None, 'regret': None, 'regret_reason': 'Needs hidden evaluator probabilities, which are absent from the teammate store.'})
    return result

