"""Scientific matching and actor-level averaging in the receptiveness sweep."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mab_receptiveness_sweep as sweep


class SweepAnalysisTest(unittest.TestCase):
    def fixture(self):
        actors=[{'id':'fixture_actor','original_profile':'Low-expression'}]
        def results(rho):
            records=[]
            for repeat in range(3):
                for mechanism in ('none','current','recent'):
                    rows=[]
                    for condition in ('A','C','E','D','F'):
                        multiplier={'A':0,'C':100,'E':80,'D':-100 if mechanism=='current' else 50,'F':200 if mechanism=='current' else 150}[condition]
                        if mechanism=='none' and condition in ('D','F'):multiplier=0
                        score=100*(repeat+1)+rho*multiplier*repeat
                        hashed=str(score)
                        rows.append({'participant':'fixture_actor','repeat':repeat,'task':'MAB','mechanism':mechanism,
                            'condition':condition,'primary_value':score,'trajectory_sha256':hashed,'distribution_sha256':hashed,
                            'completed':True,'active_interventions':int(condition!='A')})
                    records.append({'job_id':f'job_{repeat}_{mechanism}','case':{'participant':'fixture_actor','repeat':repeat,'mechanism':mechanism},'rows':rows})
            return records
        manifest={'sha256':'engineering-fixture','reference_dir':'unused'}
        levels={key:{'manifest':{'configuration':{'repeats':3,'mechanisms':['none','current','recent']}},'actors':actors,'results':results(float(key))}
                for key in ('0.25','0.75')}
        levels['bridge']={'manifest':{'configuration':{'repeats':1,'mechanisms':['none','current','recent']}},'actors':actors,'results':results(.5)[:3]}
        return manifest,actors,results(.5),levels

    def run_analysis(self,root,fixture):
        manifest,actors,reference,levels=fixture
        with patch.object(sweep,'bridge_check',return_value={'verified':True,'comparisons':15,'calibrations':3}):
            return sweep.analyse(root,manifest,reference,levels,actors)

    def test_matched_three_repetitions_are_one_actor_and_increased_influence_can_hurt(self):
        with tempfile.TemporaryDirectory() as temp:
            report=self.run_analysis(Path(temp),self.fixture())
            self.assertTrue(report['complete']);self.assertEqual(report['participants'],['fixture_actor'])
            self.assertEqual(len(report['individual_results']),18)
            self.assertEqual(report['controls'],{'cross_mechanism':27,'no_revision':18,'cross_level_baseline':18})
            low=next(r for r in report['individual_results'] if (r['receptiveness'],r['condition'],r['mechanism'])==(.25,'D','current'))
            high=next(r for r in report['individual_results'] if (r['receptiveness'],r['condition'],r['mechanism'])==(.75,'D','current'))
            self.assertEqual(low['mean_delta'],-25);self.assertEqual(high['mean_delta'],-75)
            self.assertEqual(high['repetitions'],3)
            self.assertAlmostEqual(high['monte_carlo_se'],75/3**.5)
            self.assertTrue(all(r['participants']==1 for r in report['groups']))

    def test_one_missing_mechanism_excludes_actor_from_primary_but_retains_matched_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture=self.fixture();fixture[3]['0.75']['results'].pop()
            report=self.run_analysis(Path(temp),fixture)
            self.assertFalse(report['complete']);self.assertEqual(report['participants'],[])
            self.assertEqual(report['groups'],[])
            self.assertEqual(report['first_repetition']['participants'],['fixture_actor'])

    def test_changed_random_baseline_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture=self.fixture()
            # Alter every mechanism's A together: internal mechanism controls
            # still pass, while cross-level matching must detect the drift.
            for result in fixture[3]['0.75']['results']:
                for row in result['rows']:
                    if row['condition']=='A' or result['case']['mechanism']=='none' and row['condition'] in ('D','F'):
                        row.update(primary_value=row['primary_value']+1,trajectory_sha256='changed',distribution_sha256='changed')
            with self.assertRaisesRegex(ValueError,'baseline differs across receptiveness'):
                self.run_analysis(Path(temp),fixture)


if __name__=='__main__':unittest.main()
