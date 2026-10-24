"""原 Job 阶段接续的断网回归；不调用模型、不生成业务任务。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf


class SessionPhasesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name)
        self.pack = self.job / 'deliverables/pack.zip'
        self.pack.parent.mkdir()
        self.pack.write_bytes(b'offline-test-pack')
        self.state = wf.make_state('same-job-id', 'reference_pack')
        self.state.update(status='positioning_ready', stage='reference_pack', revision=7,
                          reference_pack={'pack_id':'pack-1', 'pack_version':1})
        self.state['metadata']['reference_pack_delivery'] = {'pack_path':str(self.pack), 'pack_version':2}
        self.state['decisions']['confirmed_positioning'] = {'unchanged':True}
        self.state['flags']['offline_fixture'] = True
        wf.save_state(self.job, self.state)
        self.before = wf.state_path(self.job).read_bytes()

    def invoke(self, target='p0', revision=7, after=None):
        args = wf.parser().parse_args(['continue','--job-dir',str(self.job),'--revision',str(revision),'--next-task',target])
        def bind(job, source):
            state = wf.load_state(job)
            state['reference_pack'] = {'pack_id':'pack-1','pack_version':2,'path':str(source),
                                       'readiness':{'positioning_ready':True,'p0_ready':target=='article'}}
            wf.save_state(job, state)
        with patch.object(wf,'validate_reference_pack',return_value={'status':'pass','readiness':{'positioning_ready':True,'p0_ready':True}}), \
             patch.object(wf,'reference_pack_root',return_value={'pack_id':'pack-1','pack_version':2}), \
             patch.object(wf.p0_style,'freeze_examples') as freeze, \
             patch.object(wf,'bind_reference_pack',side_effect=bind), \
             patch.object(wf,'after_reference_bound',side_effect=after or (lambda _: 0)), \
             patch.object(wf,'ensure_new_job',side_effect=AssertionError('禁止新建 Job')):
            result = wf.continue_workflow(args)
            return result, freeze.call_count

    def test_pack_continues_to_p0_in_same_job_and_preserves_history(self):
        self.assertEqual(self.invoke(), (0,1))
        state = wf.load_state(self.job)
        self.assertEqual((state['job_id'],state['job_kind'],state['revision']),('same-job-id','p0',8))
        self.assertEqual(state['created_at'], self.state['created_at'])
        self.assertEqual(state['decisions'], {})
        self.assertEqual(self.pack.read_bytes(), b'offline-test-pack')
        history = state['metadata']['completed_phases']
        old = json.loads((self.job/history[0]['state_path']).read_text(encoding='utf-8'))
        self.assertEqual(old, self.state)
        self.assertEqual(state['metadata']['title_strategy'], wf.make_state('x','p0')['metadata']['title_strategy'])

    def test_completed_p0_continues_to_article_without_new_identity(self):
        state = copy.deepcopy(self.state)
        state.update(job_kind='p0', status='p0_ready')
        wf.save_state(self.job,state)
        self.assertEqual(self.invoke('article'), (0,0))
        after = wf.load_state(self.job)
        self.assertEqual((after['job_id'],after['job_kind']),('same-job-id','article'))
        self.assertIn('article_pool_policy',after['metadata'])
        self.assertEqual(after['flags'],{'offline_fixture':True})

    def test_stale_revision_does_not_change_state(self):
        with self.assertRaises(wf.WorkflowError): self.invoke(revision=6)
        self.assertEqual(wf.state_path(self.job).read_bytes(),self.before)

    def test_cannot_skip_p0_or_repeat_transition(self):
        with self.assertRaises(wf.WorkflowError): self.invoke('article')
        self.assertEqual(wf.state_path(self.job).read_bytes(),self.before)
        self.invoke()
        after = wf.state_path(self.job).read_bytes()
        with self.assertRaises(wf.WorkflowError): self.invoke(revision=8)
        self.assertEqual(wf.state_path(self.job).read_bytes(),after)

    def test_active_pause_blocks_transition(self):
        state = copy.deepcopy(self.state)
        state['current_pause']={'must_stop':True}
        wf.save_state(self.job,state)
        with self.assertRaises(wf.WorkflowError): self.invoke()
        self.assertEqual(wf.load_state(self.job),state)

    def test_rejects_foreign_pack_without_overwriting_history(self):
        args = wf.parser().parse_args(['continue','--job-dir',str(self.job),'--revision','7','--next-task','p0'])
        with patch.object(wf,'validate_reference_pack',return_value={'status':'pass','readiness':{'positioning_ready':True}}), \
             patch.object(wf,'reference_pack_root',return_value={'pack_id':'another-pack','pack_version':2}):
            with self.assertRaises(wf.WorkflowError): wf.continue_workflow(args)
        self.assertEqual(wf.state_path(self.job).read_bytes(),self.before)
        self.assertFalse((self.job/'working/phase_history').exists())

    def test_does_not_accept_implicit_confirmation_with_transition(self):
        args = wf.parser().parse_args(['continue','--job-dir',str(self.job),'--revision','7','--next-task','p0','--accept-p0-blueprint'])
        with self.assertRaises(wf.WorkflowError): wf.continue_workflow(args)
        self.assertEqual(wf.state_path(self.job).read_bytes(),self.before)


class SessionPhasesOfflineFlowTests(unittest.TestCase):
    def test_one_job_pack_p0_article_reaches_original_pauses(self):
        # 原 CLI 与合成离线响应，实际校验、绑定、写回 Pack 和生成确认页。
        # 不使用模型或生产文件，不把合成正文当作内容质量验收。
        from scripts.tests_v411 import test_workflow_v411 as flow
        with tempfile.TemporaryDirectory(prefix="frontmind-local-phase-flow-") as directory:
            job = Path(directory)/"one-job"
            manifest = json.loads((flow.FIXTURE/'manifest.json').read_text(encoding='utf-8'))
            flow.run_cli('reference-pack','create','--brand',manifest['brand'],'--input',str(flow.FIXTURE/'brand_material.md'),
                         '--job-dir',str(job),'--offline-fixture')
            flow.confirm_competitors(job)
            flow.resume(job,'--confirm-core-positioning')
            original = wf.load_state(job)
            self.assertEqual(original['status'],'positioning_ready')
            flow.resume(job,'--next-task','p0')
            self.assertEqual(wf.load_state(job)['status'],'awaiting_p0_route')
            flow.resume(job,'--p0-route','create')
            flow.resume(job,'--accept-p0-example-route','workflow')
            self.assertEqual(wf.load_state(job)['status'],'awaiting_p0_blueprint_confirmation')
            flow.resume(job,'--accept-p0-blueprint')
            self.assertEqual(wf.load_state(job)['status'],'p0_ready')
            flow.resume(job,'--next-task','article')
            final = wf.load_state(job)
            self.assertIn(final['status'],{'awaiting_question_selection','awaiting_question_research_inputs'})
            self.assertEqual(final['job_id'],original['job_id'])
            self.assertEqual(final['created_at'],original['created_at'])
            self.assertEqual([row['kind'] for row in final['metadata']['completed_phases']],['reference_pack','p0'])
            self.assertEqual(len(list(Path(directory).glob('*/job_state.json'))),1)
