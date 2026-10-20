"""Record-level integrity checks, including proof dependencies and epistemic status."""
from ..records import require,number
from .evaluation import evaluate


def validate_analysis(report):
    require(report['mode'] in {'shadow','live'},'Invalid graph argumentation mode')
    require(report['status'] in {'complete','limited','unavailable','not-evaluated'},'Invalid argumentation status')
    if report['status'] in {'unavailable','not-evaluated'}:
        require(not report['arguments'] and not report['attacks'] and not report['defeats'],'Unevaluated graph contains reasoning')
    assertions={a['id']:a for a in report['assertions']};nodes={a['id']:a for a in report['arguments']}
    require(len(assertions)==len(report['assertions']) and len(nodes)==len(report['arguments']),'Duplicate reasoning identifiers')
    for a in assertions.values():
        p=a['proposition']
        require(p['scope']==report['scope'],'Cross-state assertion')
        require(p['polarity'] in {'positive','negative'},'Invalid assertion polarity')
        for value in [p['subject'],p['predicate'],a['source']]:
            require(isinstance(value,str) and value.startswith(('https://','http://','urn:')),'Invalid assertion IRI')
        obj=p['object'];require(obj['type'] in {'iri','literal'},'Invalid proposition object')
        require(type(obj['value']) in {str,int,float,bool},'Invalid proposition value')
        if type(obj['value']) in {int,float}:require(number(obj['value']),'Nonfinite or out-of-range proposition value')
        if a['kind']=='estimate':require('inferred' in a['statuses'] and 'known' not in a['statuses'],'Estimate promoted to fact')
        if a['kind']=='report':require('source-dependent' in a['statuses'] and 'known' not in a['statuses'],'Report promoted to fact')
    for a in nodes.values():
        require(a['conclusion'] in assertions and bool(a['premises']) and set(a['premises'])<=assertions.keys(),'Dangling argument premise/conclusion')
        require(a['rule_kind'] in {'premise','strict','defeasible'} and type(a['priority']) is int,'Invalid rule application')
        require(set(a['subarguments'])<=nodes.keys(),'Dangling subargument')
        require(a['label'] in {'accepted','rejected','undecided'},'Invalid argument label')
        if a['rule_kind']=='premise':
            require(a['rule'] is None and a['premises']==[a['conclusion']] and not a['subarguments'],'Invalid atomic argument')
        else:
            require(bool(a['rule']),'Derived argument lacks a scheme')
            require({nodes[sub]['conclusion'] for sub in a['subarguments']}==set(a['premises']),'Subarguments do not establish the premises')
            conclusion=assertions[a['conclusion']]
            require(conclusion['source']==a['id'],'Conclusion lacks derivation provenance')
            if a['rule_kind']=='defeasible' or any(assertions[p]['statuses']!=['known'] for p in a['premises']):
                require(conclusion['statuses']==['inferred'],'Uncertain inference promoted to known')
    # Check acyclicity independently of the discovery procedure.
    seen=set();visiting=set()
    def visit(identifier):
        require(identifier not in visiting,'Circular proof')
        if identifier in seen:return
        visiting.add(identifier)
        for sub in nodes[identifier]['subarguments']:visit(sub)
        visiting.remove(identifier);seen.add(identifier)
    for identifier in nodes:visit(identifier)
    for attack in report['attacks']:
        require(attack['attacker'] in nodes and attack['target'] in nodes and set(attack['affected'])<=nodes.keys(),'Dangling attack')
    checked=[dict(a) for a in nodes.values()]
    expected_attacks,expected_defeats=evaluate(list(assertions.values()),checked)
    require(report['attacks']==expected_attacks,'Graph attacks do not match propositions and proofs')
    require(report['defeats']==[list(pair) for pair in expected_defeats],'Graph defeats do not match attacks and proofs')
    labels={a['id']:a['label'] for a in checked}
    require(all(a['label']==('undecided' if report['status']=='limited' else labels[a['id']]) for a in nodes.values()),'Incorrect grounded label')
    return {'conforms':True,'engine':'argument-record-validator'}
