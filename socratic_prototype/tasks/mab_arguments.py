"""MAB graph premises from public history; no hidden schedules or probabilities."""
from ..semantics import DATA


def project(w,session,event,state,h):
    valid=[row for row in h if not row['timed_out']]
    summary=state+'/history-summary';w.types(summary,'arg:HistorySummary')
    w.obj(summary,'arg:inState',state)
    w.value(summary,'mab:completedChoices',len(valid))
    w.value(summary,'mab:sampledArmCount',len({row['choice'] for row in valid}))
    w.value(summary,'mab:remainingDecisions',session['total_trials']-event['input']['index']+1)
    for row in valid:w.obj(summary,'task:basedOnObservation',DATA+row['trial_id']+'/choice')
    # Public-model benchmark, with explicit links to every input reward estimate.
    benchmark=state+'/comparison-benchmark'
    rule=w.rule(session['task_module']['definition_iri']+'/comparison-benchmark',
        'Greatest current estimated mean reward','socratic_prototype.tasks.mab_arguments.project',
        'comparison-guidance-0.1','Maximum of the six public Dirichlet mean estimates; not a hidden optimum.')
    w.calculation(benchmark,'mab:ComparisonBenchmark',state,rule,
                  max(a['estimated_value'] for a in event['snapshot']['environment']['arms']),
                  'reward-points',estimate=True)
    for a in event['snapshot']['environment']['arms']:
        w.obj(benchmark,'task:basedOnCalculation',state+'/reward/'+a['arm'])
