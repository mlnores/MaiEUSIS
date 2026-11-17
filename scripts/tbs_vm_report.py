#!/usr/bin/env python3
"""Self-contained TBS report with audited primary/secondary units kept separate."""
import argparse
import csv
import hashlib
import json
import math
from datetime import datetime
from html import escape
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

PROFILES = ('MAB-specialised', 'TBS-specialised', 'Dual-regime', 'Low-expression')
LEVELS = (.25, .5, .75)
CONDITIONS = ('C', 'E', 'D', 'F')
LABELS = ('C · Direct', 'E · Personalised direct', 'D · Socratic', 'F · Personalised Socratic')
STYLES = (('C', LABELS[0], '#0072B2', 'circle', 'solid'),
          ('E', LABELS[1], '#009E73', 'diamond', 'dash'),
          ('D', LABELS[2], '#D55E00', 'triangle-up', 'solid'),
          ('F', LABELS[3], '#CC79A7', 'square', 'dash'))
CONTRASTS = (
    ('e-c', 'Personalisation of direct support · E − C', {'E': 1, 'C': -1}),
    ('f-d', 'Personalisation of Socratic support · F − D', {'F': 1, 'D': -1}),
    ('d-c', 'Style without personalisation · D − C', {'D': 1, 'C': -1}),
    ('f-e', 'Style with personalisation · F − E', {'F': 1, 'E': -1}),
    ('interaction', 'Style × personalisation · (F − D) − (E − C)', {'F': 1, 'D': -1, 'E': -1, 'C': 1}),
)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def zero(value):
    return 0.0 if abs(value) < 1e-10 else value


def counts(values):
    return {'better': sum(v > 1e-10 for v in values), 'same': sum(abs(v) <= 1e-10 for v in values),
            'worse': sum(v < -1e-10 for v in values)}


def scale(values, step):
    return max(step, math.ceil(max(abs(v) for v in values) / step) * step)


def save_csv(path, rows):
    with Path(path).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows)


def derive(data):
    individual = {(r['participant'], r['receptiveness'], r['condition']): r for r in data['individual_results']}
    group = {(r['profile'], r['receptiveness'], r['condition']): dict(r) for r in data['groups']}
    membership = {r['participant']: r['profile'] for r in data['individual_results']}
    people = {g: sorted(p for p, profile in membership.items() if profile == g) for g in PROFILES}
    people['all'] = sorted(membership)
    for (g, rho, c), row in group.items():
        selected = [individual[p, rho, c] for p in people[g]]
        row['net_target_difference_total'] = sum(r['net_target_difference_total'] for r in selected)
        row['score_counts'] = counts([r['mean_score_delta'] for r in selected])
    paired_people, contrasts = [], []
    for key, label, weights in CONTRASTS:
        for rho in LEVELS:
            values = {}
            for p in people['all']:
                net = sum(w * individual[p, rho, c]['net_target_difference_total'] for c, w in weights.items())
                score = sum(w * individual[p, rho, c]['mean_score_delta'] for c, w in weights.items())
                prompts = sum(w * individual[p, rho, c]['mean_interventions'] for c, w in weights.items())
                value = {'participant': p, 'profile': membership[p], 'contrast': key, 'receptiveness': rho,
                         'net_target_difference_total': net, 'mean_delta_pp': 100 * net / 72,
                         'mean_score_delta': zero(score), 'mean_prompt_difference': zero(prompts)}
                values[p] = value
                paired_people.append(value)
            for g in (*PROFILES, 'all'):
                selected = [values[p] for p in people[g]]
                net = [r['net_target_difference_total'] for r in selected]
                contrasts.append({'contrast': key, 'label': label, 'profile': g, 'receptiveness': rho,
                    'participants': len(selected), 'mean_delta_pp': 100 * sum(net) / (72 * len(net)),
                    'mean_score_delta': zero(mean(r['mean_score_delta'] for r in selected)),
                    'mean_prompt_difference': zero(mean(r['mean_prompt_difference'] for r in selected)), **counts(net)})
    endpoints = []
    for g in (*PROFILES, 'all'):
        for c in CONDITIONS:
            net = [individual[p, .75, c]['net_target_difference_total'] -
                   individual[p, .25, c]['net_target_difference_total'] for p in people[g]]
            endpoints.append({'profile': g, 'condition': c, 'participants': len(net),
                              'mean_075_minus_025_pp': 100 * sum(net) / (72 * len(net)), **counts(net)})
    return individual, group, membership, people, paired_people, contrasts, endpoints


def build(root):
    import plotly
    import plotly.graph_objects as go
    from plotly.colors import sample_colorscale

    root = Path(root).resolve()
    data, audit = read(root / 'report_data.json'), read(root / 'report_audit.json')
    if not (audit['verified'] and data['complete'] and sha(root / 'report_data.json') == audit['report_data_sha256']):
        raise ValueError('Audited complete report data required')
    individual, group, membership, people, paired_people, contrasts, endpoints = derive(data)
    ordered = [p for g in PROFILES for p in people[g]]
    short = lambda p: p.rsplit('_', 1)[-1]
    title = lambda g: ('All profiles' if g == 'all' else g) + f' (n={len(people[g])})'
    primary_scale = scale([r['mean_delta_pp'] for r in data['groups']], 2.5)
    individual_scale = scale([r['mean_delta_pp'] for r in data['individual_results']], 2.5)
    contrast_scale = scale([r['mean_delta_pp'] for r in contrasts], 2.5)
    score_scale = scale([r['mean_score_delta'] for r in data['groups']], 500)
    primary_range = [-1.1 * primary_scale, 1.1 * primary_scale]
    individual_range = [-1.1 * individual_scale, 1.1 * individual_scale]
    score_range = [-1.1 * score_scale, 1.1 * score_scale]
    figures, chart_specs = [], {}
    first = True
    config = {'responsive': True, 'displaylogo': False,
              'toImageButtonOptions': {'format': 'svg', 'filename': 'tbs-pilot-figure'}}

    def figure(fig, identifier, kind, **metadata):
        nonlocal first
        figures.append({'id': identifier, 'kind': kind, **metadata})
        chart_specs[identifier] = json.loads(fig.to_json())
        html = fig.to_html(full_html=False, include_plotlyjs=first, div_id=identifier, config=config)
        first = False
        return '<div class="chart">' + html + '</div>'

    def ink(value, bound):
        rgb = sample_colorscale('RdBu', [(value + bound) / (2 * bound)])[0]
        channels = [float(x) / 255 for x in rgb[rgb.index('(') + 1:rgb.index(')')].split(',')]
        light = sum((x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4) * w
                    for x, w in zip(channels, (.2126, .7152, .0722)))
        return 'white' if 1.05 / (light + .05) >= (light + .05) / .05 else '#000000'

    def heatmap(values, x, y, details, heading, bound, unit='Δ target rate<br>(pp)', height=450, left=235):
        fig = go.Figure(go.Heatmap(z=values, x=x, y=y, zmin=-bound, zmax=bound, zmid=0,
            colorscale='RdBu', customdata=details, colorbar=dict(title=unit),
            hovertemplate='%{y}<br>%{x}<br>%{customdata}<extra></extra>'))
        for row, label in zip(values, y):
            for value, column in zip(row, x):
                fig.add_annotation(x=column, y=label, text=f'{zero(value):+,.2f}', showarrow=False,
                                   font=dict(size=13, color=ink(value, bound)))
        fig.update_layout(template='plotly_white', title=heading, height=height,
            margin=dict(l=left, r=110, t=75, b=80), font=dict(family='Arial', size=12),
            yaxis=dict(autorange='reversed'), xaxis=dict(tickangle=0))
        return fig

    def trend(lookup, heading, yrange, metric='mean_delta_pp', actor=False):
        fig = go.Figure()
        for c, label, color, symbol, dash in STYLES:
            selected = [lookup[rho, c] for rho in LEVELS]
            details = []
            for r in selected:
                if actor:
                    detail = [100 * r['mean_target_rate'], 100 * r['baseline'], r['mean_interventions'],
                              100 * r['monte_carlo_se'], ', '.join(f'{100 * x:+.2f}' for x in r['repetition_deltas']),
                              r['net_target_difference_total']]
                else:
                    count = r['score_counts'] if metric == 'mean_score_delta' else r
                    detail = [count['better'], count['same'], count['worse'], r['participants']]
                details.append(detail)
            if actor:
                hover = ('%{fullData.name}<br>Receptiveness %{x}<br>Δ target rate: %{y:+.2f} pp'
                    '<br>Mean target attainment: %{customdata[0]:.2f}%<br>Mean A: %{customdata[1]:.2f}%'
                    '<br>Prompts/run: %{customdata[2]:.2f}<br>Within-actor Monte Carlo SE: %{customdata[3]:.2f} pp'
                    '<br>Three paired repetition changes (pp): %{customdata[4]}'
                    '<br>Net extra targets across 72 blocks: %{customdata[5]}<extra></extra>')
            else:
                measure = ('Prompts/run: %{y:.2f}' if metric == 'mean_interventions' else
                           'Δ block score: %{y:+,.2f} multiplied points' if metric == 'mean_score_delta' else
                           'Δ target rate: %{y:+.2f} pp')
                hover = ('%{fullData.name}<br>Receptiveness %{x}<br>' + measure +
                         '<br>Actors better / same / worse: %{customdata[0]} / %{customdata[1]} / %{customdata[2]}'
                         '<br>Actors: %{customdata[3]}<extra></extra>')
            fig.add_trace(go.Scatter(x=list(LEVELS), y=[zero(r[metric]) for r in selected], name=label,
                mode='lines+markers', line=dict(color=color, dash=dash, width=2.5),
                marker=dict(color=color, symbol=symbol, size=9), customdata=details, hovertemplate=hover))
        axis = ('Mean prompts per 192-trial run' if metric == 'mean_interventions' else
                'Mean block-score change (multiplied points)' if metric == 'mean_score_delta' else
                'Mean target-attainment change (percentage points)')
        fig.update_layout(template='plotly_white', title=heading, height=465,
            margin=dict(l=95, r=30, t=75, b=140), font=dict(family='Arial', size=12),
            xaxis=dict(title='Receptiveness', tickvals=list(LEVELS), range=[.2, .8]),
            yaxis=dict(title=axis, range=yrange, zeroline=True, zerolinecolor='#667085', zerolinewidth=1.5),
            legend=dict(orientation='h', x=0, y=-.28, yanchor='top', font=dict(size=11)))
        return fig

    overall_lookup = {(rho, c): group['all', rho, c] for rho in LEVELS for c in CONDITIONS}
    hero = figure(trend(overall_lookup, 'All 16 actors · target-attainment change', primary_range),
                  'cluster-trend-all', 'cluster-trend', profile='all', metric='mean_delta_pp')
    group_heats = []
    for rho in LEVELS:
        selected = [[group[g, rho, c] for c in CONDITIONS] for g in PROFILES]
        details = [[f"Mean Δ: {r['mean_delta_pp']:+.2f} pp<br>Target attainment: {100*r['mean_target_rate']:.2f}%"
                    f"<br>Matched A: {100*r['baseline']:.2f}%<br>Actors better / same / worse: "
                    f"{r['better']} / {r['same']} / {r['worse']}<br>Four actors · three repetitions each" for r in row] for row in selected]
        group_heats.append(figure(heatmap([[r['mean_delta_pp'] for r in row] for row in selected], LABELS,
            [title(g) for g in PROFILES], details, f'Cluster means · receptiveness {rho:g}', primary_scale),
            'cluster-heat-r' + str(rho).replace('.', ''), 'cluster-heat', rho=rho, metric='mean_delta_pp'))
    group_lines = [figure(trend({(rho, c): group[g, rho, c] for rho in LEVELS for c in CONDITIONS}, title(g), primary_range),
        'cluster-trend-' + g.lower(), 'cluster-trend', profile=g, metric='mean_delta_pp') for g in PROFILES]

    individual_heats = []
    for rho in LEVELS:
        selected = [[individual[p, rho, c] for c in CONDITIONS] for p in ordered]
        details = [[f"{r['participant']}<br>Mean Δ: {r['mean_delta_pp']:+.2f} pp"
                    f"<br>Target attainment: {100*r['mean_target_rate']:.2f}% · A: {100*r['baseline']:.2f}%"
                    f"<br>Three repetition changes (pp): {', '.join(f'{100*v:+.2f}' for v in r['repetition_deltas'])}"
                    f"<br>Within-actor Monte Carlo SE: {100*r['monte_carlo_se']:.2f} pp"
                    f"<br>Net extra targets / 72 blocks: {r['net_target_difference_total']}"
                    f"<br>Prompts/run: {r['mean_interventions']:.2f}" for r in row] for row in selected]
        fig = heatmap([[r['mean_delta_pp'] for r in row] for row in selected], LABELS,
            [membership[p] + ' · ' + short(p) for p in ordered], details,
            f'Individual effects · receptiveness {rho:g}', individual_scale, height=910, left=275)
        for boundary in (3.5, 7.5, 11.5):
            fig.add_shape(type='line', xref='paper', x0=0, x1=1, y0=boundary, y1=boundary, line=dict(color='#667085', width=1))
        individual_heats.append(figure(fig, 'individual-heat-r' + str(rho).replace('.', ''), 'individual-heat', rho=rho))
    individual_lines = []
    for g in PROFILES:
        cards = []
        for p in people[g]:
            lookup = {(rho, c): individual[p, rho, c] for rho in LEVELS for c in CONDITIONS}
            chart = figure(trend(lookup, short(p) + ' · three paired repetitions', individual_range, actor=True),
                'individual-trend-' + short(p).lower(), 'individual-trend', participant=p, profile=g)
            cards.append('<article id="card-' + escape(p) + '" class="actor-card"><h3>' + short(p) + '</h3>'
                '<p class="small">' + escape(g) + f" · Mean A target attainment: {100*individual[p,.25,'C']['baseline']:.2f}%</p>" + chart + '</article>')
        individual_lines.append('<details class="cluster-detail"' + (' open' if g == PROFILES[0] else '') +
            '><summary>' + escape(title(g)) + ' · ' + ', '.join(short(p) for p in people[g]) +
            '</summary><div class="trends">' + ''.join(cards) + '</div></details>')
    contrast_html = []
    for key, label, _ in CONTRASTS:
        selected = [[next(r for r in contrasts if (r['contrast'], r['profile'], r['receptiveness']) == (key, g, rho))
                     for rho in LEVELS] for g in (*PROFILES, 'all')]
        details = [[f"Paired contrast: {r['mean_delta_pp']:+.2f} pp<br>Actors positive / zero / negative: "
                    f"{r['better']} / {r['same']} / {r['worse']}<br>n={r['participants']} actors"
                    f"<br>Prompt-count contrast: {r['mean_prompt_difference']:+.2f}" for r in row] for row in selected]
        contrast_html.append(figure(heatmap([[r['mean_delta_pp'] for r in row] for row in selected],
            [f'{rho:g}' for rho in LEVELS], [title(g) for g in (*PROFILES, 'all')], details, label, contrast_scale,
            unit='Paired Δ<br>(pp)', height=490), 'contrast-' + key + '-plot', 'contrast-heat', contrast=key))
    prompt_limit = math.ceil(max(r['mean_interventions'] for r in group.values()) / 5) * 5 + 5

    score_heats = []
    for rho in LEVELS:
        selected = [[group[g, rho, c] for c in CONDITIONS] for g in PROFILES]
        details = [[f"Mean Δ score: {r['mean_score_delta']:+,.2f} multiplied points<br>Mean score: {r['mean_score']:,.2f}"
                    f"<br>Matched A score: {r['baseline_score']:,.2f}<br>Primary Δ target rate: {r['mean_delta_pp']:+.2f} pp"
                    for r in row] for row in selected]
        score_heats.append(figure(heatmap([[r['mean_score_delta'] for r in row] for row in selected], LABELS,
            [title(g) for g in PROFILES], details, f'Secondary block score · receptiveness {rho:g}', score_scale,
            unit='Δ multiplied<br>score points'), 'score-heat-r' + str(rho).replace('.', ''), 'score-heat', rho=rho))
    score_lines = [figure(trend({(rho, c): group[g, rho, c] for rho in LEVELS for c in CONDITIONS},
            'Secondary score · ' + title(g), score_range, 'mean_score_delta'),
            'score-trend-' + g.lower(), 'score-trend', profile=g, metric='mean_score_delta') for g in ('all',) + PROFILES]
    prompt_chart = figure(trend(overall_lookup, 'Delivery frequency · all 16 actors', [0, prompt_limit], 'mean_interventions'),
                          'prompt-trend-all', 'prompt-trend', metric='mean_interventions')

    overall = [group['all', rho, c] for rho in LEVELS for c in CONDITIONS]
    primary_table = ['<table id="overall-table"><caption>Primary outcome · 16 actors × three repetitions × 24 blocks</caption>'
        '<thead><tr><th>Receptiveness</th><th>Condition</th><th>Target attainment</th><th>Δ vs A (pp)</th>'
        '<th>Net extra targets / 1,152 blocks</th><th>Actors better / same / worse</th><th>Prompts/run</th></tr></thead><tbody>']
    score_table = ['<table id="score-table"><caption>Secondary outcome · multiplied block-score points</caption>'
        '<thead><tr><th>Receptiveness</th><th>Condition</th><th>Mean score</th><th>Mean A score</th><th>Δ score vs A</th></tr></thead><tbody>']
    for r in overall:
        label = escape(LABELS[CONDITIONS.index(r['condition'])])
        primary_table.append(f'<tr><th>{r["receptiveness"]:g}</th><td>{label}</td><td>{100*r["mean_target_rate"]:.2f}%</td>'
            f'<td>{zero(r["mean_delta_pp"]):+.2f}</td><td>{r["net_target_difference_total"]:+d}</td>'
            f'<td>{r["better"]} / {r["same"]} / {r["worse"]}</td><td>{r["mean_interventions"]:.2f}</td></tr>')
        score_table.append(f'<tr><th>{r["receptiveness"]:g}</th><td>{label}</td><td>{r["mean_score"]:,.2f}</td>'
            f'<td>{r["baseline_score"]:,.2f}</td><td>{zero(r["mean_score_delta"]):+,.2f}</td></tr>')
    primary_table.append('</tbody></table>')
    score_table.append('</tbody></table>')
    endpoint_table = ['<table id="endpoint-table"><caption>Paired change from receptiveness 0.25 to 0.75</caption>'
        '<thead><tr><th>Profile group</th><th>Condition</th><th>Δ target rate (pp)</th><th>Actors positive / zero / negative</th></tr></thead><tbody>']
    for r in endpoints:
        endpoint_table.append('<tr><th>' + escape(title(r['profile'])) + '</th><td>' + escape(LABELS[CONDITIONS.index(r['condition'])]) +
            f'</td><td>{zero(r["mean_075_minus_025_pp"]):+.2f}</td><td>{r["better"]} / {r["same"]} / {r["worse"]}</td></tr>')
    endpoint_table.append('</tbody></table>')
    options = ''.join('<optgroup label="' + escape(g) + '">' + ''.join('<option value="' + escape(p) + '">' +
        escape(short(p) + ' · ' + g) + '</option>' for p in people[g]) + '</optgroup>' for g in PROFILES)
    high = {c: group['all', .75, c] for c in CONDITIONS}
    personalised_lower = all(group['all', rho, p]['mean_delta_pp'] < group['all', rho, g]['mean_delta_pp']
                             for rho in LEVELS for g, p in (('C', 'E'), ('D', 'F')))
    summaries = ['<li>At receptiveness 0.75, ' + '; '.join(f"{c}: <strong>{high[c]['mean_delta_pp']:+.2f} pp</strong> "
        f"({high[c]['net_target_difference_total']:+d} targets / 1,152 blocks)" for c in CONDITIONS) + '.</li>']
    if personalised_lower:
        summaries.append('<li>Personalised E/F have lower overall mean target attainment than corresponding generic C/D at all three tested values. '
                         'They also deliver fewer prompts on average. This is a descriptive result under the specified synthetic response mechanisms.</li>')
    if all(group[g, .75, c]['mean_delta_pp'] < 0 for g in PROFILES[:-1] for c in ('D', 'F')):
        summaries.append('<li>At 0.75, both Socratic conditions have positive group means only for Low-expression; '
                         'the other three profile groups have negative mean changes. Overall averages therefore conceal important differences.</li>')
    best = max(data['groups'], key=lambda r: r['mean_delta_pp'])
    worst = min(data['groups'], key=lambda r: r['mean_delta_pp'])
    summaries.append('<li>Observed cluster-mean extremes: ' + escape(best['profile']) + f" / {best['condition']} / ρ={best['receptiveness']:g}: "
        f"{best['mean_delta_pp']:+.2f} pp; " + escape(worst['profile']) + f" / {worst['condition']} / ρ={worst['receptiveness']:g}: "
        f"{worst['mean_delta_pp']:+.2f} pp. These are post-hoc descriptive extremes among four-actor groups.</li>")
    finished = datetime.fromisoformat(data['status']['updated_at_utc']).astimezone(ZoneInfo('Europe/Madrid')).strftime('%d %B %Y, %H:%M %Z')
    elapsed = data['status']['elapsed_seconds']
    duration = f'{int(elapsed//3600)} h {int(elapsed%3600//60):02d} min'
    pairs = audit['personalisation_pairs']
    ties = len(audit['exact_tie_corrections'])
    css = '''body{font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:#243247;background:#fff;max-width:1510px;margin:30px auto;padding:0 24px}
h1{letter-spacing:-.03em;line-height:1.15}h2{margin:38px 0 10px}h3{margin:16px 16px 0}p{max-width:1240px}.small{font-size:13px;color:#52657a}
nav{display:flex;flex-wrap:wrap;gap:10px 22px;margin:22px 0}a{color:#0064a3}.status,.note,.secondary-note{padding:14px 18px;border-radius:6px}
.status{background:#eef8f4;border-left:4px solid #009E73}.note{background:#f1f5fb;border-left:4px solid #0072B2}.secondary-note{background:#fff6e9;border-left:4px solid #b66b00}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:12px;margin:20px 0}.card{padding:16px;border:1px solid #dce4ed;border-radius:8px}.card strong{display:block;font-size:23px}
.chart{overflow-x:auto;border:1px solid #e0e6ee;border-radius:8px;margin:16px 0;background:#fff}.plotly-graph-div{min-width:600px}.heatmaps .plotly-graph-div{min-width:835px}.individuals .plotly-graph-div{min-width:935px}
.trends{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,625px),1fr));gap:18px}.actor-card{min-width:0;scroll-margin-top:20px}.actor-card>p{margin:5px 16px}.tables{overflow-x:auto}
table{border-collapse:collapse;margin:22px 0;font-variant-numeric:tabular-nums;font-size:14px}caption{text-align:left;font-weight:650;padding-bottom:10px}td,th{padding:9px 12px;text-align:right;border-bottom:1px solid #dbe2ea}th:first-child,td:nth-child(2){text-align:left}thead{background:#f1f4f8}
summary{cursor:pointer;font-weight:650;padding:16px 0}.cluster-detail{border-top:1px solid #dce4ed}code{font-size:12px;overflow-wrap:anywhere}footer{margin-top:32px;font-size:13px;color:#52657a}select{padding:6px;max-width:100%}
@media(max-width:700px){body{padding:0 12px;margin-top:18px}h1{font-size:27px}}'''
    controls = '''document.querySelectorAll('details').forEach(function(section){
section.addEventListener('toggle',function(){if(section.open){requestAnimationFrame(function(){
section.querySelectorAll('.plotly-graph-div').forEach(function(plot){if(plot._fullLayout){Plotly.Plots.resize(plot);}});
});}});});
document.getElementById('actor-jump').addEventListener('change',function(){
var card=document.getElementById('card-'+this.value);var group=card.closest('details');group.open=true;
requestAnimationFrame(function(){card.querySelectorAll('.plotly-graph-div').forEach(function(plot){if(plot._fullLayout){Plotly.Plots.resize(plot);}});
card.scrollIntoView({behavior:'smooth',block:'start'});});});'''
    html = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>TBS · personalisation and receptiveness</title><style>' + css + '</style></head><body>',
        '<h1>TBS: personalisation across receptiveness</h1>',
        '<p class="status"><strong>Complete · numerical checks verified.</strong> 144/144 jobs; 138,240 comparison trials replayed. '
        'Completed ' + escape(finished) + '.</p>',
        '<div class="cards"><div class="card"><strong>16 actors</strong>Four per original profile group · three repetitions</div>'
        '<div class="card"><strong>0.25 · 0.50 · 0.75</strong>Fixed true receptiveness</div>'
        '<div class="card"><strong>720 sessions</strong>Fresh A/C/E/D/F · 192 trials each</div>'
        '<div class="card"><strong>144 calibrations</strong>24 blocks × eight decisions</div></div>',
        '<nav aria-label="Report sections"><a href="#overall">Overall</a><a href="#cluster-heatmaps">Cluster heatmaps</a>'
        '<a href="#cluster-trends">Cluster trends</a><a href="#individual-heatmaps">Individual heatmaps</a>'
        '<a href="#individual-trends">Individual trends</a><a href="#contrasts">Paired contrasts</a>'
        '<a href="#secondary">Secondary score</a><a href="#delivery">Prompt volume</a><a href="#methods">Method and audit</a></nav>',
        '<p><strong>Primary outcome:</strong> target-attainment rate, targets attained / 24 blocks. Primary plots show change from matched '
        'unassisted A in <strong>percentage points (pp)</strong>. A is the zero reference. Three repetitions are averaged within each actor before group means.</p>',
        '<p><strong>Conditions:</strong> C = generic task-aware direct; E = personalised direct; D = generic task-aware Socratic; F = personalised Socratic. '
        'All four series remain separate, including coincidences.</p>',
        '<h2 id="overall">Overall target attainment</h2>',
        f'<p>Matched A target attainment: <strong>{100*overall[0]["baseline"]:.2f}%</strong> '
        '(768 targets / 1,152 blocks per level), identical across receptiveness levels.</p>',
        '<ul>' + ''.join(summaries) + '</ul>' + hero + '<div class="tables">' + ''.join(primary_table) + '</div>',
        '<p class="note"><strong>Exact ties:</strong> ' + str(ties) + ' of the 192 actor × level × assisted-condition means '
        'have zero net target difference across three repetitions but tiny nonzero floating values in the original analysis. '
        'This report calculates gain/tie/loss counts from integer target totals. The source analysis is preserved; displayed mean effects are unchanged.</p>',
        '<h2 id="cluster-heatmaps">Cluster heatmaps</h2>'
        f'<p>All three maps share a zero-centred scale of ±{primary_scale:g} pp. Blue indicates a gain; red a loss. '
        'Each original profile group contains four individually fitted actors.</p><div class="heatmaps">' + ''.join(group_heats) + '</div>',
        '<h2 id="cluster-trends">Evolution across the three tested receptiveness levels</h2>'
        '<p>All group trend panels share the overall plot’s vertical range. Straight segments connect the three tested values; '
        'intermediate values were not simulated and no linear regression or monotonic law is assumed. Click legends to hide/show conditions.</p>'
        '<div class="trends">' + ''.join(group_lines) + '</div>',
        '<h2 id="individual-heatmaps">Individual-profile heatmaps</h2>'
        f'<p>The three maps share a separate ±{individual_scale:g} pp scale. Each row averages the same actor’s three repetitions. '
        'Hover for absolute rates, paired repetition changes, Monte Carlo SE, target counts and prompts.</p>'
        '<details class="individuals" open><summary>All 16 actors, grouped by original profile</summary>' + ''.join(individual_heats) + '</details>',
        '<h2 id="individual-trends">Receptiveness trends for every individual</h2>'
        '<p>All 16 actor plots share one vertical range. Within-actor Monte Carlo SE is based on three paired repetitions; '
        'it does not quantify uncertainty about human populations or model validity.</p>'
        '<label for="actor-jump">Jump to an actor: </label><select id="actor-jump">' + options + '</select>' + ''.join(individual_lines),
        '<h2 id="contrasts">Matched personalisation, style and interaction contrasts</h2>'
        '<p>Positive E−C/F−D values favour personalisation; positive D−C/F−E values favour Socratic support under its specified processing rule. '
        'The interaction is (F−D)−(E−C). Contrasts pair the same actors and repetitions. '
        f'All five maps share ±{contrast_scale:g} pp; counts concern actors, not trials.</p><div class="heatmaps">' + ''.join(contrast_html) + '</div>',
        '<p>Full probability/trajectory/prompt records coincide in ' + str(pairs['C_E']['all_records_identical']) + '/144 C/E pairs and ' +
        str(pairs['D_F']['all_records_identical']) + '/144 D/F pairs. Choice/outcome trajectories alone coincide in ' +
        str(pairs['C_E']['trajectory_identical']) + '/144 and ' + str(pairs['D_F']['trajectory_identical']) +
        '/144 pairs respectively. Equal mean outcomes do not imply identical processing or trajectories.</p>',
        '<h2>Effect of increasing receptiveness</h2><p>Paired endpoint change is target attainment at 0.75 minus attainment at 0.25. '
        'The matched A baseline cancels. The trend plots retain non-monotonic paths.</p><div class="tables">' + ''.join(endpoint_table) + '</div>',
        '<h2 id="secondary">Secondary outcome: multiplied block score</h2>'
        '<p class="secondary-note">These plots use <strong>multiplied score points</strong>, including the conditional final-win multiplier. '
        'They are separate from target-attainment percentage points. A condition can change score and target attainment differently.</p>'
        '<div class="tables">' + ''.join(score_table) + '</div><details><summary>Secondary score heatmaps and group trends</summary>'
        '<div class="heatmaps">' + ''.join(score_heats) + '</div><div class="trends">' + ''.join(score_lines) + '</div></details>',
        '<h2 id="delivery">Prompt volume</h2><p>Mean delivered interventions per 192-trial comparison session. '
        'Fewer prompts are not automatically better; outcomes are reported separately.</p>' + prompt_chart,
        '<h2 id="methods">Method, interpretation and provenance</h2>'
        '<p>The frozen implementation uses <code>policy-0.7</code> and <code>participant-model-0.2</code>. '
        'E/F can adapt delivery using permitted public task-choice forecasts and uncertain style-specific uptake estimates. C/D do not receive those personalised estimates. '
        'True actor receptiveness is fixed and identical across actors/styles at each level; it is distinct from the assistant’s learned uptake estimate.</p>'
        '<p>Direct assistance targets the graph-supported recommended action. TBS Socratic responses reweight SAFE/RISKY using displayed task evidence and goals: '
        'immediate expected points for the relevant pre-final issue, normalised target-attainment values at the final decision, and the task’s required-gain weighting otherwise. '
        'Both styles mix their processing target with baseline choice probabilities using receptiveness. These are different processing assumptions, not a pure wording comparison or an optimal multi-step planner.</p>'
        '<p>Actor experience and assistant interaction history reset before each comparison. Calibrations and keyed choice/omission/offer/target/outcome streams are matched across levels. '
        'Extra reactance, distraction and AI-induced omission are zero; frozen actor-specific baseline omissions remain active. '
        'The original four profile labels are researcher grouping metadata, not assistant inputs. The 46 held-out evaluation actors were not assistance-tested.</p>'
        '<p><strong>Interpretation limits:</strong> the private TBS actor is a provisional seven-feature state/feedback reconstruction. Historical offers were unavailable; '
        'offer sensitivity remains zero and new offers/targets follow the current generator. Historical held-out TBS prediction limitations remain applicable. '
        'The assistant observer has 25 pressure-logistic hypotheses and can be misspecified. Offline synthetic actors process structured records, not prose meaning, and generate no helpfulness, trust or burden reports. '
        'These results describe the specified simulation; they do not establish human benefits or a general dose-response law.</p>'
        '<details><summary>Audit, execution and downloads</summary>'
        '<p>All 138,240 comparison trials were numerically replayed; 48 independent baselines were regenerated, 144 fresh A controls verified, '
        'and all 192 individual / 60 group means independently reconstructed. The VM exporter reread 144 calibrations from SQLite. '
        'Their normalised profiles and 192 evaluation/feedback pairs per job were checked locally, including 96 cross-level matches. '
        'Graph inference/SHACL and language quality were not rerun.</p>'
        '<p>The VM performed exact original-runtime checks. Local macOS replay allows 1e−12 floating tolerance; the largest observed difference was '
        f'{audit["cross_platform_floating_checks"]["max_absolute_difference"]:.2g}. All discrete choices, outcomes and target counts match exactly. '
        'Exact integer target differences determine report tie counts.</p>'
        f'<p>Execution: {data["status"]["workers"]} workers; {duration}; {data["status"]["observed_jobs_per_hour"]:.2f} committed jobs/hour. '
        f'Largest recorded per-worker peak RSS: {max(j["max_rss_bytes"] for j in data["jobs"])/1024**2:.1f} MiB. '
        'This single run does not establish the optimal worker count.</p>'
        '<p><a href="summary.md">Written summary</a> · <a href="group_results.csv">Group CSV</a> · '
        '<a href="individual_results.csv">Individual CSV</a> · <a href="paired_contrasts.csv">Contrast CSV</a> · '
        '<a href="session_results.csv">Session CSV</a> · <a href="report_audit.json">Numerical audit</a> · '
        '<a href="tie_corrections.csv">Exact-tie correction log</a> · '
        '<a href="source_analysis.json">Unmodified source analysis</a> · <a href="report_validation.json">Report checks</a></p></details>',
        '<footer>Manifest: <code>' + escape(data['manifest_sha256']) + '</code><br>Source analysis SHA-256: <code>' +
        escape(audit['analysis_sha256']) + '</code><br>Self-contained interactive Plotly figures; no external scripts or fonts. '
        'Chart camera controls export SVG. Original pilot files and earlier reports remain unchanged.</footer>',
        '<script>' + controls + '</script></body></html>']
    (root / 'receptiveness_report.html').write_text(''.join(html))
    write = lambda name, value: (root / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    write('report_contrasts.json', {'manifest_sha256': data['manifest_sha256'], 'overall': overall,
                                  'contrasts': contrasts, 'individual_contrasts': paired_people, 'endpoints': endpoints})
    write('report_charts.json', chart_specs)
    write('report_figures.json', {'manifest_sha256': data['manifest_sha256'], 'figures': figures,
        'group_scale_pp': primary_scale, 'individual_scale_pp': individual_scale, 'contrast_scale_pp': contrast_scale,
        'score_scale_points': score_scale, 'group_trend_range_pp': primary_range, 'individual_trend_range_pp': individual_range,
        'score_trend_range_points': score_range, 'prompt_range': [0, prompt_limit], 'heatmap_cells': 363,
        'trend_points': 324, 'plotly_figures': 41, 'conditions': list(CONDITIONS), 'renderer_sha256': sha(__file__),
        'plotly_version': plotly.__version__})
    save_csv(root / 'individual_results.csv', data['individual_results'])
    save_csv(root / 'group_results.csv', data['groups'])
    save_csv(root / 'paired_contrasts.csv', contrasts)
    save_csv(root / 'individual_contrasts.csv', paired_people)
    save_csv(root / 'session_results.csv', read(root / 'report_trial_summaries.json')['rows'])
    save_csv(root / 'job_runtime.csv', data['jobs'])
    save_csv(root / 'tie_corrections.csv', audit['exact_tie_corrections'])
    summary = ['# TBS pilot: observed-behaviour personalisation', '',
        f'Completed {finished}; 144/144 jobs, 16 development actors, three repetitions, three receptiveness levels.', '',
        'Primary outcome: target-attainment rate over 24 blocks. Changes are percentage points versus matched unassisted A. '
        'Repetitions are averaged within actors before group means. A attained 66.67% (768/1,152 blocks per level).', '',
        '| Receptiveness | C generic direct | E personalised direct | D generic Socratic | F personalised Socratic |',
        '| --- | ---: | ---: | ---: | ---: |']
    for rho in LEVELS:
        summary.append(f'| {rho:g} | ' + ' | '.join(f"{group['all',rho,c]['mean_delta_pp']:+.2f} pp" for c in CONDITIONS) + ' |')
    summary += ['', 'C has the largest overall mean gain at every tested level. E/F have lower overall mean target attainment '
        'than generic C/D at every tested level. At 0.75, both Socratic conditions have positive means only in Low-expression; '
        'the other three group means are negative. Group and individual heterogeneity remain visible in the report.', '',
        '| Contrast at receptiveness 0.75 | Overall mean |', '| --- | ---: |']
    for key, label, _ in CONTRASTS:
        r = next(v for v in contrasts if (v['contrast'], v['profile'], v['receptiveness']) == (key, 'all', .75))
        summary.append(f'| {label} | {r["mean_delta_pp"]:+.2f} pp |')
    summary += ['', 'Secondary multiplied-score changes at 0.75: ' + '; '.join(
        f"{c} {high[c]['mean_score_delta']:+,.2f} points" for c in CONDITIONS) + '. These are separate units from target-attainment percentage points.', '',
        f'Report arithmetic corrects {ties} floating-point near-zero actor cells to exact ties using integer target counts. '
        'The original analysis remains unchanged; displayed mean effects are unchanged.', '',
        f'Audit: 830 export checksums; 138,240 trial choices/outcomes replayed; 48 independent baselines; 144 fresh A checks; '
        f'144 calibration payloads; 96 cross-level calibration matches; 192 actor and 60 group summaries. '
        f'Execution used 64 workers and took {duration}.', '',
        'The private TBS actor is provisional and historical offers are unavailable. The assistance processing assumptions differ by style. '
        'These are conditional synthetic results, not evidence of human trust, comprehension or intervention effects. '
        'Local replay permits 1e-12 floating tolerance across Linux/macOS; all discrete choices and outcomes match. '
        'Graph inference/SHACL and language quality were not rerun.', '',
        'Interactive report: [receptiveness_report.html](receptiveness_report.html). '
        'Validation and exact-tie corrections: [report_audit.json](report_audit.json).', '',
        'Manifest: `' + data['manifest_sha256'] + '`.']
    (root / 'summary.md').write_text('\n'.join(summary) + '\n')
    if sha(root / 'source_analysis.json') != audit['analysis_sha256']:
        raise ValueError('Source analysis copy changed')
    print('Saved:', root / 'receptiveness_report.html', flush=True)
    return root / 'receptiveness_report.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    build(parser.parse_args().directory)
