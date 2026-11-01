The architecture has been updated following the research proposal in
[questions_3109.md](questions_3109.md) and our subsequent discussion. The prototype
now supports a controlled comparison of assistance style and personalisation,
with separate models for task behaviour, responses to assistance and the
assistant's understanding of a participant. It also supports environments beyond
MAB and TBS. This establishes an executable experimental framework; reconstructing
and validating the original participants remains research work.

The research objective remains the two questions raised in the proposal: whether
assistance can compensate for limitations in a participant's weaker environment
while preserving strengths elsewhere, and which assistance style helps whom,
under which circumstances. The architecture permits no benefit and interference
as outcomes. It does not assign an advantage to personalised or Socratic assistance.

The five-condition comparison is now implemented as follows:

| Condition | Assistance | Personalisation |
| --- | --- | --- |
| A | No assistance | None |
| C | Direct recommendations | Generic, task-aware |
| E | Direct recommendations | Personalised |
| D | Socratic questions | Generic, task-aware |
| F | Socratic questions | Personalised |

This implements the proposed 2 × 2 comparison plus a no-AI baseline. Condition B,
which previously provided general guidance without task awareness, has been
removed from session creation, study configuration and the interface. Its old
guidance audience is no longer accepted by the scheme loader or intervention
policy. Historical traces remain accessible. Generic assistance uses the
current permissible task evidence. Personalised assistance additionally uses
task-specific calibration and uncertain participant estimates. Assignment in the
human interface is still manual; a randomised study protocol has not been added.

The main architectural change is the separation of the following responsibilities:

| Component | Responsibility and current implementation |
| --- | --- |
| Task modules and environments | Define public observations, rules, legal transitions, scoring, numerical estimates, ontology projections and task-specific argument schemes. Private simulators generate outcomes separately from the assistant's evidence. |
| Synthetic participant | Generates choices from its own task parameters and observed history. `agents.py` delegates task decisions to environment-specific execution adapters. MAB currently uses dual-rate reward learning and softmax; TBS uses a logistic policy based on normalised target pressure. |
| Assistance-response model | `assistance_response.py` describes how a delivered intervention changes the synthetic participant's choice distribution, including responsiveness, reactance, distraction and missed responses. |
| Assistant's participant model | `participant_model.py` maintains estimates derived from permitted calibration, task observations and explicit interaction feedback. It does not receive the synthetic participant's true parameters. |
| Graph argumentation | Supplies supported reasons, objections and comparison proofs, with provenance and uncertainty. Existing graph reasoning has been retained and extended to support specific recommendations. |
| Intervention policy | Chooses whether and when to intervene, ranks supported opportunities, applies condition boundaries and controls interruption frequency. It remains separate from argument acceptance. |
| Study configuration and runner | `study.py` and `simulation.py` configure environments and conditions, reset runs, coordinate matched randomness and produce separate evaluator reports. |

This separation allows a task decision model or an assistance-response assumption
to be changed without treating it as a change to the assistant's knowledge or
reasoning rules.

The current task policies are provisional. MAB learns from observed rewards;
the present TBS actor has no learned internal state and responds to the current
constraints. Reconstructing the original participants' within-run adaptation,
particularly in TBS, requires the empirical model specifications and validation.

Direct recommendations now prescribe a specific available action, with its
keyboard shortcut, an explicit comparison criterion and a graph-supported
explanation. For MAB, the implemented criterion compares posterior mean reward
estimates from observed outcomes across all six options. For TBS, it compares
immediate expected points before the final choice and exact target-attainment
probability on the final choice, including the conditional multiplier. Strict
comparison schemes require a unique winner; a tie cannot justify a specific
recommendation under these criteria. Direct delivery requires both a supported
intervention warrant and an accepted option-comparison proof.

These are bounded decision criteria. The MAB recommendation does not solve the
exploration–exploitation problem, and the TBS recommendation does not solve
multi-trial planning with unknown future options. Those limits are retained in
the intervention record and wording.

Socratic assistance addresses a supported issue or uncertainty through a question,
without attaching a recommended option. The structured intervention records the
issue, focus, supporting and opposing arguments, and limits. A synthetic actor
responds to this structure through a task-specific reconsideration heuristic;
it is not asked to interpret arbitrary generated prose. Reconsideration may
preserve its original preference. The language layer expresses interventions for
human participants. The simulation uses offline wording so that language-model
variation is not silently introduced as another experimental factor.

Graph argumentation remains the single source of intervention reasons and
objections. The policy cannot invent an independent behavioural reason when
graph reasoning is unavailable or incomplete. Accepted arguments make an
intervention eligible; they do not require delivery. The policy still considers
provisional usefulness, interruption cost, thresholds and cooldowns. An unresolved
argument can support a clarification question only where a scheme explicitly
permits that communication. These policy values and authored schemes remain
provisional rather than empirically fitted.

Personalisation now distinguishes task tendencies from attitudes towards
assistance. In E/F, calibration informs task-specific estimates and hypotheses;
explicit feedback supplies a separate interaction history. Reported burden can
adjust interruption cost. The previous automatic personalisation bonus has been
removed: having a participant model does not itself increase an intervention's
usefulness score. C/D do not use calibrated participant estimates or receive
them in their language evidence packages.

The interaction model is deliberately limited. Choosing an advised option is
recorded as observed concordance, not established trust, causal compliance or
benefit. Socratic reconsideration remains unknown to the assistant without an
explicit report. Disagreement can contest an interpretation; it is not treated
as general distrust of AI. The current implementation therefore represents
interaction evidence and uncertainty, rather than a validated model of attitudes
towards either assistance style.

The synthetic participant and the assistant's model are kept separate throughout
the experiment. True task parameters, assumed responsiveness and hidden task
state belong to the researcher/evaluator side. The assistant receives the normal
public event projection and, in personalised conditions, estimates obtained from
unassisted calibration and permitted observations. For the default study, all
comparison conditions require completed MAB and TBS calibrations, but only E/F
use the calibrated participant model. Parameters do not automatically transfer
between tasks.

The simulation runner now compares the same specified individuals across the
configured conditions. Each comparison starts with a fresh task environment and
empty actor experience while retaining the individual's fixed parameters. The
actor learns within each run where its task policy includes learning. The same
unassisted calibration is reused across that individual's comparison conditions;
it does not initialise the actor with experience from another comparison.

Keyed random streams match environmental events and choice draws across
conditions for the same individual, task and repetition. Session and condition
identifiers do not affect those streams. Matching randomness does not force
identical outcomes when assistance changes choices. Under the null-response
scenario, however, assistance has no behavioural effect, and choices and outcomes
must agree across all five conditions. Repetitions use fresh streams.

Three explicit response scenarios are available: null, responsive and
interference. Per-person, per-task response parameters can also be supplied for
direct and Socratic assistance. Direct assistance shifts choice probabilities
towards the recommended action; Socratic assistance invokes reconsideration of
public evidence. The shared response mechanism can then express reactance,
distraction or omission. These are sensitivity assumptions, not estimates from
the original unassisted experiment. No responsiveness parameter is inferred
automatically from SFSS scores or a neuroscience profile assignment.

Participant specifications accept an arbitrary collection of distinct pseudonyms
with environment-specific parameter sets. There is no built-in restriction to
16 or 62 individuals. The MAB-specialised, TBS-specialised, Dual-regime and
Low-expression assignments can be retained as descriptive evaluator labels;
they do not substitute for individual generative policies or become hidden
evidence supplied to the assistant. The supplied examples and demonstration
profiles remain constructed examples, not reconstructions of the original cohort.

The execution architecture has also been generalised for future environments.
Each registered environment owns its namespace, ontology and shapes, task model,
argument schemes, recommendation wording, synthetic actor, private simulator,
metrics and browser adapter. Shared components dispatch through defined
interfaces rather than branching on MAB or TBS. A study JSON selects environments,
their individual protocols, calibration dependencies and comparison conditions.
Both the server and simulator accept the same study configuration.

A new environment therefore requires its own module and associated assets,
explicit registration and study configuration, without edits to the shared
engine, intervention policy or simulation runner. Browser setup controls and
adapter loading are generated from the selected study. Metrics declare units
and whether improvement means maximising or minimising a value, so the runner
does not assume that every environment awards points on a common scale.

A small REFERENCE environment demonstrates this complete extension path with
its own ontology, four-trial protocol, actor, graph criterion, browser interface
and error metric to minimise. It has been exercised across all five conditions
through simulation and scripted interface checks. MAB/TBS remain the default
study. REFERENCE is an engineering fixture, not a validated research task.

Public task events, assistant snapshots, graph proofs, interventions and delivery
records remain inspectable and replayable. Synthetic provenance is recorded
explicitly. The separate evaluator report contains private actor specifications,
response assumptions, choice probabilities, hidden environment state and paired
metric differences from A. Relevant configurations are versioned; simulation
reports also record execution-adapter source fingerprints. Reproducing a
simulation requires the corresponding code and evaluator inputs as well as the
recorded events. Repetitions are repeated simulations of the same individuals,
not additional independent participants.

Automated checks have exercised condition boundaries, graph provenance, task
completion, scoring, timing contracts, actor resets, matched null-response
behaviour, information boundaries, SHACL conformance and deterministic replay.
Scripted interface checks use the actual task scripts and Python persistence;
they do not establish visual correctness or laboratory timing accuracy. Native
browser visual verification was unavailable, and local socket binding was
restricted; HTTP routes were checked through an in-memory transport.

The remaining empirical work follows the research sequence in the proposal:

1. Obtain the original trial data, fitted models and equations, parameter
   definitions, diagnostics, task specifications and profile assignments.
   Establish compatibility before importing coefficients into a generative model,
   especially for TBS.
2. Implement and evaluate prediction of held-out human choices using only the
   information available at each trial. A dedicated held-out validation workflow
   has not yet been implemented.
3. Validate independent simulated behaviour, adaptation and performance against
   the original participants, including strengths and limitations across tasks.
4. Justify and vary assistance-response assumptions, and obtain interaction data
   where possible. Unassisted task fidelity alone cannot validate responses to AI.
5. Define and implement the analyses of compensation for weaker-task limitations,
   preservation of strengths, interference, profile differences and the
   assistance-style × personalisation interaction. Current paired metric reports
   are descriptive; they do not constitute this inferential analysis or evidence
   of a change in neuroscience profile.

Implementation details, runnable commands and parameter formats are in the
[personalisation and simulation guide](simulation/README.md). The
[task extension guide](task_modules.md) documents the environment contracts, and
the [graph argumentation guide](graph_argumentation.md) describes the reasoning
layer and its limits.
