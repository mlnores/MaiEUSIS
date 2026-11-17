"""Execution extensions for registered environments; no task-specific algorithms."""
import hashlib
from pathlib import Path
from typing import Protocol
from ..records import require


class SimulationAdapter(Protocol):
    VERSION: str
    METRICS: dict
    def validate_actor(parameters): ...
    def baseline(history,parameters,evaluation): ...
    def reconsider(history,parameters,evaluation,intervention): ...
    def make_environment(protocol,seed,random_source): ...
    def describe(): ...


class EnvironmentRuntime(Protocol):
    seed: str
    @property
    def done(self) -> bool: ...
    def evaluation(self, session_id, index): ...
    def outcome(self, evaluation, choice): ...
    def metrics(self): ...
    def evaluator_state(self): ...


def simulation_adapter(module):
    hook=getattr(module,'simulation_adapter',None)
    require(callable(hook),'Environment '+module.ID+' has no simulation adapter')
    adapter=hook()
    require(all(callable(getattr(adapter,n,None)) for n in ['validate_actor','baseline','reconsider','make_environment','describe']),
            'Incomplete simulation adapter for '+module.ID)
    require(isinstance(adapter.METRICS,dict) and bool(adapter.METRICS),'Environment needs declared outcome metrics')
    for key,value in adapter.METRICS.items():
        require(isinstance(key,str) and isinstance(value,dict) and value.get('direction') in {'maximize','minimize'}
                and isinstance(value.get('unit'),str) and bool(value['unit']),'Invalid outcome metric')
    return adapter


def describe_adapter(version,path,metrics):
    return {'version':version,'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'metrics':metrics}


def normalise(values):
    total=sum(values.values());require(total>0,'Cannot normalise an empty distribution')
    return {a:v/total for a,v in values.items()}


def validate_distribution(values,options):
    from ..records import number
    require(isinstance(values,dict) and set(values)=={o['id'] for o in options},'Actor distribution must cover the current options')
    require(all(number(p,0,1) for p in values.values()) and abs(sum(values.values())-1)<1e-8,'Invalid actor probabilities')
    return dict(values)
