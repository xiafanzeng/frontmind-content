"""Offline integration checks; these fixtures do not establish prose quality."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from shared import editorial_preparation as prep, model_runtime as rt, writing_context, writing_context_v15, writing_context_v16
from shared import language_editor_v15 as editor
from shared.host_tools import HostTools, ToolError


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name) / 'job'; self.job.mkdir()
        self.package = Path(self.temp.name) / 'package'; self.package.mkdir()
        (self.job / 'inputs').mkdir()
        (self.job / 'inputs/facts.md').write_text('企业提供业务甲，使用技术乙，面向需求丙。')
        state = wf.make_state('editorial-v16', 'article')
        state.update(selected_pattern_id='P01', selected_example_route='default', question={'question_text': '业务介绍'})
        state['metadata']['blueprint_material_roots'] = ['inputs']
        state['reference_pack'] = {'brand': '合成企业'}
        wf.atomic_json(self.job / 'job_state.json', state)

    def tools(self):
        tools = HostTools(self.package, self.job, prep.ACTION)
        tools.configure_for_prompt(prep.MARKER + '\n准备材料')
        return tools

    def result(self, tools, *, read=True, search=True):
        if search:
            with patch.object(tools, '_api', return_value={'search_result': [{'title': '同类案例', 'link': 'https://example.com/1'}]}):
                tools.execute('web_search', {'query': '同类企业介绍案例'})
        cases = []
        for n in (1, 2):
            # Mock only network acquisition; production acquisition remains untouched.
            record = tools.store.import_user_text(('完整案例正文甲乙丙。' * 3000) + f'尾部{n}', f'案例{n}', f'https://example.com/{n}')
            with patch.object(tools.store, 'acquire_http', return_value=record):
                tools.execute('web_read', {'url': f'https://example.com/{n}'})
            if read:
                offset = 0
                while True:
                    page = tools.execute('read_material', {'artifact_id': record['artifact_id'], 'offset': offset, 'limit': 24000})
                    if page['next_offset'] is None: break
                    offset = page['next_offset']
            cases.append({'source_ref': record['artifact_id'], 'title': f'案例{n}', 'url': f'https://example.com/{n}', 'insight': '以具体业务切入，再展开独立特点。'})
        tools.execute('read_material', {'artifact_id': 'inputs/facts.md'})
        return {'writing_material_markdown': '企业提供业务甲，使用技术乙。', 'blueprint_suggestions': '以业务甲切入，展开技术乙的相关特点。',
                'writing_material_sources': [{'source_ref': 'inputs/facts.md', 'use': '企业业务和技术'}], 'reference_cases': cases, 'material_adjustments': []}

    def test_two_searched_fully_read_cases_and_checkpoint_restore(self):
        tools = self.tools(); value = self.result(tools)
        self.assertTrue(tools.validate_result_sources(value))
        saved = tools.export_state()
        restored = self.tools(); restored.restore_state(saved)
        self.assertTrue(restored.validate_result_sources(value))
        self.assertEqual(restored.editorial_searches, tools.editorial_searches)

    def test_search_snippets_or_unread_pages_are_not_complete_cases(self):
        tools = self.tools(); value = self.result(tools, read=False)
        with self.assertRaisesRegex(ToolError, 'to the end'): tools.validate_result_sources(value)
        tools2 = self.tools(); value2 = self.result(tools2, search=False)
        with self.assertRaisesRegex(ToolError, 'web_search'): tools2.validate_result_sources(value2)

    def test_reference_case_cannot_become_enterprise_fact_source(self):
        tools = self.tools(); value = self.result(tools)
        value['writing_material_sources'] = [{'source_ref': value['reference_cases'][0]['source_ref'], 'use': '错误移植案例业务'}]
        with self.assertRaisesRegex(ToolError, 'enterprise fact'): tools.validate_result_sources(value)

    def test_wrong_url_and_duplicate_article_rejected(self):
        tools = self.tools(); value = self.result(tools)
        value['reference_cases'][0]['url'] = 'https://example.com/wrong'
        with self.assertRaisesRegex(ToolError, 'URL'): tools.validate_result_sources(value)
        value['reference_cases'][1] = value['reference_cases'][0]
        with self.assertRaisesRegex(ValueError, '不同'): prep.validate(value)

    def test_blueprint_inherits_clean_material_and_cannot_read_originals(self):
        tools = self.tools(); value = self.result(tools)
        prep.freeze(wf, self.job, value)
        blueprint = {'kind': 'article', 'article_brief': '介绍业务', 'example_use': '借鉴具体切入方式', 'opening': '介绍业务', 'sections': [{'heading': '业务', 'task': '说明特点'}], 'ending': '自然结束', 'writing_material_markdown': '被排除的旧服务段落', 'writing_material_sources': ['bad']}
        isolated = HostTools(self.package, self.job, 'article_blueprint')
        isolated.configure_for_prompt(prep.MARKER + '\n' + value['writing_material_markdown'])
        self.assertEqual(list(isolated.definitions), [])
        self.assertEqual({r['path'] for r in isolated.artifacts.values()}, {prep.PATH})
        with self.assertRaises(ToolError): isolated.execute('read_material', {'artifact_id': 'inputs/facts.md'})
        with self.assertRaises(ToolError): isolated.register_file(self.job / 'inputs/facts.md', 'material')
        bound = rt._checked(lambda raw: prep.bind_blueprint(self.job, raw), blueprint, isolated)
        self.assertEqual(bound['writing_material_markdown'], value['writing_material_markdown'])
        self.assertEqual(bound['writing_material_sources'], value['writing_material_sources'])
        restored = HostTools(self.package, self.job, 'article_blueprint'); restored.configure_for_prompt(prep.MARKER + '\n蓝图')
        restored.restore_state(isolated.export_state())
        self.assertTrue(restored.validate_result_sources(bound))
        before = rt.context_fingerprint(self.job, 'article_blueprint', isolated)
        (self.job / 'inputs/facts.md').write_text('未选择的新原始文本')
        self.assertEqual(before, rt.context_fingerprint(self.job, 'article_blueprint', isolated))

    def test_frozen_artifact_tampering_is_detected(self):
        prep.freeze(wf, self.job, prep.fixture())
        path = self.job / prep.PATH
        value = json.loads(path.read_text()); value['writing_material_markdown'] = '另一个文本'; wf.atomic_json(path, value)
        with self.assertRaisesRegex(ValueError, '冻结来源'): prep.load(self.job)

    def test_preparation_and_blueprint_schemas_keep_responsibilities_separate(self):
        prompt = prep.MARKER + '\n'
        properties = lambda action: rt.submit_tool_for(action, prompt=prompt)['function']['parameters']['properties']['result']
        research = properties(prep.ACTION); blueprint = properties('article_blueprint')
        self.assertEqual(research['properties']['reference_cases']['minItems'], 2)
        for name in prep.FIELDS: self.assertNotIn(name, blueprint['properties'])
        self.assertNotIn('sections', research['properties'])
        self.assertIn('sections', blueprint['required'])
        for action in ('article_finalize', 'article_polish'):
            self.assertEqual(set(properties(action)['required']), {'needs_revision', 'comments', 'local_edits'})

    def test_new_default_and_legacy_prompt_routes_remain_distinct(self):
        state = wf.load_state(self.job)
        self.assertTrue(writing_context_v16.enabled(state))
        self.assertFalse(writing_context_v15.enabled(state))
        legacy = writing_context_v15.MARKER + '\n旧请求'
        current = prep.MARKER + '\n新请求'
        self.assertEqual(rt._initial_messages('article_draft', legacy)[0]['content'], writing_context_v15.system('article_draft', legacy))
        self.assertEqual(rt._initial_messages('article_draft', current)[0]['content'], writing_context_v16.system('article_draft', current))
        self.assertEqual(rt.profile_for('article_draft')['reasoning_effort'], 'high')
        for pattern in ('P03', 'P04', 'P05', 'P06'):
            state['selected_pattern_id'] = pattern; self.assertFalse(prep.enabled(state)); self.assertFalse(editor.enabled(state))

    def test_frozen_old_writer_effort_preserved_only_for_unchanged_old_prompt(self):
        old_prompt = writing_context_v15.MARKER + '\n旧正文'
        old_profile = rt.profile_for('article_draft'); old_profile['reasoning_effort'] = 'max'
        attempt = self.job / 'provider/article_draft/runtime/attempts/saved'
        attempt.mkdir(parents=True); (attempt / 'prompt.md').write_text(old_prompt)
        record = {'attempt_id': 'saved', 'requested_configuration': old_profile}
        with patch.object(rt, 'action_record', return_value=record), patch.object(rt, '_run_action', side_effect=lambda *a, **k: rt.profile_for_request(a[2], a[3])):
            resumed = rt.run_action(self.package, self.job, 'article_draft', old_prompt, lambda x: x)
            fresh = rt.run_action(self.package, self.job, 'article_draft', prep.MARKER + '\n新正文', lambda x: x)
        self.assertEqual(resumed['reasoning_effort'], 'max'); self.assertEqual(fresh['reasoning_effort'], 'high')
        self.assertEqual(rt.profile_for_request('article_draft', old_prompt)['reasoning_effort'], 'high')

    def test_completed_max_request_replays_without_a_new_model_call_after_default_changes(self):
        from scripts.tests_v411.test_model_runtime import stream
        action = 'article_draft'
        prompt = writing_context_v15.MARKER + '\n冻结的旧正文请求'
        original_profile = rt.profile_for(action)
        maximum = {**original_profile, 'reasoning_effort': 'max'}
        with patch.object(rt, 'profile_for', return_value=maximum):
            first = rt.run_action(self.package, self.job, action, prompt, lambda v: v,
                offline=True, transport=lambda *args: stream(content='{"ok":true}'))
        before = rt.action_record(self.job, action)['attempt_id']
        recovered = rt.run_action(self.package, self.job, action, prompt, lambda v: v,
            offline=True, transport=lambda *args: self.fail('frozen max result must recover without network'))
        self.assertEqual(first, recovered)
        self.assertEqual(rt.action_record(self.job, action)['attempt_id'], before)
        self.assertEqual(rt.action_record(self.job, action)['requested_configuration']['reasoning_effort'], 'max')

    def test_blueprint_runs_preparation_first_and_reuses_frozen_offline_result(self):
        state = wf.load_state(self.job); state['flags']['offline_fixture'] = True; wf.save_state(self.job, state)
        blueprint = {'kind': 'article', 'question': '业务介绍', 'pattern_id': 'P01', 'article_brief': '介绍业务', 'example_use': '借鉴切入', 'opening': '业务', 'sections': [{'heading': '业务', 'task': '说明业务特点'}], 'ending': '结束'}
        actions = []; actual = wf.ensure_action
        def ensure(job, action, prompt, **kwargs):
            actions.append(action)
            if action == 'article_blueprint': kwargs['fixture_builder'] = lambda: blueprint
            return actual(job, action, prompt, **kwargs)
        with patch.object(wf, 'ensure_action', side_effect=ensure), patch.object(wf, 'render_blueprint_confirmation', return_value=0):
            with contextlib.redirect_stdout(io.StringIO()):
                wf.run_article_blueprint(self.job)
                wf.run_article_blueprint(self.job)
        self.assertEqual(actions, [prep.ACTION, 'article_blueprint'] * 2)
        saved = wf.read_json(self.job / 'blueprints/article_blueprint.json')
        self.assertEqual(saved['writing_material_markdown'], prep.load(self.job)['writing_material_markdown'])

    def test_outline_reordering_preserves_preparation_but_raw_changes_do_not(self):
        prep.freeze(wf, self.job, prep.fixture())
        before = rt.context_fingerprint(self.job, prep.ACTION)
        state = wf.load_state(self.job); state['decisions']['blueprint_edits'] = '交换两个章节顺序'; wf.save_state(self.job, state)
        wf.atomic_json(self.job / 'inputs/article_blueprint_edit_outline.json', {'headings': ['旧章节']})
        self.assertEqual(before, rt.context_fingerprint(self.job, prep.ACTION))
        wf.invalidate_action(self.job, 'article_blueprint', preserve_blueprint_edit=True)
        self.assertEqual(prep.load(self.job)['writing_material_markdown'], prep.fixture()['writing_material_markdown'])
        (self.job / 'inputs/facts.md').write_text('新增企业业务事实')
        self.assertNotEqual(before, rt.context_fingerprint(self.job, prep.ACTION))
        wf.invalidate_action(self.job, 'article_blueprint')
        self.assertFalse((self.job / prep.PATH).exists())

    def test_preparation_replays_after_blueprint_creates_own_brand_context(self):
        from scripts.tests_v411.agents_sdk_fake import bundle
        prompt = prep.MARKER + '\n同一份原始材料与编辑准备委托'
        tools = self.tools(); value = self.result(tools)
        sdk, engine = bundle(fault='unread', result=value)
        first = rt.run_action(self.package, self.job, prep.ACTION, prompt, prep.validate,
                              host_tools=tools, transport=sdk, offline=True)
        saved = rt.action_record(self.job, prep.ACTION)
        calls = engine.calls
        original_context = rt.context_fingerprint(self.job, prep.ACTION)
        derived = self.job / 'inputs/own_brand_context.md'
        for content in ('正式蓝图后生成的品牌定位投影', '之后重新生成的品牌定位投影'):
            derived.write_text(content)
            self.assertEqual(original_context, rt.context_fingerprint(self.job, prep.ACTION))
            recovered = rt.run_action(self.package, self.job, prep.ACTION, prompt, prep.validate,
                                      host_tools=self.tools(), transport=sdk, offline=True)
            self.assertEqual(recovered, first)
            self.assertEqual(engine.calls, calls)
            self.assertEqual(rt.action_record(self.job, prep.ACTION)['attempt_id'], saved['attempt_id'])
        # A real source change must still run a new preparation request.
        (self.job / 'inputs/facts.md').write_text('企业新增了业务丁和技术戊。')
        self.assertNotEqual(original_context, rt.context_fingerprint(self.job, prep.ACTION))
        changed_tools = self.tools(); changed_value = self.result(changed_tools)
        changed_sdk, changed_engine = bundle(fault='unread', result=changed_value)
        rt.run_action(self.package, self.job, prep.ACTION, prompt, prep.validate,
                      host_tools=changed_tools, transport=changed_sdk, offline=True)
        self.assertGreater(changed_engine.calls, 0)
        self.assertNotEqual(rt.action_record(self.job, prep.ACTION)['attempt_id'], saved['attempt_id'])

    def test_preparation_cannot_use_downstream_brand_projection_as_a_source(self):
        projection = self.job / 'inputs/own_brand_context.md'
        projection.write_text('下游生成的品牌定位和推荐论证')
        tools = self.tools()
        self.assertNotIn('inputs/own_brand_context.md', {r['path'] for r in tools.artifacts.values()})
        for ref in ('inputs/own_brand_context.md', str(projection), projection.name):
            with self.subTest(ref=ref), self.assertRaises(ToolError):
                tools.execute('read_material', {'artifact_id': ref})
        with self.assertRaises(ToolError): tools.register_file(projection, 'material')
        value = self.result(tools)
        value['writing_material_sources'] = [{'source_ref': 'inputs/own_brand_context.md', 'use': '旧投影'}]
        with self.assertRaises(ToolError): tools.validate_result_sources(value)
        # An older, broader registry cannot sneak the projection into a restored preparation.
        legacy = HostTools(self.package, self.job, 'article_blueprint')
        saved = legacy.export_state(); saved['action'] = prep.ACTION
        with self.assertRaisesRegex(ToolError, 'dependency changed'): tools.restore_state(saved)
        # Only the known controller path is excluded, not an uploaded file sharing its name.
        original = self.job / 'inputs/customer/own_brand_context.md'
        original.parent.mkdir(); original.write_text('客户提供的原始业务介绍')
        before = rt.context_fingerprint(self.job, prep.ACTION)
        readable = self.tools().execute('read_material', {'artifact_id': 'inputs/customer/own_brand_context.md'})
        self.assertEqual(readable['text'], '客户提供的原始业务介绍')
        original.write_text('客户补充的原始业务介绍')
        self.assertNotEqual(before, rt.context_fingerprint(self.job, prep.ACTION))

    def test_direct_material_override_is_rejected_before_manuscript_revision(self):
        args = argparse.Namespace(job_dir=str(self.job), writing_materials='never-read.md', manuscript_edits='edit.md')
        with self.assertRaisesRegex(wf.WorkflowError, '蓝图补料'): wf.continue_workflow(args)


from scripts.tests_v411 import test_language_editor_v15 as legacy_flow


class V16FinalEditingFlowTests(legacy_flow.LanguageEditorFlowTests):
    def job(self, *, legacy=False):
        job = super().job(legacy=legacy)
        if legacy:
            return job
        state = wf.load_state(job)
        state['metadata']['natural_prose_contract'] = prep.CONTRACT
        wf.save_state(job, state)
        blueprint = wf.read_json(job / 'blueprints/article_blueprint.json')
        prepared = prep.fixture()
        prepared.update({key: blueprint[key] for key in ('writing_material_markdown', 'writing_material_sources', 'material_adjustments')})
        prep.freeze(wf, job, prepared)
        wf.atomic_json(job / 'blueprints/article_blueprint.json', prep.bind_blueprint(job, blueprint))
        return job

    def test_final_source_names_v16_and_verifies_preparation(self):
        job = self.job(); self.finish(job)
        self.assertEqual(wf.read_json(job / 'production/article_final_source.json')['contract'], prep.CONTRACT)
        from shared import manuscript_revision
        manuscript_revision.validate_completed_manuscript(wf, job, p0=False)
        (job / prep.PATH).unlink()
        with self.assertRaisesRegex(ValueError, '编辑准备'):
            manuscript_revision.validate_completed_manuscript(wf, job, p0=False)


if __name__ == '__main__': unittest.main()
