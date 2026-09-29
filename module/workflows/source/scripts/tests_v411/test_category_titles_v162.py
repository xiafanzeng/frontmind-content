"""Category title requests and frozen title-only revisions; no network/model calls."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_title_input_scope_final13 as scope
from shared import manuscript_revision, model_runtime, title_strategy, writing_context, writing_context_v14


class CategoryTitleTests(unittest.TestCase):
    setUp = scope.TitleInputScopeTests.setUp
    job = scope.TitleInputScopeTests.job
    step = scope.TitleInputScopeTests.step
    until = scope.TitleInputScopeTests.until
    finish = scope.TitleInputScopeTests.finish
    request_titles = scope.TitleInputScopeTests.request_titles
    retry = scope.TitleInputScopeTests.retry

    def category_job(self, pattern='P01', question='东莞腰腹吸脂机构推荐', brief=None):
        job = self.job()
        state = wf.load_state(job)
        state['selected_pattern_id'] = pattern
        state['question'] = {'question_text': question}
        state['metadata']['title_strategy'] = dict(title_strategy.DEFAULT)
        state['metadata']['writing_mission_input_mode'] = writing_context_v14.MODE
        wf.save_state(job, state)
        if brief:
            bp = wf.read_json(job/'blueprints/article_blueprint.json')
            bp['article_brief'] = brief
            wf.atomic_json(job/'blueprints/article_blueprint.json', bp)
        return job

    def test_requests_share_policy_full_body_and_hide_old_h1(self):
        job = self.category_job()
        for pattern, question in (('P01', '东莞腰腹吸脂机构推荐'), ('P02', '留学机构品牌推荐')):
            state = wf.load_state(job)
            state['selected_pattern_id'] = pattern
            state['question'] = {'question_text': question}
            wf.save_state(job, state)
            titles = wf.fixture_titles(job, p0=False)
            author = writing_context.prompt_titles(wf, job, p0=False, final_markdown=self.body)
            editor = writing_context.prompt_title_review(wf, job, p0=False, final_markdown=self.body, title_result=titles)
            for action, prompt in (('article_titles', author), ('article_title_review', editor)):
                system = model_runtime._initial_messages(action, prompt)[0]['content']
                self.assertTrue(title_strategy.matches(prompt))
                self.assertIn(question, prompt)
                self.assertIn(self.body.split('\n', 1)[1], prompt)
                self.assertNotIn('# 内部标题', prompt)
                self.assertIn(writing_context_v14.CATEGORY_TITLE_RULES, system)
                self.assertNotIn('不靠同义词', system)
                self.assertNotIn('形成不同阅读入口', system)
                self.assertIn('默认所有标题都不带品牌', system)
                self.assertIn('P01采用不带品牌的品类推荐标题', system)
            schema = model_runtime.submit_tool_for('article_title_review', prompt=editor)['function']['parameters']['properties']['result']
            self.assertIn('10个', schema['description'])
            self.assertNotIn('minItems', schema['properties']['candidates'])

    def test_explicit_brand_instruction_reaches_author_and_editor(self):
        job = self.category_job(brief='推荐合成机构。所有候选标题必须带“合成机构”品牌名。')
        raw = wf.fixture_titles(job, p0=False)
        for item in raw["candidates"]:
            item["title"] = "合成机构：" + item["title"]
        wf.validate_action_result(job, "article_titles", raw)
        for action, prompt in (
            ('article_titles', writing_context.prompt_titles(wf, job, p0=False, final_markdown=self.body)),
            ('article_title_review', writing_context.prompt_title_review(wf, job, p0=False, final_markdown=self.body, title_result=raw))):
            self.assertIn('所有候选标题必须带', prompt)
            self.assertIn('明确要求带品牌时才覆盖此默认', model_runtime._initial_messages(action, prompt)[0]['content'])

    def test_new_default_is_scoped_and_legacy_revision_wins(self):
        state = wf.make_state('new', 'article')
        for pattern, count in (('P01',10), ('P02',10), ('P03',20), ('P04',20), ('P05',20), ('P06',20)):
            state['selected_pattern_id'] = pattern
            self.assertEqual(title_strategy.expected_count(state), count)
        self.assertEqual(title_strategy.expected_count(wf.make_state('p0', 'p0')), 20)
        state['selected_pattern_id'] = 'P01'
        state['metadata']['article_title_revision'] = {'edits_markdown':'旧请求'}
        self.assertEqual(title_strategy.expected_count(state), 20)
        state['metadata']['article_title_revision']['title_strategy'] = dict(title_strategy.DEFAULT)
        self.assertEqual(title_strategy.expected_count(state), 10)
        state['metadata']['article_title_revision']['title_strategy']['requested_count'] = 11
        with self.assertRaises(ValueError):
            title_strategy.expected_count(state)

    def test_title_only_upgrade_preserves_body_and_snapshot(self):
        job = self.job()  # historical 20-title job, no new marker
        self.finish(job)
        self.assertEqual(wf.read_json(Path(wf.load_state(job)['metadata']['delivery']['title_map']))['total_count'], 20)
        before = {p.name:p.read_bytes() for p in (job/'production').glob('*.json') if 'title' not in p.name}
        old_prompt = wf.prompt_titles(job, p0=False)
        old_identity = model_runtime.request_fingerprint('article_titles', old_prompt)
        calls = len(self.actions)
        self.request_titles(job, '本轮10个标题不带品牌，围绕本题机构推荐做近义改写。')
        frozen = manuscript_revision.current_title_revision(wf, job, p0=False)
        snapshot = Path(frozen['source_snapshot'])
        self.assertEqual(frozen['title_strategy'], title_strategy.DEFAULT)
        adopted = wf.load_state(job)
        adopted['metadata'].pop('article_title_revision')
        self.assertEqual(title_strategy.expected_count(adopted), 10)  # subsequent body edits retain the adopted title policy
        self.assertEqual(wf.prompt_titles(snapshot, p0=False), old_prompt)
        self.assertEqual(model_runtime.request_fingerprint('article_titles', wf.prompt_titles(snapshot,p0=False)), old_identity)
        new_prompt = wf.prompt_titles(job, p0=False)
        self.assertNotEqual(model_runtime.request_fingerprint('article_titles', new_prompt), old_identity)
        self.retry(job, 'article_titles')
        self.assertEqual(wf.prompt_titles(job,p0=False), new_prompt)
        self.finish(job)
        self.assertEqual(self.actions[calls:], ['article_titles','article_title_review'])
        self.assertEqual(before, {p.name:p.read_bytes() for p in (job/'production').glob('*.json') if 'title' not in p.name})
        delivery = wf.load_state(job)['metadata']['delivery']
        self.assertEqual(wf.read_json(Path(delivery['title_map']))['total_count'], 10)
        self.assertIn('以下 10 个标题', Path(delivery['title_options']).read_text())
        self.assertIn('以下 10 个标题', Path(delivery['title_options_html']).read_text())
        self.assertNotIn('# 内部标题', Path(delivery['markdown']).read_text())
        manuscript_revision.validate_completed_manuscript(wf,job,p0=False)
        # A second title-only revision must validate the completed 10-title job.
        self.request_titles(job, '保持10个同主题标题，标题明确带合成机构品牌。')
        self.finish(job)
        manuscript_revision.validate_completed_manuscript(wf,job,p0=False)

    def test_arrival_validation_rejects_stale_twenty_titles(self):
        job = self.category_job()
        raw = wf.fixture_titles(job,p0=False)
        self.assertEqual(len(raw['candidates']),10)
        wf.validate_action_result(job,'article_titles',raw)
        old = copy.deepcopy(raw)
        old['candidates'] += [{'title':f'旧候选{i}', 'angle':'旧表达'} for i in range(10)]
        with self.assertRaises(ValueError):
            wf.validate_action_result(job,'article_titles',old)

    def test_historical_request_payload_is_unchanged_by_surrounding_new_default(self):
        job = self.job()
        self.finish(job)
        prompt = wf.prompt_titles(job,p0=False)
        identity = model_runtime.request_fingerprint('article_titles',prompt)
        self.retry(job,'article_titles')
        self.assertEqual(wf.prompt_titles(job,p0=False), prompt)
        self.assertEqual(model_runtime.request_fingerprint('article_titles',prompt),identity)
        self.assertNotIn('title_strategy',wf.load_state(job)['metadata'])


if __name__ == '__main__':
    unittest.main()
