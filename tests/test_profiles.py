"""Synthetic personas remain reproducible, attributable and usable as calibrations."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_prototype.profiles import PROFILES,trial_inputs,seed_profiles,session_id
from socratic_prototype.store import Store
from socratic_prototype.models import calibration_profile
from socratic_prototype.records import ValidationError


class SyntheticProfilesTest(unittest.TestCase):
    def test_histories_and_fits_distinguish_the_declared_examples(self):
        mab={name:[fb for _,fb in trial_inputs(name,'MAB','fixture')] for name in PROFILES}
        self.assertEqual(len({e['choice'] for e in mab['synthetic_broad_sampling']}),6)
        self.assertEqual({e['choice'] for e in mab['synthetic_persistent']},{'red2'})
        self.assertEqual(mab['synthetic_pressure_up'],mab['synthetic_pressure_down'])
        broad=calibration_profile('MAB',mab['synthetic_broad_sampling'])
        fast=calibration_profile('MAB',mab['synthetic_fast_updates'])
        self.assertGreater(fast['beta'],broad['beta'])
        slopes={}
        for name in PROFILES:
            h=[{**fb,'points_before':ev['points'],'target':ev['target'],'remaining':ev['remaining']}
               for ev,fb in trial_inputs(name,'TBS','fixture')]
            self.assertEqual(len(h),24)
            slopes[name]=calibration_profile('TBS',h)['policy']
        self.assertGreater(slopes['synthetic_pressure_up']['p_positive_sensitivity'],.9)
        self.assertLess(slopes['synthetic_pressure_down']['p_positive_sensitivity'],.1)
        self.assertEqual(list(trial_inputs('synthetic_fast_updates','MAB','fixture')),list(trial_inputs('synthetic_fast_updates','MAB','fixture')))
        self.assertEqual(len(list(trial_inputs('synthetic_pressure_up','TBS','fixture','full'))),192)

    def test_seed_resume_replay_and_comparison_provenance(self):
        with tempfile.TemporaryDirectory() as td,patch.dict('os.environ',{'SOCRATIC_LLM':'offline'}):
            store=Store(Path(td)/'s.sqlite3');name='synthetic_pressure_up'
            human=store.create(dict(participant_id='existing_participant',task='MAB',condition='A',
                phase='calibration',protocol='short',preference='standard'))
            # Simulate a stopped generator with one evaluation already committed.
            from socratic_prototype.profiles import VERSION
            sid=session_id(name,'MAB','short')
            metadata={'name':name,'version':VERSION,'description':PROFILES[name]['description'],
                      'notice':'Synthetic scripted calibration, not human data. Fitted estimates need not equal generating parameters.'}
            s=store.create(dict(id=sid,participant_id=name,task='MAB',condition='A',phase='calibration',
                protocol='short',preference='standard',seed=VERSION+':'+name),synthetic_profile=metadata)
            ev,_=next(trial_inputs(name,'MAB',sid));store.event(sid,ev)
            with patch('urllib.request.urlopen',side_effect=AssertionError('Profile generation called an LLM')):
                ids=seed_profiles(store,names=[name])[name]
            before={sid:copy.deepcopy(store.get(sid)) for sid in ids.values()}
            self.assertEqual(seed_profiles(store,names=[name])[name],ids)
            self.assertEqual({sid:store.get(sid) for sid in ids.values()},before)
            self.assertEqual(len(store.list()),3)
            self.assertEqual(store.get(human['id']),human)
            for task,sid in ids.items():
                s=store.get(sid);self.assertTrue(s['completed']);self.assertTrue(s['synthetic'])
                self.assertEqual(s['profile']['task'],task)
                self.assertEqual(sum(e['input']['kind']=='feedback' for e in s['events']),40 if task=='MAB' else 24)
                self.assertTrue(store.replay(sid)['matches'])
                self.assertTrue(all(e.get('snapshot',{}).get('decision',{}).get('action','silence')=='silence' for e in s['events']))
            comparison=store.create(dict(participant_id=name,task='MAB',condition='F',phase='assisted',protocol='short',
                preference='standard',calibration_ids=ids))
            self.assertTrue(comparison['uses_synthetic_calibration'])
            self.assertEqual(comparison['calibration_profile'],before[ids['MAB']]['profile'])
            self.assertTrue(all(source['synthetic'] for source in comparison['calibration_sources'].values()))
            self.assertNotIn('synthetic',comparison,'Real subsequent choices are not automatically synthetic observations')
            with self.assertRaises(ValidationError):store.create(dict(participant_id='human',task='MAB',condition='A',
                phase='calibration',protocol='short',preference='standard',synthetic_profile=metadata))
