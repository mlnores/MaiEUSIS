"""Synthetic actors delegate environment-specific decisions to registered adapters."""
import copy
from .records import fields,require,identity,number
from .tasks import get_task
from .tasks.execution import simulation_adapter,validate_distribution
from .assistance_response import apply,validate,SCENARIOS
from .reconsideration import configuration as reconsideration_configuration, target as reconsideration_target

VERSION='synthetic-agent-0.4'


def validate_participant(spec,tasks=None):
    fields(spec,['id','source','task_models'],['response_parameters','original_profile','provenance','baseline_omission'])
    require(identity(spec['id']),'Invalid participant pseudonym')
    require(isinstance(spec['source'],str) and bool(spec['source']),'Specify parameter provenance')
    require('provenance' not in spec or isinstance(spec['provenance'],dict),'Invalid researcher-side actor provenance')
    models=spec['task_models'];require(isinstance(models,dict) and bool(models),'Provide environment-keyed task models')
    omissions=spec.get('baseline_omission',{})
    require(isinstance(omissions,dict) and omissions.keys()<=models.keys() and all(number(p,0,1) for p in omissions.values()),'Invalid baseline omission model')
    require(set(tasks or models)<=models.keys(),'Participant lacks a model for a study environment')
    for task,parameters in models.items():simulation_adapter(get_task(task)).validate_actor(parameters)
    responses=spec.get('response_parameters',{})
    require(isinstance(responses,dict) and responses.keys()<=models.keys(),'Unknown response-parameter environment')
    for styles in responses.values():
        fields(styles,['direct','socratic'])
        for value in styles.values():validate(value)
    return copy.deepcopy(spec)


class Participant:
    def __init__(self,spec,task,scenario='null',reconsideration='current'):
        self.spec=validate_participant(spec,[task]);self.module=get_task(task);self.adapter=simulation_adapter(self.module)
        self.task=task;self.history=[];require(scenario in SCENARIOS,'Unknown assistance response scenario');self.scenario=scenario
        self.reconsideration=reconsideration
        self.reconsideration_configuration=reconsideration_configuration(self.module,reconsideration)
    def baseline(self,ev):
        return validate_distribution(self.adapter.baseline(self.history,self.spec['task_models'][self.task],ev),ev['options'])
    def reconsider(self,ev,intervention,baseline=None):
        return reconsideration_target(self.module,self.reconsideration,self.history,self.spec['task_models'][self.task],ev,intervention,
                                      self.baseline(ev) if baseline is None else baseline)
    def distribution(self,ev,intervention):
        baseline=self.baseline(ev)
        omission=self.spec.get('baseline_omission',{}).get(self.task,0.)
        if not intervention:return baseline,baseline,{'applied':False,'omission_probability':omission}
        style=intervention['style']
        parameters=SCENARIOS['null'][style] if self.scenario=='null' else self.spec.get('response_parameters',{}).get(self.task,{}).get(style,SCENARIOS[self.scenario][style])
        # Direct recommendations never invoke a Socratic processor.
        is_question=style=='socratic'
        reconsidered=self.reconsider(ev,intervention,baseline) if is_question else baseline
        result,effect=apply(baseline,intervention,parameters,reconsidered,
                            strategic_revision=not is_question or self.reconsideration!='none')
        if is_question:effect['reconsideration_mechanism']=self.reconsideration
        effect['omission_probability']=omission+(1-omission)*effect['omission_probability']
        return baseline,validate_distribution(result,ev['options']),effect
    def observe(self,ev,feedback):self.history.append({**feedback,**self.module.history_context(ev)})
