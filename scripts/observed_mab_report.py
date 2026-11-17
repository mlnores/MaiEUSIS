#!/usr/bin/env python3
"""Offline cluster/individual report for the observed-personalisation MAB pilot."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

PROFILES = ('MAB-specialised', 'TBS-specialised', 'Dual-regime', 'Low-expression')
CONDITIONS = ('C', 'E', 'D', 'F')
LEVELS = (.25, .5, .75)
LABELS = ('C · Direct', 'E · Personalised direct', 'D · Socratic', 'F · Personalised Socratic')
STYLES = (
    ('C', LABELS[0], '#0072B2', 'circle', 'solid'),
    ('E', LABELS[1], '#009E73', 'diamond', 'dash'),
    ('D', LABELS[2], '#D55E00', 'triangle-up', 'solid'),
    ('F', LABELS[3], '#CC79A7', 'square', 'dash'),
)
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
    return 0. if abs(value) < 1e-9 else value


def counts(values):
    return {'better': sum(v > 1e-9 for v in values), 'same': sum(abs(v) <= 1e-9 for v in values),
            'worse': sum(v < -1e-9 for v in values)}


def ceiling(values):
    return max(100, math.ceil(max(abs(v) for v in values)/100)*100)


def payload(root):
    a = read(root/'analysis.json')
    audit = read(root/'report_audit.json')
    if not (a['complete'] and audit['verified'] and sha(root/'analysis.json') == audit['analysis_sha256']
            and a['manifest_sha256'] == audit['manifest_sha256']):
        raise ValueError('A complete, independently audited pilot is required')
    individuals = {(r['participant'], r['receptiveness'], r['condition']): r for r in a['individual_results']}
    groups = {(r['profile'], r['receptiveness'], r['condition']): r for r in a['groups']}
    membership = {r['participant']: r['profile'] for r in a['individual_results']}
    people = {g: sorted(p for p, label in membership.items() if label == g) for g in PROFILES}
    people['all'] = sorted(membership)
    if len(individuals) != 192 or any(len(people[g]) != 4 for g in PROFILES):
        raise ValueError('Wrong actor/condition grid')
    overall = []
    for rho in LEVELS:
        for c in CONDITIONS:
            rows = [individuals[p, rho, c] for p in people['all']]
            overall.append({**groups['all', rho, c], 'mean_score': mean(r['mean_score'] for r in rows),
                            'baseline': mean(r['baseline'] for r in rows),
                            'mean_interventions': mean(r['mean_interventions'] for r in rows)})
    contrasts = []
    for key, label, weights in CONTRASTS:
        for group in (*PROFILES, 'all'):
            for rho in LEVELS:
                values = [sum(w*individuals[p, rho, c]['mean_delta'] for c, w in weights.items()) for p in people[group]]
                prompts = [sum(w*individuals[p, rho, c]['mean_interventions'] for c, w in weights.items()) for p in people[group]]
                contrasts.append({'contrast': key, 'label': label, 'profile': group, 'receptiveness': rho,
                                  'participants': len(values), 'mean_delta': zero(mean(values)),
                                  'mean_prompt_difference': zero(mean(prompts)), **counts(values)})
    endpoints = []
    for group in (*PROFILES, 'all'):
        for c in CONDITIONS:
            values = [individuals[p, .75, c]['mean_delta']-individuals[p, .25, c]['mean_delta'] for p in people[group]]
            endpoints.append({'profile': group, 'condition': c, 'participants': len(values),
                              'mean_075_minus_025': zero(mean(values)), **counts(values)})
    return a, audit, individuals, groups, membership, people, overall, contrasts, endpoints


def build(root):
    import plotly
    import plotly.graph_objects as go
    from plotly.colors import sample_colorscale
    root = Path(root).resolve()
    a, audit, individual, group, membership, people, overall, contrasts, endpoints = payload(root)
    group_scale = ceiling([r['mean_delta'] for r in a['groups']])
    contrast_scale = ceiling([r['mean_delta'] for r in contrasts])
    individual_scale = ceiling([r['mean_delta'] for r in a['individual_results']])
    group_range = [-group_scale*1.1, group_scale*1.1]
    individual_range = [-individual_scale*1.1, individual_scale*1.1]
    config = {'responsive': True, 'displaylogo': False, 'toImageButtonOptions': {'format': 'svg'}}
    figures = []; first = True
    title = lambda g: ('All profiles' if g == 'all' else g)+f' (n={len(people[g])})'
    short = lambda p: p.rsplit('_', 1)[-1]

    def figure(fig, identifier, kind, **metadata):
        nonlocal first
        figures.append({'id': identifier, 'kind': kind, **metadata})
        html = fig.to_html(full_html=False, include_plotlyjs=first, div_id=identifier, config=config)
        first = False
        return '<div class="chart">'+html+'</div>'

    def ink(value, scale):
        rgb = sample_colorscale('RdBu', [(value+scale)/(2*scale)])[0]
        channels = [float(x)/255 for x in rgb[rgb.index('(')+1:rgb.index(')')].split(',')]
        light = sum((x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4)*w
                    for x, w in zip(channels, (.2126, .7152, .0722)))
        return 'white' if 1.05/(light+.05) >= (light+.05)/.05 else '#000000'

    def heatmap(values, x, y, detail, name, scale, height=440, left=235, colour_title='Δ points<br>versus A'):
        fig = go.Figure(go.Heatmap(z=values, x=x, y=y, zmin=-scale, zmax=scale, zmid=0, colorscale='RdBu',
                                 customdata=detail, colorbar=dict(title=colour_title),
                                 hovertemplate='%{y}<br>%{x}<br>%{customdata}<extra></extra>'))
        for row, label in zip(values, y):
            for value, column in zip(row, x):
                fig.add_annotation(x=column, y=label, text=f'{value:+,.2f}', showarrow=False,
                                   font=dict(size=13, color=ink(value, scale)))
        fig.update_layout(template='plotly_white', title=name, height=height,
                          margin=dict(l=left, r=95, t=65, b=70), font=dict(family='Arial', size=12),
                          yaxis=dict(autorange='reversed'), xaxis=dict(tickangle=0))
        return fig

    def trend(rows, name, yrange, metric='mean_delta', individual_plot=False):
        fig = go.Figure()
        for c, label, color, symbol, dash in STYLES:
            selected = [rows[rho, c] for rho in LEVELS]
            if individual_plot:
                detail = [[r['mean_score'], r['baseline'], r['mean_interventions'], r['monte_carlo_se'],
                           ', '.join(f'{x:+g}' for x in r['repetition_deltas'])] for r in selected]
                hover = ('%{fullData.name}<br>Receptiveness %{x}<br>Change from A: %{y:+,.2f} points'
                         '<br>Mean score: %{customdata[0]:,.2f}<br>Mean A: %{customdata[1]:,.2f}'
                         '<br>Prompts/run: %{customdata[2]:.2f}<br>Within-actor Monte Carlo SE: %{customdata[3]:,.2f}'
                         '<br>Three repetition changes: %{customdata[4]}<extra></extra>')
            else:
                detail = [[r['better'], r['same'], r['worse'], r['participants']] for r in selected]
                hover = ('%{fullData.name}<br>Receptiveness %{x}<br>'+('Prompts/run: %{y:.2f}' if metric != 'mean_delta'
                         else 'Mean change from A: %{y:+,.2f} points')+
                         '<br>Actors better / same / worse than A: %{customdata[0]} / %{customdata[1]} / %{customdata[2]}'
                         '<br>Actors: %{customdata[3]}<extra></extra>')
            fig.add_trace(go.Scatter(x=LEVELS, y=[zero(r[metric]) for r in selected], name=label, mode='lines+markers',
                                    line=dict(color=color, dash=dash, width=2.5),
                                    marker=dict(color=color, symbol=symbol, size=9), customdata=detail,
                                    hovertemplate=hover))
        fig.update_layout(template='plotly_white', title=name, height=455,
                          margin=dict(l=85, r=25, t=65, b=135), font=dict(family='Arial', size=12),
                          xaxis=dict(title='Receptiveness', tickvals=LEVELS, range=[.2, .8]),
                          yaxis=dict(title='Mean change from A (points)' if metric == 'mean_delta' else 'Mean prompts per run',
                                     range=yrange, zeroline=True, zerolinecolor='#667085', zerolinewidth=1.5),
                          legend=dict(orientation='h', x=0, y=-.28, yanchor='top', font=dict(size=11)))
        return fig

    group_heats = []
    for rho in LEVELS:
        selected = [[group[g, rho, c] for c in CONDITIONS] for g in PROFILES]
        values = [[r['mean_delta'] for r in row] for row in selected]
        details = [[f"Mean Δ from A: {r['mean_delta']:+,.2f} points<br>Actors better / same / worse: "
                    f"{r['better']} / {r['same']} / {r['worse']}<br>n=4 actors · three repetitions each"
                    for r in row] for row in selected]
        group_heats.append(figure(heatmap(values, LABELS, [title(g) for g in PROFILES], details,
                                         f'Cluster means · receptiveness {rho:g}', group_scale),
                                   'cluster-heat-r'+str(rho).replace('.', ''), 'cluster-heat', rho=rho))

    group_lines = []
    for g in ('all',)+PROFILES:
        rows = {(rho, c): group[g, rho, c] for rho in LEVELS for c in CONDITIONS}
        html = figure(trend(rows, title(g), group_range), 'cluster-trend-'+g.lower(), 'cluster-trend', profile=g)
        group_lines.append(('<div class="overall">' if g == 'all' else '<div>')+html+'</div>')

    ordered = [p for g in PROFILES for p in people[g]]
    individual_heats = []
    for rho in LEVELS:
        values = [[individual[p, rho, c]['mean_delta'] for c in CONDITIONS] for p in ordered]
        details = [[f"{p}<br>Mean Δ from A: {r['mean_delta']:+,.2f}<br>Mean score: {r['mean_score']:,.2f}"
                    f"<br>Mean A score: {r['baseline']:,.2f}<br>Within-actor Monte Carlo SE: {r['monte_carlo_se']:,.2f}"
                    f"<br>Three repetition changes: {', '.join(f'{v:+g}' for v in r['repetition_deltas'])}"
                    f"<br>Mean prompts/run: {r['mean_interventions']:.2f}"
                    for r in [individual[p, rho, c] for c in CONDITIONS]] for p in ordered]
        fig = heatmap(values, LABELS, [membership[p]+' · '+short(p) for p in ordered], details,
                      f'Individual effects · receptiveness {rho:g}', individual_scale, height=900, left=275)
        for boundary in (3.5, 7.5, 11.5):
            fig.add_shape(type='line', xref='paper', x0=0, x1=1, y0=boundary, y1=boundary,
                          line=dict(color='#667085', width=1))
        individual_heats.append(figure(fig, 'individual-heat-r'+str(rho).replace('.', ''), 'individual-heat', rho=rho))

    individual_lines = []
    for g in PROFILES:
        cards = []
        for p in people[g]:
            rows = {(rho, c): individual[p, rho, c] for rho in LEVELS for c in CONDITIONS}
            chart = figure(trend(rows, short(p)+' · three matched repetitions', individual_range, individual_plot=True),
                           'individual-trend-'+short(p).lower(), 'individual-trend', participant=p, profile=g)
            cards.append('<article id="card-'+escape(p)+'" class="actor-card"><h3>'+escape(short(p))+
                         '</h3><p class="small">'+escape(g)+' · Mean A: '+
                         f"{individual[p,.25,'C']['baseline']:,.2f} points</p>"+chart+'</article>')
        individual_lines.append('<details class="cluster-detail"'+(' open' if g == PROFILES[0] else '')+
                                '><summary>'+escape(title(g))+' · '+', '.join(short(p) for p in people[g])+
                                '</summary><div class="trends">'+''.join(cards)+'</div></details>')

    contrast_html = []
    for key, label, weights in CONTRASTS:
        selected = [[next(r for r in contrasts if r['contrast'] == key and r['profile'] == g and r['receptiveness'] == rho)
                     for rho in LEVELS] for g in PROFILES+('all',)]
        values = [[r['mean_delta'] for r in row] for row in selected]
        details = [[f"Paired contrast: {r['mean_delta']:+,.2f} points<br>Actors positive / zero / negative: "
                    f"{r['better']} / {r['same']} / {r['worse']}<br>n={r['participants']} actors"
                    f"<br>Mean prompt-count contrast: {r['mean_prompt_difference']:+.2f}"
                    for r in row] for row in selected]
        contrast_html.append(figure(heatmap(values, [f'{rho:g}' for rho in LEVELS],
                                           [title(g) for g in PROFILES+('all',)], details, label,
                                           contrast_scale, height=480, colour_title='Paired Δ<br>points'),
                                    'contrast-'+key+'-plot', 'contrast-heat', contrast=key))

    prompt_rows = {(r['receptiveness'], r['condition']): r for r in overall}
    prompt_limit = math.ceil(max(r['mean_interventions'] for r in overall)/5)*5+5
    prompts = figure(trend(prompt_rows, 'Delivery frequency · all 16 actors', [0, prompt_limit], metric='mean_interventions'),
                     'prompt-trend-all', 'prompt-trend')

    overall_table = ['<table id="overall-table"><caption>Overall averages · n=16 actors · three repetitions each</caption>'
                     '<thead><tr><th>Receptiveness</th><th>Condition</th><th>Mean score</th><th>Δ from A</th>'
                     '<th>Actors better / same / worse</th><th>Prompts/run</th></tr></thead><tbody>']
    for r in overall:
        label = LABELS[CONDITIONS.index(r['condition'])]
        overall_table.append(f'<tr><th>{r["receptiveness"]:g}</th><td>{escape(label)}</td><td>{r["mean_score"]:,.2f}</td>'
                             f'<td>{r["mean_delta"]:+,.2f}</td><td>{r["better"]} / {r["same"]} / {r["worse"]}</td>'
                             f'<td>{r["mean_interventions"]:.2f}</td></tr>')
    overall_table.append('</tbody></table>')
    endpoint_table = ['<table id="endpoint-table"><caption>Change from receptiveness 0.25 to 0.75</caption>'
                      '<thead><tr><th>Cluster</th><th>Condition</th><th>Paired score change</th><th>Actors positive / zero / negative</th></tr></thead><tbody>']
    for r in endpoints:
        endpoint_table.append('<tr><th>'+escape(title(r['profile']))+'</th><td>'+escape(LABELS[CONDITIONS.index(r['condition'])])+
                              f'</td><td>{r["mean_075_minus_025"]:+,.2f}</td><td>{r["better"]} / {r["same"]} / {r["worse"]}</td></tr>')
    endpoint_table.append('</tbody></table>')
    options = ''.join('<optgroup label="'+escape(g)+'">'+''.join('<option value="'+escape(p)+'">'+
                      escape(short(p)+' · '+g)+'</option>' for p in people[g])+'</optgroup>' for g in PROFILES)
    baseline = overall[0]['baseline']
    personal = [r for r in contrasts if r['contrast'] in ('e-c', 'f-d') and r['profile'] != 'all']
    best = max(personal, key=lambda r: r['mean_delta']); worst = min(personal, key=lambda r: r['mean_delta'])
    generic_equal = audit['prior_generic_comparison']
    status = read(root/'status.json')
    finished = datetime.fromisoformat(status['updated_at_utc']).astimezone(ZoneInfo('Europe/Madrid')).strftime('%d %B %Y, %H:%M %Z')
    pairs = audit['identical_personalisation_pairs']
    summary = [
        '<li>All four assisted conditions have positive overall mean changes from A at each tested receptiveness; gains are not universal across actors or clusters.</li>',
        '<li>In these observed results, personalised E/F deliver fewer prompts on average, but have lower overall mean scores than their corresponding generic C/D at all three values.</li>',
        '<li>The largest observed cluster-level personalisation gain is '+escape(best['profile'])+
        f' at {best["receptiveness"]:g}, {escape(best["contrast"].upper())}: {best["mean_delta"]:+,.2f} points; the largest loss is '+
        escape(worst['profile'])+f' at {worst["receptiveness"]:g}, {escape(worst["contrast"].upper())}: {worst["mean_delta"]:+,.2f} points. These are post-hoc descriptive extremes.</li>',
    ]
    # Never silently reuse this narrative if future input results reverse it.
    if not all(r['mean_delta'] > 0 for r in overall):
        raise ValueError('Overall-positive narrative no longer matches the data')
    for rho in LEVELS:
        for generic, personal_c in [('C', 'E'), ('D', 'F')]:
            left = next(r for r in overall if r['receptiveness'] == rho and r['condition'] == generic)
            right = next(r for r in overall if r['receptiveness'] == rho and r['condition'] == personal_c)
            if not (right['mean_score'] < left['mean_score'] and right['mean_interventions'] < left['mean_interventions']):
                raise ValueError('Personalisation narrative no longer matches the data')

    css = '''body{font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:#243247;background:#fff;
max-width:1510px;margin:30px auto;padding:0 24px}h1{letter-spacing:-.03em;line-height:1.15}h2{margin:38px 0 10px}
h3{margin:16px 16px 0}p{max-width:1220px}.small{font-size:13px;color:#52657a}.actor-card>p{margin:5px 16px}
nav{display:flex;flex-wrap:wrap;gap:10px 22px;margin:22px 0}a{color:#0064a3}.status,.note{padding:14px 18px;border-radius:6px}
.status{background:#eef8f4;border-left:4px solid #009E73}.note{background:#f1f5fb;border-left:4px solid #0072B2}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:20px 0}
.card{padding:16px;border:1px solid #dce4ed;border-radius:8px}.card strong{display:block;font-size:23px}
.chart{overflow-x:auto;border:1px solid #e0e6ee;border-radius:8px;margin:16px 0;background:#fff}
.plotly-graph-div{min-width:590px}.heatmaps .plotly-graph-div{min-width:820px}.individuals .plotly-graph-div{min-width:920px}
.trends{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,625px),1fr));gap:18px}.overall{grid-column:1/-1}
.actor-card{min-width:0;scroll-margin-top:20px}.tables{overflow-x:auto}
table{border-collapse:collapse;margin:22px 0;font-variant-numeric:tabular-nums;font-size:14px}
caption{text-align:left;font-weight:650;padding-bottom:10px}td,th{padding:9px 12px;text-align:right;border-bottom:1px solid #dbe2ea}
th:first-child,td:nth-child(2){text-align:left}thead{background:#f1f4f8}summary{cursor:pointer;font-weight:650;padding:16px 0}
.cluster-detail{border-top:1px solid #dce4ed}code{font-size:12px;overflow-wrap:anywhere}select{font:inherit;padding:8px;max-width:100%}
footer{margin-top:32px;font-size:13px;color:#52657a}@media(max-width:700px){body{padding:0 12px;margin-top:18px}h1{font-size:27px}}
'''
    script = '''document.querySelectorAll('details').forEach(function(section){
section.addEventListener('toggle',function(){if(section.open){requestAnimationFrame(function(){
section.querySelectorAll('.plotly-graph-div').forEach(function(plot){if(plot._fullLayout){Plotly.Plots.resize(plot);}});
});}});});
document.getElementById('actor-jump').addEventListener('change',function(){
var card=document.getElementById('card-'+this.value);var group=card.closest('details');group.open=true;
requestAnimationFrame(function(){card.querySelectorAll('.plotly-graph-div').forEach(function(plot){if(plot._fullLayout){Plotly.Plots.resize(plot);}});
card.scrollIntoView({behavior:'smooth',block:'start'});});});
'''
    html = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>MAB · observed personalisation and receptiveness</title><style>'+css+'</style></head><body>',
        '<h1>MAB: personalisation across receptiveness</h1>',
        '<p class="status"><strong>Complete and independently audited.</strong> 144/144 jobs; 144 fresh baseline checks, '
        '96 cross-level calibration checks and 144 historical baseline checks passed. Completed '+escape(finished)+'.</p>',
        '<div class="cards"><div class="card"><strong>0.25 · 0.5 · 0.75</strong>Fixed true receptiveness</div>'
        '<div class="card"><strong>16 actors</strong>Four per original cluster · three repetitions</div>'
        '<div class="card"><strong>720 sessions</strong>Fresh A/C/E/D/F · 200 trials each</div>'
        '<div class="card"><strong>144 calibrations</strong>Full MAB protocol · MAB only</div></div>',
        '<nav aria-label="Report sections"><a href="#cluster-heatmaps">Cluster heatmaps</a><a href="#cluster-trends">Cluster trends</a>'
        '<a href="#individual-heatmaps">Individual heatmaps</a><a href="#individual-trends">Individual trends</a>'
        '<a href="#contrasts">Paired contrasts</a><a href="#delivery">Prompt volume</a><a href="#methods">Method and audit</a></nav>',
        '<p><strong>Outcome:</strong> every score plot shows change from matched unassisted A in MAB points. '
        'A is the zero reference and is not plotted as an extra condition. Three repetitions are averaged within each actor before cluster means.</p>',
        '<p><strong>Conditions:</strong> C = task-aware direct; E = personalised direct; D = task-aware Socratic; F = personalised Socratic. '
        'Colours and line/marker styles are consistent throughout. All four series remain separate, including any coincidences.</p>',
        '<p class="note"><strong>Personalisation now changes behaviour:</strong> full probability/trajectory/prompt records coincide in '
        f'{pairs["C_E"]}/144 C/E pairs and {pairs["D_F"]}/144 D/F pairs; the remaining pairs differ in one or more of those records. '
        'The preceding report’s combined C/E and D/F curves are not used here.</p>',
        '<h2>Overall outcomes</h2><div class="tables">'+''.join(overall_table)+'</div>',
        f'<p>Mean A score: <strong>{baseline:,.2f} points</strong>, identical across receptiveness levels.</p><ul>'+''.join(summary)+'</ul>',
        '<h2 id="cluster-heatmaps">Cluster heatmaps</h2><p>One heatmap per receptiveness value. '
        f'All share a zero-centred scale of ±{group_scale:,.0f} points: blue indicates a gain and red a loss. '
        'Clusters are the original fixed archetypes; each contains four individually fitted actors.</p>',
        '<div class="heatmaps">'+''.join(group_heats)+'</div>',
        '<h2 id="cluster-trends">Linear evolution with receptiveness: overall and clusters</h2>'
        '<p>Straight segments connect the three tested values; intermediate values were not simulated and no linear regression or monotonic effect is assumed. '
        'All five score panels use the same vertical range. Click legend entries to hide/show conditions; double-click isolates one.</p>',
        '<div class="trends">'+''.join(group_lines)+'</div>',
        '<h2 id="individual-heatmaps">Individual-profile heatmaps</h2>'
        f'<p>Each row is one reconstructed individual, averaged over three repetitions. These maps share a separate zero-centred scale of ±{individual_scale:,.0f} points '
        'to retain individual extremes. Hover for raw mean scores, repetition changes, prompts and Monte Carlo SE.</p>',
        '<details class="individuals" open><summary>Show all 16 profiles at each receptiveness value</summary>'+
        ''.join(individual_heats)+'</details>',
        '<h2 id="individual-trends">Linear evolution for every individual profile</h2>'
        '<p>All 16 profiles have their own four-condition line plot, grouped by original cluster. Individual plots share one vertical range. '
        'Hover points to inspect the three paired changes and their within-actor Monte Carlo SE; this is not uncertainty about human populations or model validity.</p>',
        '<label for="actor-jump">Jump to a profile: </label><select id="actor-jump">'+options+'</select>'+
        ''.join(individual_lines),
        '<h2 id="contrasts">Matched personalisation, style and interaction contrasts</h2>'
        '<p>These comparisons use the same actors, repetitions and receptiveness. Positive E−C/F−D values favour personalisation; '
        'positive D−C/F−E values favour Socratic support. The interaction is the difference between the two personalisation effects. '
        f'All five maps share ±{contrast_scale:,.0f} points. Counts concern actors, not trials.</p>',
        '<div class="heatmaps">'+''.join(contrast_html)+'</div>',
        '<h2>Effect of increasing receptiveness</h2><p>Paired endpoint change is score at 0.75 minus score at 0.25. '
        'The matched A score cancels. Non-monotonic paths remain visible in the line plots above.</p><div class="tables">'+''.join(endpoint_table)+'</div>',
        '<h2 id="delivery">Prompt volume</h2><p>Counts are per 200-trial run. Fewer prompts are not automatically better; reward effects are reported separately.</p>'+prompts,
        '<h2 id="methods">Method, interpretation and provenance</h2>',
        '<p>This is the completed <code>policy-0.7</code> / <code>participant-model-0.2</code> pilot. E/F use task-choice forecasts and learned style-specific uptake '
        'to adapt delivery. All conditions retain the shared public ranking and performance gate. The actor’s true receptiveness on the horizontal axis stays fixed; '
        'it is distinct from the assistant’s uncertain learned estimate.</p>',
        '<p>Actors begin conditions with reset experience, and assistant interaction histories reset. Calibration and random streams are matched across levels; '
        'condition/session identifiers and receptiveness do not enter those streams. Baseline omissions remain active; extra reactance, distraction and omissions are zero. '
        'No none/recent processing factor is present. Every condition and calibration was run fresh; no old assisted result contributes to these averages.</p>',
        '<p>The four clusters retain the colleague’s original assignments. n=4 means four actors, each with three repetitions, not twelve people. '
        'The other 46 evaluation profiles were not assistance-tested. Archetypes are grouping metadata, not assistant inputs.</p>',
        '<p><strong>Scope:</strong> current synthetic actors respond to structured singleton/pair guidance, not the meaning of prose. They generate no helpfulness, '
        'disagreement or burden reports. Uptake and task models may be misspecified; this study does not measure human trust, comprehension, satisfaction or '
        'the full human effect of Socratic dialogue. Three fixed response levels do not establish a general dose-response law.</p>',
        '<details><summary>Independent numerical audit and downloads</summary><p>All 144,000 raw comparison choices, action probabilities, keyed outcomes and '
        'task transitions were replayed. Every active response mixture, 192 individual summaries and 60 group means were checked. '
        'All 144 calibration profiles/feedback signatures were reread from SQLite, including 96 cross-level matches. '
        f'The prior generic C/D control matches in {generic_equal["identical"]}/{generic_equal["checked"]} cases; old data are a verification reference only.</p>'
        '<p><a href="analysis.json">Frozen analysis</a> · <a href="report_audit.json">Numerical audit</a> · '
        '<a href="report_trial_summaries.json">Trial-derived session summaries</a> · <a href="report_contrasts.json">Contrasts and overall data</a> · '
        '<a href="report_validation.json">Rendered-report checks</a></p>'
        '<p>The audit does not rerun every graph/SHACL calculation or evaluate language quality. All original source analyses and previous reports remain unchanged.</p></details>',
        '<footer>Manifest: <code>'+escape(a['manifest_sha256'])+'</code><br>Frozen analysis SHA-256: <code>'+
        escape(audit['analysis_sha256'])+'</code><br>Self-contained interactive Plotly figures; no external scripts/fonts required. Use chart controls to export SVG.</footer>',
        '<script>'+script+'</script></body></html>',
    ]
    output = root/'receptiveness_report.html'
    output.write_text(''.join(html))
    (root/'report_contrasts.json').write_text(json.dumps({'manifest_sha256': a['manifest_sha256'],
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'overall': overall, 'contrasts': contrasts,
        'endpoints': endpoints}, indent=2, allow_nan=False)+'\n')
    (root/'report_figures.json').write_text(json.dumps({'manifest_sha256': a['manifest_sha256'], 'figures': figures,
        'group_scale': group_scale, 'individual_scale': individual_scale, 'contrast_scale': contrast_scale,
        'group_trend_range': group_range, 'individual_trend_range': individual_range,
        'prompt_range': [0, prompt_limit], 'heatmap_cells': 315, 'trend_points': 264,
        'conditions': list(CONDITIONS), 'renderer_sha256': sha(__file__), 'plotly_version': plotly.__version__}, indent=2)+'\n')
    if sha(root/'analysis.json') != audit['analysis_sha256']:
        raise ValueError('Frozen analysis was modified')
    print('Saved:', output, flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    build(parser.parse_args().directory)
