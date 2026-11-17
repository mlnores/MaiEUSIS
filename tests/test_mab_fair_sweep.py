"""Fail-closed matching and participant-level averaging in the fresh MAB grid."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from statistics import mean

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mab_fair_sweep as sweep
from socratic_prototype.records import ValidationError


def seal(result):
    result.pop('result_sha256',None)
    result['result_sha256']=sweep.pilot.fingerprint(result)


class FairSweepTest(unittest.TestCase):
    def fixture(self):
        actors=[{'id':f'actor_{i}','original_profile':'Low-expression'} for i in range(2)]
        expected=[]
        for a in actors:
            for r in range(3):
                expected.append({'participant':a['id'],'repeat':r,'trajectory_sha256':f't_{a["id"]}_{r}',
                    'distribution_sha256':f'd_{a["id"]}_{r}','primary_value':100+r,'trials':200,'omissions':0})
        audit={'expected':expected,'historical_A_checks':18};levels={}
        for level in sweep.LEVELS:
            results=[]
            for i,a in enumerate(actors):
                for r in range(3):
                    base=next(x for x in expected if (x['participant'],x['repeat'])==(a['id'],r))
                    rows=[]
                    for condition in sweep.CONDITIONS:
                        effect=0 if condition=='A' else float(level)*(100*r if i==0 else -20*r)
                        rows.append({**base,'condition':condition,'task':'MAB','completed':True,
                            'primary_value':base['primary_value']+effect,'active_interventions':int(condition!='A'),
                            'baseline_control_passed':True if condition=='A' else None})
                    result={'case':{'participant':a['id'],'repeat':r},'rows':rows,
                        'calibration':{'profile_sha256':f'p_{i}_{r}','feedback_sha256':f'f_{i}_{r}',
                                       'completed_trials':200,'samples':199}}
                    seal(result);results.append(result)
            levels[level]={'manifest':{'configuration':{'repeats':3}},'results':results}
        return {'sha256':'authored-engineering-fixture'},audit,actors,levels

    def analyse(self,fixture):
        with tempfile.TemporaryDirectory() as temp:
            return sweep.analyse(Path(temp),*fixture)

    def test_complete_grid_averages_repetitions_within_people_and_keeps_harms(self):
        report=self.analyse(self.fixture())
        self.assertTrue(report['complete']);self.assertEqual(report['completed_jobs'],18)
        self.assertEqual(report['baseline_checks_passed'],18)
        self.assertEqual(report['calibration_cross_level_checks'],12)
        row=next(x for x in report['groups'] if (x['profile'],x['condition'],x['receptiveness'])==('all','D',.75))
        self.assertEqual(row['participants'],2);self.assertEqual(row['mean_delta'],30.)
        self.assertEqual((row['better'],row['same'],row['worse']),(1,0,1))
        person=next(x for x in report['individual_results'] if (x['participant'],x['condition'],x['receptiveness'])==('actor_0','D',.75))
        self.assertEqual(person['repetition_deltas'],[0,75,150]);self.assertEqual(person['mean_delta'],75)

    def test_missing_level_case_excludes_person_from_primary_but_retains_matched_first_repeat(self):
        fixture=self.fixture();fixture[3]['0.75']['results'].pop()
        report=self.analyse(fixture)
        self.assertFalse(report['complete']);self.assertEqual(report['participants'],['actor_0'])
        self.assertEqual(report['first_repetition']['participants'],['actor_0','actor_1'])

    def test_baseline_drift_is_rejected_even_with_a_valid_result_checksum(self):
        fixture=self.fixture();result=fixture[3]['0.5']['results'][0]
        result['rows'][0]['distribution_sha256']='changed';seal(result)
        with self.assertRaisesRegex(ValidationError,'Matched A baseline differs'):self.analyse(fixture)

    def test_cross_level_calibration_drift_is_rejected(self):
        fixture=self.fixture();result=fixture[3]['0.5']['results'][0]
        result['calibration']['feedback_sha256']='changed';seal(result)
        with self.assertRaisesRegex(ValidationError,'Calibration differs'):self.analyse(fixture)

    def test_capped_or_missing_conditions_are_not_accepted_as_scientific_results(self):
        for kind in ('capped','missing'):
            fixture=self.fixture();result=fixture[3]['0.25']['results'][0]
            if kind=='capped':result['rows'][1].update(completed=False,trials=8)
            else:result['rows'].pop()
            seal(result)
            with self.assertRaisesRegex(ValidationError,'Incomplete MAB|Missing assistance conditions'):self.analyse(fixture)

    def test_committed_metadata_tampering_is_detected(self):
        fixture=self.fixture();fixture[3]['0.25']['results'][0]['calibration']['samples']=100
        with self.assertRaisesRegex(ValidationError,'Committed result changed'):self.analyse(fixture)


if __name__=='__main__':unittest.main()
