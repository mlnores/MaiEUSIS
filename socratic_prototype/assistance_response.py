"""Explicit simulation assumptions about assistance, not estimated human attitudes."""
from .records import fields,require,number

VERSION='assistance-response-0.3'
DEFAULT={'responsiveness':0.0,'reactance':0.0,'distraction':0.0,'omission_probability':0.0}
SCENARIOS={
    'null':{'direct':dict(DEFAULT),'socratic':dict(DEFAULT)},
    'responsive':{style:{**DEFAULT,'responsiveness':.5} for style in ['direct','socratic']},
    'interference':{style:{**DEFAULT,'responsiveness':.25,'reactance':.5,'distraction':.2,'omission_probability':.05} for style in ['direct','socratic']},
}


def validate(parameters):
    fields(parameters,list(DEFAULT))
    require(all(number(v,0,1) for v in parameters.values()),'Response parameters must be finite probabilities')
    return dict(parameters)


def conditional_preferences(base,options):
    """The same rule for a direct singleton and a profile-weighted option set."""
    ids=set(options)
    require(bool(ids) and ids<=set(base),'Guidance contains an unavailable action')
    mass=sum(value for a,value in base.items() if a in ids)
    # A singleton is a point target even when its baseline probability is zero.
    # A zero-mass set has no relative preference information: use equal weights.
    return {a:(base[a]/mass if mass>0 else 1/len(ids)) if a in ids else 0. for a in base}


def apply(base,intervention,parameters,reconsidered):
    """Both styles share the same response mechanism but different processing targets.

    Direct: consider the recommended action. Socratic: reconsider the named issue
    from public evidence, which may reaffirm the original action. No LLM reading
    ability, conscious intent or beneficial causal effect is implied.
    """
    parameters=validate(parameters)
    if not intervention:return dict(base),{'applied':False,'omission_probability':0.0}
    style=intervention['style'];require(style in {'direct','socratic'},'Unknown intervention style')
    if style=='direct':
        option=intervention['recommendation']['option_id']
        target=conditional_preferences(base,[option])
    else:target=reconsidered
    require(set(target)==set(base) and abs(sum(target.values())-1)<1e-8,'Invalid reconsideration distribution')
    processing_target=dict(target)
    # Reactance reverses the processing target; distraction mixes in uniform noise.
    r=parameters['reactance'];n=len(base)
    opposite={a:(1-target[a])/(n-1) if n>1 else 1.0 for a in base}
    target={a:(1-r)*target[a]+r*opposite[a] for a in base}
    weight=parameters['responsiveness'];noise=parameters['distraction']
    revised={a:(1-weight)*base[a]+weight*target[a] for a in base}
    result={a:(1-noise)*revised[a]+noise/n for a in base}
    return result,{'applied':True,'style':style,'parameters':parameters,
                   'response_rule':'single-task-response','processing_target':processing_target,
                   'omission_probability':parameters['omission_probability'],
                   'notice':'Scenario assumption, not a measured human response or guaranteed benefit.'}
