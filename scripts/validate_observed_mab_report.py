#!/usr/bin/env python3
"""Check actual offline HTML figures/tables against audited trial-derived summaries."""
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean, stdev

from observed_mab_report import PROFILES, CONDITIONS, LABELS, LEVELS, STYLES, CONTRASTS


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def same(values, expected):
    return len(values) == len(expected) and all(close(x, y) for x, y in zip(values, expected))


def sign_counts(values):
    return [sum(v > 1e-9 for v in values), sum(abs(v) <= 1e-9 for v in values), sum(v < -1e-9 for v in values)]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []; self.scripts = []; self.dependencies = []; self.plot_divs = []; self.options = []
        self.tables = {}; self.table_id = None; self.table = None; self.row = None; self.cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        if tag == 'script':
            self.scripts.append(a)
        if tag in ('script', 'link', 'img') and (a.get('src') or a.get('href')):
            self.dependencies.append(a)
        if tag == 'option':
            self.options.append(a.get('value'))
        if tag == 'div' and 'plotly-graph-div' in a.get('class', ''):
            self.plot_divs.append(a['id'])
        if tag == 'table':
            self.table_id = a.get('id'); self.table = []
        if tag == 'tr' and self.table is not None:
            self.row = []
        if tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell)); self.cell = None
        if tag == 'tr' and self.row is not None:
            self.table.append(self.row); self.row = None
        if tag == 'table' and self.table is not None:
            self.tables[self.table_id] = self.table; self.table = None; self.table_id = None


def validate(root):
    root = Path(root).resolve()
    audit = read(root/'report_audit.json'); a = read(root/'analysis.json')
    check(a['complete'] and audit['verified'] and sha(root/'analysis.json') == audit['analysis_sha256'], 'Frozen analysis changed')
    raw = read(root/'report_trial_summaries.json')
    check(raw['manifest_sha256'] == a['manifest_sha256'] and len(raw['rows']) == 720, 'Wrong audited source')
    rows = {(r['participant'], r['repeat'], r['receptiveness'], r['condition']): r for r in raw['rows']}
    check(len(rows) == 720, 'Duplicate source cases')
    root_manifest = read(root/'manifest.json')
    actors = read(root/root_manifest['levels']['0.25']['directory']/'participants.json')
    membership = {p['id']: p['original_profile'] for p in actors}
    people = {g: sorted(p for p, label in membership.items() if label == g) for g in PROFILES}
    people['all'] = sorted(membership)
    check(len(people['all']) == 16 and all(len(people[g]) == 4 for g in PROFILES), 'Wrong membership')
    individual = {}
    for p in people['all']:
        for rho in LEVELS:
            for c in CONDITIONS:
                chosen = [rows[p, r, rho, c] for r in range(3)]
                baseline = [rows[p, r, rho, 'A'] for r in range(3)]
                changes = [x['score']-b['score'] for x, b in zip(chosen, baseline)]
                individual[p, rho, c] = {'mean_delta': mean(changes), 'mean_score': mean(x['score'] for x in chosen),
                                        'baseline': mean(b['score'] for b in baseline),
                                        'mean_interventions': mean(x['interventions'] for x in chosen),
                                        'monte_carlo_se': stdev(changes)/math.sqrt(3),
                                        'repetition_deltas': changes}
    group = {}
    for g in (*PROFILES, 'all'):
        for rho in LEVELS:
            for c in CONDITIONS:
                data = [individual[p, rho, c] for p in people[g]]
                values = [r['mean_delta'] for r in data]
                group[g, rho, c] = {'mean_delta': mean(values), 'mean_score': mean(r['mean_score'] for r in data),
                                    'mean_interventions': mean(r['mean_interventions'] for r in data),
                                    'counts': sign_counts(values), 'participants': len(data)}
    html = (root/'receptiveness_report.html').read_text()
    page = Page(); page.feed(html)
    metadata = read(root/'report_figures.json')
    ordered = [p for g in PROFILES for p in people[g]]
    short = lambda p: p.rsplit('_', 1)[-1]
    title = lambda g: ('All profiles' if g == 'all' else g)+f' (n={len(people[g])})'
    expected_ids = [
        *(f'cluster-heat-r{str(r).replace(".","")}' for r in LEVELS),
        *(f'cluster-trend-{g.lower()}' for g in ('all',)+PROFILES),
        *(f'individual-heat-r{str(r).replace(".","")}' for r in LEVELS),
        *(f'individual-trend-{short(p).lower()}' for p in ordered),
        *(f'contrast-{key}-plot' for key, _, _ in CONTRASTS), 'prompt-trend-all',
    ]
    check(page.plot_divs == expected_ids == [r['id'] for r in metadata['figures']], 'Wrong chart IDs/order')
    check(len(page.plot_divs) == 33 and len(page.ids) == len(set(page.ids)), 'Missing/duplicate figures or IDs')
    check(not page.dependencies, 'External rendering dependencies')
    check(sorted(page.options) == people['all'], 'Individual-profile jump selector is incomplete')
    check(all('card-'+p in page.ids for p in ordered), 'Missing individual profile panels')
    plots = {}; decoder = json.JSONDecoder()
    for identifier in expected_ids:
        matches = list(re.finditer(r'Plotly\.newPlot\(\s*'+re.escape(json.dumps(identifier))+r'\s*,\s*', html))
        check(len(matches) == 1, 'Missing/duplicate Plotly call')
        start = matches[0].end(); traces, end = decoder.raw_decode(html[start:])
        rest = html[start+end:].lstrip()
        check(rest.startswith(','), 'Missing layout')
        layout, _ = decoder.raw_decode(rest[1:].lstrip())
        plots[identifier] = traces, layout

    heat_cells = 0; trend_points = 0; contrast_ratios = []

    def light(rgb):
        return sum((v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)*w
                   for v, w in zip(rgb, (.2126, .7152, .0722)))

    def rgb(value):
        return [float(x)/255 for x in value[value.index('(')+1:value.index(')')].split(',')]

    def heat(identifier, values, columns, labels, scale):
        nonlocal heat_cells
        traces, layout = plots[identifier]
        check(len(traces) == 1 and traces[0]['type'] == 'heatmap', 'Wrong heatmap trace')
        t = traces[0]
        check(len(t['z']) == len(values) and all(same(x, y) for x, y in zip(t['z'], values)), 'Heatmap data differ from raw summaries')
        check(t['x'] == list(columns) and t['y'] == list(labels), 'Wrong heatmap axes')
        check(t['zmin'] == -scale and t['zmax'] == scale and t['zmid'] == 0, 'Wrong shared zero-centred colour scale')
        check(layout['yaxis']['autorange'] == 'reversed', 'Wrong row ordering')
        annotations = layout['annotations']
        check(len(annotations) == sum(len(x) for x in values), 'Missing numerical heatmap labels')
        for row, y in zip(values, labels):
            for value, x in zip(row, columns):
                check(abs(value) <= scale, 'Clipped heatmap value')
                found = [r for r in annotations if r['x'] == x and r['y'] == y]
                v = 0. if abs(value) < 1e-9 else value
                check(len(found) == 1 and found[0]['text'] == f'{v:+,.2f}', 'Incorrect cell annotation')
                position = (value+scale)/(2*scale)
                low, high = next((lo, hi) for lo, hi in zip(t['colorscale'], t['colorscale'][1:])
                                 if lo[0] <= position <= hi[0])
                w = (position-low[0])/(high[0]-low[0])
                background = [a*(1-w)+b*w for a, b in zip(rgb(low[1]), rgb(high[1]))]
                ink = found[0]['font']['color']
                check(ink in ('white', '#000000'), 'Unknown annotation colour')
                foreground = [1., 1., 1.] if ink == 'white' else [0., 0., 0.]
                levels = sorted((light(background), light(foreground)))
                contrast = (levels[1]+.05)/(levels[0]+.05)
                check(contrast >= 4.5, 'Insufficient heatmap text contrast')
                contrast_ratios.append(contrast); heat_cells += 1

    for rho in LEVELS:
        heat('cluster-heat-r'+str(rho).replace('.', ''),
             [[group[g, rho, c]['mean_delta'] for c in CONDITIONS] for g in PROFILES], LABELS,
             [title(g) for g in PROFILES], metadata['group_scale'])
        heat('individual-heat-r'+str(rho).replace('.', ''),
             [[individual[p, rho, c]['mean_delta'] for c in CONDITIONS] for p in ordered], LABELS,
             [membership[p]+' · '+short(p) for p in ordered], metadata['individual_scale'])

    def curve(identifier, lookup, yrange, individual_plot=False, prompt=False):
        nonlocal trend_points
        traces, layout = plots[identifier]
        check(len(traces) == 4, 'C/E/D/F must be four separate series')
        check(layout['yaxis']['range'] == yrange and layout['xaxis']['tickvals'] == list(LEVELS), 'Wrong/shared trend axes')
        check(layout['margin']['b'] >= 120 and layout['legend']['orientation'] == 'h', 'Legend space/style missing')
        metric = 'mean_interventions' if prompt else 'mean_delta'
        for trace, (c, label, color, symbol, dash) in zip(traces, STYLES):
            selected = [lookup[rho, c] for rho in LEVELS]
            check(trace['type'] == 'scatter' and trace['mode'] == 'lines+markers', 'Nonlinear/missing trend trace')
            check(trace['x'] == list(LEVELS) and same(trace['y'], [r[metric] for r in selected]), 'Trend values differ')
            check(trace['name'] == label and trace['line']['color'] == color and trace['line']['dash'] == dash
                  and trace['marker']['symbol'] == symbol, 'Inconsistent condition encoding')
            for custom, expected in zip(trace['customdata'], selected):
                if individual_plot:
                    check(same(custom[:4], [expected[k] for k in ('mean_score', 'baseline', 'mean_interventions', 'monte_carlo_se')]),
                          'Wrong individual hover score/prompts/uncertainty')
                    check(custom[4] == ', '.join(f'{x:+g}' for x in expected['repetition_deltas']), 'Wrong repetition hover values')
                else:
                    check(custom == [*expected['counts'], expected['participants']], 'Wrong group count/harms tooltip')
            check(all(yrange[0] <= v <= yrange[1] for v in trace['y']), 'Clipped trend')
            trend_points += len(trace['x'])

    for g in ('all',)+PROFILES:
        curve('cluster-trend-'+g.lower(), {(rho, c): group[g, rho, c] for rho in LEVELS for c in CONDITIONS},
              metadata['group_trend_range'])
    for p in ordered:
        curve('individual-trend-'+short(p).lower(), {(rho, c): individual[p, rho, c] for rho in LEVELS for c in CONDITIONS},
              metadata['individual_trend_range'], individual_plot=True)
    curve('prompt-trend-all', {(rho, c): group['all', rho, c] for rho in LEVELS for c in CONDITIONS}, metadata['prompt_range'], prompt=True)

    exported = read(root/'report_contrasts.json')
    check(len(exported['contrasts']) == 75 and len(exported['endpoints']) == 20 and len(exported['overall']) == 12, 'Missing exported comparisons')
    for key, label, weights in CONTRASTS:
        values = []
        for g in PROFILES+('all',):
            row = []
            for rho in LEVELS:
                paired = [sum(w*individual[p, rho, c]['mean_delta'] for c, w in weights.items()) for p in people[g]]
                row.append(mean(paired))
                saved = next(r for r in exported['contrasts'] if (r['contrast'], r['profile'], r['receptiveness']) == (key, g, rho))
                check(close(saved['mean_delta'], mean(paired)) and saved['participants'] == len(paired)
                      and [saved[k] for k in ('better', 'same', 'worse')] == sign_counts(paired), 'Wrong paired contrast')
                prompts = [sum(w*individual[p, rho, c]['mean_interventions'] for c, w in weights.items()) for p in people[g]]
                check(close(saved['mean_prompt_difference'], mean(prompts)), 'Wrong paired prompt contrast')
            values.append(row)
        heat('contrast-'+key+'-plot', values, [f'{r:g}' for r in LEVELS],
             [title(g) for g in PROFILES+('all',)], metadata['contrast_scale'])

    check(heat_cells == 315 and trend_points == 264, 'Unexpected number of chart data values')
    expected_overall = []
    for rho in LEVELS:
        for c, label, _, _, _ in STYLES:
            r = group['all', rho, c]
            expected_overall.append([f'{rho:g}', label, f'{r["mean_score"]:,.2f}', f'{r["mean_delta"]:+,.2f}',
                                     ' / '.join(str(x) for x in r['counts']), f'{r["mean_interventions"]:.2f}'])
    check(page.tables['overall-table'][1:] == expected_overall, 'Rendered overall table differs')
    expected_endpoints = []
    for g in PROFILES+('all',):
        for c, label, _, _, _ in STYLES:
            values = [individual[p, .75, c]['mean_delta']-individual[p, .25, c]['mean_delta'] for p in people[g]]
            value = 0. if abs(mean(values)) < 1e-9 else mean(values)
            expected_endpoints.append([title(g), label, f'{value:+,.2f}', ' / '.join(str(x) for x in sign_counts(values))])
            saved = next(r for r in exported['endpoints'] if r['profile'] == g and r['condition'] == c)
            check(close(saved['mean_075_minus_025'], value) and saved['participants'] == len(values)
                  and [saved[k] for k in ('better', 'same', 'worse')] == sign_counts(values), 'Wrong endpoint contrast')
    check(page.tables['endpoint-table'][1:] == expected_endpoints, 'Rendered endpoint table differs')
    check(len(page.tables) == 2, 'Missing/unexpected summary tables')
    check('intermediate values were not simulated' in html and 'no linear regression' in html, 'Missing interpolation qualification')
    check('combine the identical pairs' not in html, 'Old pair-collapsing narrative was retained')
    check(sha(root/'analysis.json') == audit['analysis_sha256'], 'Frozen analysis was changed')
    prior = read(root/'previous_policy_reference.json')
    check(all(sha(r['path']) == r['sha256'] for r in prior['files']), 'Prior outputs were changed')
    validation = {
        'validated_at_utc': datetime.now(timezone.utc).isoformat(), 'manifest_sha256': a['manifest_sha256'],
        'analysis_sha256': audit['analysis_sha256'], 'report_sha256': sha(root/'receptiveness_report.html'),
        'validated': True, 'plotly_figures': len(plots), 'cluster_trend_panels': 5, 'individual_trend_panels': 16,
        'heatmap_cells_checked': heat_cells, 'trend_points_checked': trend_points, 'conditions_per_trend': 4,
        'within_individual_uncertainty_and_repetition_tooltips_checked': True,
        'paired_contrast_cells_checked': 75, 'endpoint_contrasts_checked': 20, 'rendered_table_rows_checked': 32,
        'minimum_heatmap_label_contrast': min(contrast_ratios), 'all_actor_selector_targets_present': True,
        'self_contained_html': True, 'analysis_unchanged': True, 'previous_study_hashes_unchanged': True,
        'validator_sha256': sha(__file__),
        'native_preview': 'Not available in this session; chart data, annotations, encodings and offline structure verified programmatically.',
    }
    (root/'report_validation.json').write_text(json.dumps(validation, indent=2)+'\n')
    print(json.dumps(validation, indent=2))
    return validation


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    validate(parser.parse_args().directory)
