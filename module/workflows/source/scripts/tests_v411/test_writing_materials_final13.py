"""Explicit current facts persist through real edit/title controller transitions."""
import json
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_editorial_mission_final13 as mission
from shared import manuscript_revision, model_runtime, writing_context, writing_materials


class WritingMaterialsTests(unittest.TestCase):
    setUp = mission.EditorialMissionTests.setUp
    job = mission.EditorialMissionTests.job
    step = mission.EditorialMissionTests.step
    until = mission.EditorialMissionTests.until
    finish = mission.EditorialMissionTests.finish

    def revised(self, job, path=None, flag='--manuscript-edits'):
        request = self.root/'request.md'; request.write_text('本轮组织完整文章，不重复背景。')
        argv = ['continue','--job-dir',str(job),'--revision',str(wf.load_state(job)['revision']),flag,str(request)]
        if path is not None:
            argv += ['--writing-materials',str(path)]
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(wf.parser().parse_args(argv))

    def fact_file(self):
        path = self.root/'facts.json'
        path.write_text(json.dumps({'writing_material_markdown':'CURRENT_FULL_FACTS：甲公司新增乙业务。',
            'material_adjustments':['CURRENT_USE_NOTE：业务归属甲公司。'],
            'writing_material_sources':[{'source_ref':'inputs/source.md','use':'CURRENT_LOOKUP'}]},ensure_ascii=False))
        return path

    def finished_job(self, kind='article'):
        job = self.job(kind)
        bp_path = job/f'blueprints/{kind}_blueprint.json'
        bp = wf.read_json(bp_path)
        bp.update(writing_material_markdown='OLD_BLUEPRINT_FACTS',material_adjustments=['OLD_BLUEPRINT_NOTE'],
                  writing_material_sources=[{'source_ref':'old.md','use':'OLD_BLUEPRINT_LOOKUP'}])
        wf.atomic_json(bp_path,bp)
        self.finish(job,p0=kind=='p0')
        return job

    def test_fact_file_is_frozen_then_used_by_e8_review_and_single_repair(self):
        job = self.finished_job(); source = self.fact_file()
        self.revised(job,source)
        frozen = manuscript_revision.current_revision(wf,job,p0=False)
        self.assertEqual(frozen['writing_materials']['contract'], writing_materials.CONTRACT)
        source.write_text('File changed after explicit revision, not a new commission.')
        self.needs_revision = True
        self.finish(job)
        for action in ('article_edit','article_finalize','article_repair'):
            prompt = self.prompts[action]
            self.assertIn('CURRENT_FULL_FACTS',prompt)
            self.assertIn('CURRENT_USE_NOTE',prompt)
            self.assertNotIn('OLD_BLUEPRINT_',prompt)
            self.assertNotIn('File changed',prompt)
        self.assertIn('CURRENT_LOOKUP',self.prompts['article_finalize'])
        self.assertNotIn('CURRENT_LOOKUP',self.prompts['article_edit'])
        self.assertNotIn('CURRENT_LOOKUP',self.prompts['article_repair'])
        self.assertEqual(self.actions[-5:],['article_edit','article_finalize','article_repair','article_titles','article_title_review'])

    def test_title_edit_then_new_manuscript_edit_inherits_until_explicit_replace(self):
        job = self.finished_job(); self.revised(job,self.fact_file()); self.finish(job)
        original = manuscript_revision.current_revision(wf,job,p0=False)['writing_materials']
        self.revised(job,flag='--title-edits'); self.finish(job)
        self.assertEqual(manuscript_revision.current_revision(wf,job,p0=False)['writing_materials'],original)
        self.revised(job); self.finish(job)
        self.assertEqual(manuscript_revision.current_revision(wf,job,p0=False)['writing_materials'],original)
        self.assertIn('CURRENT_FULL_FACTS',self.prompts['article_edit'])
        folder=self.root/'replacement';folder.mkdir();(folder/'writing_materials.md').write_text('REPLACED_FULL_FACTS')
        self.revised(job,folder);self.finish(job)
        prompt=self.prompts['article_edit']
        self.assertIn('REPLACED_FULL_FACTS',prompt)
        self.assertNotIn('CURRENT_FULL_FACTS',prompt)
        self.assertNotIn('CURRENT_USE_NOTE',prompt)

    def test_historical_edit_without_bundle_preserves_request_on_retry(self):
        job = self.finished_job();self.revised(job)
        self.assertNotIn('writing_materials',manuscript_revision.current_revision(wf,job,p0=False))
        before=wf.prompt_edit(job,p0=False);identity=model_runtime.request_fingerprint('article_edit',before)
        state=wf.load_state(job);state['pending_action']={'action':'article_edit','error':{'code':'interrupted_attempt'}};wf.save_state(job,state)
        args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(state['revision']),'--retry-current-action'])
        with patch.object(wf,'drive',return_value=0):wf.continue_workflow(args)
        self.assertEqual(wf.prompt_edit(job,p0=False),before)
        self.assertEqual(model_runtime.request_fingerprint('article_edit',before),identity)
        self.assertIn('OLD_BLUEPRINT_FACTS',before)

    def test_in_progress_request_cannot_receive_new_materials(self):
        job=self.job()
        before=(job/'job_state.json').read_bytes()
        with self.assertRaises(wf.WorkflowError):self.revised(job,self.fact_file())
        self.assertEqual((job/'job_state.json').read_bytes(),before)

    def test_new_blueprint_ends_local_fact_selection(self):
        job=self.finished_job();self.revised(job,self.fact_file());self.finish(job)
        args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(wf.load_state(job)['revision']),
                                    '--blueprint-edits','重新构思本篇。'])
        with patch.object(wf,'drive',return_value=0):wf.continue_workflow(args)
        self.assertIsNone(manuscript_revision.current_revision(wf,job,p0=False))

    def test_invalid_or_title_only_input_does_not_mutate_job(self):
        job=self.finished_job();before=(job/'job_state.json').read_bytes()
        with self.assertRaises(wf.WorkflowError):self.revised(job,self.fact_file(),flag='--title-edits')
        self.assertEqual((job/'job_state.json').read_bytes(),before)
        invalid=self.root/'invalid.md';invalid.write_text(' ')
        with self.assertRaises(wf.WorkflowError):self.revised(job,invalid)
        self.assertEqual((job/'job_state.json').read_bytes(),before)
        folder=self.root/'ambiguous';folder.mkdir();(folder/'writing_materials.md').write_text('facts');(folder/'writing_materials.json').write_text('{}')
        with self.assertRaises(ValueError):writing_materials.read_input(folder)


if __name__ == '__main__':
    unittest.main()
