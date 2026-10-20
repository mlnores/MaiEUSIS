# Generated language: implementation and evaluation

The prototype now supports newly composed Socratic questions and proposed
interpretations of participant responses. These are experimental capabilities.
The model services and policy continue to decide which intervention is warranted.

## Evaluate offline first

With Ollama running and the model downloaded, activate the project environment:

```bash
cd "/Users/martinlopeznores/Desktop/Irena Danilovska"
source .venv/bin/activate
export SOCRATIC_LLM=ollama
export OLLAMA_MODEL=qwen3:4b
python -m socratic_prototype.shadow --fixtures --output shadow_report.json
```

Open `shadow_report.html`. The matching JSON contains all case inputs, outputs,
rejections, timing estimates and human-review fields. Synthetic fixtures are
labelled and are not evidence of effects on human decisions. Their calibration
values are illustrative, not fitted participant data. Repeat generation to assess
variation and warm/cold latency:

```bash
python -m socratic_prototype.shadow --fixtures --repeats 3 --timeout 15 --output repeated_review.json
```

The offline timeout does not change experiment timing. The report compares elapsed
generation time against the recorded live generation budget and estimates how
much of the preparation window remains. Backend graph validation, saving and
browser transport take additional time. A passing setup check or an estimated
positive reading window does not establish adequate exposure. Summary latency
quantiles include only questions that passed hard checks; failed-attempt timings
remain visible per case and cannot make successful generation appear faster.

To use actual recorded contexts, export teammate JSON from the inspector and run:

```bash
python -m socratic_prototype.shadow --trace exported_teammate.json --output trace_review.json
```

The command only reads the source file and writes separate reports. It never
opens the session database or modifies participant records. It uses frozen
evidence packages rather than recomputing historical state using new models.
Trace provenance is not assumed to be human: a null `synthetic` field means that
the source trace did not explicitly classify it. Older traces without packages
are skipped with a reason. `--limit` defaults to
20 cases. Exit status 1 indicates that no generated question passed hard checks;
inspect the report for provider failures, rejections or skipped cases. A zero
exit status establishes only that at least one question passed hard checks.

## What the generator receives

`grounding.build_evidence_package` projects allowed data into a versioned record.
It never forwards a whole session or snapshot.

| Condition | Evidence supplied |
| --- | --- |
| A | No generation or package |
| B | Generic guidance only; no task identity, state, history or participant profile |
| C/D | Relevant public observations, environment estimates, unknowns and opposing reasons; no calibrated participant model |
| E/F | The task evidence plus task-specific calibration and researcher-reviewed self-reports |

Only D/F use the generated-question path. B/C/E keep their conventional reviewed
messages in generated mode. Their packages remain inspectable for auditing.
MAB input excludes upcoming options, hidden reward probabilities and actual shift
times. TBS input includes current published probabilities and constraints, with
future options and outcomes explicitly unknown. Observations, estimates,
hypotheses and reports retain their distinctions.

Compact references (`e0`, `e1`, `u0`) map to full source claim identifiers in the
stored package. Internal identifiers are omitted from the compact provider input.
This reduces output overhead while preserving traceability. Supporting and
opposing reasons and revision conditions accompany the selected issue.

## Question output and validation

Ollama receives JSON-schema-constrained instructions and returns a record like:

```json
{
  "action": "ask",
  "evidence_refs": ["e0"],
  "uncertainty_refs": ["u0"],
  "question": "What evidence would justify reconsidering your current approach?",
  "updates": []
}
```

The backend checks the exact action and ordered evidence/uncertainty references,
an empty update list, one single-line English question of 5–24 words and at most
180 characters, and selected numerical, diagnostic, certainty and directive cues.
Numerical task context is rendered from backend values, outside the generated
question. The validated result records `semantic_grounding: unverified`.

These checks **cannot prove semantic entailment**. A grammatically valid question
can still contain an unjustified presupposition, misrepresent an objection, or
be unhelpful. Neither JSON schema, citations nor keyword filters establish the
truth or usefulness of its meaning. There is no second model presented as an
authoritative semantic judge. The offline review must examine these properties.

For each case, assess:

1. Does every presupposition follow from permitted evidence, without converting
   an estimate or report into an observed fact?
2. Does the question preserve uncertainty and plausible alternatives?
3. Does it preserve the assigned condition and selected intervention intent?
4. Does it invite useful reflection while leaving the choice to the participant?
5. Is the question readable in the exposure actually available?

The JSON includes initially null human-review fields and notes for recording
these judgments manually. The summary intentionally does not infer approval from
hard-check success or automatically enable live generation. Establish the review
criteria and acceptable error/latency rates before collecting study data.

## Experimental live mode

After assessing shadow outputs, configure a new local run:

```bash
export SOCRATIC_LANGUAGE_MODE=generated
python -m socratic_prototype.language --check
python -m socratic_prototype.server
```

In this mode `--check` tests a synthetic evidence-grounded question, rather than
only the old wording selector. `ollama-generated` means structural checks passed;
semantic grounding remains unverified. The current three-second generation budget
and four-second preparation period remain fixed. One generation attempt is made.
Failure or rejection uses the existing reviewed message. Messages arriving after
preparation closes are not shown. Measure delivery, exposure, backend overhead
and fallback frequency in realistic sessions.

This mode changes how D/F messages are produced. It therefore needs an explicit
study protocol; do not pool differently configured runs as if language mode and
exposure were identical. The default remains `SOCRATIC_LANGUAGE_MODE=bounded`.
This new contract is currently implemented for local Ollama. The existing OpenAI
bounded adapter remains available unchanged in scope.

## Proposed interpretations and researcher review

Optionally set `SOCRATIC_INTERPRET_RESPONSES=1` before creating sessions. For E/F,
text submitted after exposed assistance may produce at most two typed proposals:

- `reported_strategy`: a literal quotation of the participant's strategy report.
- `contest_hypothesis`: a literal quotation proposing contestation of the
  hypothesis associated with the delivered intervention.

Each proposal must quote a contiguous passage of the recorded response and use
only the delivered hypothesis. Fitted parameters, model probabilities and observed
facts cannot be rewritten. Ambiguity or provider failure produces no applied
update. A literal quotation supports provenance; it does not establish the
correctness of the proposed interpretation, particularly when negation or quoted
instructions occur. Raw participant text is sent only for this opt-in extraction;
the generated-question package receives researcher-reviewed report quotations.

Open the inspector, select the intervention, and expand its response interpretation.
Inspect the quote against the full response. Enter a researcher pseudonym and
accept or reject the whole proposal. Acceptance creates an immutable
`interpretation-review` event; it does not edit past events or messages. Pending
or rejected proposals have no effect on the participant model. Existing explicit
feedback controls, such as disagreement and fewer prompts, continue to work
independently of LLM extraction.

Accepted reports appear in future annotated claims as source-dependent,
requiring verification. An accepted contestation can lower the corresponding
future candidate's score, preserving competing explanations. Reports expire by
the original response trial and stay within the task and TBS block. Reviews after
a session finishes remain auditable but cannot change its past decisions.
Extraction latency is recorded separately and can add backend delay.

## Versioning and replay

New sessions freeze language provider, requested model, endpoint, mode, extraction
flag and contract versions in their configuration hash. Credentials are not
stored. Model tags can change outside the application: retain the actual Ollama
model artifact/version for a study. The program does not claim that a model name
alone identifies immutable weights.

Replay checks frozen evidence-package digests, question output and deterministic
rendering, source quotations and recorded review events. It reuses recorded
language/extraction outputs and makes no provider calls, even if environment
settings subsequently change. Model/policy/backend or contract drift still
requires the matching original runtime. Export and inspection remain available
for old sessions; the legacy bounded replay path is retained.
