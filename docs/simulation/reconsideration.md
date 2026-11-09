# Reconsideration sensitivity pilot

This pilot varies **how** a synthetic participant processes a Socratic question,
separately from its configured receptiveness, reactance, distraction and omission.
These mechanisms are authored assumptions. The actor processes a structured issue,
not the natural-language meaning of the displayed question. No mechanism is chosen
because it improves scores or makes Socratic assistance look better.

## Three retained mechanisms

| CLI name | Processing assumption |
| --- | --- |
| `none` | Retain the baseline preference. Baseline learning continues. There is no strategic revision or directional reactance; distraction and omission costs still apply. |
| `current` | Use the existing task-owned reconsideration heuristic, unchanged. This remains the ordinary simulator default. |
| `recent` | Emphasise a fixed recent window of six **elapsed** trials. Missed trials consume window positions but do not become outcome evidence. |

In MAB, `current` weights exploration towards less-sampled arms for exploration
questions, and otherwise uses the existing public-outcome value heuristic.
`recent` applies the same issue-specific rule to just the six-trial window.
It changes the evidence considered rather than multiplying responsiveness.

In TBS, simply shortening history would leave `current` unchanged: that rule uses
the displayed pair and current goal/horizon. The `recent` alternative therefore
introduces an explicit perception bias. For each SAFE/RISKY option:

```text
perceived_probability = (4 * displayed_probability + recent_wins)
                        / (4 + recent_known_responses)
```

Only the current block and last six elapsed trials contribute. Unknown choices
and misses are excluded from these counts. Outcomes transfer across changing
offers of the same SAFE/RISKY identity; this is an assumption, not a statistically
justified update of an already displayed probability. The existing goal/horizon
rule then uses those perceived probabilities. Real offered probabilities, reward
draws, scores, deadlines and task transitions are unchanged. The window of six and
pseudo-count of four are fixed pilot choices, not fitted human parameters.

All rules use current public displays and previous observed outcomes. None can
inspect hidden probabilities, evaluator state, future outcomes or original neural
profile scores. The actor's own task parameters remain distinct from the assistant's
estimates. Direct advice targets its recommended option and never invokes a
Socratic processor.

## Ordinary simulator

The existing simulator now accepts `--reconsideration none|current|recent`:

```bash
.venv/bin/python -m socratic_prototype.simulation \
  --participants docs/simulation/participants.example.json \
  --scenario responsive --reconsideration recent --protocol short \
  --data-dir /tmp/reconsideration-example/sessions \
  --output /tmp/reconsideration-example/evaluator.json
```

The evaluator report records the mechanism, assumptions, processing target,
configured response coefficients and resulting probabilities. These fields do
not enter public sessions or assistant evidence. Under the null response scenario,
all five conditions still match. `none` matches A when distraction and additional
omission are zero; with costs enabled it can cause interference without revision.

New environments retain the original required simulation-adapter contract.
To support `recent`, an adapter adds `reconsider_recent(...)` and the descriptive
`RECENT_RECONSIDERATION` dictionary. Unsupported variants fail before any session
is created. The shared actor, policy and pilot have no MAB/TBS dispatch branches.

## Frozen development pilot

[`reconsideration-pilot.json`](reconsideration-pilot.json) specifies:

- The supplied development 16, four per original core profile.
- Full MAB 200 and TBS 192 protocols, with complete unassisted calibrations.
- All five conditions A/C/E/D/F under each of the three processing mechanisms.
- Responsiveness 0.5, reactance 0, distraction 0 and additional omission 0,
  identical across people, communication styles and processing mechanisms.
  These controlled assumptions override any response coefficients in actor exports;
  fitted task parameters and baseline omission rates remain individual.
- One initial repetition. MAB primary outcome is reward; TBS is targets attained
  divided by 24. Higher is better in each task; their units are not pooled.

This is 48 jobs, 480 comparison sessions and 96 calibration sessions. Each job is
one participant, mechanism and repetition. Calibration is regenerated within a
job using matching streams, so its numerical trajectories match across mechanisms.
The repeated stored calibrations are not additional people. A new repetition
draws a new calibration and comparison history; experience resets between conditions.

Freeze and inspect the specification without starting the long run:

```bash
.venv/bin/python -m socratic_prototype.pilot \
  --config docs/simulation/reconsideration-pilot.json \
  --output-dir socratic_prototype/data/reconsideration_pilot \
  --prepare-only
```

Run one job to benchmark the full protocol, then resume:

```bash
.venv/bin/python -m socratic_prototype.pilot \
  --output-dir socratic_prototype/data/reconsideration_pilot --max-jobs 1

.venv/bin/python -m socratic_prototype.pilot \
  --output-dir socratic_prototype/data/reconsideration_pilot
```

`status.json` is updated after every completed session. The runner locks its output
directory, skips verified completed jobs, and preserves interrupted attempts in
separate directories. An interrupted job restarts in a fresh attempt; it does not
pretend its partial protocol was complete. Only the verified completed attempt
enters analysis. Ctrl-C stops the current attempt; the same command resumes later.

`manifest.json` freezes configurations, actor inputs, package versions, relevant
source fingerprints, mechanisms and assumptions. Altering the frozen inputs or
execution implementation requires a new output directory. Complete job reports
are integrity-checked before reuse. The original empirical cohort is not refitted:
its existing actor export supplies frozen point estimates under the new recorded
execution code. Earlier cohort bundles and their historical validation reports
remain unchanged. Their strict empirical rebuild/export commands still require
their recorded implementation; a new empirical bundle is needed to refit/export
under changed code. Existing exported actors can be used directly for this pilot.

The runner uses offline reviewed language and disables response interpretation.
Mechanism names, condition IDs and job IDs never enter random streams. The
full pilot can be computationally expensive; benchmark a job before estimating
the total duration or increasing repetitions.

## Reports and interpretation

`analysis.json` and `analysis.md` are refreshed as jobs complete. They contain:

- Paired improvements from A, averaged within participants before cohort/profile
  summaries, with the declared metric direction and normalisation.
- Individual variation, participants worse than A, intervention counts and omissions.
- D/F effect ranges and sign reversals across mechanisms, retaining every variant.
- A/C/E trajectory and probability invariance across mechanisms. Null-response
  jobs additionally check D/F. With no extra costs, `none` D/F must match A.
- Per-person Monte Carlo standard errors only when at least two repetitions are
  available. With the initial one repetition these are null, not fabricated intervals.

An aggregate uses only completed protocols, matched mechanism sets and all
configured repetitions for the included person. A partial cohort report states
its actual number of people. Optional `max_trials` in a separate engineering
configuration caps comparisons; those runs produce diagnostics but no full-protocol
outcome estimates. Calibrations still complete normally.

The original profiles remain researcher-side grouping variables, not weak-task
labels or inferred AI attitudes. Neither sign consistency nor a positive score
difference establishes human benefit. The weak held-out TBS result, unknown offers,
point-estimate uncertainty and synthetic timing limitations remain in force.
Later stages can vary response coefficients independently and introduce more
elaborate processing mechanisms, with independent evaluation where possible.
