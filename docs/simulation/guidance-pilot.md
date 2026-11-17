# Full-protocol pilot of guided Socratic comparisons

> Historical experiment: new runs use the [single-response design](single-response.md).
> The former `none`/`recent` configurations require their recorded runtime.

The [configuration](guidance-pilot.json) assesses the
[new comparison guidance](../socratic_guidance.md) on the development 16. Its
separate output directory is
`socratic_prototype/data/guidance_pilot_20261111`. The completed earlier pilot in
`reconsideration_pilot_20261106` remains unchanged. This is a conditional synthetic
experiment, not evidence of human assistance effects.

Launched on **11 November 2026** and completed on **13 November 2026** with all
**144 jobs, 1,440 comparison sessions and 288 calibration sessions**. All 288
A/C/E cross-mechanism controls and 192 no-revision controls passed. The
[final heatmap report](#final-heatmap-report) averages three repetitions within
each actor before the group means; the four archetypes each retain four actors.

## Fixed design

- Sixteen existing development actor exports, four per original profile; no refit
  and no selection against the 46 evaluation individuals.
- Full MAB 200-trial and TBS 192-trial protocols, with complete unassisted
  calibrations in both tasks for every job.
- All five conditions A/C/E/D/F and all three mechanisms `none/current/recent`.
- **Three matched repetitions**, giving 144 jobs, 1,440 comparison sessions and
  288 stored calibration sessions. Repetitions are repeated simulations of the
  same people, not additional independent participants.
- Responsiveness 0.5 for every individual, task, communication style and mechanism;
  reactance, distraction and additional AI omission remain zero. Individual
  baseline omissions remain in force. Responsiveness 1 is a separate possible
  sensitivity experiment, not another factor silently introduced here.
- Same base seed as the earlier pilot: repetition zero aligns its random streams
  with the previous run, while repetitions one and two draw new keyed streams.
  Within a repetition, conditions/mechanisms share the same streams; neither
  condition IDs nor mechanism names enter the random keys. The old/new A/C/E
  trajectories should be checked when complete reports become available.
- Reviewed offline language, with response interpretation disabled. The guide's
  structured evidence and actor processing are the experimental change; LLM
  wording variation is not introduced.
- MAB primary outcome is score; TBS is targets attained divided by 24. Experience
  resets between conditions. Calibration is regenerated with matching streams
  across mechanisms and new observations across repetitions.

The existing runner freezes actor inputs, configurations, source fingerprints and
dependencies. It preserves interrupted attempts and skips verified completed jobs
on resume. Avoid modifying runtime Python, JSON or ontology/rule files during the
run. Changes require a new frozen run rather than a revised manifest.

## Analysis

The runner checks A/C/E invariance across mechanisms and `none` D/F equivalence to
A when the specified extra costs are zero. Paired changes from A are averaged
within individuals before overall/profile summaries. All mechanisms are retained.
Three repetitions allow descriptive per-person Monte Carlo standard errors;
they do not capture uncertainty in the fitted actors or human response models.
Matched outcome estimates for a person become available only when all their
configured repetitions and mechanisms are complete.

In addition to the primary outcomes, inspect individual harms, sign reversals,
intervention frequencies and whether personalised versus generic TBS assistance
actually differs. The new public comparison panel does not itself guarantee a
personalisation contrast. Retain the provisional TBS actor's negative held-out
prediction result and missing historical offers as interpretation limits.

## Launch, monitor and resume

For a new empty output directory:

```bash
caffeinate -i .venv/bin/python -u -m socratic_prototype.pilot \
  --config docs/simulation/guidance-pilot.json \
  --output-dir socratic_prototype/data/guidance_pilot_20261111
```

Once launched, do not start a second runner for this output directory. The
background launch records its process information in local `launch.json`, and
progress goes to `pilot.log`:

```bash
tail -f socratic_prototype/data/guidance_pilot_20261111/pilot.log
```

`status.json` records the current job, Python PID and latest completed session;
`analysis.json`/`analysis.md` refresh as jobs finish. A job has two calibrations
and ten comparisons, so the job count can remain unchanged while sessions run.
If the process has stopped, resume the same frozen run:

```bash
caffeinate -i .venv/bin/python -u -m socratic_prototype.pilot \
  --output-dir socratic_prototype/data/guidance_pilot_20261111 \
  2>&1 | tee -a socratic_prototype/data/guidance_pilot_20261111/pilot.log
```

Completed jobs are reused; an interrupted job restarts in a preserved new attempt.
`caffeinate -i` prevents idle sleep while its child runs, but does not ensure
progress through manual sleep, closing the lid, shutdown or process termination.

## Preliminary duration estimate

This section records the initial sequential planning estimate. The run subsequently
completed using the parallel scheduler; recorded launch/status metadata contain
its actual timing and throughput.

The earlier full-protocol pilot used 94,954 seconds, or **26.38 hours**, across
48 completed jobs: about 33 minutes per job. At that rate, 144 jobs would need
**79.13 hours** before allowing for the new guidance's extra graph/validation
work and machine-load differences. An initial planning range is **72–120 hours
(three to five days) of uninterrupted execution**. This is not a measured duration
for the new full protocol; update it after the first complete jobs. The short
engineering check is unsuitable for linear extrapolation because history and
stored graph costs grow during the full protocol.

## Parallel execution

The separate [process scheduler](../../scripts/pilot_parallel.py) runs independent
jobs concurrently without modifying the fingerprinted simulation package. The
original sequential runner remains available. A coordinator holds the same
exclusive output-directory lock, dispatches at most the requested number of
subprocesses, and owns shared status and analysis updates. Each worker writes its
own attempt database and evaluator report. Workers inherit the directory lease,
so an abruptly terminated coordinator cannot permit a second runner to start
while its surviving children still write. Numerical-library thread counts are
limited to one per worker to avoid nested CPU pools.

For an existing, **stopped** frozen run:

```bash
caffeinate -i .venv/bin/python -u scripts/pilot_parallel.py \
  --output-dir socratic_prototype/data/guidance_pilot_20261111 \
  --workers 4 \
  2>&1 | tee -a socratic_prototype/data/guidance_pilot_20261111/pilot.log
```

For a new run, supply `--config docs/simulation/guidance-pilot.json` and a new
empty output directory. Existing completed jobs are verified and reused in place;
an unfinished job gets a new attempt, preserving the earlier one. Manifest,
actor inputs, seeds, response parameters, mechanisms and the primary analysis
remain unchanged. Scheduler version/hash and numerical thread settings are
recorded separately in launch and worker metadata.

Jobs are ordered by repetition, then by individuals interleaved across the
original profiles, retaining all three mechanisms for each. This makes the first
matched repetition across the cohort available sooner. Scheduling order never
enters the keyed random streams. `first_repetition.json` and
`first_repetition.md` provide a **separate, preliminary** view restricted to full
protocols and individuals with all three mechanisms in repetition zero. This
view has one repetition per person and no Monte Carlo standard errors. It does
not relax the primary analysis's requirement for all three repetitions, add
participants, or replace `analysis.json`/`analysis.md`.

During parallel execution, `status.json` lists `active_jobs` with their worker
PIDs, attempt paths and latest completed sessions. Per-attempt `progress.json`
and `worker.log` provide details. Aggregate throughput and remaining-time
estimates become available as new jobs complete; initial estimates include
worker startup and are provisional. Four workers have an ideal remaining time
of roughly one quarter of the sequential estimate, but actual speedup must be
measured on full jobs because they share CPU, memory and disk resources.

The scheduler checks passed on 12 November 2026: eight scheduling, lease,
handover, failure and graceful-stop tests; a real MAB/TBS equivalence integration
test; and the three original pilot regression tests. The integration check used
complete short calibrations and comparisons capped at eight trials, retaining
all mechanisms. One completed job was reused and two were run concurrently.
All 240 trial records matched the sequential choices, outcomes and baseline/
assisted distributions, including 18 guided decisions; six F sessions replayed
exactly. Reused result bytes and interrupted attempts were preserved, and capped
jobs produced no full-protocol outcome estimates. Three sequential engineering
jobs took 162.3 seconds; the two remaining jobs together took 58.7 seconds in
parallel. These unequal job counts and short histories do not establish a
four-worker full-protocol speedup.

For a handover from an active sequential runner, add `--handover-pid PID`. The
coordinator waits for that runner's current job result to be committed, requests
SIGINT, and waits for the original exclusive lock to be released before starting
workers. A small part of the next job may already have begun; that attempt is
retained. If local tool permissions deny the signal, `handover.json` records
`manual_signal_required` and the exact `kill -INT PID` command for the user's
Terminal. The waiting coordinator starts automatically after the original runner
exits. It never alters a source fingerprint or bypasses the directory lock.

To stop parallel dispatch **after active jobs finish**, create a request file:

```bash
touch socratic_prototype/data/guidance_pilot_20261111/parallel-stop.json
```

After it stops, remove that request before resuming with the same command:

```bash
rm socratic_prototype/data/guidance_pilot_20261111/parallel-stop.json
```

Changing worker count on resume changes execution capacity only. Do not modify
the frozen simulation package, actor inputs, pilot configuration or scheduler
while workers are running. Worker failures stop new dispatch, allow other active
jobs to finish, and retain the failed attempt for inspection before resuming.

Generated output and process metadata are private local artifacts ignored by
Git. This tracked configuration and note document the design and interpretation.

## Final heatmap report

The verified final report was generated on **13 November 2026** in
`socratic_prototype/data/guidance_profiles_20261113/`. It contains six heatmaps:
MAB/TBS group differences from A, individual differences from A and
personalisation contrasts. Individual hover details include all three repetition
effects and their Monte Carlo standard error. All 264 plotted cells, 384 actor
means/standard errors and 120 group/overall summaries were independently checked
against the completed records. The earlier report remains unchanged.

Mean changes from A across all 16 actors are:

| Support | MAB points | TBS percentage points |
| --- | ---: | ---: |
| C, task-aware direct | +583.33 | +3.65 |
| E, personalised direct | +570.83 | +3.65 |
| D, current Socratic | +170.83 | +0.52 |
| F, current personalised Socratic | +206.25 | +0.52 |
| D, recent Socratic | +250.00 | +0.69 |
| F, recent personalised Socratic | +377.08 | +0.69 |

All mechanisms remain in the analysis. With `none`, D/F reproduce A exactly.
All 288 audited TBS personalisation pairs have identical outcome and probability
trajectories. The fuller intervention-selection audit remains separate; these
results do not establish an effective TBS personalisation contrast.

The report uses exact recorded score/target numerators for paired means and ties.
Some target changes cancel across repetitions but left tiny signed floating-point
residuals in the source cached summary. The derived report treats those as exact
ties and records the corrections in `analysis.json`, including eight affected
aggregate harm-count cells. Source pilot summaries and manifests are preserved.
`validation.json` records the checks and the unavailable browser visual preview.

The separate [final report builder](../../scripts/final_pilot_report.py) requires
the pilot and its cached analysis to be complete with passing controls. It can
wait for an active runner, but never labels partial results as final or modifies
the source pilot. Run it in a Python environment with Plotly installed:

```bash
python scripts/final_pilot_report.py \
  --pilot-dir socratic_prototype/data/guidance_pilot_20261111 \
  --output-dir socratic_prototype/data/guidance_profiles_20261113 \
  --title 'Guided pilot: final three-repetition results' \
  --wait-seconds 1800
```

The local build uses the existing base-environment Plotly installation, leaving
the frozen prototype environment unchanged. Outputs are `profile_effects.html`,
`report.md` and `analysis.json`, separate from the earlier one-repetition report.
The self-contained HTML contains group and individual differences from A,
personalisation contrasts, absolute outcome tables, individual repetition changes
and Monte Carlo standard errors. A is retained as the comparison reference but
has no heatmap column. Each archetype still has four actors; averaging three
repetitions does not increase that count to twelve.

Before generating the report, the builder verifies all completed evaluator
hashes, recomputes trial/outcome summaries and matched controls, reconciles the
cached actor/group effects, and independently checks the per-actor Monte Carlo
standard errors. These errors describe simulation variability under fixed model
assumptions, rather than uncertainty about human effects or fitted parameters.
