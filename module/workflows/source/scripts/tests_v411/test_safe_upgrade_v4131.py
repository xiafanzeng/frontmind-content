"""No live/local customer code is modified by these temporary-directory tests."""
import base64
import tempfile
import unittest
from pathlib import Path
from scripts import upgrade_to_v4131 as upgrade

class UpgradeTests(unittest.TestCase):
    def test_hunk_preserves_unrelated_sdk_fix(self):
        encode=lambda s:base64.b64encode(s).decode()
        raw=b'local SDK fix\nhead\nold\ntail\n'
        h=[{'before':encode(b'head\nold\ntail\n'),'after':encode(b'head\nnew\ntail\n')}]
        self.assertEqual(b'local SDK fix\nhead\nnew\ntail\n',upgrade.merge_hunks(raw,h))
        self.assertEqual(upgrade.merge_hunks(raw,h),upgrade.merge_hunks(upgrade.merge_hunks(raw,h),h))

    def test_conflicting_or_ambiguous_hunk_stops(self):
        h=[{'before':base64.b64encode(b'old').decode(),'after':base64.b64encode(b'new').decode()}]
        for raw in (b'local changed',b'old old'):
            with self.assertRaises(ValueError):upgrade.merge_hunks(raw,h)

    def test_protected_files_and_paths_cannot_be_modified(self):
        for file in ('config/xty.json','jobs/a.txt','shared/agents_runtime.py','../escape'):
            with self.assertRaises(ValueError):upgrade.safe_file(Path('/tmp/test'),file)

    def test_failed_whole_plan_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'new';target=root/'old';source.mkdir();target.mkdir()
            (source/'first.md').write_text('new');(target/'first.md').write_text('base')
            (source/'second.md').write_text('new');(target/'second.md').write_text('local')
            manifest={'files':[{'path':f,'new_sha256':upgrade.sha(b'new'),'base_sha256':upgrade.sha(b'base'),'hunks':[]} for f in ('first.md','second.md')]}
            with self.assertRaises(ValueError):upgrade.prepare(target,manifest,source)
            self.assertEqual('base',(target/'first.md').read_text())
            self.assertFalse((target/'.frontmind-upgrade-backups').exists())

    def test_success_saves_backup_and_receipt(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'new';target=root/'old';source.mkdir();target.mkdir()
            (source/'file.md').write_text('new');(target/'file.md').write_text('base')
            manifest={'files':[{'path':'file.md','new_sha256':upgrade.sha(b'new'),'base_sha256':upgrade.sha(b'base')}]}
            plans=upgrade.prepare(target,manifest,source);backup=upgrade.apply(plans,target)
            self.assertEqual('base',(backup/'file.md').read_text());self.assertEqual('new',(target/'file.md').read_text())
            self.assertTrue((backup/'upgrade_receipt.json').is_file())
            self.assertEqual([],upgrade.prepare(target,manifest,source))

if __name__=='__main__':unittest.main()
