"""Context behavior and actual payload roles; no claim of generated prose quality."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.tests_v411 import test_article_reader_final8 as fixtures
from scripts import frontmind_workflow as controller
from shared import article_positioning, natural_editor, writing_context as wc, model_runtime as runtime


class NaturalWritingContextTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.ArticleReaderTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.state['metadata'] = {'writing_editor_contract': natural_editor.CONTRACT,
                                       'article_reader_contract': article_positioning.CURRENT_CONTRACT}
        self.case.blueprint['article_brief'] = 'CURRENT_BRIEF: 新闻品宣专题，介绍主对象；不写替代路径。'
        self.case.put('blueprints/article_blueprint.json', self.case.blueprint)

    def test_effective_payloads_select_new_roles_without_old_choice_contract(self):
        for stage, builder in fixtures.BUILDERS.items():
            prompt = builder(self.case.wf, self.case.job, p0=False)
            action = 'article_' + stage
            messages = runtime._initial_messages(action, prompt)
            self.assertTrue(prompt.startswith(natural_editor.MARKER + '\n'))
            self.assertEqual(messages[1]['content'], prompt)
            self.assertIn(article_positioning.NATURAL_ROLES[stage], messages[0]['content'])
            self.assertNotIn(article_positioning.CHOICE_LOGIC, messages[0]['content'])

    def test_consolidated_brief_replaces_concurrent_historical_commands(self):
        original = (self.case.job / 'blueprints/article_blueprint.json').read_bytes()
        prompt = wc.prompt_article(self.case.wf, self.case.job, p0=False)
        self.assertIn(self.case.blueprint['article_brief'], prompt)
        self.assertNotIn(self.case.state['decisions']['blueprint_edits'], prompt)
        self.assertNotIn(self.case.blueprint['answer_use'], prompt)
        self.assertNotIn('FULL_QUESTION_POSITIONING', prompt)
        self.assertEqual((self.case.job / 'blueprints/article_blueprint.json').read_bytes(), original)

    def test_reference_roles_keep_ai_at_selection_not_authoring(self):
        ai = self.case.answers[0]
        self.case.put('examples/ai.md', ai)
        self.case.wf.load_examples = lambda *_: [
            {'title': '独立文风例文', 'path': 'examples/current.md'},
            {'title': '通义千问原回答', 'path': 'examples/ai.md'},
            {'title': '文风例文的重复引用', 'path': 'examples/current.md'}]
        refs = wc._natural_reference_sets(self.case.wf, self.case.job, p0=False)
        self.assertEqual([r['text'] for r in refs['style']], [self.case.example])
        self.assertEqual([r['text'] for r in refs['content']], self.case.answers)
        blueprint = wc.prompt_blueprint(self.case.wf, self.case.job, p0=False)
        self.assertEqual(blueprint.count(ai), 1)
        for builder in (wc.prompt_article, wc.prompt_edit):
            prompt = builder(self.case.wf, self.case.job, p0=False)
            self.assertNotIn(ai, prompt)
            self.assertEqual(prompt.count(self.case.example), 1)
        self.assertEqual(len(wc.reference_length_budget(self.case.wf, self.case.job, p0=False)['samples']), 2)

    def test_explicit_length_role_keeps_sample_statistics_without_style_prose(self):
        # Suitability is an editorial choice recorded as a role, not a lexical
        # test of words in the example. Its source file remains untouched.
        source = self.case.job / 'examples/current.md'
        before = source.read_bytes()
        self.case.wf.load_examples = lambda *_: [
            {'title': '既有篇幅样本', 'path': 'examples/current.md', 'role': 'length_only'}]
        refs = wc._natural_reference_sets(self.case.wf, self.case.job, p0=False)
        self.assertEqual(refs['style'], [])
        self.assertEqual([row['text'] for row in refs['length']], [self.case.example])
        for builder in (wc.prompt_blueprint, wc.prompt_article, wc.prompt_edit):
            prompt = builder(self.case.wf, self.case.job, p0=False)
            self.assertNotIn(self.case.example, prompt)
            self.assertEqual('既有篇幅样本' in prompt, builder is wc.prompt_blueprint)
        self.assertEqual(source.read_bytes(), before)

    def test_selected_length_budget_replaces_raw_sample_statistics_after_blueprint(self):
        self.case.blueprint['estimated_length'] = 'SELECTED_BUDGET：约4330字符，不设下限。'
        self.case.put('blueprints/article_blueprint.json', self.case.blueprint)
        selection = wc.prompt_blueprint(self.case.wf, self.case.job, p0=False)
        self.assertIn('longest_sample_characters', selection)
        for builder in (wc.prompt_article, wc.prompt_edit, wc.prompt_finalize):
            prompt = builder(self.case.wf, self.case.job, p0=False)
            self.assertIn(self.case.blueprint['estimated_length'], prompt)
            self.assertNotIn('longest_sample_characters', prompt)
            self.assertNotIn('篇幅样本统计', prompt)

    def test_non_ai_background_role_is_available_to_selection_only(self):
        background = 'EXPLICIT_BACKGROUND：本题历史市场资料，并非行文范本。'
        self.case.put('examples/background.md', background)
        self.case.wf.load_examples = lambda *_: [
            {'title': '历史背景', 'path': 'examples/background.md', 'role': 'content_background'}]
        refs = wc._natural_reference_sets(self.case.wf, self.case.job, p0=False)
        self.assertEqual(refs['style'], [])
        self.assertIn(background, [row['text'] for row in refs['content']])
        self.assertIn(background, wc.prompt_blueprint(self.case.wf, self.case.job, p0=False))
        for builder in (wc.prompt_article, wc.prompt_edit):
            self.assertNotIn(background, builder(self.case.wf, self.case.job, p0=False))

    def test_save_and_reload_real_examples_retains_chosen_role_and_original_text(self):
        store = controller.ExampleStore(self.case.job)
        originals = [('旧篇幅样本', 'ORIGINAL_LENGTH_ONLY_BODY'),
                     ('市场背景', 'ORIGINAL_NON_AI_BACKGROUND_BODY')]
        acquired = [store.import_user_text(body, title) for title, body in originals]
        items = [{'artifact_id': acquired[0]['artifact_id'], 'reference_role': 'length_only', 'role': '文风参考'},
                 {'artifact_id': acquired[1]['artifact_id'], 'role': 'content_background'}]
        self.case.state['flags'] = {'offline_fixture': False}
        with patch.object(controller, 'load_state', return_value=self.case.state):
            saved = controller.save_examples(self.case.job, items, 'question')
            reloaded = controller.load_examples(self.case.job, 'question')
            self.assertEqual(saved, reloaded)
            self.assertEqual([x['role'] for x in reloaded], ['length_only', 'content_background'])
            self.case.wf.load_examples = controller.load_examples
            refs = wc._natural_reference_sets(self.case.wf, self.case.job, p0=False)
            self.assertEqual(refs['style'], [])
            self.assertEqual([x['text'].strip() for x in refs['length']], [body for _, body in originals])
            for item, original in zip(reloaded, acquired):
                self.assertEqual(item['text_sha256'], original['text_sha256'])
            # Historical jobs keep their old interpretation on a future save.
            self.case.state['metadata'] = {'article_reader_contract': article_positioning.LEGACY_EDITOR_CONTRACT}
            legacy = controller.save_examples(self.case.job, items, 'question')
            self.assertEqual([x['role'] for x in legacy], ['文风参考', '文风参考'])
            self.assertEqual([x['text_sha256'] for x in legacy], [x['text_sha256'] for x in acquired])

    def test_offline_example_save_has_the_same_v12_role_projection(self):
        self.case.state['flags'] = {'offline_fixture': True}
        with patch.object(controller, 'load_state', return_value=self.case.state):
            saved = controller.save_examples(self.case.job, [
                {'title': '只看篇幅', 'markdown': 'SYNTHETIC_LENGTH_BODY', 'reference_role': 'length_only'},
                {'title': '独立文风', 'markdown': 'SYNTHETIC_STYLE_BODY'}], 'question')
        self.assertEqual([x['role'] for x in saved], ['length_only', '文风参考'])

    def test_author_projection_preserves_fact_conditions_without_source_narrative(self):
        fact = '合成甲夜间服务尚未启用；日间预约至少提前两日。'
        source_note = 'SOURCE_USE_NOTE：研究时曾误写夜间全天开放，现已纠正。'
        self.case.blueprint['writing_material_markdown'] = fact
        self.case.blueprint['writing_material_sources'][0]['use'] = source_note
        self.case.put('blueprints/article_blueprint.json', self.case.blueprint)
        self.case.put('production/article_editorial_review.json', {'needs_revision': True, 'comments': ['删除无据开放时间。']})
        path = self.case.job / 'blueprints/article_blueprint.json'
        before = path.read_bytes()
        for builder in (wc.prompt_article, wc.prompt_edit, wc.prompt_repair):
            prompt = builder(self.case.wf, self.case.job, p0=False)
            self.assertEqual(prompt.count(fact), 1)
            self.assertNotIn(source_note, prompt)
            self.assertNotIn('inputs/source.md', prompt)
        review = wc.prompt_finalize(self.case.wf, self.case.job, p0=False)
        self.assertIn(fact, review)
        self.assertIn(source_note, review)
        self.assertIn('inputs/source.md', review)
        self.assertEqual(path.read_bytes(), before)

    def test_review_and_repair_use_exact_same_candidate_and_separate_artifacts(self):
        self.case.put('production/article_editorial_review.json', {'needs_revision': True, 'comments': ['第二段删除重复说明。']})
        review = wc.prompt_finalize(self.case.wf, self.case.job, p0=False)
        repair = wc.prompt_repair(self.case.wf, self.case.job, p0=False)
        for prompt in (review, repair):
            self.assertEqual(prompt.count(self.case.body), 1)
            self.assertNotIn(self.case.answers[0], prompt)
            self.assertNotIn(self.case.example, prompt)
        self.assertIn('第二段删除重复说明。', repair)
        self.assertEqual(json.loads((self.case.job / 'production/article_edited.json').read_text())['article_markdown'], self.case.body)
        self.case.put('production/article_editorial_review.json', {'needs_revision': False, 'comments': []})
        with self.assertRaises(wc.EditorialContractError):
            wc.prompt_repair(self.case.wf, self.case.job, p0=False)

    def test_edit_and_repair_payloads_assign_actual_composition_role_once(self):
        self.case.put('production/article_editorial_review.json', {'needs_revision': True, 'comments': ['合并重复后整理段落。']})
        for stage, builder in (('edit', wc.prompt_edit), ('repair', wc.prompt_repair)):
            prompt = builder(self.case.wf, self.case.job, p0=False)
            payload = runtime.build_payload('article_'+stage, prompt)
            system = payload['messages'][0]['content']
            self.assertEqual(system.count(article_positioning.NATURAL_ROLES[stage]), 1)
            self.assertIn('重新组织', system)
            self.assertEqual(payload['messages'][1]['content'].count(self.case.body), 1)
            self.assertNotIn(article_positioning.EDIT, system)

    def test_titles_read_selected_final_not_host_review_result(self):
        final_body = '# 旧题\n\n**合成甲服务中心**\n\nACTUAL_REPAIRED_BODY'
        self.case.put('production/article_finalized.json', {'outcome': 'revised', 'article_markdown': final_body})
        self.case.put('provider/article_finalize/result.json', {'needs_revision': True, 'comments': ['HOST_COMMENT']})
        prompt = wc.prompt_titles(self.case.wf, self.case.job, p0=False)
        self.assertIn('**合成甲服务中心**', prompt)
        self.assertIn('ACTUAL_REPAIRED_BODY', prompt)
        self.assertNotIn('HOST_COMMENT', prompt)
        self.assertNotIn('# 旧题', prompt)

    def test_both_title_stages_inherit_only_latest_manuscript_commission(self):
        from shared import manuscript_revision as mr
        final_body = '# 旧内部题\n\n合成甲服务中心的新业务介绍。'
        current_edits = 'LATEST_EDITS：统一完整名称为合成甲服务中心，按新闻品宣体裁写。'
        titles = {'candidates': [{'title': f'合成甲服务中心业务介绍{i:02d}', 'angle': '业务'} for i in range(20)],
                  'canonical_title_id': 'title_01'}
        for p0 in (False, True):
            prefix = 'p0' if p0 else 'article'
            self.case.state['job_kind'] = prefix
            path = f'production/manuscript_revisions/{prefix}_current.json'
            record = {'contract': mr.CONTRACT_VERSION, 'prefix': prefix,
                      'base_markdown': self.case.body, 'base_sha256': mr.text_hash(self.case.body),
                      'edits_markdown': current_edits, 'edits_sha256': mr.text_hash(current_edits),
                      'source': {'draft_sha256': mr.file_hash(self.case.job/f'production/{prefix}_draft.json'),
                                 'blueprint_sha256': mr.file_hash(self.case.job/f'blueprints/{prefix}_blueprint.json')}}
            self.case.put(path, record)
            self.case.put(f'production/{prefix}_finalized.json', {'outcome': 'revised', 'article_markdown': final_body})
            self.case.state['metadata'][prefix+'_manuscript_revision'] = {
                'path': path, 'sha256': mr.file_hash(self.case.job/path)}
            self.case.state['metadata'][prefix+'_manuscript_revision_history'] = [
                {'edits_markdown': 'OLD_EDITS：旧名称与旧指南体裁'}]
            before = (self.case.job/path).read_bytes()
            prompts = [wc.prompt_titles(self.case.wf, self.case.job, p0=p0),
                       wc.prompt_title_review(self.case.wf, self.case.job, p0=p0, title_result=titles)]
            for prompt in prompts:
                self.assertEqual(prompt.count(current_edits), 1)
                self.assertNotIn('OLD_EDITS', prompt)
                self.assertNotIn(self.case.state['decisions']['blueprint_edits'], prompt)
                old = json.loads((self.case.job/f'blueprints/{prefix}_blueprint.json').read_text())
                self.assertNotIn(old['article_brief'], prompt)
                self.assertNotIn(old['estimated_length'], prompt)
                self.assertIn('合成甲服务中心的新业务介绍。', prompt)
            self.assertEqual((self.case.job/path).read_bytes(), before)

    def test_completed_manuscript_revision_uses_current_request_and_actual_base_only(self):
        from shared import manuscript_revision as mr
        old_brief = 'OLD_BRIEF：用旧名称，后四个主体不能只有一段。'
        old_adjustment = 'OLD_ADJUSTMENT：必须写到旧预算且保留旧名。'
        old_budget = 'OLD_BUDGET_1348'
        fact = '2026年3月启动改造；夜间服务尚未启用；日间预约至少提前两日。'
        self.case.blueprint.update(article_brief=old_brief, estimated_length=old_budget,
                                   candidate_order=['OLD_ORDER_A', 'OLD_ORDER_B'],
                                   material_adjustments=[old_adjustment], writing_material_markdown=fact)
        self.case.put('blueprints/article_blueprint.json', self.case.blueprint)
        base = self.case.body + '\n\nBASE_KEEP：这一段保留原来的事实和加粗排版。'
        request = 'LATEST_LOCAL：只把第二段名称改为合成甲服务中心，其余沿用基稿。'
        path = 'production/manuscript_revisions/current.json'
        self.case.put(path, {'contract': mr.CONTRACT_VERSION, 'prefix': 'article',
            'base_markdown': base, 'base_sha256': mr.text_hash(base),
            'edits_markdown': request, 'edits_sha256': mr.text_hash(request),
            'source': {'draft_sha256': mr.file_hash(self.case.job/'production/article_draft.json'),
                       'blueprint_sha256': mr.file_hash(self.case.job/'blueprints/article_blueprint.json')}})
        self.case.state['metadata']['article_manuscript_revision'] = {'path': path, 'sha256': mr.file_hash(self.case.job/path)}
        self.case.put('production/article_edited.json', {'article_markdown': base, 'edit_status': 'accepted',
            'editorial_notes': [], 'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''})
        self.case.put('production/article_editorial_review.json', {'needs_revision': True, 'comments': ['按最新名称完成本轮修改。']})
        before = {p: p.read_bytes() for p in self.case.job.rglob('*') if p.is_file()}
        with patch.object(self.case.wf, 'load_examples', side_effect=AssertionError('old examples must not reopen a local edit')):
            for builder in (wc.prompt_edit, wc.prompt_finalize, wc.prompt_repair):
                prompt = builder(self.case.wf, self.case.job, p0=False)
                self.assertEqual(prompt.count(request), 1)
                self.assertEqual(prompt.count(base), 1)
                self.assertIn(fact, prompt)
                for obsolete in (old_brief, old_adjustment, old_budget, 'OLD_ORDER_A',
                                 self.case.state['question']['question_text'], self.case.example,
                                 'longest_sample_characters'):
                    self.assertNotIn(obsolete, prompt)
        self.assertEqual(before, {p: p.read_bytes() for p in self.case.job.rglob('*') if p.is_file()})

    def test_pattern_relationships_are_not_all_converted_to_brand_introductions(self):
        for pattern in ('P01', 'P02', 'P03', 'P04', 'P05', 'P06'):
            self.case.state['selected_pattern_id'] = pattern
            prompt = wc.prompt_article(self.case.wf, self.case.job, p0=False)
            self.assertIn(wc.NATURAL_PATTERN_GUIDANCE[pattern], prompt)
            self.assertNotIn(wc.NATURAL_PATTERN_GUIDANCE['P00'], prompt)

    def test_prior_blueprint_rewrite_does_not_reinject_old_fact_prose(self):
        import hashlib
        current = self.case.state['decisions']['blueprint_edits']
        self.case.put('inputs/article_blueprint_edit_outline.json', {
            'edit_sha256': hashlib.sha256(current.encode()).hexdigest(),
            'headings': ['旧章节'], 'revision_candidate': self.case.blueprint})
        prompt = wc.prompt_blueprint(self.case.wf, self.case.job, p0=False)
        self.assertIn('旧章节', prompt)
        self.assertNotIn(self.case.blueprint['writing_material_markdown'], prompt)
        self.assertNotIn(self.case.blueprint['article_brief'], prompt)
        self.assertIn(current, prompt)

    def test_historical_positioning_is_preserved_but_not_reinjected(self):
        source = self.case.job / 'question_positioning/question_positioning.json'
        before = source.read_bytes()
        for builder in (wc.prompt_blueprint, wc.prompt_article, wc.prompt_edit, wc.prompt_finalize):
            prompt = builder(self.case.wf, self.case.job, p0=False)
            self.assertNotIn('FULL_QUESTION_POSITIONING', prompt)
        self.assertEqual(source.read_bytes(), before)

    def test_malformed_order_is_not_forwarded_as_current_writing_intent(self):
        self.case.blueprint['candidate_order'] = 'WRONG_TYPE_TITLE_STAGE_REMINDER'
        self.case.put('blueprints/article_blueprint.json', self.case.blueprint)
        prompt = wc.prompt_article(self.case.wf, self.case.job, p0=False)
        self.assertNotIn('WRONG_TYPE_TITLE_STAGE_REMINDER', prompt)
        self.assertIn(self.case.blueprint['article_brief'], prompt)

    def test_host_preserves_ai_content_reading_without_classifying_it_as_style(self):
        from shared.host_tools import HostTools
        self.case.state['flags'] = {'offline_fixture': True}
        self.case.put('job_state.json', self.case.state)
        self.case.put('examples/ai.md', self.case.answers[0])
        self.case.put('inputs/article_blueprint_edit_outline.json', {'old': 'not factual material'})
        self.case.put('examples/question/index.json', {'examples': [
            {'title':'通义千问原回答','path':str((self.case.job/'examples/ai.md').resolve())},
            {'title':'真实文风例文','path':str((self.case.job/'examples/current.md').resolve())}]})
        tools = HostTools(Path(__file__).resolve().parents[2], self.case.job, 'article_blueprint')
        records = list(tools.artifacts.values())
        ai = next(row for row in records if row['path'].endswith('examples/ai.md'))
        style = next(row for row in records if row['path'].endswith('examples/current.md'))
        self.assertEqual(ai['category'], 'content_background')
        self.assertTrue(ai['required'])
        self.assertEqual(style['category'], 'example')
        self.assertTrue(style['required'])
        self.assertFalse(any(row['path'].endswith('blueprint_edit_outline.json') for row in records))

    def test_host_explicit_background_role_is_v12_only_and_readable(self):
        from shared.host_tools import HostTools
        self.case.state['flags'] = {'offline_fixture': True}
        self.case.put('examples/background.md', 'NON_AI_BACKGROUND_SOURCE_BODY')
        self.case.put('examples/question/index.json', {'examples': [
            {'title': '本题背景材料', 'path': str((self.case.job/'examples/background.md').resolve()),
             'reference_role': 'content_background'}]})
        for current in (True, False):
            if not current:
                self.case.state['metadata'] = {'article_reader_contract': article_positioning.LEGACY_EDITOR_CONTRACT}
            self.case.put('job_state.json', self.case.state)
            tools = HostTools(Path(__file__).resolve().parents[2], self.case.job, 'article_blueprint')
            row = next(x for x in tools.artifacts.values() if x['path'].endswith('examples/background.md'))
            self.assertEqual(row['category'], 'content_background' if current else 'example')
            self.assertTrue(row['required'])
            self.assertEqual(tools._text(row), 'NON_AI_BACKGROUND_SOURCE_BODY')

    def test_p0_keeps_third_pass_full_examples_without_fixed_opening_template(self):
        self.case.state.update(job_kind='p0')
        self.case.state['metadata'] = {'writing_editor_contract': natural_editor.CONTRACT,
                                       'p0_style_contract': 'frontmind-p0-style/4.12.8'}
        self.case.put('blueprints/p0_blueprint.json', {**self.case.blueprint, 'kind': 'p0'})
        records = [{'title': 'Reference A', 'text': 'FULL_EXAMPLE_A'},
                   {'title': 'Reference B', 'text': 'FULL_EXAMPLE_B'}]
        with patch('shared.brand_references.job_examples', return_value=records):
            prompt = wc.prompt_p0_style(self.case.wf, self.case.job)
        self.assertEqual(prompt.count(self.case.body), 1)
        self.assertIn('FULL_EXAMPLE_A', prompt)
        self.assertIn('FULL_EXAMPLE_B', prompt)
        self.assertNotIn(self.case.state['decisions']['blueprint_edits'], prompt)
        self.assertNotIn('开头两段一律', natural_editor.system('p0_style'))


if __name__ == '__main__':
    unittest.main()
