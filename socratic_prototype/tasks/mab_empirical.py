"""Original handover RW convention; private actor/fitting calculations only."""
import math
from .mab import ARMS

VERSION='handover-dual-rw-0.1'
MODEL='handover_dual_rw_v1'
BOUNDS=((.001,.999),(.001,.999),(.01,30.))


def probabilities(q,beta):
    logits=[beta*q[a] for a in ARMS];maximum=max(logits)
    values=[math.exp(z-maximum) for z in logits];total=sum(values)
    return dict(zip(ARMS,(v/total for v in values)))


def eligible(row):
    return not row.get('timed_out',False) and row.get('model_eligible',True) and row.get('choice') in ARMS


def update(q,row,alpha_plus,alpha_minus):
    if eligible(row):
        a=row['choice'];pe=row['outcome']/100.-q[a]
        q[a]+=(alpha_plus if pe>=0 else alpha_minus)*pe


def values(history,parameters):
    q=dict.fromkeys(ARMS,0.)
    for row in history:update(q,row,parameters['alpha_plus'],parameters['alpha_minus'])
    return q


def nll_gradient(x,history):
    """Analytic RW likelihood gradient, including the dependence of Q on alpha."""
    ap,an,beta=x;q=dict.fromkeys(ARMS,0.);dq={a:[0.,0.] for a in ARMS}
    loss=0.;gradient=[0.,0.,0.]
    for row in history:
        if not eligible(row):continue
        a=row['choice'];p=probabilities(q,beta)
        logits=[beta*q[b] for b in ARMS];maximum=max(logits)
        loss+=maximum+math.log(sum(math.exp(z-maximum) for z in logits))-beta*q[a]
        for j in range(2):gradient[j]+=beta*(sum(p[b]*dq[b][j] for b in ARMS)-dq[a][j])
        gradient[2]+=sum(p[b]*q[b] for b in ARMS)-q[a]
        pe=row['outcome']/100.-q[a];j=0 if pe>=0 else 1;alpha=ap if j==0 else an
        dq[a]=[(1-alpha)*d+(pe if k==j else 0.) for k,d in enumerate(dq[a])]
        q[a]+=alpha*pe
    return loss,gradient
