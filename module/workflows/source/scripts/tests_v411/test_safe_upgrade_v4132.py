"""Upgrade safety; runs only in disposable directories."""
import base64
import tempfile
import unittest
from pathlib import Path
from scripts import upgrade_to_v4132 as up

class RuntimeUpgradeTests(unittest.TestCase):
    def test_configs_jobs_and_unchanged_providers_stay_protected(self):
        for rel in ['config/xty.json','jobs/q000001/job_state.json','shared/managed_runtime.py','requirements.txt','../out']:
            with self.subTest(rel=rel),self.assertRaises(ValueError):up.safe_file(Path('/tmp/isolated'),rel)
        self.assertEqual(up.safe_file(Path('/tmp/isolated'),'shared/agents_runtime.py'),Path('/tmp/isolated/shared/agents_runtime.py'))
    def test_unrelated_local_edits_are_preserved_but_conflicts_stop(self):
        enc=lambda b:base64.b64encode(b).decode()
        h=[{'before':enc(b'context\nold\ntail\n'),'after':enc(b'context\nfixed\ntail\n')}]
        data=b'LOCAL_ADAPTER_CHANGE\ncontext\nold\ntail\n'
        result=up.merge_hunks(data,h);self.assertIn(b'LOCAL_ADAPTER_CHANGE',result)
        self.assertEqual(result,up.merge_hunks(result,h))
        with self.assertRaises(ValueError):up.merge_hunks(b'context\nconflicting fix\ntail\n',h)
    def test_any_conflict_prevents_all_planned_writes(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);new=r/'new';old=r/'old';new.mkdir();old.mkdir()
            for name in ['first.md','second.md']:(new/name).write_text('fixed')
            (old/'first.md').write_text('base');(old/'second.md').write_text('local conflicting change')
            manifest={'files':[{'path':name,'new_sha256':up.sha(b'fixed'),'base_sha256':up.sha(b'base'),'hunks':[]} for name in ['first.md','second.md']]}
            with self.assertRaises(ValueError):up.prepare(old,manifest,new)
            self.assertEqual((old/'first.md').read_text(),'base')
            self.assertFalse((old/'.frontmind-upgrade-backups').exists())
    def test_apply_backs_up_and_preserves_external_job_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);new=r/'new';old=r/'old';new.mkdir();old.mkdir()
            (new/'runtime.py').write_text('fixed=True\n');(old/'runtime.py').write_text('fixed=False\n')
            evidence=old/'jobs/q000001/provider/failed_attempts/one.json';evidence.parent.mkdir(parents=True);evidence.write_text('evidence')
            manifest={'files':[{'path':'runtime.py','new_sha256':up.sha(b'fixed=True\n'),'base_sha256':up.sha(b'fixed=False\n')}]}
            backup=up.apply(up.prepare(old,manifest,new),old)
            self.assertEqual((backup/'runtime.py').read_text(),'fixed=False\n')
            self.assertEqual(evidence.read_text(),'evidence');self.assertEqual(up.prepare(old,manifest,new),[])
