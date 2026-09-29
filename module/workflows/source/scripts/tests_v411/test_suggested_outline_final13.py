"""Carry adjustable composition ideas without changing historical requests."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from shared import manuscript_revision, model_runtime, writing_context
from shared import writing_requirements as requirements

OUTLINE = {
    'opening': 'OUTLINE_OPENING：从具体服务进入。',
    'sections': [{'heading': 'OUTLINE_HEADING：服务怎样展开',
                  'task': 'OUTLINE_TASK：先介绍方法，再用具体动作推进。'}],
    'ending': 'OUTLINE_ENDING：完成服务介绍处收束。',
    'example_use': 'OUTLINE_EXAMPLE：从完整例文借鉴详略与推进。',
}
MARKERS = ('OUTLINE_OPENING', 'OUTLINE_HEADING', 'OUTLINE_TASK', 'OUTLINE_ENDING', 'OUTLINE_EXAMPLE')


class SuggestedOutlineTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp
    job = flow.NaturalEditorFlowTests.job
    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def prepared_job(self, *, marked=True, prefix='article'):
        job = self.job(prefix)
        bp = wf.read_json(job/'blueprints'/f'{prefix}_blueprint.json')
        bp.update(OUTLINE)
        wf.atomic_json(job/'blueprints'/f'{prefix}_blueprint.json', bp)
        if not marked:
            state = wf.load_state(job)
            state['metadata'].pop('writing_outline_input_mode', None)
            wf.save_state(job, state)
        return job

    def test_actual_draft_edit_and_repair_payloads_receive_adjustable_outline(self):
        job = self.prepared_job()
        self.needs_revision = True
        self.finish(job)
        for action in ('article_draft', 'article_edit', 'article_repair'):
            prompt = self.prompts[action]
            for marker in MARKERS:
                self.assertEqual(prompt.count(marker), 1, (action, marker))
            self.assertIn('当前用户要求和后续明确修改优先', prompt)
            self.assertIn('不要求把正文重排回旧章节', prompt)
            wire = json.dumps(model_runtime.build_payload(action, prompt), ensure_ascii=False)
            for marker in MARKERS:
                self.assertIn(marker, wire)
        self.assertEqual(self.actions, ['article_draft', 'article_edit', 'article_finalize',
                                       'article_repair', 'article_titles', 'article_title_review'])

    def test_unmarked_v13_prompt_bytes_and_request_identity_are_unchanged(self):
        # Captured before suggested-outline-v1 with these exact synthetic inputs.
        expected = {
            'article_draft': ('76250b7935ac4737cfa8732296cec463b6c9c111f8dbc7ca04be529d445f3f98',
                             '94b8ae73ac72ac031f9c9a16367f4e263938ef58595b0176a669098cecdcba7b'),
            'article_edit': ('143a206921086fdd5a7a51a019586fd19c8d5a0ec8af570cca9138b7afea735c',
                            'd1e7ca2833003b9354ac41f9fa31b04b057b38d68394ecb89a8cf85e57bebeae'),
            'article_repair': ('3b5a2bfc898a25271b938fe2f4e442a7545ddb478913b659d1f2f8a964c0c13f',
                              '0862b0084cc4941c3d155f61305d67ae81f40523ad5283bbefa0b5146964b212'),
        }
        job = self.prepared_job(marked=False)
        self.needs_revision = True
        builders = {
            'draft': lambda: wf.prompt_article(job, p0=False),
            'edit': lambda: wf.prompt_edit(job, p0=False),
            'repair': lambda: writing_context.prompt_repair(wf, job, p0=False),
        }
        for stage, build in builders.items():
            self.until(job, stage)
            prompt = build(); action = 'article_'+stage
            self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), expected[action][0])
            # v16.2 intentionally changed provider transport/configuration; prompt bytes stay frozen.
            self.assertEqual(model_runtime.build_payload(action, prompt)["messages"][1]["content"], prompt)
            self.assertNotIn('OUTLINE_OPENING', prompt)
        self.assertNotIn('writing_outline_input_mode', wf.load_state(job)['metadata'])

    def test_retry_keeps_unmarked_input_and_does_not_opt_in(self):
        job = self.prepared_job(marked=False)
        self.until(job, 'edit')
        before = wf.prompt_edit(job, p0=False)
        state = wf.load_state(job)
        state['pending_action'] = {'action': 'article_edit', 'error': {'code': 'interrupted_attempt'}}
        wf.save_state(job, state)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']), '--retry-current-action'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        self.assertNotIn('writing_outline_input_mode', wf.load_state(job)['metadata'])
        self.assertEqual(wf.prompt_edit(job, p0=False), before)

    def test_new_blueprint_commission_marks_after_verification_and_old_snapshot(self):
        job = self.prepared_job(marked=False)
        self.finish(job)
        old = wf.load_state(job)
        validate = manuscript_revision.validate_completed_manuscript
        events = []
        def check(*args, **kwargs):
            self.assertNotIn('writing_outline_input_mode', wf.load_state(job)['metadata'])
            result = validate(*args, **kwargs)
            events.append('old-validated')
            return result
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(old['revision']),
                                      '--blueprint-edits', '明确重新构思本篇内容。', '--upgrade-writing-editor'])
        with patch.object(manuscript_revision, 'validate_completed_manuscript', side_effect=check), \
             patch.object(wf, 'drive', return_value=0) as drive:
            wf.continue_workflow(args)
            drive.assert_called_once()
        self.assertEqual(events, ['old-validated'])
        state = wf.load_state(job)
        self.assertEqual(state['metadata']['writing_outline_input_mode'], requirements.WRITING_OUTLINE_INPUT_MODE)
        snapshot = Path(state['metadata']['writing_reruns'][-1]['archive_path'])
        self.assertNotIn('writing_outline_input_mode', wf.load_state(snapshot)['metadata'])
        self.assertEqual((job/'production/article_finalized.json').read_bytes(), (snapshot/'production/article_finalized.json').read_bytes())

    def test_new_jobs_and_explicit_p0_blueprint_edits_get_mode_but_plain_acceptance_does_not(self):
        for kind in ('p0', 'article'):
            self.assertEqual(wf.make_state('new-'+kind, kind)['metadata']['writing_outline_input_mode'], requirements.WRITING_OUTLINE_INPUT_MODE)
        job = self.prepared_job(marked=False, prefix='p0')
        state = wf.load_state(job); state['status'] = 'awaiting_p0_blueprint_confirmation'; wf.save_state(job, state)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']), '--p0-blueprint-edits', '新的P0构思。'])
        with patch.object(wf, 'drive', return_value=0):
            wf.handle_p0_blueprint_pause(args, job)
        self.assertEqual(wf.load_state(job)['metadata']['writing_outline_input_mode'], requirements.WRITING_OUTLINE_INPUT_MODE)
        other = self.prepared_job(marked=False)
        state = wf.load_state(other); state['status'] = 'awaiting_blueprint_confirmation'; wf.save_state(other, state)
        args = wf.parser().parse_args(['continue', '--job-dir', str(other), '--revision', str(state['revision']), '--accept-blueprint'])
        with patch.object(wf, 'drive', return_value=0):
            wf.handle_article_blueprint_pause(args, other)
        self.assertNotIn('writing_outline_input_mode', wf.load_state(other)['metadata'])

    def test_later_manuscript_revision_keeps_actual_base_and_labels_outline_as_advisory(self):
        job = self.prepared_job()
        self.finish(job)
        request = self.root/'edit.md'; request.write_text('本轮将两节合并，沿用实际完整终稿。')
        state = wf.load_state(job)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']), '--manuscript-edits', str(request)])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        prompt = wf.prompt_edit(job, p0=False)
        self.assertIn(request.read_text(), prompt)
        self.assertIn(self.body, prompt)
        self.assertIn('不是必须逐节完成的正文合同', prompt)
        self.assertIn('不要求把正文重排回旧章节', prompt)


if __name__ == '__main__':
    unittest.main()
