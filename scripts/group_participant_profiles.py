#!/usr/bin/env python3
"""Export all reconstructed actors by their frozen original archetype.

No fitting, new clustering, simulation, or modification of the cohort bundle.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

GROUPS = {'MAB-specialised': 'mab_specialised', 'TBS-specialised': 'tbs_specialised',
          'Dual-regime': 'dual_regime', 'Low-expression': 'low_expression'}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def classify(mab, tbs, settings):
    low = ((mab < settings['LowBothCutoff'] and tbs < settings['LowBothCutoff']) or
           ((mab+tbs)/2 <= settings['ObservedVeryLowCut_N62'] and mab <= 0 and tbs <= 0))
    if low:
        return 'Low-expression'
    if mab > 0 and tbs > 0 and abs(mab-tbs) <= settings['DualBalanceTolerance']:
        return 'Dual-regime'
    return 'MAB-specialised' if mab >= tbs else 'TBS-specialised'


def group(bundle, output):
    require(not output.is_relative_to(bundle), 'Write grouped exports outside the frozen bundle')
    manifest = read(bundle/'bundle_manifest.json')
    names = ['cohort.json', 'import_audit.json', 'participants.all.json',
             'participants.development.json', 'participants.evaluation.json']
    for name in names:
        require(hashlib.sha256((bundle/name).read_bytes()).hexdigest() == manifest['files'][name],
                'Frozen bundle file changed: '+name)
    cohort = read(bundle/'cohort.json'); actors = read(bundle/'participants.all.json')
    people = {p['id']:p for p in cohort['people']}
    require(len(people) == len(cohort['people']) == len(actors) == 62, 'Expected 62 distinct participants')
    actor_map = {a['id']:a for a in actors}
    require(len(actor_map) == 62 and set(actor_map) == set(people), 'Actor/registry identities differ')
    for split in ('development','evaluation'):
        subset = read(bundle/f'participants.{split}.json')
        require(len({a['id'] for a in subset}) == len(subset), 'Duplicate split export identity')
        require({a['id'] for a in subset} == {p['id'] for p in people.values() if p['split'] == split}, 'Split membership changed')
        require(all(a == actor_map[a['id']] for a in subset), 'Split actor parameters differ from all-actor export')
    settings = read(bundle/'import_audit.json')['classification_settings'][0]
    for person in people.values():
        actor = actor_map[person['id']]
        require(actor['original_profile'] == person['original_profile'] and
                actor['provenance']['source_id'] == person['source_id'] and
                actor['provenance']['split'] == person['split'], 'Original profile or provenance mismatch')
        scores = person['core_profile_scores']
        require(classify(scores['MAB_CoreProfile_Z'],scores['TBS_CoreProfile_Z'],settings) == person['original_profile'],
                'Frozen classification cannot be reproduced for '+person['source_id'])
    groups = []
    for label, slug in GROUPS.items():
        members = []
        for person in sorted(people.values(), key=lambda p:p['source_id']):
            if person['original_profile'] == label:
                members.append({k:person[k] for k in ('id','source_id','split','original_profile','core_profile_scores')})
        require(len(members) == cohort['profile_counts'][label], 'Archetype count mismatch')
        groups.append({'archetype':label,'total':len(members),'percentage':len(members)/62*100,
                       'split_counts':dict(Counter(p['split'] for p in members)),
                       'actors_file':f'participants.{slug}.json','members':members})
    require(sum(g['total'] for g in groups) == 62, 'Grouping does not cover the complete cohort')
    report = {'created_at_utc':datetime.now(timezone.utc).isoformat(), 'researcher_only':True,
              'method':'Preserved original assignments, independently reproduced from the frozen classification rules.',
              'frozen_procedure_sha256':manifest['frozen_procedure_sha256'],
              'source_file_sha256':{name:manifest['files'][name] for name in names},
              'classification_settings':settings,'participants':62,'development':16,'evaluation':46,'groups':groups,
              'notice':'Original exploratory L1–L5 multilevel profiles, including neural and dispositional components. '
                       'These are not guaranteed task-score rankings or inferred AI attitudes. Individual actor parameters '
                       'and the development/evaluation split are unchanged. Original profiles remain researcher-side metadata.'}
    output.mkdir(parents=True,exist_ok=True)
    for item in groups:
        write(output/item['actors_file'],[actor_map[p['id']] for p in item['members']])
    write(output/'groups.json',report)
    lines = ['# All 62 reconstructed participants by original archetype','',report['notice'],'',
             '| Archetype | Total | Share | Development | Evaluation | Actor export |',
             '| --- | ---: | ---: | ---: | ---: | --- |']
    for item in groups:
        lines.append(f"| {item['archetype']} | {item['total']} | {item['percentage']:.1f}% | "
                     f"{item['split_counts']['development']} | {item['split_counts']['evaluation']} | "
                     f"[JSON]({item['actors_file']}) |")
    lines += ['', '## Original classification rule', '',
        'Let x be MAB_CoreProfile_Z and y be TBS_CoreProfile_Z. Apply the rules in this order:', '',
        '1. Low-expression if both x and y are below −0.25, or if both are nonpositive and '
        '(x+y)/2 is at most −0.46637458843810997 (the original observed 15th-percentile cutoff).',
        '2. Otherwise, Dual-regime if both scores are positive and |x−y| ≤ 0.75.',
        '3. Otherwise, MAB-specialised if x ≥ y; TBS-specialised if y > x.', '',
        'All 62 assignments reproduce the supplied labels. These regions are not four simple sign quadrants.']
    for item in groups:
        lines += ['', '## '+item['archetype'], '',
                  '**Development:** '+', '.join(p['source_id'] for p in item['members'] if p['split']=='development')+'.', '',
                  '**Evaluation:** '+', '.join(p['source_id'] for p in item['members'] if p['split']=='evaluation')+'.', '',
                  '| Participant | Split | MAB core z | TBS core z |','| --- | --- | ---: | ---: |']
        for p in item['members']:
            lines.append(f"| {p['source_id']} | {p['split']} | {p['core_profile_scores']['MAB_CoreProfile_Z']:+.3f} | "
                         f"{p['core_profile_scores']['TBS_CoreProfile_Z']:+.3f} |")
    (output/'membership.md').write_text('\n'.join(lines)+'\n')
    return report


def plot(report, output):
    import plotly.graph_objects as go
    fig = go.Figure()
    colours = ['#2864b4','#a14173','#218268','#8a6819']
    for item, colour in zip(report['groups'],colours):
        for split, symbol in [('evaluation','circle'),('development','diamond')]:
            people = [p for p in item['members'] if p['split']==split]
            fig.add_trace(go.Scatter(x=[p['core_profile_scores']['MAB_CoreProfile_Z'] for p in people],
                y=[p['core_profile_scores']['TBS_CoreProfile_Z'] for p in people],mode='markers',
                name=f"{item['archetype']} · {split} ({len(people)})",text=[p['source_id'] for p in people],
                marker=dict(color=colour,symbol=symbol,size=13 if split=='development' else 10,line=dict(color='white',width=1)),
                hovertemplate='%{text}<br>MAB core z: %{x:.3f}<br>TBS core z: %{y:.3f}<extra>%{fullData.name}</extra>'))
    fig.update_layout(template='plotly_white',title='All 62 participants: original archetype assignments',
        xaxis_title='MAB core profile (z score)',yaxis_title='TBS core profile (z score)',height=760,
        margin=dict(l=70,r=40,t=75,b=70),font=dict(family='Arial, sans-serif',size=14),
        legend=dict(orientation='h',y=-.13),yaxis=dict(scaleanchor='x',scaleratio=1))
    fig.add_hline(y=0,line_width=1,line_dash='dot',line_color='#aaa')
    fig.add_vline(x=0,line_width=1,line_dash='dot',line_color='#aaa')
    intro = ('<h1>The four original archetypes</h1><p>All 62 reconstructed participants. '
             'Diamonds identify the 16 development actors; circles identify the 46 evaluation actors. '
             'Hover for identities and original scores; click legend entries to filter groups. '
             'The dotted zero lines are reference lines, not classification boundaries. '
             'Assignments follow the original low-expression thresholds and dual-balance tolerance.</p>')
    output.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Original archetypes: all 62 participants</title><style>body{font:16px system-ui;color:#243247;max-width:1250px;'
        'margin:25px auto;padding:0 20px}p{line-height:1.5}</style>'+intro+
        fig.to_html(full_html=False,include_plotlyjs=True)+'</html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--plot',action='store_true',help='Optional self-contained Plotly scatterplot')
    args = parser.parse_args()
    output = args.output_dir.resolve();report = group(args.cohort_dir.resolve(),output)
    if args.plot:
        plot(report,output/'archetypes.html')
    print(json.dumps({g['archetype']:{'total':g['total'],**g['split_counts']} for g in report['groups']},indent=2))
    print('Saved grouping:',output)


if __name__ == '__main__':
    main()
