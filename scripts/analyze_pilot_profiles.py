#!/usr/bin/env python3
"""Audit an archived MAB/TBS pilot and describe effects by original profile.

Reads frozen evaluator reports directly: never imports or executes the current
simulation package, rewrites a historical manifest, or touches a running pilot.
The core report uses only Python's standard library; --plot optionally uses Plotly.
"""
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from html import escape
from pathlib import Path
from statistics import mean, median

PROFILES = ['MAB-specialised', 'TBS-specialised', 'Dual-regime', 'Low-expression']
VARIANTS = [('C', 'current'), ('E', 'current'), ('D', 'current'), ('F', 'current'),
            ('D', 'recent'), ('F', 'recent')]
LABELS = ['C direct', 'E personalised direct', 'D Socratic/current',
          'F personalised/current', 'D Socratic/recent', 'F personalised/recent']
CONTRASTS = {'E-C': {'E': 1, 'C': -1}, 'F-D': {'F': 1, 'D': -1},
             'D-C': {'D': 1, 'C': -1}, 'F-E': {'F': 1, 'E': -1},
             '(F-D)-(E-C)': {'F': 1, 'D': -1, 'E': -1, 'C': 1}}


def read(path):
    return json.loads(Path(path).read_text())


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def checked(condition, message):
    if not condition:
        raise ValueError(message)


def equal(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def sign(value):
    return 0 if abs(value) < 1e-9 else 1 if value > 0 else -1


def describe(values):
    return {'participants': len(values), 'mean': mean(values), 'median': median(values),
            'minimum': min(values), 'maximum': max(values),
            'better': sum(sign(v) > 0 for v in values), 'same': sum(sign(v) == 0 for v in values),
            'worse': sum(sign(v) < 0 for v in values)}


def audit(directory):
    manifest = read(directory/'manifest.json')
    checked(fingerprint({k:v for k,v in manifest.items() if k != 'sha256'}) == manifest['sha256'], 'Altered manifest')
    actors = read(directory/'participants.json')
    checked(fingerprint(actors) == manifest['actors_sha256'], 'Altered frozen actor export')
    config = manifest['configuration']; mechanisms = config['mechanisms']
    checked(set(config['study']['tasks']) == {'MAB', 'TBS'}, 'This analysis describes MAB and TBS outcomes')
    checked(set(mechanisms) == {'none', 'current', 'recent'}, 'All three mechanisms are required')
    checked(not any(config['response_parameters'][n] for n in ('reactance','distraction','omission_probability')),
            'This report assumes zero additional reactance, distraction and AI omission costs')
    checked(not config.get('max_trials'), 'Capped engineering pilots do not provide full-protocol outcomes')
    checked(config['primary_outcomes']['MAB']['metric'] == 'score' and
            config['primary_outcomes']['MAB']['divisor'] == 1 and
            config['primary_outcomes']['TBS']['metric'] == 'targets_attained' and
            config['primary_outcomes']['TBS']['divisor'] == 24, 'Unexpected primary metric or unit')
    checked(len(actors) == config['expected_participants'] and len({a['id'] for a in actors}) == len(actors), 'Actor count or duplicate identity')
    checked(dict(Counter(a['original_profile'] for a in actors)) == config['expected_profiles'], 'Unexpected profile assignments')
    expected = {}
    for actor in actors:
        for repeat in range(config['repeats']):
            for mechanism in mechanisms:
                case = {'participant': actor['id'], 'repeat': repeat, 'mechanism': mechanism}
                case['id'] = 'job_' + fingerprint(case)[:16]
                expected[case['id']] = case
    results, index = {}, {}
    calibrations = 0
    versions = set()
    for path in sorted((directory/'jobs').glob('*/result.json')):
        result = read(path); job = result['job_id']
        checked(job not in results and path.parent.name == job and result['case'] == expected.get(job), 'Unexpected or duplicate job')
        checked(result['manifest_sha256'] == manifest['sha256'], 'Job from a different pilot')
        checked(fingerprint(result['rows']) == result['summary_sha256'], 'Altered summary')
        report_file = (directory/result['report_file']).resolve()
        checked(report_file.is_relative_to(directory.resolve()), 'Report outside pilot directory')
        checked(hashlib.sha256(report_file.read_bytes()).hexdigest() == result['report_sha256'], 'Altered evaluator report')
        report = read(report_file)
        versions.add((report['version'], report['agent_version'], report['response_version']))
        checked(len(report['calibrations']) == len(config['study']['tasks']), 'Calibration count mismatch')
        calibrations += len(report['calibrations'])
        for actor in report['participants']:
            for task in config['study']['tasks']:
                for style in ('direct', 'socratic'):
                    checked(actor['response_parameters'][task][style] == config['response_parameters'], 'Unexpected AI response coefficients')
        runs = {(r['task'], r['condition']):r for r in report['runs']}
        checked(len(runs) == len(report['runs']) == len(result['rows']) == 10, 'Unexpected comparison count')
        checked(set(runs) == {(t,c) for t in config['study']['tasks'] for c in config['study']['conditions']}, 'Missing task/condition')
        for row in result['rows']:
            run = runs[(row['task'], row['condition'])]; trials = run['trials']
            checked(run['completed'] and row['completed'], 'Incomplete comparison protocol')
            checked(len(trials) == row['trials'] and [t['index'] for t in trials] == list(range(1,len(trials)+1)), 'Trial sequence mismatch')
            checked(row['session_id'] == run['session_id'] and row['participant'] == result['case']['participant'], 'Session/actor mismatch')
            checked(fingerprint([(t['index'],t['choice'],t['outcome']) for t in trials]) == row['trajectory_sha256'], 'Trajectory mismatch')
            checked(fingerprint([t['assisted_probabilities'] for t in trials]) == row['distribution_sha256'], 'Distribution mismatch')
            outcome = config['primary_outcomes'][row['task']]
            checked(equal(run['metrics'][outcome['metric']]/outcome['divisor'], row['primary_value']), 'Outcome summary mismatch')
            checked(sum(t['effect'].get('applied',False) for t in trials) == row['active_interventions'], 'Intervention count mismatch')
            checked(sum(t['choice'] == 'NO_RESPONSE' for t in trials) == row['omissions'], 'Omission count mismatch')
            checked(row['repeat'] == result['case']['repeat'] and row['mechanism'] == result['case']['mechanism'], 'Case summary mismatch')
            key = (row['participant'], row['repeat'], row['task'], row['mechanism'], row['condition'])
            checked(key not in index, 'Duplicate outcome row')
            index[key] = {**row, 'primary_numerator':run['metrics'][outcome['metric']],
                          'primary_divisor':outcome['divisor']}
        results[job] = result
    checked(set(results) == set(expected), 'Pilot must be complete before this profile analysis')
    cross_checks = no_revision_checks = tbs_pairs = tbs_identical = 0
    for actor in actors:
        for repeat in range(config['repeats']):
            for task in config['study']['tasks']:
                for condition in ('A', 'C', 'E'):
                    values = [index[(actor['id'],repeat,task,m,condition)] for m in mechanisms]
                    checked(len({(v['primary_value'],v['trajectory_sha256'],v['distribution_sha256']) for v in values}) == 1, 'Mechanism control failed')
                    cross_checks += 1
                if not any(config['response_parameters'][n] for n in ('distraction','omission_probability')):
                    baseline = index[(actor['id'],repeat,task,'none','A')]
                    for condition in ('D','F'):
                        row = index[(actor['id'],repeat,task,'none',condition)]
                        checked(all(row[k] == baseline[k] for k in ('primary_value','trajectory_sha256','distribution_sha256')), 'No-revision control failed')
                        no_revision_checks += 1
            for mechanism in mechanisms:
                for personalised,generic in [('E','C'),('F','D')]:
                    a = index[(actor['id'],repeat,'TBS',mechanism,personalised)]
                    b = index[(actor['id'],repeat,'TBS',mechanism,generic)]
                    tbs_pairs += 1
                    tbs_identical += all(a[k] == b[k] for k in ('primary_value','trajectory_sha256','distribution_sha256'))
    return manifest, actors, index, {'manifest_sha256': manifest['sha256'], 'actors_sha256': manifest['actors_sha256'],
        'jobs': len(results), 'comparison_sessions': len(index), 'calibration_sessions': calibrations,
        'verified_evaluator_reports': len(results), 'recomputed_trial_summaries': len(index),
        'cross_mechanism_controls': cross_checks, 'no_revision_controls': no_revision_checks,
        'tbs_personalisation_pairs': tbs_pairs, 'tbs_personalisation_pairs_identical': tbs_identical,
        'source_versions': [list(v) for v in sorted(versions)],
        'execution_versions': {k:v['version'] for k,v in manifest['study']['execution'].items()}}


def analyse(directory):
    manifest, actors, index, checks = audit(directory)
    config = manifest['configuration']; individuals = []
    for actor in actors:
        for task in ('MAB','TBS'):
            scale = 100 if task == 'TBS' else 1
            for mechanism in config['mechanisms']:
                for condition in ('C','E','D','F'):
                    values = [index[(actor['id'],r,task,mechanism,condition)] for r in range(config['repeats'])]
                    baselines = [index[(actor['id'],r,task,mechanism,'A')] for r in range(config['repeats'])]
                    differences = [(Fraction(v['primary_numerator'])-Fraction(b['primary_numerator'])) /
                                   Fraction(v['primary_divisor']) for v,b in zip(values,baselines)]
                    individuals.append({'participant': actor['id'], 'original_profile': actor['original_profile'],
                        'task': task, 'condition': condition, 'mechanism': mechanism, 'repetitions': len(values),
                        'unit': 'percentage points of targets attained' if task == 'TBS' else 'points',
                        'mean_improvement_from_A': float(mean(differences)*scale),
                        'repetition_changes_from_A': [float(d*scale) for d in differences],
                        'baseline': float(mean(Fraction(b['primary_numerator'])/Fraction(b['primary_divisor']) for b in baselines)*scale),
                        'assisted': float(mean(Fraction(v['primary_numerator'])/Fraction(v['primary_divisor']) for v in values)*scale),
                        'mean_interventions': mean(v['active_interventions'] for v in values),
                        'mean_omissions': mean(v['omissions'] for v in values)})
    cached = read(directory/'analysis.json')
    checked(cached['manifest_sha256'] == manifest['sha256'] and cached['complete'], 'Cached report from another or incomplete run')
    original = {(r['participant'],r['task'],r['condition'],r['mechanism']):r for r in cached['individual_results']}
    checked(len(original) == len(individuals), 'Cached individual count mismatch')
    zero_corrections = []
    for row in individuals:
        old = original[(row['participant'],row['task'],row['condition'],row['mechanism'])]
        checked(equal(row['mean_improvement_from_A']/(100 if row['task']=='TBS' else 1),old['mean_improvement_from_A']), 'Cached individual outcome mismatch')
        if row['mean_improvement_from_A']==0 and old['mean_improvement_from_A']!=0:
            zero_corrections.append({k:row[k] for k in ('participant','task','condition','mechanism')} |
                                    {'cached_raw_mean':old['mean_improvement_from_A'],'exact_mean':0})
    groups = []
    for task in ('MAB','TBS'):
        for profile in [*PROFILES,'all']:
            for condition in ('C','E','D','F'):
                for mechanism in config['mechanisms']:
                    values = [r for r in individuals if r['task']==task and r['condition']==condition and
                              r['mechanism']==mechanism and (profile=='all' or r['original_profile']==profile)]
                    groups.append({'task':task,'profile':profile,'condition':condition,'mechanism':mechanism,
                        **describe([r['mean_improvement_from_A'] for r in values]),
                        'mean_baseline':mean(r['baseline'] for r in values),'mean_assisted':mean(r['assisted'] for r in values),
                        'mean_interventions':mean(r['mean_interventions'] for r in values)})
    original_groups = {(r['task'],r['profile'],r['condition'],r['mechanism']):r for r in cached['aggregates']}
    checked(len(original_groups) == len(groups), 'Cached aggregate count mismatch')
    count_corrections = []
    for row in groups:
        old = original_groups[(row['task'],row['profile'],row['condition'],row['mechanism'])]
        scale = 100 if row['task']=='TBS' else 1
        checked(all(equal(row[new]/scale,old[old_key]) for new,old_key in
                    [('mean','mean_improvement_from_A'),('minimum','min_individual_improvement'),('maximum','max_individual_improvement')]), 'Cached group effect mismatch')
        checked(row['participants']==old['participants'] and
                equal(row['mean_interventions'],old['mean_interventions']), 'Cached group counts mismatch')
        members = [r for r in individuals if (r['task'],r['condition'],r['mechanism']) ==
                   (row['task'],row['condition'],row['mechanism']) and
                   (row['profile']=='all' or r['original_profile']==row['profile'])]
        strict_cached = sum(original[(r['participant'],r['task'],r['condition'],r['mechanism'])]['mean_improvement_from_A']<0 for r in members)
        checked(strict_cached==old['participants_worse_than_A'],'Cached harm count is inconsistent with its actor means')
        if row['worse']!=old['participants_worse_than_A']:
            corrected = [r['participant'] for r in members if r['mean_improvement_from_A']==0 and
                         -1e-9 < original[(r['participant'],r['task'],r['condition'],r['mechanism'])]['mean_improvement_from_A'] < 0]
            checked(old['participants_worse_than_A']-row['worse']==len(corrected),
                    'Cached harm-count discrepancy exceeds exact-zero roundoff')
            count_corrections.append({k:row[k] for k in ('task','profile','condition','mechanism')} |
                                     {'cached_worse':old['participants_worse_than_A'],
                                      'reported_worse':row['worse'],'exact_ties':corrected})
    by_individual = {(r['participant'],r['task'],r['mechanism'],r['condition']):r for r in individuals}
    contrasts, changes = [], []
    for task in ('MAB','TBS'):
        for profile in PROFILES:
            people = [a['id'] for a in actors if a['original_profile']==profile]
            for mechanism in ('current','recent'):
                for name,weights in CONTRASTS.items():
                    differences = [sum(w*by_individual[(p,task,mechanism,c)]['mean_improvement_from_A'] for c,w in weights.items()) for p in people]
                    contrasts.append({'task':task,'profile':profile,'mechanism':mechanism,'contrast':name,**describe(differences)})
            for condition in ('D','F'):
                pairs = [(p,by_individual[(p,task,'current',condition)]['mean_improvement_from_A'],
                            by_individual[(p,task,'recent',condition)]['mean_improvement_from_A']) for p in people]
                changes.append({'task':task,'profile':profile,'condition':condition,
                    'mean_recent_minus_current':mean(recent-current for _,current,recent in pairs),
                    'sign_reversals':[p for p,current,recent in pairs if sign(current)*sign(recent)==-1],
                    'changed_outcomes':[p for p,current,recent in pairs if not equal(current,recent)]})
    checks.update(cached_individual_effects_verified=len(individuals),cached_aggregates_verified=len(groups),
                  exact_zero_corrections=zero_corrections,harm_count_roundoff_corrections=count_corrections)
    return {'generated_at_utc':datetime.now(timezone.utc).isoformat(),'source_directory':str(directory.resolve()),
            'analysis_implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'audit':checks,'configuration':config,'individual_results':individuals,'group_results':groups,
            'contrasts':contrasts,'mechanism_changes':changes,
            'notice':'Exploratory descriptive simulation: four deliberately selected actors per original profile and '
                     f"{config['repeats']} repetition(s). Mechanisms are sensitivity assumptions, not extra participants. "
                     'AI response coefficients are identical across profiles. Original labels are grouping metadata, '
                     'not inferred AI attitudes or guaranteed task strengths. Historical TBS offers are missing and '
                     'the provisional TBS actor underperformed its held-out frequency baseline. '
                     'Results describe the archived pre-comparison-guidance implementation; no human assistance effects, '
                     'significance tests, new clustering, or intervention policy tuning are claimed.'}


def markdown(report):
    rows = report['group_results']; lines = ['# Earlier pilot: original-profile breakdown','',report['notice'],'',
        f"Manifest: `{report['audit']['manifest_sha256']}`.", '',
        f"Verified {report['audit']['jobs']} jobs, {report['audit']['comparison_sessions']} full comparisons, "
        f"{report['audit']['calibration_sessions']} calibrations, {report['audit']['cross_mechanism_controls']} cross-mechanism "
        f"and {report['audit']['no_revision_controls']} no-revision checks. Cached means are reconciled; exact score/target numerators determine ties. Any floating-point zero corrections are recorded in the audit.", '',
        'C = task-aware direct; E = personalised direct; D = task-aware Socratic; F = personalised Socratic. '
        'Direct effects are identical across mechanisms. With none, D/F equal A. Each actor is counted once per cell.']
    for task in ('MAB','TBS'):
        unit = 'points' if task=='MAB' else 'percentage points'
        lines += ['',f'## {task}: mean paired change from A ({unit})','',
                  '| Original profile | '+' | '.join(LABELS)+' |','| --- | '+' | '.join(['---:']*6)+' |']
        for profile in PROFILES:
            values = [next(r for r in rows if (r['task'],r['profile'],r['condition'],r['mechanism'])==(task,profile,c,m)) for c,m in VARIANTS]
            lines.append('| '+profile+' | '+' | '.join(f"{r['mean']:+,.2f}" for r in values)+' |')
        lines += ['', 'Counts below are **better / same / worse** than A, out of four actors.', '',
                  '| Original profile | '+' | '.join(LABELS)+' |','| --- | '+' | '.join(['---:']*6)+' |']
        for profile in PROFILES:
            values = [next(r for r in rows if (r['task'],r['profile'],r['condition'],r['mechanism'])==(task,profile,c,m)) for c,m in VARIANTS]
            lines.append('| '+profile+' | '+' | '.join(f"{r['better']}/{r['same']}/{r['worse']}" for r in values)+' |')
        lines += ['',f'### {task}: personalisation and communication contrasts ({unit})','',
                  'Positive E-C/F-D favours personalisation; positive D-C/F-E favours Socratic over direct.', '',
                  '| Original profile | Mechanism | E-C | F-D | D-C | F-E | Interaction (F-D)-(E-C) |',
                  '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
        for profile in PROFILES:
            for mechanism in ('current','recent'):
                values = [next(r for r in report['contrasts'] if (r['task'],r['profile'],r['mechanism'],r['contrast'])==(task,profile,mechanism,c)) for c in CONTRASTS]
                lines.append('| '+profile+' | '+mechanism+' | '+' | '.join(f"{r['mean']:+,.2f}" for r in values)+' |')
        lines += ['',f'### {task}: individual changes from A ({unit})','',
                  '| Original profile | Actor | '+' | '.join(LABELS)+' |','| --- | --- | '+' | '.join(['---:']*6)+' |']
        for profile in PROFILES:
            people = sorted({r['participant'] for r in report['individual_results'] if r['original_profile']==profile})
            for person in people:
                values = [next(r for r in report['individual_results'] if (r['participant'],r['task'],r['condition'],r['mechanism'])==(person,task,c,m)) for c,m in VARIANTS]
                lines.append('| '+profile+' | '+person.removeprefix('reconstructed_')+' | '+' | '.join(f"{r['mean_improvement_from_A']:+,.2f}" for r in values)+' |')
    return '\n'.join(lines)+'\n'


def absolute_tables(report):
    """Final group levels alongside the existing change-from-baseline charts."""
    groups = {(r['task'],r['profile'],r['condition'],r['mechanism']):r for r in report['group_results']}
    same_tbs = report['audit']['tbs_personalisation_pairs'] == report['audit']['tbs_personalisation_pairs_identical']
    sections = ['<section id="absolute-averages"><h2>Absolute group averages</h2>',
        '<p>These tables show mean final outcomes. The charts below show changes from A. '
        'A = no assistance; C = task-aware direct advice; E = personalised direct advice; '
        'D = task-aware Socratic questions; F = personalised Socratic questions. '
        'Current and recent identify the processing mechanism. With none, D/F match A; '
        'C/E are invariant across mechanisms.</p>']
    for task in ('MAB','TBS'):
        variants = VARIANTS
        headers = ['C','E','D current','F current','D recent','F recent']
        if task == 'TBS' and same_tbs:
            variants = [('C','current'),('D','current'),('D','recent')]
            headers = ['C = E','D = F current','D = F recent']
        caption = 'MAB: mean final score (points)' if task == 'MAB' else 'TBS: mean targets attained (%)'
        rows = [f'<div class="table-scroll"><table class="stats-table" id="{task.lower()}-absolute">',
                f'<caption>{caption}</caption><thead><tr><th scope="col">Archetype</th>',
                '<th scope="col" class="baseline">A · no assistance</th>']
        rows.extend(f'<th scope="col">{escape(label)}</th>' for label in headers)
        rows.append('</tr></thead><tbody>')
        for profile in PROFILES:
            baseline = groups[(task,profile,'C','current')]['mean_baseline']
            values = [baseline]+[groups[(task,profile,c,m)]['mean_assisted'] for c,m in variants]
            display = [f'{value:,.0f}' if task == 'MAB' else f'{value:.2f}%' for value in values]
            rows.append(f'<tr><th scope="row">{escape(profile)}</th>')
            rows.append(f'<td class="baseline">{display[0]}</td>')
            rows.extend(f'<td>{value}</td>' for value in display[1:])
            rows.append('</tr>')
        rows.append('</tbody></table></div>')
        sections.extend(rows)
    repeats = report['configuration']['repeats']
    counts = sorted({r['participants'] for r in report['group_results'] if r['profile'] != 'all'})
    count_text = str(counts[0]) if len(counts) == 1 else '–'.join(map(str,(min(counts),max(counts))))
    sections.append(f'<p class="table-note">{count_text} synthetic actors per archetype; '
                    f'{repeats} matched repetition(s) per actor. TBS percentages refer to targets attained '
                    'over 24 blocks. Each actor is counted once per table cell.</p></section>')
    return ''.join(sections)


def group_average_visualizations(report):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    groups = {(r['task'],r['profile'],r['condition'],r['mechanism']):r for r in report['group_results']}
    columns = LABELS
    fig = make_subplots(rows=1,cols=2,horizontal_spacing=.16,
                        subplot_titles=('MAB: mean score difference from A (points)',
                                        'TBS: mean target-attainment difference from A (percentage points)'))
    for column,task in enumerate(('MAB','TBS'),1):
        z,hover,labels = [],[],[]
        for profile in PROFILES:
            baseline = groups[(task,profile,'C','current')]
            values = [groups[(task,profile,c,m)]['mean_assisted'] for c,m in VARIANTS]
            changes = [groups[(task,profile,c,m)]['mean'] for c,m in VARIANTS]
            labels.append(f"{profile} (n={baseline['participants']})")
            z.append(changes)
            hover.append([f"{profile}<br>Mean difference from A: {change:+,.0f} points<br>Mean final outcome: {value:,.0f} points"
                          if task=='MAB' else
                          f"{profile}<br>Mean difference from A: {change:+.2f} percentage points<br>Mean targets attained: {value:.2f}%"
                          for value,change in zip(values,changes)])
        limit = max(abs(v) for row in z for v in row) or 1
        fig.add_trace(go.Heatmap(z=z,x=columns,y=labels,zmin=-limit,zmax=limit,zmid=0,colorscale='RdBu',
            customdata=hover,text=[[f'{v:+,.0f}' if task=='MAB' else f'{v:+.2f}' for v in row] for row in z],
            texttemplate='%{text}',hovertemplate='%{x}<br>%{customdata}<extra></extra>',
            colorbar=dict(x=.44 if column==1 else 1.02,thickness=10,len=.8,
                          ticksuffix=' pp' if task=='TBS' else '')),row=1,col=column)
        fig.update_yaxes(autorange='reversed',side='left' if column==1 else 'right',row=1,col=column)
        fig.update_xaxes(tickangle=-35,row=1,col=column)
    fig.update_layout(template='plotly_white',height=570,margin=dict(l=180,r=180,t=65,b=185),
                      font=dict(family='Arial, sans-serif',size=12),title='Group-average differences from A: earlier pilot')
    return ('<section id="group-average-visualizations"><h2>Group-average outcomes</h2>'
        '<p>Mean paired differences from each archetype’s unassisted A baseline. '
        'Blue indicates a gain; red indicates a loss; zero is neutral. Each task uses its own '
        'symmetric colour scale centred on zero, shared across all archetypes and conditions. '
        'MAB differences are points; TBS differences are percentage points, not relative percentages. '
        'Hover for the difference and the absolute mean. '
        'C/E and all active Socratic processing variants are shown separately, including identical TBS cells.</p>'
        '<div class="chart">'+fig.to_html(full_html=False,include_plotlyjs=False)+'</div></section>')


def plot(report, output):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    figures = []
    participants = {r['participant']:r['original_profile'] for r in report['individual_results']}
    profile_counts = Counter(participants.values())
    repeats = report['configuration']['repeats']
    sample_note = (f'<p id="pilot-sample"><strong>Pilot sample: {len(participants)} synthetic actors.</strong> '
        f'The n labels count the individual actors actually tested in each archetype, with {repeats} '
        'matched repetition(s) per actor. These results describe the selected development sample. '
        'Grouping the complete 62-person registry preserves profile membership; it does not supply '
        'assistance outcomes for the remaining evaluation actors.</p>')
    for individual in (False, True):
        fig = make_subplots(rows=1,cols=2,horizontal_spacing=.16,
                            subplot_titles=('MAB: points gained/lost from A','TBS: percentage-point change in targets attained'))
        if individual:
            identities = [(p,a) for p in PROFILES for a in sorted({r['participant'] for r in report['individual_results'] if r['original_profile']==p})]
            labels = [p+' · '+a.removeprefix('reconstructed_') for p,a in identities]
        else:
            labels = [f'{p} (n={profile_counts[p]})' for p in PROFILES]
        for column,task in enumerate(('MAB','TBS'),1):
            z,hover = [],[]
            for identity in identities if individual else PROFILES:
                zr,hr = [],[]
                for condition,mechanism in VARIANTS:
                    if individual:
                        profile,person = identity
                        row = next(r for r in report['individual_results'] if (r['participant'],r['task'],r['condition'],r['mechanism'])==(person,task,condition,mechanism))
                        value = row['mean_improvement_from_A']
                        detail = f"{profile} · {person.removeprefix('reconstructed_')}<br>Change: {value:+.2f}<br>Baseline: {row['baseline']:.2f}<br>Assisted: {row['assisted']:.2f}<br>Interventions: {row['mean_interventions']:.1f}"
                    else:
                        row = next(r for r in report['group_results'] if (r['profile'],r['task'],r['condition'],r['mechanism'])==(identity,task,condition,mechanism))
                        value = row['mean']
                        detail = f"{identity}<br>Mean change: {value:+.2f}<br>Median: {row['median']:+.2f}<br>Range: {row['minimum']:+.2f} to {row['maximum']:+.2f}<br>Better / same / worse: {row['better']} / {row['same']} / {row['worse']}<br>Mean interventions: {row['mean_interventions']:.1f}"
                    zr.append(value);hr.append(detail)
                z.append(zr);hover.append(hr)
            limit = max(abs(v) for row in z for v in row)
            fig.add_trace(go.Heatmap(z=z,x=LABELS,y=labels,zmin=-limit,zmax=limit,
                colorscale='RdBu',customdata=hover,text=[[f'{v:+.0f}' if task=='MAB' else f'{v:+.2f}' for v in row] for row in z],
                texttemplate='%{text}',hovertemplate='%{x}<br>%{customdata}<extra></extra>',
                colorbar=dict(x=.44 if column==1 else 1.02,thickness=10,len=.8)),row=1,col=column)
            fig.update_yaxes(autorange='reversed',side='left' if column==1 else 'right',row=1,col=column)
            fig.update_xaxes(tickangle=-35,row=1,col=column)
        fig.update_layout(template='plotly_white',height=820 if individual else 520,
            margin=dict(l=180,r=180,t=65,b=160),font=dict(family='Arial, sans-serif',size=12),
            title='Individual actors' if individual else 'Original profile means: earlier pilot')
        figures.append(fig.to_html(full_html=False,include_plotlyjs=True if not individual else False))
    same_tbs = report['audit']['tbs_personalisation_pairs'] == report['audit']['tbs_personalisation_pairs_identical']
    tbs_note = 'TBS C=E and D=F in this archived run.' if same_tbs else 'TBS personalisation contrasts vary; inspect individual results.'
    text = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Earlier pilot: original-profile effects</title><style>body{font:16px system-ui;max-width:1500px;margin:30px auto;padding:0 20px;color:#243247}p{max-width:1100px;line-height:1.5}.plotly-graph-div{min-width:1050px}.chart,.table-scroll{overflow-x:auto}code{font-size:13px}.stats-table{border-collapse:collapse;width:100%;margin:12px 0 24px;font-size:14px;font-variant-numeric:tabular-nums}.stats-table caption{text-align:left;font-size:18px;font-weight:600;margin:0 0 12px}.stats-table th,.stats-table td{padding:12px 14px;text-align:right;white-space:nowrap;border-bottom:1px solid #dbe2ea}.stats-table thead th{background:#f1f4f8;border-bottom:2px solid #b8c6d6}.stats-table th:first-child{text-align:left}.stats-table .baseline{background:#edf3fa}.table-note{font-size:14px;color:#506176}</style><h1>Earlier pilot: original-profile effects</h1><p>'+report['notice']+'</p>'+sample_note+absolute_tables(report)+'<section id="changes-from-baseline"><h2>Changes from no assistance</h2><p><strong>Blue = gain; red = loss.</strong> MAB and TBS use separate units and colour scales. Hover for individual ranges and harm counts. C/E are invariant across mechanisms; none D/F equal A. '+tbs_note+'</p>'+''.join('<div class="chart">'+figure+'</div>' for figure in figures)+'</section>'+group_average_visualizations(report)+'<p>Frozen manifest: <code>'+report['audit']['manifest_sha256']+'</code></p></html>'
    output.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--plot',action='store_true',help='Also write a self-contained interactive Plotly HTML (optional installed dependency)')
    args = parser.parse_args()
    output = args.output_dir.resolve(); source = args.pilot_dir.resolve()
    checked(not output.is_relative_to(source), 'Keep derived analysis outside the frozen pilot')
    output.mkdir(parents=True,exist_ok=True)
    report = analyse(source)
    (output/'analysis.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    (output/'report.md').write_text(markdown(report))
    if args.plot:
        plot(report,output/'profile_effects.html')
    print(json.dumps(report['audit'],indent=2))
    print('Saved profile analysis:',output)


if __name__ == '__main__':
    main()
