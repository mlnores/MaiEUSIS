"""Descriptive pilot summaries. No causal effects or psychological labels."""
import argparse
import json
import statistics
from pathlib import Path
from .engine import history
from .tasks import get_task


def summarize(session):
    h=history(session);valid=[x for x in h if not x['timed_out']]
    decisions=[e['snapshot']['decision'] for e in session['events'] if e.get('snapshot',{}).get('decision')]
    delivery=[e['input'] for e in session['events'] if e['input'].get('kind')=='delivery']
    responses=[e['input'] for e in session['events'] if e['input'].get('kind')=='response']
    latency=[x['generation_latency_ms'] for x in delivery]
    languages=[d['language'] for d in decisions if d.get('language')]
    result={'session_id':session['id'],'participant_id':session['participant_id'],'task':session['task'],'condition':session['condition'],
            'phase':session['phase'],'protocol':session['protocol'],'completed':session['completed'],'completed_trials':len(h),
            'timeouts':len(h)-len(valid),'median_response_ms':statistics.median([x['response_ms'] for x in valid if x['response_ms'] is not None]) if any(x['response_ms'] is not None for x in valid) else None,
            'eligible_points':len(decisions),'silence_decisions':sum(d['action']=='silence' for d in decisions),
            'prompts_delivered':sum(x['delivered'] for x in delivery),
            'total_reading_exposure_ms':sum(x['reading_exposure_ms'] for x in delivery),
            'mean_generation_latency_ms':statistics.mean(latency) if latency else None,
            'generated_question_decisions':sum(l['mode']=='ollama-generated' for l in languages),
            'language_fallbacks':sum('fallback_reason' in l for l in languages),
            'unexposed_active_decisions':sum(not x['delivered'] for x in delivery
                if any(d['id']==x['decision_id'] and d['action']!='silence' for d in decisions)),
            'pending_response_reviews':sum(e.get('interpretation',{}).get('status')=='pending-review' and not any(
                r['input'].get('kind')=='interpretation-review' and r['input']['response_event_id']==e['id']
                for r in session['events']) for e in session['events']),
            'early_response_attempts':sum(x['early_attempts'] for x in delivery),
            'disagreements':sum(x['feedback']=='disagree' for x in responses),
            'self_reported_helpful':sum(x['feedback']=='helpful' for x in responses),
            'unmeasured':['Appropriate reliance','Reasoning quality','Subjective confidence calibration','Causal intervention benefit','Workload beyond exposure and self-report']}
    result.update(get_task(session['task']).summarize(session,h,valid))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data-dir',default=str(Path(__file__).parent/'data'));parser.add_argument('--output',required=True);args=parser.parse_args()
    from .store import Store
    store=Store(Path(args.data_dir)/'sessions.sqlite3');rows=[summarize(store.get(s['id'])) for s in store.list()]
    Path(args.output).write_text(json.dumps(rows,indent=2)+'\n');print('Wrote descriptive summaries for',len(rows),'sessions')

if __name__=='__main__':main()
