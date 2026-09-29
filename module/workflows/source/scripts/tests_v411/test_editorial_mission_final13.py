"""New commissions use a small editorial mission; paid older inputs stay fixed."""
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from shared import article_positioning, manuscript_revision, model_runtime, natural_editor
from shared import writing_requirements as requirements


class EditorialMissionTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp
    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def job(self, prefix='article'):
        job = flow.NaturalEditorFlowTests.job(self, prefix)
        state = wf.load_state(job)
        state["metadata"]["writing_mission_input_mode"] = requirements.WRITING_MISSION_INPUT_MODE
        wf.save_state(job, state)
        return job

    # Exercise the same complete selection, interruption and continuation
    # contracts with actual requests carrying the new input marker.
    test_no_comments_keeps_exact_body = flow.NaturalEditorFlowTests.test_no_comments_selects_exact_candidate_and_skips_writer_repair
    test_comments_repair_once_then_titles = flow.NaturalEditorFlowTests.test_comments_trigger_one_repair_then_titles_without_body_rereview
    test_interrupted_repair_recovers_without_second_call = flow.NaturalEditorFlowTests.test_interruption_after_provider_result_recovers_without_duplicate_call
    test_repaired_output_supports_future_edits = flow.NaturalEditorFlowTests.test_completed_repair_can_continue_with_title_and_manuscript_edits
    test_p0_retains_third_pass = flow.NaturalEditorFlowTests.test_p0_keeps_style_pass_and_repair_uses_styled_body

    def test_actual_writer_payload_preserves_requirements_facts_and_separates_lookup(self):
        job = self.job()
        bp = wf.read_json(job/'blueprints/article_blueprint.json')
        bp.update(article_brief='本篇新闻专题委托。', estimated_length='3000个正文可见字符',
                  recommendation_relationships='保留本题确定的推荐分档。',
                  formatting='主体名称行内加粗，正文紧接。',
                  writing_material_markdown='甲机构开展水动力项目。李医生方向为脂肪整形。具体部位结合面诊安排。',
                  material_adjustments=['本篇不采用项目价格。'],
                  writing_material_sources=[{'source_ref': 'inputs/facts.md', 'use': 'SOURCE_LOCATION_A17_B17'}])
        wf.atomic_json(job/'blueprints/article_blueprint.json', bp)
        self.needs_revision = True
        self.finish(job)
        for action in ('article_draft', 'article_edit', 'article_repair'):
            prompt = self.prompts[action]
            self.assertTrue(prompt.startswith(requirements.MISSION_MARKER+'\n'))
            self.assertEqual(prompt.count(bp['writing_material_markdown']), 1)
            self.assertEqual(prompt.count('本篇不采用项目价格。'), 1)
            self.assertEqual(prompt.count('3000个正文可见字符'), 1)
            self.assertIn(bp['recommendation_relationships'], prompt)
            self.assertIn(bp['formatting'], prompt)
            self.assertNotIn('SOURCE_LOCATION_A17_B17', prompt)
            payload = model_runtime.build_payload(action, prompt)
            system = payload['messages'][0]['content']
            self.assertLess(len(system), 800)
            self.assertIn(requirements.EDITORIAL_CORE, system)
        self.assertIn('SOURCE_LOCATION_A17_B17', self.prompts['article_finalize'])
        self.assertIn(self.body, self.prompts['article_edit'])
        self.assertIn(self.body, self.prompts['article_repair'])

    def test_independent_mission_does_not_inherit_old_roles_or_change_provider_budget(self):
        job = self.job()
        prompt = wf.prompt_article(job, p0=False)
        normal = model_runtime.build_payload('article_draft', prompt)
        with patch.object(article_positioning, 'NATURAL_CORE', 'OLD_CORE_SENTINEL'), \
             patch.object(model_runtime, 'WRITING_FACTS_CORE', 'OLD_FACTS_SENTINEL'):
            actual = model_runtime.build_payload('article_draft', prompt)
        self.assertEqual(actual, normal)
        state = wf.load_state(job)
        state['metadata'].pop('writing_mission_input_mode')
        wf.save_state(job, state)
        old_payload = model_runtime.build_payload('article_draft', wf.prompt_article(job, p0=False))
        for key in set(actual)-{'messages'}:
            self.assertEqual(actual[key], old_payload[key], key)

    def test_explicit_commission_upgrades_only_after_old_manuscript_snapshot(self):
        job = flow.NaturalEditorFlowTests.job(self)
        self.finish(job)
        old_prompt = self.prompts['article_edit']
        old_fingerprint = model_runtime.request_fingerprint('article_edit', old_prompt)
        manuscript_revision.validate_completed_manuscript(wf, job, p0=False)
        previous = wf.load_state(job)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(previous['revision']),
                                      '--blueprint-edits', '重新组织本篇。', '--upgrade-writing-editor'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        state = wf.load_state(job)
        from shared import writing_context_v14
        self.assertTrue(writing_context_v14.enabled(state))
        snapshot = Path(state['metadata']['writing_reruns'][-1]['archive_path'])
        self.assertFalse(requirements.editorial_mission(wf.load_state(snapshot)))
        self.assertEqual((snapshot/'production/article_finalized.json').read_bytes(),
                         (job/'production/article_finalized.json').read_bytes())
        self.assertEqual(model_runtime.request_fingerprint('article_edit', old_prompt), old_fingerprint)
        self.assertTrue(wf.prompt_blueprint(job, p0=False).startswith(writing_context_v14.MARKER+'\n'))

    def test_retry_acceptance_and_existing_outline_do_not_opt_in(self):
        job = flow.NaturalEditorFlowTests.job(self)
        self.until(job, 'edit')
        before = wf.prompt_edit(job, p0=False)
        state = wf.load_state(job)
        self.assertIn('writing_outline_input_mode', state['metadata'])
        state['pending_action'] = {'action': 'article_edit', 'error': {'code': 'interrupted_attempt'}}
        wf.save_state(job, state)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']), '--retry-current-action'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        self.assertEqual(wf.prompt_edit(job, p0=False), before)
        self.assertFalse(requirements.editorial_mission(wf.load_state(job)))
        state = wf.load_state(job)
        state['status'] = 'awaiting_blueprint_confirmation'
        wf.save_state(job, state)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']), '--accept-blueprint'])
        with patch.object(wf, 'drive', return_value=0):
            wf.handle_article_blueprint_pause(args, job)
        self.assertFalse(requirements.editorial_mission(wf.load_state(job)))

    def test_new_blueprint_schema_and_patterns_keep_each_article_task(self):
        from shared import writing_context_v14
        for kind in ('p0', 'article'):
            self.assertTrue(writing_context_v14.enabled(wf.make_state('new-'+kind, kind)))
        job = self.job()
        for pattern in ('P01', 'P02', 'P03', 'P04', 'P05', 'P06'):
            state = wf.load_state(job)
            state['selected_pattern_id'] = pattern
            wf.save_state(job, state)
            prompt = wf.prompt_blueprint(job, p0=False)
            from shared.writing_context_v13 import NATURAL_PATTERN_GUIDANCE
            self.assertIn(NATURAL_PATTERN_GUIDANCE[pattern], prompt)
            schema = model_runtime.submit_tool_for('article_blueprint', prompt=prompt)
            fields = schema['function']['parameters']['properties']['result']['properties']
            self.assertEqual(fields['estimated_length']['description'], '当前明确篇幅目标及统计口径；未指定时参考最长有效篇幅样本。')
            self.assertIn('writing_material_sources', fields['writing_material_markdown']['description'])
            self.assertTrue(natural_editor.matches(prompt))


if __name__ == '__main__':
    unittest.main()
