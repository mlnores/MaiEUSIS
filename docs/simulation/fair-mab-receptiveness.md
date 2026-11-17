# Fresh matched MAB receptiveness comparison

Prepared on **14 November 2026**, following the shared-ranking, performance-gate
and single-response revisions. This experiment compares receptiveness **0.25,
0.5 and 0.75** for MAB only. The configuration is
[`fair-mab-receptiveness.json`](fair-mab-receptiveness.json), using the
[single-response template](profile-response-pilot.json).

Completed on **15 November 2026 at 13:56 CET**, after approximately **14 hours**
with eight workers. All **144/144 jobs**, **144 fresh A checks**, **144 historical
A checks** and **96 cross-level calibration checks** passed.

## Completed report

The self-contained local report is
`socratic_prototype/data/fair_mab_receptiveness_20261114/receptiveness_report.html`.
It contains three group heatmaps (one per receptiveness value), five trend
panels (overall and four archetypes), a paired Socratic-minus-direct heatmap,
three expandable individual heatmaps, and paired 0.75-minus-0.25 tables.
Graphs show differences from A; A is not an additional plotted condition.

Overall mean changes from A, in MAB points:

| Receptiveness | C/E direct | D/F Socratic |
| ---: | ---: | ---: |
| 0.25 | +208.33 | +106.25 |
| 0.5 | +435.42 | +141.67 |
| 0.75 | +531.25 | +339.58 |

C/E and D/F have identical choice/outcome and probability trajectories in all
144 matched cases per pair, not merely identical group means. Trend plots
combine the coincident pairs and label this explicitly; heatmaps retain all
four conditions. This synthetic response model does not interpret personalised
wording, so these findings do not establish human personalisation effects.
Group responses include non-monotonicity and harms; the individual heatmaps and
paired contrasts retain them.

The independent report audit checked all **144,000 comparison-trial outcomes**,
**12,440 active response mixtures**, all **144 actual calibration records**,
**192 individual summaries** and **60 group summaries**. The HTML validator
checked **255 heatmap cells**, **30 combined-curve points**, **20 endpoint
contrasts**, **15 style-gap cells** and the rendered overall table. All inline
JavaScript parsed. Native Chrome preview was not approved and browser integration
was unavailable; validation covers numerical content, structure and syntax.
The original analyses and earlier reports remain unchanged.

Reproduce the audit, render using an interpreter with Plotly, then validate:

```bash
.venv/bin/python scripts/audit_mab_fair_report.py \
  --directory socratic_prototype/data/fair_mab_receptiveness_20261114
/Users/martinlopeznores/miniconda3/bin/python scripts/mab_fair_report.py \
  --directory socratic_prototype/data/fair_mab_receptiveness_20261114
.venv/bin/python scripts/validate_mab_fair_report.py \
  --directory socratic_prototype/data/fair_mab_receptiveness_20261114
```

The rendering command uses the existing local Plotly environment; it does not
change the prototype's frozen dependencies. Audit/validation records are saved
as `report_audit.json` and `report_validation.json`, with machine-readable paired
effects in `report_contrasts.json`.

## Fresh conditions and independent baseline audit

The old direct-assistance scores used policy 0.5. The new performance gate and
ranking also change C/E, so they cannot be the matched controls for new D/F.
Historical A is compatible mathematically, but we run A again as a same-version
control. No historical assisted score enters a new average.

The plan has **144 jobs**: 16 development actors × three repetitions × three
receptiveness values. Each job has a full 200-trial MAB calibration and five
fresh 200-trial condition sessions: **720 comparisons**, comprising **576
assisted sessions and 144 A controls**, plus **144 calibrations**. The reserved
46 evaluation actors remain outside development. Repetitions are not new people.

Before dispatch, the current actor and simulator independently reconstructed
**48 complete A trajectories** and matched all **144 historical A records**
across the three levels. Comparisons checked actor inputs, seeds, protocols,
trial counts, choice/outcome and distribution hashes, scores and omissions.
Historical manifests, job summaries and evaluator report hashes were verified
read-only and will be checked again on resumption and completion.

Every fresh A must match its independently audited expected trajectory before
a job can be committed. New calibration parameter/evidence and full feedback
hashes must agree across levels within an actor/repetition. Generated calibration
session IDs are normalised to trial numbers when comparing evidence.

The public shared ranking and performance gate apply to C/D/E/F. One response
rule is used. Receptiveness is fixed and identical across actors and styles;
reactance, distraction and additional omissions are zero. Individual baseline
omissions remain active. No condition, job ID or receptiveness value enters the
keyed environmental or choice random streams. All gains and harms are retained.

Primary summaries require all repetitions, conditions and levels for an actor;
repetitions are averaged within that actor before group means. A separately
labelled first-repetition preview requires all three levels for repetition zero.
Faster-finishing incomplete actors do not enter that preview.

This is a conditional simulation of structured guidance. The actor does not
understand or answer natural-language questions; scores cannot establish human
benefits attributable to Socratic dialogue itself.

## Execution and progress

[`mab_fair_sweep.py`](../../scripts/mab_fair_sweep.py) owns **one eight-worker
pool** across all levels, with one numerical-library thread per worker. It
interleaves profiles and levels, prioritising the first matched repetition.
Each attempt has its own SQLite store. Inherited root/level leases prevent a
second coordinator while old workers remain active. Completed results are
verified on resume; interrupted attempts are preserved.

The dataset is `socratic_prototype/data/fair_mab_receptiveness_20261114/`.
It contains `baseline_audit.json`, frozen manifests/configurations, `status.json`,
`sweep.log`, `analysis.json`, `analysis.md` and per-level `runs/r025`, `runs/r05`
and `runs/r075`.

Initial duration estimate: **12–20 hours of active execution**, based on the
preceding eight-worker full-MAB sweep, with allowance for the new graph checks.
Status estimates update from actual completions. Sleep/interruption extends
calendar time. The previous full-MAB worker peak RSS was 654 MiB median and
940 MiB maximum; the machine has eight detected CPU cores and 24 GiB RAM.

```bash
tail -f socratic_prototype/data/fair_mab_receptiveness_20261114/sweep.log
```

Stop dispatch after current jobs finish:

```bash
touch socratic_prototype/data/fair_mab_receptiveness_20261114/stop-after-jobs.json
```

After it stops, remove that request and resume the same frozen directory:

```bash
caffeinate -i .venv/bin/python -u scripts/mab_fair_sweep.py \
  --output-dir socratic_prototype/data/fair_mab_receptiveness_20261114 --workers 8
```

The configuration argument is needed only for a new directory. Runtime source,
configurations, reference audit and coordinator fingerprints are frozen. Source
changes, baseline/calibration mismatches, incomplete conditions or worker
failures stop dispatch and prevent completion being reported. Do not modify
runtime Python, policy, ontology or coordinator files while the run is active;
documentation and independent report rendering can be edited separately.

## Pre-launch verification

All six focused sweep tests passed: participant-level averaging/harms, complete
matching, baseline drift, cross-level calibration drift, incomplete conditions
and committed-metadata tampering. The real full-protocol calibration signature
parser also matched a saved actor/repetition across all three old levels.
Earlier single-response checks covered the actual MAB/TBS runner, serial/parallel
equivalence, persistence and replay. Historical reports remain untouched.

Launch validation confirmed eight active workers with fresh calibration feedback
in their SQLite stores. Five overlapping within-actor calibration-prefix pairs
matched across levels. Exact launch command, PIDs and checks are recorded in
`launch_request.json` and `launch_validation.json` in the dataset directory.
