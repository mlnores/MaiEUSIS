"""Explicit simulation assumptions about assistance, not estimated human attitudes."""
from .records import fields,require,number

VERSION='assistance-response-0.1'
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
        require(option in base,'Recommendation is not an available action')
        target={a:float(a==option) for a in base}
    else:target=reconsidered
    require(set(target)==set(base) and abs(sum(target.values())-1)<1e-8,'Invalid reconsideration distribution')
    # Reactance reverses the processing target; distraction mixes in uniform noise.
    r=parameters['reactance'];n=len(base)
    opposite={a:(1-target[a])/(n-1) if n>1 else 1.0 for a in base}
    target={a:(1-r)*target[a]+r*opposite[a] for a in base}
    weight=parameters['responsiveness'];noise=parameters['distraction']
    result={a:(1-noise)*((1-weight)*base[a]+weight*target[a])+noise/n for a in base}
    return result,{'applied':True,'style':style,'parameters':parameters,
                   'omission_probability':parameters['omission_probability'],
                   'notice':'Scenario assumption, not a measured human response or guaranteed benefit.'}
