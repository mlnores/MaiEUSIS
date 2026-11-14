#!/usr/bin/env python3
"""Render a completed MAB receptiveness sweep without importing its runtime."""
import argparse
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from statistics import mean

PROFILES=('MAB-specialised','TBS-specialised','Dual-regime','Low-expression','all')
VARIANTS=(('C','current'),('E','current'),('D','current'),('F','current'),('D','recent'),('F','recent'))
LABELS=('C direct','E personalised direct','D current','F current','D recent','F recent')
LEVELS=(.25,.5,.75)
STYLES=(('#0072B2','circle','solid'),('#009E73','square','solid'),
        ('#D55E00','triangle-up','solid'),('#CC79A7','diamond','solid'),
        ('#D55E00','triangle-up','dash'),('#CC79A7','diamond','dash'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    root=parser.parse_args().directory.resolve();analysis=json.loads((root/'analysis.json').read_text())
    if not (analysis['complete'] and analysis['bridge']['verified'] and analysis['control_checks_passed']):
        raise ValueError('Only a complete sweep with verified bridge and controls can produce the final report')
    import plotly.graph_objects as go
    groups={(r['profile'],r['receptiveness'],r['condition'],r['mechanism']):r for r in analysis['groups']}
    individuals={(r['participant'],r['receptiveness'],r['condition'],r['mechanism']):r for r in analysis['individual_results']}
    profiles={r['participant']:r['profile'] for r in analysis['individual_results']}
    limit=max(abs(r['mean_delta']) for r in analysis['groups']) or 1
    people_by_profile={profile:[p for p,g in profiles.items() if profile=='all' or g==profile] for profile in PROFILES}
    titles={profile:('All actors' if profile=='all' else profile)+f' (n={len(people_by_profile[profile])})'
            for profile in PROFILES}
    charts=[];curves=[];comparisons=[];tables=[]
    for rho in LEVELS:
        rows=[[groups[(profile,rho,c,m)] for c,m in VARIANTS] for profile in PROFILES[:-1]]
        values=[[r['mean_delta'] for r in row] for row in rows]
        detail=[[f"Mean change: {r['mean_delta']:+,.2f} points<br>Better / same / worse than A: "
                 f"{r['better']} / {r['same']} / {r['worse']}<br>Actors: {r['participants']}; "
                 f"repetitions per actor: {r['repetitions']}" for r in row] for row in rows]
        fig=go.Figure(go.Heatmap(z=values,x=LABELS,y=[titles[p] for p in PROFILES[:-1]],
            zmin=-limit,zmax=limit,zmid=0,colorscale='RdBu',colorbar=dict(title='Points<br>from A'),
            text=[[f'{v:+,.2f}' for v in row] for row in values],texttemplate='%{text}',customdata=detail,
            hovertemplate=f'Receptiveness {rho:g}<br>%{{y}}<br>%{{x}}<br>%{{customdata}}<extra></extra>'))
        fig.update_layout(template='plotly_white',title=f'Receptiveness {rho:g}',
                          margin=dict(l=195,r=90,t=65,b=95),height=440,
                          yaxis=dict(autorange='reversed'),xaxis=dict(tickangle=-15),
                          xaxis_title='Assistance condition and processing mechanism',font=dict(family='Arial',size=12))
        charts.append(fig.to_html(full_html=False,include_plotlyjs=(rho==LEVELS[0]),config={'responsive':True,'displaylogo':False}))
    for profile in ('all',)+PROFILES[:-1]:
        curve=go.Figure()
        for label,(c,m),(color,symbol,dash) in zip(LABELS,VARIANTS,STYLES):
            rows=[groups[(profile,rho,c,m)] for rho in LEVELS]
            curve.add_trace(go.Scatter(x=LEVELS,y=[r['mean_delta'] for r in rows],mode='lines+markers',name=label,
                line=dict(color=color,dash=dash,width=2),marker=dict(color=color,symbol=symbol,size=8),
                customdata=[[r['better'],r['same'],r['worse'],r['participants']] for r in rows],
                hovertemplate='%{fullData.name}<br>Receptiveness %{x}<br>Change from A: %{y:+,.2f} points'
                '<br>Better / same / worse: %{customdata[0]} / %{customdata[1]} / %{customdata[2]}'
                '<br>Actors: %{customdata[3]}<extra></extra>'))
        curve.update_layout(template='plotly_white',title=titles[profile],height=550,
                            margin=dict(l=80,r=25,t=65,b=160),
                            xaxis=dict(title='Receptiveness',tickvals=LEVELS,range=[.2,.8]),
                            yaxis=dict(title='Mean change from A (points)',range=[-limit*1.1,limit*1.1],
                                       zeroline=True,zerolinewidth=1.5,zerolinecolor='#667085'),
                            legend=dict(orientation='h',x=0,y=-.24,xanchor='left',yanchor='top'),
                            font=dict(family='Arial',size=12))
        curves.append(curve.to_html(full_html=False,include_plotlyjs=False,config={'responsive':True,'displaylogo':False}))
    for profile in PROFILES:
        title=titles[profile];people=people_by_profile[profile]
        table=['<table><caption>'+escape(title)+': change when receptiveness increases from 0.25 to 0.75</caption>'
               '<thead><tr><th>Support</th><th>Mean score change</th><th>Better / same / worse</th></tr></thead><tbody>']
        for label,(c,m) in zip(LABELS,VARIANTS):
            deltas=[individuals[(p,.75,c,m)]['mean_delta']-individuals[(p,.25,c,m)]['mean_delta'] for p in people]
            counts=(sum(x>1e-9 for x in deltas),sum(abs(x)<=1e-9 for x in deltas),sum(x< -1e-9 for x in deltas))
            record={'profile':profile,'condition':c,'mechanism':m,'participants':len(people),
                    'mean_075_minus_025':mean(deltas),'better':counts[0],'same':counts[1],'worse':counts[2]}
            comparisons.append(record)
            table.append(f'<tr><th>{label}</th><td>{record["mean_075_minus_025"]:+,.2f}</td>'
                         f'<td>{counts[0]} / {counts[1]} / {counts[2]}</td></tr>')
        table.append('</tbody></table>');tables.append(''.join(table))
    html=('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>MAB receptiveness sensitivity</title><style>body{font:16px system-ui;color:#243247;max-width:1550px;'
        'margin:30px auto;padding:0 24px}p{max-width:1150px;line-height:1.5}.charts{display:grid;grid-template-columns:'
        'repeat(auto-fit,minmax(min(100%,660px),1fr));gap:22px}.chart,.tables{overflow-x:auto}.plotly-graph-div{min-width:660px}'
        '.heatmaps .plotly-graph-div{min-width:850px}.chart{border:1px solid #e4e9f0;border-radius:8px;margin:16px 0}'
        'h2{margin-top:38px}.status{padding:14px 18px;border-left:4px solid #009E73;background:#eef8f4}'
        'nav a{margin-right:20px}a{color:#0064a3}'
        'table{border-collapse:collapse;margin:24px 0}caption{text-align:left;font-weight:600;padding:0 0 12px}'
        'td,th{padding:10px 14px;border-bottom:1px solid #dbe2ea;text-align:right}th:first-child{text-align:left}'
        'thead{background:#f1f4f8}code{font-size:12px;overflow-wrap:anywhere}</style></head><body><h1>MAB receptiveness sensitivity</h1>'
        '<p class="status"><strong>Complete and verified.</strong> '
        f'{analysis["new_jobs_completed"]}/{analysis["new_jobs_planned"]} new jobs; '
        f'{analysis["reused_reference_jobs"]} reused reference jobs; '
        f'{sum(analysis["controls"].values()):,} matched controls passed. The full-protocol bridge passed '
        f'{analysis["bridge"]["comparisons"]} comparison and {analysis["bridge"]["calibrations"]} calibration checks.</p>'
        '<nav aria-label="Report sections"><a href="#heatmaps">Heatmaps</a><a href="#trends">Trends</a>'
        '<a href="#contrasts">Paired changes</a></nav>'
        '<p>Complete matched experiment at receptiveness 0.25, 0.5 and 0.75: 2,160 MAB condition sessions. Sixteen development actors, '
        'four per archetype, three repetitions per actor, all five assistance conditions and all three '
        'reconsideration mechanisms. Repetitions are averaged within actors before group means; they are not additional participants.</p>'
        '<p>'+escape(analysis['notice'])+'</p><p>The receptiveness parameter (<code>responsiveness</code> in the implementation) weights reconsidered/recommended preferences '
        'against baseline preferences. It is identical for both assistance styles and does not evolve. '
        'Higher receptiveness need not increase rewards. The same random streams are used across levels. '
        'With none, D/F retain baseline preferences and match A; those verified control variants remain in the data.</p>'
        '<p>A = no assistance; C = task-aware direct advice; E = personalised direct advice; '
        'D = task-aware Socratic questions; F = personalised Socratic questions. Current/recent '
        'identify the actor’s reconsideration mechanism. C/E appear once because their trajectories are identical across mechanisms.</p>'
        '<h2 id="heatmaps">Heatmaps by receptiveness</h2>'
        '<p>Each cell is the archetype’s mean change from unassisted A, in MAB points. Blue = gain; red = loss. '
        'All three heatmaps share one symmetric scale centred on zero. Hover over cells for actor counts '
        'and the number doing better, the same or worse than A.</p><div class="heatmaps">'+''.join('<div class="chart">'+c+'</div>' for c in charts)+
        '</div><h2 id="trends">Trends across receptiveness values</h2>'
        '<p>Overall and archetype averages use the same vertical scale, colours and marker shapes. '
        'Solid D/F lines use current processing; dashed D/F lines use recent processing. Lines connect the three '
        'tested values descriptively; intermediate values were not simulated. Click legend entries to hide '
        'or show individual support variants.</p><div class="charts">'+''.join('<div class="chart">'+c+'</div>' for c in curves)+
        '</div><h2 id="contrasts">Effect of increasing receptiveness</h2>'
        '<p>Paired changes compare 0.75 against 0.25 within the same actors, repetitions and mechanisms. '
        'Counts refer to actors, not trials or repeated simulations.</p><div class="tables">'+''.join(tables)+
        '</div><p>Conditional synthetic outcomes, not measured human responsiveness or assistance effects. '
        'Original profile labels remain exploratory grouping metadata. The 0.5 reference is reused from the completed guided pilot, '
        'after a full-protocol MAB-only calibration/trajectory bridge check. Bridge jobs are excluded from comparative averages.</p>'
        '<p>Source: <code>analysis.json</code>; paired contrasts: <code>receptiveness_contrasts.json</code>. '
        'Manifest: <code>'+analysis['manifest_sha256']+'</code></p></body></html>')
    (root/'receptiveness_report.html').write_text(html)
    (root/'receptiveness_contrasts.json').write_text(json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'manifest_sha256':analysis['manifest_sha256'],'contrasts':comparisons},indent=2)+'\n')
    print('Saved MAB sensitivity report:',root/'receptiveness_report.html',flush=True)


if __name__=='__main__':main()
