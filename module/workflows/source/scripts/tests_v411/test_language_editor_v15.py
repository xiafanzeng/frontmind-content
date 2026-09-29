"""Offline state/provenance tests. Fixtures do not establish prose quality."""
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411.test_article_reader_final8 import fixture_profile
from shared import language_editor_v15 as editor, manuscript_revision, model_runtime, natural_editor, title_strategy


def review(*, structural=False, edits=None):
    return {"needs_revision": structural, "comments": ["重组导语与第一节的重复内容。"] if structural else [],
            "local_edits": [] if structural else (edits or [])}


class LocalEditTests(unittest.TestCase):
    body = '# 内部题目\n\n**某机构**提供预约服务。另有独立接待室，方便沟通。\n\n最后一段内容。'

    def test_exact_edits_are_simultaneous_and_keep_structure(self):
        edits = [{"original": "提供预约服务", "replacement": "可预约面诊"},
                 {"original": "方便沟通", "replacement": "用于面诊沟通"}]
        value = editor.validate_review(review(edits=edits), self.body)
        actual = editor.apply_local_edits(self.body, value['local_edits'])
        self.assertIn('**某机构**可预约面诊。', actual)
        self.assertIn('用于面诊沟通', actual)

    def test_reject_missing_duplicate_overlap_and_structural_edits(self):
        cases = [
            [{"original": "找不到的文字", "replacement": "新文字"}],
            [{"original": "。", "replacement": "！"}],
            [{"original": "提供预约服务", "replacement": "预约服务"}, {"original": "预约服务", "replacement": "门诊服务"}],
            [{"original": "提供预约服务", "replacement": "提供\n\n预约服务"}],
            [{"original": "# 内部题目", "replacement": "# 新标题"}],
            [{"original": "某机构", "replacement": "另一机构"}],
            [{"original": "最后一段内容。", "replacement": ""}],
            [{"original": "提供预约服务", "replacement": "提供预约服务"}],
        ]
        for edits in cases:
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                editor.validate_review(review(edits=edits), self.body)

    def test_review_union_does_not_mix_rework_and_local_edits(self):
        bad = review(structural=True)
        bad['local_edits'] = [{'original': '预约服务', 'replacement': '面诊服务'}]
        with self.assertRaises(ValueError): editor.validate_review(bad, self.body)
        bad = review();bad['comments'] = ['只是换词']
        with self.assertRaises(ValueError): editor.validate_review(bad, self.body)

    def test_frozen_old_review_schema_stays_distinct(self):
        natural_editor.validate_review({'needs_revision': False, 'comments': []})
        with self.assertRaises(ValueError): natural_editor.validate_review(review())
        with self.assertRaises(ValueError): editor.validate_review({'needs_revision': False, 'comments': []})

    def test_even_overlapping_occurrences_are_ambiguous(self):
        with self.assertRaisesRegex(ValueError, '唯一'):
            editor.validate_review(review(edits=[{'original': '哈哈', 'replacement': '呵呵'}]), '# 题目\n\n哈哈哈。')


class RuntimeBindingTests(unittest.TestCase):
    def test_new_final_editor_payload_only_has_submit_and_new_schema(self):
        from shared import writing_context_v15
        prompt = writing_context_v15.MARKER + '\n实际完整稿'
        extra = {'type': 'function', 'function': {'name': 'web_search', 'parameters': {'type': 'object'}}}
        for action in ('article_finalize', 'article_polish'):
            payload = model_runtime._payload_with_profile(action,
                {'provider': 'offline_fixture', 'model': 'offline-host'},
                model_runtime._initial_messages(action, prompt), [extra])
            self.assertEqual([t['function']['name'] for t in payload['tools']], ['submit_result'])
            schema = payload['tools'][0]['function']['parameters']['properties']['result']
            self.assertEqual(set(schema['required']), {'needs_revision', 'comments', 'local_edits'})
            self.assertNotIn('article_markdown', schema['properties'])

    def test_host_reads_only_current_candidate_including_post_repair(self):
        from shared.host_tools import HostTools
        from shared import writing_context_v15
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp);(job/'production').mkdir();(job/'answers').mkdir()
            state = wf.make_state('host-test', 'article');state['selected_pattern_id'] = 'P02'
            wf.atomic_json(job/'job_state.json', state)
            (job/'answers/old.md').write_text('旧答案不应成为终稿编辑的必读资料。')
            bodies = {'edited': '# 标题\n\n实际E8稿。', 'repaired': '# 标题\n\n实际返工稿。'}
            for suffix, body in bodies.items(): wf.atomic_json(job/'production'/f'article_{suffix}.json', {'article_markdown': body})
            for action, suffix in [('article_finalize', 'edited'), ('article_polish', 'repaired')]:
                tools = HostTools(wf.ROOT, job, action)
                prompt = writing_context_v15.MARKER + '\n' + bodies[suffix]
                tools.configure_for_prompt(prompt)
                self.assertEqual(list(tools.definitions), [])
                self.assertEqual([tools.artifacts[i]['path'] for i in tools._required], [f'production/article_{suffix}.json'])
                tools.record_inline_inputs(model_runtime._initial_messages(action, prompt))
                tools.validate_complete_reads()

    def test_only_new_p01_p02_jobs_enable_the_new_contract(self):
        state = wf.make_state('new', 'article')
        for pattern in ('P01', 'P02'):
            state['selected_pattern_id'] = pattern;self.assertTrue(editor.enabled(state))
        state['selected_pattern_id'] = 'P03';self.assertFalse(editor.enabled(state))
        state['selected_pattern_id'] = 'P01';state['metadata'].pop('natural_prose_contract')
        self.assertFalse(editor.enabled(state))


class LanguageEditorFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.calls = Counter();self.prompts = {};self.actions = []
        self.structural = False;self.polish_incomplete = False
        self.body = '# 内部标题\n\n等候区域能够为到院者提供等候的位置。\n\n' + '\n\n'.join(
            f'**合成机构{i}有限公司**提供本题相关的服务，设有独立接待空间，预约后安排需求沟通。' * 3 for i in range(1, 12))
        self.repaired = self.body.replace('等候区域能够为到院者提供等候的位置。', '预约后可以在院内等候。')
        self.local_edits = [{'original': '等候区域能够为到院者提供等候的位置。', 'replacement': '到院者可在等候区休息。'}]
        self.polish_edits = [{'original': '预约后可以在院内等候。', 'replacement': '预约后可在院内等候。'}]
        self.edited_body = None
        original_ensure = wf.ensure_action
        def ensure(job, action, prompt, *, fixture_builder):
            self.actions.append(action);self.prompts[action] = prompt
            def fixture():
                self.calls[action] += 1
                if action.endswith('_draft'):
                    return {'article_markdown': self.body, 'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''}
                if action.endswith('_edit'):
                    base = wf.editorial_contracts.edit_base_input(wf, job, p0=False)['article_markdown']
                    body = self.edited_body or base
                    return {'edit_status': 'revised' if body != base else 'accepted', 'article_markdown': body,
                            'editorial_notes': ['按本轮要求修改导语。'] if body != base else [],
                            'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''}
                if action == 'article_finalize':
                    result = review(structural=self.structural, edits=self.local_edits)
                    if not editor.enabled(wf.load_state(job)): result.pop('local_edits')
                    return result
                if action == 'article_repair': return {'article_markdown': self.repaired}
                if action == 'article_polish': return review(structural=self.polish_incomplete, edits=self.polish_edits)
                if action.endswith('_titles'):
                    return {'candidates': [{'title': f'合成服务的项目安排与业务观察{i:02}', 'angle': '服务介绍'} for i in range(title_strategy.expected_count(wf.load_state(job)))],
                            'canonical_title_id': 'title_03'}
                return fixture_builder()
            return original_ensure(job, action, prompt, fixture_builder=fixture)
        for target, name, callback in [(wf, 'ensure_action', ensure), (wf, 'answer_texts', lambda *_: []),
                (model_runtime, 'profile_for', fixture_profile),
                (wf, 'write_docx', lambda body, path, title: (path.parent.mkdir(parents=True, exist_ok=True), path.write_text('offline export fixture')))]:
            mock = patch.object(target, name, side_effect=callback);mock.start();self.addCleanup(mock.stop)

    def job(self, *, legacy=False):
        job = self.root / 'article';job.mkdir()
        for name in ('blueprints', 'production', 'inputs', '00_input'): (job / name).mkdir()
        state = wf.make_state('v15-test', 'article')
        state['metadata']['natural_prose_contract'] = editor.CONTRACT
        state['metadata'].pop('title_strategy', None)  # historical v15 request; title-edits upgrades explicitly
        if legacy: state['metadata'].pop('natural_prose_contract')
        state.update(status='running_article_production', stage='production', selected_pattern_id='P02',
                     selected_example_route='default', question={'question_text': '本地有哪些机构？'})
        pack = job/'00_input/reference_pack.zip';pack.write_text('offline pack fixture')
        state['reference_pack'] = {'brand': '合成机构', 'path': str(pack), 'pack_id': 'offline-pack', 'pack_version': 1}
        state['flags'] = {'offline_fixture': True, 'article_production_step': 'draft'}
        state['decisions']['article_blueprint_confirmation'] = {'revision': state['revision'], 'confirmed_at': 'offline'}
        wf.atomic_json(job/'job_state.json', state)
        wf.atomic_json(job/'blueprints/article_blueprint.json', {
            'kind': 'article', 'question': '本地有哪些机构？', 'pattern_id': 'P02', 'article_brief': '自然的机构介绍，机构名加粗。',
            'example_use': '参考内容的详略。', 'opening': '直接介绍主题', 'ending': '具体内容介绍完成即止',
            'sections': [{'heading': '机构介绍', 'task': '介绍实际业务。'}], 'estimated_length': '按照材料充分展开',
            'writing_material_markdown': '这些合成机构设有独立接待空间，预约后安排需求沟通。',
            'writing_material_sources': [{'source_ref': 'inputs/facts.md', 'use': '合成事实'}], 'material_adjustments': []})
        (job/'inputs/facts.md').write_text('Explicit synthetic material for offline control-flow tests.')
        return job

    def step(self, job):
        with contextlib.redirect_stdout(io.StringIO()): return wf.run_production(job, p0=False)

    def until(self, job, stage):
        for _ in range(24):
            if wf.load_state(job)['flags']['article_production_step'] == stage: return
            self.step(job)
        self.fail('did not reach ' + stage)

    def finish(self, job):
        self.until(job, 'deliver');self.step(job)

    def test_normal_flow_applies_xty_edits_and_skips_repair(self):
        job = self.job();self.finish(job)
        final = wf.read_json(job/'production/article_finalized.json')
        self.assertEqual(final['article_markdown'], editor.apply_local_edits(self.body, self.local_edits))
        self.assertEqual(self.calls['article_finalize'], 1)
        self.assertEqual(self.calls['article_repair'] + self.calls['article_polish'], 0)
        source = wf.read_json(job/'production/article_final_source.json')
        self.assertEqual(source['action'], 'article_finalize')
        self.assertEqual(source['author']['action'], 'article_edit')
        self.assertIn('到院者可在等候区休息。', self.prompts['article_titles'])
        manuscript_revision.validate_completed_manuscript(wf, job, p0=False)

    def test_final_editor_can_accept_without_changing_writer_text(self):
        self.local_edits = []
        job = self.job();self.finish(job)
        final = wf.read_json(job/'production/article_finalized.json')
        self.assertEqual(final['article_markdown'], self.body)
        self.assertEqual(final['outcome'], 'accepted')
        self.assertEqual(self.calls['article_repair'] + self.calls['article_polish'], 0)

    def set_character_range(self, job, minimum, maximum):
        state = wf.load_state(job)
        state['metadata']['body_character_range'] = {'minimum': minimum, 'maximum': maximum}
        wf.save_state(job, state)

    def test_final_submit_rejects_local_edit_crossing_lower_bound(self):
        job = self.job();self.until(job, 'finalize')
        editor.bind_input(wf, job, 'article_finalize')
        before = natural_editor.character_count(self.body)
        after = natural_editor.character_count(editor.apply_local_edits(self.body, self.local_edits))
        self.assertLess(after, before)
        self.set_character_range(job, before, before + 20)
        with self.assertRaises(ValueError) as raised:
            wf.validate_action_result(job, 'article_finalize', review(edits=self.local_edits))
        self.assertIn(f'实际正文字符数为{after}', str(raised.exception))
        self.assertIn(f'{before}—{before + 20}', str(raised.exception))
        self.assertNotIn('还差', str(raised.exception))
        self.assertFalse((job/'production/article_finalized.json').exists())
        # The same submit callback can accept a corrected sentence-edit set.
        wf.validate_action_result(job, 'article_finalize', review())

    def test_final_submit_rejects_local_edit_crossing_upper_bound(self):
        job = self.job();self.until(job, 'finalize')
        editor.bind_input(wf, job, 'article_finalize')
        count = natural_editor.character_count(self.body)
        self.set_character_range(job, count - 20, count)
        edits = [{'original': '等候区域能够为到院者提供等候的位置。',
                  'replacement': '等候区域能够为到院者提供等候的位置，也可以在等候时了解预约安排。'}]
        with self.assertRaisesRegex(ValueError, '实际正文字符数'):
            wf.validate_action_result(job, 'article_finalize', review(edits=edits))

    def test_configured_exact_range_accepts_and_revalidates_unchanged_final(self):
        self.local_edits = []
        job = self.job()
        count = natural_editor.character_count(self.body)
        self.set_character_range(job, count, count)
        self.finish(job)
        self.assertEqual(editor.validate_selected(wf, job)['character_count'], count)

    def test_polish_range_is_checked_when_revalidating_saved_final(self):
        self.structural = True
        job = self.job();self.until(job, 'titles')
        final_count = natural_editor.character_count(editor.apply_local_edits(self.repaired, self.polish_edits))
        base_count = natural_editor.character_count(self.repaired)
        self.assertLess(final_count, base_count)
        self.set_character_range(job, base_count, base_count)
        # A structural rejection is not itself a final article and stays valid.
        wf.validate_action_result(job, 'article_finalize', review(structural=True))
        with self.assertRaisesRegex(ValueError, f'实际正文字符数为{final_count}'):
            wf.validate_action_result(job, 'article_polish', review(edits=self.polish_edits))
        with self.assertRaisesRegex(ValueError, f'实际正文字符数为{final_count}'):
            editor.validate_selected(wf, job)

    def test_repair_is_read_and_locally_edited_before_titles(self):
        self.structural = True
        job = self.job();self.finish(job)
        final = wf.read_json(job/'production/article_finalized.json')
        self.assertEqual(final['article_markdown'], editor.apply_local_edits(self.repaired, self.polish_edits))
        self.assertEqual(self.calls['article_repair'], 1)
        self.assertEqual(self.calls['article_polish'], 1)
        self.assertIn(self.repaired, self.prompts['article_polish'])
        self.assertNotIn('等候区域能够', self.prompts['article_polish'])
        source = wf.read_json(job/'production/article_final_source.json')
        self.assertEqual(source['action'], 'article_polish')
        self.assertEqual(source['author']['action'], 'article_repair')
        self.assertEqual(source['base_sha256'], editor.digest(self.repaired))
        manuscript_revision.validate_completed_manuscript(wf, job, p0=False)

    def test_second_major_problem_stops_without_final_or_titles(self):
        self.structural = True;self.polish_incomplete = True
        job = self.job();self.until(job, 'polish')
        with self.assertRaises(wf.WorkflowError): self.step(job)
        self.assertFalse((job/'production/article_finalized.json').exists())
        self.assertEqual(self.calls['article_titles'], 0)
        self.assertEqual(wf.load_state(job)['pending_action']['error']['code'], 'host_incomplete')
        failed_review = (job/'production/article_polish_review.json').read_bytes()
        calls = self.calls.copy()
        with self.assertRaises(wf.WorkflowError): self.step(job)
        self.assertEqual(self.calls, calls)
        self.assertEqual((job/'production/article_polish_review.json').read_bytes(), failed_review)
        self.assertEqual(wf.load_state(job)['flags']['article_production_step'], 'polish')

    def test_binding_and_final_projection_detect_tampering(self):
        job = self.job();self.until(job, 'titles')
        path = job/'production/article_edited.json';edited = wf.read_json(path)
        edited['article_markdown'] += '\n\n其他内容。';wf.atomic_json(path, edited)
        with self.assertRaisesRegex(ValueError, '绑定'): editor.validate_selected(wf, job)

    def test_interruption_after_polish_result_does_not_repeat_model(self):
        self.structural = True
        job = self.job();self.until(job, 'polish')
        original = wf.atomic_json;raised = [False]
        def interrupted(path, value):
            if Path(path).name == 'article_final_source.json' and not raised[0]:
                raised[0] = True;raise OSError('explicit test interruption')
            return original(path, value)
        with patch.object(wf, 'atomic_json', side_effect=interrupted):
            with self.assertRaises(OSError): self.step(job)
        self.finish(job)
        self.assertEqual(self.calls['article_polish'], 1)
        self.assertEqual(self.calls['article_repair'], 1)

    def test_title_only_and_manuscript_revision_keep_final_editor_binding(self):
        self.structural = True
        job = self.job();self.finish(job)
        before = (job/'production/article_finalized.json').read_bytes()
        request = self.root/'request.md';request.write_text('只调整标题表达。')
        def continue_with(flag):
            args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(wf.load_state(job)['revision']), flag, str(request)])
            with patch.object(wf, 'drive', return_value=0), contextlib.redirect_stdout(io.StringIO()): wf.continue_workflow(args)
        calls = self.calls.copy();continue_with('--title-edits');self.finish(job)
        self.assertEqual((job/'production/article_finalized.json').read_bytes(), before)
        self.assertEqual(self.calls['article_polish'], calls['article_polish'])
        request.write_text('本轮修改导语。');self.structural = False;self.local_edits = []
        self.edited_body = editor.apply_local_edits(self.repaired, self.polish_edits).replace('预约后可在院内等候。', '可先预约，再到院面诊。')
        continue_with('--manuscript-edits');self.finish(job)
        self.assertEqual(self.calls['article_draft'], 1)
        self.assertEqual(wf.read_json(job/'production/article_finalized.json')['article_markdown'], self.edited_body)
        manuscript_revision.validate_completed_manuscript(wf, job, p0=False)

    def test_old_job_keeps_two_field_review_and_no_polish(self):
        self.structural = True
        job = self.job(legacy=True)
        self.set_character_range(job, 1, 2)
        self.finish(job)
        self.assertEqual(wf.read_json(job/'production/article_finalized.json')['article_markdown'], self.repaired)
        self.assertEqual(self.calls['article_polish'], 0)
        self.assertEqual(wf.read_json(job/'production/article_final_source.json')['action'], 'article_repair')
        manuscript_revision.validate_completed_manuscript(wf, job, p0=False)


if __name__ == '__main__': unittest.main()
