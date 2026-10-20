"""TBS mechanics and calculation provenance. Arithmetic stays in the Python model."""
from ..semantics import CORE,DATA,project_observations
from . import tbs


def project(w,session,event,state,evaluation,previous):
    definition=w.definition(session,tbs);base=definition+'/'
    ev_rule=w.rule(base+'expected-gain','Immediate expected gain',
        'socratic_prototype.tasks.tbs.tbs_context',tbs.MODULE_VERSION,'Displayed probability times displayed gain; not final attainment.')
    final_rule=w.rule(base+'final-attainment','Conditional final-trial attainment',
        'socratic_prototype.tasks.tbs.tbs_context',tbs.MODULE_VERSION,'Final trial only; multiplier applies after a win, not after no gain.')
    for rule in [ev_rule,final_rule]:w.obj(definition,'task:hasRule',rule)
    block=DATA+session['id']+'/block/'+str(evaluation['block']);goal=block+'/goal';rule=block+'/multiplier'
    if w.once(block):
        w.types(block,'tbs:Block')
        w.value(block,'tbs:blockIndex',evaluation['block'])
        w.obj(block,'tbs:inSession',CORE+session['id'])
        w.types(goal,'tbs:TargetGoal','task:Goal')
        w.value(goal,'tbs:target',evaluation['target'])
        w.obj(block,'task:hasGoal',goal)
        w.rule(rule,'Block final-win multiplier','socratic_prototype.tasks.tbs.tbs_context',
               tbs.MODULE_VERSION,'remaining choices = 1 AND final gain > 0')
        w.types(rule,'tbs:FinalWinMultiplierRule')
        w.value(rule,'tbs:multiplier',evaluation['multiplier'])
        w.value(rule,'tbs:appliesOnFinalWin',True)
        w.value(rule,'tbs:requiredRemainingChoices',1)
        w.value(rule,'tbs:requiresPositiveGain',True)
        w.value(rule,'task:expression','if remaining == 1 and gain > 0: (points + gain) * multiplier; otherwise points + gain')
        w.obj(block,'task:hasRule',rule)
    snap=event['snapshot'];env=snap['environment'];inp=event['input']
    w.state(session,event,state,'tbs:TargetState',previous)
    w.obj(state,'tbs:inBlock',block);w.obj(state,'task:hasGoal',goal)
    values=env.get('after_feedback') if inp['kind']=='feedback' else None
    points=values['points'] if values else evaluation['points']
    gap=values['target_gap'] if values else env['target_gap']
    remaining=values['remaining'] if values else env['remaining']
    w.value(state,'tbs:points',points);w.value(state,'tbs:targetGap',gap)
    w.value(state,'tbs:remainingChoices',remaining);w.value(state,'tbs:multiplier',evaluation['multiplier'])
    option=lambda identifier:DATA+evaluation['trial_id']+'/option/'+identifier
    for o in env['options']:
        iri=option(o['id'])
        if w.once(iri):
            w.types(iri,'tbs:GambleOption','task:Option')
            w.value(iri,'task:label',o['id'])
            w.value(iri,'tbs:displayedGain',o['amount'])
            w.value(iri,'tbs:displayedWinProbability',o['probability'])
            w.obj(iri,'task:displayedIn',CORE+evaluation['trial_id'])
        w.obj(state,'task:hasOption',iri)
        # The snapshot's option calculations describe pre-choice state. Do not
        # misattribute them to the post-feedback points/horizon.
        if inp['kind']!='evaluation':continue
        calc=state+'/expected-gain/'+o['id']
        w.calculation(calc,'tbs:ExpectedGainCalculation',state,ev_rule,o['expected_value'],'points',iri)
        w.obj(CORE+event['id']+'_environment','task:basedOnCalculation',calc)
        if env['remaining']==1:
            win=state+'/win-score/'+o['id']
            w.calculation(win,'tbs:FinalWinScoreCalculation',state,final_rule,o['final_trial_win_score'],'points',iri)
            w.obj(win,'task:usesRule',rule)
            chance=state+'/attainment/'+o['id']
            w.calculation(chance,'tbs:AttainmentCalculation',state,final_rule,o['final_trial_target_probability'],'probability',iri)
            w.obj(chance,'task:usesRule',rule)
            w.obj(chance,'task:basedOnCalculation',win)
            w.obj(CORE+event['id']+'_environment','task:basedOnCalculation',chance)
    if values:
        w.value(state,'tbs:multiplierApplied',values['multiplier_applied'])
        if values['multiplier_applied']:
            calc=state+'/final-total'
            w.calculation(calc,'tbs:FinalTotalCalculation',previous,rule,points,'points')
            w.obj(calc,'task:basedOnObservation',DATA+inp['trial_id']+'/outcome')
            w.obj(state,'task:basedOnCalculation',calc)
    # The pressure policy is explicitly estimated, not an observed disposition.
    model=state+'/pressure-model';estimate=snap['participant']['pressure_policy']
    w.types(model,'tbs:PressurePolicyEstimate','task:Estimate','task:Calculation')
    pressure_rule=w.rule(base+'pressure-policy','Exploratory grid pressure policy',
        'socratic_prototype.tasks.tbs.tbs_pressure_model',tbs.MODULE_VERSION,'Equal grid priors; option-value and horizon effects are not separately identified.')
    w.obj(model,'task:inputState',state);w.obj(model,'task:usesRule',pressure_rule)
    w.value(model,'task:value',estimate['sensitivity_mean']);w.value(model,'task:unit','normalised-pressure-sensitivity')
    w.value(model,'task:samples',estimate['samples']);w.value(model,'s:status','inferred')
    w.value(model,'task:lowerBound',estimate['sensitivity_interval'][0]);w.value(model,'task:upperBound',estimate['sensitivity_interval'][1])
    for trial in estimate.get('evidence',[]):w.obj(model,'task:basedOnObservation',DATA+trial+'/choice')
    project_observations(w,session,event,evaluation,option,'points')
