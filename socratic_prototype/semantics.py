"""Shared RDF projection primitives. Task modules own their vocabulary and rules.

This writer needs no RDF package. OWL imports are resolved from explicit local
files by validation; neither projection nor validation fetches remote documents.
"""
import json
import math

CORE='https://example.org/socratic/'
TASK=CORE+'task/'
DATA=CORE+'data/'


class Writer:
    def __init__(self):
        self.lines=[];self.subjects=set();self.seen=set()

    def iri(self,value):
        if value.startswith(('http://','https://','urn:')):return '<'+value+'>'
        return value  # Only module-owned compact names enter this branch.

    def once(self,value):
        if value in self.seen:return False
        self.seen.add(value);return True

    def obj(self,subject,predicate,obj):
        self.subjects.add(subject)
        self.lines.append(f'{self.iri(subject)} {self.iri(predicate)} {self.iri(obj)} .')

    def value(self,subject,predicate,value):
        if value is None:return
        if isinstance(value,bool):literal='"'+str(value).lower()+'"^^xsd:boolean'
        elif type(value) is int:literal='"'+str(value)+'"^^xsd:integer'
        elif type(value) is float:
            if not math.isfinite(value):raise ValueError('Nonfinite RDF quantity')
            literal='"'+repr(value)+'"^^xsd:double'
        else:literal=json.dumps(str(value),ensure_ascii=False)
        self.subjects.add(subject)
        self.lines.append(f'{self.iri(subject)} {self.iri(predicate)} {literal} .')

    def types(self,subject,*classes):
        for cls in classes:self.obj(subject,'a',cls)

    def rule(self,identifier,label,implementation,version,condition=None):
        if self.once(identifier):
            self.types(identifier,'task:Rule')
            self.value(identifier,'task:label',label)
            self.value(identifier,'task:implementation',implementation)
            self.value(identifier,'task:version',version)
            self.value(identifier,'task:applicability',condition)
        return identifier

    def definition(self,session,module):
        definition=session['task_module']['definition_iri']
        if self.once(definition):
            self.types(definition,'task:TaskDefinition')
            self.value(definition,'task:label',module.ID)
            self.value(definition,'task:version',module.MODULE_VERSION)
            self.obj(CORE+session['id'],'task:hasDefinition',definition)
        return definition

    def state(self,session,event,state,kind,previous):
        self.types(state,'task:TaskState',kind)
        self.obj(state,'task:forTrial',CORE+event['input']['trial_id'])
        self.value(state,'task:phase',event['input']['kind'])
        self.value(state,'task:version',session['task_module']['version'])
        if previous:self.obj(state,'task:previousState',previous)

    def calculation(self,identifier,cls,state,rule,value,unit,option=None,estimate=False):
        self.types(identifier,'task:Calculation',cls)
        if estimate:self.types(identifier,'task:Estimate')
        self.obj(identifier,'task:inputState',state)
        self.obj(identifier,'task:usesRule',rule)
        if option:self.obj(identifier,'task:forOption',option)
        self.value(identifier,'task:value',value)
        self.value(identifier,'task:unit',unit)
        self.value(identifier,'s:status','inferred' if estimate else 'known')


def project_observations(writer,session,event,evaluation,option_iri,unit):
    """Common observation record; caller supplies task-specific option identities."""
    inp=event['input'];trial=CORE+inp['trial_id'];base=DATA+inp['trial_id']
    if inp['kind']!='feedback':return
    choice=base+'/choice';outcome=base+'/outcome'
    writer.types(choice,'task:ChoiceObservation','task:Observation')
    writer.obj(choice,'task:forTrial',trial)
    writer.value(choice,'task:timedOut',inp['timed_out'])
    if not inp['timed_out']:writer.obj(choice,'task:chosenOption',option_iri(inp['choice']))
    writer.value(choice,'task:responseTimeMs',inp['response_ms'])
    writer.types(outcome,'task:OutcomeObservation','task:Observation')
    writer.obj(outcome,'task:forTrial',trial)
    writer.obj(outcome,'task:outcomeOf',choice)
    writer.value(outcome,'task:value',inp['outcome'])
    writer.value(outcome,'task:unit',unit)
    writer.value(outcome,'task:timedOut',inp['timed_out'])
