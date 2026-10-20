"""Bounded forward construction from locally authored SPARQL argument schemes."""
from functools import lru_cache
import re
from ..records import require
from ..semantics import Writer
from . import ARG,documents
from .graph import build_input,write_assertion,term,fingerprint,PREFIXES
from .evaluation import evaluate,proposition_key


@lru_cache(maxsize=64)
def prepared(query):
    from rdflib.plugins.sparql import prepareQuery
    # Schemes are versioned local source, never participant text or LLM output.
    require(not re.search(r'\b(SERVICE|LOAD|INSERT|DELETE)\b',query,re.I),'Nonlocal or mutating argument query')
    result=prepareQuery(query)
    require(result.algebra.name=='SelectQuery','Argument schemes must select explicit premise bindings')
    return result


@lru_cache(maxsize=32)
def load_schemes(contents):
    from rdflib import Graph,Namespace,RDF
    g=Graph();arg=Namespace(ARG)
    for text in contents:g.parse(data=text,format='turtle')
    result=[]
    for node in sorted(g.subjects(RDF.type,arg.Scheme),key=str):
        def one(predicate,default=None):
            values=list(g.objects(node,arg[predicate]));require(len(values)<=1,'Multiple scheme '+predicate)
            return values[0] if values else default
        kind=str(one('ruleKind'));require(kind in {'strict','defeasible'},'Invalid scheme inference kind')
        variables=str(one('premiseVariables','')).split();require(bool(variables),'Scheme requires premises')
        query=str(one('query',''));require(bool(query),'Scheme lacks a query')
        result.append({'id':str(node),'query':prepared(query),'kind':kind,'variables':variables,
                       'subject_variable':str(one('subjectVariable','state')),
                       'predicate':str(one('conclusionPredicate')),
                       'object_variable':str(one('objectVariable','')),
                       'object':term(one('conclusionObject')) if one('conclusionObject') is not None else None,
                       'polarity':str(one('polarity','positive')),'priority':int(one('priority',0)),
                       'reason':str(one('reason','')),'questions':sorted(map(str,g.objects(node,arg.criticalQuestion)))})
    return result


def discover(session,event,base):
    from rdflib import URIRef
    from ..tasks import get_task
    module=get_task(session['task'])
    graph,assertions,facts=build_input(session,event);input_triples=len(graph)
    limits=session['argumentation_configuration']['limits']
    schemes=load_schemes(tuple(p.read_text() for p in documents(module)[2:]))
    records={a['id']:a for a in assertions};arguments=[];nodes={};proofs={};matches=0;limited=False
    input_assertions=len(assertions)
    state=base['scope'];ancestors={}
    def atomic(identifier):
        if identifier in proofs:return proofs[identifier]
        a={'id':state+'/argument/'+fingerprint(['premise',identifier]),'conclusion':identifier,
           'premises':[identifier],'subarguments':[],'rule':None,'rule_kind':'premise','priority':0,
           'reason':'Recorded '+records[identifier]['kind']+' premise; source and epistemic status retained.',
           'critical_questions':[],'label':'undecided'}
        arguments.append(a);nodes[a['id']]=a;proofs[identifier]=a['id']
        ancestors[a['id']]={proposition_key(records[identifier]['proposition'])+(records[identifier]['proposition']['polarity'],)}
        return a['id']
    if len(assertions)>limits['max_assertions']:limited=True
    for round_index in range(limits['max_rounds']):
        if limited:break
        added=False
        # Fixed order plus content-derived IDs gives deterministic replay.
        for scheme in schemes:
            rows=sorted(graph.query(scheme['query'],initBindings={'state':URIRef(state)}),
                        key=lambda row:tuple(sorted((str(k),str(v)) for k,v in row.asdict().items())))
            for row in rows:
                matches+=1
                if matches>limits['max_matches']:limited=True;break
                bindings={'state':URIRef(state),**{str(k):v for k,v in row.asdict().items()}}
                premises=sorted({str(bindings.get(v,'')) for v in scheme['variables']})
                require(all(p in records for p in premises),'Scheme returned an unbound or non-assertion premise')
                require(all(records[p]['proposition']['scope']==state for p in premises),'Cross-state argument premise')
                subject=bindings.get(scheme['subject_variable'])
                require(isinstance(subject,URIRef),'Scheme conclusion subject must be an IRI')
                obj=term(bindings[scheme['object_variable']]) if scheme['object_variable'] else scheme['object']
                require(obj is not None and scheme['polarity'] in {'positive','negative'},'Invalid scheme head')
                prop={'subject':str(subject),'predicate':scheme['predicate'],'object':obj,'scope':state,'polarity':scheme['polarity']}
                identifier=state+'/argument/'+fingerprint([scheme['id'],premises,prop])
                if identifier in nodes:continue
                if len(arguments)+len(premises)+1>limits['max_arguments'] or len(assertions)>=limits['max_assertions']:
                    limited=True;break
                subs=[atomic(p) for p in premises]
                inherited=set().union(*(ancestors[sub] for sub in subs));key=proposition_key(prop)+(prop['polarity'],)
                # Do not construct circular proofs or infinite chains of self-support.
                if key in inherited:continue
                known=scheme['kind']=='strict' and all(records[p]['statuses']==['known'] for p in premises)
                conclusion={'id':identifier+'/claim','proposition':prop,'kind':'derived','source':identifier,
                            'statuses':['known'] if known else ['inferred'],
                            'content':scheme['reason']}
                a={'id':identifier,'conclusion':conclusion['id'],'premises':premises,'subarguments':subs,
                   'rule':scheme['id'],'rule_kind':scheme['kind'],'priority':scheme['priority'],
                   'reason':scheme['reason'],'critical_questions':scheme['questions'],'label':'undecided'}
                assertions.append(conclusion);records[conclusion['id']]=conclusion
                arguments.append(a);nodes[identifier]=a;proofs[conclusion['id']]=identifier
                ancestors[identifier]=inherited|{key}
                w=Writer();write_assertion(w,conclusion,event)
                graph.parse(data=PREFIXES+'\n'.join(w.lines),format='turtle');added=True
            if limited:break
        if not added:break
    else:
        limited=True
    attacks,defeats=evaluate(assertions,arguments)
    if limited:
        # An incomplete construction may omit a defeater. Never report acceptance.
        for argument in arguments:argument['label']='undecided'
    questions=sorted({q for a in arguments for q in a['critical_questions']})
    # Discovery considers every input fact. Persist the complete premises of all
    # discovered proofs, avoiding copies of unrelated numerical records per trial.
    used={p for a in arguments for p in a['premises']}|{a['conclusion'] for a in arguments}
    retained=[a for a in assertions if a['id'] in used or a['kind']=='report']
    return {**base,'status':'limited' if limited else 'complete','assertions':retained,
            'arguments':arguments,'attacks':attacks,'defeats':[list(pair) for pair in defeats],
            'critical_questions':questions,'facts_turtle':facts,
            'stats':{'input_triples':input_triples,'input_assertions':input_assertions,
                     'retained_assertions':len(retained),'schemes':len(schemes),'matches':matches,'rounds':round_index+1},
            'limits':dict(limits)}
