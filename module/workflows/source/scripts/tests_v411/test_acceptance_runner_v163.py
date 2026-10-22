"""Acceptance runner follows the CLI's P02 pause and latest Pack chain."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import run_acceptance_v411 as runner
from scripts.tests_v411 import test_workflow_v411 as flow


class AcceptanceRunnerTests(unittest.TestCase):
    setUpClass = classmethod(flow.WorkflowV411Tests.setUpClass.__func__)
    tearDownClass = classmethod(flow.WorkflowV411Tests.tearDownClass.__func__)

    def test_selected_pack_is_the_next_article_input(self):
        output = self.base / 'acceptance-runner-chain'
        output.mkdir()
        with patch.object(runner, 'render_docx_qa', side_effect=AssertionError('no external renderer')):
            job, selected, _, latest = runner.build_article(output, self.p0_pack, self.manifest['cases'][2])
            record = selected['metadata']['p02_selection']
            self.assertEqual([e['name'] for e in record['entities']],
                             [self.brand, '合成竞品甲', '合成竞品乙'])
            self.assertTrue(record['confirmed'])
            self.assertTrue(list((job / 'reviews').glob('awaiting_competitor_selection*.md')))
            self.assertEqual(latest, Path(selected['metadata']['p02_reference_pack_delivery']['pack_path']))
            self.assertEqual(selected['reference_pack']['pack_version'], 3)
            self.assertEqual(json.loads((latest / 'reference_pack.json').read_text())['pack_version'], 4)
            _, following, _, following_pack = runner.build_article(output, latest, self.manifest['cases'][1])
        self.assertEqual(following['reference_pack']['pack_version'], 5)
        self.assertNotIn('p02_reference_pack_delivery', following['metadata'])
        self.assertEqual(following_pack, Path(following['reference_pack']['path']))
        self.assertEqual(json.loads((following_pack / 'strategy/p02_selection.json').read_text()), record)

    def test_manifest_counts_selection_versions_and_frozen_title_counts(self):
        output = self.base / 'acceptance-runner-manifest'
        next_version = 2
        records = {}

        def build_article(root, pack, case):
            nonlocal next_version
            next_version += 1
            job = root / ('article_' + case['case_id'])
            value = {'job_kind': 'article', 'selected_pattern_id': case['pattern_id'],
                     'reference_pack': {'pack_id': 'synthetic', 'pack_version': next_version},
                     'metadata': {}}
            if case['pattern_id'] == 'P02':
                next_version += 1
                value['metadata'].update(p02_reference_pack_delivery={'pack_version': next_version},
                                         title_strategy=dict(runner.title_strategy.DEFAULT))
            records[str(job)] = value
            return job, value, {'docx': 'synthetic.docx'}, root / ('pack-v' + str(next_version))

        initial = {'metadata': {'reference_pack_delivery': {'pack_id': 'synthetic'}}}
        with patch.object(runner, 'build_positioning_pack', return_value=(self.positioning_pack, initial)), \
             patch.object(runner, 'build_p0', return_value=(self.p0_pack, initial, {'docx': 'synthetic.docx'})), \
             patch.object(runner, 'build_article', side_effect=build_article), \
             patch.object(runner, 'state', side_effect=lambda job: records[str(job)]), \
             patch.object(runner, 'render_docx_qa', return_value={'status': 'not-rendered', 'documents': []}):
            manifest = runner.create_acceptance(output)
        self.assertEqual(manifest['pack_versions'], list(range(1, 14)))
        self.assertEqual([case['pack_version'] for case in manifest['cases']], [2, 4, 5, 7, 8, 9, 11, 13])
        self.assertEqual(manifest['counts']['titles'], 120)


if __name__ == '__main__':
    unittest.main()
