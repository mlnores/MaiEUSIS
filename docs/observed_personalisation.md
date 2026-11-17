# Personalisation from observed behaviour

Implemented on **15 November 2026**, following the identical C/E and D/F choice
trajectories in the completed fair MAB sweep. That historical study is unchanged.
This implementation makes delivery depend on individual observations; it does
not assume that personalisation improves outcomes.

## Two estimates, separate from the participant

E/F maintain two uncertain models:

1. **Task behaviour.** A task-owned observer predicts unaided choices from
   calibration and the current run. MAB has 27 dual-learning-rate/softmax hypotheses
   and their learned values. TBS has 25 exploratory pressure-logistic hypotheses.
   New calibrations retain their full discrete parameter posterior. MAB learned
   values reset between runs; parameter uncertainty transfers from calibration.
2. **Reaction to assistance.** Independent direct/Socratic uptake posteriors over
   rho = 0, .05, ..., 1, initially uniform. Explicit reports retain their own meanings.

C/D use common delivery defaults and do not acquire these estimates. A remains
unassisted. Private synthetic actor parameters, actual receptiveness, archetype
and evaluator state are never observer inputs. Estimated rho is distinct from
the true rho configured for a synthetic experiment.

Code: `participant_model.py`, `learning.py`, `tasks/mab_participant.py` and
`tasks/tbs_participant.py`. Future environments may implement the optional
`participant_observer(profile)` and
`assistance_target(evaluation, baseline, intervention)` hooks. The observer has
`distributions(evaluation)`, `predict(evaluation)`, `observe(evaluation, feedback,
unaided)` and `describe()` methods, and normalized grid `weights`. Environments
without these hooks remain usable, with unknown behavioural uptake and common
task delivery defaults; explicit feedback still applies. The shared learner has
no MAB/TBS dispatch branches.

## Learning from a trial

The learner replays public events in original order:

- Predict each action **before** the choice, with posterior predictive means and
  discrete-model intervals.
- Fit task parameter weights only to demonstrably unaided, completed choices:
  silent trials or explicit acknowledgements that assistance was not delivered.
  Assisted choices do not masquerade as unaided preferences.
- Update learned MAB values from every completed outcome, assisted or otherwise.
  Timeouts provide no observed reward to this model.
- Update uptake only after positive exposure acknowledged before a completed
  choice. A delivery logged after feedback cannot explain that earlier choice.
  Missing/zero exposure for an active prompt fits neither task preferences nor
  uptake. Exposure duration is not evidence of comprehension.

For the pre-choice unaided forecast p and task-owned processing target q:

```
P(observed action a | rho, exposure) = (1 - rho) p(a) + rho q(a)
```

Both p and q are averaged over the task posterior frozen at that trial. Direct
assistance targets its recommended action. MAB Socratic processing conditions
each hypothesis's preferences on the shared top-two set. TBS uses an explicitly
assumed gain/goal-processing target, including the conditional final multiplier.
Conditioning on both TBS choices would leave preferences unchanged, so it is
not substituted for that hypothesis.

When predictive distributions differ by less than .05 in total variation, record
an uninformative exposure without updating rho. Agreement already very likely
therefore supplies little or no uptake evidence. Rewards never label assistance
as helpful: lucky outcomes do not establish causal benefit.

This is an **approximate model-based behavioural uptake estimate**, conditional
on the observer and processing hypothesis. It does not identify trust, conscious
acceptance, comprehension or benefit. Reactance, distraction and task-model error
are not separately estimated and can appear as low or misleading uptake.

## Explicit reports

| Observation | Effect |
| --- | --- |
| Fewer prompts | Immediately changes frequency to infrequent; E/F additionally use 1.5 times the common interruption cost. Repeated clicks on one prompt do not accumulate cost. |
| Disagree | Contests that interpretation through the existing scoped, expiring graph undercutter. Does not imply general aversion to assistance. |
| Helpful | Records perceived usefulness by style; does not prove benefit or automatically lower burden. |
| Dismiss | Records dismissal; does not automatically raise burden or lower uptake. |
| Reply / no reply | Attributed text, or no report; no automatic acceptance/rejection inference. |

Text interpretation remains bounded and subject to researcher review. The LLM
cannot establish traits, update numerical beliefs from its own assertions or
change structured interventions. New reports appear in the next task snapshot;
“Fewer prompts” changes the stored preference immediately.

## Arguments, then delivery

The public ranking, graph acceptance and MAB performance gate are preserved.
Direct MAB support recommends rank 1; Socratic support compares ranks 1 and 2.
Personalisation adds no independent reasons or alternate ranking.

Versioned forecasts and uptake estimates are projected as uncertain RDF records,
with event/calibration evidence links. A digest binds the model and delivery
settings to a separate `forecastScheduling` graph warrant. This permits cautious
scheduling; it does not warrant a participant-facing recommendation. Scheduling
proof IDs remain separate from content proof IDs.

MAB learned values are posterior means across learning hypotheses, not a replay
at the mean parameter values. Their RDF rule names the observer implementation
explicitly. The online TBS pressure rule similarly identifies the transferred
posterior/unaided-choice estimator and links its actual calibration/current
choice evidence. SHACL checks forecast probabilities, ordered interval bounds,
style identifiers, exposure counts and forecast version/digest metadata.

Within an eligible opportunity, `personalisation.py` estimates the possible
change in the choice distribution:

```
distance = 0.5 * sum(abs(p(a) - q(a)))
```

It conservatively uses the **upper 95% discrete-model bound** and requires at
least six unaided choices from the transferred calibration/current run before
acting on task fit:

- Suppress prompts whose upper response-distance bound is at most .15. For a
  direct MAB singleton, this corresponds to already assigning at least .85 mass
  to the recommended action; for a Socratic pair, to existing mass on that pair.
  TBS uses its actual processing target, not membership in its two-option set.
- Otherwise attenuate provisional usefulness only when the upper distance is
  below the same task/style's common uniform-baseline distance. No upward
  personalisation bonus is applied.
- After six informative exposures of that style, cautiously attenuate usefulness
  if the upper uptake bound falls below the prior mean .5. The reduction is capped
  at 25%, avoiding a blanket low-uptake veto.
- If the upper uptake bound is at most .25, add three trials to the cooldown.
  Stronger opportunities can still clear the ordinary score threshold.
- Preserve existing contestation and explicit frequency preferences. Other
  graph-supported issues remain available after one interpretation is contested.

These configurable `policy.json` (`policy-0.7`) rules are authored screening
choices, not validated psychological cutoffs or predicted reward improvements.
The participant model is `participant-model-0.2`. Decisions retain distance/uptake
intervals, evidence, scheduling proof, factors, effective usefulness, cost,
cooldown and rationale. Validation reconstructs adaptation and rejects altered
model/proof links or scores. The inspector exposes the participant and decision
records. Only compact, condition-permitted estimates enter LLM packages.

## Experimental state and limits

Each comparison starts from the same calibration and fresh interaction priors.
No condition inherits another condition's observations. There is no `none`/`recent`
factor. The actor's private response rules and true response settings are unchanged.

Synthetic choices exercise uptake adaptation. The simulator does **not** invent
helpfulness, disagreement or burden reports. Testing those adaptations requires
actual human feedback or an explicitly specified future feedback generator with
matched assumptions across conditions. Current actors do not understand language;
content-sensitive response needs separate modelling and validation.

The TBS baseline observer omits offer-value and distinct horizon effects. Coarse
model intervals are not calibrated predictive coverage. Parameters currently
assume stationarity within a run: estimates evolve with new observations, without
a separate latent time-varying responsiveness process. There is no guaranteed
C/E or D/F separation or improvement. New matched runs must measure this.

## Try it

Restart the server and create **fresh calibrations/sessions**. Historical sessions
remain readable/exportable; mutation/replay requires their recorded runtime.
Do not resume historical pilots with this implementation.

```bash
SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
  .venv/bin/python -m socratic_prototype.demo --data-dir /tmp/maieusis-observed-personalisation
SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
  .venv/bin/python -m socratic_prototype.server --data-dir /tmp/maieusis-observed-personalisation
```

In the researcher inspector, examine `participant.online_task`,
`participant.interaction.direct` / `.socratic` and candidate `personalisation`
records. E/F learn; C/D retain common inputs. The demo is an engineering fixture,
not an experiment demonstrating personalisation effects.

```bash
SOCRATIC_LLM=offline .venv/bin/python -m unittest tests.test_observed_personalisation -v
```

Tests cover both observers/styles, prior transfer/reset, causal order, exposure,
timeouts, private-information isolation, reports, conservative delivery, actual
schedule changes, graph/RDF conformance, tampering and deterministic replay.
No new dependency is required.

## Verification on 15 November

All 17 new tests passed, including actual incremental validation of live MAB/TBS
events and independent full-session SHACL/replay checks. Another 11 task-module
and environment-extension tests and 37 argumentation/shared-guidance/separation
checks passed. Generated-language/graph-policy regression checks, all five
conditions' completion/replay, and the sequential/parallel engineering comparison
were also exercised; the latter matched 240 trial records and six exact F replays.
Teammate-panel tests passed for both games. Checks ran in targeted batches; the
entire suite was not rerun after the final TBS provenance correction.

One live-socket test was unavailable in this environment; in-memory HTTP routes
passed. No live Ollama generation or full outcome experiment was run at that
implementation-check stage. Earlier pilot data/reports remain historical results.

After these implementation checks, the [matched MAB experiment](simulation/observed-mab-receptiveness.md)
ran with eight workers, three repetitions and receptiveness .25/.5/.75,
completing all 144 jobs on 16 November 2026. The
[report](../socratic_prototype/data/observed_mab_receptiveness_20261115/receptiveness_report.html)
shows cluster and individual results with C/E/D/F kept separate. Personalised
conditions delivered fewer prompts, but their overall mean rewards were below
their corresponding non-personalised conditions at each receptiveness level;
cluster and individual contrasts vary. These are descriptive synthetic results,
not evidence of human benefit. All 144,000 comparison trials were numerically
audited, and preceding studies remain separate historical results.
