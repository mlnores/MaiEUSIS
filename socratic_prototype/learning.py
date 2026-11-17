"""Small discrete posteriors used by public-observation participant models."""
import math


def normalise(weights):
    total=sum(weights)
    return [w/total for w in weights]


def condition(weights,likelihoods):
    return normalise([w*max(1e-12,p) for w,p in zip(weights,likelihoods)])


def summary(values,weights):
    def quantile(level):
        acc=0
        for value,weight in sorted(zip(values,weights)):
            acc+=weight
            if acc>=level:return value
        return max(values)
    return {'mean':sum(v*w for v,w in zip(values,weights)),
            'interval':[quantile(.025),quantile(.975)]}


def posterior(rows,weights):
    return [{'parameters':dict(row),'weight':w} for row,w in zip(rows,weights)]


def prior(rows,record):
    """Only an exact, task-owned calibration grid transfers; otherwise stay broad."""
    if record and len(record)==len(rows) and all(r.get('parameters')==p for r,p in zip(record,rows)):
        weights=[r.get('weight') for r in record]
        if all(type(w) in {int,float} and math.isfinite(w) and w>=0 for w in weights) and sum(weights)>0:
            return normalise(weights),True
    return [1/len(rows)]*len(rows),False


def prediction(distributions,weights):
    return {a:summary([d[a] for d in distributions],weights) for a in distributions[0]}
