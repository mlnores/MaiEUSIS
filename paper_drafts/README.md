# Research paper drafts

`productive_ignorance_decision_making.tex` is a self-contained working manuscript
for a future contribution to the Stanford discussion on the human implications
of decision-making technologies in national security and governance. It is not
an accepted submission and does not assume a venue template or confirmed date.

It covers motivation, the five conditions A/C/E/D/F, the implemented 62-person
empirical pipeline with its supplied development 16 and evaluation complement 46,
the individual MAB/TBS actor models, and the assistant architecture. Five native
TikZ figures illustrate the conditions, study, separate fitting roles, information
boundaries and intervention loop. References are included with `thebibliography`;
BibTeX and external image files are not required.

The 5 November 2026 update adds the recorded TBS/AI-response assumptions,
chronological prediction results, fresh behaviour and recovery checks, and
five-condition integration checks. It retains the negative TBS prediction result:
the provisional state/feedback policy is worse than a simple choice-frequency
baseline on average. Missing historical offers remain unknown. Cohort averages,
source reproduction and software checks are not presented as human assistance
effects or proof of validated participant reconstructions.

The 6 November 2026 update documents why Socratic processing must be varied during
development: equal response coefficients can act on different targets, while a
single authored reconsideration rule could determine an apparent style effect.
It specifies no revision, the current heuristic and recent-feedback processing;
the fixed-coefficient development-16 pilot; matched controls; resumption and
analysis. The completed 30-session short integration check is distinguished from
the full-protocol pilot, which is running with aggregate results still pending.
The paper retains every mechanism rather than choosing the one with favourable
assistance outcomes, and separates these assumptions from human comprehension.

The `.tex` is the canonical source and the PDF is its compiled reading copy.
The existing `.docx` is an earlier export and is not synchronised with this update.

Build from this directory with a TeX distribution containing the packages listed
in the preamble, including TikZ:

```bash
pdflatex -interaction=nonstopmode -halt-on-error productive_ignorance_decision_making.tex
pdflatex -interaction=nonstopmode -halt-on-error productive_ignorance_decision_making.tex
```

Alternatively:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error productive_ignorance_decision_making.tex
```

The updated source was compiled with pdfLaTeX into a 25-page PDF without warnings
or unresolved references. Every page was rendered and visually checked, including
the new mixture/perception equations, tables and all five native TikZ figures.
Temporary build and review images are kept outside this directory; the compiled
PDF and editor synchronisation file are copied alongside the source.

The draft distinguishes completed computational checks from prospective human
assistance research. The 46-person complement is not independent external
validation of the original full-cohort profiles or model selection. AI response,
reading and timing remain assumptions; point estimates do not represent parameter
uncertainty. Before submission, agree authorship, confirm internal-document
references, reconcile original task/display specifications, and add the agreed
human protocol and uncertainty analyses. In particular, the current TBS
preparation/exposure protocol and original MAB history-reset behaviour need to be
reconciled before claiming laboratory reconstruction fidelity.

Primary project sources are in `../docs/`: the design note, productive-ignorance
essay, empirical briefing, original experiment design, meeting notes and the
current architecture/simulation guides. The read-only empirical handover is in
`../git_Irena/`; the reproducible procedure is described in
`../docs/empirical_profiles.md`. Numerical results are drawn from the local frozen
`empirical_20261105_v2` bundle, whose generated private data remain ignored by Git.
The reconsideration rationale and pilot specification are in
`../docs/simulation/reconsideration.md` and `reconsideration-pilot.json` in that
same directory. The short integration outputs and full-protocol pilot occupy
separate ignored data directories; pending full-pilot outcomes are not inferred
from the short check.
The meeting notes describe earlier alternatives; the manuscript uses the
subsequently agreed five-condition design.
