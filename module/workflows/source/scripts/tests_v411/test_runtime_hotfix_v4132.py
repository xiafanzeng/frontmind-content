"""Local regression fixtures, not live model or gateway evidence."""
from __future__ import annotations
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shared import agents_runtime as ar, model_runtime as rt
from shared.host_tools import HostTools, ToolError, _is_intake_answer_copy
from scripts.tests_v411.test_model_runtime import FakeTools, valid
from scripts.tests_v411.agents_sdk_fake import bundle


class JournalSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.attempt=Path(self.tmp.name)/'attempt';self.attempt.mkdir()
        self.record={'requested_configuration':{'max_tool_calls':1}}
        rt._atomic(self.attempt/'request_plan.json',{'instructions':'task','input':[]})

    def prepare(self,name='read_material',args=None,status='started'):
        args=args or {'artifact_id':'one'};call_id='call_exact_1'
        rt._atomic(self.attempt/'model_0001_response.json',{'output':[
            {'type':'function_call','name':name,'call_id':call_id,'arguments':json.dumps(args)}]})
        source=ar._source_call(self.attempt,call_id,name,args)
        path=self.attempt/('tool_'+hashlib.sha256(call_id.encode()).hexdigest()+'.json')
        row={'name':name,'arguments':args,'call_id':call_id,'signature':ar.digest({'name':name,'arguments':args,'call_id':call_id}),
             'status':status,'source':source,'started_at':'2026-09-01T00:00:00Z'}
        rt._atomic(path,row)
        return path,row

    def test_all_three_local_read_tools_can_replay_started_markers(self):
        class LocalTools(FakeTools):
            def __init__(self):super().__init__();self.calls=[]
            def execute(self,name,args):self.calls.append(name);self.read=True;return {'text':'fresh read'}
        for name in sorted(ar.READONLY_REPLAY_TOOLS):
            with self.subTest(name=name):
                path,row=self.prepare(name);tools=LocalTools()
                output=asyncio.run(ar.ToolJournal(self.attempt,self.record,tools,valid,[]).invoke(name,row['call_id'],json.dumps(row['arguments'])))
                after=rt._read_json(path)
                self.assertEqual(tools.calls,[name]);self.assertEqual(json.loads(output),{'text':'fresh read'})
                self.assertEqual(after['status'],'completed');self.assertEqual(after['readonly_replay_count'],1)
                self.assertEqual(after['readonly_replay_history'][0]['started_at'],row['started_at'])

    def test_external_write_and_submit_started_markers_do_not_reexecute(self):
        for name in ['web_read','web_search','extract_document','ocr','submit_result','unknown_tool']:
            with self.subTest(name=name):
                path,row=self.prepare(name);before=path.read_bytes();tools=FakeTools()
                with patch.object(tools,'execute',side_effect=AssertionError('must not execute')) as run:
                    with self.assertRaises(rt.ProviderActionError) as exc:
                        asyncio.run(ar.ToolJournal(self.attempt,self.record,tools,valid,[]).invoke(name,row['call_id'],json.dumps(row['arguments'])))
                self.assertEqual(exc.exception.code,'tool_outcome_unknown');run.assert_not_called()
                self.assertEqual(path.read_bytes(),before)

    def test_non_started_incomplete_status_is_not_a_readonly_replay(self):
        path,row=self.prepare(status='corrupt')
        with self.assertRaises(rt.ProviderActionError) as exc:
            asyncio.run(ar.ToolJournal(self.attempt,self.record,FakeTools(),valid,[]).invoke('read_material',row['call_id'],json.dumps(row['arguments'])))
        self.assertEqual(exc.exception.code,'tool_outcome_unknown')

    def test_same_call_id_with_different_arguments_is_rejected(self):
        path,row=self.prepare();changed={'artifact_id':'other'}
        rt._atomic(self.attempt/'model_0001_response.json',{'output':[
            {'type':'function_call','name':'read_material','call_id':row['call_id'],'arguments':json.dumps(changed)}]})
        with self.assertRaises(rt.ProviderActionError) as exc:
            asyncio.run(ar.ToolJournal(self.attempt,self.record,FakeTools(),valid,[]).invoke('read_material',row['call_id'],json.dumps(changed)))
        self.assertEqual(exc.exception.code,'tool_call_id_reused')

    def test_completed_toolerror_receipt_replays_without_reexecution(self):
        path,row=self.prepare();path.unlink();tools=FakeTools();secret='unit-test-private-token'
        with patch.object(tools,'execute',side_effect=ToolError('bad source '+secret)) as run:
            journal=ar.ToolJournal(self.attempt,self.record,tools,valid,[secret])
            first=asyncio.run(journal.invoke('read_material',row['call_id'],json.dumps(row['arguments'])))
            second=asyncio.run(journal.invoke('read_material',row['call_id'],json.dumps(row['arguments'])))
        self.assertEqual(run.call_count,1);self.assertEqual(first,second)
        receipt=rt._read_json(path);self.assertEqual(receipt['status'],'completed')
        self.assertEqual(receipt['output']['ok'],False);self.assertEqual(receipt['output']['error'],'tool_error')
        self.assertNotIn(secret,path.read_text())

    def test_external_transport_toolerror_keeps_unknown_guard(self):
        from shared.host_tools import ToolOutcomeUnknown
        path,row=self.prepare(name='web_search',args={'query':'test'});path.unlink();tools=FakeTools()
        with patch.object(tools,'execute',side_effect=ToolOutcomeUnknown('reader transport failed')) as invoke:
            with self.assertRaises(rt.ProviderActionError) as caught:
                asyncio.run(ar.ToolJournal(self.attempt,self.record,tools,valid,[]).invoke('web_search',row['call_id'],json.dumps(row['arguments'])))
            self.assertEqual(caught.exception.code, 'tool_outcome_unknown')
            with self.assertRaises(rt.ProviderActionError):
                asyncio.run(ar.ToolJournal(self.attempt,self.record,tools,valid,[]).invoke('web_search',row['call_id'],json.dumps(row['arguments'])))
            self.assertEqual(invoke.call_count,1)
        self.assertEqual(rt._read_json(path)['status'],'started')

    def test_unexpected_io_error_is_not_swallowed_as_toolerror(self):
        path,row=self.prepare();path.unlink();tools=FakeTools()
        with patch.object(tools,'execute',side_effect=OSError('unknown filesystem effect')):
            with self.assertRaises(OSError):
                asyncio.run(ar.ToolJournal(self.attempt,self.record,tools,valid,[]).invoke('read_material',row['call_id'],json.dumps(row['arguments'])))
        self.assertEqual(rt._read_json(path)['status'],'started')

    def test_completed_read_does_not_repeat_even_at_tool_budget(self):
        path,row=self.prepare();path.unlink();tools=FakeTools()
        journal=ar.ToolJournal(self.attempt,self.record,tools,valid,[])
        asyncio.run(journal.invoke('read_material',row['call_id'],json.dumps(row['arguments'])))
        with patch.object(tools,'execute',side_effect=AssertionError('must use completed receipt')):
            asyncio.run(journal.invoke('read_material',row['call_id'],json.dumps(row['arguments'])))

    def test_tools_with_side_effects_are_not_in_replay_allowlist(self):
        self.assertEqual(ar.READONLY_REPLAY_TOOLS,{'list_materials','read_material','search_materials'})


class HostPathAndRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.pkg=self.root/'package';self.pkg.mkdir()
        self.job=self.root/'job';(self.job/'inputs').mkdir(parents=True)
        self.fact=self.job/'inputs/company_facts.md';self.fact.write_text('Verified local facts')
    def tools(self,action='answer_analysis'):return HostTools(self.pkg,self.job,action)

    def test_four_real_action_names_accept_absolute_registered_source(self):
        for action in ['answer_analysis','question_positioning','positioning_market_research','positioning_value_synthesis']:
            with self.subTest(action=action):
                tools=self.tools(action)
                self.assertEqual(tools.execute('read_material',{'artifact_id':str(self.fact)})['text'],'Verified local facts')

    def test_absolute_path_does_not_register_an_unknown_file(self):
        tools=self.tools();unknown=self.job/'inputs/new.md';unknown.write_text('not registered')
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(unknown)})

    def test_absolute_paths_keep_credential_provider_and_neighbor_boundaries(self):
        tools=self.tools()
        for name in ['config/xty.json','provider/raw.txt']:
            p=self.job/name;p.parent.mkdir(exist_ok=True);p.write_text('hidden')
            with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(p)})
        neighbor=self.root/'job-other/inputs/company_facts.md';neighbor.parent.mkdir(parents=True);neighbor.write_text('other job')
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(neighbor)})

    def test_absolute_paths_keep_traversal_and_backslash_rejection(self):
        tools=self.tools()
        for ref in [str(self.job/'inputs/../inputs/company_facts.md'),'../job/inputs/company_facts.md',r'C:\\job\\inputs\\company_facts.md',str(self.fact)+'\x00']:
            with self.subTest(ref=ref),self.assertRaises(ToolError):tools.resolve_artifact(ref)

    def test_internal_symlink_even_to_safe_file_is_rejected(self):
        alias=self.job/'inputs/link.md';alias.symlink_to(self.fact)
        tools=self.tools()
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(alias)})

    def test_caller_root_alias_is_accepted_without_allowing_inner_symlinks(self):
        alias=self.root/'job-alias';alias.symlink_to(self.job,target_is_directory=True)
        tools=HostTools(self.pkg,alias,'answer_analysis')
        self.assertEqual(tools.execute('read_material',{'artifact_id':str(alias/'inputs/company_facts.md')})['text'],'Verified local facts')
        (self.job/'inputs/link.md').symlink_to(self.fact)
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(alias/'inputs/link.md')})

    def test_absolute_path_still_checks_registered_content_sha256(self):
        tools=self.tools();self.fact.write_text('changed after registration')
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(self.fact)})

    def test_absolute_unregistered_same_basename_does_not_select_another(self):
        other=self.job/'unused/company_facts.md';other.parent.mkdir();other.write_text('other')
        with self.assertRaises(ToolError):self.tools().execute('read_material',{'artifact_id':str(other)})

    def with_old_staging_snapshot(self):
        (self.job/'00_input').mkdir()
        for i in (1,2):
            (self.job/f'inputs/answer_{i:02d}.md').write_text(f'Frozen answer {i}')
            (self.job/f'00_input/loose_answer_{i:02d}.txt').write_text(f'Frozen answer {i}')
        # Generate the old registry behavior without editing source or raw inputs.
        with patch('shared.host_tools._is_intake_answer_copy',return_value=False):
            old=self.tools()
            for ident in sorted(old._required):old.execute('read_material',{'artifact_id':ident})
            saved=copy.deepcopy(old.export_state())
        return saved

    def test_restore_old_registry_does_not_reintroduce_intake_copies(self):
        saved=self.with_old_staging_snapshot();raw=copy.deepcopy(saved)
        frozen_files={p:p.read_bytes() for p in self.job.glob('00_input/*')}
        tools=self.tools();tools.restore_state(saved)
        self.assertEqual({tools.artifacts[x]['path'] for x in tools._required},{'inputs/answer_01.md','inputs/answer_02.md'})
        self.assertFalse(any(_is_intake_answer_copy(x['path']) for x in tools.artifacts.values()))
        self.assertTrue(tools.validate_complete_reads());self.assertEqual(saved,raw)
        self.assertEqual({p:p.read_bytes() for p in frozen_files},frozen_files)
        self.assertTrue(set(tools.read_ranges).issubset(tools.artifacts));self.assertTrue(set(tools.dependencies).issubset(tools.artifacts))

    def test_restore_still_rejects_changed_frozen_answer(self):
        saved=self.with_old_staging_snapshot();(self.job/'inputs/answer_01.md').write_text('changed')
        with self.assertRaises(ToolError):self.tools().restore_state(saved)

    def test_staging_namespace_is_not_a_global_answer_exclusion(self):
        (self.job/'inputs/client_answer_notes.md').write_text('Client supplied answer material')
        tools=self.tools()
        self.assertIn('inputs/client_answer_notes.md',{tools.artifacts[x]['path'] for x in tools._required})
        self.assertFalse(_is_intake_answer_copy('materials/loose_answer_01.md'))
        self.assertFalse(_is_intake_answer_copy('00_input/loose_answer_notes.md'))
        self.assertFalse(_is_intake_answer_copy('inputs/answer_01.md'))

    def test_intake_copy_cannot_be_reregistered_by_explicit_read_or_register(self):
        self.with_old_staging_snapshot();tools=self.tools();p=self.job/'00_input/loose_answer_01.txt'
        with self.assertRaises(ToolError):tools.register_file(p,'answer',True)
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(p)})


class ContractCompatibilityTests(unittest.TestCase):
    def test_release_patch_keeps_exact_legacy_request_identity(self):
        self.assertEqual(ar.REQUEST_CONTRACT,'frontmind-agents-runtime/4.13.0-1')
        self.assertNotEqual(ar.CONTRACT,ar.REQUEST_CONTRACT)
        plan=ar.request_plan('p0_blueprint',ar.public_profile(),rt._initial_messages('p0_blueprint','original task'),[])
        old=copy.deepcopy(plan);old['contract']='frontmind-agents-runtime/4.13.0-1'
        self.assertEqual(ar.fingerprint(plan,'ctx',False),ar.fingerprint(old,'ctx',False))

    def test_implementation_contract_change_does_not_start_another_session(self):
        with tempfile.TemporaryDirectory() as d:
            pkg=Path(d)/'pkg';pkg.mkdir();job=Path(d)/'job';job.mkdir();sdk,e=bundle()
            with patch.object(ar,'CONTRACT','frontmind-agents-runtime/4.13.0-1'):
                first=ar.run_agents_action(pkg,job,'p0_blueprint','same task',valid,host_tools=FakeTools(),offline=True,sdk_override=sdk)
            before=e.calls;old=rt.action_record(job,'p0_blueprint')
            second=ar.run_agents_action(pkg,job,'p0_blueprint','same task',valid,host_tools=FakeTools(),offline=True,sdk_override=sdk)
            self.assertEqual(first,second);self.assertEqual(e.calls,before)
            self.assertEqual(rt.action_record(job,'p0_blueprint')['session_id'],old['session_id'])

    def test_failed_legacy_checkpoint_resumes_same_attempt_with_new_implementation(self):
        with tempfile.TemporaryDirectory() as d:
            pkg=Path(d)/'pkg';pkg.mkdir();job=Path(d)/'job';job.mkdir();sdk,e=bundle(fault='network_after_read')
            with patch.object(ar,'CONTRACT','frontmind-agents-runtime/4.13.0-1'):
                with self.assertRaises(rt.ProviderActionError):ar.run_agents_action(pkg,job,'p0_blueprint','same task',valid,host_tools=FakeTools(),offline=True,sdk_override=sdk)
            old=rt.action_record(job,'p0_blueprint');sdk2,e2=bundle()
            ar.run_agents_action(pkg,job,'p0_blueprint','same task',valid,retry=True,host_tools=FakeTools(),offline=True,sdk_override=sdk2)
            current=rt.action_record(job,'p0_blueprint')
            self.assertEqual(current['attempt_id'],old['attempt_id']);self.assertEqual(current['session_id'],old['session_id'])
            self.assertEqual(current['agents_contract'],old['agents_contract'])
            self.assertEqual(current['resumed_with_agents_contract'],ar.CONTRACT);self.assertEqual(e2.calls,2)  # submit + post-submit final turn


class SDKReleaseGateTests(unittest.TestCase):
    def suite(self,xml,code=0):
        from scripts.validate_workflow import _sdk_suite_result
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'suite.xml'
            if xml is not None:p.write_text(xml)
            return _sdk_suite_result(code,p,'offline fixture log')
    def test_skipped_sdk_cases_fail_release_gate(self):
        report=self.suite('<testsuite><testcase><skipped/></testcase><testcase/></testsuite>')
        self.assertEqual(report['status'],'fail');self.assertEqual(report['skipped'],1)
    def test_zero_or_missing_sdk_tests_cannot_pass(self):
        for xml in [None,'<testsuite/>','invalid xml']:
            with self.subTest(xml=xml):self.assertEqual(self.suite(xml)['status'],'fail')
    def test_four_actual_successes_pass_but_nonzero_exit_still_fails(self):
        xml='<testsuite>'+('<testcase/>'*4)+'</testsuite>'
        self.assertEqual(self.suite(xml)['status'],'pass')
        self.assertEqual(self.suite(xml,1)['status'],'fail')
    def test_sdk_failure_cannot_be_masked_by_zero_exit(self):
        xml='<testsuite><testcase><failure/></testcase><testcase/></testsuite>'
        self.assertEqual(self.suite(xml)['status'],'fail')


class AcceptanceContractTests(unittest.TestCase):
    def test_current_brand_stage_does_not_request_removed_example_confirmation(self):
        from scripts import run_acceptance_v411 as acceptance
        with patch.object(acceptance, 'state', return_value={}), \
             patch.object(acceptance.brand_stage, 'enabled', return_value=True), \
             patch.object(acceptance, 'require_status') as required, \
             patch.object(acceptance, 'resume') as resume:
            acceptance.reach_p0_blueprint(Path('job'))
            required.assert_called_once_with(Path('job'), 'awaiting_p0_blueprint_confirmation')
            resume.assert_not_called()

    def test_legacy_contract_still_exercises_example_pause(self):
        from scripts import run_acceptance_v411 as acceptance
        with patch.object(acceptance, 'state', return_value={}), \
             patch.object(acceptance.brand_stage, 'enabled', return_value=False), \
             patch.object(acceptance, 'require_status') as required, \
             patch.object(acceptance, 'resume') as resume:
            acceptance.reach_p0_blueprint(Path('job'))
            self.assertEqual([c.args[1] for c in required.call_args_list],
                             ['awaiting_p0_example_confirmation', 'awaiting_p0_blueprint_confirmation'])
            resume.assert_called_once_with(Path('job'), '--accept-p0-example-route', 'top20')


class ExternalToolFailureTests(unittest.TestCase):
    def test_transport_failure_remains_toolerror_but_is_not_recoverable_feedback(self):
        from shared.host_tools import ToolOutcomeUnknown
        from urllib.error import URLError
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'config').mkdir();(root/'job').mkdir()
            (root/'config/zhipu.json').write_text(json.dumps({'api_key':'test-fixture-key'}))
            tools=HostTools(root,root/'job','answer_analysis')
            with patch('shared.host_tools.urlopen',side_effect=URLError('offline-test')):
                with self.assertRaises(ToolOutcomeUnknown) as caught:
                    tools._api('web_search', {'search_query':'test'})
            self.assertIsInstance(caught.exception,ToolError)
            self.assertTrue(caught.exception.outcome_unknown)

    def test_missing_configuration_is_still_known_model_correctable_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'job').mkdir();tools=HostTools(root,root/'job','answer_analysis')
            with self.assertRaises(ToolError) as caught:tools._api('web_search',{})
            self.assertFalse(getattr(caught.exception,'outcome_unknown',False))
