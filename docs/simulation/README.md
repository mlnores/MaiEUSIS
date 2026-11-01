# Personalisation and matched synthetic experiments

The prototype compares five conditions: A (no assistance), C (generic direct
recommendations), E (personalised direct recommendations), D (generic Socratic
questions) and F (personalised Socratic questions). Condition B has been removed.
Generic means task-aware without a calibrated participant model.

## Components

- `tasks/mab.py` and `tasks/tbs.py` compute estimates from public task events. The
  original researchers' fitted models have not yet been supplied or integrated.
- `participant_model.py` represents the assistant's estimates. E/F receive the
  task calibration, explicit self-report history and uncertain interaction
  summaries. C/D do not receive those personalised estimates in their language
  packages or use them for intervention selection. A stays silent.
- `argumentation/` remains the sole source of reasons and objections. Specific
  recommendations additionally require an accepted comparison proof. MAB compares
  all six posterior mean reward estimates; ties cause abstention. TBS compares
  immediate expected points before the final trial and exact target-attainment
  probability on the final trial. These criteria are explicit, bounded choices,
  not an optimal MAB exploration strategy or a TBS multi-trial planning solver.
- `intervention_policy.py` schedules and ranks graph-grounded candidates. There
  is no personalisation bonus. Explicit feedback reporting burden can adjust the
  interruption cost in E/F. Disagreement continues to contest the relevant
  hypothesis rather than automatically being interpreted as general distrust.
- `agents.py` dispatches the synthetic participant's own task policies through
  registered execution adapters. `tasks/mab_execution.py` uses dual-rate reward
  learning and softmax; `tasks/tbs_execution.py` uses a logistic policy over
  normalised target pressure. Each condition starts with a new actor and empty
  experience. Fixed characteristics persist; experience does not carry over.
- `assistance_response.py` models effects on the actor's choice distribution.
  Direct assistance proposes a specific option. A Socratic question invokes a
  public-evidence reconsideration heuristic for the structured issue, without
  receiving a recommended option. Reconsideration can preserve the original
  preference. Reactance, distraction and omission assumptions permit harm.
- `simulation.py` runs the same individuals through the configured conditions, using
  common per-trial random streams for choices, option outcomes, task transitions,
  option pairs and targets. Condition/session IDs never enter those streams.

The agent's latent task and response parameters are researcher/evaluator inputs.
They are **not** supplied to the assistant. The assistant instead fits its ordinary
coarse calibration models to separately generated unassisted observations and
updates from permitted observations. Direct recommendation/choice agreement is
recorded as concordance, not established trust, causal compliance or benefit.
Socratic reconsideration is unknown to the assistant unless reported. No response
parameter is inferred from a neuroscience profile label or SFSS score.

## Run an example

Use the existing research environment with RDFLib. The runner deliberately uses
offline wording: language variation is not silently added as another experimental
factor.

```bash
.venv/bin/python -m socratic_prototype.simulation \
  --participants docs/simulation/participants.example.json \
  --scenario null --protocol short --seed first-comparison \
  --data-dir /tmp/maieusis-simulation \
  --output /tmp/maieusis-simulation/evaluator.json
```

The example parameters are **assumed synthetic values**, not reconstructions of
any human participant or the original four empirical profiles. Supply an array
of distinct pseudonyms and supported task-model parameter sets to run more
individuals. There is no built-in restriction to 16 or 62. Original parameter
names/equations must be checked for compatibility before importing real estimates;
a fitted coefficient from a different model must not simply be relabelled here.
Each specification requires `id`, a nonempty `source` describing provenance, and
`task_models` entries for every environment selected by the study. For the default
study these are MAB (`alpha_plus`, `alpha_minus`, `beta`) and TBS (`intercept`,
`slope`). Each registered adapter validates its own parameter schema.
Optional `original_profile` is a descriptive evaluator
label; it does not substitute for the task models and is not sent to the assistant.

Default calibrations are complete short protocols (MAB 40, TBS 24), reused across
all five conditions for that individual's comparison. `--protocol full` uses
MAB 200 / TBS 192. `--repeats N` adds paired replications with fresh outcomes.
`--max-trials 2` caps comparisons for a smoke check while still making complete
calibrations; capped comparisons are marked incomplete, not valid full studies.
Rerunning creates new inspectable sessions rather than overwriting earlier runs.

Use `--scenario responsive` or `--scenario interference` to vary explicit response
assumptions. `null` forces zero responsiveness, reactance, distraction and omission
for both styles, including when a participant specification provides overrides.
Under null, all five conditions must produce identical choices and outcomes for
the same individual/task/repetition. The other scenarios apply the same default
parameter values to both styles; style effects arise from the distinct processing
mechanisms. Optional per-person `response_parameters` are keyed by environment;
each supplied environment entry must specify both direct/socratic styles, each
with all four probabilities:
`responsiveness`, `reactance`, `distraction`, `omission_probability`.

Task rules mirror the current browser: stable then volatile MAB reward schedules,
unchanged gain/zero/loss probabilities and jump rules, and eight-choice TBS blocks
with published option pairs, target/multiplier mapping and conditional final-win
multiplication of the whole accumulated score. Actor response timing and display
exposure are explicitly synthetic placeholders; they are not measurements of
human reading or browser timing.

## Study configuration and new environments

The same study JSON is accepted by both `simulation --study` and `server --study`:

```json
{
  "id": "mab-tbs",
  "tasks": {
    "MAB": {"protocol": "short", "calibration_tasks": ["MAB", "TBS"]},
    "TBS": {"protocol": "short", "calibration_tasks": ["MAB", "TBS"]}
  },
  "conditions": ["A", "C", "E", "D", "F"]
}
```

Protocols belong to each environment; names need not be `short` or `full` and
different environments may use different protocols in one study. Each dependency
must be selected in the study and each environment includes its own calibration.
Calibration is always unassisted, even if A is omitted from comparison conditions.
Without A there are no paired differences from A. The UI selects only the
study's adapters and uses its fixed protocols. Without `--study` the original
MAB/TBS short/full selector remains available. A supplied study configuration is
frozen into each new session; existing sessions are not relabelled.

To try a complete third environment, use the supplied engineering fixture:

```bash
.venv/bin/python -m socratic_prototype.simulation \
  --study docs/simulation/reference-study.json \
  --participants docs/simulation/reference-participants.json \
  --scenario null --seed reference-check \
  --data-dir /tmp/maieusis-reference \
  --output /tmp/maieusis-reference/evaluator.json

SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
  .venv/bin/python -m socratic_prototype.server \
  --study docs/simulation/reference-study.json \
  --data-dir /tmp/maieusis-reference
```

Open `http://127.0.0.1:8765`, enter `synthetic_reference`, select its completed
calibration, then start a comparison. Or use a new pseudonym and first complete
the four-trial calibration yourself. REFERENCE alternates displayed win
probabilities for two one-point options, uses its own `mini` protocol and reports
`decision_errors` (minimise). Its simple actor learns from its own outcomes. It is
an extension check, not an empirical decision task or fitted human model.

The [task extension guide](../task_modules.md#adding-another-task) describes the
module, ontology, graph, simulation and browser contracts. Adding an environment
requires those environment-owned files, explicit registration and a study file;
no shared runner or intervention policy branches are needed.

## Outputs and interpretation

The SQLite store contains only the ordinary public-event projection, labelled
synthetic provenance and the assistant's trace. JSON exports and the inspector
identify simulated observations. The separate evaluator report contains latent
actor specifications, assumed response scenario, baseline/assisted choice
probabilities, realised outcomes, private `evaluator_state` and paired descriptive
metric differences from A for completed runs. Each run has `metrics`; each paired
row has `metric_deltas_from_A` with raw assisted-minus-A differences. Interpret
each metric using its declared direction/unit in `study.execution`: a negative
delta improves a metric to minimise, and a positive delta improves one to maximise.
There is no assumed universal score or common scale across environments.
MAB reports reward score; TBS reports completed-block score and targets attained,
plus block details. Keep that report on the researcher side;
it is not participant-visible task evidence. Partial TBS scores include completed
blocks only. Replications are repeated simulations of the same individuals, not
additional independent human participants.

The report records simulation/agent versions (currently 0.2), response-model
version, and each execution adapter's version, source SHA-256 and metric
definitions. This is distinct from a session's frozen task/ontology, graph,
participant-model and policy descriptors. Replay checks the recorded public
events and assistant decisions; reproducing synthetic choices also requires the
evaluator report, seed, participant specifications and the recorded execution
implementations. A code hash is a drift record, not an archived copy of that code.

Simulation results are conditional on the assumed response mechanisms. Baseline
prediction on held-out human choices, independent behavioural validation,
calibration/parameter recovery and human assistance-response data remain research
work. Sensitivity scenarios do not validate human causal effects or establish a
winning assistance style. The supplied sample cannot substantiate empirical
claims about the 62-person cohort.

Policy 0.4 and argumentation 0.3 change runtime semantics. Restart the server and
create new comparison sessions. Completed calibrations can still be selected when
their numerical model and task-module versions match. Existing traces, including
condition B, remain readable/exportable; deterministic replay of an earlier configuration requires
its recorded runtime. The numerical task calibration algorithms are unchanged.
