# One participant-response rule

Updated on **14 November 2026**. New synthetic runs no longer offer `none` or
`recent`. Their use in completed experiments remains recorded in historical
reports, frozen configurations and archived analysis tools.

## Rationale and behaviour

Giving only Socratic support an extra memory/no-reconsideration selector added
assumptions to the comparison. New MAB runs instead use one simple rule for both
styles. Let `p` be the participant's ordinary profile-dependent choice
probabilities and `S` the offered set:

```text
q(a) = p(a) / sum(p(b) for b in S), if a is in S; otherwise 0
P(a) = (1 - responsiveness) * p(a) + responsiveness * q(a)
```

C/E offer the first option in the shared public reward ranking. A singleton gives
a point target. D/F offer ranks 1 and 2; their relative weights come from the
same participant's learned preferences. `conditional_preferences` implements
both operations. A zero-mass offered set uses equal weights within that set;
ordinary MAB softmax probabilities remain positive under the supported bounds.

The participant continues ordinary outcome learning across the whole run using
its individual positive/negative learning rates and choice sensitivity. There
is no six-trial memory reset, no uncertainty bonus, and no special refusal to
reconsider. The existing shared performance gate, cooldown and interruption
policy decide when assistance appears. They do not set the participant's weights.
Reactance, distraction and omission parameters retain their shared definitions.

This removes those particular modelling asymmetries; it does not prove that
either assistance style is unbiased or beneficial. The substantive difference
remains deliberate: one offered action versus a comparison of two actions.

## TBS and future environments

TBS has only SAFE and RISKY. Conditioning on both would leave its baseline
distribution unchanged and make Socratic guidance directionally ineffective.
This revision therefore retains TBS's existing single response to displayed
task evidence/goals. It removes the recent-feedback probability distortion and
the no-reconsideration alternative. It does not silently replace the TBS model
with MAB's pair restriction. TBS still has additional task-specific response
assumptions, documented in its execution adapter.

Future environments expose one `reconsider` adapter hook with an explicit rule,
alongside their baseline actor. No optional recency contract is required.

## Controls, configuration and compatibility

- Assistance condition A remains the unassisted baseline.
- At receptiveness 0 with zero distraction/additional omission, all five
  conditions reproduce A's choice/outcome streams under matched seeds. This is
  the response control; it no longer requires a separate Socratic mechanism.
- New pilots default to one job per actor/repetition. The `mechanisms` input can
  be omitted. If present, only `["current"]` is accepted as a compatibility label.
  It is not an experimental factor; no single-rule sensitivity contrast is made.
- Library calls retaining `reconsideration='current'` continue to work. Other
  values fail before sessions are created. The simulator CLI no longer has a
  `--reconsideration` option.
- Reports retain a fixed `mechanism: current` field for format compatibility.
  They check actual A distributions and, when configured, zero-response
  trajectories. They do not count self-comparisons as cross-mechanism controls.
- Old pilots are not migrated, rerun or pooled into new estimates. Their recorded
  runtime is needed for replay/resumption. Historical renderers remain available.

## New MAB pilot template

[`profile-response-pilot.json`](profile-response-pilot.json) specifies the same
16 development actors, three repetitions, full 200-trial MAB calibration and
comparisons, all five conditions and receptiveness 0.5: **48 jobs**, including
240 condition sessions. It omits mechanism choices. Other receptiveness levels
need separate fresh configurations/output directories; no old 0.5 assisted
results can be reused. The seed string is retained to support later baseline
audits; it does not select a processing mechanism.

Freeze and inspect the plan without running simulations:

```bash
.venv/bin/python -m socratic_prototype.pilot \
  --config docs/simulation/profile-response-pilot.json \
  --output-dir /tmp/maieusis-single-response-plan --prepare-only
```

The existing parallel runner accepts that configuration. A subsequent
[fresh matched receptiveness comparison](fair-mab-receptiveness.md) has now been
launched with all five conditions fresh at 0.25/0.5/0.75. The earlier
simplification checks did not estimate full-protocol assistance effects.

Actor/simulation versions are 0.6; assistance response is 0.3, MAB execution is
0.6, TBS execution is 0.5, and the default-rule descriptor is 0.4. Session and
pilot fingerprints preserve the distinction from earlier results.

## Verification

The focused regression run passed **54 checks**, including shared conditioning,
receptiveness, retired-mode rejection before session creation, full-history
learning, whole/incremental RDF validation, zero-response controls, frozen inputs,
resumption, privacy boundaries and the third-environment contract.

A separate real serial/parallel check passed with three repetitions of the one
response rule: **240 matched trial records**, **six exact F replays**, and
unchanged reuse of completed jobs. Comparisons were capped at eight trials and
are engineering checks, not experimental outcome estimates.

The simulator's help exposes no mechanism selector. The 16-actor pilot template
validated as 48 jobs with zero executed. Historical receptiveness analysis and
HTML report hashes were unchanged. No live language-model performance was tested.
