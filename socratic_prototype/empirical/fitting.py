"""Training-only estimators; no future summaries or profile labels are predictors."""
import math
from .data import evaluation
from ..records import require
from ..tasks import mab_empirical as mab,tbs_empirical as tbs


def fit_mab(history,config):
    import numpy as np
    from scipy.optimize import minimize
    require(sum(mab.eligible(row) for row in history)>=20,'Insufficient MAB training choices')
    anchors=[[.3,.3,2],[.1,.1,.5],[.8,.2,5],[.2,.8,5],[.7,.7,15],[.95,.05,25],[.05,.95,25]]
    rng=np.random.default_rng(config['seed'])
    starts=anchors+[list(rng.uniform([.001,.001,.01],[.999,.999,30])) for _ in range(config['random_starts'])]
    results=[]
    for start in starts:
        result=minimize(lambda x:mab.nll_gradient(x,history),start,jac=True,bounds=mab.BOUNDS,method='L-BFGS-B',
                        options={'maxiter':1000,'ftol':1e-12,'gtol':1e-7,'maxls':40})
        if result.success and math.isfinite(result.fun):results.append(result)
    require(bool(results),'No converged MAB training fit')
    best=min(results,key=lambda r:r.fun);x=list(map(float,best.x))
    boundary=any(min(v-lo,hi-v)<=1e-4*(hi-lo) for v,(lo,hi) in zip(x,mab.BOUNDS))
    return {'model':mab.MODEL,'reward_scale':100,'alpha_plus':x[0],'alpha_minus':x[1],'beta':x[2]}, {
        'converged':True,'nll':float(best.fun),'boundary':boundary,'starts':len(starts),'converged_starts':len(results),
        'trials':sum(mab.eligible(row) for row in history)}


def fit_tbs(history,config):
    import numpy as np
    from scipy.optimize import minimize
    xs=[];ys=[];past=[]
    for row in history:
        if row['choice_eligible'] and not row['timed_out']:
            xs.append(tbs.features(evaluation('TBS',row),past));ys.append(float(row['choice']=='risky'))
        past.append(row)
    require(len(ys)>=20,'Insufficient TBS training choices')
    x=np.asarray(xs,dtype=float);y=np.asarray(ys);means=x.mean(axis=0);scales=x.std(axis=0,ddof=1)
    constant=scales<1e-12;scales[constant]=1.;z=np.column_stack([np.ones(len(y)),(x-means)/scales])
    penalties=np.array([config['ridge_intercept']]+[config['ridge_slopes']]*len(tbs.FEATURES))
    def objective(beta):
        logits=z@beta
        from scipy.special import expit
        loss=np.logaddexp(0,logits).sum()-y@logits+.5*np.dot(penalties*beta,beta)
        return loss,z.T@(expit(logits)-y)+penalties*beta
    prior=(y.sum()+.5)/(len(y)+1);start=np.zeros(z.shape[1]);start[0]=math.log(prior/(1-prior))
    result=minimize(objective,start,jac=True,method='L-BFGS-B',options={'maxiter':2000,'ftol':1e-13,'gtol':1e-7,'maxls':40})
    require(result.success and math.isfinite(result.fun),'TBS state-policy fit did not converge')
    params={'model':tbs.MODEL,'features':list(tbs.FEATURES),'intercept':float(result.x[0]),
            'coefficients':list(map(float,result.x[1:])),'means':list(map(float,means)),'scales':list(map(float,scales)),
            'offer_sensitivity':config['default_offer_sensitivity']}
    tbs.validate_actor(params)
    return params,{'converged':True,'trials':len(y),'penalized_objective':float(result.fun),
                   'constant_features':[name for name,c in zip(tbs.FEATURES,constant) if c],
                   'training_nll':float(np.logaddexp(0,z@result.x).sum()-y@(z@result.x))}
