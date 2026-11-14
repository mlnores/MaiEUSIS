# All reconstructed participants by original archetype

Checked on **12 November 2026**. All 62 reconstructed participants retain the
original exploratory profile assignments supplied in the colleague's handover.
This is a grouping of individually fitted actors, without fitting new clusters
or replacing individuals with four averaged agents.

| Archetype | Whole cohort | Share | Development | Evaluation |
| --- | ---: | ---: | ---: | ---: |
| MAB-specialised | 21 | 33.9% | 4 | 17 |
| TBS-specialised | 24 | 38.7% | 4 | 20 |
| Dual-regime | 10 | 16.1% | 4 | 6 |
| Low-expression | 7 | 11.3% | 4 | 3 |
| Total | 62 | 100.0% | 16 | 46 |

## Original classification

The source is `Chapter6_Step06A_IntegratedMultilevelProfiles_FINAL_02oct2026_LOCKED.xlsx`,
sheets `Participant_Profiles` and `Classification_Settings`, with the rule order
also given in `SelectPrototypeDevelopmentParticipants.m`. The corresponding
scores, labels and settings are preserved in the frozen cohort's `cohort.json`
and `import_audit.json`. These are L1–L5 multilevel profiles, incorporating
dispositional and neural as well as computational and behavioural measures.
L6 performance was excluded from the scores, although performance informed
earlier component selection. Labels are not guarantees of simulated raw task
scores or estimates of attitudes to AI assistance.

For x = `MAB_CoreProfile_Z` and y = `TBS_CoreProfile_Z`, apply:

1. **Low-expression** if both scores are strictly below −0.25, or if both are
   nonpositive and their average is at most −0.46637458843810997. The latter is
   the original observed 15th-percentile cutoff, kept fixed rather than
   recalculated on the development subset.
2. Otherwise, **Dual-regime** if both scores are positive and |x−y| ≤ 0.75.
3. Otherwise, **MAB-specialised** if x ≥ y; **TBS-specialised** if y > x.

All 62 supplied assignments reproduce these rules exactly. A simple sign-based
four-quadrant split would disagree for nine participants, since the original
definition accounts for both overall expression and relative balance.

## Grouped actor exports

The [export script](../../scripts/group_participant_profiles.py) verifies the
frozen source file hashes, joins identities and splits, reproduces every original
label, and exports each actor without changing any parameter:

```bash
.venv/bin/python scripts/group_participant_profiles.py \
  --cohort-dir socratic_prototype/data/empirical_20261105_v2 \
  --output-dir socratic_prototype/data/archetype_groups_20261112
```

The generated directory contains:

- `membership.md`: every participant, original scores and development/evaluation
  membership, grouped by archetype.
- `groups.json`: machine-readable membership, frozen settings and source digests.
- `participants.mab_specialised.json`: all 21 individually parameterised actors.
- `participants.tbs_specialised.json`: all 24 actors.
- `participants.dual_regime.json`: all 10 actors.
- `participants.low_expression.json`: all 7 actors.

Optional `--plot`, using an existing Plotly installation, adds `archetypes.html`:
a self-contained scatterplot of both original core scores, with archetype colours,
development/evaluation marker shapes and individual hover details. Zero-score
reference lines are explicitly distinguished from classification boundaries.
This option adds no dependency to the running prototype.

All generated files are researcher-side artifacts in the ignored local data
directory. Actor parameters, original data, frozen cohort files, both pilot
manifests and the 16/46 split remain unchanged. Group membership is not supplied
as evidence to the assistant. No additional simulations are launched and no
evaluation outcomes are used to tune the intervention policy.
