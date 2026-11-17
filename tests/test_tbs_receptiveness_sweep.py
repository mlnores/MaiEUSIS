"""Matched TBS controls, target-rate units and participant-level averaging."""
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from statistics import mean

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tbs_receptiveness_sweep as sweep
from socratic_prototype.records import ValidationError


def seal(result):
    result.pop('result_sha256',None)
    result['result_sha256']=sweep.pilot.fingerprint(result)


class TBSSweepTest(unittest.TestCase):
    def fixture(self):
        actors=[{'id':f'actor_{i}','original_profile':'Low-expression'} for i in range(2)]
        expected=[]
        for a in actors:
            for r in range(3):
                expected.append({'participant':a['id'],'repeat':r,'trajectory_sha256':f't_{a["id"]}_{r}',
                    'distribution_sha256':f'd_{a["id"]}_{r}','primary_value':(10+r)/24,'score':10000+100*r,'targets_attained':10+r,
                    'blocks_completed':24,'trials':192,'omissions':0})
        audit={'expected':expected,'independent_full_trajectories':6};levels={}
        for level in sweep.LEVELS:
            results=[]
            for i,a in enumerate(actors):
                for r in range(3):
                    base=next(x for x in expected if (x['participant'],x['repeat'])==(a['id'],r))
                    rows=[]
                    for condition in sweep.CONDITIONS:
                        effect=0 if condition=='A' else (r if i==0 else -2*r)
                        rows.append({**base,'condition':condition,'task':'TBS','completed':True,
                            'primary_value':(base['targets_attained']+effect)/24,
                            'targets_attained':base['targets_attained']+effect,'score':base['score']+100*effect,'active_interventions':int(condition!='A'),
                            'baseline_control_passed':True if condition=='A' else None})
                    result={'case':{'participant':a['id'],'repeat':r},'rows':rows,
                        'calibration':{'profile_sha256':f'p_{i}_{r}','inputs_sha256':f'f_{i}_{r}',
                                       'completed_trials':192,'samples':190},
                        'numerical_replay':{'trial_choices_outcomes_and_distributions':960,'full_condition_metrics':5}}
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
        self.assertEqual(row['participants'],2);self.assertAlmostEqual(row['mean_delta'],-.5/24)
        self.assertAlmostEqual(row['mean_delta_pp'],-50/24)
        self.assertEqual(row['mean_score_delta'],-50)
        self.assertEqual((row['better'],row['same'],row['worse']),(1,0,1))
        person=next(x for x in report['individual_results'] if (x['participant'],x['condition'],x['receptiveness'])==('actor_0','D',.75))
        self.assertEqual(person['repetition_score_deltas'],[0,100,200]);self.assertAlmostEqual(person['mean_delta'],1/24)

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
        result['calibration']['inputs_sha256']='changed';seal(result)
        with self.assertRaisesRegex(ValidationError,'Calibration differs'):self.analyse(fixture)

    def test_capped_or_missing_conditions_are_not_accepted_as_scientific_results(self):
        for kind in ('capped','missing'):
            fixture=self.fixture();result=fixture[3]['0.25']['results'][0]
            if kind=='capped':result['rows'][1].update(completed=False,trials=8)
            else:result['rows'].pop()
            seal(result)
            with self.assertRaisesRegex(ValidationError,'Incomplete TBS|Missing assistance conditions'):self.analyse(fixture)

    def test_committed_metadata_tampering_is_detected(self):
        fixture=self.fixture();fixture[3]['0.25']['results'][0]['calibration']['samples']=100
        with self.assertRaisesRegex(ValidationError,'Committed result changed'):self.analyse(fixture)


    def test_primary_denominator_secondary_score_and_blocks_are_checked_separately(self):
        for field,value,message in [('primary_value',.9,'target-attainment rate'),
                                     ('blocks_completed',23,'Incomplete TBS'),
                                     ('score',1,'Matched A baseline differs')]:
            with self.subTest(field=field):
                fixture=self.fixture();result=fixture[3]['0.25']['results'][0]
                result['rows'][0][field]=value;seal(result)
                with self.assertRaisesRegex(ValidationError,message):self.analyse(fixture)

    def test_missing_numerical_replay_is_rejected(self):
        fixture=self.fixture();result=fixture[3]['0.5']['results'][0]
        result['numerical_replay']['trial_choices_outcomes_and_distributions']=191;seal(result)
        with self.assertRaisesRegex(ValidationError,'numerical replay'):self.analyse(fixture)

    def test_full_unassisted_rollout_retains_omissions_and_24_blocks(self):
        actor={'id':'tbs_omissions','source':'Authored omission-boundary engineering fixture',
               'task_models':{'TBS':{'intercept':0,'slope':1}},'baseline_omission':{'TBS':1}}
        result=sweep.baseline_rollout(actor,'fixture',0,'full')
        self.assertEqual((result['trials'],result['blocks_completed'],result['omissions']),(192,24,192))
        self.assertEqual((result['score'],result['targets_attained'],result['primary_value']),(0,0,0))
        self.assertEqual(result,sweep.baseline_rollout(actor,'fixture',0,'full'))
        self.assertNotEqual(result['environment_seed'],sweep.baseline_rollout(actor,'fixture',1,'full')['environment_seed'])

    def test_calibration_signature_ignores_session_ids_but_tracks_displayed_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            database=Path(temp)/'calibrations.sqlite3'
            with sqlite3.connect(database) as connection:
                connection.execute('CREATE TABLE sessions(id TEXT, body TEXT)')
                for sid,amount in [('calibration_a',100),('calibration_b',100),('calibration_c',200)]:
                    events=[]
                    for index in range(1,193):
                        trial=sid+'_trial_'+str(index)
                        events.extend([{'input':{'kind':'evaluation','index':index,'trial_id':trial,
                                                   'options':[{'id':'safe','amount':amount,'probability':.75}]}},
                                       {'input':{'kind':'feedback','index':index,'trial_id':trial,'choice':'safe',
                                                   'outcome':0,'timed_out':False,'points_after':0}}])
                    profile={'task':'TBS','policy':{'samples':192,'evidence':[sid+'_trial_'+str(i) for i in range(1,193)]}}
                    connection.execute('INSERT INTO sessions VALUES(?,?)',(sid,json.dumps({'profile':profile,'events':events})))
            signature=lambda sid:sweep.calibration_signature({'calibrations':[{'task':'TBS','session_id':sid}]},database)
            a,b,c=map(signature,['calibration_a','calibration_b','calibration_c'])
            self.assertEqual(a,b)
            self.assertEqual(a['profile_sha256'],c['profile_sha256'])
            self.assertNotEqual(a['inputs_sha256'],c['inputs_sha256'])


if __name__=='__main__':unittest.main()
