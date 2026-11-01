"""Small public-probability task used to verify the complete extension contract.

This is an engineering reference environment, not a validated research task.
"""
import copy
from ..records import fields,require,number
from .base import MODEL_VERSION,describe_task,document_paths,common_observation

ID='REFERENCE'
NAMESPACE='https://example.org/socratic/reference/'
MODULE_VERSION='reference-0.1'
ONTOLOGY_VERSION='reference-ontology-0.1'
ELIGIBLE_POINT='pre-choice preparation'
PROTOCOLS={'mini':4}

def documents():
    p=document_paths(ID);return p[:3],p[3:]
def describe():return describe_task(ID,NAMESPACE,MODULE_VERSION,ONTOLOGY_VERSION,documents())
def task_rules():return {'gain':1,'response_timeout_ms':5000}
def argumentation_documents():
    from ..argumentation import ROOT
    return (ROOT/'schemes/reference.ttl',)
def browser_adapter():return {'help':'This engineering reference task displays win probabilities. It is not a validated research task.','script':'task-adapters/reference.js','title':'Reference public-probability choice','start_id':'startReference','calibration_id':'referenceCalibration'}
def simulation_adapter():
    from . import reference_execution
    return reference_execution

def recommendation_message(rec):
    require(rec['criterion']=='public_expected_gain','Unsupported reference criterion')
    return f"I recommend {rec['option_id'].upper()} (key {rec['key']}) because its displayed win probability gives higher expected gain. The outcome remains uncertain."
def intervention_focus(issue):return 'public_evidence_review'
def calibrate(h):
    h=[r for r in h if not r['timed_out']]
    return {'task':ID,'model_version':MODEL_VERSION,'samples':len(h),'mean_right_choice':sum(r['choice']=='right' for r in h)/len(h) if h else .5}
def participant(h,profile):return {'observed_right_rate':profile.get('mean_right_choice',.5)}
def hypothesis_inputs(*args):return [],{}
def hypothesis_message(*args):return 'What evidence would lead you to reconsider?'
def same_scope(*args):return True
def scope_suffix(ev):return ''
def history_context(ev):return {'points_before':ev['points']}
evidence_observation=common_observation

def environment(h,ev,policy,event):return {'points':ev['points'],'options':copy.deepcopy(ev['options']),'unknown':['Next random outcome']}
def environment_claim(env):return 'Current win probabilities are displayed; outcomes remain uncertain.',['known']
def evidence_environment(env):return copy.deepcopy(env),'Current win probabilities are displayed.'
def evidence_participant(person):return {'calibration':copy.deepcopy(person['calibration'])}
def summarize(s,h,valid):return {'reference_points':h[-1]['points_after'] if h else 0}

def validate_event(e):
    from .base import validate_envelope
    validate_envelope(e)
    if e['kind']=='evaluation':
        fields(e,['kind','trial_id','index','points','options']);require(number(e['points'],0),'Invalid points')
        require([o['id'] for o in e['options']]==['left','right'],'Wrong reference options')
        for o,key in zip(e['options'],['1','9']):
            fields(o,['id','key','probability']);require(o['key']==key and number(o['probability'],0,1),'Invalid displayed option')
        require([o['probability'] for o in e['options']]==([.75,.25] if e['index']%2 else [.25,.75]),'Wrong public probability schedule')
    else:
        fields(e,['kind','trial_id','index','choice','outcome','timed_out','response_ms','points_after'])
        require(e['kind']=='feedback' and type(e['timed_out']) is bool,'Invalid feedback')
        require(e['choice'] in {'left','right','NO_RESPONSE'} and e['outcome'] in [0,1],'Invalid outcome')
        require(e['timed_out']==(e['choice']=='NO_RESPONSE') and (not e['timed_out'] or e['outcome']==0),'Invalid missed choice')
        require(number(e['response_ms'],0,60000) and number(e['points_after'],0),'Invalid feedback timing/points')
def validate_transition(s,e,h,evaluations):
    if e['kind']=='evaluation':require(e['points']==(h[-1]['points_after'] if h else 0),'Points changed without feedback')
    else:require(e['points_after']==evaluations[-1]['points']+e['outcome'],'Wrong points arithmetic')

def project_rdf(w,s,event,state,ev,previous):
    from ..semantics import DATA,project_observations
    definition=w.definition(s,__import__(__name__,fromlist=['describe']))
    rule=w.rule(definition+'/expectation','Expected gain','socratic_prototype.tasks.reference.project_rdf',MODULE_VERSION,'Displayed probability times one point')
    w.state(s,event,state,'reference:ChoiceState',previous);w.value(state,'reference:points',event['input'].get('points_after',ev['points']))
    option=lambda name:DATA+ev['trial_id']+'/option/'+name
    for o in ev['options']:
        iri=option(o['id']);w.types(iri,'task:Option');w.value(iri,'task:label',o['id']);w.obj(state,'task:hasOption',iri)
        w.value(iri,'reference:publicWinProbability',o['probability'])
        w.calculation(state+'/expected/'+o['id'],'reference:ExpectedGainCalculation',state,rule,o['probability'],'points',iri)
    project_observations(w,s,event,ev,option,'points')
