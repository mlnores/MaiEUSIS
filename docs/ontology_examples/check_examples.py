"""Parse the actual projections, validate their shapes and execute example queries.

Run with the research environment:
  .venv/bin/python docs/ontology_examples/check_examples.py
No participant store is read or changed.
"""
import json
from pathlib import Path
import sys
from rdflib import Graph, Namespace, RDF, OWL, RDFS, Literal
from pyshacl import validate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from socratic_prototype.tasks import get_task
S=Namespace('https://example.org/socratic/')


def main():
    schema=Graph()
    for name in ['schema','task','mab','tbs']:schema.parse(ROOT/('socratic_prototype/ontology/'+name+'.ttl'),format='turtle')
    classes=set(schema.subjects(RDF.type,OWL.Class))
    declared=set().union(*(set(schema.subjects(RDF.type,t)) for t in [OWL.ObjectProperty,OWL.DatatypeProperty,RDF.Property]))
    short=lambda value:str(value).replace(str(S),'s:')
    audit={'synthetic':True,'schema_version':'ontology-0.2',
           'declared_classes':sorted(map(short,classes)),
           'declared_object_properties':sorted(map(short,schema.subjects(RDF.type,OWL.ObjectProperty))),
           'declared_datatype_properties':sorted(map(short,schema.subjects(RDF.type,OWL.DatatypeProperty))),
           'property_domain_declarations':len(list(schema.triples((None,RDFS.domain,None)))),
           'property_range_declarations':len(list(schema.triples((None,RDFS.range,None)))),
           'cases':{},'queries':{}}
    graphs={}
    for task in ['mab','tbs']:
        module=get_task(task.upper());ontology=Graph();shapes=Graph()
        for path in module.documents()[0]:ontology.parse(path,format='turtle')
        for path in module.documents()[1]:shapes.parse(path,format='turtle')
        graph=Graph().parse(HERE/(task+'.ttl'),format='turtle');graphs[task]=graph
        ok,_,report=validate(graph,shacl_graph=shapes,ont_graph=ontology,inference='none',do_owl_imports=False)
        assert ok,report
        predicates={p for _,p,_ in graph if str(p).startswith(str(S))}
        numeric={p for _,p,o in graph if isinstance(o,Literal) and type(o.toPython()) in [int,float]}
        audit['cases'][task]={'triples':len(graph),'shacl_conforms':bool(ok),
            'class_instances':{short(c):len(set(graph.subjects(RDF.type,c))) for c in sorted(classes,key=str)},
            'used_properties_not_declared_in_schema':sorted(map(short,predicates-declared)),
            'numeric_predicates':sorted(map(short,numeric)),
            'trial_predicates':sorted(map(short,{p for t in graph.subjects(RDF.type,S.Trial) for p in graph.predicates(t)}))}
        assert not predicates-declared,'Undeclared emitted properties'
        task_ns=Namespace(str(S)+'task/')
        assert list(graph.subjects(RDF.type,task_ns.ChoiceObservation))
        assert list(graph.subjects(RDF.type,task_ns.OutcomeObservation))
        for calc in graph.subjects(RDF.type,task_ns.Calculation):
            assert list(graph.objects(calc,task_ns.usesRule))
            assert list(graph.objects(calc,task_ns.inputState))
    for name,task in [('mab_contested','mab'),('mab_silence','mab'),('tbs_final_arguments','tbs'),
                      ('mab_estimates','mab'),('tbs_final_calculations','tbs')]:
        results=graphs[task].query(HERE.joinpath(name+'.rq').read_text())
        rows=[{str(k):short(v) for k,v in row.asdict().items()} for row in results]
        assert rows,name+' returned no examples'
        audit['queries'][name]=rows
    assert audit['queries']['mab_silence'][0]['action']=='silence'
    quantities={row['option']:row for row in audit['queries']['tbs_final_calculations']}
    assert float(quantities['safe']['ev'])==108 and float(quantities['safe']['attainment'])==0
    assert float(quantities['risky']['ev'])==91 and float(quantities['risky']['attainment'])==.35
    HERE.joinpath('audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
