"""Review advice concerns actual manuscript claims; older requests stay fixed."""
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_manuscript_outline_input_final13 as outline
from shared import manuscript_revision, model_runtime, writing_context
from shared import writing_requirements as requirements
from shared.writing_context_v13 import _review_scope

V1_SCOPE = ("\n\n本轮编辑阅读原则：事实修正针对正文实际作出的断言；未作出的能力主张不新增缺失说明。"
            "篇幅意见指向原件中尚未采用的具体信息。作者可以组织已知材料，说明业务特点与读者需求的关系；"
            "具体诊疗流程、手术能力和效果陈述须有直接材料支持。")


class ReviewScopeInputTests(unittest.TestCase):
    setUp = outline.ManuscriptOutlineInputTests.setUp
    job = outline.ManuscriptOutlineInputTests.job
    step = outline.ManuscriptOutlineInputTests.step
    until = outline.ManuscriptOutlineInputTests.until
    finish = outline.ManuscriptOutlineInputTests.finish
    prepare_edit = outline.ManuscriptOutlineInputTests.prepare_edit

    def test_new_edit_freezes_review_scope_and_preserves_single_repair_flow(self):
        job = self.prepare_edit()
        revision = manuscript_revision.current_revision(wf, job, p0=False)
        self.assertEqual(revision['editorial_review_scope_mode'], requirements.EDITORIAL_REVIEW_SCOPE_MODE)
        self.needs_revision = True
        self.finish(job)
        scope = _review_scope(wf, job, p0=False)
        self.assertTrue(scope)
        self.assertIn(scope, self.prompts['article_finalize'])
        for action in ('article_edit', 'article_repair', 'article_titles'):
            self.assertNotIn(scope, self.prompts[action])
        self.assertEqual(self.actions[-5:], ['article_edit', 'article_finalize', 'article_repair', 'article_titles', 'article_title_review'])

    def test_existing_revision_retry_keeps_original_review_request_and_fingerprint(self):
        job = self.prepare_edit()
        state = wf.load_state(job)
        pointer = state['metadata']['article_manuscript_revision']
        path = job/pointer['path']
        frozen = wf.read_json(path)
        frozen.pop('editorial_review_scope_mode')
        wf.atomic_json(path, frozen)
        pointer['sha256'] = manuscript_revision.file_hash(path)
        wf.save_state(job, state)
        self.until(job, 'finalize')
        before = writing_context.prompt_finalize(wf, job, p0=False)
        identity = model_runtime.request_fingerprint('article_finalize', before)
        self.assertEqual(_review_scope(wf, job, p0=False), '')
        state = wf.load_state(job)
        state['pending_action'] = {'action':'article_finalize', 'error':{'code':'interrupted_attempt'}}
        wf.save_state(job, state)
        args = wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(state['revision']),'--retry-current-action'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        after = writing_context.prompt_finalize(wf, job, p0=False)
        self.assertEqual(before, after)
        self.assertEqual(identity, model_runtime.request_fingerprint('article_finalize', after))
        self.assertNotIn('editorial_review_scope_mode', manuscript_revision.current_revision(wf, job, p0=False))

    def test_initial_commission_does_not_implicitly_change_review_scope(self):
        job = self.job()
        self.assertIsNone(manuscript_revision.current_revision(wf, job, p0=False))
        self.assertEqual(_review_scope(wf, job, p0=False), '')

    def test_frozen_v1_retry_preserves_exact_old_scope_prompt_and_identity(self):
        with patch.object(requirements, 'EDITORIAL_REVIEW_SCOPE_MODE', 'actual-claims-v1'):
            job = self.prepare_edit()
        self.until(job, 'finalize')
        before = writing_context.prompt_finalize(wf, job, p0=False)
        identity = model_runtime.request_fingerprint('article_finalize', before)
        state = wf.load_state(job)
        pointer = state['metadata']['article_manuscript_revision']
        frozen_bytes = (job/pointer['path']).read_bytes()
        self.assertEqual(_review_scope(wf, job, p0=False), V1_SCOPE)
        state['pending_action'] = {'action': 'article_finalize', 'error': {'code': 'interrupted_attempt'}}
        wf.save_state(job, state)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']), '--retry-current-action'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        after = writing_context.prompt_finalize(wf, job, p0=False)
        self.assertEqual(before, after)
        self.assertEqual(identity, model_runtime.request_fingerprint('article_finalize', after))
        self.assertEqual((job/pointer['path']).read_bytes(), frozen_bytes)
        self.assertEqual(manuscript_revision.current_revision(wf, job, p0=False)['editorial_review_scope_mode'], 'actual-claims-v1')

    def test_explicit_edit_upgrades_v1_only_after_preserving_old_revision(self):
        with patch.object(requirements, 'EDITORIAL_REVIEW_SCOPE_MODE', 'actual-claims-v1'):
            job = self.prepare_edit()
        self.needs_revision = False
        self.finish(job)
        old_state = wf.load_state(job)
        old_pointer = old_state['metadata']['article_manuscript_revision']
        old_bytes = (job/old_pointer['path']).read_bytes()
        request = self.root/'next_edit.md'
        request.write_text('保留有依据的技术解释，展开已经采用但尚未讲清的业务关系。')
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(old_state['revision']), '--manuscript-edits', str(request)])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        new_record = manuscript_revision.current_revision(wf, job, p0=False)
        self.assertEqual(new_record['editorial_review_scope_mode'], 'actual-claims-v2')
        snapshot = Path(new_record['source_snapshot'])
        self.assertEqual((snapshot/old_pointer['path']).read_bytes(), old_bytes)
        self.assertEqual((job/old_pointer['path']).read_bytes(), old_bytes)
        self.assertEqual(_review_scope(wf, snapshot, p0=False), V1_SCOPE)
        self.needs_revision = True
        before_calls = len(self.actions)
        self.finish(job)
        self.assertEqual(self.actions[before_calls:], ['article_edit', 'article_finalize', 'article_repair', 'article_titles', 'article_title_review'])
        self.assertNotIn(V1_SCOPE, self.prompts['article_finalize'])
        self.assertIn(_review_scope(wf, job, p0=False), self.prompts['article_finalize'])

    def test_v2_no_comments_preserves_body_and_skips_repair(self):
        job = self.prepare_edit()
        self.needs_revision = False
        before_calls = len(self.actions)
        self.finish(job)
        self.assertEqual(self.actions[before_calls:], ['article_edit', 'article_finalize', 'article_titles', 'article_title_review'])
        self.assertEqual(wf.read_json(job/'production/article_finalized.json')['article_markdown'], self.body)


if __name__ == '__main__':
    unittest.main()
