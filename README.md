# Socratic teammate prototype

A local, runnable first prototype for the controlled MAB and TBS tasks in
`socratic_ai_design_note.tex`, informed by *The Sophist Machine Needs Productive
Ignorance* and `MeetingNotes_SocraticAIforDecisionMaking.pdf` (13 October 2026).
The original `mab_tbs_web_demo` is preserved. The prototype extends a copy of its
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

The default language layer uses reviewed templates in every condition. Calling
these an empirical comparison of LLM systems would require enabling and piloting
the provider layer, fixing its model/version, and agreeing the study protocol.

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
- **Silence:** recorded for every eligible point, with its rationale. No language
  request is made for silence.
- **Corrections:** self-reports are attributed evidence, never silently promoted
  to facts. Disagreement contests the named hypothesis for a configured window;
  it lowers that candidate's policy score while alternatives remain available.
- **Traceability:** immutable input events, snapshots after evaluation and feedback,
  provenance, epistemic labels, model/policy versions, and configuration hashes
  support deterministic replay. Invalid candidate updates do not partially commit.

The schema uses RDF claim objects with annotations and relations including
`supportedBy`, `dependsOn`, `contradicts`, `revises`, and `opposes`. The fixed
ontology is in `socratic_prototype/ontology/schema.ttl`; hand-written SHACL shapes
cover trials, claims, hypotheses, and interventions. JSON snapshots are the
canonical persisted records and Turtle is the inspectable graph projection.
The JSON validator runs before commitment. When pySHACL is installed, the
candidate RDF graph also must conform before commitment, and the report is stored.

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

The OpenAI adapter is opt-in and reads credentials only from the server environment:

```bash
export SOCRATIC_LLM=openai
export OPENAI_API_KEY='your-key'
export OPENAI_MODEL='your-structured-output-capable-model'
python3 -m socratic_prototype.server
```

This adapter uses the [Responses API and structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
It may select an approved wording variant for an already-selected action and
claim list. The backend rejects different actions, fabricated evidence, arbitrary
prose, and proposed promotion of an inference to a fact. For this first version,
model updates remain the job of the deterministic model services; LLM updates
must be empty. Missing credentials, provider failures, and invalid proposals fall
back to the reviewed template and are recorded. Silence bypasses generation.
Only the selected action, opaque claim IDs and approved messages go to the
provider; no raw participant text, hidden schedule, or complete session is sent.
Replay uses the recorded validated language result and makes no API calls.

This is deliberately bounded language realisation, not an open-ended conversational
teammate. Free prose generation with a reliable grounding validator is later work.
The short generation timeout is provisional and may cause frequent fallback;
it needs latency testing before an LLM comparison study.

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
```

The Python tests exercise all six conditions in complete short MAB/TBS sessions,
replay, correction/revision, uncertainty, information boundaries, language-output
validation, score rules and the actual HTTP handler via an in-memory transport.
The JavaScript contract test executes the actual extended task scripts against
the real Python store, using a minimal DOM and accelerated clock. It verifies
complete task runs, delivery, persistence, replay, and the public event contract;
it does not establish real-browser appearance or physical timing.

Verification in the implementation environment: 28 Python tests, 26 passed and
2 skipped (local socket binding prohibited; optional pySHACL unavailable).
The MAB/TBS JavaScript contract runs passed, including fixed preparation timing.
Scripted full protocols also completed and replayed correctly: MAB 200 choices
and TBS 192 choices. Package installation and real browser
launch were blocked, so pgmpy/pySHACL execution, live HTTP transport, visual browser
QA and live LLM calls remain unverified. No model is empirically validated.

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
