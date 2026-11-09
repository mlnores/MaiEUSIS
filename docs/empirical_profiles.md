# Empirical participant reconstructions

The empirical pipeline imports the Irena handover, freezes the 62-person registry
and development/evaluation split, preserves the original MAB model, and fits an
explicitly provisional TBS model from the information available. It provides
training-only prediction, fresh unassisted simulations, internal recovery checks
and actor exports for the existing five-condition simulator. It does not infer
responses to AI from the original unassisted experiment.

The next experiment layer is the [reconsideration sensitivity pilot](simulation/reconsideration.md).
It uses the existing frozen actor exports and varies three Socratic processing
assumptions under identical response coefficients, retaining the development 16.

The supplied files in `git_Irena/` remain unchanged. Generated bundles belong in
the ignored local data directory or a researcher-selected directory. They contain
researcher-side observations and fitted parameters and are not assistant inputs.

## Create a frozen cohort bundle

From the repository root:

```bash
.venv/bin/python -m pip install -r requirements-empirical.txt

COHORT_DIR=socratic_prototype/data/my_empirical_cohort
.venv/bin/python -m socratic_prototype.empirical build \
  --source-dir git_Irena --output-dir "$COHORT_DIR"
```

Use a new empty directory for each procedure version. The build imports all 62
participants and all 24,304 historical trial rows, checks joins and sequence
completeness, and checks the supplied MAB forward calculations and TBS arithmetic.
It retains the supplied 16 development participants, four per original profile;
the complement contains 46 evaluation participants. Original labels and continuous
**core** profile scores are preserved, not recomputed from simulated performance.
Full L1-L6 scores and raw neural/dispositional variables are not actor features.

The procedure, source-file SHA-256 values, relevant implementation hashes and
Python/NumPy/SciPy versions are saved before fitting or scoring. Development
individuals are processed first. The model features, penalties and fitting rules
are fixed in code; there is no selection against the 46-person evaluation result.
Original profiles and original MAB model selection already used this cohort, so
the complement is not independent external validation of those earlier decisions.

The importer checks all 62 original full-data MAB fits against stored Q states,
choice probabilities, prediction errors and likelihoods. It records all boundary
flags rather than excluding difficult individuals. The source fits use 200
preserved trials per person but fewer likelihood observations where responses
were missed. The importer preserves 82 MAB timeouts, 171 TBS timeouts and 138
known-bug TBS unknown choices as different cases.

## Actor models and missing TBS offers

The empirical MAB adapter reproduces the original dual RW model:

```text
Q starts at zero; reward = observed points / 100
delta = reward - Q(chosen)
Q(chosen) += alpha_positive * delta, when delta >= 0
Q(chosen) += alpha_negative * delta, otherwise
choice probabilities = softmax(beta * Q)
```

No-response trials affect the task score but do not update Q. Q continues across
stages. Imported actors explicitly declare `handover_dual_rw_v1` and
`reward_scale: 100`. Existing illustrative actors without a model ID keep their
previous points/200 convention. Actor and assistant calibration are separate:
the assistant still fits its own coarse exploratory models from a fresh generated
unassisted calibration and is not given the actor's coefficients.

Historical TBS offer IDs and per-trial offered probabilities/gains remain null.
They are never invented from the outcome or replaced with randomly sampled offers
for historical prediction. The new `tbs_state_feedback_v1` actor estimates
**offer-marginal** risky choice from seven features:

| Feature | Available information |
| --- | --- |
| Pressure | `max(0, target - points) / remaining` |
| Remaining opportunities | Includes the current trial |
| Final-trial indicator | Whether one opportunity remains |
| Final-trial required gain | `target / multiplier - points` on the final trial; zero otherwise |
| Previous risky choice | One for a known risky response on the preceding trial in the same block |
| Previous choice known | Distinguishes a known safe response from an unavailable preceding choice |
| Previous gain | Whether the preceding same-block outcome was positive |

Previous-trial features reset at each block. An unknown preceding choice is not
imputed as safe; its separate known-choice indicator is zero. Known observed
feedback and score progression remain usable. A missed response and a logging-bug
unknown choice remain distinct observation records.

The model is a jointly fitted logistic policy with L2 penalty 1 on standardised
slopes and 0.001 on the intercept. Means and sample SDs are learned from eligible
training choices; a constant feature has scale 1. These choices are authored
regularisation assumptions. The model is not assembled by adding the original
one-predictor slopes and is not an already validated original TBS cognitive model.

The default `offer_sensitivity: 0` applies the fitted marginal policy to fresh
offers. This does **not** demonstrate that the original people ignored offers.
An optional sensitivity analysis allows prospective choices to depend on the
displayed expected-gain contrast:

```text
cue(pair) = (risky expected points - safe expected points) / 100
P(risky | state, pair) = sigmoid(offset(state) + eta * cue(pair))
```

For each state, the offset is solved so that the average risky probability over
the eight equally weighted offers equals the fitted marginal probability. Thus
eta changes conditional offer responsiveness without silently replacing the
historically fitted marginal. Eta is an assumption, not a fitted coefficient.
It uses immediate expected gain, not an optimal multi-trial planning criterion.
Fresh TBS offers and targets are sampled independently and uniformly using the
current task generator. Original realised offers and MAB shifts are not replayed.

Baseline omission probabilities are estimated separately by participant and task
with a Beta(0.5,0.5) prior: `(misses + 0.5) / (trials + 1)`. Full-history rates
belong to reconstruction actors; training-only rates belong to validation actors.
Fresh omissions are independent Bernoulli events. Baseline and additional
AI-induced omission combine as `1 - (1 - p_baseline) * (1 - p_AI)`.

## Distinct reconstruction and prediction roles

The bundle contains:

| File | Meaning |
| --- | --- |
| `cohort.json` | Frozen IDs, original profile metadata, split and fit diagnostics |
| `observations.json` | Canonical histories, including missingness and eligibility |
| `source_measures.json`, `variable_registry.json` | All 200 supplied reference measures and the supplied calculation/access definitions |
| `participants.all.json` | Full-data reconstruction actors; suitable for conditional simulation |
| `participants.development.json`, `participants.evaluation.json` | The two subsets of full-data actors |
| `participants.*.training.json` | Distinct actors fitted using training observations only |
| `heldout_report.json`, `heldout_predictions.jsonl` | Held-out scores and individual predictions from training-only models |
| `observed_metrics.json`, `source_metric_crosscheck.json` | Recomputed selected behavioural measures and comparison with supplied summaries |
| `fits/` | Per-person full/training specifications and diagnostics |
| `assumptions.json`, `frozen_procedure.json`, `bundle_manifest.json` | Assumptions, provenance, frozen procedure and integrity checks |

MAB training uses trials 1-150 and prediction uses trials 151-200. TBS training
uses blocks 1-16 and prediction uses blocks 17-24. No full-data Q states, outcomes,
summary columns or profile scores become predictors. Sequential test predictions
may use already observed test feedback; they never use future feedback. Unknown
choices and timeouts have separate test counts and do not enter choice likelihood.
TBS historical predictions remain marginal over unrecorded offers.

Reports include mean log loss, Brier score and comparison with uniform choice and
training-only choice frequencies with Dirichlet(1) smoothing. Groups are reported
separately for the development 16 and evaluation 46, using an equal-weight mean
of participant scores. Lower log loss and Brier score are better; Brier definitions
differ between binary and six-option tasks and are not pooled across tasks.
These reports are descriptive, with no automatic validation-success declaration.

Full-data MAB actors use the supplied fits. Full-data TBS actors are fitted on all
available choices for reconstruction. Their fit or simulation performance must
not be substituted for training-only held-out results. Point estimates do not
represent parameter uncertainty; convergence and source replay are not evidence
of identifiability or human fidelity.

## Fresh behaviour, recovery and sensitivity checks

```bash
.venv/bin/python -m socratic_prototype.empirical baseline \
  --cohort-dir "$COHORT_DIR" --split all --repeats 10 \
  --offer-sensitivity 0 --output "$COHORT_DIR/unassisted_eta0.json"

.venv/bin/python -m socratic_prototype.empirical baseline \
  --cohort-dir "$COHORT_DIR" --split all --repeats 10 \
  --offer-sensitivity 2 --output "$COHORT_DIR/unassisted_eta2.json"

.venv/bin/python -m socratic_prototype.empirical recover \
  --cohort-dir "$COHORT_DIR" --split development --repeats 1 \
  --output "$COHORT_DIR/recovery.json"
```

Fresh checks run the full 200/192-trial protocols with each actor's own experience
and fresh keyed streams. They compare score/attainment and selected switching,
exploration, feedback-adjustment and pressure/horizon-sensitivity measures with
observed references. All 200 source measures remain available, but not all have
been reimplemented as fresh-run diagnostics. A MAB adjacent-choice switch rate
excludes transitions spanning missed trials; feedback-to-next-valid-choice
measures have their distinct original eligibility rules.

Recovery simulates observations under known actor parameters and refits them.
It reports MAB parameter errors and probability differences on common histories.
TBS standardisation changes between samples, so policy probabilities are compared
rather than treating differently scaled coefficients as directly equivalent.
Recovery under an assumed model does not validate that model against humans.

## Use reconstructions in the five-condition prototype

For a small integration run, export one actor:

```bash
.venv/bin/python -m socratic_prototype.empirical export \
  --cohort-dir "$COHORT_DIR" --split development --source-id E004 \
  --offer-sensitivity 2 --output "$COHORT_DIR/actor_E004.json"

SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
  .venv/bin/python -m socratic_prototype.simulation \
  --participants "$COHORT_DIR/actor_E004.json" --protocol short --scenario null \
  --data-dir "$COHORT_DIR/sessions" --output "$COHORT_DIR/five_conditions.json"
```

Remove `--source-id` to export all actors in the split. Use `--split all` for all
62 and `--fit-role training` for training-only parameters. Use `--protocol full`
for original-length simulations. The short protocol is an engineering check.
All five conditions receive the same actor characteristics and separate generated
calibration; experience resets between comparisons. Null responsiveness must
produce matched choices/outcomes, including baseline omissions. Responsive and
interference scenarios are explicitly assumed AI-response mechanisms.

To add only unassisted calibrations to the known-pseudonym selector:

```bash
SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
  .venv/bin/python -m socratic_prototype.simulation \
  --participants "$COHORT_DIR/actor_E004.json" --protocol short \
  --calibration-only --data-dir "$COHORT_DIR/sessions" \
  --output "$COHORT_DIR/calibration_seed.json"

.venv/bin/python -m socratic_prototype.server --data-dir "$COHORT_DIR/sessions"
```

The pseudonym is `reconstructed_E004`. Selecting it supplies a **synthetic**
calibration; subsequent manual choices are still made by the human using the
interface. The original human records are not silently imported as synthetic
trial events. True coefficients, omission parameters, original profiles/core
scores and offer sensitivity remain outside assistant inputs.

## Interpretation limits

The original TBS offers cannot currently be recovered. The seven-feature policy,
regularisation, independent omissions and offer-sensitivity settings are explicit
assumptions. The original unassisted experiment contains no AI interaction data;
responsiveness, reactance, reading cost and reconsideration remain unvalidated
mechanisms. The assistant's coarse calibration may also miss the actor's policy.

Browser display/history/timing differs from the original experiment in documented
ways. Synthetic timing and reading exposure are placeholders. A fresh-run score
match, numerical reproduction or passing an engineering test does not establish
effective human assistance, causal benefit, calibrated trust or a changed neural
profile. Repetitions are not new independent participants. The current TBS model
must be judged against the simple baselines in its held-out report, including
negative results; it should not be tuned on the evaluation 46 to manufacture
validation success.
