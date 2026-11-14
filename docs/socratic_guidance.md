# Evidence-backed Socratic guidance

Implemented on 11 November 2026. In D/F, the teammate guides deliberation by
showing alternatives worth examining, their evidence and uncertainty, alongside
a Socratic question. C/E continue to prescribe one graph-supported action under
their stated comparison criterion. Guidance works with reviewed wording; Ollama
can compose the question through the existing generated-language mode.

## What the participant sees

MAB can show two or three named options with their existing keys, observed sample
counts, estimated mean rewards and approximate intervals. An unobserved option
is explicitly described as prior-based uncertainty, rather than a demonstrated
good reward. The accompanying question asks what evidence or comparison would
justify revising a choice. The panel keeps the alternatives readable alongside
the question and dims both when the intervention becomes silent.

TBS shows SAFE and RISKY with their amounts, win probabilities and immediate
expected gains, together with the target gap and remaining choices. On the final
trial it additionally shows exact current target-attainment chances, including
zero, with the multiplier conditional on a win. Before that final trial it does
not present immediate expected gain as a multi-trial attainment probability.
**Current TBS offer details remain hidden throughout preparation** and appear
alongside the task options at evaluation onset. MAB comparison evidence can be
shown during preparation because it concerns previously observed outcomes.

The browser logs `INTERVENTION_COMPARISON_DISPLAY`, selected option IDs, and total
comparison visibility time. Existing choice deadlines, response keys, reward
sampling, stage transitions and scoring are unchanged. Visibility is not proof
of reading or comprehension.

## Graph reasons and selection

`argumentation/schemes/mab_comparisons.ttl` and `tbs_comparisons.ttl` derive
`arg:worthComparingFor` propositions. These are comparison opportunities, not
recommendations or participant probability distributions.

For MAB, the current public reward estimates supply a benchmark equal to the
greatest estimated mean across all six arms. Its RDF calculation links all six
input estimates and its versioned numerical rule. A defeasible comparison reason
requires an option's approximate upper bound to reach that benchmark, plus:

- **Plausible reward:** at least three non-timeout observations of that option.
- **Informative uncertainty:** fewer than six observations and more than two
  decisions remaining. Unsampled options may qualify through their explicit prior
  uncertainty; this does not establish that their rewards are good.

Among accepted opportunities, the presentation retains a sampled reward anchor
when available, then ranks alternatives by potential headroom above the benchmark
divided by one plus the sample count. It shows at most three options. This is an
authored proxy for worthwhile comparison, not a formal value-of-information
calculation or an optimal exploration policy. No second option is fabricated
when fewer than two have accepted reasons. Existing short-horizon objections
still lead to a cost-clarification question rather than pressure to explore.

For TBS, separate strict arguments support examining each displayed gain/chance
tradeoff and, when applicable, each final-trial attainment calculation. Both
options can be relevant to comparing objectives even when one has zero chance
of reaching the target. Presentation does not label both equally good.

The shared `comparisons.py` selects only accepted propositions in the current
graph scope. Each entry carries option identity, key, criteria, public quantities
and proof IDs. Those proofs enter the selected intervention, evidence package,
inspector and RDF justification links. Delivery validation reconstructs the set
and its text from the graph/environment, rejecting changed quantities, unsupported
alternatives or mismatched proof links. C/D evidence does not acquire E/F personal
model premises through these public comparisons.

## Synthetic participant processing

The human-facing comparison set is distinct from the actor's response. No choice
probabilities are prescribed to the human. For new structured interventions:

- `none` retains baseline preferences, including ordinary outcome learning.
- MAB `current` reassesses the delivered alternatives using the public rolling
  reward estimates. Exploration weights combine reward plausibility above the
  greatest lower bound with interval width divided by one plus the sample count.
  Other questions use reward-based softmax within the set. Options outside the
  set receive zero reconsideration-target weight; responsiveness still blends
  this target with the full baseline preference.
- MAB `recent` computes those weights from the last six elapsed trials while
  retaining the alternatives actually presented. Misses consume memory positions
  but supply no reward observations.
- TBS `current` addresses the issue: an expected-gain question compares expected
  gains; final-trial questions examine conditional attainment; other goal/horizon
  questions retain the existing gap-sensitive heuristic. TBS `recent` uses its
  recorded four-pseudo-observation perception rule before the same processing.
- An empty comparison set leaves baseline preferences intact under all three
  mechanisms. Legacy researcher fixtures without the new comparison field retain
  the older processing rule; new MAB/TBS interventions always have the field.
  Tasks without the optional comparison hooks retain their existing processors.

These remain authored behavioral assumptions, not natural-language comprehension
or measured human effects. Responsiveness is unchanged and does not learn from
outcomes. No automatic score or personalization bonus has been added.

## Versions, existing results and running

New sessions use policy 0.5, argumentation 0.4, grounding 0.3 and structured
interventions 0.2. Simulation/actor versions are 0.5 and MAB/TBS execution adapters
are 0.4. Graph configuration records comparison-guidance version and source
fingerprints. Optional task-owned hooks (`select_comparisons`,
`comparison_context`, `comparison_evaluation`) support future environments;
the registry requires the complete hook set when any is supplied.

Restart the server and create new comparison sessions:

```bash
SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
  .venv/bin/python -m socratic_prototype.server --data-dir /tmp/maieusis-guided
```

Complete or supply compatible calibrations in that data store, then choose D/F.
The earlier development-16 pilot remains an unchanged historical baseline. Its
scores were produced by the earlier heuristics and do not measure this guidance.
Historical records remain readable/exportable; replay and resumed experiments
require their recorded software. New experiments need a new output directory
and should retain all three mechanisms and matched repetitions. The
[new guided full-protocol pilot](simulation/guidance-pilot.md) was launched on
11 November and completed on 13 November 2026 with three repetitions, 144 jobs
and all three mechanisms. Its [final report](simulation/guidance-pilot.md#final-heatmap-report)
uses all completed repetitions; the earlier pilot and capped check remain separate.

## Verification

The Python regression run completed 128 tests with one socket-binding check
skipped by the environment. All six focused guidance tests passed, including
rejected/missing proofs, changed comparison quantities, unpromising undersampled
options, condition separation, generated-language replay and the optional task
extension. The third-environment suite passed after the compatibility check.

The actual participant scripts passed complete short MAB/TBS runs with timing,
input, scoring, persistence and replay checks. The presentation contract verifies
that TBS offer details stay absent during preparation, appear at evaluation and
remain readable while silent. Inspector, selector and full/short standalone task
contracts passed. These DOM-based checks do not establish native browser layout
or physical display timing; live Ollama generation latency was not measured.

The separate local `socratic_prototype/data/guidance_check_20261111/` engineering
run used one existing development actor export with all three mechanisms. It
completed six full short calibrations and 30 comparisons capped at eight trials.
All six cross-mechanism controls and four no-revision controls passed; six F
sessions replayed exactly. Public traces excluded private actor/response fields.
`checks.json` records actual comparison text and proofs. Capped comparisons were
excluded from full-protocol outcome estimates; these checks establish software
behavior, not a performance benefit.
