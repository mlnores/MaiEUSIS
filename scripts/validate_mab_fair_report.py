#!/usr/bin/env python3
"""Validate the actual report's chart data, annotations, tables and offline HTML."""
import argparse
import json
import math
import re
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean

import mab_fair_report as report


def check(ok,message):
    if not ok:raise ValueError(message)


class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.scripts=[];self.dependencies=[];self.plot_divs=[]
        self.tables=[];self.table=None;self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='script':self.scripts.append(a)
        if tag in ('script','link','img') and (a.get('src') or a.get('href')):self.dependencies.append(a)
        if tag=='div' and 'plotly-graph-div' in a.get('class',''):self.plot_divs.append(a['id'])
        if tag=='table':self.table=[]
        if tag=='tr' and self.table is not None:self.row=[]
        if tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell));self.cell=None
        if tag=='tr' and self.row is not None:self.table.append(self.row);self.row=None
        if tag=='table' and self.table is not None:self.tables.append(self.table);self.table=None


def validate(root):
    root=Path(root).resolve();a=json.loads((root/'analysis.json').read_text())
    audit=json.loads((root/'report_audit.json').read_text())
    check(report.sha(root/'analysis.json')==audit['analysis_sha256'],'Frozen analysis changed')
    html=(root/'receptiveness_report.html').read_text();page=Page();page.feed(html)
    figures=json.loads((root/'report_figures.json').read_text())
    expected_ids=[*(f'group-r{str(rho).replace(".","")}' for rho in report.LEVELS),
        *(f'trend-{p.lower()}' for p in ('all',)+report.PROFILES),'style-gap',
        *(f'individual-r{str(rho).replace(".","")}' for rho in report.LEVELS)]
    check(page.plot_divs==figures['figures']==expected_ids,'Wrong figure/section order')
    check(len(page.ids)==len(set(page.ids)) and len(page.plot_divs)==12,'Duplicate/missing figure IDs')
    check(not page.dependencies,'HTML contains external rendering dependencies')
    decoder=json.JSONDecoder();plots={}
    for identifier in page.plot_divs:
        matches=list(re.finditer(r'Plotly\.newPlot\(\s*'+re.escape(json.dumps(identifier))+r'\s*,\s*',html))
        check(len(matches)==1,'Missing/duplicate Plotly call')
        start=matches[0].end();traces,end=decoder.raw_decode(html[start:])
        rest=html[start+end:].lstrip();check(rest.startswith(','),'Missing layout')
        layout,_=decoder.raw_decode(rest[1:].lstrip());plots[identifier]=(traces,layout)
    groups={(r['profile'],r['receptiveness'],r['condition']):r for r in a['groups']}
    individuals={(r['participant'],r['receptiveness'],r['condition']):r for r in a['individual_results']}
    profiles={r['participant']:r['profile'] for r in a['individual_results']}
    people={p:sorted(q for q,g in profiles.items() if g==p) for p in report.PROFILES};people['all']=sorted(profiles)
    heat_cells=trend_points=0;contrasts_seen=[]
    def luminance(rgb):
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    def colour_rgb(value):
        return [float(x)/255 for x in value[value.index('(')+1:value.index(')')].split(',')]
    def heat(identifier,expected,scale):
        nonlocal heat_cells
        traces,layout=plots[identifier];check(len(traces)==1 and traces[0]['type']=='heatmap','Wrong heatmap trace')
        t=traces[0]
        check(t['z']==expected,'Heatmap values differ from audited analysis')
        check(t['zmin']==-scale and t['zmax']==scale and t['zmid']==0,'Wrong colour domain')
        check(layout['yaxis']['autorange']=='reversed','Wrong row order')
        check(len(layout['annotations'])==sum(len(row) for row in expected),'Missing numerical cell labels')
        for row,y in zip(expected,t['y']):
            for v,x in zip(row,t['x']):
                check(abs(v)<=scale,'Cell outside colour scale')
                annotations=[r for r in layout['annotations'] if r['x']==x and r['y']==y]
                check(len(annotations)==1 and annotations[0]['text']==f'{v:+,.2f}','Annotation differs from data')
                position=(v+scale)/(2*scale)
                stops=t['colorscale']
                low,high=next((lo,hi) for lo,hi in zip(stops,stops[1:]) if lo[0]<=position<=hi[0])
                weight=(position-low[0])/(high[0]-low[0])
                background=[lo*(1-weight)+hi*weight for lo,hi in zip(colour_rgb(low[1]),colour_rgb(high[1]))]
                ink=annotations[0]['font']['color']
                check(ink in ('white','#000000'),'Unexpected heatmap text colour')
                foreground=[1.,1.,1.] if ink=='white' else [0.,0.,0.]
                lights=sorted((luminance(background),luminance(foreground)))
                contrast=(lights[1]+.05)/(lights[0]+.05)
                check(contrast>=4.5,'Insufficient heatmap label contrast')
                contrasts_seen.append(contrast)
                heat_cells+=1
        return t,layout
    for rho in report.LEVELS:
        t,_=heat('group-r'+str(rho).replace('.',''),[[groups[p,rho,c]['mean_delta'] for c in report.CONDITIONS] for p in report.PROFILES],figures['group_scale'])
        check(t['x']==list(report.LABELS) and t['y']==[p+' (n=4)' for p in report.PROFILES],'Wrong group labels/counts')
    ordered=[p for profile in report.PROFILES for p in people[profile]]
    for rho in report.LEVELS:
        t,_=heat('individual-r'+str(rho).replace('.',''),[[individuals[p,rho,c]['mean_delta'] for c in report.CONDITIONS] for p in ordered],figures['individual_scale'])
        check(t['x']==list(report.LABELS),'Wrong individual condition columns')
    for profile in ('all',)+report.PROFILES:
        traces,layout=plots['trend-'+profile.lower()]
        check(len(traces)==2 and layout['yaxis']['range']==[-figures['group_scale']*1.1,figures['group_scale']*1.1],'Wrong/shared trend scale')
        for trace,(c,label,color,marker) in zip(traces,report.STYLES):
            check(trace['x']==list(report.LEVELS) and trace['y']==[groups[profile,rho,c]['mean_delta'] for rho in report.LEVELS],'Wrong trend points')
            check(trace['name']==label and trace['line']['color']==color and trace['marker']['symbol']==marker,'Inconsistent trend encoding')
            check(all(x[3]==(16 if profile=='all' else 4) for x in trace['customdata']),'Wrong trend sample size')
            trend_points+=len(trace['x'])
    gap=[[mean(individuals[p,rho,'D']['mean_delta']-individuals[p,rho,'C']['mean_delta'] for p in people[profile])
          for rho in report.LEVELS] for profile in report.PROFILES+('all',)]
    heat('style-gap',gap,figures['group_scale'])
    check(heat_cells==255 and trend_points==30,'Unexpected number of plotted data values')
    contrasts=json.loads((root/'report_contrasts.json').read_text())
    check(len(contrasts['endpoints'])==20 and len(contrasts['style_gaps'])==15 and len(contrasts['overall'])==12,'Missing exported contrasts')
    for row in contrasts['endpoints']:
        values=[individuals[p,.75,row['condition']]['mean_delta']-individuals[p,.25,row['condition']]['mean_delta'] for p in people[row['profile']]]
        check(row['mean_075_minus_025']==mean(values) and row['participants']==len(values),'Wrong endpoint contrast')
        check(tuple(row[k] for k in ('better','same','worse'))==(sum(v>1e-9 for v in values),sum(abs(v)<=1e-9 for v in values),sum(v< -1e-9 for v in values)),'Wrong endpoint harm counts')
    check(len(page.tables)==6 and len(page.tables[0])==7,'Missing summary tables')
    table_rows=[]
    for rho in report.LEVELS:
        for c,label,_,_ in report.STYLES:
            data=[individuals[p,rho,c] for p in people['all']];g=groups['all',rho,c]
            table_rows.append([f'{rho:g}',label,f'{mean(r["mean_score"] for r in data):,.2f}',f'{g["mean_delta"]:+,.2f}',
                              f'{g["better"]} / {g["same"]} / {g["worse"]}',f'{mean(r["mean_interventions"] for r in data):.2f}'])
    check(page.tables[0][1:]==table_rows,'Rendered overall table differs from source results')
    check('Identical personalised pairs' in html or 'Personalised pairs coincide' in html,'Missing overlap explanation')
    check(report.sha(root/'analysis.json')==audit['analysis_sha256'],'Analysis was rewritten')
    validation={'validated_at_utc':datetime.now(timezone.utc).isoformat(),'manifest_sha256':a['manifest_sha256'],
        'analysis_sha256':audit['analysis_sha256'],'report_sha256':report.sha(root/'receptiveness_report.html'),
        'plotly_figures':len(plots),'heatmap_cells_checked':heat_cells,'trend_points_checked':trend_points,
        'endpoint_contrasts_checked':20,'paired_style_gap_cells_checked':15,'rendered_overall_table_rows_checked':6,
        'minimum_heatmap_label_contrast':min(contrasts_seen),
        'self_contained_html':True,'analysis_unchanged':True,
        'native_preview':'Unavailable: browser access host unavailable; native Chrome access was not approved.'}
    (root/'report_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps(validation,indent=2));return validation


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    validate(parser.parse_args().directory)
