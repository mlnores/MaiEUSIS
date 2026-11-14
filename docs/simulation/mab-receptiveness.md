# MAB receptiveness sensitivity experiment

Requested on **13 November 2026**. This experiment varies the synthetic actor's
fixed `responsiveness` coefficient over **0.25, 0.5 and 0.75**, for MAB only.
The coefficient mixes baseline preferences with a recommendation/reconsideration
target. It is not an estimated human attitude or the probability of obeying a
question.

Launched on **13 November 2026** and completed on **14 November 2026** in
`socratic_prototype/data/mab_receptiveness_20261113`, using eight workers.
All **291/291 new jobs** finished, the full-protocol bridge passed its **15
comparison and three calibration checks**, and all **1,008 matched controls**
passed (432 across mechanisms, 288 no-revision and 288 across-level baselines).
All 16 actors have complete matched results at all three levels.

## Matched design

- The same 16 development actors, four per original archetype, with their
  individually fitted parameters unchanged. The 46 evaluation actors remain
  outside prototype development.
- Full MAB 200-trial protocols and full MAB calibration. No new TBS sessions.
- Conditions A/C/E/D/F and all three mechanisms `none/current/recent` at every
  receptiveness level. Three matched repetitions per actor.
- The coefficient applies equally to direct and Socratic support and every
  actor. Reactance, distraction and additional AI omission are zero; individual
  baseline omission rates remain active. It stays fixed within each run.
- Identical keyed random streams across levels: the same base seed as the
  completed guided pilot, with no receptiveness value entering the random keys.
  Experience resets between conditions. A is checked to have identical
  choice/outcome and distribution trajectories across levels.

The scientific comparison has **2,160 MAB condition sessions**: 16 actors ×
3 repetitions × 3 mechanisms × 3 receptiveness levels × 5 conditions. Repetitions
and mechanisms are not additional people.

## Reusing the completed 0.5 reference

The MAB portion of the completed `guidance_pilot_20261111` supplies the 0.5
reference: 144 verified job records containing 720 MAB comparisons. Its TBS
outcomes are excluded. Reference actor/configuration/report hashes are frozen
in the new sweep manifest and verified again at the end.

The previous study required calibration in both tasks. MAB personalisation reads
only its MAB calibration profile; the new study declares MAB-only calibration.
To verify equivalence, three additional full-protocol 0.5 runs for E004, one per
mechanism, compare all five MAB outcome/distribution trajectories, intervention
counts, calibration parameters and actual calibration feedback against the old
records. Evidence references are compared by trial number because the separate
sessions have different generated IDs. The 0.5 reference enters comparative
averages only after this bridge passes. A mismatch stops further dispatch.

These bridge jobs are validation, not extra observations in the analysis. The
new execution therefore has **291 jobs**: 144 at 0.25, 144 at 0.75 and three
bridge jobs. The 0.5 comparisons are reused rather than recomputed for everyone.
Neither completed pilot nor the cohort bundle is rewritten.

The short engineering bridge passed all 15 MAB comparisons and three calibration
profile/history checks. A separate nine-job capped engineering sweep exercised
eight concurrent workers, all 21 available internal/baseline controls, resumption
and the bridge. Capped comparisons produced no full-protocol outcome estimates.
Three focused analysis tests cover actor-level repetition averaging,
matched-sample exclusion and failing closed on random-baseline drift.

## One eight-worker process pool

The [sweep coordinator](../../scripts/mab_receptiveness_sweep.py) owns one bounded
pool across all new levels and bridge checks. It does not start an eight-worker
pool for each level. On the current machine, eight workers use all eight detected
CPU cores, each with numerical-library thread pools limited to one. The machine
has 24 GiB of memory; the capped engineering workers peaked at about 312 MiB each.
The completed sweep recorded about **24.3 hours** of coordinator execution.

Each worker has a separate SQLite attempt database. The parent holds the sweep
and per-level runner leases, which workers inherit. Completed reports are
verified and reused on resume; interrupted attempts are retained. One coordinator
owns the aggregate status and analysis outputs.

The frozen [sweep specification](mab-receptiveness.json) points to separate
[0.25](mab-receptiveness-025.json), [0.75](mab-receptiveness-075.json) and
[0.5 bridge](mab-receptiveness-050-bridge.json) configurations.

```bash
caffeinate -i .venv/bin/python -u scripts/mab_receptiveness_sweep.py \
  --config docs/simulation/mab-receptiveness.json \
  --output-dir socratic_prototype/data/mab_receptiveness_20261113 \
  --workers 8
```

The background launch records its exact command, interpreter, manifest and
process ID in the local output. Progress is in `status.json` and `sweep.log`:

```bash
tail -f socratic_prototype/data/mab_receptiveness_20261113/sweep.log
```

To stop dispatch after current jobs finish:

```bash
touch socratic_prototype/data/mab_receptiveness_20261113/stop-after-jobs.json
```

After it stops, remove that request and resume the same directory with the launch
command (the config argument can be omitted). To generate the final HTML
automatically, the launch additionally supplies `--report-python` with a Python
interpreter having Plotly installed. The local launch uses the existing base
environment, without changing the prototype's frozen dependencies.

Avoid changing runtime Python/JSON/ontology files or either scheduler while the
sweep runs. No refits or task-mechanics changes are part of this experiment.

## Analysis and report

Primary summaries include an actor only when all configured repetitions,
mechanisms and receptiveness levels are matched and complete. Repetitions are
averaged within that actor before group means. A separately labelled
`first_repetition` preview in `analysis.json` uses the same complete-matching rule
for repetition zero only. Group sample sizes are stated explicitly.

The [report renderer](../../scripts/mab_receptiveness_report.py) produces
`receptiveness_report.html` after completion: one common-scale heatmap per
receptiveness value (archetype rows and support columns), trend plots for each
archetype and all actors, and paired 0.75-minus-0.25 effects with actor-level
better/same/worse counts. Trend plots share the same vertical scale, colours and
marker shapes; dashed D/F lines denote recent processing. Source data are in
`analysis.json`; tables are in `analysis.md` and
`receptiveness_contrasts.json`. The graphs use changes from A, without an A column.
The report can also be generated manually in a Python environment with Plotly:

```bash
python scripts/mab_receptiveness_report.py \
  --directory socratic_prototype/data/mab_receptiveness_20261113
```

The local report is at
`socratic_prototype/data/mab_receptiveness_20261113/receptiveness_report.html`.
It embeds Plotly and works without network access. Regenerating it does not
rewrite the scientific analysis or run more simulations.

Higher responsiveness is not assumed to improve performance. The analysis keeps
negative effects, non-monotonic patterns and every processing mechanism. These
remain conditional model sensitivity results, not human receptiveness estimates
or evidence that a profile has a particular attitude toward assistance.

## Initial duration estimate

Recent completed jobs spent about 24.9 minutes in their MAB calibration and MAB
comparison sessions at four-worker concurrency. At that same per-job duration,
291 jobs on eight workers would require about 15.1 hours. Eight workers share
CPU and memory resources, so an initial planning range is **18–30 hours of active
execution**. This is provisional; `status.json` estimates remaining time from
actual completions. Sleep or interruptions extend calendar time.
