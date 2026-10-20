"""Estimates from permitted observations, with task-specific calibration."""
import math
from collections import Counter
from itertools import product

VERSION = 'models-0.1'
ARMS = ('blue1','blue2','blue3','red1','red2','red3')
KEYS = {'blue1':'8','blue2':'1','blue3':'3','red1':'2','red2':'7','red3':'9'}


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


def calibration_profile(task, history):
    if task=='TBS':return {'task':task,'model_version':VERSION,'policy':tbs_pressure_model(history)}
    grid=[]
    valid=[h for h in history if not h['timed_out']]
    for ap,am,b in product([.15,.45,.75],[.15,.45,.75],[.5,2,5]):
        _,obs=rl(valid,ap,am,b)
        lp=sum(math.log(max(1e-12,x['choice_probability'])) for x in obs)
        grid.append((ap,am,b,lp))
    top=max(x[3] for x in grid); weights=[math.exp(x[3]-top) for x in grid]; total=sum(weights); weights=[w/total for w in weights]
    result={'task':task,'samples':len(valid),'model_version':VERSION,'assumptions':['Equal prior on 27 dual-learning-rate / softmax parameter combinations.', 'A coarse exploratory calibration; parameter estimates may be weakly identified.', 'Q values reset for the new task session; fitted parameters transfer only within MAB.']}
    for i,name in enumerate(['alpha_plus','alpha_minus','beta']):
        result[name]=sum(g[i]*w for g,w in zip(grid,weights))
        vals=sorted((g[i],w) for g,w in zip(grid,weights)); qs=[]
        for cutoff in [.025,.975]:
            acc=0
            for v,w in vals:
                acc+=w
                if acc>=cutoff:qs.append(v);break
        result[name+'_interval']=qs
    result['evidence']=[h['trial_id'] for h in valid]
    return result
