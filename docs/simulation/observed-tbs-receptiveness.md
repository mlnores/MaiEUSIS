# TBS receptiveness pilot with observed-behaviour personalisation

Prepared on **16 November 2026** using
[`observed-tbs-receptiveness.json`](observed-tbs-receptiveness.json) and
[`observed-profile-tbs-pilot.json`](observed-profile-tbs-pilot.json).
Initial Mac output: `socratic_prototype/data/observed_tbs_receptiveness_20261116/`.

Launched on **16 November 2026 at 18:53 CET** with eight worker processes.
The frozen root manifest is
`af141caf05a0fd3ff3b78c6224971c027fdcc818cbdd188fac869bc554b1c718`.

## Completed VM run: 17 November 2026

The separately prepared Linux VM run completed **144/144 jobs at 04:34 CET on
17 November**, using 64 workers in **5 h 26 min**. All comparisons and calibrations
were fresh; the earlier Mac attempt's output was not pooled or transplanted.
The VM root manifest is
`447fed1c4b384736ce848e3264e9eaa5ae019dbb6b2c338c5b075c2c4ebccc3c`.

- [Interactive report](../../socratic_prototype/data/tbs_vm_report_20261117/receptiveness_report.html)
- [Written summary](../../socratic_prototype/data/tbs_vm_report_20261117/summary.md)
- [Numerical audit](../../socratic_prototype/data/tbs_vm_report_20261117/report_audit.json)
- [Report validation](../../socratic_prototype/data/tbs_vm_report_20261117/report_validation.json)
- [VM deployment/run instructions](../../deployment/tbs-vm/RUNBOOK.md)

The imported read-only export is under
`socratic_prototype/data/tbs_vm_received_20261117/tbs-vm-20261116T220756Z/`;
derived report files are separate in `socratic_prototype/data/tbs_vm_report_20261117/`.
The 9 MB archive contains committed evaluator records, normalised calibration
profiles/inputs, frozen manifests and source snapshots. Full SQLite stores remain
on the VM. All 830 exported-file checksums passed.

The VM exporter performed exact original-runtime replay and reread all 144
calibrations from SQLite. Local replay using the frozen VM source reproduced all
138,240 comparison choices/outcomes and 48 independent baseline trajectories.
There are 144 fresh A checks and 96 cross-level calibration matches. Linux/macOS
floating calculations differed in 317 comparisons by at most 1.11e-16; local
numeric checks used an explicit 1e-12 tolerance, while discrete choices, outcomes
and target counts matched exactly. This is numerical validation, not a second
implementation of graph inference/SHACL or a natural-language evaluation.

Overall primary changes from matched A, in **percentage points**:

| Receptiveness | C generic direct | E personalised direct | D generic Socratic | F personalised Socratic |
| --- | ---: | ---: | ---: | ---: |
| 0.25 | +2.08 | +0.87 | +0.43 | +0.09 |
| 0.50 | +3.65 | +1.82 | +0.52 | -0.09 |
| 0.75 | +4.77 | +2.08 | +0.43 | -0.09 |

Matched A attainment is 66.67%. At 0.75, the overall E−C contrast is −2.69 pp,
and F−D is −0.52 pp. Both Socratic conditions have positive group means only in
Low-expression at that level; the other three groups' means are negative.
These are descriptive results under the documented synthetic processing rules,
not established human intervention effects. Secondary multiplied block scores
have separate plots and CSV fields.

**Exact-tie reporting correction:** 13 of the 192 actor/level/assisted-condition
means have zero integer net target difference across repetitions, but rounding
left tiny signed values in the original floating-point means. Derived gain/tie/loss
counts use the sign of the integer target difference summed over the three
repetitions. The original analysis is unchanged; displayed means are unchanged.
`tie_corrections.csv` and `report_audit.json` record every corrected cell.

The report contains 41 interactive figures, with all 363 heatmap cells and 324
trend points checked against trial-derived data. It retains separate C/E/D/F
series, all three repetitions, explicit units and the original four actor groups.

## Matched design

- TBS only: full **192 trials**, comprising 24 blocks of eight decisions, for
  each unassisted calibration and each comparison condition.
- The same **16 development actors** as the completed MAB pilot: four each in
  MAB-specialised, TBS-specialised, Dual-regime and Low-expression. These labels
  are descriptive researcher information, not assistant inputs. The 46 evaluation
  actors remain untouched.
- Three matched repetitions at receptiveness **0.25, 0.50 and 0.75**.
- All five conditions **A/C/E/D/F** run fresh at every level. There are
  **144 jobs**, 720 comparison sessions and 144 calibrations: 138,240 comparison
  trials and 27,648 calibration trials. No earlier assisted outcomes are reused.
- A single TBS response rule; `current` is retained only as a historical format
  label. There are no `none` or `recent` experimental factors.
- True receptiveness is identical across actors and assistance styles at each
  level. Additional reactance, distraction and AI-induced omission are zero.
  Actor-specific baseline omission rates remain active.
- The seed is `reconsideration-development16-v1`. Independent keyed random
  streams for choices, omissions, offers, targets and outcomes omit condition,
  receptiveness and session identifiers. Actor experience and assistant interaction
  history reset before every comparison. Within a job, E/F receive the same
  generated TBS calibration; C/D use common task-aware delivery inputs.

The primary outcome is **target-attainment rate**, `targets_attained / 24`.
Paired assisted-minus-A differences are displayed in **percentage points**.
Completed-block score, including the conditional final-win multiplier, is a
secondary outcome in multiplied points. Primary and secondary units are kept
separate. Individual results average three paired repetitions before group
means; repetitions do not create extra participants. C/E/D/F stay separate even
when results coincide, and both gains and harms are retained.

## Assistance and response assumptions

The runtime is the same observed-behaviour personalisation implementation used
in the completed MAB study: `policy-0.7` and `participant-model-0.2`. The graph
supplies reasons, objections and accepted comparisons; the intervention policy
decides timing, eligibility and delivery. E/F can adapt from permitted public
task choices and uncertain style-specific uptake estimates. C/D do not receive
those personalised estimates. A remains unassisted.

TBS has two available actions. Restricting a Socratic response to both would leave
the actor's distribution unchanged. This pilot therefore retains the existing
task-owned evidence-processing rule in `tasks/tbs_execution.py`:

- Direct assistance targets the graph-supported recommended action.
- Socratic guidance compares SAFE and RISKY. An `expected_value_limit` issue
  before the final decision weights the actions by their displayed immediate
  expected points. On a final decision, positive target-attainment values are
  normalised, accounting for the conditional multiplier. Other cases weight
  actions by `probability * max(1, amount) / (1 + abs(amount - required_per_trial))`.
- Both styles mix their processing target with the actor's baseline using the
  configured receptiveness. Task processing assumptions differ between styles;
  this is not the MAB singleton/pair rule or a multi-trial optimal planner.

The assistant's TBS observer has 25 pressure-logistic hypotheses and is simpler
than the private empirical actor. Its uncertain forecasts can be misspecified.
An inferred uptake coefficient is conditional on those forecasts, not a measured
attitude, trust score or causal benefit estimate. No beneficial personalisation
contrast or C/E–D/F separation is enforced.

The private actor retains the provisional **seven-feature state/feedback model**
from the colleague's handover. Historical offers remain unavailable; exported
`offer_sensitivity: 0` is retained, rather than fitting or inventing offer effects.
New offers and targets follow the current task generator's independent uniform
sampling. Baseline omissions are independent Bernoulli draws from the frozen
actor estimates. The [empirical-model limitations](../empirical_profiles.md#interpretation-limits),
including the negative held-out TBS prediction result, remain applicable.

Language is offline/bounded. Active synthetic reading exposure is 7,000 ms.
Actors process structured intervention records, not natural language, and do not
generate helpfulness, disagreement or burden reports. These results will assess
the specified synthetic mechanisms, not establish effects on human participants.

## Controls, analysis and parallel execution

The new coordinator is `scripts/tbs_receptiveness_sweep.py`, outside the frozen
runtime package. Earlier MAB runners, source snapshots and reports are preserved.
It uses eight independent worker processes on the eight detected local CPUs,
with one numerical-library thread per worker. Jobs are ordered by repetition,
interleaving original profile groups and receptiveness levels. Each worker has
its own SQLite store and immutable numbered attempts; only the coordinator writes
shared status and analysis. `caffeinate -i` prevents idle system sleep.

Before execution, 48 full unassisted trajectories are independently reconstructed
without graph inference or assistance. Every new A must match the expected
choice/outcome trajectory, choice distributions, omissions, target count and
score. Every completed job additionally replays all 960 comparison trials and
five sets of block metrics before committing. This is numerical replay, not a
second independent graph/SHACL implementation.

Calibration profiles and complete evaluation/feedback inputs are compared across
receptiveness levels, normalising session identifiers only. These signatures
include displayed option amounts/probabilities, targets, horizons and multipliers,
as well as choices, omissions, outcomes and points. A complete grid has 144 fresh
A checks and 96 cross-level calibration checks.

Each level freezes actor inputs, source and dependency fingerprints. The root
manifest also freezes the coordinator and scheduler. Execution rejects altered
software, incomplete protocols, missing conditions, inconsistent rate denominators,
changed baseline streams or calibration drift. Do not change the executable
`socratic_prototype/` package, this coordinator or `scripts/pilot_parallel.py`
while the experiment is running.

`analysis.json` and `analysis.md` update after committed jobs. Primary actor
summaries require all three repetitions, all three levels and all five conditions.
The separately labelled `first_repetition` preview requires all levels/conditions
of repetition zero. Partial completion never silently increases or changes the
denominator. Full group/individual heatmaps and receptiveness trend plots can be
generated after completion from these records.

The initial planning allowance is **18–30 hours** with eight workers, informed
by the preceding MAB run rather than a measured full TBS throughput. The runner
publishes an updated estimate after completed jobs; early estimates may change.

## Start, monitor and resume

The commands below document the initial **Mac attempt**. For a new VM run, use
the [VM runbook](../../deployment/tbs-vm/RUNBOOK.md) and a fresh output directory;
the completed VM experiment and its runtime are frozen.

All **36 preflight tests passed**, covering the new coordinator, observed
personalisation and single-response contracts. A separate real short-protocol
simulator check replayed 240 trials at receptiveness 0 and .75, including all
five zero-response controls and unchanged fresh A across levels. C/E/D/F each
changed choice probabilities in the nonzero-response check. Those engineering
sessions are excluded from the pilot. `preflight.json` and copied logs in the
output root record the checks. All 48 independent full baseline trajectories
were reconstructed and verified before workers were launched.

Prepare and validate the frozen plan without executing comparison jobs:

```bash
PYTHONPATH=. .venv/bin/python scripts/tbs_receptiveness_sweep.py \
  --config docs/simulation/observed-tbs-receptiveness.json \
  --output-dir socratic_prototype/data/observed_tbs_receptiveness_20261116 \
  --workers 8 --prepare-only
```

Start a prepared grid, or resume an interrupted grid after all previous workers
have exited:

```bash
PYTHONPATH=. caffeinate -i .venv/bin/python -u scripts/tbs_receptiveness_sweep.py \
  --output-dir socratic_prototype/data/observed_tbs_receptiveness_20261116 \
  --workers 8
```

The runner sets offline language mode and single-thread numerical settings before
loading the simulation package. Monitor:

```bash
tail -f socratic_prototype/data/observed_tbs_receptiveness_20261116/sweep.log
cat socratic_prototype/data/observed_tbs_receptiveness_20261116/status.json
```

For a graceful stop, create `stop-after-jobs.json` in the output root. Current
jobs finish and commit, then scheduling stops. Remove that request before
resuming. Exclusive inherited leases prevent concurrent coordinators. Existing
completed results are retained and checked; missing jobs get new numbered
attempts. The output directory must never be re-prepared with changed software.
