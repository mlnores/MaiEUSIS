"""Researcher-controlled Socratic processing assumptions, separate from strength."""
from .records import require
from .tasks.execution import simulation_adapter, validate_distribution

VERSION = 'reconsideration-0.2'
MECHANISMS = ('none', 'current', 'recent')


def configuration(module, mechanism):
    require(mechanism in MECHANISMS, 'Unknown reconsideration mechanism')
    adapter = simulation_adapter(module)
    if mechanism == 'recent':
        require(callable(getattr(adapter, 'reconsider_recent', None)) and
                isinstance(getattr(adapter, 'RECENT_RECONSIDERATION', None), dict),
                'Recent reconsideration is not implemented for ' + module.ID)
        assumptions = dict(adapter.RECENT_RECONSIDERATION)
    elif mechanism == 'none':
        assumptions = {'rule': 'Retain baseline preference; no directional revision or reactance. Distraction and omission costs still apply.'}
    else:
        assumptions = {'rule': 'Existing environment-owned public-evidence reconsideration heuristic.'}
    return {'version': VERSION, 'mechanism': mechanism, 'assumptions': assumptions,
            'execution': adapter.describe(),
            'notice': 'Authored processing assumption, not measured comprehension or a guarantee of benefit.'}


def target(module, mechanism, history, parameters, evaluation, intervention, baseline):
    configuration(module, mechanism)
    if mechanism == 'none' or ('comparisons' in intervention and len(intervention['comparisons']) < 2):
        result = dict(baseline)
    else:
        adapter = simulation_adapter(module)
        function = adapter.reconsider if mechanism == 'current' else adapter.reconsider_recent
        result = function(history, parameters, evaluation, intervention)
    return validate_distribution(result, evaluation['options'])
