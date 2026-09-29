"""Mandatory P0 stage, source binding and legacy isolation; entirely offline."""
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.tests_v411 import test_controller_runtime_v4114 as integration
from scripts.tests_v411 import test_manuscript_revision as revision_fixture
from shared import editorial_contracts as contracts, p0_style, manuscript_revision
from shared.host_tools import HostTools, ToolError
wf = integration.wf


class P0StyleControllerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = integration.ControllerRuntimeIntegration(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.examples = []
        self.calls = []
        self.failure = None
        self.styled = self.fixture.draft.replace('初稿特征。', '修饰稿的具体开篇。')
        self.addCleanup(patch.stopall)
        patch.object(p0_style, 'job_examples', side_effect=lambda *a, **kw: self.examples).start()
        patch.object(p0_style, 'freeze_examples', side_effect=lambda *a, **kw: self.examples).start()
        patch.object(wf, 'ensure_action', side_effect=self.action).start()

    def job(self, *, legacy=False, prefix='p0', route='workflow'):
        job = self.fixture.job(prefix)
        state = wf.load_state(job)
        state['selected_example_route'] = route
        if prefix == 'p0' and not legacy:
            state['metadata']['p0_style_contract'] = p0_style.LEGACY_STYLE_CONTRACT_VERSION
        wf.save_state(job, state)
        if prefix == 'p0':
            for ident in p0_style.EXAMPLE_IDS:
                path = job/'inputs'/f'{ident}.md'; text = f'{ident}离线完整例文首段。\n\n例文中段说明真实方法。\n\n例文末段。'
                path.write_text(text)
                self.examples.append({'id':ident, 'title':ident, 'text':text, 'path':str(path.resolve()), 'sha256':p0_style.sha256(text), 'guide':'只借鉴写法。', 'guide_sha256':p0_style.sha256('只借鉴写法。')})
        return job

    def action(self, job, action, prompt, *, fixture_builder):
        self.calls.append(action)
        if action == self.failure:
            raise integration.runtime.ProviderActionError('invalid_result_contract', 'offline failure', action=action)
        if action.endswith('_draft'):
            result = {'article_markdown':self.fixture.draft, 'requires_blueprint_reconfirmation':False, 'reconfirmation_reason':''}
        elif action.endswith('_edit'):
            result = p0_style.fixture_style_result(self.fixture.draft)
        elif action == 'p0_style':
            result = {**p0_style.fixture_style_result(self.styled), 'edit_status':'revised', 'editorial_notes':['将身份式开篇改为具体业务问题。']}
        elif action.endswith('_finalize'):
            p0 = action.startswith('p0_')
            candidate = contracts.prepare_finalize_input(wf,job,p0=p0)['candidate_markdown']
            result = {'outcome':'accepted','article_markdown':candidate,'editorial_notes':[],'reason':''}
        else:
            result = fixture_builder()
        return wf.validate_action_result(job, action, result)

    def step(self, job, *, p0=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return wf.run_production(job,p0=p0)

    def test_new_jobs_activate_only_p0_and_keep_runtime_schema(self):
        for kind in ('p0','article','reference_pack'):
            state=wf.make_state('synthetic',kind)
            self.assertEqual(p0_style.is_enabled(state),kind=='p0')
            self.assertEqual(state['workflow_version'],'4.11')

    def test_workflow_route_cannot_skip_style_and_final_source_is_styled(self):
        job=self.job()
        for _ in range(7): self.step(job)
        self.assertEqual(self.calls,['p0_draft','p0_edit','p0_style','p0_finalize','p0_titles','p0_title_review'])
        self.assertEqual(wf.read_json(job/'production/p0_finalized.json')['article_markdown'],self.styled)
        self.assertEqual(wf.read_json(job/'production/p0_final_source.json')['candidate_source'],'deepseek_style')
        self.assertFalse(wf.read_json(job/'production/p0_style_diff.json')['identical'])
        state=wf.load_state(job)
        body=Path(state['metadata']['pending_p0_delivery']['markdown']).read_text()
        self.assertEqual(body,wf.title_publication.body_only(self.styled))

    def test_legacy_unfinished_p0_and_question_keep_original_chain(self):
        for prefix in ('p0','article'):
            job=self.job(legacy=True,prefix=prefix)
            self.calls=[]
            for _ in range(6):self.step(job,p0=prefix=='p0')
            self.assertEqual(self.calls,[prefix+'_'+stage for stage in ('draft','edit','finalize','titles','title_review')])
            self.assertFalse((job/'production'/f'{prefix}_styled.json').exists())

    def test_manual_step_forward_is_rewound_to_missing_style(self):
        job=self.job();self.step(job);self.step(job)
        state=wf.load_state(job);state['flags']['p0_production_step']='finalize';wf.save_state(job,state)
        self.step(job)
        self.assertEqual(wf.load_state(job)['flags']['p0_production_step'],'style')
        self.assertNotIn('p0_finalize',self.calls)

    def test_style_failure_never_falls_back_or_delivers(self):
        job=self.job();self.step(job);self.step(job);self.failure='p0_style'
        with self.assertRaises(integration.runtime.ProviderActionError):self.step(job)
        self.assertEqual(wf.load_state(job)['flags']['p0_production_step'],'style')
        self.assertNotIn('p0_finalize',self.calls)
        self.assertFalse((job/'production/p0_styled.json').exists())
        with self.assertRaises(contracts.EditorialContractError):contracts.prepare_finalize_input(wf,job,p0=True)

    def test_new_p0_e8_format_failure_also_stops_before_style(self):
        job=self.job();self.step(job);self.failure='p0_edit'
        with self.assertRaises(integration.runtime.ProviderActionError):self.step(job)
        self.assertEqual(wf.load_state(job)['flags']['p0_production_step'],'edit')
        self.assertFalse((job/'production/p0_edit_failure.json').exists())
        self.assertNotIn('p0_style',self.calls)

    def test_tampered_style_and_e8_invalidate_right_stage(self):
        job=self.job()
        for _ in range(3):self.step(job)
        path=job/'production/p0_styled.json';value=wf.read_json(path);value['article_markdown']+='\n被篡改';wf.atomic_json(path,value)
        self.step(job)
        self.assertEqual(wf.load_state(job)['flags']['p0_production_step'],'style')
        self.step(job)
        self.assertEqual(wf.read_json(path)['article_markdown'],self.styled)
        path=job/'production/p0_edited.json';value=wf.read_json(path);value['article_markdown']+='\n不可信';wf.atomic_json(path,value)
        self.step(job)
        self.assertEqual(wf.load_state(job)['flags']['p0_production_step'],'edit')
        self.step(job)
        self.assertFalse((job/'production/p0_styled.json').exists())
        self.assertTrue(list((job/'production/history').rglob('p0_styled.json')))

    def test_host_must_read_styled_and_both_examples_on_workflow_route(self):
        job=self.job()
        for _ in range(3):self.step(job)
        tools=HostTools(wf.ROOT,job,'p0_finalize')
        required=[tools.artifacts[ident] for ident in tools._required]
        self.assertTrue(any(row['path']=='production/p0_styled.json' for row in required))
        self.assertEqual(sum(row['category']=='example' for row in required),2)
        with self.assertRaises(ToolError):tools.validate_complete_reads()
        tools.record_inline_inputs([{'role':'user','content':wf.writing_context.prompt_finalize(wf,job,p0=True)}])
        tools.validate_complete_reads()

    def test_failed_new_job_freeze_leaves_empty_retryable_directory(self):
        job=self.fixture.base/'retry-new-job'
        def fail_after_partial_write(package, temporary):
            asset=temporary/'inputs/p0_style_examples/partial.md'
            asset.parent.mkdir(parents=True)
            asset.write_text('尚未冻结完整例文')
            raise contracts.EditorialContractError('fetch_failed','离线模拟来源不可用')
        with patch.object(p0_style,'freeze_examples',side_effect=fail_after_partial_write):
            with self.assertRaises(contracts.EditorialContractError):
                wf.ensure_new_job(job,'p0',offline=True)
        self.assertTrue(job.is_dir())
        self.assertEqual(list(job.iterdir()),[])
        self.assertEqual(list(job.parent.glob('.frontmind-init-*')),[])
        with patch.object(p0_style,'freeze_examples',return_value=[]) as freeze:
            returned=wf.ensure_new_job(job,'p0',offline=True)
        self.assertEqual(returned,job.resolve())
        self.assertTrue(p0_style.is_enabled(wf.load_state(returned)))
        self.assertEqual(freeze.call_count,1)
        self.assertEqual(list(job.parent.glob('.frontmind-init-*')),[])

    def test_supplemental_example_page_never_offers_to_remove_fixed_pair(self):
        job=self.job()
        state=wf.load_state(job);state['metadata']['example_acquisition_errors']=['补充网址未能取得'];wf.save_state(job,state)
        with contextlib.redirect_stdout(io.StringIO()):
            wf.render_example_confirmation(job,p0=True)
        page=Path(wf.load_state(job)['current_pause']['review_markdown_path']).read_text()
        self.assertIn('固定例文：星源智、港隽，始终保留',page)
        self.assertIn('不采用补充例文（保留固定两篇）',page)
        self.assertIn('或选择仅保留固定两篇例文',page)
        self.assertNotIn('不采用例文文风',page)
        self.assertNotIn('选择默认写作规范',page)

    def test_blueprint_discovery_uses_fixed_assets_without_provider_or_pause(self):
        job=self.job()
        self.assertIsNone(wf.run_p0_example_discovery(job))
        self.assertEqual(wf.load_state(job)['status'],'running_p0_blueprint')
        self.assertEqual(self.calls,[])


class P0StyleRevisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=revision_fixture.ManuscriptRevisionTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(patch.stopall)
        patch.object(p0_style,'freeze_examples',return_value=[]).start()
        patch.object(p0_style,'job_examples',return_value=[]).start()

    def test_old_completed_local_revision_keeps_original_chain_and_forwards_edits(self):
        job=self.fixture.completed('p0');self.fixture.start(job)
        self.assertFalse(p0_style.is_enabled(wf.load_state(job)))
        frozen=manuscript_revision.current_revision(wf,job,p0=True)
        prompt=wf.writing_context.prompt_edit(wf,job,p0=True)
        self.assertIn(self.fixture.request.read_text(),prompt)
        self.assertIn(frozen['base_markdown'],prompt)
        self.assertNotIn('p0_style',wf.load_state(job)['flags']['model_action_epochs'])

    def test_styled_completed_chain_requires_style_provenance_and_source(self):
        job=self.fixture.completed('p0')
        state=wf.load_state(job);state['metadata']['p0_style_contract']=p0_style.LEGACY_STYLE_CONTRACT_VERSION;wf.save_state(job,state)
        wf.atomic_json(job/'production/p0_styled.json',p0_style.fixture_style_result(self.fixture.fixture.draft))
        source=wf.read_json(job/'production/p0_final_source.json');source['candidate_source']='deepseek_style';wf.atomic_json(job/'production/p0_final_source.json',source)
        result=manuscript_revision.validate_completed_manuscript(wf,job,p0=True)
        self.assertIn('p0_style',[row['action'] for row in result['source']['actions']])
        (job/'production/p0_styled.json').unlink()
        with self.assertRaises(ValueError):manuscript_revision.validate_completed_manuscript(wf,job,p0=True)

    def test_old_completed_title_only_does_not_activate_style(self):
        job=self.fixture.completed('p0')
        with patch.object(wf,'drive',return_value=0):
            wf.continue_workflow(self.fixture.args(job,'--title-edits',str(self.fixture.request)))
        self.assertFalse(p0_style.is_enabled(wf.load_state(job)))


if __name__=='__main__':unittest.main()
