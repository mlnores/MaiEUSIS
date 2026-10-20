# Graph argumentation and intervention policy

New sessions use `argumentation-0.2` in live mode with `policy-0.3`. Graph
argumentation is the single source of substantive reasons and objections. There
is no independent Python candidate-trigger mechanism. The engine computes models
and annotated claims, discovers and validates the graph, maps proof-backed
conclusions to communication candidates, then applies the delivery policy.

RDFLib is required for assistance. Without it the task can still run, but reasoning
is explicitly unavailable and the policy stays silent. No old trigger mechanism
is used as a fallback. Complete reasoning is also required: limited construction
cannot authorize an intervention.

This is a small, explicit structured argumentation implementation. It is inspired
by strict/defeasible rules and attacks on premises, conclusions and rule applications
in [ASPIC+](https://webspace.science.uu.nl/~prakk101/pubs/ASPICtutorial.pdf), but is
not a complete ASPIC+ implementation or a general classical-logic reasoner.

## Data and execution

The shared extension uses `arg: <https://example.org/socratic/argumentation/>`.
Its vocabulary, shapes and shared schemes are under
[`socratic_prototype/argumentation/`](../socratic_prototype/argumentation/).
MAB and TBS provide separate scheme packs through optional task hooks. The existing
core/task/domain ontology files and their frozen descriptors are unchanged.

```mermaid
flowchart LR
  R[Current typed task records] --> C[Structured assertions]
  C --> Q[SPARQL scheme matches]
  Q --> A[Arguments and subarguments]
  A --> D[Attacks and propagated defeats]
  D --> L[Grounded labels]
  L --> P[Condition and delivery policy]
  P --> W[Validated wording and fixed-window delivery]
  L --> I[Researcher inspector and exports]
```

For each evaluation snapshot the reasoner builds a local graph from the actual
task RDF projection. It wraps relevant numerical records as assertions, preserving
their sources and kinds. MAB contributes observed-choice counts, sampled-arm count
and remaining decisions as typed history summaries. Eligible model hypotheses
become provisional model premises. Disagreement and accepted strategy quotations
retain participant attribution and source event identifiers.

An assertion has a structured proposition: subject, predicate, typed object,
positive/negative polarity and current-state scope. The assertion also has a kind,
epistemic statuses and source. Propositions are not asserted as unqualified facts
about the participant. A recorded model estimate or quoted report stays an estimate
or report, including when its premise argument is labelled accepted.

Rules operate on assertion indexes that mirror those propositions. SHACL checks
that the indexes equal the canonical proposition values. Every match must return
actual assertion identifiers from the same current state. Queries are SELECT-only,
locally authored and versioned; network SERVICE queries and updates are rejected.
Participant text and LLM output cannot become executable queries or rules.

Each match creates an argument with a conclusion assertion, premise identifiers,
subarguments, scheme, inference kind and explicit priority. Rules run in a bounded
forward sequence so a derived conclusion can support another argument. Content-derived
identifiers, sorted matches and fixed rule order make replay deterministic. Circular
proofs are excluded. Independent proofs of the same proposition remain distinct.

All input assertions participate in discovery. Stored reports retain complete
premises/conclusions for every constructed proof, plus attributed reports. Unrelated
numerical records remain in the canonical task snapshots and task RDF, avoiding
another copy of every quantity in every reasoning report.

## Initial schemes

| Pack | Discovered arguments |
| --- | --- |
| Shared | A preparation point permits considering a generic reminder; an eligible provisional model interpretation warrants considering a challenge; explicit participant contestation undercuts that model-to-challenge inference pending verification |
| MAB | At least six observed choices leave some arms unsampled; this coverage gap warrants discussing exploration; a horizon of two or fewer decisions supports an objection and undercuts personalised underexploration challenges; sampled change estimates can warrant checking for change; observed histories permit a revision question |
| TBS | Compare expected gains and final-choice attainment; detect diverging rankings and clarify objectives; discuss conditional final-win dependence, the shrinking horizon, and a changed gap after a recorded gain |

MAB's coverage argument is strict arithmetic about observed counts. Its exploration
argument is defeasible: limited coverage does not establish that further exploration
is worthwhile. The short-horizon objection has its own count premise. With the
default equal priorities, these contrary arguments remain undecided rather than
one being declared the winner.

For the synthetic TBS final-choice example, safe has EV 108 versus risky's 91,
while risky has attainment probability 0.35 versus safe's zero. Separate strict
comparisons support a third argument that the criteria rank the options differently.
A defeasible argument then supports clarifying the objective. These compatible
comparisons do not attack one another and do not prove which option the participant
ought to choose. No current scheme claims knowledge of the participant's objective.

Strict inference preserves uncertainty: a strict consequence of estimated premises
remains inferred. Known conclusions require a strict rule and exclusively known
premises. The numerical models and Bayesian probabilities are not recalculated by
the argument evaluator.

## From proofs to interventions

A scheme can include reviewed presentation metadata: `arg:issue`, `arg:audience`,
`arg:conventionalMessage`, `arg:socraticMessage`, `arg:socraticAction`, provisional
`arg:usefulness`, and `arg:schedule` (`event`, `periodic`, or `fallback`). This
metadata does not add premises or change argument priorities. `discovery.py` stores
it with the constructed argument. `intervention_policy.py` maps only those graph
arguments into communication candidates; it does not inspect reward sequences or
recreate behavioural triggers.

- **A/calibration:** always silent, even when the graph contains accepted warrants.
- **B:** only generic reminder warrants, scheduled every fourth trial by default.
- **C/D:** task warrants only; no personalised model-challenge candidates. D uses
  questions, C conventional guidance.
- **E/F:** task warrants plus personalised model-challenge warrants. E advises,
  F asks/challenges. Calibrated task profiles retain their existing boundaries.

Accepted warrants may form candidates. Rejected warrants are excluded regardless
of their usefulness. An undecided warrant can form a clarification candidate only
in D/F when the scheme explicitly supplies `arg:clarificationMessage` and names
its expected attacker with `arg:clarificationObjection`. The actual attacking
argument must be present. At the end of MAB, the opposed exploration arguments
therefore support a question about exploration costs; they do not authorize
conventional exploration advice. A separate short-horizon undercutter blocks a
personalised underexploration challenge while leaving the cost clarification open.

Candidates carry unique IDs, graph scope, supporting and opposing argument IDs,
and the argument evaluation. The policy filters audiences and schedules, applies
provisional usefulness minus interruption cost, and enforces cooldown from actual
delivery acknowledgements. Personalised usefulness comes from the existing model
estimate plus its personalisation bonus. It cannot restore a defeated warrant.
Fallback support is considered only when no other permitted candidate is available.

The decision stores `reasoning_source: graph`, `selected_candidate`, `argument_ids`
and `opposing_argument_ids`. Python validation checks these links and excludes
rejected/undecided advice. RDF links interventions to arguments with
`arg:justifiedBy` and `arg:consideredObjection`. The inspector shows candidate
scores and proof links alongside the full graph. Historical `snapshot.arguments`
records remain displayable, but new snapshots leave that old independent-reason
list empty.

Language packages contain only the selected proof closure and its actual attackers,
including assertion kinds/statuses and open critical questions. They never receive
the entire research graph. B remains generic; C/D exclude personalised premises.
An absent graph objection is represented as an empty opposition, not an invented
counterargument. Possible explanations on model claims remain uncertainty metadata,
not fabricated attacking arguments. Bounded or generated language cannot change
policy selection, graph labels or model claims.

The four-second preparation window, five-second choice window, generation deadline,
frequency controls, feedback/review semantics and actual-exposure logging remain
in force. Numerical task models and task mechanics are unchanged.

## Objections, defeat and labels

The initial conflict language requires an explicit opposite polarity over the same
subject, predicate, typed object and state. Missing data is not negation, different
states are not contradictions, and different comparison criteria are not contraries.
Additional domain-specific contraries would need an explicit extension.

- **Undermining** targets a contrary ordinary premise: an assumption, report or estimate.
- **Rebutting** targets the contrary conclusion of a defeasible rule application.
- **Undercutting** targets applicability of a named defeasible scheme to the same subject.

Rebuttal and undermining succeed when the attacker is not less preferred than the
targeted argument. Undercutting is independent of these priorities. The initial packs
use equal priorities; Bayesian confidence and intervention usefulness are not argument
priorities. A successful attack also defeats proofs containing the targeted subargument.

Grounded labelling iteratively accepts arguments whose defeaters are rejected and
rejects arguments with an accepted defeater; unresolved cycles remain undecided.
Labels express justification under this finite rule system, not truth or measured
intervention benefit. Inconsistent accepted strict conclusions are rejected as a
rule/premise integrity error, rather than being presented as jointly justified.
The implementation does not supply arbitrary logical closure, automatic priority
learning, preferred-extension enumeration or unrestricted argument mining. Related
issues are not automatically equated. The explicit short-horizon challenge
undercutter connects horizon evidence to a personalised underexploration challenge;
other connections still require authored schemes.

Critical questions are attached to rules and shown in the inspector. An unanswered
question is not a fabricated objection. No rule infers unobserved intention, neglect
or irrationality from a missing explanation. Explicit contestation undercuts the
particular model-to-challenge inference; it does not refute logged choices or revise
the Bayesian posterior. Reports and contestation follow the existing scope/expiry
rules, and later snapshots are recomputed without overwriting past analyses.
Re-analysing an earlier event uses only its event-history prefix, excluding later
feedback and researcher reviews.

## Integrity, dependencies and timing

New sessions freeze reasoner version, mode, semantics, RDFLib version, construction
limits and SHA-256 hashes of the schema, shapes and selected scheme packs. Store
ingestion and replay reject drift. Source changes require corresponding version
discipline, just as for the existing model implementations. Historical sessions retain their stored snapshots and exports. They are not
automatically migrated: new input is refused and replay requires the recorded
software version. Restart the server and create a new session for the live policy.

Record validation checks links, proof acyclicity, scope, epistemic preservation and
grounded labels. With pySHACL installed, the normal candidate-event graph validation
also checks the argumentation projection; full graph validation remains available.
RDFLib is the required reasoning dependency (`requirements.txt`). If absent when a session starts,
the analysis explicitly reports `unavailable`; it does not claim reasoning executed.
Install the requirements and start a new session to enable assistance.

Construction is bounded to six rounds, 256 arguments, 512 assertions and 1,024
matches per snapshot. A limited construction labels all arguments undecided because
an omitted argument could defeat one already found. These are construction limits,
not a hard real-time guarantee for arbitrary custom SPARQL queries.

Graph reasoning adds backend work. The four-second preparation window and generation
deadline are unchanged; live display latency still requires a pilot. Benchmark graph
discovery separately from model calculation, SHACL, persistence, generation and browser
transport, and inspect actual exposure before any study use.

## Running and extending

```bash
.venv/bin/python -m socratic_prototype.server
.venv/bin/python -m socratic_prototype.argumentation.examples --output /tmp/argumentation_examples.json
.venv/bin/python -m unittest discover -s tests -p test_argumentation.py -v
```

Restart the server and create a new session. Open an evaluation snapshot in the
researcher inspector to see labels, rules, premises, subarguments, attacks, open
questions and the complete report. The example command creates synthetic partial unassisted
MAB/TBS sessions in a temporary database, verifies replay without generation and
writes three reasoning cases plus a local discovery-only timing sample. These
are condition A, so their live policy remains silent despite accepted warrants. It neither
reads nor changes participant stores.
The checked-in [synthetic example report](argumentation_examples.json) illustrates
accepted MAB exploration arguments, undecided short-horizon objections and the TBS
comparison chain, with the frozen definitions and replay results.

A new task can provide `argumentation_documents()` returning its local scheme files
and `project_argumentation_facts(...)` for additional public-history aggregates.
Neither hook is mandatory for existing tasks. Schemes declare strict/defeasible
kind, premise variable names, conclusion subject/object bindings, polarity, priority,
reason and critical questions. Keep predicates in the task's own namespace, declare
them in its pack, and explicitly scope every query to the bound current state.
The shared loader checks that returned premises resolve to that state's assertions.

The delivery integration is exercised separately in `tests/test_graph_policy.py`,
including all condition projections, generic and task-only proof boundaries,
removal of necessary premises, rejected personalised warrants, unresolved
clarification, TBS comparison chains, cross-block isolation, unavailable/limited
reasoning and tampered decision-proof links. Complete MAB/TBS runs, actual browser
script contracts, mocked language providers and deterministic replay have their
existing integration tests.
