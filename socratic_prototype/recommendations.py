"""Specific action proposals require an accepted comparison proof in the graph."""
from .argumentation import ARG
from .tasks import get_task

VERSION='structured-intervention-0.1'


def from_graph(task,evaluation,report):
    assertions={a['id']:a for a in report['assertions']}
    for argument in report['arguments']:
        prop=assertions[argument['conclusion']]['proposition']
        if argument['label']!='accepted' or prop['predicate']!=ARG+'recommendedByCriterion':continue
        option_id=prop['subject'].rsplit('/',1)[-1]
        option=next((o for o in evaluation['options'] if o['id']==option_id),None)
        if not option:continue
        criterion=prop['object']['value']
        return {'option_id':option_id,'key':option['key'],'criterion':criterion,'argument_id':argument['id'],
                'limits':'Current evidence and the stated criterion only; no optimal future policy or hidden probabilities are known.'}
    return None


def message(task,recommendation):
    return get_task(task).recommendation_message(recommendation)


def structured(task,condition,candidate):
    from .study import CONDITIONS
    style=CONDITIONS[condition]['style']
    issue=candidate['name']
    hook=getattr(get_task(task),'intervention_focus',None)
    focus=hook(issue) if hook else 'evidence_review'
    return {'version':VERSION,'task':task,'style':style,'personalised':CONDITIONS[condition]['personalised'],
            'issue':issue,'focus':focus,'recommendation':candidate.get('recommendation'),
            'supporting_arguments':list(candidate['supporting_arguments']),
            'opposing_arguments':list(candidate['opposing_arguments']),
            'limits':['Interpretations remain provisional.','The participant retains the final choice.']}
