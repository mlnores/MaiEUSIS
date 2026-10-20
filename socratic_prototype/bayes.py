"""Small hand-designed network; every number is a provisional assumption.

Optional pgmpy backend and dependency-free exact conditional enumeration use
identical CPTs. Probabilities are NOT empirically calibrated psychological scores.
"""
from itertools import product

VERSION = 'bn-0.1'
CPTS = {
    # columns: adverse task evidence, repeated behavioural pattern (0/1 each)
    'mismatch': [0.08, 0.25, 0.30, 0.72],
    # columns: mismatch, decision relevance (0/1 each)
    'useful': [0.10, 0.35, 0.25, 0.80],
}

class EpistemicNetwork:
    def __init__(self):
        self.backend = 'exact-enumeration'
        self.infer = None
        try:
            from pgmpy.models import DiscreteBayesianNetwork
            from pgmpy.factors.discrete import TabularCPD
            from pgmpy.inference import VariableElimination
        except ImportError:
            return
        model = DiscreteBayesianNetwork([
            ('adverse', 'mismatch'), ('pattern', 'mismatch'),
            ('mismatch', 'useful'), ('relevant', 'useful')])
        model.add_cpds(*[TabularCPD(v, 2, [[.5], [.5]]) for v in ['adverse','pattern','relevant']])
        for v, parents in [('mismatch', ['adverse','pattern']), ('useful', ['mismatch','relevant'])]:
            p = CPTS[v]
            model.add_cpds(TabularCPD(v, 2, [[1-x for x in p],p], evidence=parents, evidence_card=[2,2]))
        model.check_model()
        self.infer = VariableElimination(model)
        self.backend = 'pgmpy'

    def query(self, adverse, pattern, relevant):
        evidence = {'adverse': int(adverse), 'pattern': int(pattern), 'relevant': int(relevant)}
        if self.infer:
            mismatch = float(self.infer.query(['mismatch'], evidence=evidence, show_progress=False).values[1])
            useful = float(self.infer.query(['useful'], evidence=evidence, show_progress=False).values[1])
        else:
            mismatch = CPTS['mismatch'][2*int(adverse)+int(pattern)]
            useful = (1-mismatch)*CPTS['useful'][int(relevant)] + mismatch*CPTS['useful'][2+int(relevant)]
        return {'posterior': round(mismatch,6), 'usefulness': round(useful,6),
                'inputs': evidence, 'model_version': VERSION, 'backend': self.backend,
                'interpretation': 'Posterior under provisional hand-written CPTs; not a diagnosis or calibrated intervention effect.'}

    def describe(self):
        return {'version': VERSION, 'backend': self.backend, 'cpts': CPTS,
                'states': ['absent','present'], 'parent_order': {'mismatch':['adverse','pattern'], 'useful':['mismatch','relevant']},
                'assumptions': ['Root priors are 0.5; inputs are coarse rule-derived evidence states.',
                                'CPTs are provisional, not fitted to the briefing cohort.',
                                'Usefulness is a policy assumption, not a measured causal effect.']}
