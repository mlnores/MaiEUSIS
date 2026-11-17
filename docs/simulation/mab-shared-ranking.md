# MAB: performance-gated guidance from a shared ranking

Implemented on **14 November 2026**, following the receptiveness experiment.
The later [single-response simplification](single-response.md) removes the
`none`/`recent` variants from new runs.
The [fresh fair comparison](fair-mab-receptiveness.md) completed on 15 November
under this shared-ranking, single-response design. Subsequent
[observed-behaviour personalisation](../observed_personalisation.md) changes
delivery in E/F; completed reports retain their recorded preceding policy.

## Rationale and shared evidence

Limited exploration is not itself poor performance. A participant repeatedly
choosing a rewarding option should not be urged to explore merely because other
options remain unsampled. The previous Socratic processor also rewarded uncertainty
within its shortlist; it could therefore divert choices toward sparse evidence
even when this reduced rewards. This is a possible explanation of the earlier
results, not an established causal finding.

New MAB guidance separates three decisions:

1. The public reward model supplies **one ranking** for every assistance style.
2. A graph-backed performance screen and the ordinary intervention policy decide
   whether interruption is warranted.
3. The participant model decides how to respond to the offered information.

The ranking uses the existing rolling Dirichlet mean from the last 24 completed
outcomes per arm. It orders all six options by descending estimated mean, then
ascending option ID for exact ties in the recorded estimates. A tie-break is a
presentation convention, not evidence that one option is better. Unsampled options
retain the existing zero-mean symmetric prior and are described as prior-based.
No hidden probabilities, future rewards, synthetic actor parameters or original
archetype labels enter the ranking.

**C/E direct advice recommends rank 1. D/F Socratic guidance presents exactly
ranks 1 and 2**, with keys, sample counts, estimated rewards, uncertainty and
ties. It asks the participant to compare the evidence. The pair can contain the
participant's current favourite; switching is not compulsory. E/F retain their
existing personalised hypotheses, calibration evidence and interruption-cost
adaptation. Personalisation does not supply a different private ranking.

Both recommendations and comparison entries have accepted graph proofs rooted
in the same rank calculations. Each calculation links all six public reward
estimates. Missing/rejected pair proofs prevent Socratic delivery rather than
manufacturing another alternative. Reasons and objections still come exclusively
from the argument graph; the policy schedules their communication.

## Performance gate

Defaults are recorded under `mab_guidance` in
[`policy.json`](../../socratic_prototype/policy.json). At an eligible evaluation
point, consider the last **12 elapsed trials**. Misses occupy positions but are
excluded from outcome means and sample counts. All of the following are required:

- At least **6 completed outcomes** in that window.
- At least **3 decisions remaining**, including the pending decision.
- The first-ranked estimated reward exceeds the recent observed mean by at
  least **20 points per choice**.
- At least one poor-performance signal:
  - The recent observed mean is nonpositive.
  - The mean of the earlier half of completed outcomes exceeds that of the later
    half by at least **30 points**, with at least three outcomes in each half.
  - The approximate upper bound on the recent mean is below the first-ranked
    option's approximate lower reward bound.

The recent-mean upper bound is `mean + 1.96 * sample_sd / sqrt(n)`. The arm's
lower bound comes from the existing Dirichlet approximation. These bounds and
thresholds form an authored screening heuristic. They are not a calibrated
significance test, a hidden-regret estimate or proof that changing options helps.
Overlapping evidence and nonstationarity further limit their interpretation.

The gate therefore permits positive returns to count as underperformance when
there is supported evidence of a better opportunity. A single loss following
sustained wins does not suffice in the regression fixture. Zero returns without
estimated headroom also remain silent. Minimum evidence delays assistance at
the start; a short remaining horizon suppresses it at the end.

The gate applies identically to **C/D/E/F at the same observable state**. Their
later states can diverge as their choices differ; this is not a forced yoking of
interventions across counterfactual trajectories. Existing relevance thresholds,
delivered-prompt cooldowns, frequency preferences and calibration/A silence still
apply. Passing the gate does not guarantee delivery.

`mab_performance.ttl` derives the performance warrant from explicit scoped
premises for evidence count, horizon, signal, gap and thresholds. Each delivered
candidate includes this proof. Snapshots record the full ranking, assessment,
settings, evidence references, gate decision and silence rationale. Delivery
validation rejects missing/tampered gate or ranking evidence.
Before any completed outcome exists, the performance mean and gap remain
unknown. They are recorded as such in JSON; no numeric RDF calculation or
performance warrant is manufactured.

## Synthetic response to the two options

Let `p` be the actor's ordinary full-history choice distribution
from its own fitted positive/negative learning rates and softmax sensitivity.
For suggested options `a1` and `a2`, the reconsideration target is:

```text
q(ai) = p(ai) / (p(a1) + p(a2)), for i = 1, 2
q(a)  = 0, for other options
P(a)  = (1 - responsiveness) * p(a) + responsiveness * q(a)
```

The same `conditional_preferences` function conditions the actor's probabilities
on a singleton for direct advice or a pair for Socratic guidance. The empirical
points/100 and illustrative points/200 conventions are preserved. The actor can
favour the runner-up if its learned preferences differ from the assistant's
estimates. The assistant does not receive these private preferences.

New runs use full-history learned preferences only. The former `none` and
`recent` variants have been removed. Zero receptiveness supplies the no-response
control without a separate Socratic processing mode. Historical results retain
their original labels and require their recorded runtime for reproduction.

Receptiveness stays fixed within a run and separate from this processing rule.
At 1, with zero reactance/distraction, choices come entirely from the pair. Below
1, options outside it retain baseline probability. Existing reactance,
distraction and omission mechanisms are unchanged. Direct advice still targets
rank 1 and never calls a Socratic processor.

This models guided consideration, not natural-language comprehension or measured
human acceptance. It cannot guarantee that Socratic outcomes match direct advice.
With a shared pair, identical response assumptions and no feedback differences,
personalised and generic variants can also produce identical synthetic choices.
The system does not add an artificial personalisation advantage.

## Isolating the two changes

The recorded policy supports a 2×2 comparison:

| Performance gate | Comparison strategy | Purpose |
| --- | --- | --- |
| `false` | `legacy_uncertainty` | Uncertainty shortlist with the single profile response |
| `true` | `legacy_uncertainty` | Performance screen with the uncertainty shortlist |
| `false` | `shared_top_two` | Shared ranking and profile-weighted pair without the screen |
| `true` | `shared_top_two` | New default: both changes |

These are researcher settings in `policy.json`, copied into new sessions and
fingerprinted by the pilot. Use separate output directories and frozen software/
policy versions for each experiment. The earlier completed pilots remain the
exact historical baseline: the legacy control above does not reproduce their
bytes because the current graph also records ranks and the performance warrant,
and direct advice now resolves tied estimates explicitly.

A future matched pilot should hold actors, repetitions, seeds, response
coefficients and the single response rule fixed across the four variants. Include
receptiveness 0 as a no-response control and the requested 0.25/0.5/0.75 levels.
All of these new-policy levels, including 0.5, need fresh comparisons. The old
receptiveness sweep's reused 0.5 reference belongs to the preceding software and
must not be combined with new-policy outcomes.
Report rewards, intervention counts, harms and archetype/individual variation;
do not optimise these thresholds against the reserved evaluation actors.

## Versions and use

New sessions record policy **0.6**, MAB module **0.2**, MAB execution **0.6**,
comparison guidance **0.2**, default-rule descriptor **0.4** and structured interventions
**0.3**. Task/source fingerprints include the ranking and performance code.
Actor/simulation versions are **0.6**; assistance response is **0.3**.
TBS retains its existing offers and default task-evidence response; its
no-reconsideration/recent variants have also been retired.

Restart the server and create new sessions. Existing sessions remain readable
and exportable; replay/resumption requires the software recorded with them.

```bash
SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded \
  .venv/bin/python -m socratic_prototype.server --data-dir /tmp/maieusis-shared-ranking
```

The focused regression suite checks successful persistence, isolated/sustained
losses, positive underperformance, missing evidence, horizon, ties, graph proofs,
profile dependence, receptiveness, cooldown, SHACL and replay:

```bash
.venv/bin/python -m unittest discover -s tests -p test_mab_shared_guidance.py -v
```

### Initial shared-ranking verification on 14 November

These checks preceded removal of the extra memory variants; see the
[single-response specification](single-response.md) for the current design.

- All **14 focused checks** passed, including complete and incremental SHACL
  validation, declared RDF vocabulary, unknown initial performance, profile
  dependence, gate/shortlist ablations, late-horizon clarification and replay.
- The broad Python regression run exercised **154 tests**, with one socket-binding
  check skipped by the environment. It exposed two RDF issues (undeclared new
  properties and an initial calculation without a value); both were corrected
  and the two affected tests passed on rerun, together with the focused suite.
- The real serial/parallel runner check matched **240 trial records**, reused
  completed jobs unchanged and replayed **six F sessions** exactly. Its
  comparisons were capped; they do not estimate experimental performance.
- The actual interface scripts completed **40 MAB and 24 TBS trials**, checking
  preparation, early-input handling, deadlines, scoring, persistence and replay
  through the Python bridge. Active/silent teammate-panel checks passed for both
  tasks. These use a DOM harness and accelerated clocks, not native display timing.
- Generated-language tests used a mocked provider. No live Ollama latency or new
  full-protocol assistance effect was measured. The completed receptiveness
  analysis and HTML report retained their recorded SHA-256 hashes.
