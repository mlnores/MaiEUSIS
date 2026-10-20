"""Descriptive pilot summaries. No causal effects or psychological labels."""
import argparse
import json
import statistics
from pathlib import Path
from .engine import history


def summarize(session):
    h=history(session);valid=[x for x in h if not x['timed_out']]
    decisions=[e['snapshot']['decision'] for e in session['events'] if e.get('snapshot',{}).get('decision')]
    delivery=[e['input'] for e in session['events'] if e['input'].get('kind')=='delivery']
    responses=[e['input'] for e in session['events'] if e['input'].get('kind')=='response']
    latency=[x['generation_latency_ms'] for x in delivery]
    result={'session_id':session['id'],'participant_id':session['participant_id'],'task':session['task'],'condition':session['condition'],
            'phase':session['phase'],'protocol':session['protocol'],'completed':session['completed'],'completed_trials':len(h),
            'timeouts':len(h)-len(valid),'median_response_ms':statistics.median([x['response_ms'] for x in valid if x['response_ms'] is not None]) if any(x['response_ms'] is not None for x in valid) else None,
            'eligible_points':len(decisions),'silence_decisions':sum(d['action']=='silence' for d in decisions),
            'prompts_delivered':sum(x['delivered'] for x in delivery),
            'total_reading_exposure_ms':sum(x['reading_exposure_ms'] for x in delivery),
            'mean_generation_latency_ms':statistics.mean(latency) if latency else None,
            'early_response_attempts':sum(x['early_attempts'] for x in delivery),
            'disagreements':sum(x['feedback']=='disagree' for x in responses),
            'self_reported_helpful':sum(x['feedback']=='helpful' for x in responses),
            'unmeasured':['Appropriate reliance','Reasoning quality','Subjective confidence calibration','Causal intervention benefit','Workload beyond exposure and self-report']}
    if session['task']=='MAB':
        choices=[x['choice'] for x in valid]
        result.update({'final_score':h[-1]['score_after'] if h else 0,'sampled_arms':len(set(choices)),
                       'switch_rate':sum(a!=b for a,b in zip(choices,choices[1:]))/(len(choices)-1) if len(choices)>1 else None,
                       'regret':None,'regret_reason':'Needs hidden evaluator probabilities, which are absent from the teammate store.'})
    else:
        blocks=[x for x in h if x['remaining']==1]
        scores=[x['points_after']*(session['task_rules']['multipliers'][session['task_rules']['targets'].index(x['target'])] if x['outcome']>0 else 1) for x in blocks]
        result.update({'completed_blocks':len(blocks),'targets_met':sum(score>=b['target'] for score,b in zip(scores,blocks)),
                       'final_block_scores':scores,'risky_choice_rate':sum(x['choice']=='risky' for x in valid)/len(valid) if valid else None})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data-dir',default=str(Path(__file__).parent/'data'));parser.add_argument('--output',required=True);args=parser.parse_args()
    from .store import Store
    store=Store(Path(args.data_dir)/'sessions.sqlite3');rows=[summarize(store.get(s['id'])) for s in store.list()]
    Path(args.output).write_text(json.dumps(rows,indent=2)+'\n');print('Wrote descriptive summaries for',len(rows),'sessions')

if __name__=='__main__':main()
