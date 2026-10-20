# Socratic teammate prototype

A local, runnable first prototype for the controlled MAB and TBS tasks in
[the design note](docs/socratic_ai_design_note.tex), informed by *The Sophist Machine Needs Productive
Ignorance* and [the meeting notes](docs/MeetingNotes_SocraticAIforDecisionMaking.pdf) (13 October 2026).
The standalone `mab_tbs_web_demo` includes the updated outcome-history and reward/probability visuals.
The Socratic prototype extends a separate copy of its
runner, retaining its reward rules, key mapping, outcome sampling, timeouts,
fixation intervals, and conditional final-trial multiplier.

## Run

From this directory, with Python 3.10 or later:

```bash
python3 -m socratic_prototype.server
```

Open **http://127.0.0.1:8765** for tasks and
**http://127.0.0.1:8765/inspector.html** for the researcher inspector.
No packages, build step, account, or API key are needed for the default mode.
Use `--port 8766` if the port is occupied. Sessions persist in
`socratic_prototype/data/sessions.sqlite3`; `--data-dir /path/to/data` selects a
separate study store. The service binds only to loopback. It has no authentication
or multi-user hosting configuration and is intended for a local prototype.

1. Set a participant pseudonym and short or full protocol.
2. Complete **unassisted calibration** in MAB and TBS under that pseudonym.
3. Select **Comparison session**, its assistance condition, and the two completed
   calibration sessions. Calibration and comparison protocol lengths must match.
4. Run either task. Choices remain yours; prompts may be disputed, dismissed, or
   marked helpful. “Fewer prompts” changes the subsequent cooldown.
5. Use the inspector to step through evaluations and feedback, examine supporting
   and opposing reasons, validate replay, and export JSON or RDF.

For a quick inspectable walkthrough, generate explicitly **synthetic** sessions:

```bash
python3 -m socratic_prototype.demo
```

This creates completed short calibrations and personalised Socratic sessions for
`synthetic_demo`. They appear in the inspector. To try personalised gameplay
immediately, enter that pseudonym and select Comparison session. The synthetic
calibrations exercise the software; they are not fitted human data. Use a separate
`--data-dir` for actual participants.

## Study conditions and timing

The meeting notes describe alternatives for discussion, not an agreed protocol.
The compact comparison is implemented as A/B/C/F; D/E expose its six-condition
extension. Assignment is manual, not randomised, and no protocol is preregistered.
All comparison groups have the same completed unassisted calibration, but only
E/F supply those calibrated estimates to the intervention policy.

| Condition | Policy inputs and delivery |
| --- | --- |
| A | No assistance; matched neutral preparation window |
| B | Scheduled general guidance; no task-specific or person-specific advice |
| C | Task-aware conventional guidance; no calibrated person model |
| D | Task-aware Socratic questions; no calibrated person model |
| E | Task-aware conventional guidance with task-specific calibration |
| F | Task-aware personalised Socratic support, challenge, or justified silence |

The default language layer uses reviewed templates in every condition. An
experimental Ollama mode can now compose new questions for D/F from a
condition-filtered evidence package. B/C/E retain reviewed conventional wording.
An empirical comparison requires piloting the provider layer, fixing its
model/version and language mode, and agreeing the study protocol.

A **four-second preparation window** is used in all conditions, then the original
**five-second choice window**. MAB preparation precedes the next options display
and uses previous feedback. The first MAB window has no prior feedback. TBS options
are visible throughout preparation; keyboard and mouse choice input is disabled
until the choice window. Number-key attempts during preparation are logged.
The prompt disappears before commitment. No assistance is delivered after the
last trial because there is no next decision.

Generation runs inside the fixed window. Late messages are not displayed and
receive an unexposed delivery record; API acknowledgements do not extend that
window. Logs distinguish generation latency, request round-trip time, actual
reading exposure, late arrival, and early attempts. Backend validation and saving
can add infrastructure delay between trials. The inherited browser timing is
uncalibrated software timing, with no EEG triggers or physical onset measurement;
this implementation has not been validated for laboratory acquisition.

## Productive ignorance in the implementation

- **Observations:** permitted option displays, selected choices, rewards, timeouts,
  and response times. Timeouts never enter the reward-learning model as arm losses.
- **Environment estimates:** MAB has symmetric Dirichlet reward beliefs and a
  Bayes-factor comparison of stationary vs unknown-split outcome histories.
  Reward noise remains an alternative to a change. TBS exposes gap, pressure,
  immediate EV, and exact current final-trial attainment arithmetic.
- **Participant estimates:** MAB uses a coarse Bayesian calibration grid over dual
  learning rates and softmax sensitivity, then resets Q values in the new session.
  TBS uses an exploratory grid-based Bayesian logistic pressure-policy model.
  Parameter intervals and assumptions are retained; no task-to-task transfer of
  participant tendencies occurs.
- **Hypotheses:** underexploration, premature exploitation, feedback overweighting,
  and possible constraint neglect are task-scoped inferences with supporting
  trials, provisional posteriors, alternatives, and revision conditions. Neither
  persistence nor response time is turned into overconfidence or hesitation.
- **Reasoning:** explicit supporting and opposing arguments retain objections.
  A hand-written Bayesian network estimates possible mismatch and usefulness;
  a separate policy weighs thresholds, interruption cost, preferences, and
  cooldown from actually delivered messages.
- **Graph argumentation (shadow):** with RDFLib, new evaluation snapshots discover
  arguments through scoped SPARQL schemes over structured assertions. Strict and
  defeasible derivations retain their premises, subarguments, objections and
  grounded labels. These researcher-only results do not control live messages.
- **Silence:** recorded for every eligible point, with its rationale. No language
  request is made for silence.
- **Corrections:** self-reports are attributed evidence, never silently promoted
  to facts. Disagreement contests the named hypothesis for a configured window;
  it lowers that candidate's policy score while alternatives remain available.
- **Traceability:** immutable input events, snapshots after evaluation and feedback,
  provenance, epistemic labels, model/policy versions, and configuration hashes
  support deterministic replay. Invalid candidate updates do not partially commit.

The epistemic core uses RDF claims with annotations and relations including
`supportedBy`, `dependsOn`, `contradicts`, `revises`, and `opposes`. Ontology 0.2
adds a shared `task:` layer and separate `mab:`/`tbs:` namespaces for mechanics,
states, observations, goals and calculations. Derived values link to input states,
named versioned rules, units and evidence; estimates remain explicitly inferred.
Python computes the models and JSON snapshots remain the canonical records.
Selected local SHACL modules validate new graph entities and their context before
commitment when pySHACL is installed. Full exported graphs can also be audited.

MAB/TBS models, event boundaries, task-specific checks and RDF projections live
in registered Python task modules. New sessions freeze module/ontology versions
and definition-file hashes; original core URIs and legacy exports remain supported.
See the [task module and extension guide](docs/task_modules.md).

The separately versioned `arg:` extension adds structured propositions, argument
schemes, rule applications and attacks. The inspector exposes derivations,
accepted/rejected/undecided labels, source records and open critical questions.
An estimate or attributed report remains uncertain even when its argument is
accepted. Argumentation definitions, backend and limits are frozen into new
sessions; older traces retain their original behaviour and export.
See the [graph argumentation guide](docs/graph_argumentation.md) for semantics,
limits, task extension hooks and synthetic examples. Restart the research server
and create a new session to inspect this analysis.

For a concrete audit of what is represented in RDF versus JSON, see the
[MAB/TBS ontology walkthrough](docs/ontology_examples/README.md), with synthetic
examples, validated Turtle exports and executable SPARQL queries.

## Information boundary

The browser task runner knows evaluator truth to sample outcomes. Its full logs
still include hidden MAB probabilities and volatility checks. **They are not sent
to the teammate service.** The browser projects an allowlist of public fields and
the server independently rejects unknown fields, including nested probabilities,
actual shifts, random draws, and future outcomes. It also validates task rules,
choice identities, horizon, target/multiplier pairing, order, and score arithmetic.

Teammate JSON/RDF and calibration contain only permitted observations. The separate
“Download logs” browser export is evaluator data; the researcher must retain it
separately for regret or hidden-state ground-truth analysis. Those browser logs
are not durably stored by this server and must be downloaded before closing the
page or starting a new task. The client-side runner is not a tamper-resistant
experiment runner; its developer tools can inspect its hidden variables.

## Optional research libraries

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-research.txt
.venv/bin/python -m socratic_prototype.server
```

`pgmpy` enables the hand-designed discrete network's exact variable-elimination
queries. Without it, a standard-library exact conditional calculation uses the
same CPTs. `rdflib` and `pyshacl` enable RDF parsing and SHACL validation. Without
those libraries, strict Python record validation runs, and the inspector reports
that SHACL **was not executed**. Runtime backends are recorded and replay rejects
backend or model/policy drift instead of claiming an old trace was reproduced.

The relevant library APIs are described in the [pgmpy inference documentation](https://pgmpy.org/examples/Inference_Discrete_BN.html)
and [pySHACL documentation](https://github.com/RDFLib/pySHACL).

## Optional bounded LLM layer

### Local Ollama (preferred)

Install [Ollama for macOS](https://ollama.com/download/mac), launch the app, then
download a local model. [Qwen3 4B](https://ollama.com/library/qwen3:4b) is a starting
point for this bounded wording task; its suitability and latency need testing.
If Ollama is already installed, skip installation. No additional Python package
or API key is required for this adapter.

```bash
ollama pull qwen3:4b
cd "/Users/martinlopeznores/Desktop/Irena Danilovska"
source .venv/bin/activate
export SOCRATIC_LLM=ollama
export OLLAMA_MODEL=qwen3:4b
python -m socratic_prototype.language --check
python -m socratic_prototype.server
```

Open `http://127.0.0.1:8765`. If the Ollama app is not running, start it or run
`OLLAMA_NO_CLOUD=1 ollama serve` in a separate Terminal. Do not start a second
Ollama server if one is already listening. For the macOS app, Ollama documents
`launchctl setenv OLLAMA_NO_CLOUD 1` followed by restarting the app to
[disable cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features).

The adapter uses Ollama's native [`/api/chat`](https://docs.ollama.com/api/chat)
and [JSON-schema structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
with streaming and thinking disabled, temperature zero, and a ten-minute
model keep-alive. It accepts loopback HTTP addresses only (default
`http://127.0.0.1:11434`, optionally set with `OLLAMA_BASE_URL`), bypasses HTTP
proxies, rejects redirects and `:cloud` model tags, and never sends OpenAI
credentials. Disable cloud features in Ollama itself too, especially if using
custom model aliases. Models must be downloaded before use; the adapter does
not pull them automatically.

`--check` exercises the actual validation with synthetic setup data and warms
the model, allowing up to 60 seconds (`--timeout` overrides that setup limit).
Success reports `ollama-bounded`; fallback reports its reason and exits with
status 1. This does not change the experiment's timing. Policy 0.2 allows
3 seconds for generation, increased from 0.8 after a successful user-reported
warm Qwen3 4B setup check took 2.79 seconds (the first took 7.85 seconds).
These checks establish connectivity and validation, not latency for actual
trial prompts. The four-second preparation period remains fixed, leaving only
about one second for reading a message arriving after three seconds, before
allowing for other backend work. Warm the model before sessions and inspect
recorded `generation_ms`, `fallback_reason` and actual reading exposure.
Late results remain unexposed. Restart the prototype server and start new
sessions to use this policy. Existing sessions retain their recorded settings;
replaying them requires the matching policy configuration. Freeze the policy
and model version before collecting study data.

### OpenAI (alternative)

The OpenAI adapter is opt-in and reads credentials only from the server environment:

```bash
export SOCRATIC_LLM=openai
export OPENAI_API_KEY='your-key'
export OPENAI_MODEL='your-structured-output-capable-model'
python3 -m socratic_prototype.server
```

This adapter uses the [Responses API and structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Both adapters may select an approved wording variant for an already-selected action and
claim list. The backend rejects different actions, fabricated evidence, arbitrary
prose, and proposed promotion of an inference to a fact. For this first version,
model updates remain the job of the deterministic model services; LLM updates
must be empty. Missing credentials, provider failures, and invalid proposals fall
back to the reviewed template and are recorded. Silence bypasses generation.
In bounded mode, only the selected action, opaque claim IDs and approved messages
go to the provider. Generated mode receives the explicitly projected evidence
described below. A complete session and hidden evaluator state are never sent.
Replay uses the recorded validated language result and makes no API calls.

### Generated questions and shadow evaluation

Start by evaluating alternatives offline. This writes a JSON report and matching
HTML review page, without changing sessions or displaying generated text to participants:

```bash
export SOCRATIC_LLM=ollama
export OLLAMA_MODEL=qwen3:4b
python -m socratic_prototype.shadow --fixtures --output shadow_report.json
```

The synthetic scenarios cover MAB/TBS uncertainty, personalisation, conventional
condition boundaries, ambiguous feedback and quoted instruction attempts. To
evaluate a new-format exported teammate trace instead:

```bash
python -m socratic_prototype.shadow --trace exported_teammate.json --output trace_review.json
```

Reports include the evidence, reviewed baseline, generated question or rejection,
latency, estimated time left in the preparation window, and unfilled human-review
fields. These estimates exclude other backend work and browser transport.
Inspect semantic grounding, uncertainty, condition fidelity and usefulness;
passing hard checks does **not** establish these qualities. JSON-schema validation
and literal evidence references do not prove that a question's meaning is supported.

For an explicitly experimental live run after reviewing shadow outputs:

```bash
export SOCRATIC_LANGUAGE_MODE=generated
python -m socratic_prototype.language --check
python -m socratic_prototype.server
```

Restart the server and start new sessions. D/F may receive a newly composed short
question after backend-rendered context. Questions must preserve the policy action
and evidence/uncertainty references; they cannot introduce model updates. Hard
checks reject numerical prose, several directive/diagnostic cues, invalid
references and malformed/overlong output. Invalid or slow generations fall back
to the reviewed message. The four-second preparation window remains fixed, and
late results remain unexposed. No second LLM call or automatic repair consumes
the remaining window. Use `SOCRATIC_LANGUAGE_MODE=bounded` to retain the original
wording-selection mode. Generated mode currently uses local Ollama only.

Optional response interpretation is separately enabled with
`export SOCRATIC_INTERPRET_RESPONSES=1` before starting new sessions. For E/F,
Ollama may propose a literal strategy quotation or contestation of the delivered
hypothesis. Proposals remain pending until accepted/rejected in the inspector.
Accepted interpretations are attributed self-reports and can affect future
hypotheses only within their original task/block and expiry window. Fitted
parameters and observed facts are never overwritten. Response generation can
add backend delay; it is separately logged. Both switches default to the original
bounded wording and disabled response interpretation.

Language mode, provider, requested model, local endpoint and contract versions
are frozen into new sessions without API keys. Replay revalidates the recorded
question/interpretation and uses recorded researcher reviews without contacting
Ollama. Older bounded traces remain inspectable; replay still requires their
original model/policy/backend and implementation versions.

See [the implementation and evaluation guide](docs/llm_generation.md) for the
output contract, researcher review workflow, and limitations.

## Descriptive summaries and verification

JSON exports contain descriptive session summaries. To collect all summaries:

```bash
python3 -m socratic_prototype.analysis --output pilot_summaries.json
```

The summaries include task outcomes, switching/exploration, response times,
timeouts, intervention/silence counts, exposure, and attributed feedback. Regret
is left uncomputed without evaluator truth. Reasoning quality, appropriate
reliance, subjective confidence, causal benefit and workload are explicitly
unmeasured. Satisfaction and compliance are not treated as effectiveness.
Primary endpoints, assignment/counterbalancing, participant consent, analysis,
and calibration-length adequacy need an agreed pilot protocol.

```bash
python3 -m unittest discover -s tests -v
node tests/test_browser_contract.cjs
node tests/test_inspector_contract.cjs
node tests/test_demo_visuals.cjs
```

The Python tests exercise both provider request/response contracts with mocked
transports, local-only Ollama routing, generated-question checks, condition-filtered
packages, shadow reporting, reviewed self-report updates, safe fallback and replay without generation,
plus all six conditions in complete short MAB/TBS sessions,
replay, correction/revision, uncertainty, information boundaries, language-output
validation, score rules and the actual HTTP handler via an in-memory transport.
The task JavaScript contract test executes the actual extended task scripts against
the real Python store, using a minimal DOM and accelerated clock. It verifies
complete task runs, delivery, persistence, replay, and the public event contract;
it does not establish real-browser appearance or physical timing. A separate
inspector contract test executes the actual review controls and verifies acceptance
requests, reviewed-state rendering and preservation of past decisions.

The current catalog contains 82 Python tests. Task-module checks cover a third
task through the common pipeline, version/document drift, legacy compatibility,
numerical RDF provenance and conditional multiplier behaviour. Eighteen graph
argumentation tests cover multi-step discovery, independent objections, grounded
cycles/defence, priorities, attack propagation, state isolation, attributed
contestation, epistemic preservation, construction limits, shadow-only behaviour,
SHACL integrity and replay. RDF-dependent tests skip explicitly without the
research libraries; a local socket test can also skip where binding is forbidden.

MAB/TBS task and inspector JavaScript contract tests passed, including fixed
preparation timing and interpretation review. Complete short generated-mode
MAB/TBS sessions and replay passed with a mocked provider, with and without the
research libraries. Earlier scripted full protocols completed and replayed:
MAB 200 choices and TBS 192 choices.

Live HTTP transport, visual browser QA and live generated questions for trial
prompts remain unverified. Ollama's loopback API was unreachable from the
implementation session; generated-mode setup and shadow CLI checks correctly
reported fallback and wrote separate reports. The user previously reported
successful bounded setup checks with Qwen3 4B: 7.85 seconds initially and
2.79 seconds warm. Those timings do not establish performance of the new question
or response-generation prompts. Both provider transports passed mocked tests.
No model or intervention effect is empirically validated.

## Deliberate modelling limits

The briefing's fitted participant models and original analysis scripts were not
supplied. The prototype does not pretend to reproduce them. MAB's change belief
compares unknown categorical regimes, not the original-vs-swapped ideal observer
with known likelihoods. It is bounded by the participant-visible information;
initial hidden reward probabilities are never supplied as priors. TBS pressure
sensitivity is a proposed, coarse extension, with option-value and horizon effects
not separately identified. Its posteriors do not establish intent or neglect.

`policy.json` and the Bayesian CPTs in `bayes.py` are explicit **provisional**
parameters. They are frozen into each session, not claimed optimal or preregistered.
Sensitivity/calibration studies, independent effectiveness evaluation, original
model integration, and richer statistical analysis (e.g. PyMC) remain research
work. The purpose of this milestone is a runnable, inspectable intervention loop.
