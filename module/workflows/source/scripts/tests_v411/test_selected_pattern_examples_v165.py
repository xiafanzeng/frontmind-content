"""Offline configuration and actual prompt delivery, not article quality tests."""
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editorial_v165 as natural_flow
from shared import editorial_preparation as prep
from shared import recommendation_references as references
from shared import writing_context_v165 as prose, writing_requirements as requirements
from shared.example_acquisition import ExampleStore, AcquisitionError


class SelectedPatternExamplesTests(unittest.TestCase):
    def setUp(self):
        fixture = natural_flow.NaturalEditorialV165Tests(
            'test_all_six_patterns_route_actual_system_and_review_schema')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.base = fixture.root
        self.case_count = 0

    def job(self, pattern='P01'):
        self.case_count += 1
        self.fixture.root = self.base / str(self.case_count)
        self.fixture.root.mkdir()
        job = self.fixture.job(pattern)
        state = wf.load_state(job)
        state['selected_example_route'] = 'A'
        wf.save_state(job, state)
        prep.freeze(wf, job, prep.fixture())
        return job

    @staticmethod
    def acquired(store, url, **kwargs):
        return store._save(b'offline webpage',
            'STYLE_OPEN\n\nSTYLE_MIDDLE\n\n![image](https://example.com/image.jpg)\n\nSTYLE_END',
            {'title': 'synthetic style source', 'original_url': url, 'final_url': url,
             'obtained_via': 'offline_source', 'completeness': 'complete',
             'acquisition_status': 'complete'})

    def test_selected_counts_titles_and_complete_text_reach_actual_prompts(self):
        for pattern in sorted(prose.PATTERNS):
            with self.subTest(pattern=pattern):
                job = self.job(pattern)
                with patch.object(ExampleStore, 'acquire_http', self.acquired):
                    rows = references.register_selected(wf, wf.ROOT, job)
                _, entry = references.profile_items(wf.ROOT, pattern)
                self.assertEqual(len(rows), 2 if pattern == 'P01' else 1)
                self.assertEqual([r['title'] for r in rows], [e['title'] for e in entry['examples']])
                wf.atomic_json(job / 'production/article_draft.json', {
                    'article_markdown': self.fixture.body,
                    'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''})
                prompts = [prose.prompt_blueprint(wf, job), prose.prompt_article(wf, job),
                           prose.prompt_edit(wf, job)]
                for prompt in prompts:
                    self.assertIn(entry['estimated_length'], prompt)
                    self.assertIn('不插入图片、图注或配图占位', prompt)
                    for row in rows:
                        self.assertIn(row['title'], prompt)
                    if pattern != 'P01':
                        for text in ('STYLE_OPEN', 'STYLE_MIDDLE', 'STYLE_END'):
                            self.assertIn(text, prompt)
                        self.assertNotIn('![image]', prompt)
                self.assertIn(entry['estimated_length'], prose.preparation_commission(wf, job))
                self.assertNotIn('body_character_range', wf.load_state(job)['metadata']['effective_writing_requirements'])

    def test_type_switch_and_explicit_overrides_survive_ordinary_revision(self):
        job = self.job('P02')
        references.apply_selected_defaults(wf, wf.ROOT, job)
        state = wf.load_state(job)
        current = requirements.effective(wf, job, p0=False)
        requirements.merge_changes(state, current, explicit_fields={})
        self.assertIn('estimated_length', state['metadata']['pattern_example_defaults'])
        requirements.merge_changes(state, {'estimated_length': '用户指定约4000字符'})
        state['selected_pattern_id'] = 'P06'
        wf.save_state(job, state)
        references.apply_selected_defaults(wf, wf.ROOT, job)
        state = wf.load_state(job)
        self.assertEqual(state['metadata']['effective_writing_requirements']['estimated_length'], '用户指定约4000字符')
        self.assertNotIn('estimated_length', state['metadata']['pattern_example_defaults'])
        self.assertIn('怎么样', prose.commission(wf, job))

    def test_http_failure_uses_existing_reader_and_freezes_single_text(self):
        job = self.job('P06')
        store = ExampleStore(job)
        source = self.acquired(store, 'https://example.com/source')
        with patch.object(ExampleStore, 'acquire_http', side_effect=AcquisitionError('offline failed HTTP')), \
             patch('shared.host_tools.HostTools') as host:
            host.return_value.execute.return_value = source
            rows = references.register_selected(wf, wf.ROOT, job)
        self.assertEqual(len(rows), 1)
        self.assertEqual(host.return_value.execute.call_args.args[0], 'web_read')
        self.assertEqual(host.return_value.execute.call_args.args[1]['method'], 'reader')

    def test_extraction_drops_images_captions_and_keeps_body_end(self):
        item = {'body_start': '正文开始', 'body_end': '自然结束。',
                'omit_lines': ['缺失数据'], 'omit_line_prefixes': ['图为']}
        source = '# 网页标题\n\n**正文开始**\n\n完整段落。\n\n图为小店\n\n缺失数据\n\n![图](https://example.com/a)\n\n自然结束。返回搜狐，查看更多\n页脚'
        result = references.text_only_reference(source, item)
        self.assertEqual(result, '正文开始\n\n完整段落。\n\n自然结束。\n')

    def test_profile_is_new_article_only_and_legacy_pair_remains(self):
        self.assertTrue(references.profile_enabled(wf.make_state('new', 'article')))
        self.assertFalse(references.profile_enabled(wf.make_state('p0', 'p0')))
        job = self.job()
        state = wf.load_state(job)
        state['metadata'].pop('pattern_example_profile', None)
        state['flags']['offline_fixture'] = False
        wf.save_state(job, state)
        self.assertFalse(references.profile_enabled(state))
        rows = references.register(wf, wf.ROOT, job)
        self.assertEqual(len(rows), 2)
        self.assertNotIn('pattern_example_selection', wf.load_state(job)['metadata'])


if __name__ == '__main__':
    unittest.main()
