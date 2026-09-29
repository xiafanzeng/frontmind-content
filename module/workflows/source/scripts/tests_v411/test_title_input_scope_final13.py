"""Titles use the delivered article; saved older title inputs remain stable."""
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_manuscript_outline_input_final13 as outline
from shared import manuscript_revision, model_runtime, writing_context
from shared import writing_requirements as requirements


class TitleInputScopeTests(unittest.TestCase):
    setUp = outline.ManuscriptOutlineInputTests.setUp
    job = outline.ManuscriptOutlineInputTests.job
    step = outline.ManuscriptOutlineInputTests.step
    until = outline.ManuscriptOutlineInputTests.until
    finish = outline.ManuscriptOutlineInputTests.finish
    prepare_edit = outline.ManuscriptOutlineInputTests.prepare_edit

    def request_titles(self, job, text='NEW_TITLE_REQUEST：各标题覆盖这篇完整文章。'):
        path = self.root/'titles.md'
        path.write_text(text)
        state = wf.load_state(job)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']),
                                      '--title-edits', str(path)])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)

    def title_inputs(self, job):
        return {
            'article_titles': writing_context.prompt_titles(wf, job, p0=False),
            # This helper inspects requests before the new generation has run.
            'article_title_review': writing_context.prompt_title_review(wf, job, p0=False, title_result=wf.fixture_titles(job, p0=False)),
        }

    def retry(self, job, action):
        state = wf.load_state(job)
        state['pending_action'] = {'action': action, 'error': {'code': 'interrupted_attempt'}}
        wf.save_state(job, state)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']),
                                      '--retry-current-action'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)

    def test_new_article_title_stages_drop_completed_body_commands(self):
        job = self.prepare_edit()
        self.finish(job)
        for action in ('article_titles', 'article_title_review'):
            prompt = self.prompts[action]
            self.assertNotIn('NEW_EDIT_REQUEST', prompt)
            self.assertNotIn('OBSOLETE_', prompt)
            self.assertNotIn('SPECIFIC_FACTS', prompt)
            self.assertIn('3000个正文可见字符', prompt)
            self.assertIn(self.body.split('\n', 1)[1], prompt)
        self.assertIn('NEW_EDIT_REQUEST', self.prompts['article_edit'])
        self.assertIn('NEW_EDIT_REQUEST', self.prompts['article_finalize'])

    def test_new_title_revision_from_old_job_freezes_current_brief_and_preserves_body(self):
        job = self.prepare_edit()
        state = wf.load_state(job)
        state['metadata'].pop('title_input_mode')
        wf.save_state(job, state)
        self.finish(job)
        old_prompts = self.title_inputs(job)
        for prompt in old_prompts.values():
            self.assertIn('NEW_EDIT_REQUEST', prompt)
        immutable = {name: (job/'production'/name).read_bytes() for name in (
            'article_draft.json', 'article_edited.json', 'article_editorial_review.json',
            'article_finalized.json', 'article_final_source.json')}
        pointer = state['metadata']['article_manuscript_revision']
        old_record = (job/pointer['path']).read_bytes()
        before_calls = len(self.actions)
        self.request_titles(job)
        revision = manuscript_revision.current_title_revision(wf, job, p0=False)
        self.assertEqual(revision['title_input_mode'], requirements.TITLE_INPUT_MODE)
        self.assertEqual(revision['effective_writing_requirements']['estimated_length'], '3000个正文可见字符')
        snapshot = Path(revision['source_snapshot'])
        self.assertEqual(self.title_inputs(snapshot), old_prompts)
        self.assertEqual((snapshot/pointer['path']).read_bytes(), old_record)
        self.finish(job)
        self.assertEqual(self.actions[before_calls:], ['article_titles', 'article_title_review'])
        for action in ('article_titles', 'article_title_review'):
            prompt = self.prompts[action]
            self.assertIn('NEW_TITLE_REQUEST', prompt)
            self.assertNotIn('NEW_EDIT_REQUEST', prompt)
            self.assertIn(self.body.split('\n', 1)[1], prompt)
        for name, data in immutable.items():
            self.assertEqual((job/'production'/name).read_bytes(), data, name)
        self.assertEqual((job/pointer['path']).read_bytes(), old_record)

    def test_old_frozen_title_request_ignores_new_default_on_retry(self):
        job = self.prepare_edit()
        self.finish(job)
        self.request_titles(job)
        state = wf.load_state(job)
        frozen = state['metadata']['article_title_revision']
        frozen.pop('title_input_mode')
        frozen.pop('effective_writing_requirements')
        frozen.pop('title_strategy', None)
        frozen.pop('title_question', None)
        # A legacy saved request wins even if the surrounding state now has a
        # newer default. The old record itself must not be rewritten on retry.
        wf.save_state(job, state)
        before = self.title_inputs(job)
        identities = {a: model_runtime.request_fingerprint(a, p) for a, p in before.items()}
        for prompt in before.values():
            self.assertIn('NEW_EDIT_REQUEST', prompt)
            self.assertIn('NEW_TITLE_REQUEST', prompt)
        self.retry(job, 'article_titles')
        after = self.title_inputs(job)
        self.assertEqual(after, before)
        self.assertEqual({a: model_runtime.request_fingerprint(a, p) for a, p in after.items()}, identities)
        self.assertEqual(wf.load_state(job)['metadata']['article_title_revision'], frozen)

    def test_new_title_request_retry_keeps_same_input_and_frozen_requirements(self):
        job = self.prepare_edit()
        self.finish(job)
        self.request_titles(job)
        before = self.title_inputs(job)
        state = wf.load_state(job)
        frozen = state['metadata']['article_title_revision']
        state['metadata']['effective_writing_requirements']['estimated_length'] = 'UNRELATED_LATER_STATE'
        wf.save_state(job, state)
        self.retry(job, 'article_titles')
        after = self.title_inputs(job)
        self.assertEqual(after, before)
        self.assertEqual(wf.load_state(job)['metadata']['article_title_revision'], frozen)
        for action in before:
            self.assertEqual(model_runtime.request_fingerprint(action, before[action]),
                             model_runtime.request_fingerprint(action, after[action]))

    def test_initial_p0_and_article_commissions_save_title_input_mode(self):
        for kind in ('p0', 'article'):
            self.assertEqual(wf.make_state('new-'+kind, kind)['metadata']['title_input_mode'], requirements.TITLE_INPUT_MODE)
        job = self.job('p0')
        self.finish(job, p0=True)
        before = (job/'production/p0_finalized.json').read_bytes()
        for action in ('p0_titles', 'p0_title_review'):
            self.assertIn('当前写作要求', self.prompts[action])
            self.assertIn(self.body.split('\n', 1)[1], self.prompts[action])
        self.assertEqual((job/'production/p0_finalized.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
