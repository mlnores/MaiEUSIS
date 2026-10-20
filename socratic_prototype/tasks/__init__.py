"""Explicit task registry. HTTP input cannot import arbitrary Python modules."""
from ..records import require,identity
import re

_TASKS={}
_LOADED=False
_METHODS=('describe','documents','task_rules','calibrate','validate_event','validate_transition','environment',
          'participant','hypothesis_inputs','contribute_candidates','hypothesis_message','same_scope',
          'scope_suffix','environment_claim','history_context','evidence_environment',
          'evidence_participant','evidence_observation','summarize','project_rdf')


def register_task(module):
    require(identity(module.ID) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',module.ID),'Invalid task identifier')
    require(module.ID not in _TASKS,'Task is already registered')
    require(all(callable(getattr(module,name,None)) for name in _METHODS),'Task does not implement the task contract')
    require(bool(module.PROTOCOLS) and all(isinstance(k,str) and type(v) is int and v>0 for k,v in module.PROTOCOLS.items()),'Invalid task protocols')
    _TASKS[module.ID]=module


def _load():
    global _LOADED
    if not _LOADED:
        from . import mab,tbs
        register_task(mab);register_task(tbs);_LOADED=True


def get_task(identifier):
    _load()
    require(isinstance(identifier,str) and identifier in _TASKS,'Unknown task')
    return _TASKS[identifier]


def available_tasks():
    _load();return tuple(_TASKS)
