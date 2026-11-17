"""Public comparison sets backed by accepted, state-scoped graph arguments.

These guide deliberation; they contain neither a prescribed action nor a
participant choice distribution. Task hooks rank and explain permitted options.
"""
import hashlib
from pathlib import Path
from .argumentation import ARG
from .tasks import get_task

VERSION = 'comparison-guidance-0.2'


def configuration(module):
    sources={'comparisons.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if callable(getattr(module,'select_comparisons',None)) and getattr(module,'__file__',None):
        sources[Path(module.__file__).name]=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    return {'version':VERSION,'enabled':callable(getattr(module,'select_comparisons',None)),
            'sources':sources,'notice':'Accepted graph reasons guide comparison; no participant distribution is prescribed.'}


def from_graph(task, evaluation, snapshot):
    report = snapshot['graph_argumentation']
    module = get_task(task)
    select = getattr(module, 'select_comparisons', None)
    if report['status'] != 'complete' or not callable(select):
        return []
    assertions = {a['id']: a for a in report['assertions']}
    available = {o['id']: o for o in evaluation['options']}
    grouped = {}
    for argument in report['arguments']:
        proposition = assertions[argument['conclusion']]['proposition']
        if (argument['label'] != 'accepted' or proposition['scope'] != report['scope'] or
                proposition['predicate'] != ARG + 'worthComparingFor' or proposition['polarity'] != 'positive'):
            continue
        identifier = proposition['subject'].rsplit('/', 1)[-1]
        if identifier not in available:
            continue
        item = grouped.setdefault(identifier, {'option_id': identifier, 'key': available[identifier]['key'],
                                               'criteria': [], 'argument_ids': []})
        item['criteria'].append(proposition['object']['value'])
        item['argument_ids'].append(argument['id'])
    for item in grouped.values():
        item['criteria'] = sorted(set(item['criteria']))
        item['argument_ids'] = sorted(set(item['argument_ids']))
    result = select(list(grouped.values()), snapshot['environment'], evaluation)
    # Never manufacture a second alternative to satisfy a presentation rule.
    return result if len(result) >= 2 else []


def context(task, comparisons, evaluation):
    if not comparisons:
        return ''
    return get_task(task).comparison_context(comparisons, evaluation)
