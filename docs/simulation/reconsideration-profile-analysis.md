# Earlier pilot: assistance effects by original profile

Analysis checked on **12 November 2026** against the completed pilot in
`socratic_prototype/data/reconsideration_pilot_20261106`. This report describes
the **earlier** assistance/processing implementation, before the new comparison
guidance. It does not combine results from the running guided pilot or alter its
configuration.

The grouping variables are the colleague's original MAB-specialised,
TBS-specialised, Dual-regime and Low-expression assignments. No new clusters are
fitted. There are **four deliberately selected development actors per group and
one matched repetition per actor**. Each actor is counted once in a reported
cell. The three mechanisms are sensitivity assumptions, not independent samples.

Conditions are A (no assistance), C (task-aware direct recommendations), E
(personalised direct recommendations), D (task-aware Socratic questions) and F
(personalised Socratic questions). All response coefficients were controlled:
responsiveness 0.5; reactance, distraction and additional AI omission zero.
Individual task models and baseline omission rates remained participant-specific.
The original profile labels were researcher-side metadata, not assistant inputs
or profile-specific receptiveness settings.

## MAB: profile means conceal meaningful differences

Values are mean paired **changes in points from the same actor's A run**.

| Original profile | C direct | E personalised direct | D current | F current | D recent | F recent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MAB-specialised | +1,325 | +2,225 | +25 | −25 | −800 | −925 |
| TBS-specialised | −50 | +275 | −375 | −525 | −100 | −200 |
| Dual-regime | +1,625 | +2,250 | +1,000 | +450 | +525 | −25 |
| Low-expression | +925 | +350 | +750 | +425 | +1,300 | +525 |

C/E have identical effects under all three processing mechanisms. With `none`,
D/F reproduce A exactly; those zero-effect cells are omitted from this table.
`current` and `recent` refer to the archived rules documented in
[the earlier pilot description](reconsideration.md#three-retained-mechanisms),
not to the updated graph-backed comparison guidance.

The following counts are **better / same / worse than A**, out of four:

| Original profile | C direct | E personalised direct | D current | F current | D recent | F recent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MAB-specialised | 2/1/1 | 4/0/0 | 2/0/2 | 1/0/3 | 1/0/3 | 1/0/3 |
| TBS-specialised | 2/0/2 | 3/0/1 | 0/1/3 | 0/1/3 | 1/1/2 | 1/1/2 |
| Dual-regime | 4/0/0 | 4/0/0 | 2/1/1 | 2/0/2 | 2/0/2 | 2/0/2 |
| Low-expression | 3/0/1 | 3/0/1 | 3/0/1 | 3/0/1 | 4/0/0 | 3/0/1 |

Personalised direct recommendations have the largest observed group means for
the MAB-specialised and Dual-regime actors, improving all eight actors. This
does not mean task-specialised actors are intrinsically more receptive: their
response coefficients were identical to those of the other groups.

The Low-expression group provides an exception to the overall direct-over-
Socratic mean ranking. Generic Socratic questions with `recent` processing
improved all four actors, by 800–1,700 points, averaging +1,300. This exceeded
generic direct advice by 375 points on average; three actors scored higher with
D/recent than with C, and one lower. This is a useful hypothesis to examine in
the new repetitions, not a processing mechanism selected as a winner.

For the MAB-specialised actors, D/current's mean of +25 hides two gains and two
losses, ranging from −1,500 to +1,600. F/current's mean of −25 hides one gain and
three losses, from −1,400 to +3,000. Both recent Socratic variants harm three of
four actors. Near-zero means therefore do not imply negligible individual effects.

For TBS-specialised actors in MAB, personalised direct advice offers only a small
positive mean (+275); three benefit and one loses 800 points. Both current
Socratic variants harm three, with the fourth unchanged. Thus this particular
simulation does not demonstrate consistent compensation for the putatively
weaker MAB regime.

The Dual-regime group's positive F/current mean (+450) also masks two harmed
actors. One actor gains 2,700 points; the other three average −300. D/current's
+1,000 mean includes a +3,600 gain, a −300 loss, a +700 gain and an unchanged
actor. These observations explain why group medians, ranges and individual
effects accompany the means in the generated report.

## Personalisation has different effects across profiles

Values below compare the two assistance variants directly, rather than treating
an improvement over A as proof that personalisation helped.

| Original profile | Direct E−C | Socratic F−D, current | Socratic F−D, recent |
| --- | ---: | ---: | ---: |
| MAB-specialised | +900 | −50 | −125 |
| TBS-specialised | +325 | −150 | −100 |
| Dual-regime | +625 | −550 | −550 |
| Low-expression | −575 | −325 | −775 |

Personalising direct advice helped relative to C for two MAB-specialised actors
(the other two were unchanged), three TBS-specialised actors (one was worse),
and two Dual-regime actors (two unchanged). It reduced the benefit for three
Low-expression actors and increased it for one. The latter group's E mean remains
positive against A, but it is lower than C's mean: these are different contrasts.

F's mean is below D's in every profile group under both active processing
mechanisms. This is an observation about the earlier personalisation policy and
authored actor processing, rather than evidence that personalisation or Socratic
reasoning is generally harmful.

The machine-readable report also includes the full paired 2 × 2 contrasts:
E−C, F−D, D−C, F−E and the interaction (F−D)−(E−C). A positive interaction alone
need not mean either personalised variant improves on its generic counterpart.
For example, Low-expression/current has interaction +250 because F−D (−325) is
less negative than E−C (−575); both personalisation contrasts are negative.

## TBS: largest gains in the Low-expression group

Values are mean paired changes in target-attainment rate, in **percentage
points**, over 24 blocks. A single additional attained target is 4.17 percentage
points for an individual. Group means may be smaller because four individuals
are averaged.

| Original profile | Direct C = E | Socratic D = F, current | Socratic D = F, recent |
| --- | ---: | ---: | ---: |
| MAB-specialised | +2.08 | −3.13 | −2.08 |
| TBS-specialised | +4.17 | 0.00 | 0.00 |
| Dual-regime | +3.13 | 0.00 | +1.04 |
| Low-expression | +8.33 | +5.21 | +3.13 |

| Original profile | C/E better / same / worse | D/F current | D/F recent |
| --- | ---: | ---: | ---: |
| MAB-specialised | 2/2/0 | 0/3/1 | 0/3/1 |
| TBS-specialised | 2/2/0 | 1/2/1 | 1/2/1 |
| Dual-regime | 3/1/0 | 1/2/1 | 1/3/0 |
| Low-expression | 4/0/0 | 2/2/0 | 2/1/1 |

Low-expression actors show the largest TBS gains with every assistance variant.
Direct advice improves all four, averaging two additional attained targets per
actor. Their assisted rate is 64.58%, still below the other groups' 72.92–73.96%
with direct support: improvement does not eliminate the performance gap.
Current Socratic processing improves two and leaves two unchanged; recent
processing improves two, leaves one unchanged and harms one. The MAB-specialised
Socratic mean loss is entirely due to one actor: three attain the same number of
targets, while the fourth loses three targets under current and two under recent.

TBS personalisation is **not an effective behavioural contrast** in this archived
pilot. C/E have identical choice/outcome and probability trajectories within
each actor and mechanism, as do D/F. Consequently E−C and F−D are zero in every
profile. The separate, unfinished TBS intervention-selection audit remains
necessary; this profile breakdown does not explain away that limitation.

## Baselines and interpretation

| Original profile | Mean unassisted MAB points | Mean unassisted TBS targets attained |
| --- | ---: | ---: |
| MAB-specialised | 9,125 | 70.83% |
| TBS-specialised | 7,975 | 68.75% |
| Dual-regime | 9,950 | 70.83% |
| Low-expression | 7,700 | 56.25% |

Lower Low-expression baselines leave more scope for improvement, particularly in
TBS, but baseline differences alone do not identify the mechanism behind a gain.
Original multilevel profile labels do not guarantee an ordering of simulated raw
task scores. For example, the TBS-specialised group does not have the highest
unassisted TBS rate in this repetition. The current data therefore do not justify
calling these results established compensation of an original weaker environment,
or preservation of every original task strength.

The group differences are promising exploratory contrasts for the new pilot,
particularly Low-expression versus MAB-specialised responses to recent Socratic
processing, and the profile-dependent E−C contrast. Keep all mechanisms and
inspect whether the pattern survives repetition and the new guidance; do not
tune interventions to these favourable outcomes or reinterpret the 46-person
evaluation set as development data.

With only four selected actors per group and one simulated repetition, there is
no estimated Monte Carlo standard error or defensible claim here about human
profile-specific treatment effects. Effects combine fixed task-model differences,
public histories, intervention selection, the authored processing rule and a
particular outcome realisation. They are not measurements of different AI
attitudes. Intervention frequencies also differ across conditions, so these are
whole-policy comparisons rather than isolated changes of linguistic style. The
actors process structured metadata, not the meaning of natural-language questions.
Unknown historical TBS offers and the provisional TBS actor's inferior
held-out prediction relative to the frequency baseline further limit conclusions.

## Reproduction and integrity

The [analysis script](../../scripts/analyze_pilot_profiles.py) reads the archived
reports directly and uses only the standard library for the audit and tables:

```bash
.venv/bin/python scripts/analyze_pilot_profiles.py \
  --pilot-dir socratic_prototype/data/reconsideration_pilot_20261106 \
  --output-dir socratic_prototype/data/reconsideration_profiles_20261112
```

`--plot` additionally produces a self-contained interactive HTML figure if Plotly
is installed in the selected Python environment. The local analysis used the
existing Plotly installation in the base Python environment; no dependencies
were added to the prototype or its running workers.

Generated local files are `analysis.json`, `report.md` and `profile_effects.html`.
The HTML has separate MAB/TBS colour scales, group and individual heatmaps, and
hover details for means, medians, ranges, harm counts and intervention counts.
After the change-from-baseline section, the group-average outcome heatmaps show
paired differences from A for the assistance conditions. MAB differences
are points and TBS differences are percentage points. Each task uses a symmetric
diverging scale centred on zero; hover details retain the absolute means. The
absolute-average tables above remain available.
The graph n labels count actors tested in this pilot: four per archetype, 16 in
total. The separate full-cohort grouping contains 62 profiles and does not add
assistance outcomes for the other 46 actors.
These generated files remain outside the immutable source pilot and are ignored
by Git. The Markdown and JSON reports include individual-level contrasts.

Integrity checks verified the manifest and actor digests, all 48 completed report
hashes, all 480 outcome/trajectory/probability summaries, all 96 cross-mechanism
controls and 64 no-revision controls. All 384 cached individual effects and 120
cached group/overall summaries were independently reconciled. The manifest is
`ab9662c1879400802d1ef780ba2c6a31f6281f2a5014da1db9ed8d1fec7492f6`;
the archived task execution versions are MAB/TBS 0.3. This analysis does not
replay those sessions with the newer implementation or alter their fingerprints.
