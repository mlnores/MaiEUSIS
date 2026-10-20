"""Task contract and small helpers; no MAB/TBS mechanics belong in this layer."""
import copy
import hashlib
from pathlib import Path
from typing import Protocol
from ..records import fields,require,identity

MODEL_VERSION='models-0.1'  # Numerical algorithms are unchanged by the module split.
SCHEMA_VERSION='ontology-0.2'


class TaskModule(Protocol):
    ID: str
    NAMESPACE: str
    MODULE_VERSION: str
    ONTOLOGY_VERSION: str
    ELIGIBLE_POINT: str
    PROTOCOLS: dict

    def describe(self): ...
    def documents(self): ...
    def task_rules(self): ...
    def calibrate(self,history): ...
    def validate_event(self,event): ...
    def validate_transition(self,session,event,history,evaluations): ...
    def environment(self,history,evaluation,policy,event): ...
    def participant(self,history,profile): ...
    def hypothesis_inputs(self,session,evaluation,environment,history): ...
    def hypothesis_message(self,name,socratic): ...
    def same_scope(self,event,evaluation): ...
    def scope_suffix(self,evaluation): ...
    def environment_claim(self,environment): ...
    def history_context(self,evaluation): ...
    def evidence_environment(self,environment): ...
    def evidence_participant(self,participant): ...
    def evidence_observation(self,observation): ...
    def summarize(self,session,history,valid): ...
    def project_rdf(self,writer,session,event,state,evaluation,previous): ...


class ArgumentationSchemes(Protocol):
    """Optional extension, separate from the required TaskModule contract."""
    def argumentation_documents(self): ...


class ArgumentationFacts(Protocol):
    """Optional task-specific public-history aggregates for graph reasoning."""
    def project_argumentation_facts(self,writer,session,event,state,history): ...


def document_paths(identifier):
    root=Path(__file__).resolve().parents[1]/'ontology'
    return (root/'schema.ttl',root/'task.ttl',root/(identifier.lower()+'.ttl'),
            root/'shapes.ttl',root/'task-shapes.ttl',root/(identifier.lower()+'-shapes.ttl'))


def describe_task(identifier,namespace,version,ontology_version,documents=None):
    paths=document_paths(identifier) if documents is None else tuple(p for group in documents for p in group)
    return {'id':identifier,'namespace':namespace,'version':version,
            'ontology_version':ontology_version,'definition_iri':namespace+'definition/'+version,
            'shared_ontology_version':'task-ontology-0.1','core_ontology_version':SCHEMA_VERSION,
            'document_digests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def pick(data,keys):
    return {k:copy.deepcopy(data[k]) for k in keys if k in data}


def validate_envelope(event):
    require(isinstance(event,dict),'Expected an event object')
    require(identity(event.get('trial_id')),'Invalid trial identifier')
    require(type(event.get('index')) is int and event['index']>=1,'Invalid trial index')


def common_observation(history):
    return pick(history,['trial_id','choice','outcome','timed_out','target','remaining','points_before'])
