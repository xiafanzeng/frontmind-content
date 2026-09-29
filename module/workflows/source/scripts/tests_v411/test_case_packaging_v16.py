"""Do not merge a current sample into residue from an earlier collection."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import package_v16 as package


class CaseDestinationTests(unittest.TestCase):
    def test_nonempty_destination_is_rejected_before_reading_or_copying_the_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('old_prompt.md', '.hidden-residue', 'old_materials/source.txt'):
                with self.subTest(residue=name):
                    case=root/name.replace('/','_')
                    destination=case/'generated/P02'
                    residue=destination/name
                    residue.parent.mkdir(parents=True)
                    residue.write_bytes(b'preserve previous collection')
                    before={str(path.relative_to(destination)):path.read_bytes()
                            for path in destination.rglob('*') if path.is_file()}
                    with patch.object(package.manuscript_revision,'validate_completed_manuscript') as validate:
                        with self.assertRaisesRegex(RuntimeError,'must be absent or empty'):
                            package.collect_completed_case('P02',{'job':str(root/'missing-job'),'status':'accepted'},case)
                        validate.assert_not_called()
                    after={str(path.relative_to(destination)):path.read_bytes()
                           for path in destination.rglob('*') if path.is_file()}
                    self.assertEqual(after,before)

    def test_absent_or_empty_destination_reaches_normal_chain_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            job=root/'job';job.mkdir()
            (job/'job_state.json').write_text(json.dumps({'status':'running_article_production'}))
            for create_empty in (False,True):
                with self.subTest(existing_empty=create_empty):
                    case=root/str(create_empty)
                    destination=case/'generated/P01'
                    if create_empty:
                        destination.mkdir(parents=True)
                    with self.assertRaisesRegex(RuntimeError,'complete model chain'):
                        package.collect_completed_case('P01',{'job':str(job),'status':'accepted'},case)
                    self.assertEqual(destination.exists(),create_empty)
                    if create_empty:
                        self.assertEqual(list(destination.iterdir()),[])


if __name__=='__main__':
    unittest.main()
