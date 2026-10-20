"""Structured assertions over the actual current task projection, plus provenance."""
import hashlib
import json
import math
from ..semantics import Writer,CORE,DATA,TASK
from . import ARG,VERSION

PREFIXES='\n'.join('@prefix '+p+': <'+iri+'> .' for p,iri in [
    ('s',CORE),('core',CORE),('task',TASK),('arg',ARG),
    ('xsd','http://www.w3.org/2001/XMLSchema#')])+'\n'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]


def term(value):
    from rdflib import URIRef,Literal
    if isinstance(value,URIRef):return {'type':'iri','value':str(value)}
    if isinstance(value,Literal):
        native=value.toPython()
        if isinstance(native,float) and not math.isfinite(native):raise ValueError('Nonfinite argument quantity')
        if type(native) not in {str,int,float,bool}:native=str(value)
        result={'type':'literal','value':native}
        if value.datatype:result['datatype']=str(value.datatype)
        return result
    raise ValueError('Argument propositions require IRIs or literals')


def rdf_term(value):
    from rdflib import URIRef,Literal
    return URIRef(value['value']) if value['type']=='iri' else Literal(value['value'],datatype=URIRef(value['datatype']) if value.get('datatype') else None)


def write_term(w,subject,predicate,value):
    if value['type']=='iri':w.obj(subject,predicate,value['value'])
    else:
        # rdflib preserves the original literal datatype, including numeric units.
        w.subjects.add(subject);w.lines.append(f'{w.iri(subject)} {w.iri(predicate)} {rdf_term(value).n3()} .')


def write_assertion(w,assertion,event):
    identifier=assertion['id'];p=assertion['proposition'];proposition=identifier+'/proposition'
    w.types(identifier,'arg:Assertion','core:Claim')
    for key,value in [('content',assertion['content']),('scope',p['scope']),('timestamp',event['timestamp']),
                      ('provenance',assertion['source']),('model_version',VERSION)]:w.value(identifier,'core:'+key,value)
    for status in assertion['statuses']:w.value(identifier,'core:status',status)
    w.obj(identifier,'core:supportedBy',CORE+event['input']['trial_id'])
    w.obj(identifier,'arg:asserts',proposition);w.obj(identifier,'arg:source',assertion['source'])
    w.value(identifier,'arg:kind',assertion['kind'])
    if assertion.get('confidence') is not None:w.value(identifier,'arg:modelConfidence',assertion['confidence'])
    w.types(proposition,'arg:Proposition')
    w.obj(proposition,'arg:subject',p['subject']);w.obj(proposition,'arg:predicate',p['predicate'])
    write_term(w,proposition,'arg:object',p['object'])
    w.obj(proposition,'arg:scope',p['scope']);w.value(proposition,'arg:polarity',p['polarity'])
    # Materialized indexes keep rule joins selective. They mirror the canonical
    # proposition exactly and are always generated together, never user-supplied.
    w.obj(identifier,'arg:subject',p['subject']);w.obj(identifier,'arg:predicate',p['predicate'])
    write_term(w,identifier,'arg:object',p['object'])
    w.obj(identifier,'arg:scope',p['scope']);w.value(identifier,'arg:polarity',p['polarity'])


def build_input(session,event):
    from rdflib import Graph,Namespace,RDF,URIRef,Literal
    from ..tasks import get_task
    from ..engine import history
    module=get_task(session['task']);state=DATA+event['id']+'/state'
    w=Writer();w.definition(session,module)
    module.project_rdf(w,session,event,state,event['input'],None)
    extra=Writer()
    hook=getattr(module,'project_argumentation_facts',None)
    if hook:hook(extra,session,event,state,history(session))
    snap=event['snapshot'];task=Namespace(TASK);arg=Namespace(ARG)
    header=PREFIXES+f'@prefix {module.ID.lower()}: <{module.NAMESPACE}> .\n'
    g=Graph().parse(data=header+'\n'.join(w.lines+extra.lines),format='turtle')
    assertions=[]
    def add(subject,predicate,value,kind,source,content=None,confidence=None):
        p={'subject':str(subject),'predicate':str(predicate),'object':term(value),'polarity':'positive','scope':state}
        identifier=state+'/assertion/'+fingerprint([p,str(source)])
        statuses={'observation':['known'],'calculation':['known'],'estimate':['inferred','source-dependent'],
                  'report':['source-dependent'],'assumption':['assumed']}[kind]
        record={'id':identifier,'proposition':p,'kind':kind,'source':str(source),'statuses':statuses,
                'content':content or f'{str(predicate).rsplit("/",1)[-1]} = {value}'}
        if confidence is not None:record['confidence']=confidence
        assertions.append(record)
    # Only numeric facts from the current state, its calculations, displayed
    # options/goals and task-owned history aggregates become queryable premises.
    scoped={URIRef(state)}|set(g.subjects(task.inputState,URIRef(state)))|set(g.objects(URIRef(state),task.hasOption))|set(g.objects(URIRef(state),task.hasGoal))|set(g.subjects(arg.inState,URIRef(state)))
    for subject in sorted(scoped,key=str):
        types=set(g.objects(subject,RDF.type))
        for predicate,value in sorted(g.predicate_objects(subject),key=lambda pair:(str(pair[0]),str(pair[1]))):
            if not isinstance(value,Literal) or type(value.toPython()) not in {int,float,bool}:continue
            if not str(predicate).startswith((module.NAMESPACE,TASK,ARG)):continue
            kind='estimate' if task.Estimate in types and predicate!=task.samples else 'calculation' if task.Calculation in types or arg.HistorySummary in types else 'observation'
            add(subject,predicate,value,kind,subject)
    claims={c['id']:c for c in snap['claims']}
    events={e['id']:e for e in session['events']}
    def report_metadata(recorded,quote):
        report=CORE+recorded['id'];extra.types(report,'arg:Report')
        extra.value(report,'arg:reportedText',quote);extra.obj(report,'arg:inState',state)
        if recorded.get('timestamp'):extra.value(report,'core:timestamp',recorded['timestamp'])
        decision_id=recorded['input'].get('decision_id')
        if decision_id:
            origin=next((e for e in session['events'] if e.get('snapshot',{}).get('decision',{}).get('id')==decision_id),None)
            if origin:extra.obj(report,'task:forTrial',CORE+origin['input']['trial_id'])
        return report
    for hyp in snap['participant'].get('hypotheses',[]):
        if not hyp.get('claim_id'):continue
        source=CORE+hyp['claim_id'];c=claims[hyp['claim_id']]
        extra.types(source,'core:Hypothesis');extra.value(source,'arg:eligible',hyp['eligible'])
        extra.obj(source,'arg:inState',state)
        add(CORE+'participant-'+session['participant_id'],arg.possiblePattern,Literal(hyp['name']),
            'estimate',source,c['content'],hyp['inference']['posterior'])
        for identifier in sorted(set(hyp['contested_by'])):
            recorded=events[identifier];inp=recorded['input']
            if inp['kind']=='interpretation-review':recorded=events[inp['response_event_id']]
            report=report_metadata(recorded,recorded['input']['text'])
            add(report,arg.contests,URIRef(source),'report',report,
                'Participant contests this interpretation; its truth remains unverified.')
    from ..grounding import reviewed_responses
    for reviewed in reviewed_responses(session,event['input']):
        for update in reviewed['updates']:
            if update['kind']!='reported_strategy':continue
            report=report_metadata(reviewed['response'],update['quote'])
            extra.obj(report,'arg:source',CORE+reviewed['review']['id'])
            add(report,arg.reportedText,Literal(update['quote']),'report',report,
                'Researcher-reviewed strategy quotation; attributed text does not establish intent.')
    # Every fact is a structured claim. The assertion of a model output or report
    # does not assert a corresponding hidden state, intention or psychological trait.
    asserted=Writer()
    for assertion in assertions:write_assertion(asserted,assertion,event)
    facts='\n'.join(extra.lines)
    # extra now also contains eligible/report metadata created after initial parse.
    g.parse(data=header+facts+'\n'+'\n'.join(asserted.lines),format='turtle')
    return g,assertions,facts


def project_report(w,event):
    report=event.get('snapshot',{}).get('graph_argumentation')
    if not report:return
    root=report['scope']+'/argumentation';w.types(root,'arg:Analysis')
    w.obj(root,'arg:inState',report['scope'])
    for key in ['status','mode','semantics']:w.value(root,'arg:'+key,report[key])
    w.value(root,'arg:version',report['version'])
    if report.get('reason'):w.value(root,'arg:reason',report['reason'])
    if report.get('facts_turtle'):w.lines.append(report['facts_turtle'])
    assertions={a['id']:a for a in report['assertions']}
    for assertion in assertions.values():write_assertion(w,assertion,event)
    for a in report['arguments']:
        identifier=a['id'];w.types(identifier,'arg:Argument','core:Argument')
        w.obj(root,'arg:hasArgument',identifier)
        w.value(identifier,'core:conclusion',assertions[a['conclusion']]['content'])
        w.value(identifier,'core:reason',a['reason']);w.value(identifier,'core:scope',report['scope'])
        w.value(identifier,'core:status',{'accepted':'supported','rejected':'opposed','undecided':'unresolved'}[a['label']])
        w.obj(identifier,'arg:conclusion',a['conclusion']);w.value(identifier,'arg:label',a['label'])
        w.value(identifier,'arg:ruleKind',a['rule_kind']);w.value(identifier,'arg:priority',a['priority'])
        if a['rule']:
            w.obj(identifier,'arg:usesScheme',a['rule'])
            if w.once(a['rule']):
                w.types(a['rule'],'arg:Scheme');w.value(a['rule'],'arg:version',VERSION)
                w.value(a['rule'],'arg:ruleKind',a['rule_kind'])
        for premise in a['premises']:
            w.obj(identifier,'arg:hasPremise',premise);w.obj(identifier,'core:supportedBy',premise)
        for sub in a['subarguments']:w.obj(identifier,'arg:hasSubargument',sub)
        for question in a['critical_questions']:w.value(identifier,'arg:criticalQuestion',question)
    for i,attack in enumerate(report['attacks']):
        identifier=root+'/attack/'+str(i);w.types(identifier,'arg:Attack')
        w.obj(identifier,'arg:attacker',attack['attacker']);w.obj(identifier,'arg:target',attack['target'])
        w.value(identifier,'arg:attackKind',attack['kind']);w.value(identifier,'arg:succeeds',attack['succeeds'])
        for affected in attack['affected']:w.obj(identifier,'arg:affects',affected)
