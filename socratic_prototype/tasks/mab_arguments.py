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
