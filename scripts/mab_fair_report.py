#!/usr/bin/env python3
"""Render the audited fresh MAB sweep as a self-contained interactive report."""
import argparse
import hashlib
import json
import math
from datetime import datetime,timezone
from html import escape
from pathlib import Path
from statistics import mean

PROFILES=('MAB-specialised','TBS-specialised','Dual-regime','Low-expression')
CONDITIONS=('C','E','D','F')
LEVELS=(.25,.5,.75)
LABELS=('C · Direct','E · Personalised direct','D · Socratic','F · Personalised Socratic')
STYLES=(('C','C/E · Direct','#0072B2','circle'),('D','D/F · Socratic','#D55E00','diamond'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    root=parser.parse_args().directory.resolve()
    a=json.loads((root/'analysis.json').read_text());audit=json.loads((root/'report_audit.json').read_text())
    if not (a['complete'] and audit['verified'] and audit['analysis_sha256']==sha(root/'analysis.json') and
            audit['manifest_sha256']==a['manifest_sha256']):raise ValueError('Complete, independently audited results are required')
    if audit['identical_personalisation_pairs']!={'C_E':144,'D_F':144}:
        raise ValueError('Combined trend curves require verified identity of every C/E and D/F pair')
    import plotly.graph_objects as go
    from plotly.colors import sample_colorscale
    groups={(r['profile'],r['receptiveness'],r['condition']):r for r in a['groups']}
    individuals={(r['participant'],r['receptiveness'],r['condition']):r for r in a['individual_results']}
    profiles={r['participant']:r['profile'] for r in a['individual_results']}
    people={g:sorted(p for p,label in profiles.items() if label==g) for g in PROFILES}
    people['all']=sorted(profiles)
    title=lambda p:('All profiles' if p=='all' else p)+f' (n={len(people[p])})'
    limit=math.ceil(max(abs(r['mean_delta']) for r in a['groups'])/100)*100 or 100
    individual_limit=math.ceil(max(abs(r['mean_delta']) for r in a['individual_results'])/100)*100 or 100
    plot_config={'responsive':True,'displaylogo':False,'toImageButtonOptions':{'format':'svg'}}
    first=True;figures=[]
    def cell_ink(value,scale):
        rgb=sample_colorscale('RdBu',[(value+scale)/(2*scale)])[0]
        channels=[float(x)/255 for x in rgb[rgb.index('(')+1:rgb.index(')')].split(',')]
        linear=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in channels]
        light=sum(x*w for x,w in zip(linear,(.2126,.7152,.0722)))
        dark_channels=[0.,0.,0.]
        dark=sum((x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4)*w
                 for x,w in zip(dark_channels,(.2126,.7152,.0722)))
        return 'white' if 1.05/(light+.05)>=(light+.05)/(dark+.05) else '#000000'
    def html(fig,identifier):
        nonlocal first
        figures.append(identifier)
        value=fig.to_html(full_html=False,include_plotlyjs=first,div_id=identifier,config=plot_config)
        first=False
        return '<div class="chart">'+value+'</div>'
    def heatmap(values,x,y,details,name,scale,height=430,left=220,color_title='Change<br>from A'):
        fig=go.Figure(go.Heatmap(z=values,x=x,y=y,zmin=-scale,zmax=scale,zmid=0,colorscale='RdBu',
            text=[[f'{v:+,.2f}' for v in row] for row in values],customdata=details,
            colorbar=dict(title=color_title),hovertemplate='%{y}<br>%{x}<br>%{customdata}<extra></extra>'))
        for row,label in zip(values,y):
            for v,column in zip(row,x):
                fig.add_annotation(x=column,y=label,text=f'{v:+,.2f}',showarrow=False,
                    font=dict(color=cell_ink(v,scale),size=13))
        fig.update_layout(template='plotly_white',title=name,height=height,margin=dict(l=left,r=95,t=60,b=65),
            yaxis=dict(autorange='reversed'),font=dict(family='Arial',size=12),xaxis=dict(tickangle=0))
        return fig

    group_html=[]
    for rho in LEVELS:
        selected=[[groups[p,rho,c] for c in CONDITIONS] for p in PROFILES]
        values=[[r['mean_delta'] for r in row] for row in selected]
        detail=[[f"Mean change: {r['mean_delta']:+,.2f} points<br>Better / same / worse than A: "
                  f"{r['better']} / {r['same']} / {r['worse']}<br>{r['participants']} actors · {r['repetitions']} repetitions per actor"
                 for r in row] for row in selected]
        fig=heatmap(values,LABELS,[title(p) for p in PROFILES],detail,f'Receptiveness {rho:g}',limit)
        group_html.append(html(fig,'group-r'+str(rho).replace('.','')))

    curves=[]
    for profile in ('all',)+PROFILES:
        fig=go.Figure()
        for c,label,color,marker in STYLES:
            selected=[groups[profile,rho,c] for rho in LEVELS]
            fig.add_trace(go.Scatter(x=LEVELS,y=[r['mean_delta'] for r in selected],name=label,mode='lines+markers',
                line=dict(color=color,width=3),marker=dict(color=color,symbol=marker,size=9),
                customdata=[[r['better'],r['same'],r['worse'],r['participants']] for r in selected],
                hovertemplate='%{fullData.name}<br>Receptiveness %{x}<br>Change from A: %{y:+,.2f} points'
                 '<br>Better / same / worse: %{customdata[0]} / %{customdata[1]} / %{customdata[2]}'
                 '<br>Actors: %{customdata[3]}<extra></extra>'))
        fig.update_layout(template='plotly_white',title=title(profile),height=430,
            margin=dict(l=85,r=30,t=60,b=95),font=dict(family='Arial',size=12),
            xaxis=dict(title='Receptiveness',tickvals=LEVELS,range=[.2,.8]),
            yaxis=dict(title='Mean change from A (points)',range=[-limit*1.1,limit*1.1],
                       zeroline=True,zerolinewidth=1.5,zerolinecolor='#667085'),
            legend=dict(orientation='h',x=0,y=-.25,yanchor='top'))
        curves.append(('<div class="overall">' if profile=='all' else '<div>')+
                      html(fig,'trend-'+profile.lower())+'</div>')

    gaps=[];gap_values=[];gap_detail=[]
    for profile in PROFILES+('all',):
        row=[];detail=[]
        for rho in LEVELS:
            values=[individuals[p,rho,'D']['mean_delta']-individuals[p,rho,'C']['mean_delta'] for p in people[profile]]
            record={'profile':profile,'receptiveness':rho,'participants':len(values),'socratic_minus_direct':mean(values),
                    'socratic_better':sum(v>1e-9 for v in values),'same':sum(abs(v)<=1e-9 for v in values),
                    'socratic_worse':sum(v< -1e-9 for v in values)}
            gaps.append(record);row.append(record['socratic_minus_direct'])
            detail.append(f"Socratic − direct: {mean(values):+,.2f} points<br>Actors with Socratic higher / same / lower: "
                          f"{record['socratic_better']} / {record['same']} / {record['socratic_worse']}")
        gap_values.append(row);gap_detail.append(detail)
    gap=heatmap(gap_values,[str(rho) for rho in LEVELS],[title(p) for p in PROFILES+('all',)],gap_detail,
                'Paired Socratic − direct difference',limit,height=480,color_title='Socratic −<br>direct')
    gap_html=html(gap,'style-gap')

    individual_html=[];ordered=[p for profile in PROFILES for p in people[profile]]
    for rho in LEVELS:
        values=[[individuals[p,rho,c]['mean_delta'] for c in CONDITIONS] for p in ordered]
        detail=[[f"{p}<br>Mean change: {r['mean_delta']:+,.2f} points<br>Mean score: {r['mean_score']:,.2f}"
                   f"<br>Mean A score: {r['baseline']:,.2f}<br>Three repetition changes: {', '.join(f'{v:+g}' for v in r['repetition_deltas'])}"
                   f"<br>Within-actor Monte Carlo SE: {r['monte_carlo_se']:,.2f} points"
                for r in [individuals[p,rho,c] for c in CONDITIONS]] for p in ordered]
        labels=[profiles[p]+' · '+p.rsplit('_',1)[-1] for p in ordered]
        fig=heatmap(values,LABELS,labels,detail,f'Individual effects · receptiveness {rho:g}',individual_limit,height=790,left=265)
        for boundary in (3.5,7.5,11.5):
            fig.add_shape(type='line',xref='paper',x0=0,x1=1,y0=boundary,y1=boundary,line=dict(color='#667085',width=1))
        individual_html.append(html(fig,'individual-r'+str(rho).replace('.','')))

    endpoints=[];endpoint_tables=[]
    for profile in PROFILES+('all',):
        table=['<table><caption>'+escape(title(profile))+': effect of increasing receptiveness from 0.25 to 0.75</caption>'
               '<thead><tr><th>Support</th><th>Paired score change</th><th>Actors better / same / worse</th></tr></thead><tbody>']
        for c in CONDITIONS:
            values=[individuals[p,.75,c]['mean_delta']-individuals[p,.25,c]['mean_delta'] for p in people[profile]]
            endpoints.append({'profile':profile,'condition':c,'participants':len(values),'mean_075_minus_025':mean(values),
                'better':sum(v>1e-9 for v in values),'same':sum(abs(v)<=1e-9 for v in values),'worse':sum(v< -1e-9 for v in values)})
        for c,label,_,_ in STYLES:
            r=next(r for r in endpoints if r['profile']==profile and r['condition']==c)
            table.append(f'<tr><th>{escape(label)}</th><td>{r["mean_075_minus_025"]:+,.2f}</td>'
                         f'<td>{r["better"]} / {r["same"]} / {r["worse"]}</td></tr>')
        table.append('</tbody></table>');endpoint_tables.append(''.join(table))

    overall=[];overall_table=['<table><caption>Overall averages · 16 actors, three repetitions each</caption>'
        '<thead><tr><th>Receptiveness</th><th>Support</th><th>Mean score</th><th>Change from A</th>'
        '<th>Actors better / same / worse</th><th>Mean prompts per run</th></tr></thead><tbody>']
    for rho in LEVELS:
        for c in CONDITIONS:
            values=[individuals[p,rho,c] for p in people['all']];g=groups['all',rho,c]
            overall.append({**g,'mean_score':mean(r['mean_score'] for r in values),'baseline':mean(r['baseline'] for r in values),
                            'mean_interventions':mean(r['mean_interventions'] for r in values)})
        for c,label,_,_ in STYLES:
            r=next(r for r in overall if r['receptiveness']==rho and r['condition']==c)
            overall_table.append(f'<tr><th>{rho:g}</th><td>{escape(label)}</td><td>{r["mean_score"]:,.2f}</td>'
                f'<td>{r["mean_delta"]:+,.2f}</td><td>{r["better"]} / {r["same"]} / {r["worse"]}</td><td>{r["mean_interventions"]:.2f}</td></tr>')
    overall_table.append('</tbody></table>')
    baseline=overall[0]['baseline']
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MAB · fair receptiveness comparison</title>
<style>
body{font:16px system-ui,sans-serif;color:#243247;max-width:1500px;margin:32px auto;padding:0 24px;background:#fff}
h1{letter-spacing:-.03em}h2{margin-top:38px}p,li{line-height:1.55}p{max-width:1180px}a{color:#0064a3}
nav{display:flex;flex-wrap:wrap;gap:12px 24px;margin:22px 0}.status,.note{padding:14px 18px;border-radius:6px}
.status{background:#eef8f4;border-left:4px solid #009E73}.note{background:#f1f5fb;border-left:4px solid #0072B2}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:20px 0}.card{padding:16px;border:1px solid #dce4ed;border-radius:8px}
.card strong{display:block;font-size:24px;margin-bottom:4px}.chart{overflow-x:auto;border:1px solid #e0e6ee;border-radius:8px;margin:16px 0}
.plotly-graph-div{min-width:640px}.heatmaps .plotly-graph-div{min-width:800px}.individuals .plotly-graph-div{min-width:900px}
.trends{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,640px),1fr));gap:16px}.overall{grid-column:1/-1}
.tables{overflow-x:auto}table{border-collapse:collapse;margin:24px 0;font-variant-numeric:tabular-nums}
caption{text-align:left;font-weight:600;padding-bottom:12px}td,th{padding:10px 14px;text-align:right;border-bottom:1px solid #dbe2ea}
th:first-child,td:nth-child(2){text-align:left}thead{background:#f1f4f8}code{font-size:12px;overflow-wrap:anywhere}
summary{cursor:pointer;font-weight:600;padding:14px 0}footer{margin-top:32px;font-size:13px;color:#52657a}
</style></head><body>
<h1>MAB: fair comparison across receptiveness</h1>
<p class="status"><strong>Complete and independently verified.</strong> All 144 jobs finished, with 144 fresh A checks,
96 cross-level calibration checks and 144 historical baseline checks passing.</p>
<div class="cards"><div class="card"><strong>0.25 · 0.5 · 0.75</strong>Fixed receptiveness values</div>
<div class="card"><strong>16 actors</strong>Four per archetype · three repetitions</div>
<div class="card"><strong>720 fresh sessions</strong>A/C/E/D/F · 200 trials each</div>
<div class="card"><strong>144 calibrations</strong>Full MAB protocol · MAB only</div></div>
<nav aria-label="Report sections"><a href="#heatmaps">Heatmaps</a><a href="#trends">Receptiveness trends</a>
<a href="#style-gap">Socratic versus direct</a><a href="#individuals">Individual effects</a>
<a href="#endpoints">Paired receptiveness changes</a><a href="#method">Method and limits</a></nav>
<p>All five conditions were run afresh under the shared-ranking, performance-gated, single-response design.
Historical A results validate baseline equivalence; historical assisted results are excluded from these averages.
Repetitions are averaged within each actor before group means.</p>
<p><strong>Condition key:</strong> A = no assistance; C = task-aware direct; E = personalised direct;
D = task-aware Socratic; F = personalised Socratic. All plotted effects are in MAB reward points.</p>
<p class="note"><strong>Personalised pairs coincide:</strong> C/E and D/F had identical choice/outcome and
probability trajectories in all 144 matched cases per pair. Heatmaps retain all four conditions.
Trend plots combine the identical pairs as C/E and D/F; actor counts are not doubled.</p>
<h2>Overall outcomes</h2>
'''+''.join(overall_table)+f'<p>The shared mean unassisted A score is <strong>{baseline:,.2f} points</strong> at every receptiveness value.</p>'+'''
<ul><li>Both styles improve on A on average at all three tested values. Direct support has the higher overall mean at each value.</li>
<li>Group responses vary and can be non-monotonic. For example, the Dual-regime Socratic mean falls below A at 0.75;
the Low-expression Socratic mean falls below A at 0.5 and rises above it at 0.75.</li>
<li>These are descriptive synthetic outcomes. Identical personalised pairs reflect this implementation and response model;
they do not establish that personalisation or Socratic dialogue has no effect on people.</li></ul>
<h2 id="heatmaps">Group effects at each receptiveness value</h2>
<p>Each cell is the mean score change from A for four actors, each averaged across three repetitions.
Blue = gain; red = loss. All three group heatmaps share a symmetric scale centred on zero.
Hover for the number of actors doing better, the same or worse than A.</p><div class="heatmaps">
'''+''.join(group_html)+'''</div><h2 id="trends">Evolution with receptiveness</h2>
<p>All five panels use the same vertical scale. C/E share the blue circle curve; D/F share the orange diamond curve.
Lines connect the three tested values descriptively; intermediate values were not simulated. Click legend entries to hide/show a style.</p>
<div class="trends">'''+''.join(curves)+'''</div><h2>Socratic versus direct: paired differences</h2>
<p>Each cell below is Socratic minus direct, paired within the same actors and repetitions.
Blue means Socratic scored higher; red means direct scored higher. This uses the same point scale as the group heatmaps.
C/E are equivalent here, as are D/F.</p><div class="heatmaps">'''+gap_html+'''</div>
<details id="individuals"><summary>Individual effects · all 16 actors</summary>
<p>Each row is one actor's mean change from A across three repetitions. These three heatmaps share their own symmetric scale,
which is wider than the group scale. Hover for the three repetition changes, absolute scores and within-actor Monte Carlo SE.
This SE concerns repeated simulation, not uncertainty about human participants.</p><div class="individuals">'''+''.join(individual_html)+'''</div></details>
<h2 id="endpoints">Paired effect of increasing receptiveness</h2>
<p>Each table compares 0.75 with 0.25 within the same actor/repetition before taking actor and group averages.
Positive values mean the higher receptiveness improved the score. Counts are actors, not trials or extra participants.
Endpoint changes do not imply monotonicity at the intermediate value.</p><div class="tables">'''+''.join(endpoint_tables)+'''</div>
<h2 id="method">Method, interpretation and provenance</h2>
<p>The same 16 development profiles and matched random streams were used in every condition and level.
The four archetype labels are exploratory grouping metadata from the original profiles; results cover four selected actors per group,
not the entire 62-person registry. Every result here is MAB, including those for TBS-specialised actors.
Ordinary learning continues within each run and experience resets between conditions.
Receptiveness is a fixed mixture weight, not a measured probability of obeying or a learned trust parameter.
Reactance, distraction and additional omissions are zero; individual baseline omissions remain active.</p>
<p><strong>What this simulation measures:</strong> participant-facing direct assistance recommends an action with reasons;
Socratic assistance asks an evidence-backed question and guides comparison. The synthetic actor uses the structured
singleton/pair guidance and does not understand the wording, answer the question or deliberate through dialogue.
These scores assess a minimal recommendation-following/guided-choice model, not the full human effects of Socratic questioning.</p>
<p>The absence of an additional C/E or D/F difference is consistent with their shared public ranking and the actor's response to
structured guidance. Extra personalised wording/hypotheses are not interpreted by this actor. No artificial personalisation bonus is added.</p>
<details><summary>Audit details</summary><p>Every raw score, keyed outcome and transition was checked against the simulator.
All 144,000 comparison-trial outcomes, every active response mixture, 192 actor summaries and 60 group summaries were checked.
Actual calibration profiles and feedback were re-read from all 144 SQLite stores. All original frozen analyses remain unchanged.</p>
<p><a href="analysis.json">Frozen analysis</a> · <a href="report_audit.json">Numerical audit</a> ·
<a href="report_contrasts.json">Paired contrasts</a> · <a href="report_trial_summaries.json">Trial-derived session summaries</a></p></details>
<footer>Manifest: <code>'''+escape(a['manifest_sha256'])+'''</code><br>Source: completed fair MAB sweep; all repetitions included. Interactive charts are embedded for offline use.</footer>
<script>document.querySelectorAll('details').forEach(function(section){section.addEventListener('toggle',function(){if(section.open){requestAnimationFrame(function(){section.querySelectorAll('.plotly-graph-div').forEach(function(plot){if(plot._fullLayout){Plotly.Plots.resize(plot);}});});}});});</script>
</body></html>'''
    (root/'receptiveness_report.html').write_text(page)
    (root/'report_contrasts.json').write_text(json.dumps({'manifest_sha256':a['manifest_sha256'],
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),'overall':overall,'endpoints':endpoints,'style_gaps':gaps},indent=2)+'\n')
    (root/'report_figures.json').write_text(json.dumps({'manifest_sha256':a['manifest_sha256'],'figures':figures,
        'group_scale':limit,'individual_scale':individual_limit,'trend_pairs':['C/E','D/F'],'heatmap_cells':255,'trend_points':30},indent=2)+'\n')
    print('Saved:',root/'receptiveness_report.html')


if __name__=='__main__':main()
