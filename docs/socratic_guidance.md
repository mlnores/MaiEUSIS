# Evidence-backed Socratic guidance

Updated on **14 November 2026**. MAB now uses a
[performance gate and shared top-two ranking](simulation/mab-shared-ranking.md):
C/E recommend rank 1, while D/F compare ranks 1 and 2. Successful persistence
alone does not trigger intervention. The synthetic actor weights the pair using
its own learned preferences, then blends that target with baseline preferences
according to receptiveness. TBS retains the 11 November mechanism.

On **15 November**, [observed-behaviour personalisation](observed_personalisation.md)
added online task forecasts and separate direct/Socratic uptake estimates to E/F.
These can change delivery relevance and cooldowns without changing the public
ranking, comparison set or performance gate. Private actor receptiveness remains
hidden; the assistant learns a conditional estimate from exposed choices.

Initially implemented on 11 November 2026. In D/F, the teammate guides deliberation by
showing alternatives worth examining, their evidence and uncertainty, alongside
a Socratic question. C/E continue to prescribe one graph-supported action under
their stated comparison criterion. Guidance works with reviewed wording; Ollama
can compose the question through the existing generated-language mode.

## What the participant sees

MAB shows exactly two named options from the shared reward ranking, with existing keys, observed sample
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

The new MAB default derives both direct advice and Socratic comparisons from
the same scoped rank calculations. `mab_performance.ttl` supplies the performance
warrant that every delivered C/D/E/F candidate must include. The policy still
applies its threshold, cooldown and frequency preference after this gate passes.

For the **original MAB uncertainty shortlist**, retained as an explicit ablation
setting, the public reward estimates supply a benchmark equal to the
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
when fewer than two have accepted reasons. With the performance gate explicitly
disabled for an ablation, existing short-horizon objections can still lead to a
cost-clarification question. The new default remains silent with fewer than
three decisions remaining.

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

The human-facing comparison set is distinct from the actor's response. New
runs use [one participant-response rule](simulation/single-response.md), without
`none` or `recent` variants. MAB conditions the actor's full-history learned
preferences on the offered pair, using the same operation as a direct singleton.
Receptiveness blends either target with baseline preferences. Ordinary profile
learning continues, with no additional memory reset or uncertainty bonus.

TBS retains its default response to displayed gain/chance and goal information.
Conditioning on its two-option pair would leave baseline probabilities unchanged;
that MAB rule has therefore not been silently substituted for TBS's existing
response. There are no TBS memory variants either. Future tasks provide one
explicit response hook.

Zero receptiveness, with zero added distraction/omission, is the no-response
control. These remain authored behavioural assumptions, not measured human
acceptance or natural-language comprehension. No automatic reward or
personalisation bonus is added.

## Versions, existing results and running

New sessions use policy 0.6, argumentation 0.4, grounding 0.3 and structured
interventions 0.3. Simulation/actor versions are 0.6; the MAB execution adapter is
0.6 and TBS is 0.5. Assistance response is 0.3. Graph configuration records comparison-guidance version and source
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
and should use the single response rule with matched repetitions. The historical
[new guided full-protocol pilot](simulation/guidance-pilot.md) was launched on
11 November and completed on 13 November 2026 with three repetitions, 144 jobs
and all three mechanisms. Its [final report](simulation/guidance-pilot.md#final-heatmap-report)
uses all completed repetitions; the earlier pilot and capped check remain separate.

## Verification of the 11 November version

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
