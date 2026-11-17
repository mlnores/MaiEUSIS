"""One task-owned response rule; historical memory variants are retired."""
from .records import require
from .tasks.execution import simulation_adapter, validate_distribution

VERSION = 'reconsideration-0.4'
# Kept as fixed metadata for existing analysis formats, not an experimental axis.
MECHANISMS = ('current',)


def configuration(module, mechanism='current'):
    require(mechanism == 'current', 'Socratic memory variants are retired; new runs use the single default response rule')
    adapter = simulation_adapter(module)
    assumptions = dict(getattr(adapter, 'CURRENT_RECONSIDERATION',
                               {'rule': 'Single task-owned evidence response. No memory truncation or no-revision variant.'}))
    return {'version': VERSION, 'mechanism': mechanism, 'assumptions': assumptions,
            'execution': adapter.describe(),
            'notice': 'Authored processing assumption, not measured comprehension or a guarantee of benefit.'}


def target(module, mechanism, history, parameters, evaluation, intervention, baseline):
    configuration(module, mechanism)
    if 'comparisons' in intervention and len(intervention['comparisons']) < 2:
        result = dict(baseline)
    else:
        adapter = simulation_adapter(module)
        result = adapter.reconsider(history, parameters, evaluation, intervention)
    return validate_distribution(result, evaluation['options'])
