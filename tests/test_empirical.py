"""Numerical and information-boundary checks for empirical actor extensions."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from socratic_prototype.agents import Participant,validate_participant
from socratic_prototype.tasks import mab_empirical as mab,tbs_empirical as tbs
from socratic_prototype.tasks.tbs import RULES
from socratic_prototype.empirical.assumptions import procedure
from socratic_prototype.empirical.data import observation
from socratic_prototype.empirical.fitting import fit_tbs
from socratic_prototype.empirical.evaluation import free_history,predict,omission_rate,metrics
from socratic_prototype.empirical.pipeline import aggregate
from socratic_prototype.records import ValidationError


def tbs_parameters(sensitivity=0):
    return {'model':tbs.MODEL,'features':list(tbs.FEATURES),'intercept':-.3,
            'coefficients':[0.]*len(tbs.FEATURES),'means':[0.]*len(tbs.FEATURES),'scales':[1.]*len(tbs.FEATURES),
            'offer_sensitivity':sensitivity}


def spec():
    return {'id':'fixture_empirical','source':'Explicit test assumptions',
            'task_models':{'MAB':{'model':mab.MODEL,'reward_scale':100,'alpha_plus':.4,'alpha_minus':.2,'beta':2.},'TBS':tbs_parameters()},
            'baseline_omission':{'MAB':.01,'TBS':.02},'original_profile':'researcher-only fixture',
            'provenance':{'source_id':'fixture','parameter_role':'test'}}


class EmpiricalActorTest(unittest.TestCase):
    def test_original_reward_units_and_rw_gradient(self):
        history=[{'choice':a,'outcome':r,'timed_out':False} for a,r in [('blue1',100),('red1',200),('blue1',0),('red1',-200),('blue1',100)]]
        p=spec()['task_models']['MAB'];q=mab.values(history[:1],p)
        self.assertAlmostEqual(q['blue1'],.4)
        history.insert(2,{'choice':'NO_RESPONSE','outcome':-200,'timed_out':True})
        x=[.4,.2,2.];loss,gradient=mab.nll_gradient(x,history)
        self.assertTrue(math.isfinite(loss))
        for i in range(3):
            plus=x.copy();minus=x.copy();plus[i]+=1e-6;minus[i]-=1e-6
            finite=(mab.nll_gradient(plus,history)[0]-mab.nll_gradient(minus,history)[0])/2e-6
            self.assertAlmostEqual(gradient[i],finite,places=6)
        actor=Participant(spec(),'MAB');actor.history=history
        self.assertEqual(actor.baseline({'options':[{'id':a} for a in mab.ARMS]}),mab.probabilities(mab.values(history,p),2.))
        wrong=spec();wrong['task_models']['MAB']['reward_scale']=200
        with self.assertRaises(ValidationError):validate_participant(wrong)

    def test_offer_sensitivity_preserves_the_marginal(self):
        cues=[tbs.offer_cue(pair) for pair in RULES['options']]
        for marginal in [.01,.2,.5,.9,.99]:
            for sensitivity in [-2.,0.,2.]:
                conditional=[tbs.conditional_probability(marginal,cues,c,sensitivity) for c in cues]
                self.assertAlmostEqual(sum(conditional)/8,marginal,places=12)
                self.assertTrue(all(0<=v<=1 for v in conditional))
        self.assertEqual(tbs.conditional_probability(0,cues,cues[0],2),0)
        self.assertEqual(tbs.conditional_probability(1,cues,cues[0],2),1)

    def test_unknown_choice_is_not_a_timeout_and_next_features_reset_by_block(self):
        raw={'ID_OverallTrial':2,'ID_TrialKey':'fixture_trial_2','BEH_ChosenOption':'unknown','BEH_NoResponseThisTrial':False,
             'ANL_ValidChoiceTrial':False,'ANL_ValidOutcomeTrial':True,'BEH_ChoiceMissingDueToKnownBug':True,
             'BEH_Block':1,'BEH_RemainingTrials':7,'BEH_BlockTarget':595,'BEH_BlockMultiplier':1.1,
             'BEH_BlockScoreBeforeTrial_PreMultiplier':0,'BEH_BlockScoreAfterTrial_PreMultiplier':0,
             'BEH_TrialPointsGained_PreMultiplier':0,'BEH_ScoreAfterTrial_MultiplierAdjusted':0}
        row=observation('TBS',raw)
        self.assertIsNone(row['choice']);self.assertFalse(row['timed_out']);self.assertIsNone(row['historical_offer'])
        ev={'points':0,'target':595,'remaining':6,'multiplier':1.1,'block':1}
        self.assertEqual(tbs.features(ev,[row])[-3:],[0,0,0])
        previous={**row,'choice':'risky','outcome':200}
        self.assertEqual(tbs.features(ev,[previous])[-3:],[1,1,1])
        self.assertEqual(tbs.features({**ev,'block':2},[previous])[-3:],[0,0,0])

    def test_training_scaling_and_sequential_prediction_exclude_future(self):
        history=free_history(spec(),'TBS',0,'training-test');train=history[:128]
        fitted,diagnostics=fit_tbs(train,procedure()['tbs'])
        self.assertTrue(diagnostics['converged'])
        before,predictions=predict('TBS',history,fitted,128)
        changed=copy.deepcopy(history)
        changed[150]['outcome']=999999;changed[150]['points_after']=999999
        _,altered=predict('TBS',changed,fitted,128)
        self.assertEqual(predictions[0]['probabilities'],altered[0]['probabilities'])
        self.assertEqual(fitted['offer_sensitivity'],0)
        self.assertGreater(before['eligible_test_choices'],0)
        self.assertAlmostEqual(omission_rate(train),(sum(r['timed_out'] for r in train)+.5)/129)

    def test_actor_reset_and_combined_omission(self):
        s=spec();a=Participant(s,'MAB','null');b=Participant(s,'MAB','null')
        ev={'options':[{'id':name} for name in mab.ARMS]}
        a.observe({},dict(choice='blue1',outcome=100,timed_out=False))
        self.assertNotEqual(a.baseline(ev),b.baseline(ev))
        self.assertEqual(b.distribution(ev,None)[2]['omission_probability'],.01)
        intervention={'style':'direct','recommendation':{'option_id':'blue1'},'focus':'value_revision'}
        active=Participant(s,'MAB','interference');_,_,effect=active.distribution(ev,intervention)
        self.assertAlmostEqual(effect['omission_probability'],1-.99*.95)
        self.assertNotIn('original_profile',effect)

    def test_source_switch_eligibility_distinguishes_adjacent_and_next_valid(self):
        history=[{'index':i,'choice':choice,'outcome':outcome,'timed_out':missed,'choice_eligible':not missed,
                  'model_eligible':not missed,'score_after':100} for i,choice,outcome,missed in
                 [(1,'blue1',100,False),(2,'NO_RESPONSE',-200,True),(3,'blue1',0,False),(4,'red1',200,False)]]
        result=metrics('MAB',history,spec()['task_models']['MAB'])
        self.assertEqual(result['MAB_SwitchRate_Overall'],1.)
        self.assertEqual(result['MAB_PostPositiveStayRate_Overall'],1.)

    def test_calibration_only_seeds_profiles_without_leaking_actor_truth(self):
        import json
        from socratic_prototype.store import Store
        from socratic_prototype.simulation import run
        with tempfile.TemporaryDirectory() as td,patch('socratic_prototype.engine.shacl_report',return_value={'conforms':True,'engine':'test-fixture','report':'SHACL covered separately'}):
            store=Store(Path(td)/'sessions.sqlite3');report=run(store,[spec()],calibration_only=True)
            self.assertEqual(len(report['calibrations']),2);self.assertEqual(report['runs'],[])
            for entry in report['calibrations']:
                session=store.get(entry['session_id']);self.assertTrue(session['completed'])
                public=json.dumps(session)
                for forbidden in ['task_models','baseline_omission','original_profile','researcher-only fixture','parameter_role']:
                    self.assertNotIn(forbidden,public)
                self.assertTrue(store.replay(session['id'])['matches'])

    def test_frozen_bundle_rejects_changed_research_inputs(self):
        import json,hashlib
        from socratic_prototype.empirical.pipeline import verify_bundle,write
        from socratic_prototype.empirical.assumptions import implementation_hashes
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);write(directory/'observations.json',{'recorded':1})
            write(directory/'frozen_procedure.json',{'implementation':implementation_hashes()})
            write(directory/'build_status.json',{'status':'complete'})
            names=['observations.json','frozen_procedure.json']
            write(directory/'bundle_manifest.json',{'files':{name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in names}})
            self.assertEqual(verify_bundle(directory),directory)
            write(directory/'observations.json',{'recorded':2})
            with self.assertRaisesRegex(ValidationError,'Frozen bundle file changed'):verify_bundle(directory)


if __name__=='__main__':unittest.main()
