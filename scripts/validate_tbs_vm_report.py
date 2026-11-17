#!/usr/bin/env python3
"""Check rendered TBS figures/tables/CSVs against trial-derived integer outcomes."""
import argparse
import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

from tbs_vm_report import PROFILES, LEVELS, CONDITIONS, LABELS, STYLES, CONTRASTS
from validate_observed_mab_report import Page


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def close(x, y):
    return math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-9)


def same(xs, ys):
    return len(xs) == len(ys) and all(close(x, y) for x, y in zip(xs, ys))


def signs(values):
    return [sum(v > 1e-10 for v in values), sum(abs(v) <= 1e-10 for v in values), sum(v < -1e-10 for v in values)]


def validate(root):
    root = Path(root).resolve()
    a, audit = read(root / 'report_data.json'), read(root / 'report_audit.json')
    check(audit['verified'] and sha(root / 'report_data.json') == audit['report_data_sha256'], 'Audited data changed')
    check(sha(root / 'source_analysis.json') == audit['analysis_sha256'], 'Source analysis changed')
    check(sha(root / 'report_trial_summaries.json') == audit['trial_summaries_sha256'], 'Trial summaries changed')
    raw = read(root / 'report_trial_summaries.json')['rows']
    index = {(r['participant'], r['repeat'], r['receptiveness'], r['condition']): r for r in raw}
    check(len(index) == len(raw) == 720, 'Wrong session grid')
    membership = {r['participant']: r['profile'] for r in a['individual_results']}
    people = {g: sorted(p for p, label in membership.items() if label == g) for g in PROFILES}
    people['all'] = sorted(membership)
    ordered = [p for g in PROFILES for p in people[g]]
    check(len(people['all']) == 16 and all(len(people[g]) == 4 for g in PROFILES), 'Wrong profile groups')
    short = lambda p: p.rsplit('_', 1)[-1]
    title = lambda g: ('All profiles' if g == 'all' else g) + f' (n={len(people[g])})'
    individual, group = {}, {}
    for p in people['all']:
        for rho in LEVELS:
            for c in CONDITIONS:
                selected = [index[p, r, rho, c] for r in range(3)]
                base = [index[p, r, rho, 'A'] for r in range(3)]
                changes = [x['targets_attained'] - y['targets_attained'] for x, y in zip(selected, base)]
                score = [x['score'] - y['score'] for x, y in zip(selected, base)]
                individual[p, rho, c] = {'net': sum(changes), 'pp': sum(changes) * 100 / 72,
                    'rate': sum(x['targets_attained'] for x in selected) * 100 / 72,
                    'baseline': sum(x['targets_attained'] for x in base) * 100 / 72,
                    'score': mean(score), 'score_mean': mean(x['score'] for x in selected),
                    'score_baseline': mean(x['score'] for x in base),
                    'prompts': mean(x['interventions'] for x in selected),
                    'se_pp': stdev([x * 100 / 24 for x in changes]) / math.sqrt(3),
                    'repeat_pp': ', '.join(f'{x*100/24:+.2f}' for x in changes)}
    for g in (*PROFILES, 'all'):
        for rho in LEVELS:
            for c in CONDITIONS:
                selected = [individual[p, rho, c] for p in people[g]]
                group[g, rho, c] = {'pp': mean(r['pp'] for r in selected), 'score': mean(r['score'] for r in selected),
                    'rate': mean(r['rate'] for r in selected), 'baseline': mean(r['baseline'] for r in selected),
                    'score_mean': mean(r['score_mean'] for r in selected), 'score_baseline': mean(r['score_baseline'] for r in selected),
                    'prompts': mean(r['prompts'] for r in selected), 'counts': signs([r['net'] for r in selected]),
                    'score_counts': signs([r['score'] for r in selected]), 'n': len(selected), 'net': sum(r['net'] for r in selected)}

    html = (root / 'receptiveness_report.html').read_text()
    page = Page()
    page.feed(html)
    metadata = read(root / 'report_figures.json')
    chart_specs = read(root / 'report_charts.json')
    check(len(metadata['figures']) == len(page.plot_divs) == 41 and
          page.plot_divs == [r['id'] for r in metadata['figures']], 'Missing figures or wrong order')
    check(len(page.ids) == len(set(page.ids)) and not page.dependencies, 'Duplicate IDs or external resources')
    check(sorted(page.options) == people['all'], 'Missing actor selector entries')
    check(all('card-' + p in page.ids for p in people['all']), 'Missing actor card')
    plots = {}
    decoder = json.JSONDecoder()
    for item in metadata['figures']:
        identifier = item['id']
        matches = list(re.finditer(r'Plotly\.newPlot\(\s*' + re.escape(json.dumps(identifier)) + r'\s*,\s*', html))
        check(len(matches) == 1, 'Missing or duplicate Plotly call: ' + identifier)
        data, end = decoder.raw_decode(html[matches[0].end():])
        rest = html[matches[0].end() + end:].lstrip()
        check(rest.startswith(','), 'Missing chart layout')
        layout, _ = decoder.raw_decode(rest[1:].lstrip())
        check(data == chart_specs[identifier]['data'] and layout == chart_specs[identifier]['layout'], 'HTML chart differs from saved specification')
        plots[identifier] = data, layout
    cells = points = 0
    contrast_ratios = []

    def luminance(channels):
        return sum((x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4) * w
                   for x, w in zip(channels, (.2126, .7152, .0722)))

    def rgb(value):
        return [float(x) / 255 for x in value[value.index('(') + 1:value.index(')')].split(',')]

    def heat(identifier, values, columns, labels, bound, score=False):
        nonlocal cells
        traces, layout = plots[identifier]
        check(len(traces) == 1 and traces[0]['type'] == 'heatmap', 'Wrong heatmap trace')
        t = traces[0]
        check(len(t['z']) == len(values) and all(same(x, y) for x, y in zip(t['z'], values)), 'Heatmap values differ from trials')
        check(t['x'] == list(columns) and t['y'] == list(labels), 'Wrong heatmap axes')
        check((t['zmin'], t['zmax'], t['zmid']) == (-bound, bound, 0), 'Wrong zero-centred scale')
        check(('score points' in t['colorbar']['title']['text']) if score else ('pp' in t['colorbar']['title']['text']), 'Wrong heatmap units')
        check(layout['yaxis']['autorange'] == 'reversed', 'Wrong row order')
        check(len(layout['annotations']) == sum(len(row) for row in values), 'Missing heatmap labels')
        for row, y in zip(values, labels):
            for value, x in zip(row, columns):
                check(abs(value) <= bound + 1e-9, 'Clipped heatmap cell')
                annotation = next(r for r in layout['annotations'] if r['x'] == x and r['y'] == y)
                v = 0. if abs(value) < 1e-10 else value
                check(annotation['text'] == f'{v:+,.2f}', 'Wrong cell label')
                position = (value + bound) / (2 * bound)
                lo, hi = next((lo, hi) for lo, hi in zip(t['colorscale'], t['colorscale'][1:]) if lo[0] <= position <= hi[0])
                weight = (position - lo[0]) / (hi[0] - lo[0])
                background = [x * (1 - weight) + y * weight for x, y in zip(rgb(lo[1]), rgb(hi[1]))]
                foreground = [1., 1., 1.] if annotation['font']['color'] == 'white' else [0., 0., 0.]
                low, high = sorted((luminance(background), luminance(foreground)))
                ratio = (high + .05) / (low + .05)
                check(ratio >= 4.5, 'Unreadable heatmap annotation')
                contrast_ratios.append(ratio)
                cells += 1

    def curve(identifier, lookup, bound, metric='pp', actor=False):
        nonlocal points
        traces, layout = plots[identifier]
        check(len(traces) == 4 and layout['yaxis']['range'] == bound and layout['xaxis']['tickvals'] == list(LEVELS), 'Wrong trend axes/series')
        check(layout['margin']['b'] >= 120 and layout['legend']['orientation'] == 'h', 'Insufficient legend space')
        for trace, (c, label, color, symbol, dash) in zip(traces, STYLES):
            selected = [lookup[rho, c] for rho in LEVELS]
            check(trace['type'] == 'scatter' and trace['mode'] == 'lines+markers' and trace['x'] == list(LEVELS) and
                  same(trace['y'], [r[metric] for r in selected]), 'Wrong trend values')
            check(trace['name'] == label and trace['line']['color'] == color and trace['line']['dash'] == dash and
                  trace['marker']['symbol'] == symbol, 'Inconsistent condition style')
            for hover, r in zip(trace['customdata'], selected):
                if actor:
                    check(same(hover[:4], [r['rate'], r['baseline'], r['prompts'], r['se_pp']]) and
                          hover[4] == r['repeat_pp'] and hover[5] == r['net'], 'Wrong actor tooltip units/data')
                else:
                    check(hover == [*(r['score_counts'] if metric == 'score' else r['counts']), r['n']], 'Wrong group gain/tie/loss tooltip')
            check(all(bound[0] <= value <= bound[1] for value in trace['y']), 'Clipped trend values')
            points += len(trace['x'])

    for rho in LEVELS:
        heat('cluster-heat-r' + str(rho).replace('.', ''), [[group[g, rho, c]['pp'] for c in CONDITIONS] for g in PROFILES],
             LABELS, [title(g) for g in PROFILES], metadata['group_scale_pp'])
        heat('individual-heat-r' + str(rho).replace('.', ''), [[individual[p, rho, c]['pp'] for c in CONDITIONS] for p in ordered],
             LABELS, [membership[p] + ' · ' + short(p) for p in ordered], metadata['individual_scale_pp'])
        heat('score-heat-r' + str(rho).replace('.', ''), [[group[g, rho, c]['score'] for c in CONDITIONS] for g in PROFILES],
             LABELS, [title(g) for g in PROFILES], metadata['score_scale_points'], score=True)
    for g in ('all',) + PROFILES:
        lookup = {(rho, c): group[g, rho, c] for rho in LEVELS for c in CONDITIONS}
        curve('cluster-trend-' + g.lower(), lookup, metadata['group_trend_range_pp'])
        curve('score-trend-' + g.lower(), lookup, metadata['score_trend_range_points'], metric='score')
    for p in ordered:
        curve('individual-trend-' + short(p).lower(), {(rho, c): individual[p, rho, c] for rho in LEVELS for c in CONDITIONS},
              metadata['individual_trend_range_pp'], actor=True)
    curve('prompt-trend-all', {(rho, c): group['all', rho, c] for rho in LEVELS for c in CONDITIONS}, metadata['prompt_range'], metric='prompts')
    comparisons = read(root / 'report_contrasts.json')
    check(len(comparisons['contrasts']) == 75 and len(comparisons['individual_contrasts']) == 240 and
          len(comparisons['endpoints']) == 20, 'Wrong contrast grids')
    for key, _, weights in CONTRASTS:
        values = []
        for g in (*PROFILES, 'all'):
            row = []
            for rho in LEVELS:
                net = [sum(w * individual[p, rho, c]['net'] for c, w in weights.items()) for p in people[g]]
                value = mean(net) * 100 / 72
                saved = next(r for r in comparisons['contrasts'] if (r['contrast'], r['profile'], r['receptiveness']) == (key, g, rho))
                check(close(saved['mean_delta_pp'], value) and [saved[k] for k in ('better', 'same', 'worse')] == signs(net), 'Wrong paired contrast')
                row.append(value)
            values.append(row)
        heat('contrast-' + key + '-plot', values, [f'{rho:g}' for rho in LEVELS],
             [title(g) for g in (*PROFILES, 'all')], metadata['contrast_scale_pp'])
    expected_primary, expected_score, expected_endpoint = [], [], []
    for rho in LEVELS:
        for c, label, _, _, _ in STYLES:
            r = group['all', rho, c]
            expected_primary.append([f'{rho:g}', label, f'{r["rate"]:.2f}%', f'{r["pp"]:+.2f}', f'{r["net"]:+d}',
                                     ' / '.join(map(str, r['counts'])), f'{r["prompts"]:.2f}'])
            expected_score.append([f'{rho:g}', label, f'{r["score_mean"]:,.2f}', f'{r["score_baseline"]:,.2f}', f'{r["score"]:+,.2f}'])
    for g in (*PROFILES, 'all'):
        for c in CONDITIONS:
            net = [individual[p, .75, c]['net'] - individual[p, .25, c]['net'] for p in people[g]]
            expected_endpoint.append([title(g), LABELS[CONDITIONS.index(c)], f'{mean(net)*100/72:+.2f}', ' / '.join(map(str, signs(net)))])
    check(page.tables['overall-table'][1:] == expected_primary, 'Primary table differs')
    check(page.tables['score-table'][1:] == expected_score, 'Secondary table differs')
    check(page.tables['endpoint-table'][1:] == expected_endpoint, 'Endpoint table differs')
    check(set(page.tables) == {'overall-table', 'score-table', 'endpoint-table'}, 'Unexpected/missing tables')
    check(cells == metadata['heatmap_cells'] == 363 and points == metadata['trend_points'] == 324, 'Wrong plotted-value count')
    check('intermediate values were not simulated' in html and 'no linear regression' in html and
          '13 of the 192' in html and 'percentage points' in html and 'multiplied score points' in html, 'Missing interpretation/unit qualifications')
    check(all(group['all', rho, 'C']['pp'] == max(group['all', rho, c]['pp'] for c in CONDITIONS) for rho in LEVELS), 'Summary winner differs')
    check(all(group['all', rho, p]['pp'] < group['all', rho, g]['pp'] for rho in LEVELS for g, p in (('C', 'E'), ('D', 'F'))), 'Summary personalisation conclusion differs')
    csv_sizes = {}
    for name, count in (('group_results.csv', 60), ('individual_results.csv', 192), ('paired_contrasts.csv', 75),
                        ('individual_contrasts.csv', 240), ('session_results.csv', 720), ('job_runtime.csv', 144),
                        ('tie_corrections.csv', 13)):
        with (root / name).open(newline='') as handle:
            csv_rows = list(csv.DictReader(handle))
        check(len(csv_rows) == count, 'CSV row count differs: ' + name)
        csv_sizes[name] = count
        for r in csv_rows:
            if name in ('group_results.csv', 'individual_results.csv'):
                key = (r['profile'] if name.startswith('group') else r['participant'], float(r['receptiveness']), r['condition'])
                expected = group[key] if name.startswith('group') else individual[key]
                check(close(float(r['mean_delta_pp']), expected['pp']) and close(float(r['mean_score_delta']), expected['score']) and
                      close(float(r['mean_interventions']), expected['prompts']), 'CSV units/values differ: ' + name)
                if name.startswith('group'):
                    check([int(r[k]) for k in ('better', 'same', 'worse')] == expected['counts'], 'CSV tie counts differ')
                else:
                    check(int(r['net_target_difference_total']) == expected['net'], 'CSV integer target differences differ')
            elif name == 'session_results.csv':
                expected = index[r['participant'], int(r['repeat']), float(r['receptiveness']), r['condition']]
                for field in ('targets_attained', 'target_rate', 'score', 'interventions', 'omissions'):
                    check(close(float(r[field]), expected[field]), 'Session CSV differs: ' + field)
            elif name in ('paired_contrasts.csv', 'individual_contrasts.csv'):
                weights = next(w for key, _, w in CONTRASTS if key == r['contrast'])
                persons = people[r['profile']] if name == 'paired_contrasts.csv' else [r['participant']]
                rho = float(r['receptiveness'])
                values = [sum(w * individual[p, rho, c]['net'] for c, w in weights.items()) for p in persons]
                check(close(float(r['mean_delta_pp']), mean(values) * 100 / 72), 'Contrast CSV primary units differ')
                if name == 'paired_contrasts.csv':
                    check([int(r[k]) for k in ('better', 'same', 'worse')] == signs(values), 'Contrast CSV sign counts differ')
            elif name == 'tie_corrections.csv':
                expected = individual[r['participant'], float(r['receptiveness']), r['condition']]
                check(expected['net'] == 0 and r['report_classification'] == 'same' and int(r['exact_net_target_difference']) == 0,
                      'Tie correction does not correspond to an integer tie')
    result = {'validated_at_utc': datetime.now(timezone.utc).isoformat(), 'validated': True,
        'manifest_sha256': a['manifest_sha256'], 'report_sha256': sha(root / 'receptiveness_report.html'),
        'plotly_figures': len(plots), 'heatmap_cells_checked': cells, 'trend_points_checked': points,
        'paired_contrast_cells_checked': 75, 'individual_actor_panels': 16, 'conditions_per_trend': 4,
        'rendered_table_rows_checked': 44, 'minimum_heatmap_label_contrast': min(contrast_ratios),
        'csv_row_counts': csv_sizes, 'csv_primary_values_and_tie_counts_verified': True, 'primary_secondary_units_separate': True,
        'exact_integer_tie_counts_checked': True, 'all_actor_selector_targets_present': True,
        'self_contained_html': True, 'original_analysis_unchanged': sha(root / 'source_analysis.json') == audit['analysis_sha256'],
        'validator_sha256': sha(__file__),
        'native_preview': 'Blocked: Computer Use was not approved to use Google Chrome. Chart data, labels, contrast, HTML structure and JavaScript controls are checked programmatically.'}
    (root / 'report_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    validate(parser.parse_args().directory)
