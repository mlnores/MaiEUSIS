"""MAB mechanics projection. No generative probabilities or actual shift times."""
from ..semantics import CORE,DATA,project_observations
from . import mab


def project(w,session,event,state,evaluation,previous):
    definition=w.definition(session,mab);base=definition+'/'
    value_rule=w.rule(base+'dirichlet','Rolling Dirichlet reward estimate',
        'socratic_prototype.tasks.mab.mab_environment',mab.MODULE_VERSION,'Only sampled, non-timeout outcomes; last 24 per arm.')
    change_rule=w.rule(base+'change','Stationary versus unknown-split comparison',
        'socratic_prototype.tasks.mab.change_belief',mab.MODULE_VERSION,'At least six observations for evidence beyond the prior.')
    learning_rule=w.rule(base+'learning','Dual-rate reward learning',
        'socratic_prototype.tasks.mab.rl',mab.MODULE_VERSION,'Non-timeout outcomes; rewards normalised by 200.')
    for rule in [value_rule,change_rule,learning_rule]:w.obj(definition,'task:hasRule',rule)
    if w.once(base+'parameters'):
        w.value(value_rule,'mab:priorCount',1);w.value(value_rule,'mab:windowSamples',24)
        w.value(learning_rule,'mab:rewardScale',200)
    arm=lambda identifier:base+'arm/'+identifier
    for identifier in mab.ARMS:
        iri=arm(identifier)
        if w.once(iri):
            w.types(iri,'mab:BanditArm','task:Option')
            w.value(iri,'task:label',identifier)
            w.value(iri,'mab:rewardMagnitude',100 if identifier.startswith('blue') else 200)
            w.obj(definition,'task:hasOption',iri)
    snap=event['snapshot'];w.state(session,event,state,'mab:BanditState',previous)
    w.value(state,'mab:score',event['input'].get('score_after',evaluation['score']))
    for a in snap['environment']['arms']:
        option=arm(a['arm']);w.obj(state,'task:hasOption',option)
        estimate=state+'/reward/'+a['arm']
        w.calculation(estimate,'mab:RewardBelief',state,value_rule,a['estimated_value'],'reward-points',option,True)
        w.value(estimate,'task:samples',a['samples'])
        w.value(estimate,'task:lowerBound',a['approximate_95_interval'][0])
        w.value(estimate,'task:upperBound',a['approximate_95_interval'][1])
        for key,predicate in [('-1','mab:estimatedLossProbability'),('0','mab:estimatedZeroProbability'),('1','mab:estimatedGainProbability')]:
            w.value(estimate,predicate,a['reward_distribution'][key])
        change=state+'/change/'+a['arm']
        w.calculation(change,'mab:ChangeEstimate',state,change_rule,a['change']['posterior'],'probability',option,True)
        w.value(change,'task:samples',a['change']['samples'])
        w.value(change,'mab:evidenceLevel',a['change']['evidence'])
        for trial in a['evidence']:
            w.obj(estimate,'task:basedOnObservation',DATA+trial+'/outcome')
            w.obj(change,'task:basedOnObservation',DATA+trial+'/outcome')
        w.obj(CORE+event['id']+'_environment','task:basedOnCalculation',estimate)
        w.obj(CORE+event['id']+'_environment','task:basedOnCalculation',change)
    # Q is an estimate under recorded parameters, never the participant's conscious belief.
    person=snap['participant'];model=state+'/learning-model'
    w.types(model,'mab:LearningModel')
    w.value(model,'task:version',mab.MODULE_VERSION)
    w.value(model,'mab:calibrated',bool(session.get('calibration_profile')))
    for key,predicate in [('alpha_plus','mab:alphaPlus'),('alpha_minus','mab:alphaMinus'),('beta','mab:softmaxSensitivity')]:
        w.value(model,predicate,person['parameters'][key])
    for identifier,value in person['q'].items():
        estimate=state+'/learned/'+identifier
        w.calculation(estimate,'mab:LearnedValue',state,learning_rule,value,'reward/200',arm(identifier),True)
        w.obj(estimate,'mab:learningModel',model)
        for record in session['events']:
            obs=record['input']
            if obs.get('kind')!='feedback' or obs['timed_out'] or obs['choice']!=identifier:continue
            if obs['index']<event['input']['index'] or (event['input']['kind']=='feedback' and obs['index']==event['input']['index']):
                w.obj(estimate,'task:basedOnObservation',DATA+obs['trial_id']+'/outcome')
    project_observations(w,session,event,evaluation,arm,'reward-points')
