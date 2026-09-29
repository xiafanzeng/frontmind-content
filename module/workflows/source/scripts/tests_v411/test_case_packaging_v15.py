"""Offline packaging tests; synthetic fixtures are never prose acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf, package_v15 as package
from scripts.tests_v411 import test_language_editor_v15 as flow
from shared import natural_editor


class SystemPromptPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.dest=self.root/'generated';self.dest.mkdir()
        self.portable=package.PortableRecords(self.root/'job')

    def attempt(self,name,record=None,requests=None):
        path=self.root/'attempts'/name;path.mkdir(parents=True)
        wf.atomic_json(path/'execution.json',record or {})
        for filename,request in (requests or {}).items():
            wf.atomic_json(path/filename,request)
        return path

    def collect(self,attempt):
        return package.collect_system_prompts('article_edit',attempt,self.dest,self.portable)

    def test_deepseek_saves_only_actual_system_text_and_all_round_sources(self):
        prompt='真实系统指令。\n保留换行。'
        request={'api_key':'credential-must-not-export','model':'model-metadata',
                 'messages':[{'role':'system','content':prompt},
                             {'role':'user','content':'private-user-prompt'}],
                 'tools':[{'description':'private-tool-definition'}]}
        attempt=self.attempt('normal',requests={'round_01_request.json':request,'round_02_request.json':request})
        records=self.collect(attempt)
        self.assertEqual(len(records),1)
        self.assertEqual((self.dest/records[0]['file']).read_text(),prompt)
        self.assertEqual(records[0]['original_text_sha256'],records[0]['packaged_text_sha256'])
        self.assertEqual([row['request_file'] for row in records[0]['sources']],
                         ['round_01_request.json','round_02_request.json'])
        exported=json.dumps(records)+(self.dest/records[0]['file']).read_text()
        for secret in ('credential-must-not-export','model-metadata','private-user-prompt','private-tool-definition'):
            self.assertNotIn(secret,exported)
        self.assertEqual(sorted(path.name for path in self.dest.iterdir()),['article_edit_system_prompt.md'])

    def test_xty_resume_preserves_each_actual_instruction_variant(self):
        attempt=self.attempt('sdk_resume',{'resume_count':1},requests={
            'model_0001_request.json':{'system_instructions':'原调用指令','input':[{'role':'user','content':'不导出'}]},
            'model_0002_request.json':{'system_instructions':'恢复时实际指令','profile':{'api_key':'不导出'}}})
        wf.atomic_json(attempt/'request_plan.json',{'instructions':'不使用计划或当前源码代替真实调用'})
        records=self.collect(attempt)
        self.assertEqual([(self.dest/row['file']).read_text() for row in records],['原调用指令','恢复时实际指令'])
        self.assertEqual([row['file'] for row in records],['article_edit_system_prompt.md','article_edit_system_prompt_02.md'])
        self.assertEqual(records[1]['sources'][0]['field'],'system_instructions')

    def test_zero_call_recovery_follows_original_request(self):
        original=self.attempt('original',requests={'round_01_request.json':{
            'messages':[{'role':'system','content':'恢复前真正发送的指令'}]}})
        (original/'prompt.md').write_text('原用户提示')
        recovered=self.attempt('recovered',{'recovered_from_attempt':'original',
            'source_execution_sha256':package.digest(original/'execution.json'),'model_calls':0})
        records=self.collect(recovered)
        self.assertEqual(records[0]['sources'][0]['attempt_id'],'original')
        self.assertEqual((self.dest/records[0]['file']).read_text(),'恢复前真正发送的指令')
        self.assertEqual(package.prompt_source_attempts(recovered),[original,recovered])

    def test_resumed_writer_includes_original_and_resumed_call_sources(self):
        request={'messages':[{'role':'system','content':'同一完整指令'}]}
        original=self.attempt('first',requests={'round_01_request.json':request})
        resumed=self.attempt('second',{'resumed_tools_from_attempt':'first',
            'resumed_execution_sha256':package.digest(original/'execution.json')},
            requests={'round_01_request.json':request})
        records=self.collect(resumed)
        self.assertEqual(len(records),1)
        self.assertEqual([row['attempt_id'] for row in records[0]['sources']],['first','second'])

    def test_missing_actual_request_never_falls_back_to_template(self):
        attempt=self.attempt('missing')
        wf.atomic_json(attempt/'request_plan.json',{'instructions':'仅是计划'})
        with self.assertRaisesRegex(RuntimeError,'Actual model system prompt is missing'):
            self.collect(attempt)

    def test_changed_or_escaping_recovery_reference_is_rejected(self):
        original=self.attempt('original')
        for source_id,checksum in [('original','wrong-hash'),('../outside','wrong-hash')]:
            with self.subTest(source_id=source_id):
                wf.atomic_json(original/'execution.json',{'recovered_from_attempt':source_id,
                                                         'source_execution_sha256':checksum})
                with self.assertRaises(RuntimeError):
                    self.collect(original)

    def test_responses_and_text_block_instruction_fields(self):
        rows=package.request_instruction_texts({'instructions':'Responses指令','messages':[
            {'role':'developer','content':[{'type':'input_text','text':'文本块指令'}]},
            {'role':'user','content':'用户正文'}]})
        self.assertEqual(rows,[('instructions','Responses指令'),('messages[0].content[0].text','文本块指令')])


class CasePackagingTests(unittest.TestCase):
    setUp = flow.LanguageEditorFlowTests.setUp
    job = flow.LanguageEditorFlowTests.job
    step = flow.LanguageEditorFlowTests.step
    until = flow.LanguageEditorFlowTests.until
    finish = flow.LanguageEditorFlowTests.finish

    def case(self):
        job = self.job()
        self.finish(job)
        entry = {'job': str(job), 'status': 'accepted', 'characters': -1}
        return job, entry, self.root / 'case'

    def test_tampered_final_is_rejected_before_copying(self):
        job, entry, case = self.case()
        path = job / 'production/article_finalized.json'
        value = wf.read_json(path)
        value['article_markdown'] += '\n\n未经模型编辑的新增正文。'
        wf.atomic_json(path, value)
        with self.assertRaisesRegex(ValueError, '交付稿'):
            package.collect_completed_case('P02', entry, case)
        self.assertFalse(case.exists())

    def test_valid_offline_chain_cannot_be_published_as_model_sample(self):
        _, entry, case = self.case()
        with self.assertRaisesRegex(RuntimeError, 'actual model outputs'):
            package.collect_completed_case('P02', entry, case)
        self.assertFalse(case.exists())

    def test_pending_polish_is_not_packaged_even_if_acceptance_flag_is_stale(self):
        self.structural = True
        self.polish_incomplete = True
        job = self.job()
        self.until(job, 'polish')
        with self.assertRaises(wf.WorkflowError):
            self.step(job)
        case = self.root / 'case'
        with self.assertRaisesRegex(RuntimeError, 'complete model chain'):
            package.collect_completed_case('P02', {'job': str(job), 'status': 'accepted'}, case)
        self.assertFalse(case.exists())

    def test_verified_projection_keeps_prose_and_resolves_final_review(self):
        self.structural = True
        job, entry, case = self.case()
        # Exercise the projection after a simulated production-verification
        # boundary. The actual validator is tested above and by flow tests.
        verified = package.manuscript_revision.validate_completed_manuscript(wf, job, p0=False)
        verified = copy.deepcopy(verified)
        for action in verified['source']['actions']:
            action['execution_mode'] = 'production'
        source = wf.read_json(job / 'production/article_final_source.json')
        with patch.object(package.manuscript_revision, 'validate_completed_manuscript', return_value=verified) as validate:
            package.collect_completed_case('P02', entry, case)
        validate.assert_called_once_with(wf, job, p0=False)
        dest = case / 'generated/P02'
        packaged = wf.read_json(dest / 'article_final_source.json')
        self.assertEqual(packaged['result_file'], 'article_polish_review.json')
        self.assertEqual(wf.read_json(dest / packaged['result_file']), wf.read_json(job / source['result_file']))
        self.assertEqual(packaged['body_sha256'], source['body_sha256'])
        self.assertEqual(wf.read_json(dest / 'article_finalized.json')['article_markdown'], verified['base_markdown'])
        self.assertEqual((dest / 'article.md').read_bytes(), Path(wf.load_state(job)['metadata']['delivery']['markdown']).read_bytes())
        self.assertEqual(wf.read_json(dest / 'run.json')['body_characters'], natural_editor.character_count(verified['base_markdown']))

    def test_path_portability_does_not_rewrite_manuscript_strings(self):
        job = self.root / 'job'
        body = '# 内部标题\n\n正文中作为示例出现 ' + str(job) + '/production/article_polish_review.json。'
        records = package.PortableRecords(job, prose=[body], relative_files={
            'production/article_polish_review.json': 'article_polish_review.json'})
        value = {'article_markdown': body, 'result_file': 'production/article_polish_review.json',
                 'prompt': '当前稿：\n' + body + '\n输入路径：' + str(job) + '/inputs/facts.md'}
        result = records.json(value)
        self.assertEqual(result['article_markdown'], body)
        self.assertIn(body, result['prompt'])
        self.assertIn('CASE_JOB/inputs/facts.md', result['prompt'])
        self.assertEqual(result['result_file'], 'article_polish_review.json')


if __name__ == '__main__':
    unittest.main()
