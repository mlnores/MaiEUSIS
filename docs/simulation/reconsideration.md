# Reconsideration sensitivity pilot

> Historical experiment: new runs use the [single-response design](single-response.md).
> The former `none`/`recent` configurations require their recorded runtime.

This pilot varies **how** a synthetic participant processes a Socratic question,
separately from its configured receptiveness, reactance, distraction and omission.
These mechanisms are authored assumptions. The actor processes a structured issue,
not the natural-language meaning of the displayed question. No mechanism is chosen
because it improves scores or makes Socratic assistance look better.

**11 November implementation update:** new interventions use
[evidence-backed comparison sets](../socratic_guidance.md), with execution
adapters 0.4. `current` and `recent` now reassess those delivered alternatives;
MAB exploration combines reward plausibility and uncertainty. The completed
initial pilot below used adapters 0.3 and the earlier rules documented in this
section. Its frozen results are unchanged and do not evaluate the new guidance.
An additional run must use a new output directory and recorded configuration.

## Three retained mechanisms

| CLI name | Processing assumption |
| --- | --- |
| `none` | Retain the baseline preference. Baseline learning continues. There is no strategic revision or directional reactance; distraction and omission costs still apply. |
| `current` | Use the task-owned reconsideration heuristic; new interventions reassess the graph-backed comparison set. This remains the ordinary simulator default. |
| `recent` | Emphasise a fixed recent window of six **elapsed** trials. Missed trials consume window positions but do not become outcome evidence. |

In the initial pilot's MAB implementation, `current` weighted exploration towards less-sampled arms for exploration
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

## Completed development pilot

Status verified on **10 November 2026**. The initial full-protocol run completed
all **48 jobs, 480 comparison sessions and 96 calibration sessions** for the 16
development individuals, four per original profile. All 96 A/C/E cross-mechanism
trajectory/distribution checks and 64 `none` D/F-versus-A checks passed. Completed
job summaries and full evaluator reports passed their recorded integrity checks;
all 120 overall/profile aggregate means and worse-than-A counts were independently
checked against the job summaries. The interrupted job's completed second attempt
enters analysis; its preserved partial first attempt does not.

Mean unassisted performance was 8,687.5 MAB points and 66.67% of TBS targets
attained. The following are mean paired changes from A. TBS changes are
**percentage points**, not relative percentages; MAB and TBS units are not pooled.

| Condition | MAB `current` (points) | MAB `recent` (points) | TBS `current` (percentage points) | TBS `recent` (percentage points) |
| --- | ---: | ---: | ---: | ---: |
| C: task-aware direct recommendations | +956.25 | +956.25 | +4.43 | +4.43 |
| E: personalised direct recommendations | +1,275.00 | +1,275.00 | +4.43 | +4.43 |
| D: task-aware Socratic questions | +350.00 | +231.25 | +0.52 | +0.52 |
| F: personalised Socratic questions | +81.25 | −156.25 | +0.52 | +0.52 |

With `none`, D/F matched A exactly in both tasks. C/E were invariant across all
three mechanisms. Holding response coefficients equal therefore did not force
the two assistance styles to have the same results.

Individual differences and the mechanism contrast matter:

- Personalised direct recommendations increased MAB scores for 14 individuals
  and reduced them for two. Personalised Socratic questions reduced MAB scores
  for nine individuals under `current`, and eight under `recent`.
- Switching between `current` and `recent` reversed the sign of the MAB effect
  for five individuals in D and five in F. The F cohort mean also changed sign.
- In TBS, C/E had identical intervention timings, issues, choice distributions
  and choice/outcome trajectories for all 16 individuals; the same held for D/F
  within each mechanism. This run does not provide an effective behavioural
  contrast for TBS personalisation.
- Equal TBS cohort means under `current` and `recent` conceal differences:
  Socratic choice distributions differed for all 16 individuals, trajectories
  differed for nine, and target-attainment totals differed for four in each of
  D/F. The differences cancelled in the cohort mean.

These results are descriptive simulations under authored response assumptions.
There is only one repetition per individual, so Monte Carlo standard errors are
unavailable. The development set is deliberately selected and profile-balanced;
480 sessions are not 480 independent participants. Historical TBS offers remain
unknown, and the provisional TBS actor's held-out prediction was worse than the
simple choice-frequency baseline on average. This pilot does not validate human
assistance effects or identify a winning communication style.

The [original-profile breakdown](reconsideration-profile-analysis.md), checked on
12 November, separates the four profile groups and reports individual harms,
personalisation contrasts and processing sensitivity. Each group has four
selected actors and one repetition. In MAB, E improved all MAB-specialised and
Dual-regime actors, whereas D/recent had the largest Low-expression group mean
and improved all four there. The same recent Socratic variants harmed three of
four MAB-specialised actors. These are exploratory conditional patterns, not
validated human profile effects or a basis for selecting a favourable mechanism.

The local frozen outputs are in
`socratic_prototype/data/reconsideration_pilot_20261106/`: `manifest.json`,
`participants.json`, `status.json`, `analysis.json`, `analysis.md` and per-job
evaluator reports/session databases. Generated private data are ignored by Git;
the tracked configuration and this summary remain available in a repository clone.
Reproduction requires the actor export, its source/provenance and the frozen
software/dependency versions.

### Follow-up status

The requested TBS personalisation audit is in progress. Initial trace inspection
found accepted personalised `constraint_neglect` candidates that lost selection
to higher-scoring task-level candidates. For example, a trial with two choices
remaining scored `shrinking_horizon` at 0.660 and `constraint_neglect` at 0.554.
This is a diagnostic observation, not a completed audit of every decision or a
reason to force personalised interventions to win. The simulator also generates
no explicit participant replies, leaving reported-burden adaptation without new
self-report evidence.

The full audit and additional matched repetitions are **pending**; no follow-up
runner has been launched as of the status check above. All three mechanisms
(`none`, `current`, `recent`) are retained. The completed pilot and its manifest
remain unchanged. Any revised experimental configuration must use a separate
output directory; additional repetitions must not be presented as new people.

**11 November update:** the [new guided pilot](guidance-pilot.md) has now launched
in `guidance_pilot_20261111`, with three matched repetitions and all three
mechanisms. It evaluates the updated guidance rather than appending new results
to the original manifest. The full TBS personalisation audit remains pending.

## Starting or resuming a pilot

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
