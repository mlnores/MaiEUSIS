"""Synthetic actors delegate environment-specific decisions to registered adapters."""
import copy
from .records import fields,require,identity
from .tasks import get_task
from .tasks.execution import simulation_adapter,validate_distribution
from .assistance_response import apply,validate,SCENARIOS

VERSION='synthetic-agent-0.2'


def validate_participant(spec,tasks=None):
    fields(spec,['id','source','task_models'],['response_parameters','original_profile'])
    require(identity(spec['id']),'Invalid participant pseudonym')
    require(isinstance(spec['source'],str) and bool(spec['source']),'Specify parameter provenance')
    models=spec['task_models'];require(isinstance(models,dict) and bool(models),'Provide environment-keyed task models')
    require(set(tasks or models)<=models.keys(),'Participant lacks a model for a study environment')
    for task,parameters in models.items():simulation_adapter(get_task(task)).validate_actor(parameters)
    responses=spec.get('response_parameters',{})
    require(isinstance(responses,dict) and responses.keys()<=models.keys(),'Unknown response-parameter environment')
    for styles in responses.values():
        fields(styles,['direct','socratic'])
        for value in styles.values():validate(value)
    return copy.deepcopy(spec)


class Participant:
    def __init__(self,spec,task,scenario='null'):
        self.spec=validate_participant(spec,[task]);self.module=get_task(task);self.adapter=simulation_adapter(self.module)
        self.task=task;self.history=[];require(scenario in SCENARIOS,'Unknown assistance response scenario');self.scenario=scenario
    def baseline(self,ev):
        return validate_distribution(self.adapter.baseline(self.history,self.spec['task_models'][self.task],ev),ev['options'])
    def reconsider(self,ev,intervention):
        return validate_distribution(self.adapter.reconsider(self.history,self.spec['task_models'][self.task],ev,intervention),ev['options'])
    def distribution(self,ev,intervention):
        baseline=self.baseline(ev)
        if not intervention:return baseline,baseline,{'applied':False,'omission_probability':0.0}
        style=intervention['style']
        parameters=SCENARIOS['null'][style] if self.scenario=='null' else self.spec.get('response_parameters',{}).get(self.task,{}).get(style,SCENARIOS[self.scenario][style])
        result,effect=apply(baseline,intervention,parameters,self.reconsider(ev,intervention))
        return baseline,validate_distribution(result,ev['options']),effect
    def observe(self,ev,feedback):self.history.append({**feedback,**self.module.history_context(ev)})
