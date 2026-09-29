"""A newly commissioned edit works from the manuscript, not its obsolete plan."""
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_editorial_mission_final13 as mission
from shared import manuscript_revision, model_runtime, writing_requirements as requirements


class ManuscriptOutlineInputTests(unittest.TestCase):
    setUp = mission.EditorialMissionTests.setUp
    job = mission.EditorialMissionTests.job
    step = mission.EditorialMissionTests.step
    until = mission.EditorialMissionTests.until
    finish = mission.EditorialMissionTests.finish

    def prepare_edit(self):
        job = self.job()
        path = job/'blueprints/article_blueprint.json'
        bp = wf.read_json(path)
        bp.update(opening='OBSOLETE_OPENING', sections=[{'heading':'OBSOLETE_SECTION', 'task':'OBSOLETE_TASK'}],
                  ending='OBSOLETE_ENDING', example_use='OBSOLETE_EXAMPLE_USE',
                  estimated_length='3000个正文可见字符', writing_material_markdown='SPECIFIC_FACTS',
                  material_adjustments=['EXISTING_FACT_SCOPE'])
        wf.atomic_json(path, bp)
        self.finish(job)
        request = self.root/'revision.md'
        request.write_text('NEW_EDIT_REQUEST：合并两个重复章节，按现有完整文章展开。')
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(wf.load_state(job)['revision']),
                                      '--manuscript-edits', str(request)])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        return job

    def test_new_revision_keeps_actual_body_requirements_and_facts_without_old_layout(self):
        job = self.prepare_edit()
        revision = manuscript_revision.current_revision(wf, job, p0=False)
        self.assertEqual(revision['outline_input_mode'], requirements.MANUSCRIPT_OUTLINE_INPUT_MODE)
        self.assertEqual(revision['base_markdown'], self.body)
        self.needs_revision = True
        self.finish(job)
        for action in ('article_edit', 'article_finalize', 'article_repair'):
            prompt = self.prompts[action]
            self.assertNotIn('OBSOLETE_', prompt)
            for text in ('NEW_EDIT_REQUEST', 'SPECIFIC_FACTS', 'EXISTING_FACT_SCOPE', '3000个正文可见字符', self.body):
                self.assertIn(text, prompt, (action, text))
        self.assertEqual(self.actions[-5:], ['article_edit','article_finalize','article_repair','article_titles','article_title_review'])

    def test_historical_frozen_revision_retry_preserves_outline_and_request_identity(self):
        job = self.prepare_edit()
        state = wf.load_state(job)
        pointer = state['metadata']['article_manuscript_revision']
        path = job/pointer['path']
        frozen = wf.read_json(path)
        frozen.pop('outline_input_mode')  # exact shape of a pre-change frozen input
        wf.atomic_json(path, frozen)
        pointer['sha256'] = manuscript_revision.file_hash(path)
        wf.save_state(job, state)
        before = wf.prompt_edit(job, p0=False)
        identity = model_runtime.request_fingerprint('article_edit', before)
        for text in ('OBSOLETE_OPENING','OBSOLETE_SECTION','OBSOLETE_TASK','OBSOLETE_ENDING','OBSOLETE_EXAMPLE_USE'):
            self.assertIn(text, before)
        state['pending_action'] = {'action':'article_edit', 'error':{'code':'interrupted_attempt'}}
        wf.save_state(job, state)
        args = wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(state['revision']),'--retry-current-action'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        self.assertEqual(wf.prompt_edit(job, p0=False), before)
        self.assertEqual(model_runtime.request_fingerprint('article_edit', before), identity)
        self.assertNotIn('outline_input_mode', manuscript_revision.current_revision(wf,job,p0=False))

    def test_initial_commission_still_receives_outline(self):
        job = self.job()
        self.assertIsNone(manuscript_revision.current_revision(wf,job,p0=False))
        prompt = wf.prompt_article(job,p0=False)
        self.assertIn('可调整的内容构思',prompt)
        self.assertIn('直接介绍主题',prompt)


if __name__ == '__main__':
    unittest.main()
