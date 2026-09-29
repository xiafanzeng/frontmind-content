"""Blueprint review is derived presentation; history shapes never alter facts."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.tests_v411.test_workflow_v411 import CONTROLLER as C


class BlueprintReviewCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='frontmind-blueprint-review-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        guard = mock.patch.object(C, 'run_action', side_effect=AssertionError('Review must never invoke a model'))
        guard.start()
        self.addCleanup(guard.stop)

    def blueprint(self, p0=True):
        return {
            'kind': 'p0' if p0 else 'article',
            'opening': '开篇建立企业身份，介绍软件测试服务。',
            'sections': [{'heading': '测试如何服务项目', 'task': '解释客户任务与测试动作的关系。'}],
            'ending': '以项目交付条件收束。',
            'materials': {'核心材料': '保留项目名称与真实测试动作。', '适用条件': ['常规周期有前提。', '历史资质不作现行保证。']},
            'material_adjustments': '历史证书仅按对应日期使用，不推断当前续期状态。',
            'existing_p0_edit_plan': '保留章节主题，按本篇素材重新展开自然叙述。',
            'writing_material_markdown': '企业围绕客户软件项目开展测试并交付报告。',
            'style_source': {'观察': '具体业务事实连续推进。', '采用': '解释动作之间的关系。'},
            'estimated_length': 3200,
            'candidate_order': ['主体甲', '主体乙'],
        }

    def job(self, p0=True):
        job = self.base / ('p0' if p0 else 'article')
        job.mkdir(exist_ok=True)
        value = self.blueprint(p0)
        source = job / 'blueprints' / ('p0_blueprint.json' if p0 else 'article_blueprint.json')
        C.atomic_json(source, value)
        state = C.make_state('review-compatibility', 'p0' if p0 else 'article')
        state['decisions'] = {'preserved_user_choice': {'text': '保留原用户决策', 'revision': 2}}
        C.atomic_json(job / 'job_state.json', state)
        status = 'awaiting_p0_blueprint_confirmation' if p0 else 'awaiting_blueprint_confirmation'
        C.set_pause(job, status, '# 旧错误页面\n\n- 历\n- 史\n\n只显示材料键', choices=['确认蓝图'], full_text_links=[source], stage='blueprint')
        return job, source

    def continue_job(self, job, *flags):
        args = C.parser().parse_args(['continue', '--job-dir', str(job), *flags])
        with redirect_stdout(io.StringIO()) as output:
            result = args.func(args)
        return result, output.getvalue()

    def test_real_string_and_mapping_shapes_render_complete_without_mutation(self):
        value = self.blueprint()
        original = deepcopy(value)
        C.validate_blueprint(value, p0=True)
        text = C.blueprint_confirmation_markdown(value, p0=True)
        self.assertEqual(value, original)
        self.assertIn(value['material_adjustments'], text)
        self.assertIn(value['existing_p0_edit_plan'], text)
        self.assertIn(value['materials']['核心材料'], text)
        for item in value['materials']['适用条件']:
            self.assertIn(item, text)
        self.assertIn(value['style_source']['观察'], text)
        self.assertIn('3200', text)
        self.assertNotIn('- 历\n- 史', text)

    def test_blank_continue_refreshes_only_derived_page_and_is_idempotent(self):
        for p0 in (True, False):
            with self.subTest(p0=p0):
                job, source = self.job(p0)
                state_path = job / 'job_state.json'
                state_bytes, source_bytes = state_path.read_bytes(), source.read_bytes()
                state = json.loads(state_bytes)
                review = Path(state['current_pause']['review_markdown_path'])
                old_page = review.read_bytes()
                result, output = self.continue_job(job)
                self.assertEqual(result, 0)
                self.assertIn(self.blueprint(p0)['material_adjustments'], output)
                self.assertEqual(state_path.read_bytes(), state_bytes)
                self.assertEqual(source.read_bytes(), source_bytes)
                history = list((job / 'reviews/history').glob('*.md'))
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0].read_bytes(), old_page)
                after = review.stat().st_mtime_ns
                self.continue_job(job)
                self.assertEqual(review.stat().st_mtime_ns, after)
                self.assertEqual(state_path.read_bytes(), state_bytes)
                self.assertEqual(len(list((job / 'reviews/history').glob('*.md'))), 1)

    def test_list_and_map_fields_keep_both_labels_and_values(self):
        value = self.blueprint(False)
        value['material_adjustments'] = {'证书': ['保留历史日期。', '不推断自动采信。'], '周期': '区分业务条件。'}
        value['candidate_order'] = '只讨论题目指定主体。'
        text = C.blueprint_confirmation_markdown(value, p0=False)
        for token in ('证书', '保留历史日期。', '不推断自动采信。', '周期', '区分业务条件。', '只讨论题目指定主体。'):
            self.assertIn(token, text)
        self.assertNotIn('1. 只\n2. 讨', text)

    def test_reconfirmation_appends_note_preserving_string_list_and_map(self):
        for index, original in enumerate(('原始收窄说明。', ['原说明甲。', '原说明乙。'], {'原事项': '原条件。'})):
            with self.subTest(shape=type(original).__name__):
                job = self.base / ('reconfirm-' + str(index));job.mkdir()
                value = self.blueprint()
                value['material_adjustments'] = deepcopy(original)
                source = job / 'blueprints/p0_blueprint.json'
                provider = job / 'provider/p0_blueprint/result.json'
                C.atomic_json(source, value);C.atomic_json(provider, value)
                provider_bytes = provider.read_bytes()
                C.atomic_json(job/'job_state.json', C.make_state('reconfirm', 'p0'))
                with redirect_stdout(io.StringIO()):
                    C._return_blueprint_after_substantive_edit(job, p0=True, reason='核心表述需要用户重新确认。')
                result = json.loads(source.read_text())
                expected_original = original if isinstance(original, list) else [original]
                self.assertEqual(result['material_adjustments'][:-1], expected_original)
                note = result['material_adjustments'][-1]
                self.assertIn('核心表述需要用户重新确认。', note)
                self.assertEqual(result['writing_material_markdown'], value['writing_material_markdown'])
                self.assertEqual(result['sections'], value['sections'])
                self.assertEqual(provider.read_bytes(), provider_bytes)
                with redirect_stdout(io.StringIO()):
                    C._return_blueprint_after_substantive_edit(job, p0=True, reason='核心表述需要用户重新确认。')
                self.assertEqual(json.loads(source.read_text())['material_adjustments'].count(note), 1)

    def test_other_business_pause_is_not_refreshed(self):
        job, _ = self.job()
        C.set_pause(job, 'awaiting_p0_route', '# 原路由确认页\n', choices=['新建 P0'], stage='p0_route')
        state_path = job/'job_state.json';before=state_path.read_bytes()
        state=json.loads(before);review=Path(state['current_pause']['review_markdown_path']);page=review.read_bytes()
        self.continue_job(job)
        self.assertEqual(state_path.read_bytes(), before)
        self.assertEqual(review.read_bytes(), page)
        self.assertFalse((job/'reviews/history').exists())

    def test_refresh_does_not_allow_stale_revision_to_confirm(self):
        job, _ = self.job()
        self.continue_job(job)
        with self.assertRaises(C.WorkflowError):
            self.continue_job(job, '--accept-p0-blueprint', '--revision', '0')

    def test_v14_render_and_refresh_translate_field_names_without_changing_blueprint(self):
        for p0 in (True, False):
            with self.subTest(p0=p0):
                job, source = self.job(p0)
                value = json.loads(source.read_text())
                value['article_brief'] = '按 article_brief 与 formatting 展开自然介绍。'
                value['material_adjustments'] = [
                    '完整保留 candidate_order 的顺序及 recommendation_relationships。',
                    'estimated_length 沿用当前目标，writing_material_markdown 按重点选用。',
                ]
                C.atomic_json(source, value)
                original = source.read_bytes()
                with redirect_stdout(io.StringIO()):
                    C.render_blueprint_confirmation(job, p0=p0)
                state_path = job / 'job_state.json'
                state = json.loads(state_path.read_text())
                before_state = state_path.read_bytes()
                review = Path(state['current_pause']['review_markdown_path'])
                page = review.read_text()
                for label in ('## 导语与切入方式', '## 内容安排', '## 其他写作约定',
                              '主体顺序', '推荐关系', '篇幅目标', '写作素材', '本篇写作要求', '排版要求'):
                    self.assertIn(label, page)
                for field in ('candidate_order', 'recommendation_relationships', 'writing_material_markdown'):
                    self.assertNotIn(field, page)
                self.assertEqual(source.read_bytes(), original)
                C.assert_public_review(page)  # Existing public-page assertion is unchanged.
                review.write_text('# 旧显示副本\n')
                with redirect_stdout(io.StringIO()):
                    C.refresh_blueprint_confirmation(job, p0=p0)
                self.assertEqual(review.read_text(), page)
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(state_path.read_bytes(), before_state)

    def test_legacy_blueprint_page_keeps_its_labels_and_public_assertion(self):
        from shared import writing_requirements
        job, source = self.job(False)
        state = C.load_state(job)
        state['metadata']['writing_mission_input_mode'] = writing_requirements.WRITING_MISSION_INPUT_MODE
        C.save_state(job, state)
        original = source.read_bytes()
        expected = C.blueprint_confirmation_markdown(json.loads(source.read_text()), p0=False)
        with redirect_stdout(io.StringIO()):
            C.render_blueprint_confirmation(job, p0=False)
        review = Path(C.load_state(job)['current_pause']['review_markdown_path'])
        self.assertEqual(review.read_text(), expected)
        for label in ('## 开头如何直接建立位置或结论', '## 最终 H2/H3 与内容任务',
                      '## 当前材料不足导致的收窄、改写或省略'):
            self.assertIn(label, review.read_text())
        self.assertEqual(source.read_bytes(), original)
        value = json.loads(original)
        value['material_adjustments'] = ['保持 candidate_order。']
        historical = C.blueprint_confirmation_markdown(value, p0=False)
        self.assertIn('candidate_order', historical)
        with self.assertRaises(C.WorkflowError):
            C.assert_public_review(historical)


if __name__ == '__main__':
    unittest.main()
