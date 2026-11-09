"""Versioned decisions fixed before empirical prediction and simulation."""
import hashlib
import json
from pathlib import Path
from . import VERSION
from ..tasks.tbs_empirical import FEATURES


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def procedure(random_starts=24):
    return {'version':VERSION,'mab':{'model':'handover_dual_rw_v1','reward_scale':100,'initial_q':0,
            'bounds':[[.001,.999],[.001,.999],[.01,30]],'random_starts':random_starts,'anchor_starts':7,
            'optimizer':'scipy L-BFGS-B; analytic gradient','seed':20260725,'training_last_trial':150},
            'tbs':{'model':'tbs_state_feedback_v1','features':list(FEATURES),'ridge_slopes':1.,'ridge_intercept':.001,
            'training_last_block':16,'scaling':'training eligible choices only; sample SD; constant SD replaced by 1',
            'default_offer_sensitivity':0.,'historical_offer_handling':'unknown; fit marginal risky choice conditional on recorded state and preceding feedback'},
            'selection':'Supplied deterministic Development16; original full-cohort profiles retained unchanged',
            'evaluation':'Remaining46 held out from new procedure development; original model/profile selection already used cohort information'}


def assumptions():
    return {'version':VERSION,'decisions':[
        {'id':'MAB-01','status':'source convention','decision':'Dual RW uses raw reward / 100, zero initial Q, prediction-error-sign learning rates, and no update on missed/invalid choices. Actor Q carries across MAB stages.'},
        {'id':'TBS-01','status':'provisional model','decision':'Fit a regularised state/previous-feedback logistic policy, not a combination of the original univariate slopes or a reconstruction of an established TBS generative model.'},
        {'id':'TBS-02','status':'unavailable information','decision':'Historical offer IDs, offered amounts and probabilities stay unknown. Never manufacture them from outcomes, sample replacements for historical prediction, or call marginal prediction exact offer-conditional prediction.'},
        {'id':'TBS-03','status':'sensitivity assumption','decision':'Default offer sensitivity is zero, interpreting the fitted policy as offer-marginal rather than proving humans ignore offers. Nonzero assumed EV-contrast sensitivity preserves the fitted risky probability averaged over the eight equally weighted prospective offers. It is not estimated from historical data.'},
        {'id':'ENV-01','status':'prospective schedule assumption','decision':'Fresh tasks use the published numerical rules and current independent uniform sampling of eight TBS pairs and four target/multiplier combinations. No original realised offer sequence or hidden MAB shift sequence is reconstructed.'},
        {'id':'DATA-01','status':'missingness rule','decision':'Preserve missed responses and known-bug unknown choices separately. Exclude each only from its ineligible choice likelihood; preserve elapsed trials, observed score, feedback and subsequent public state. Never zero-fill undefined adjustment measures.'},
        {'id':'DATA-02','status':'omission assumption','decision':'Estimate baseline missed-response probability separately per participant/task with a Beta(0.5,0.5) prior. Training-only rates are used for validation actors; full-history rates for reconstruction. Fresh omissions are independent Bernoulli draws, not a validated timing process. Baseline and assistance-induced omission hazards combine as 1-(1-p_base)(1-p_AI).'},
        {'id':'FIT-01','status':'validation protocol','decision':'Chronological training: MAB trials 1-150, TBS blocks 1-16. Hold-out: remaining trials/blocks. Fit/scaling use training observations only. Test predictions may use earlier observed test feedback, never future outcomes.'},
        {'id':'FIT-02','status':'reconstruction role','decision':'Full-data MAB supplied fits and newly fitted full-data TBS actors support reconstruction/simulation. Held-out scores are calculated using distinct training-only models. Full-data states/summary columns do not become predictor features.'},
        {'id':'FIT-03','status':'uncertainty limitation','decision':'Convergence does not establish identifiability. Retain boundary-fit flags, report recovery and behavioural discrepancies, and do not exclude participants solely for being hard to fit. Point estimates are not a posterior uncertainty model.'},
        {'id':'SPLIT-01','status':'selection limitation','decision':'The 16-person pilot favours clear memberships. The 46-person complement tests a frozen new procedure, not independent external validation of original profiles or model selection. Report development/evaluation separately.'},
        {'id':'ACCESS-01','status':'information boundary','decision':'Original profile labels/core scores, true actor parameters, future-linked measures, full outcomes, and ideal-observer benchmarks are researcher-side. The assistant fits its own estimates from a separate generated unassisted calibration and public events.'},
        {'id':'AI-01','status':'unidentified response mechanism','decision':'Null/responsive/interference scenarios and reconsideration heuristics remain explicit assumptions. No trust, responsiveness or reading ability is inferred from SFSS, neural scores, or unassisted feedback sensitivity.'},
        {'id':'AI-02','status':'assistant model limitation','decision':'The assistant still uses its separate coarse exploratory calibration models. It is not given the fitted actor coefficients and is not assumed to recover them accurately. A failure of personalisation under this model does not establish that personalisation or Socratic inquiry cannot help humans.'},
        {'id':'TIME-01','status':'timing limitation','decision':'Synthetic response times and reading exposure are placeholders. Browser history/display/timing differs from original tasks in documented ways; numerical reconstruction is not visual or laboratory-timing validation.'},
        {'id':'INFERENCE-01','status':'analysis limitation','decision':'Replications are repeated simulations, not extra participants. Predictive and simulation reports are descriptive; they do not establish causal human assistance effects or changes in neuroscience profiles.'}
    ]}


def implementation_hashes():
    paths=list(Path(__file__).parent.glob('*.py'))
    tasks=Path(__file__).parents[1]/'tasks'
    paths.extend(tasks/name for name in ['mab_empirical.py','tbs_empirical.py','mab_execution.py','tbs_execution.py'])
    paths.extend(Path(__file__).parents[1]/name for name in ['agents.py','simulation.py','assistance_response.py'])
    return {str(p.relative_to(Path(__file__).parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
