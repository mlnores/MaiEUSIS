"""Public MAB ranking and an explicit, configurable performance assessment.

Only recorded outcomes and the public rolling reward model enter these rules.
The policy consumes graph proofs of eligibility, not this module as a trigger.
"""
import math
from statistics import mean, stdev
from ..records import fields, require, number

VERSION = 'mab-shared-guidance-0.1'
TOP_TWO = 'shared_top_two'
DEFAULTS = {'performance_gate': True, 'comparison_strategy': TOP_TWO,
            'window_trials': 12, 'min_observations': 6, 'min_remaining': 3,
            'min_gap_points': 20., 'decline_points': 30.}


def settings(policy):
    result = {**DEFAULTS, **policy.get('mab_guidance', {})}
    fields(result, list(DEFAULTS))
    require(type(result['performance_gate']) is bool, 'Invalid MAB performance gate')
    require(result['comparison_strategy'] in {TOP_TWO, 'legacy_uncertainty'}, 'Invalid MAB comparison strategy')
    require(all(type(result[k]) is int for k in ('window_trials', 'min_observations', 'min_remaining')),
            'MAB guidance windows must be integers')
    require(6 <= result['min_observations'] <= result['window_trials'] <= 200 and result['min_remaining'] >= 1,
            'Invalid MAB guidance evidence window or horizon')
    require(all(number(result[k], 0, 400) and result[k] > 0 for k in ('min_gap_points', 'decline_points')),
            'Invalid MAB guidance point thresholds')
    return result


def ranking(environment):
    """One total order; ties in recorded estimates use stable option IDs."""
    arms = sorted(environment['arms'], key=lambda a: (-a['estimated_value'], a['arm']))
    return [{'option_id': a['arm'], 'rank': i + 1, 'estimated_value': a['estimated_value'],
             'samples': a['samples'], 'approximate_95_interval': list(a['approximate_95_interval']),
             'tie_count': sum(b['estimated_value'] == a['estimated_value'] for b in arms)}
            for i, a in enumerate(arms)]


def assess(history, environment, remaining, config):
    window = history[-config['window_trials']:]
    valid = [r for r in window if not r['timed_out']]
    rewards = [r['outcome'] for r in valid]
    ordered = ranking(environment)
    best = ordered[0]
    average = mean(rewards) if rewards else None
    half = len(rewards) // 2
    decline = mean(rewards[:half]) - mean(rewards[half:]) if half >= 3 else None
    upper = average + 1.96 * stdev(rewards) / math.sqrt(len(rewards)) if len(rewards) >= 2 else None
    gap = best['estimated_value'] - average if average is not None else None
    signals = []
    if average is not None and average <= 0:
        signals.append('nonpositive_recent_mean')
    if decline is not None and decline >= config['decline_points']:
        signals.append('declining_recent_returns')
    if upper is not None and upper < best['approximate_95_interval'][0]:
        signals.append('below_supported_alternative')
    enough = len(valid) >= config['min_observations']
    eligible = enough and remaining >= config['min_remaining'] and bool(signals) and gap >= config['min_gap_points']
    if not enough:
        reason = f'Only {len(valid)} completed outcomes in the recent window; {config["min_observations"]} required.'
    elif remaining < config['min_remaining']:
        reason = f'Only {remaining} decisions remain; {config["min_remaining"]} required.'
    elif not signals:
        reason = 'Recent performance does not meet the configured poor-performance criteria.'
    elif gap < config['min_gap_points']:
        reason = f'Estimated improvement gap {gap:.2f} points is below {config["min_gap_points"]:g}.'
    else:
        reason = f'Recent mean {average:.2f}; first-ranked estimated mean {best["estimated_value"]:.2f}; gap {gap:.2f} points.'
    return {'version': VERSION, 'settings': dict(config), 'ranking': ordered,
            'performance': {'eligible': eligible, 'reason': reason, 'observations': len(valid),
                            'elapsed_trials': len(window), 'remaining': remaining,
                            'recent_mean': average, 'recent_mean_upper': upper, 'decline': decline,
                            'estimated_gap': gap, 'signals': signals,
                            'evidence': [r['trial_id'] for r in valid],
                            'limits': 'Authored screening thresholds and approximate uncertainty bounds; not a significance test, hidden regret or proof that switching helps.'}}
