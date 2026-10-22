"""Offline integration coverage for the six-genre natural editor.

Every source, manuscript and review below is synthetic. No provider or search
is called, and passing these tests says nothing about real prose acceptance.
"""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from shared import (article_pool, editorial_preparation as prep, manuscript_revision, model_runtime,
                    natural_editorial_v165 as runner, question_positioning_handoff,
                    title_strategy, writer_measure, writing_context,
                    writing_context_v16 as old_prose, writing_context_v165 as prose)
from shared.host_tools import HostTools

REAL_WRITE_DOCX = wf.write_docx


class NaturalEditorialV165Tests(unittest.TestCase):
    def setUp(self):
        actual_ensure = wf.ensure_action
        flow.NaturalEditorFlowTests.setUp(self)
        self.body = ('# 合成终端的日常使用\n\n'
                     '合成品牌把测量和结果查看安排在同一台终端里。使用时，先按屏幕提示操作，再查看结果。\n\n'
                     '## 看得见的操作\n\n界面把每一步放在当前位置，初次使用的人也能顺着完成。'
                     '本篇仅为离线合成稿，不描述真实企业。\n\n'
                     '终端把结果分成几个页面，使用者可以先看本次记录，再回到前一次记录。页面上的时间帮助区分不同的记录，'
                     '数据从哪里进入、接下来在哪里查看，都沿着操作过程说明。介绍产品时可以选择这些具体动作展开，让读者了解一台终端怎样使用。\n\n'
                     '一次使用结束后，设备回到开始界面。下一位使用者从这里进入，仍然按照同样的提示完成操作。'
                     '场景、段落与名称均为测试编造的数据，保存它们只是为了检查编辑流程是否继承了上一份完整稿和本轮意见。')
        self.repaired = self.body.replace('看得见的操作', '顺着屏幕完成操作')
        self.review_plan = [{'needs_revision': False, 'comments': []}]
        self.repair_bodies = [self.repaired]
        self.reviewed_bodies = []
        self.repair_inputs = []

        def ensure(job, action, prompt, *, fixture_builder):
            self.actions.append(action)
            self.prompts[action] = prompt

            def fixture():
                self.calls[action] += 1
                if action.endswith('_draft'):
                    return {'article_markdown': self.body,
                            'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''}
                if action.endswith('_edit'):
                    from shared.editorial_contracts import edit_base_input
                    base = edit_base_input(wf, job, p0=action.startswith('p0_'))['article_markdown']
                    body = self.edited_body or base
                    changed = body != base
                    return {'edit_status': 'revised' if changed else 'accepted', 'article_markdown': body,
                            'editorial_notes': ['完成合成编辑。'] if changed else [],
                            'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''}
                if action in {'article_finalize', 'article_polish'}:
                    self.reviewed_bodies.append(runner.input_body(wf, job, after_repair=action == 'article_polish'))
                    if not self.review_plan:
                        raise AssertionError('unexpected extra synthetic review')
                    return self.review_plan.pop(0)
                if action == 'article_repair':
                    self.repair_inputs.append(runner.repair_context(wf, job))
                    if not self.repair_bodies:
                        raise AssertionError('unexpected extra synthetic repair')
                    return {'article_markdown': self.repair_bodies.pop(0)}
                if action.endswith('_titles'):
                    state = wf.load_state(job)
                    policy = title_strategy.policy(state)
                    grouped = title_strategy.grouped(policy)
                    v4 = policy == title_strategy.DEFAULT
                    return {'candidates': [{'title': f'合成终端的操作安排与业务观察{i:02}', 'angle': '产品介绍',
                                            **({'style': title_strategy.STYLE_SEQUENCE[i]} if grouped else {}),
                                            **({'usage_hint': ['文档标题']} if v4 else {})}
                                           for i in range(title_strategy.expected_count(state))],
                            'canonical_title_id': 'title_03', **({'title_notes': []} if v4 else {})}
                return fixture_builder()

            return actual_ensure(job, action, prompt, fixture_builder=fixture)

        for target, name, value in ((wf, 'ensure_action', ensure),
                                   (model_runtime, 'http_events', AssertionError('offline tests cannot call a provider'))):
            monkey = patch.object(target, name, side_effect=value)
            monkey.start()
            self.addCleanup(monkey.stop)

    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def job(self, pattern='P01', *, contract=prose.CONTRACT):
        job = flow.NaturalEditorFlowTests.job(self)
        state = wf.load_state(job)
        state['selected_pattern_id'] = pattern
        state['metadata']['natural_prose_contract'] = contract
        # Pool/handoff retention is tested separately with explicit inputs.
        state['metadata'].pop('article_pool_policy', None)
        state['metadata'].pop('question_positioning_handoff', None)
        wf.save_state(job, state)
        bp = wf.read_json(job / 'blueprints/article_blueprint.json')
        bp.update(pattern_id=pattern, article_brief='CURRENT_SCOPE 合成终端产品介绍。',
                  writing_material_markdown='SOURCE_ONLY 合成终端按屏幕提示完成操作。',
                  sections=[{'heading': 'BLUEPRINT_ONLY', 'task': '介绍操作过程。'}],
                  estimated_length='LENGTH_ONCE 约3000字')
        wf.atomic_json(job / 'blueprints/article_blueprint.json', bp)
        return job

    def seed_candidates(self, job):
        wf.atomic_json(job / 'production/article_draft.json', {
            'article_markdown': self.body, 'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''})
        wf.atomic_json(job / 'production/article_edited.json', {
            'edit_status': 'accepted', 'article_markdown': self.body, 'editorial_notes': [],
            'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''})
        wf.atomic_json(job / 'production/article_repaired.json', {'article_markdown': self.repaired})
        wf.atomic_json(job / 'production/article_revision_input.json', {
            'contract': prose.CONTRACT, 'article_markdown': self.body,
            'base_sha256': runner.digest(self.body), 'comments': ['合成导语需要重新组织。'],
            'review_action': 'article_finalize'})

    def test_all_six_patterns_route_actual_system_and_review_schema(self):
        job = self.job()
        self.seed_candidates(job)
        prep.freeze(wf, job, prep.fixture())
        builders = (
            ('article_editorial_preparation', lambda: prose.prompt_preparation(wf, job)),
            ('article_blueprint', lambda: writing_context.prompt_blueprint(wf, job, p0=False)),
            ('article_draft', lambda: writing_context.prompt_article(wf, job, p0=False)),
            ('article_edit', lambda: writing_context.prompt_edit(wf, job, p0=False)),
            ('article_finalize', lambda: writing_context.prompt_finalize(wf, job, p0=False)),
            ('article_repair', lambda: writing_context.prompt_repair(wf, job, p0=False)),
            ('article_polish', lambda: prose.prompt_finish(wf, job, after_repair=True)),
        )
        for pattern in sorted(prose.PATTERNS):
            state = wf.load_state(job)
            state['selected_pattern_id'] = pattern
            wf.save_state(job, state)
            with self.subTest(pattern=pattern), patch('shared.writing_context_v14.examples', return_value='FULL_STYLE_EXAMPLE'):
                for action, builder in builders:
                    prompt = builder()
                    self.assertTrue(prose.matches(prompt), action)
                    self.assertEqual(model_runtime._initial_messages(action, prompt)[0]['content'],
                                     prose.system(action, prompt))
                    if action in {'article_finalize', 'article_polish'}:
                        schema = model_runtime.submit_tool_for(action, prompt=prompt)['function']['parameters']['properties']['result']
                        self.assertEqual(set(schema['properties']), {'needs_revision', 'comments'})
                        self.assertFalse(schema['additionalProperties'])
                    if action == 'article_blueprint':
                        schema = model_runtime.submit_tool_for(action, prompt=prompt)['function']['parameters']['properties']['result']
                        self.assertEqual(schema['properties']['sections']['items']['properties']['task']['description'], prose.SECTION_TASK)
                        for field in prep.FIELDS:
                            self.assertNotIn(field, schema['properties'])

    def test_controller_preparation_and_blueprint_dispatch_for_six_patterns(self):
        job = self.job()
        captures = []

        def ensure(job_root, action, prompt, *, fixture_builder):
            captures.append((action, prompt))
            raw = prep.fixture() if action == prep.ACTION else wf.read_json(job / 'blueprints/article_blueprint.json')
            return wf.validate_action_result(job_root, action, raw)

        for pattern in sorted(prose.PATTERNS):
            state = wf.load_state(job)
            state['selected_pattern_id'] = pattern
            wf.save_state(job, state)
            captures.clear()
            with self.subTest(pattern=pattern), patch.object(wf, 'ensure_action', side_effect=ensure), \
                 patch.object(wf, 'prepare_own_brand_context', return_value=job / 'inputs/own_brand_context.md'), \
                 patch.object(wf, 'render_blueprint_confirmation', return_value=0), \
                 patch('shared.writing_context_v14.examples', return_value='FULL_STYLE_EXAMPLE'):
                wf.run_article_blueprint(job)
            self.assertEqual([action for action, _ in captures], [prep.ACTION, 'article_blueprint'])
            self.assertTrue(all(prose.matches(prompt) for _, prompt in captures))
            self.assertEqual(prep.load(job), prep.fixture())
            self.assertEqual(wf.read_json(job / prep.SOURCE_PATH)['contract'], prose.CONTRACT)

    def test_preparation_freeze_binds_materials_for_new_and_historical_contracts(self):
        job = self.job()
        for contract in (prose.CONTRACT, old_prose.CONTRACT):
            state = wf.load_state(job)
            state['metadata']['natural_prose_contract'] = contract
            wf.save_state(job, state)
            original = prep.fixture()
            prep.freeze(wf, job, original)
            forged = {**wf.read_json(job / 'blueprints/article_blueprint.json'),
                      'writing_material_markdown': 'unfrozen second selection', 'material_adjustments': ['replacement']}
            bound = wf.validate_action_result(job, 'article_blueprint', forged)
            for field in prep.FIELDS:
                self.assertEqual(bound[field], original[field])
            self.assertEqual(wf.read_json(job / prep.SOURCE_PATH)['contract'], contract)
        path = job / prep.PATH
        path.write_text(path.read_text() + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '冻结来源'):
            prep.load(job)

    def test_actual_preparation_submit_schema_routes_new_descriptions_and_preserves_v16(self):
        job = self.job()
        original = prep.schema()
        prompt = prose.prompt_preparation(wf, job)
        schema = model_runtime.submit_tool_for(prep.ACTION, prompt=prompt)['function']['parameters']['properties']['result']
        fields = schema['properties']
        self.assertEqual(fields['writing_material_markdown']['description'], prose.MATERIAL_FIELD_DESCRIPTION)
        self.assertIn('只讲产品、业务或事件的正向内容组织', fields['blueprint_suggestions']['description'])
        self.assertIn('不进入作者素材、构思建议、章节任务或正文', fields['material_adjustments']['description'])
        self.assertEqual(schema['required'], original['required'])
        self.assertEqual(set(fields), set(original['properties']))
        payload = model_runtime._payload_with_profile(
            prep.ACTION, {'model': 'synthetic-host', 'wire_api': 'chat_completions'},
            model_runtime._initial_messages(prep.ACTION, prompt))
        outgoing = next(item for item in payload['tools'] if item['function']['name'] == 'submit_result')
        self.assertEqual(outgoing['function']['parameters']['properties']['result'], schema)
        state = wf.load_state(job)
        state['metadata']['natural_prose_contract'] = old_prose.CONTRACT
        wf.save_state(job, state)
        legacy_prompt = old_prose.prompt_preparation(wf, job)
        historical = model_runtime.submit_tool_for(prep.ACTION, prompt=legacy_prompt)['function']['parameters']['properties']['result']
        self.assertEqual(historical, original)
        self.assertEqual(prep.schema(), original)

    def test_full_edit_retains_examples_and_omits_blueprint_script(self):
        job = self.job()
        self.seed_candidates(job)
        with patch('shared.writing_context_v14.examples', return_value='FULL_STYLE_EXAMPLE'):
            draft = writing_context.prompt_article(wf, job, p0=False)
            edit = writing_context.prompt_edit(wf, job, p0=False)
            repair = writing_context.prompt_repair(wf, job, p0=False)
            finish = writing_context.prompt_finalize(wf, job, p0=False)
        self.assertIn('BLUEPRINT_ONLY', draft)
        self.assertIn('可调整的内容构思', draft)
        for prompt in (edit, repair):
            self.assertIn('FULL_STYLE_EXAMPLE', prompt)
            self.assertIn('SOURCE_ONLY', prompt)
            self.assertNotIn('BLUEPRINT_ONLY', prompt)
        for excluded in ('FULL_STYLE_EXAMPLE', 'SOURCE_ONLY', 'BLUEPRINT_ONLY'):
            self.assertNotIn(excluded, finish)
        self.assertIn(self.body, finish)

    def test_pool_stays_in_planning_and_positioning_moves_through_preparation(self):
        job = self.job()
        self.seed_candidates(job)
        prepared = {**prep.fixture(), 'writing_material_markdown': 'PREPARED_POSITIONING_SOURCE 合成终端提供屏幕操作与记录查看。'}
        prep.freeze(wf, job, prepared)
        wf.atomic_json(job / 'blueprints/article_blueprint.json',
                       prep.bind_blueprint(job, wf.read_json(job / 'blueprints/article_blueprint.json')))
        with patch.object(article_pool, 'prompt_references', return_value='POOL_SELECTED_1_5'), \
             patch.object(question_positioning_handoff, 'context', return_value='CONFIRMED_POSITIONING RAW_POSITIONING_REVIEW'), \
             patch('shared.writing_context_v14.examples', return_value='FULL_STYLE_EXAMPLE'):
            preparation = prose.prompt_preparation(wf, job)
            blueprint = prose.prompt_blueprint(wf, job)
            downstream = [prose.prompt_article(wf, job), prose.prompt_edit(wf, job), prose.prompt_finalize(wf, job)]
        self.assertIn('CONFIRMED_POSITIONING', preparation)
        self.assertIn('RAW_POSITIONING_REVIEW', preparation)
        self.assertIn('PREPARED_POSITIONING_SOURCE', blueprint)
        self.assertNotIn('RAW_POSITIONING_REVIEW', blueprint)
        for prompt in (preparation, blueprint):
            self.assertIn('POOL_SELECTED_1_5', prompt)
        for prompt in downstream:
            self.assertNotIn('POOL_SELECTED_1_5', prompt)
            self.assertNotIn('CONFIRMED_POSITIONING', prompt)
            self.assertNotIn('RAW_POSITIONING_REVIEW', prompt)
        for prompt in downstream[:2]:
            self.assertIn('PREPARED_POSITIONING_SOURCE', prompt)
        self.assertNotIn('PREPARED_POSITIONING_SOURCE', downstream[2])

    def test_preparation_tools_expose_original_files_without_p0_or_strategy_notes(self):
        job = self.job()
        state = wf.load_state(job)
        pack = (job / '00_input/synthetic_pack').resolve()
        for relative, body in (('materials/original.md', 'ORIGINAL_ENTERPRISE_CONTENT'),
                               ('p0/article.md', 'OLD_P0_MANUSCRIPT'),
                               ('strategy/internal_notes.md', 'OLD_AUDIT_NOTES')):
            path = pack / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding='utf-8')
        state['reference_pack']['path'] = str(pack)
        wf.save_state(job, state)
        host = HostTools(wf.ROOT, job, prep.ACTION)
        host.configure_for_prompt(prose.prompt_preparation(wf, job))
        paths = [value['path'] for value in host.artifacts.values()]
        self.assertTrue(any(path.endswith('materials/original.md') for path in paths))
        self.assertFalse(any('/p0/' in path or '/strategy/' in path for path in paths))
        self.assertFalse(any(value.get('category') == 'brand_background' for value in host.artifacts.values()))
        names = [item['function']['name'] for item in host.definitions]
        self.assertIn('web_search', names)
        self.assertIn('web_read', names)
        self.assertIn('read_material', names)

    def test_finalize_and_polish_expose_only_submit_with_no_lookup_tools(self):
        job = self.job()
        self.seed_candidates(job)
        state = wf.load_state(job)
        pack = (job / '00_input/synthetic_pack').resolve()
        pack.mkdir()
        (pack / 'facts.md').write_text('Explicit synthetic pack content.', encoding='utf-8')
        state['reference_pack']['path'] = str(pack)
        wf.save_state(job, state)
        for action, after in (('article_finalize', False), ('article_polish', True)):
            prompt = prose.prompt_finish(wf, job, after_repair=after)
            host = HostTools(wf.ROOT, job, action)
            host.configure_for_prompt(prompt)
            self.assertEqual(list(host.definitions), [])
            payload = model_runtime._payload_with_profile(action, {'model': 'synthetic', 'wire_api': 'chat_completions'},
                                                         model_runtime._initial_messages(action, prompt),
                                                         [{'type': 'function', 'function': {'name': 'web_search'}}])
            self.assertEqual([item['function']['name'] for item in payload['tools']], ['submit_result'])

    def test_two_repair_polish_cycles_preserve_each_current_candidate_and_comments(self):
        job = self.job()
        prep.freeze(wf, job, prep.fixture())
        wf.atomic_json(job / 'blueprints/article_blueprint.json',
                       prep.bind_blueprint(job, wf.read_json(job / 'blueprints/article_blueprint.json')))
        first = self.body.replace('看得见的操作', '顺着提示操作')
        second = first.replace('初次使用的人也能顺着完成。', '初次使用时，照着屏幕往下操作就行。')
        comments = [['合成标题与段落重复，需要重新组织。'], ['合成末段仍有过于整齐的句式。']]
        self.review_plan = [{'needs_revision': True, 'comments': comments[0]},
                            {'needs_revision': True, 'comments': comments[1]},
                            {'needs_revision': False, 'comments': []}]
        self.repair_bodies = [first, second]
        self.until(job, 'repair')
        first_epochs = dict(wf.load_state(job)['flags']['model_action_epochs'])
        self.step(job)
        self.step(job)
        self.assertEqual(wf.load_state(job)['flags']['article_production_step'], 'repair')
        second_epochs = wf.load_state(job)['flags']['model_action_epochs']
        for action in ('article_repair', 'article_polish'):
            self.assertNotEqual(first_epochs[action], second_epochs[action])
        self.finish(job)
        self.assertEqual(self.reviewed_bodies, [self.body, first, second])
        self.assertEqual([value['article_markdown'] for value in self.repair_inputs], [self.body, first])
        self.assertEqual([value['comments'] for value in self.repair_inputs], comments)
        self.assertEqual(self.calls['article_finalize'], 1)
        self.assertEqual(self.calls['article_repair'], 2)
        self.assertEqual(self.calls['article_polish'], 2)
        final = runner.validate_selected(wf, job)
        self.assertEqual(final['article_markdown'], second)
        rounds = sorted((job / 'production/editorial_rounds').glob('*/*/review.json'))
        self.assertEqual(len(rounds), 3)
        self.assertEqual([wf.read_json(path.parent / 'candidate.json')['article_markdown'] for path in rounds],
                         [self.body, first, second])
        self.assertEqual([wf.read_json(path)['comments'] for path in rounds], comments + [[]])
        self.assertTrue((job / 'reviews/article_process.html').is_file())
        self.assertEqual(manuscript_revision.validate_completed_manuscript(wf, job, p0=False)['base_markdown'], second)

    def test_direct_acceptance_is_exact_writer_body_and_can_continue_from_completion(self):
        job = self.job()
        prep.freeze(wf, job, prep.fixture())
        wf.atomic_json(job / 'blueprints/article_blueprint.json',
                       prep.bind_blueprint(job, wf.read_json(job / 'blueprints/article_blueprint.json')))
        self.finish(job)
        self.assertEqual(runner.validate_selected(wf, job)['article_markdown'], self.body)
        self.assertEqual(self.calls['article_repair'], 0)
        self.assertEqual(self.calls['article_polish'], 0)
        inherited = manuscript_revision.validate_completed_manuscript(wf, job, p0=False)
        self.assertEqual(inherited['base_markdown'], self.body)

    def test_six_genre_commissions_complete_revision_titles_and_real_exports_offline(self):
        from pathlib import Path
        import zipfile
        from shared import title_publication
        genres = {
            'P01': ('合成终端推荐', ['合成甲'], '合成甲把操作提示和记录查看放在一台设备里，社区工作人员可以顺着屏幕完成服务。'),
            'P02': ('合成终端有哪些推荐', ['合成甲', '合成乙', '合成丙'], '合成甲侧重社区操作，合成乙侧重门店预约，合成丙侧重活动登记，三家各有展开内容。'),
            'P03': ('社区活动怎样安排终端登记', ['合成甲'], '社区活动先完成预约，再在现场登记，工作人员把本次记录保存到活动档案。'),
            'P04': ('合成甲社区服务活动有什么进展', ['合成甲'], '2026年10月10日，合成甲在测试社区举行虚构服务活动，工作人员完成了登记和操作讲解。'),
            'P05': ('合成甲与合成乙有什么区别', ['合成甲', '合成乙'], '合成甲的界面围绕现场操作，合成乙围绕提前预约，两种安排适合不同的服务流程。'),
            'P06': ('合成甲的服务口碑如何', ['合成甲'], '虚构用户在合成甲完成预约和现场操作，相关体验围绕提示、接待和记录查看展开。'),
        }
        original_root, original_body = self.root, self.body
        for pattern, (question, names, content) in genres.items():
            with self.subTest(pattern=pattern):
                self.root = original_root / pattern
                self.root.mkdir()
                self.body = original_body.replace('合成终端的日常使用', question).replace(
                    '合成品牌把测量和结果查看安排在同一台终端里。', content)
                self.repair_bodies = [self.body.replace('看得见的操作', '顺着提示操作')]
                self.review_plan = [{'needs_revision': True, 'comments': ['合成小标题与操作内容需要顺接。']},
                                    {'needs_revision': False, 'comments': []}]
                job = self.job(pattern)
                state = wf.load_state(job)
                state['question']['question_text'] = question
                state['metadata']['title_strategy'] = dict(title_strategy.DEFAULT)
                state['metadata']['effective_writing_requirements'] = {
                    'article_brief': pattern + ' 对应体裁的显式合成委托。', 'candidate_order': names}
                wf.save_state(job, state)
                prepared = {**prep.fixture(), 'writing_material_markdown': content}
                prep.freeze(wf, job, prepared)
                bp = wf.read_json(job / 'blueprints/article_blueprint.json')
                bp.update(question=question, candidate_order=names)
                wf.atomic_json(job / 'blueprints/article_blueprint.json', prep.bind_blueprint(job, bp))
                start = len(self.actions)
                with patch.object(wf, 'write_docx', wraps=REAL_WRITE_DOCX):
                    self.finish(job)
                self.assertEqual(self.actions[start:], ['article_draft', 'article_edit', 'article_finalize',
                    'article_repair', 'article_polish', 'article_titles', 'article_title_review'])
                completed = wf.load_state(job)
                self.assertEqual(completed['status'], 'completed')
                body = runner.validate_selected(wf, job)['article_markdown']
                delivery = completed['metadata']['delivery']
                self.assertEqual(Path(delivery['markdown']).read_text(), title_publication.body_only(body))
                self.assertIn('顺着提示操作', Path(delivery['html']).read_text())
                with zipfile.ZipFile(delivery['docx']) as archive:
                    self.assertIn('word/document.xml', archive.namelist())
                self.assertEqual(wf.read_json(Path(delivery['title_map']))['total_count'],
                                 10)
                self.assertIn(prose.PATTERN_GUIDANCE[pattern], self.prompts['article_draft'])
                for name in names:
                    self.assertIn(name, self.prompts['article_edit'])
        self.root, self.body = original_root, original_body

    def test_actual_continue_handles_title_only_then_full_manuscript_revision(self):
        job = self.job()
        prep.freeze(wf, job, prep.fixture())
        wf.atomic_json(job / 'blueprints/article_blueprint.json',
                       prep.bind_blueprint(job, wf.read_json(job / 'blueprints/article_blueprint.json')))
        self.finish(job)
        original_final = (job / 'production/article_finalized.json').read_bytes()
        request = self.root / 'manual_request.md'
        request.write_text('本轮只调整标题角度。', encoding='utf-8')

        def continue_with(flag):
            args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision',
                                          str(wf.load_state(job)['revision']), flag, str(request)])
            with contextlib.redirect_stdout(io.StringIO()):
                wf.continue_workflow(args)

        continue_with('--title-edits')
        self.assertEqual(wf.load_state(job)['status'], 'completed')
        self.assertEqual((job / 'production/article_finalized.json').read_bytes(), original_final)
        self.assertEqual(self.calls['article_draft'], 1)
        self.assertEqual(self.calls['article_edit'], 1)
        self.assertEqual(self.calls['article_finalize'], 1)
        request.write_text('重写开头，保留操作过程。', encoding='utf-8')
        self.edited_body = self.body.replace('合成品牌把测量和结果查看安排在同一台终端里。', '先完成操作，再看看结果，合成终端把这两件事放在一起。')
        repaired = self.edited_body.replace('看得见的操作', '跟着提示往下操作')
        self.review_plan = [{'needs_revision': True, 'comments': ['合成小标题需要与新导语顺接。']},
                            {'needs_revision': False, 'comments': []}]
        self.repair_bodies = [repaired]
        continue_with('--manuscript-edits')
        self.assertEqual(wf.load_state(job)['status'], 'completed')
        self.assertEqual(runner.validate_selected(wf, job)['article_markdown'], repaired)
        self.assertEqual(self.calls['article_draft'], 1)
        self.assertEqual(self.calls['article_edit'], 2)
        self.assertEqual(self.calls['article_repair'], 1)
        frozen = manuscript_revision.current_revision(wf, job, p0=False)
        self.assertEqual(frozen['base_markdown'], self.body)
        self.assertEqual(manuscript_revision.validate_completed_manuscript(wf, job, p0=False)['base_markdown'], repaired)

    def test_drive_batch_limit_preserves_running_and_actual_continue_resumes(self):
        job = self.job()
        prep.freeze(wf, job, prep.fixture())
        wf.atomic_json(job / 'blueprints/article_blueprint.json',
                       prep.bind_blueprint(job, wf.read_json(job / 'blueprints/article_blueprint.json')))
        self.review_plan = [{'needs_revision': True, 'comments': [f'合成第{i}轮需要重新组织末段。']}
                            for i in range(26)] + [{'needs_revision': False, 'comments': []}]
        self.repair_bodies = [self.body + f'\n\n合成完整修订稿第{i}轮。' for i in range(26)]
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            wf.drive(job)
        pending = json.loads(capture.getvalue())
        self.assertTrue(pending['continuation_required'])
        self.assertEqual(wf.load_state(job)['status'], 'running_article_production')
        self.assertFalse((job / 'production/article_finalized.json').exists())
        self.assertEqual(self.calls['article_titles'], 0)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job)])
        with contextlib.redirect_stdout(io.StringIO()):
            wf.continue_workflow(args)
        self.assertEqual(wf.load_state(job)['status'], 'completed')
        self.assertEqual(self.calls['article_repair'], 26)
        self.assertEqual(self.calls['article_polish'], 26)
        self.assertEqual(runner.validate_selected(wf, job)['article_markdown'], self.body + '\n\n合成完整修订稿第25轮。')

    def test_actual_saved_legacy_writer_efforts_restore_without_recalling_transport(self):
        from shared.writing_context_v15 import MARKER as OLD_MARKER
        from scripts.tests_v411.test_model_runtime import stream
        package = self.root / 'synthetic_runtime_package'
        (package / 'config').mkdir(parents=True)
        (package / 'config/deepseek.json').write_text('{"api_key":"offline-synthetic-credential"}', encoding='utf-8')
        default = {**model_runtime.profile_for('article_draft'), 'reasoning_effort': 'high'}
        for version, marker in (('v15', OLD_MARKER), ('v16', old_prose.MARKER), ('v165', prose.MARKER)):
            for effort in ('high', 'max'):
                with self.subTest(version=version, effort=effort):
                    job = self.root / ('saved_writer_' + version + '_' + effort)
                    job.mkdir()
                    prompt = marker + '\n合成冻结作者请求，完整JSON结果。'
                    calls = []

                    def transport(profile, key, payload):
                        calls.append(profile['reasoning_effort'])
                        return stream(content='{"ok":true}')

                    with patch.object(model_runtime, 'profile_for', return_value={**default, 'reasoning_effort': effort}):
                        self.assertEqual(model_runtime.run_action(package, job, 'article_draft', prompt, lambda value: value,
                                                                 transport=transport, offline=True), {'ok': True})
                    with patch.object(model_runtime, 'profile_for', return_value=default):
                        self.assertEqual(model_runtime.run_action(package, job, 'article_draft', prompt, lambda value: value,
                                                                 transport=AssertionError('saved complete result cannot call transport'),
                                                                 offline=True), {'ok': True})
                        self.assertEqual(model_runtime.action_record(job, 'article_draft')['requested_configuration']['reasoning_effort'], effort)
                        self.assertEqual(model_runtime.profile_for_request('article_draft', prompt)['reasoning_effort'], 'high')
                    self.assertEqual(calls, [effort])
        for change in ('different_prompt', 'different_configuration', 'missing_saved_prompt'):
            with self.subTest(nonmatching=change):
                job = self.root / ('nonmatching_writer_' + change)
                job.mkdir()
                prompt = prose.wrap('合成已保存的作者请求')
                with patch.object(model_runtime, 'profile_for', return_value={**default, 'reasoning_effort': 'max'}):
                    model_runtime.run_action(package, job, 'article_draft', prompt, lambda value: value,
                                             transport=lambda *_: stream(content='{"ok":true}'), offline=True)
                first = model_runtime.action_record(job, 'article_draft')
                current = dict(default)
                if change == 'different_prompt':
                    prompt += '\n本轮新的写作委托。'
                elif change == 'different_configuration':
                    current['max_tokens'] = default['max_tokens'] + 1
                else:
                    (job / 'provider/article_draft/runtime/attempts' / first['attempt_id'] / 'prompt.md').unlink()
                fresh_calls = []

                def fresh_transport(profile, key, payload):
                    fresh_calls.append(profile['reasoning_effort'])
                    return stream(content='{"ok":true}')

                with patch.object(model_runtime, 'profile_for', return_value=current):
                    model_runtime.run_action(package, job, 'article_draft', prompt, lambda value: value,
                                             transport=fresh_transport, offline=True)
                latest = model_runtime.action_record(job, 'article_draft')
                self.assertEqual(fresh_calls, ['high'])
                self.assertNotEqual(latest['attempt_id'], first['attempt_id'])
                self.assertEqual(latest['requested_configuration']['reasoning_effort'], 'high')
        fresh = self.root / 'fresh_v165_writer'
        fresh.mkdir()
        with patch.object(model_runtime, 'profile_for', return_value=default):
            model_runtime.run_action(package, fresh, 'article_draft', prose.wrap('新的合成作者请求'), lambda value: value,
                                     transport=lambda *_: stream(content='{"ok":true}'), offline=True)
        self.assertEqual(model_runtime.action_record(fresh, 'article_draft')['requested_configuration']['reasoning_effort'], 'high')

    def test_review_binding_rejects_stale_candidate_and_extra_fields(self):
        job = self.job()
        self.seed_candidates(job)
        wf.atomic_json(job / 'production/article_review_input.json', {
            'contract': prose.CONTRACT, 'action': 'article_finalize', 'base_sha256': 'stale-candidate'})
        with self.assertRaisesRegex(ValueError, '验读输入已改变'):
            runner.validate_action(wf, job, 'article_finalize', {'needs_revision': False, 'comments': []})
        with self.assertRaises(ValueError):
            runner.validate_review({'needs_revision': False, 'comments': [], 'local_edits': []})
        bad = wf.read_json(job / 'production/article_revision_input.json')
        bad['article_markdown'] += '\nChanged after review.'
        wf.atomic_json(job / 'production/article_revision_input.json', bad)
        with self.assertRaisesRegex(ValueError, '失败候选'):
            runner.repair_context(wf, job)

    def test_estimated_length_is_advisory_only_explicit_range_counts(self):
        job = self.job()
        self.seed_candidates(job)
        draft = prose.prompt_article(wf, job)
        self.assertIn('LENGTH_ONCE 约3000字', draft)
        self.assertNotIn(writer_measure.MARKER, draft)
        self.assertNotIn('count_article', prose.system('article_draft', draft))
        binding = {'contract': prose.CONTRACT, 'action': 'article_finalize', 'base_sha256': runner.digest(self.body)}
        wf.atomic_json(job / 'production/article_review_input.json', binding)
        accepted = {'needs_revision': False, 'comments': []}
        self.assertEqual(runner.validate_action(wf, job, 'article_finalize', accepted), accepted)
        state = wf.load_state(job)
        state['metadata']['effective_writing_requirements'] = {'body_character_range': {'minimum': 3000, 'maximum': 3600}}
        wf.save_state(job, state)
        for builder, action in ((prose.prompt_article, 'article_draft'), (prose.prompt_edit, 'article_edit'),
                                (prose.prompt_repair, 'article_repair')):
            prompt = builder(wf, job)
            self.assertIn(writer_measure.MARKER, prompt)
            self.assertIn('count_article', prose.system(action, prompt))
        with self.assertRaisesRegex(ValueError, '明确指定的硬性篇幅'):
            runner.validate_action(wf, job, 'article_finalize', accepted)
        state = wf.load_state(job)
        count = wf.natural_editor.character_count(self.body)
        state['metadata']['effective_writing_requirements']['body_character_range'] = {'minimum': count, 'maximum': count}
        wf.save_state(job, state)
        self.assertEqual(runner.validate_action(wf, job, 'article_finalize', accepted), accepted)

    def test_historical_contract_and_p0_remain_outside_v165(self):
        job = self.job(contract=old_prose.CONTRACT)
        self.seed_candidates(job)
        prep.freeze(wf, job, prep.fixture())
        prompt = writing_context.prompt_article(wf, job, p0=False)
        self.assertTrue(old_prose.matches(prompt))
        self.assertFalse(prose.matches(prompt))
        self.assertEqual(model_runtime._initial_messages('article_draft', prompt)[0]['content'], old_prose.system('article_draft', prompt))
        review = old_prose.prompt_finalize(wf, job)
        schema = model_runtime.submit_tool_for('article_finalize', prompt=review)['function']['parameters']['properties']['result']
        self.assertIn('local_edits', schema['properties'])
        p0_job = flow.NaturalEditorFlowTests.job(self, 'p0')
        state = wf.load_state(p0_job)
        self.assertFalse(runner.enabled(state))
        self.assertFalse(prose.enabled(state, p0=True))
        self.assertFalse(prep.enabled(state, p0=True))
        self.assertNotIn(prose.MARKER, writing_context.prompt_article(wf, p0_job, p0=True))


if __name__ == '__main__':
    unittest.main()
