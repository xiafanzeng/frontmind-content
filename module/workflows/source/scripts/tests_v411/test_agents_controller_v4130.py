"""Current host adapter in real controller orchestration, with fake model output.
Retains original author stream and DOCX stub; no live/quality assertion.
"""
import unittest
from unittest.mock import patch
from shared import model_runtime as rt
from scripts.tests_v411.test_model_runtime import FakeTools
from scripts.tests_v411.agents_sdk_fake import bundle

class AgentsControllerTests(unittest.TestCase):
    def route(self,prefix):
        # Import at execution, not collection: the legacy fixture registers a
        # named controller module and pytest may collect it under another name.
        from scripts.tests_v411 import test_controller_runtime_v4114 as fixture
        current=rt.profile_for
        f=fixture.ControllerRuntimeIntegration();f.setUp();self.addCleanup(f.doCleanups)
        wf=fixture.wf
        override=patch.object(rt,'profile_for',side_effect=current);override.start();self.addCleanup(override.stop)
        engines=[]
        def execute(package,job,action,prompt,validator,**kwargs):
            if action in rt.DEEPSEEK_ACTIONS:return f.offline_run(package,job,action,prompt,validator,**kwargs)
            if action.endswith('_finalize'):
                value={'outcome':'revised','article_markdown':f.final,'editorial_notes':['合成模型编辑'],'reason':''}
            else:
                titles=wf.validate_title_map(wf.read_json(job/'production'/f'{prefix}_titles.json'),p0=prefix=='p0')
                value={'outcome':'revised','candidates':[{'title':t['title_text'],'angle':'业务阅读入口'} for t in titles['options']],
                       'canonical_title_id':'title_13' if prefix=='p0' else 'title_04','title_notes':['合成模型标题'],'reason':''}
            sdk,e=bundle(result=value);engines.append(e)
            return rt.run_action(package,job,action,prompt,validator,transport=sdk,offline=True,host_tools=FakeTools(),**kwargs)
        job=f.job(prefix)
        with patch.object(wf,'run_action',side_effect=execute):
            for _ in range(6):f.run_step(job,prefix=='p0')
        self.assertEqual((job/'deliverables'/f'{prefix}.md').read_text(),wf.title_publication.body_only(f.final))
        for stage in ('finalize','title_review'):
            rec=rt.action_record(job,f'{prefix}_{stage}');self.assertEqual(rec['status'],'succeeded');self.assertEqual(rec['requested_configuration']['wire_api'],'openai_agents_sdk')
        self.assertEqual(len(engines),2)
        for stage in ('draft','edit','titles'):self.assertEqual(rt.action_record(job,f'{prefix}_{stage}')['requested_configuration']['model'],'deepseek-v4-pro')
    def test_p0_existing_contract_sdk_review_and_title(self):self.route('p0')
    def test_question_sdk_review_and_title(self):self.route('article')

class AgentsFourFieldReviewTests(unittest.TestCase):
    def test_current_prose_acceptance_keeps_exact_candidate_and_four_fields(self):
        from scripts.tests_v411.test_prose_only_v4126 import ProseOnlyTests,ROOT
        from scripts import frontmind_workflow as wf
        from shared import brand_stage as bs,brand_references as br
        f=ProseOnlyTests();f.setUp();self.addCleanup(f.doCleanups);f.put_style();br.job_examples(ROOT,f.job,freeze=True)
        value=f.final_value();sdk,e=bundle(result=value)
        prompt=bs.finalize_prompt(wf,f.job);validator=lambda v:wf.validate_action_result(f.job,'p0_finalize',v)
        got=rt.run_action(ROOT,f.job,'p0_finalize',prompt,validator,host_tools=FakeTools(),transport=sdk,offline=True)
        self.assertEqual(got,value);self.assertEqual(len(got),4)
        before=e.calls;rt.run_action(ROOT,f.job,'p0_finalize',prompt,validator,host_tools=FakeTools(),transport=sdk,offline=True);self.assertEqual(e.calls,before)
    def test_pending_legacy_action_is_not_silently_replaced(self):
        import tempfile
        from pathlib import Path
        from scripts.tests_v411.test_managed_runtime_v4123 import ManagedServer
        from scripts.tests_v411.test_model_runtime import valid
        with tempfile.TemporaryDirectory() as tmp:
            pkg=Path(tmp)/'pkg';job=Path(tmp)/'job';pkg.mkdir();job.mkdir()
            server=ManagedServer(fault='resolution_ack_lost')
            with rt.legacy_managed_routes():
                with self.assertRaises(rt.ProviderActionError):rt.run_action(pkg,job,'p0_blueprint','same task',valid,host_tools=FakeTools(),transport=server,offline=True)
            n=len(server.calls)
            with self.assertRaises(rt.ProviderActionError):rt.run_action(pkg,job,'p0_blueprint','same task',valid,host_tools=FakeTools(),transport=server,offline=True)
            self.assertEqual(n,len(server.calls))
            got=rt.run_action(pkg,job,'p0_blueprint','same task',valid,retry=True,host_tools=FakeTools(),transport=server,offline=True)
            self.assertEqual(got,{'ok':True});self.assertEqual(rt.action_record(job,'p0_blueprint')['requested_configuration']['wire_api'],'zhipu_managed_agents')

class RealHostToolRestoreTests(unittest.TestCase):
    def test_inline_full_reads_are_recomputed_on_actual_hosttools_restore(self):
        from scripts.tests_v411.test_prose_only_v4126 import ProseOnlyTests,ROOT
        from scripts import frontmind_workflow as wf
        from shared import brand_stage as bs,brand_references as br
        from shared.host_tools import HostTools
        f=ProseOnlyTests();f.setUp();self.addCleanup(f.doCleanups);f.put_style();br.job_examples(ROOT,f.job,freeze=True)
        prompt=bs.finalize_prompt(wf,f.job);value=f.final_value()
        sdk,e=bundle(result=value,fault='unread')  # Complete body is already in actual prompt.
        validator=lambda v:wf.validate_action_result(f.job,'p0_finalize',v)
        first=rt.run_action(ROOT,f.job,'p0_finalize',prompt,validator,host_tools=HostTools(ROOT,f.job,'p0_finalize'),transport=sdk,offline=True)
        calls=e.calls
        again=rt.run_action(ROOT,f.job,'p0_finalize',prompt,validator,host_tools=HostTools(ROOT,f.job,'p0_finalize'),transport=sdk,offline=True)
        self.assertEqual(first,again);self.assertEqual(e.calls,calls)
