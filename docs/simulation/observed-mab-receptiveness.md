# MAB receptiveness with observed-behaviour personalisation

Launched on **15 November 2026** with eight workers, using
[`observed-mab-receptiveness.json`](observed-mab-receptiveness.json) and
[`observed-profile-mab-pilot.json`](observed-profile-mab-pilot.json).
The output directory is
`socratic_prototype/data/observed_mab_receptiveness_20261115/`.

Completed on **16 November 2026 at 18:23 CET**: all **144/144 jobs**, 720 fresh
comparison sessions and 144 fresh calibrations. There are no failed jobs.
The [interactive report](../../socratic_prototype/data/observed_mab_receptiveness_20261115/receptiveness_report.html)
is self-contained and can be opened locally without network access.

## Completed report

The report contains 33 figures: heatmaps at each receptiveness level, overall
and four-cluster trends, all 16 individual profile trends, paired personalisation
and assistance-style contrast heatmaps, and prompt-volume trends. Score plots
show paired differences from A, with C/E/D/F displayed separately. Straight
segments connect only the three tested receptiveness values; they are not fitted
regressions or estimates at intermediate values. Hover details include scores,
matched baselines, prompts and repetition-level differences.

Overall mean score differences from A (whose mean is 8,581.25 at every level):

| Receptiveness | C | E | D | F |
| --- | ---: | ---: | ---: | ---: |
| .25 | +208.33 | +18.75 | +106.25 | +70.83 |
| .50 | +435.42 | +372.92 | +141.67 | +29.17 |
| .75 | +531.25 | +410.42 | +339.58 | +70.83 |

Personalised E/F delivered fewer prompts but had lower overall mean rewards
than C/D respectively at all three levels. Effects vary across clusters and
individuals; the report shows both gains and harms. These are descriptive
synthetic results for 16 development actors, with three repetitions per actor,
not evidence of human benefit or population-level uncertainty. The remaining
46 evaluation actors are untouched.

The numerical audit replayed all **144,000 comparison trials**, including actor
choice distributions, keyed choice/outcome draws, scores and 11,315 active
response mixtures. It checked 144 fresh and 144 historical A comparisons,
all 144 actual calibration profiles and 96 cross-level calibration matches.
C/D also reproduce the preceding policy's generic sessions in all 288 comparisons.
C/E were identical in 61/144 pairs and D/F in 54/144 pairs when comparing the
complete recorded trajectory, probabilities, score, prompt count and omissions.
Other pairs differ in one or more of those fields.

Report validation independently checked 315 heatmap cells, 264 plotted trend
points, summary tables, shared scales and all 16 individual profile targets.
JavaScript syntax and profile navigation/resize handlers passed. Native browser
preview was unavailable; visual painting and browser timing were not checked.
The audit does not rerun full graph/SHACL inference or evaluate an LLM.

The frozen analysis SHA-256 is
`52f221878b03994321f42b469ac972e2079a44cb4918059c831b5ab30c2c2569`.
`report_audit.json`, `report_validation.json` and
`report_javascript_validation.json` record the checks. The frozen analysis,
runtime and earlier reports were not rewritten to produce this report.

To reproduce the audit and report using the installed environments:

```bash
PYTHONPATH=. SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
SOCRATIC_INTERPRET_RESPONSES=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
.venv/bin/python scripts/audit_observed_mab_report.py \
  --directory socratic_prototype/data/observed_mab_receptiveness_20261115

/Users/martinlopeznores/miniconda3/bin/python scripts/observed_mab_report.py \
  --directory socratic_prototype/data/observed_mab_receptiveness_20261115

.venv/bin/python scripts/validate_observed_mab_report.py \
  --directory socratic_prototype/data/observed_mab_receptiveness_20261115

/Users/martinlopeznores/.nvm/versions/node/v22.12.0/bin/node \
  scripts/validate_observed_report_js.cjs \
  socratic_prototype/data/observed_mab_receptiveness_20261115
```

The renderer uses the existing base environment's Plotly installation; no new
dependency was installed in the experiment environment.

## Matched design

- The same 16 development actors, with four in each original archetype.
  The remaining 46 evaluation actors are untouched.
- MAB only, full 200-trial calibration and 200 trials per comparison condition.
- Three matched repetitions and receptiveness .25, .5 and .75.
- Fresh A/C/E/D/F sessions at every level: 144 jobs, 720 comparison sessions,
  and 144 calibrations. This is 144,000 comparison trials plus 28,800 calibration trials.
- One task-owned response rule, with no `none` or `recent` factor.
- True response coefficients are identical across styles and actors at each
  receptiveness level. Additional reactance, distraction and omission are zero;
  existing actor/task behaviour is preserved.
- The seed is `reconsideration-development16-v1`, with the same keyed choice and
  environment streams as preceding studies. Conditions and receptiveness do not
  enter those random streams. Each comparison resets actor experience and assistant
  interaction history, and receives the same within-job calibration where permitted.

The primary outcome is total MAB score. Effects are paired changes from fresh A,
averaged across three repetitions within each actor before computing group means.
Repetitions and receptiveness levels do not create additional participants.
The four archetypes remain descriptive group labels, not assistant inputs.

## What changes

This tests [observed-behaviour personalisation](../observed_personalisation.md),
`policy-0.7` and `participant-model-0.2`. E/F learn uncertain task-choice forecasts
and separate style-specific uptake estimates from permitted public observations.
These estimates can affect delivery relevance, redundancy suppression and cooldowns.
C/D retain common delivery inputs. The public reward ranking and poor-performance
gate remain shared. The assistant never receives an actor's true response coefficients.

The simulator generates no helpfulness, disagreement or burden reports. This run
therefore tests task/choice-based adaptation, not invented reactions to wording
or self-reported burden. The actor still does not understand natural language.
All language is offline/bounded; Ollama variation is not another experimental factor.
Uptake estimates are conditional on the coarse task/processing model and are not
measurements of trust or causal assistance benefit.

No improvement or C/E–D/F separation is enforced. Results must retain C, E, D and
F separately, including coincident results or harms. The preceding report's
combined C/E and D/F curves must not be assumed valid for this experiment.

## Controls and provenance

Every comparison and calibration is rerun. Historical assisted outcomes are not
pooled. Before launch, 48 independent complete unassisted trajectories matched
all 144 historical A checks. Each new job must reproduce its audited A trajectory,
choice distribution and score before committing. New calibration profiles and
outcomes must agree across levels; a completed grid has 96 cross-level checks.

The preceding fair sweep's manifest, analysis and HTML report are retained with
read-only hash references in `previous_policy_reference.json`. Those results are
historical descriptive references. Comparisons of the new E/F against C/D within
the fresh grid are the current matched personalisation contrasts.

The frozen root manifest is
`b2bf393e337424da3b1d09b4bda5b07507634208a9c605493604dfab170e8f3c`.
Level manifests bind source/dependency hashes, actor inputs and configurations.
Leave the executable `socratic_prototype/` package and coordinator files unchanged
while the experiment is running. Each job has its own SQLite store, progress file
and evaluator report, with completed results committed atomically.

Eighteen targeted preflight tests passed. The initial planning estimate is
**18–30 hours**, based on the preceding eight-worker run and an allowance for
online-estimation overhead. A throughput estimate becomes available after complete
jobs; this initial range is not a measured completion forecast.

## Progress and resuming (retained run instructions)

The run is complete; no resume is needed. During execution, `status.json`
recorded coordinator PID, active workers, completed jobs, failures and throughput.
`analysis.json` / `analysis.md` updated after committed jobs.
The separately labelled `first_repetition` preview requires all five conditions
and all three receptiveness levels for each included actor. Primary actor averages
require all three repetitions as well.

```bash
tail -f socratic_prototype/data/observed_mab_receptiveness_20261115/sweep.log
```

The detached run uses `caffeinate -i`. To stop cleanly at job boundaries, create
`stop-after-jobs.json` in the output root. To resume, remove that stop request
after the previous coordinator/workers have exited, then run:

```bash
PYTHONPATH=. SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
SOCRATIC_INTERPRET_RESPONSES=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
caffeinate -i .venv/bin/python -u scripts/mab_fair_sweep.py \
  --output-dir socratic_prototype/data/observed_mab_receptiveness_20261115 \
  --workers 8
```

Resume checks the frozen implementation and committed hashes, preserves previous
attempts, and schedules missing jobs. Do not prepare a new manifest in this directory
or resume it after changing its frozen software.
