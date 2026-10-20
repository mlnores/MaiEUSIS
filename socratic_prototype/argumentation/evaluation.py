"""Finite structured attacks and grounded labelling; independent of RDF and policy.

This is a deliberately small instantiation, not a complete ASPIC+ implementation.
Only explicit opposite polarities are contraries. Rule applicability is a separate
proposition. Preferences affect rebuttal/undermining, never undercutting.
"""
from ..records import require
from ..semantics import CORE


def proposition_key(proposition):
    import json
    return (proposition['scope'],proposition['subject'],proposition['predicate'],
            json.dumps(proposition['object'],sort_keys=True,separators=(',',':')))


def grounded(ids,defeats):
    ids=set(ids);attackers={i:set() for i in ids}
    for source,target in defeats:
        require(source in ids and target in ids,'Dangling defeat')
        attackers[target].add(source)
    labels={i:'undecided' for i in ids}
    while True:
        updated=dict(labels)
        for identifier in sorted(ids):
            if labels[identifier]!='undecided':continue
            incoming=attackers[identifier]
            if any(labels[a]=='accepted' for a in incoming):updated[identifier]='rejected'
            elif all(labels[a]=='rejected' for a in incoming):updated[identifier]='accepted'
        if updated==labels:return labels
        labels=updated


def evaluate(assertions,arguments):
    facts={a['id']:a for a in assertions};nodes={a['id']:a for a in arguments}
    require(len(nodes)==len(arguments),'Duplicate argument ID')
    descendants={i:{i} for i in nodes}
    for argument in arguments:
        require(argument['conclusion'] in facts,'Missing argument conclusion')
        require(set(argument['premises'])<=facts.keys(),'Missing argument premise')
        require(set(argument['subarguments'])<=nodes.keys(),'Missing subargument')
    # Propagate defeat to every proof containing the attacked subargument.
    changed=True
    while changed:
        changed=False
        for argument in arguments:
            for sub in argument['subarguments']:
                before=len(descendants[sub]);descendants[sub].update(descendants[argument['id']])
                changed|=len(descendants[sub])!=before
    attacks=[];defeats=set()
    for a in sorted(arguments,key=lambda a:a['id']):
        claim=facts[a['conclusion']]['proposition']
        for b in sorted(arguments,key=lambda a:a['id']):
            target=facts[b['conclusion']];other=target['proposition'];kind=None
            if (claim['scope']==other['scope'] and claim['subject']==other['subject'] and
                claim['predicate']==CORE+'argumentation/inapplicable' and claim['polarity']=='positive' and
                claim['object']=={'type':'iri','value':b['rule']} and b['rule_kind']=='defeasible'):
                kind='undercutting'
            elif proposition_key(claim)==proposition_key(other) and claim['polarity']!=other['polarity']:
                if b['rule_kind']=='defeasible':kind='rebutting'
                elif b['rule_kind']=='premise' and target['kind'] in {'estimate','report','assumption'}:kind='undermining'
            if kind:
                succeeds=kind=='undercutting' or a['priority']>=b['priority']
                affected=sorted(descendants[b['id']]) if succeeds else []
                attacks.append({'attacker':a['id'],'target':b['id'],'kind':kind,
                                'succeeds':succeeds,'affected':affected,
                                'reason':'Rule applicability challenged.' if kind=='undercutting' else
                                         'Explicit contrary in the same state and scope.',
                                'preference':'undercutting' if kind=='undercutting' else
                                             'not-less-preferred' if succeeds else 'target-preferred'})
                defeats.update((a['id'],target_id) for target_id in affected)
    labels=grounded(nodes,defeats)
    accepted={}
    for argument in arguments:
        if labels[argument['id']]!='accepted':continue
        prop=facts[argument['conclusion']]['proposition'];key=proposition_key(prop)
        accepted.setdefault(key,set()).add(prop['polarity'])
        # The small rule language does not implement arbitrary classical logic
        # closure. Refuse inconsistent strict premises/rules instead of presenting
        # incompatible strict conclusions as jointly justified.
        require(len(accepted[key])<=1,'Inconsistent accepted conclusions; review strict premises and rules')
    for a in arguments:a['label']=labels[a['id']]
    return attacks,sorted(defeats)
