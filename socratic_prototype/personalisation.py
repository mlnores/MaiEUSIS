"""Model-based delivery estimates; argument validity and task ranking stay separate."""
from .tasks import get_task
from .learning import summary
from .records import require,fields,number
import hashlib
import json

VERSION='observed-personalisation-0.1'
DEFAULTS={'min_task_choices':6,'min_informative_exposures':6,'redundancy_probability':.85,
          'low_uptake_upper':.25,'low_uptake_extra_cooldown':3,'uptake_discount_limit':.25}


def settings(policy):
    result={**DEFAULTS,**policy.get('personalisation',{})}
    fields(result,list(DEFAULTS))
    for k in ('min_task_choices','min_informative_exposures','low_uptake_extra_cooldown'):
        require(type(result[k]) is int and result[k]>=0,'Invalid personalisation evidence/cooldown setting')
    require(result['min_task_choices']>=1 and result['min_informative_exposures']>=1,'Personalisation needs observations')
    require(number(result['redundancy_probability'],.5,1) and number(result['low_uptake_upper'],0,.5),
            'Invalid personalisation probability setting')
    require(number(result['uptake_discount_limit'],0,.5),'Invalid uptake discount limit')
    return result


def forecast_source(state,person):
    model={k:person[k] for k in ('online_task','interaction','calibration','delivery_settings','model_version')}
    digest=hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return state+'/participant-forecast/'+digest


def scheduling_proofs(snapshot):
    from .argumentation import ARG
    report=snapshot['graph_argumentation'];assertions={a['id']:a for a in report['assertions']}
    if report['status']!='complete':return []
    source=forecast_source(report['scope'],snapshot['participant'])
    return sorted(a['id'] for a in report['arguments'] if a['label']=='accepted' and a['rule']==ARG+'forecastScheduling' and
                  assertions[a['conclusion']]['proposition']['predicate']==ARG+'mayPersonaliseDelivery' and
                  any(assertions[p]['source']==source and assertions[p]['proposition']['predicate']==ARG+'hasBehaviouralForecast'
                      for p in a['premises']))


def assess(task,condition,evaluation,snapshot,candidate):
    """Same conservative rule, with common defaults in C/D and learned inputs in E/F.

    The response-distance bound estimates how much a prompt could change the
    choice distribution. It is not a prediction of improved reward or wellbeing.
    Upper bounds prevent weak evidence from suppressing assistance prematurely.
    """
    common={'version':VERSION,'enabled':False,'relevance_factor':1.,'uptake_factor':1.,
            'redundant':False,'extra_cooldown':0,'argument_ids':[],
            'reason':'Common delivery defaults; no usable participant forecast.'}
    hook=getattr(get_task(task),'assistance_target',None)
    model=snapshot['participant'].get('online_task',{})
    if condition not in {'E','F'} or not hook or not model.get('prediction'):return common
    proofs=scheduling_proofs(snapshot)
    if not proofs:return common
    from .recommendations import structured
    intervention=structured(task,condition,candidate)
    uniform={o['id']:1/len(evaluation['options']) for o in evaluation['options']}
    target=hook(evaluation,uniform,intervention)
    if target is None:return common
    reference=.5*sum(abs(uniform[a]-target[a]) for a in uniform)
    distances=[];weights=[]
    for hypothesis in model['choice_hypotheses']:
        p=hypothesis['probabilities'];q=hook(evaluation,p,intervention)
        if q is None:return common
        distances.append(.5*sum(abs(p[a]-q[a]) for a in p));weights.append(hypothesis['weight'])
    movement=summary(distances,weights)
    config=snapshot['participant']['delivery_settings']
    calibration=snapshot['participant'].get('calibration',{})
    transferred=calibration.get('samples',calibration.get('policy',{}).get('samples',0)) if model['calibration_posterior_transferred'] else 0
    samples=transferred+model['choice_updates']
    enough=samples>=config['min_task_choices']
    upper=movement['interval'][1]
    relevance=min(1.,upper/reference) if enough and reference>1e-12 else 1.
    redundant=enough and upper<=1-config['redundancy_probability']
    uptake=snapshot['participant']['interaction'][intervention['style']]
    identified=uptake['informative']>=config['min_informative_exposures']
    # High inferred uptake never earns an automatic personalisation bonus.
    uptake_factor=1-config['uptake_discount_limit']*(1-min(1.,uptake['interval'][1]/.5)) if identified else 1.
    low=identified and uptake['interval'][1]<=config['low_uptake_upper']
    return {**common,'enabled':True,'argument_ids':proofs,'relevance_factor':relevance,
            'uptake_factor':uptake_factor,'redundant':redundant,
            'extra_cooldown':config['low_uptake_extra_cooldown'] if low else 0,
            'task_choice_samples':samples,'task_model_sufficient':enough,'response_distance':movement,
            'common_response_distance':reference,'uptake_sufficient':identified,
            'uptake_mean':uptake['mean'],'uptake_interval':uptake['interval'],
            'evidence':sorted(set(model['choice_evidence']+model['outcome_evidence']+uptake['evidence'])),
            'reason':'Likely redundant under the task model.' if redundant else
                     'Low model-based uptake: wait longer for a stronger opportunity.' if low else
                     'Delivery relevance uses conservative response-distance and uptake bounds.',
            'limits':'Conditional on coarse task/processing models; neither acceptance of the argument nor causal assistance benefit.'}


def project_forecast(add,writer,state,session,snapshot):
    """Structured, versioned, attributed graph inputs for scheduling only."""
    from rdflib import Literal
    from .semantics import CORE
    from .argumentation import ARG
    person=snapshot['participant'];model=person.get('online_task',{})
    if session['condition'] not in {'E','F'} or not model.get('prediction'):return
    source=forecast_source(state,person);writer.types(source,'arg:BehaviouralForecast')
    writer.obj(source,'arg:inState',state);writer.value(source,'arg:version',person['model_version'])
    writer.value(source,'arg:modelDigest',source.rsplit('/',1)[-1])
    writer.value(source,'core:status','inferred')
    writer.obj(source,'task:forTrial',CORE+model['prediction_for_trial'])
    writer.value(source,'arg:reason','Conditional public-observation model; not a measured belief or intention.')
    writer.value(source,'arg:observerVersion',model['version'])
    for identifier in model['choice_evidence']+model['outcome_evidence']:
        writer.obj(source,'arg:evidenceEvent',CORE+identifier)
    calibration=person.get('calibration',{})
    for trial in calibration.get('evidence',calibration.get('policy',{}).get('evidence',[])):
        writer.obj(source,'arg:calibrationTrial',CORE+trial)
    add(state,ARG+'hasBehaviouralForecast',Literal(True),'estimate',source,
        'A task-owned uncertain forecast is available for personalised delivery; it does not warrant a task recommendation.')
    add(source,ARG+'unaidedChoiceUpdates',Literal(model['choice_updates']),'calculation',source)
    writer.value(source,'arg:unaidedChoiceUpdates',model['choice_updates'])
    for option,estimate in model['prediction'].items():
        node=source+'/option/'+option;writer.types(node,'arg:ChoiceForecast')
        writer.obj(node,'arg:inState',state);writer.value(node,'arg:optionID',option)
        writer.obj(node,'arg:source',source);writer.value(node,'core:status','inferred')
        for predicate,value in [('probabilityMean',estimate['mean']),('probabilityLower',estimate['interval'][0]),
                                ('probabilityUpper',estimate['interval'][1])]:
            add(node,ARG+predicate,Literal(value),'estimate',source)
            writer.value(node,'arg:'+predicate,value)
    for style in ['direct','socratic']:
        uptake=person['interaction'][style];node=source+'/uptake/'+style
        writer.types(node,'arg:UptakeEstimate');writer.obj(node,'arg:inState',state)
        writer.value(node,'arg:style',style);writer.value(node,'arg:version',person['model_version'])
        writer.value(node,'core:status','inferred' if uptake['informative'] else 'assumed')
        for identifier in uptake['evidence']:writer.obj(node,'arg:evidenceEvent',CORE+identifier)
        kind='estimate' if uptake['informative'] else 'assumption'
        for predicate,value in [('probabilityMean',uptake['mean']),('probabilityLower',uptake['interval'][0]),
                                ('probabilityUpper',uptake['interval'][1])]:
            add(node,ARG+predicate,Literal(value),kind,node)
            writer.value(node,'arg:'+predicate,value)
        add(node,ARG+'informativeExposures',Literal(uptake['informative']),'calculation',node)
        writer.value(node,'arg:informativeExposures',uptake['informative'])
