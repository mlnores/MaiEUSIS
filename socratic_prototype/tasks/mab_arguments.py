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
    guidance=event['snapshot']['environment']['guidance']
    ranking_rule=w.rule(session['task_module']['definition_iri']+'/shared-ranking',
        'Shared estimated-reward ranking','socratic_prototype.tasks.mab_guidance.ranking',
        guidance['version'],'Descending public mean; equal recorded estimates use ascending option ID, not evidence of superiority.')
    for item in guidance['ranking']:
        identifier=state+'/rank/'+item['option_id']
        option=session['task_module']['definition_iri']+'/arm/'+item['option_id']
        w.calculation(identifier,'mab:RewardRank',state,ranking_rule,item['rank'],'ordinal-rank',option,True)
        w.value(identifier,'mab:tieCount',item['tie_count'])
        for a in guidance['ranking']:w.obj(identifier,'task:basedOnCalculation',state+'/reward/'+a['option_id'])
    performance=guidance['performance'];config=guidance['settings'];identifier=state+'/performance'
    # An unobserved mean/gap is unknown, not a zero-valued calculation. The
    # JSON assessment retains its insufficiency reason; no numeric proof exists.
    if performance['estimated_gap'] is None:return
    performance_rule=w.rule(session['task_module']['definition_iri']+'/performance-screen',
        'Recent observed performance screen','socratic_prototype.tasks.mab_guidance.assess',guidance['version'],
        'Minimum evidence and horizon, poor-performance signal, and minimum estimated improvement gap. Authored thresholds; not a hypothesis test.')
    w.calculation(identifier,'mab:PerformanceAssessment',state,performance_rule,performance['estimated_gap'],
                  'reward-points',estimate=True)
    for key,predicate in [('observations','mab:completedChoices'),('remaining','mab:remainingDecisions'),
                          ('recent_mean','mab:recentMean'),('recent_mean_upper','mab:recentMeanUpper'),
                          ('decline','mab:recentDecline')]:w.value(identifier,predicate,performance[key])
    w.value(identifier,'mab:poorPerformanceSignal',bool(performance['signals']))
    for key,predicate in [('min_observations','mab:minObservations'),('min_remaining','mab:minRemaining'),
                          ('min_gap_points','mab:minGapPoints')]:w.value(identifier,predicate,config[key])
    for trial in performance['evidence']:w.obj(identifier,'task:basedOnObservation',DATA+trial+'/outcome')
    for a in guidance['ranking']:w.obj(identifier,'task:basedOnCalculation',state+'/reward/'+a['option_id'])
