from unittest.mock import patch
from scripts.tests_v411.historical_profiles import historical_profile
"""A single native host edit, with complete article and actual title inputs."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from shared import model_runtime as runtime, p0_titles
from shared.writing_context import prompt_title_review
from scripts.tests_v411.test_model_runtime import FakeTools
from scripts.tests_v411.test_responses_runtime_v4116 import native


class TitleReviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        archived=patch.object(runtime, "profile_for", side_effect=historical_profile)
        archived.start(); self.addCleanup(archived.stop)

    def test_prompt_preserves_complete_sources_without_authorizing_body_rewrite(self):
        body = '# 原稿标识\n\n开篇。\n## 小节\n正文中的共同条件和结尾。\n'
        raw = {'candidates': [{'title': f'候选{i}', 'angle': f'角度{i}'} for i in range(20)],
               'canonical_title_id': 'title_03'}
        workflow = SimpleNamespace(load_state=lambda job: {'metadata': {}})
        prompt = prompt_title_review(workflow, Path('fixture'), p0=True,
                                     final_markdown=body, title_result=raw)
        self.assertEqual(prompt.count(body.split("\n",1)[1]), 1)
        self.assertNotIn("# 原稿标识",prompt)
        self.assertIn(json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2), prompt)
        self.assertIn('不返回article_markdown，不改正文', prompt)
        payload = runtime.build_payload('p0_title_review', prompt)
        self.assertEqual(payload['model'], 'gpt-6-astra')
        self.assertEqual(payload['reasoning'], {'effort': 'high'})
        self.assertEqual(payload['instructions'], p0_titles.system('p0_title_review'))
        submit = next(item for item in payload['tools'] if item['name'] == 'submit_result')
        self.assertNotIn('article_markdown', submit['parameters']['properties']['result']['properties'])

    def test_invalid_review_submission_stops_without_another_paid_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'package'; package.mkdir()
            job = Path(directory) / 'job'; job.mkdir()
            tools = FakeTools(); tools.read = True
            calls = []
            def transport(*args):
                calls.append(args)
                return native(name='submit_result', arguments={'result': {'invalid': True}})
            def validator(value):
                raise ValueError('not a complete title edit')
            def run(retry=False):
                return runtime.run_action(package, job, 'p0_title_review', 'complete inputs', validator,
                                          host_tools=tools, transport=transport, offline=True, retry=retry)
            with self.assertRaises(runtime.ProviderActionError) as error:
                run()
            self.assertEqual(error.exception.code, 'invalid_result_contract')
            self.assertEqual(len(calls), 1)
            with self.assertRaises(runtime.ProviderActionError) as error:
                run(retry=True)
            self.assertEqual(error.exception.code, 'saved_submission_not_recoverable')
            self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
