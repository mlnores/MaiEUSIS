# Research paper drafts

`productive_ignorance_decision_making.tex` is a self-contained working manuscript
for a future contribution to the Stanford discussion on the human implications
of decision-making technologies in national security and governance. It is not
an accepted submission and does not assume a venue template or confirmed date.

It covers motivation, the five conditions A/C/E/D/F, the proposed 16-person
development phase and intended 62-person study, and the implemented architecture.
Three native TikZ figures illustrate the study, information boundaries and
intervention loop. References are included with `thebibliography`; BibTeX and
external image files are not required.

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

The source was checked for balanced groups/environments, citation keys, labels,
references and diagram-node references. No LaTeX compiler was available in the
authoring environment, so compilation, pagination and visual layout have not been
verified. Render and inspect the compiled PDF before circulating it.

The draft distinguishes current software capabilities from proposed empirical
work. It contains no invented participant reconstructions, assistance effects or
statistical results. Before submission, agree authorship, replace or confirm
internal-document references, reconcile original task/display specifications,
and add the agreed protocol and empirical results. In particular, the current
TBS preparation/exposure protocol and original MAB history-reset behaviour need
to be reconciled before claiming reconstruction fidelity.

Primary project sources are in `../docs/`: the design note, productive-ignorance
essay, empirical briefing, original experiment design, meeting notes and the
current architecture/simulation guides. The meeting notes describe earlier
alternatives; the manuscript uses the subsequently agreed five-condition design.
