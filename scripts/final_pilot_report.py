#!/usr/bin/env python3
"""Create a separate final HTML heatmap report only after a pilot is complete.

Uses the archived-report integrity audit; never executes task simulations or
writes to a source pilot. Plotly is needed only for report rendering.
"""
import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from statistics import mean, stdev

import analyze_pilot_profiles as profiles


def await_completion(source, seconds):
    deadline = time.monotonic()+seconds
    last = None
    while True:
        status = profiles.read(source/'status.json')
        analysis = profiles.read(source/'analysis.json')
        progress = (status['completed_jobs'],status['total_jobs'])
        if progress != last:
            print(f'Pilot progress: {progress[0]}/{progress[1]} jobs',flush=True)
            last = progress
        profiles.checked(analysis['control_checks_passed'] and not status.get('failures'),
                         'Pilot has failed controls or workers; inspect it before reporting')
        if status['status']=='complete' and analysis['complete']:
            return
        profiles.checked(status['status'] in {'running','stopping','complete'},
                         'Pilot is not running or complete; resume it before creating a final report')
        profiles.checked(time.monotonic()<deadline,'Pilot has not finished; no final report was generated')
        time.sleep(5)


def prepare_report(source, title):
    report = profiles.analyse(source)
    report['title'] = title
    report['renderer_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['notice'] = ('Descriptive synthetic experiment with '+str(report['configuration']['expected_participants'])+
        ' selected development actors, four per original archetype. All configured repetitions and all three '
        'processing mechanisms are complete. Repetitions are averaged within each actor before group means '
        'are calculated. AI responsiveness is fixed at '+str(report['configuration']['response_parameters']['responsiveness'])+
        '. Original profile labels do not imply measured attitudes toward AI or guaranteed task strengths. '
        'The provisional TBS reconstruction lacks historical offer data and did not outperform its held-out '
        'choice-frequency baseline. These simulations do not establish human assistance effects.')
    cached = profiles.read(source/'analysis.json')
    cached_individual = {(r['participant'],r['task'],r['condition'],r['mechanism']):r for r in cached['individual_results']}
    for row in report['individual_results']:
        person,task,condition,mechanism = (row[k] for k in ('participant','task','condition','mechanism'))
        scale = 100 if task=='TBS' else 1
        differences = row['repetition_changes_from_A']
        error = stdev(differences)/math.sqrt(len(differences)) if len(differences)>1 else None
        recorded = cached_individual[(person,task,condition,mechanism)]['monte_carlo_se']
        profiles.checked((error is None and recorded is None) or
                         (error is not None and recorded is not None and profiles.equal(error,recorded*scale)),
                         'Monte Carlo standard error differs from the pilot analysis')
        row.update(repetition_changes_from_A=differences,monte_carlo_se=error)
    return report


def number(value,task,signed=True):
    if abs(value)<1e-10:
        value=0.
    return format(value,'+,.2f' if signed else ',.2f')


def heatmap(task, columns, labels, values, details, title, height, include_library):
    import plotly.graph_objects as go
    limit = max(abs(v) for row in values for v in row) or 1
    figure = go.Figure(go.Heatmap(z=values,x=columns,y=labels,zmin=-limit,zmax=limit,zmid=0,
        colorscale='RdBu',text=[[number(v,task) for v in row] for row in values],texttemplate='%{text}',
        customdata=details,hovertemplate='%{x}<br>%{customdata}<extra></extra>',
        colorbar=dict(thickness=12,ticksuffix=' pp' if task=='TBS' else '')))
    figure.update_layout(template='plotly_white',title=dict(text=title,font=dict(size=16)),height=height,
        margin=dict(l=235 if height>600 else 180,r=85,t=75,b=150),
        font=dict(family='Arial, sans-serif',size=12),yaxis=dict(autorange='reversed'),
        xaxis=dict(tickangle=-32))
    return '<div class="chart">'+figure.to_html(full_html=False,include_plotlyjs=include_library,
                                                config={'responsive':True,'displaylogo':False})+'</div>'


def render(report):
    group_index = {(r['task'],r['profile'],r['condition'],r['mechanism']):r for r in report['group_results']}
    individual_index = {(r['participant'],r['task'],r['condition'],r['mechanism']):r for r in report['individual_results']}
    contrast_index = {(r['task'],r['profile'],r['contrast'],r['mechanism']):r for r in report['contrasts']}
    people = sorted({(r['original_profile'],r['participant']) for r in report['individual_results']},
                    key=lambda p:(profiles.PROFILES.index(p[0]),p[1]))
    figures = {'groups':[],'individuals':[],'personalisation':[]}
    repeats = report['configuration']['repeats']
    for task in ('MAB','TBS'):
        unit = 'points' if task=='MAB' else 'percentage points'
        values,details,labels = [],[],[]
        for profile in profiles.PROFILES:
            rows = [group_index[(task,profile,c,m)] for c,m in profiles.VARIANTS]
            labels.append(f"{profile} (n={rows[0]['participants']})")
            values.append([r['mean'] for r in rows])
            details.append([f"{profile}<br>Mean change: {number(r['mean'],task)} {unit}<br>"
                f"Median actor change: {number(r['median'],task)}<br>"
                f"Actor range: {number(r['minimum'],task)} to {number(r['maximum'],task)}<br>"
                f"Better / same / worse: {r['better']} / {r['same']} / {r['worse']}<br>"
                f"Mean interventions: {r['mean_interventions']:.2f}<br>"
                f"Unassisted mean: {number(r['mean_baseline'],task,False)}<br>"
                f"Assisted mean: {number(r['mean_assisted'],task,False)}" for r in rows])
        figures['groups'].append(heatmap(task,profiles.LABELS,labels,values,details,
            task+': group mean change from A ('+unit+')',460,task=='MAB'))
        values,details,labels = [],[],[]
        for profile,person in people:
            rows = [individual_index[(person,task,c,m)] for c,m in profiles.VARIANTS]
            labels.append(profile+' · '+person.removeprefix('reconstructed_'))
            values.append([r['mean_improvement_from_A'] for r in rows])
            details.append([f"{person.removeprefix('reconstructed_')} · {profile}<br>"
                f"Mean change: {number(r['mean_improvement_from_A'],task)} {unit}<br>"
                f"Changes across repetitions: {', '.join(number(v,task) for v in r['repetition_changes_from_A'])}<br>"
                f"Monte Carlo SE: {number(r['monte_carlo_se'],task,False) if r['monte_carlo_se'] is not None else 'unavailable'}<br>"
                f"Unassisted mean: {number(r['baseline'],task,False)}<br>"
                f"Assisted mean: {number(r['assisted'],task,False)}" for r in rows])
        figures['individuals'].append(heatmap(task,profiles.LABELS,labels,values,details,
            task+': individual mean change from A ('+unit+')',880,False))
        contrasts = [('E-C','current'),('F-D','current'),('F-D','recent')]
        values,details,labels = [],[],[]
        for profile in profiles.PROFILES:
            rows = [contrast_index[(task,profile,c,m)] for c,m in contrasts]
            labels.append(profile+' (n=4)');values.append([r['mean'] for r in rows])
            details.append([f"{profile}<br>Mean personalisation contrast: {number(r['mean'],task)} {unit}<br>"
                f"Better / same / worse than generic support: {r['better']} / {r['same']} / {r['worse']}<br>"
                f"Actor range: {number(r['minimum'],task)} to {number(r['maximum'],task)}" for r in rows])
        figures['personalisation'].append(heatmap(task,['E−C direct','F−D current','F−D recent'],labels,values,details,
            task+': personalisation contrast ('+unit+')',440,False))
    summary = ['<table><caption>Overall mean change from A (16 actors)</caption><thead><tr>'
               '<th>Support</th><th>MAB points</th><th>TBS percentage points</th></tr></thead><tbody>']
    for label,(condition,mechanism) in zip(profiles.LABELS,profiles.VARIANTS):
        summary.append('<tr><th scope="row">'+escape(label)+'</th>'+''.join('<td>'+number(
            group_index[(task,'all',condition,mechanism)]['mean'],task)+'</td>' for task in ('MAB','TBS'))+'</tr>')
    summary.append('</tbody></table>')
    audit = report['audit']; checks = audit['cross_mechanism_controls']+audit['no_revision_controls']
    tbs_equal = audit['tbs_personalisation_pairs']==audit['tbs_personalisation_pairs_identical']
    tbs_note = ('All audited TBS C/E and D/F pairs have identical outcome and probability trajectories. '
                'This run does not provide a behavioural personalisation contrast in TBS.' if tbs_equal else
                f"{audit['tbs_personalisation_pairs_identical']}/{audit['tbs_personalisation_pairs']} audited TBS personalisation pairs have identical trajectories.")
    style = ('body{font:16px system-ui,sans-serif;color:#243247;max-width:1600px;margin:28px auto;padding:0 24px}'
        'p{max-width:1150px;line-height:1.55}h1{font-size:28px}h2{margin-top:38px;font-size:23px}'
        '.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,720px),1fr));gap:24px}'
        '.chart,.table-scroll{overflow-x:auto}.plotly-graph-div{min-width:720px}'
        'table{border-collapse:collapse;margin:18px 0 26px;font-size:14px;font-variant-numeric:tabular-nums}'
        'caption{text-align:left;font-weight:600;font-size:17px;padding:0 0 12px}'
        'td,th{padding:10px 14px;text-align:right;border-bottom:1px solid #dbe2ea;white-space:nowrap}'
        'thead{background:#f1f4f8}th:first-child{text-align:left}.metadata{border-left:4px solid #b8c6d6;padding-left:16px}'
        'nav a{display:inline-block;margin:6px 16px 6px 0}code{font-size:12px;overflow-wrap:anywhere}'
        'details{margin-top:28px}summary{cursor:pointer;font-weight:600}.table-note{color:#506176;font-size:14px}')
    html = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>'+escape(report['title'])+'</title><style>'+style+'</style><h1>'+escape(report['title'])+'</h1>',
        f'<p class="metadata"><strong>Complete: {audit["jobs"]} jobs, {audit["comparison_sessions"]:,} comparison sessions, '
        f'{audit["calibration_sessions"]} calibration sessions.</strong><br>'
        f'{len(people)} actors, four per archetype, {repeats} matched repetitions per actor. '
        f'All {checks} matched control checks pass. The n=4 labels count actors, not repetitions.</p>',
        '<p>'+escape(report['notice'])+'</p>',
        '<p>C = task-aware direct advice; E = personalised direct advice; D = task-aware Socratic questions; '
        'F = personalised Socratic questions. Current/recent specify how the synthetic actor reconsiders. '
        'Direct advice is invariant across mechanisms. With none, D/F match A; those zero-effect variants '
        'remain in the data and controls. All heatmaps display differences, with no A column.</p>',
        '<nav><a href="#groups">Group averages</a><a href="#individuals">Individual actors</a>'
        '<a href="#personalisation">Personalisation</a><a href="#integrity">Integrity and limitations</a></nav>',
        '<div class="table-scroll">'+''.join(summary)+'</div>',
        '<section id="groups"><h2>Group-average differences from no assistance</h2>'
        '<p>Blue = gain; red = loss; zero is neutral. Each task has a symmetric scale centred on zero, '
        'shared across its profiles and conditions. MAB uses points; TBS uses percentage points of '
        'targets attained, not relative percentages. Hover for ranges, individual harm counts and absolute means.</p>'
        '<div class="charts">'+''.join(figures['groups'])+'</div></section>',
        '<section id="individuals"><h2>Individual differences from no assistance</h2>'
        '<p>Each cell averages the actor’s paired changes over all repetitions. Hover for each repetition '
        'and its Monte Carlo standard error. That error describes variation across simulated repetitions '
        'under fixed model assumptions; it is not uncertainty about human effects or fitted model parameters.</p>'
        '<div class="charts">'+''.join(figures['individuals'])+'</div></section>',
        '<section id="personalisation"><h2>Personalisation contrasts</h2>'
        '<p>Positive values mean the personalised condition scored higher than its generic counterpart: '
        'E−C for direct advice and F−D for Socratic questions. These contrasts use the same actors and '
        'matched repetitions. An improvement over A alone does not show that personalisation helped.</p>'
        '<div class="charts">'+''.join(figures['personalisation'])+'</div><p>'+tbs_note+'</p></section>',
        '<details><summary>Absolute outcome averages, including A</summary>'+profiles.absolute_tables(report)+'</details>',
        '<section id="integrity"><h2>Integrity and interpretation</h2>'
        f'<p>Verified all {audit["verified_evaluator_reports"]} evaluator report hashes and independently recomputed '
        f'{audit["recomputed_trial_summaries"]:,} trial/metric summaries, {audit["cached_individual_effects_verified"]} '
        f'individual means and Monte Carlo standard errors, and {audit["cached_aggregates_verified"]} group/overall '
        f'summaries. Controls: {audit["cross_mechanism_controls"]} A/C/E cross-mechanism and '
        f'{audit["no_revision_controls"]} no-revision checks.</p>'
        '<p>Paired means and ties use the exact recorded score/target numerators. Tiny floating-point '
        'residuals that cancel to zero are treated as ties. Corrections to cached harm counts are '
        'recorded in analysis.json; the frozen source summaries remain unchanged.</p>'
        '<p>Four deliberately selected actors per profile remain a small development sample. Repetitions '
        'are not additional participants. No mechanism is selected for favourable results; all are retained. '
        'These results use the frozen implementation recorded here and do not rewrite the earlier pilot.</p>'
        '<p>Execution versions: '+escape(json.dumps(audit['execution_versions']))+'<br>Frozen manifest: <code>'+
        audit['manifest_sha256']+'</code></p></section></html>']
    return ''.join(html)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--title',default='Final synthetic pilot results by archetype')
    parser.add_argument('--wait-seconds',type=int,default=0,help='Wait up to this many seconds for final completion')
    args=parser.parse_args();source=args.pilot_dir.resolve();output=args.output_dir.resolve()
    profiles.checked(args.wait_seconds>=0,'wait-seconds must be nonnegative')
    profiles.checked(not output.is_relative_to(source),'Keep the new report outside its frozen source pilot')
    await_completion(source,args.wait_seconds)
    report=prepare_report(source,args.title)
    if (output/'analysis.json').exists():
        profiles.checked(profiles.read(output/'analysis.json')['audit']['manifest_sha256']==report['audit']['manifest_sha256'],
                         'Output directory already belongs to another pilot')
    html=render(report)
    markdown=profiles.markdown(report).replace('# Earlier pilot: original-profile breakdown','# '+args.title,1)
    output.mkdir(parents=True,exist_ok=True)
    (output/'analysis.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    (output/'report.md').write_text(markdown)
    (output/'profile_effects.html').write_text(html)
    print(json.dumps(report['audit'],indent=2),flush=True)
    print('Final report saved: '+str(output/'profile_effects.html'),flush=True)


if __name__=='__main__':
    main()
