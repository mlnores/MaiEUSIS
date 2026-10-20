"""Shared record and graph validation; task event schemas live in task modules."""
import json
from pathlib import Path
from .records import STATUSES,ACTIONS,CONDITIONS,ValidationError,require,fields,number,identity


def validate_event(task,event):
    from .tasks import get_task
    return get_task(task).validate_event(event)


def validate_claim(claim, trial_ids):
    required=['id','type','content','statuses','evidence','scope','timestamp','provenance','model_version']
    fields(claim, required, ['confidence','confidence_interpretation','alternatives','revision_conditions','depends_on','revises','contradicts'])
    require(identity(claim['id']),'Invalid claim ID')
    require(claim['type'] in {'Claim','Hypothesis'},'Invalid claim type')
    require(isinstance(claim['content'],str) and bool(claim['content']), 'Claim lacks content')
    statuses=claim['statuses']
    require(isinstance(statuses,list) and bool(statuses) and set(statuses)<=STATUSES,'Invalid epistemic statuses')
    for k in ['scope','timestamp','provenance','model_version']:require(isinstance(claim[k],str) and bool(claim[k]),'Missing '+k)
    require(isinstance(claim['evidence'],list),'Evidence must be a list')
    require(set(claim['evidence'])<=trial_ids, 'Dangling trial evidence')
    if claim['type']=='Hypothesis':
        require('inferred' in statuses,'Hypothesis must remain inferred')
        require(bool(claim['evidence']),'Hypothesis lacks supporting trials')
        require(bool(claim.get('revision_conditions')),'Hypothesis lacks revision conditions')
        require(bool(claim.get('alternatives')),'Hypothesis lacks alternative interpretations')
    if 'confidence' in claim:
        require(number(claim['confidence'],0,1),'Confidence outside [0,1]')
        require(bool(claim.get('confidence_interpretation')),'Confidence lacks interpretation')


def validate_snapshot(snapshot, trial_ids):
    claims=snapshot['claims']; ids={c['id'] for c in claims}
    require(len(ids)==len(claims),'Duplicate claim IDs')
    for c in claims:
        validate_claim(c,trial_ids)
        for relation in ['depends_on','revises','contradicts']:
            require(set(c.get(relation,[]))<=ids|set(snapshot.get('previous_claim_ids',[])),'Dangling claim relation')
    decision=snapshot.get('decision')
    if decision:
        require(decision['action'] in ACTIONS,'Invalid policy action')
        require(bool(decision['rationale']),'Decision lacks rationale, including silence')
        require(bool(decision['claim_ids']) and set(decision['claim_ids'])<=ids,'Decision lacks grounded claims')
        require(decision['action']=='silence' or bool(decision['message']),'Active decision lacks validated message')
    if decision and decision.get('reasoning_source')=='graph':
        from .intervention_policy import validate_decision
        validate_decision(snapshot)
    for a in snapshot['arguments']:
        require(bool(a['evidence']) and set(a['evidence'])<=ids,'Argument lacks claims')
        require(a['status'] in {'supported','opposed','unresolved'},'Invalid argument status')
    return {'conforms':True,'engine':'python-record-validator','report':'Required metadata, evidence links, epistemic status and policy grounding passed.'}


PREFIX='https://example.org/socratic/'

def _core_turtle(session):
    """Inspectable RDF representation; evaluator state is never serialized here."""
    lit=lambda x:json.dumps(str(x),ensure_ascii=False)
    ref=lambda x:'<'+PREFIX+x+'>'
    lines=['@prefix s: <'+PREFIX+'> .','@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .']
    sid=session['id']; participant=session['participant_id']
    lines.append(f'{ref("participant-"+participant)} a s:Participant .')
    lines.append(f'{ref(sid)} a s:Session ; s:participant {ref("participant-"+participant)} ; s:task {lit(session["task"])} .')
    for e in session['events']:
        inp=e['input']
        if inp.get('kind')=='evaluation':
            lines.append(f'{ref(inp["trial_id"])} a s:Trial ; s:session {ref(sid)} ; s:participant {ref("participant-"+participant)} ; s:trialIndex {inp["index"]} .')
        snap=e.get('snapshot')
        if not snap:continue
        for c in snap['claims']:
            triples=[f'a s:{c["type"]}',f's:content {lit(c["content"])}']
            for k in ['scope','timestamp','provenance','model_version']:
                triples.append(f's:{k} {lit(c[k])}')
            for status in c['statuses']:triples.append(f's:status {lit(status)}')
            for t in c['evidence']:triples.append(f's:supportedBy {ref(t)}')
            for relation,prop in [('depends_on','dependsOn'),('revises','revises'),('contradicts','contradicts')]:
                for t in c.get(relation,[]):triples.append(f's:{prop} {ref(t)}')
            if 'confidence' in c:
                triples += [f's:confidence "{c["confidence"]}"^^xsd:double', f's:confidenceInterpretation {lit(c["confidence_interpretation"])}']
            for a in c.get('alternatives',[]):triples.append(f's:alternative {lit(a)}')
            for a in c.get('revision_conditions',[]):triples.append(f's:revisionCondition {lit(a)}')
            lines.append(ref(c['id'])+' '+' ; '.join(triples)+' .')
        for a in snap['arguments']:
            triples=['a s:Argument',f's:conclusion {lit(a["conclusion"])}',f's:scope {lit(session["task"])}',f's:status {lit(a["status"])}',f's:reason {lit(a["reason"])}']
            triples += [f's:supportedBy {ref(t)}' for t in a['evidence']]
            if a.get('opposes'):triples.append(f's:opposes {ref(a["opposes"])}')
            lines.append(ref(a['id'])+' '+' ; '.join(triples)+' .')
        d=snap.get('decision')
        if d:
            triples=['a s:Intervention',f's:action {lit(d["action"])}',f's:rationale {lit(d["rationale"])}',f's:message {lit(d["message"] or "")}',f's:observedIn {ref(inp["trial_id"])}']
            triples += [f's:supportedBy {ref(c)}' for c in d['claim_ids']]
            lines.append(ref(d['id'])+' '+' ; '.join(triples)+' .')
    return '\n'.join(lines)+'\n'


def _projection(session,incremental=False):
    if incremental and 'task_module' in session:
        return _candidate_projection(session)
    core=_core_turtle(session)
    if 'task_module' not in session:return core,None
    from .semantics import Writer,DATA,CORE
    from .tasks import get_task
    module=get_task(session['task']);writer=Writer();writer.definition(session,module)
    header='\n'.join(f'@prefix {name}: <{iri}> .' for name,iri in [
        ('core',CORE),('task',CORE+'task/'),(module.ID.lower(),module.NAMESPACE),('data',DATA)])+'\n'
    if 'argumentation_configuration' in session:header+='@prefix arg: <'+CORE+'argumentation/> .\n'
    evaluations={};previous=None;focus=set()
    for event in session['events']:
        if not event.get('snapshot'):continue
        inp=event['input']
        if inp['kind']=='evaluation':evaluations[inp['trial_id']]=inp
        state=DATA+event['id']+'/state';writer.subjects=set()
        module.project_rdf(writer,session,event,state,evaluations[inp['trial_id']],previous)
        if 'argumentation_configuration' in session:
            from .argumentation.graph import project_report
            project_report(writer,event)
        previous=state;focus=set(writer.subjects)
        focus.update(PREFIX+c['id'] for c in event['snapshot']['claims'])
        focus.update(PREFIX+a['id'] for a in event['snapshot']['arguments'])
        decision=event['snapshot'].get('decision')
        if decision:focus.add(PREFIX+decision['id'])
        focus.update([PREFIX+inp['trial_id'],PREFIX+session['id'],PREFIX+'participant-'+session['participant_id']])
    return core+header+'\n'.join(writer.lines)+'\n',focus


def _candidate_projection(session):
    """Validate new entities against immutable, previously validated context.

    Avoid serialising/parsing every previous calculation on every trial. Context
    facts are retained for referenced states and observation types; full-session
    validation remains available for inspection, exports and independent audits.
    """
    from .semantics import Writer,DATA,CORE
    from .tasks import get_task
    records=[e for e in session['events'] if e.get('snapshot')]
    if not records:return _projection(session,False)
    current=records[-1];inp=current['input']
    evals={e['input']['trial_id']:e['input'] for e in session['events'] if e['input']['kind']=='evaluation'}
    context={**session,'events':[{'input':e} for e in evals.values()]+[current]}
    core=_core_turtle(context);writer=Writer();module=get_task(session['task'])
    writer.definition(session,module)
    writer.subjects=set()
    previous=DATA+records[-2]['id']+'/state' if len(records)>1 else None
    state=DATA+current['id']+'/state'
    module.project_rdf(writer,session,current,state,evals[inp['trial_id']],previous)
    if 'argumentation_configuration' in session:
        from .argumentation.graph import project_report
        project_report(writer,current)
    focus=set(writer.subjects)
    # References are resolved only to observations actually present in the store.
    extras=Writer()
    if previous:
        prior=records[-2];prior_writer=Writer()
        prior_previous=DATA+records[-3]['id']+'/state' if len(records)>2 else None
        module.project_rdf(prior_writer,session,prior,previous,evals[prior['input']['trial_id']],prior_previous)
        extras.lines.extend(line for line in prior_writer.lines if line.startswith('<'+previous+'> '))
    for event in session['events']:
        if event['input']['kind']=='feedback' and event['id']!=current['id']:
            for kind in ['choice','outcome']:extras.types(DATA+event['input']['trial_id']+'/'+kind,'task:Observation')
    focus.update(PREFIX+c['id'] for c in current['snapshot']['claims'])
    focus.update(PREFIX+a['id'] for a in current['snapshot']['arguments'])
    d=current['snapshot'].get('decision')
    if d:focus.add(PREFIX+d['id'])
    focus.update([PREFIX+inp['trial_id'],PREFIX+session['id'],PREFIX+'participant-'+session['participant_id']])
    header='\n'.join(f'@prefix {name}: <{iri}> .' for name,iri in [
        ('core',CORE),('task',CORE+'task/'),(module.ID.lower(),module.NAMESPACE),('data',DATA)])+'\n'
    if 'argumentation_configuration' in session:header+='@prefix arg: <'+CORE+'argumentation/> .\n'
    return core+header+'\n'.join(writer.lines+extras.lines)+'\n',focus


def turtle(session):
    return _projection(session)[0]


def graph_documents(session):
    """Resolve ontology/shape modules from local files, with a legacy export path."""
    root=Path(__file__).parent/'ontology'
    if 'task_module' not in session:return (root/'legacy/schema.ttl',),(root/'legacy/shapes.ttl',)
    from .tasks import get_task
    module=get_task(session['task']);ont,shapes=module.documents()
    if 'argumentation_configuration' in session:
        from .argumentation import documents
        extra=documents(module)
        return tuple(ont)+(extra[0],)+extra[2:],tuple(shapes)+(extra[1],)
    return ont,shapes


def _target_candidates(shapes,data,ontology,focus):
    """Retarget entry shapes, preserving validation of nested shapes and literals.

    pySHACL's global focus filter also filters explicit nested focus values.
    Using SHACL targetNode instead keeps nested constraints fully active while
    leaving already-validated historical context out of the entry targets.
    """
    from rdflib import Namespace,URIRef,RDF,RDFS
    sh=Namespace('http://www.w3.org/ns/shacl#');allowed={URIRef(x) for x in focus}
    for shape in set(shapes.subjects(sh.targetClass,None))|set(shapes.subjects(sh.targetNode,None))|set(shapes.subjects(sh.targetSubjectsOf,None))|set(shapes.subjects(sh.targetObjectsOf,None)):
        targets=set(shapes.objects(shape,sh.targetNode))
        for cls in shapes.objects(shape,sh.targetClass):
            classes={cls};pending=[cls]
            while pending:
                parent=pending.pop()
                for child in set(ontology.subjects(RDFS.subClassOf,parent))|set(data.subjects(RDFS.subClassOf,parent)):
                    if child not in classes:classes.add(child);pending.append(child)
            for subclass in classes:targets.update(data.subjects(RDF.type,subclass))
        for prop in shapes.objects(shape,sh.targetSubjectsOf):targets.update(data.subjects(prop,None))
        for prop in shapes.objects(shape,sh.targetObjectsOf):targets.update(data.objects(None,prop))
        for predicate in [sh.targetClass,sh.targetNode,sh.targetSubjectsOf,sh.targetObjectsOf]:shapes.remove((shape,predicate,None))
        for target in targets&allowed:shapes.add((shape,sh.targetNode,target))


def shacl_report(session,incremental=False):
    try:
        from rdflib import Graph
        from pyshacl import validate
    except ImportError:
        return {'conforms':None,'engine':'pyshacl-unavailable','report':'SHACL not executed; Python record validation is active. Install requirements-research.txt to enable SHACL.'}
    text,focus=_projection(session,incremental)
    g=Graph().parse(data=text,format='turtle');ont=Graph();shapes=Graph()
    ont_files,shape_files=graph_documents(session)
    for path in ont_files:ont.parse(str(path),format='turtle')
    for path in shape_files:shapes.parse(str(path),format='turtle')
    if incremental and focus:
        _target_candidates(shapes,g,ont,focus)
    ok,_,report=validate(g,shacl_graph=shapes,ont_graph=ont if focus is not None else None,
                         inference='none',do_owl_imports=False)
    result={'conforms':bool(ok),'engine':'pyshacl','report':report}
    if focus is not None:result['scope']='candidate-event-and-context' if incremental and focus else 'full-session'
    return result
