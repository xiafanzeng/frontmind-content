"""Exercise v12 state transitions, durable results and real Word structure offline.

Fixtures never invoke a provider and do not establish real article quality.
"""
from __future__ import annotations

from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

from scripts import frontmind_workflow as wf
from scripts.tests_v411.test_article_reader_final8 import fixture_profile
from shared import natural_editor, manuscript_revision, model_runtime, writing_context, title_strategy


class NaturalEditorFlowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.calls = Counter()
        self.actions = []
        self.needs_revision = False
        self.body = '# 内部标题\n\n简短导语。\n\n' + '\n\n'.join(
            f'**合成机构{i}有限公司**\n\n' + f'合成机构{i}提供本题相关的服务，设有独立接待空间，预约后安排需求沟通。'*3
            for i in range(1, 12))
        self.repaired = self.body.replace('简短导语。', '根据实际材料完成的导语。')
        self.edited_body = None
        self.prompts = {}
        original_ensure = wf.ensure_action
        def ensure(job, action, prompt, *, fixture_builder):
            self.actions.append(action)
            self.prompts[action] = prompt
            def fixture():
                self.calls[action] += 1
                if action.endswith('_draft'):
                    return {'article_markdown': self.body, 'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''}
                if action.endswith('_edit'):
                    from shared.editorial_contracts import edit_base_input
                    base = edit_base_input(wf, job, p0=action.startswith('p0_'))['article_markdown']
                    body = self.edited_body or base
                    changed = body != base
                    return {'edit_status': 'revised' if changed else 'accepted', 'article_markdown': body,
                            'editorial_notes': ['完成本轮修改。'] if changed else [],
                            'requires_blueprint_reconfirmation': False, 'reconfirmation_reason': ''}
                if action.endswith('_style'):
                    return {'article_markdown': wf.read_json(job/'production/p0_edited.json')['article_markdown']}
                if action.endswith('_finalize'):
                    return {'needs_revision': self.needs_revision, 'comments': ['修改导语的重复表达。'] if self.needs_revision else []}
                if action.endswith('_repair'):
                    return {'article_markdown': self.repaired}
                if action.endswith('_titles'):
                    return {'candidates': [{'title': f'合成服务的项目安排与业务观察{i:02}', 'angle': '服务介绍'} for i in range(title_strategy.expected_count(wf.load_state(job)))],
                            'canonical_title_id': 'title_03'}
                return fixture_builder()
            return original_ensure(job, action, prompt, fixture_builder=fixture)
        for target, name, value in (
            (wf, 'ensure_action', ensure),
            (wf, 'answer_texts', lambda *_: []),
            (model_runtime, 'profile_for', fixture_profile),
            (wf, 'write_docx', lambda body, path, title: (path.parent.mkdir(parents=True, exist_ok=True), path.write_text('explicit test export stub'))),
        ):
            monkey = patch.object(target, name, side_effect=value)
            monkey.start(); self.addCleanup(monkey.stop)

    def job(self, prefix='article'):
        job = self.root/prefix;job.mkdir()
        for name in ('blueprints', 'production', 'inputs', '00_input'):
            (job/name).mkdir()
        state = wf.make_state('v12-'+prefix, prefix)
        # These historical fixtures pin the pre-editorial-mission requests.
        # New-mode tests explicitly opt in at their commission boundary.
        state['metadata'].pop('writing_mission_input_mode', None)
        state['metadata'].pop('natural_prose_contract', None)
        state['metadata'].pop('title_strategy', None)
        state.update(status='running_'+prefix+'_production', stage='production', selected_pattern_id='P00' if prefix=='p0' else 'P02',
                     selected_example_route='default', question={'question_text': '本题相关机构有哪些？'})
        pack = job/'00_input/reference_pack.zip';pack.write_text('offline fixture pack')
        state['reference_pack'] = {'brand': '合成机构', 'path': str(pack), 'pack_id': 'offline-pack', 'pack_version': 1}
        state['flags'] = {'offline_fixture': True, prefix+'_production_step': 'draft'}
        state['decisions'][prefix+'_blueprint_confirmation'] = {'revision': state['revision'], 'confirmed_at':'offline'}
        wf.atomic_json(job/'job_state.json', state)
        wf.atomic_json(job/'blueprints'/f'{prefix}_blueprint.json', {
            'kind': prefix, 'question': state['question']['question_text'], 'pattern_id': state['selected_pattern_id'],
            'article_brief': '自然的机构专题；每个主体独立加粗分段。', 'example_use': '参考相关事实的展开。',
            'opening': '直接介绍主题', 'ending':'介绍完成处结束',
            'sections': [{'heading':'机构介绍','task':'展开相关业务'}], 'estimated_length':'按照材料充分展开',
            'writing_material_markdown': '这些合成机构设有独立接待空间，预约后安排需求沟通。',
            'writing_material_sources': [{'source_ref':'inputs/facts.md','use':'合成服务事实'}], 'material_adjustments': []})
        (job/'inputs/facts.md').write_text('Explicit synthetic data for offline execution tests.')
        return job

    def step(self, job, *, p0=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return wf.run_production(job, p0=p0)

    def until(self, job, step, *, p0=False):
        prefix = 'p0' if p0 else 'article'
        for _ in range(20):
            if wf.load_state(job)['flags'].get(prefix+'_production_step') == step:
                return
            self.step(job,p0=p0)
        self.fail('production did not reach '+step)

    def finish(self, job, *, p0=False):
        self.until(job,'deliver',p0=p0);self.step(job,p0=p0)
        if p0:
            state=wf.load_state(job);state['status']='p0_ready';wf.save_state(job,state)

    def test_no_comments_selects_exact_candidate_and_skips_writer_repair(self):
        job=self.job();self.finish(job)
        final=wf.read_json(job/'production/article_finalized.json')
        self.assertEqual(final['article_markdown'],self.body)
        self.assertEqual(self.calls['article_finalize'],1)
        self.assertEqual(self.calls['article_repair'],0)
        source=wf.read_json(job/'production/article_final_source.json')
        self.assertEqual(source['action'],'article_edit')
        self.assertEqual(source['body_sha256'],natural_editor.digest(self.body))
        self.assertEqual(manuscript_revision.validate_completed_manuscript(wf,job,p0=False)['base_source'],'previous_final')

    def test_explicit_null_empty_reason_keeps_body_and_raw_writer_payload(self):
        job=self.job();self.until(job,'edit')
        raw={'edit_status':'accepted','article_markdown':self.body,'editorial_notes':[],
             'requires_blueprint_reconfirmation':False,'reconfirmation_reason':None}
        result=wf.validate_action_result(job,'article_edit',raw)
        self.assertEqual(result['reconfirmation_reason'],'')
        self.assertEqual(result['article_markdown'],self.body)
        self.assertIsNone(raw['reconfirmation_reason'])
        self.assertIsNot(result,raw)

    def test_empty_reason_compatibility_does_not_hide_required_or_missing_reason(self):
        job=self.job()
        raw={'article_markdown':self.body,'requires_blueprint_reconfirmation':True,
             'reconfirmation_reason':None}
        with self.assertRaises(wf.editorial_contracts.EditorialContractError):
            wf.validate_action_result(job,'article_draft',raw)
        raw['requires_blueprint_reconfirmation']=False
        del raw['reconfirmation_reason']
        with self.assertRaises(wf.editorial_contracts.EditorialContractError):
            wf.validate_action_result(job,'article_draft',raw)
        raw['reconfirmation_reason']=None
        state=wf.load_state(job);state['metadata']={};wf.save_state(job,state)
        with self.assertRaises(wf.editorial_contracts.EditorialContractError):
            wf.validate_action_result(job,'article_draft',raw)

    def test_completed_manuscript_replays_recovered_null_writer_results_without_mutation(self):
        from scripts.tests_v411.test_model_runtime import stream
        job=self.job();self.finish(job)
        package=self.root/'mock-package';(package/'config').mkdir(parents=True)
        (package/'config/deepseek.json').write_text(json.dumps({'api_key':'offline-test-credential'}))
        recovered={}
        for action,suffix in (('article_draft','draft'),('article_edit','edited')):
            path=job/'production'/f'article_{suffix}.json'
            raw={**wf.read_json(path),'reconfirmation_reason':None}
            strict=(wf.editorial_contracts.validate_draft_result if suffix=='draft' else
                    lambda value: wf.editorial_contracts.validate_edit_result(value,self.body))
            with patch.object(model_runtime,'http_events',side_effect=lambda *args:stream(content=json.dumps(raw))):
                with self.assertRaises(model_runtime.ProviderActionError):
                    model_runtime.run_action(package,job,action,'complete writer input '+action,strict)
            with patch.object(model_runtime,'http_events',side_effect=AssertionError('recovery cannot call a model')):
                result=model_runtime.run_action(package,job,action,'complete writer input '+action,
                    lambda value: wf.validate_action_result(job,action,value),retry=True)
            record=model_runtime.action_record(job,action)
            self.assertEqual(record['model_calls'],0)
            self.assertIn('recovered_from_attempt',record)
            recovered[action]=record
            wf.atomic_json(path,result)
            wf.atomic_json(job/'provider'/action/'result.json',result)
        source=wf.read_json(job/'production/article_final_source.json')
        source['attempt_id']=recovered['article_edit']['attempt_id']
        wf.atomic_json(job/'production/article_final_source.json',source)
        original={p.relative_to(job).as_posix():p.read_bytes() for p in job.rglob('*') if p.is_file()}
        verify=manuscript_revision._verified_action
        def verify_writer(wf_arg,job_arg,action,production,validator,*,offline):
            # Other actions remain explicit offline fixtures; both writer
            # links use the real immutable request/stream/result replay.
            return verify(wf_arg,job_arg,action,production,validator,
                          offline=False if action in recovered else offline)
        with patch.object(manuscript_revision,'_verified_action',side_effect=verify_writer), \
             patch.object(model_runtime,'http_events',side_effect=AssertionError('reading cannot call a model')):
            for _ in range(2):
                result=manuscript_revision.validate_completed_manuscript(wf,job,p0=False)
                self.assertEqual(result['base_sha256'],natural_editor.digest(self.body))
                for action in recovered:
                    self.assertEqual(next(a for a in result['source']['actions'] if a['action']==action)['attempt_id'],
                                     recovered[action]['attempt_id'])
        self.assertEqual({p.relative_to(job).as_posix():p.read_bytes() for p in job.rglob('*') if p.is_file()},original)

    def test_comments_trigger_one_repair_then_titles_without_body_rereview(self):
        self.needs_revision=True
        job=self.job();self.finish(job)
        final=wf.read_json(job/'production/article_finalized.json')
        self.assertEqual(final['article_markdown'],self.repaired)
        self.assertEqual(self.calls['article_finalize'],1)
        self.assertEqual(self.calls['article_repair'],1)
        self.assertEqual(self.actions[-4:],['article_finalize','article_repair','article_titles','article_title_review'])
        self.assertIn('根据实际材料完成的导语。',self.prompts['article_titles'])
        self.assertEqual(wf.read_json(job/'production/article_edited.json')['article_markdown'],self.body)
        self.assertEqual(wf.read_json(job/'production/article_final_source.json')['action'],'article_repair')
        manuscript_revision.validate_completed_manuscript(wf,job,p0=False)

    def test_interruption_after_provider_result_recovers_without_duplicate_call(self):
        self.needs_revision=True
        job=self.job();self.until(job,'repair')
        original=wf.atomic_json
        failed=[False]
        def interrupt(path,value):
            if Path(path).name=='article_repaired.json' and not failed[0]:
                failed[0]=True
                raise OSError('simulated interruption after provider result')
            return original(path,value)
        with patch.object(wf,'atomic_json',side_effect=interrupt):
            with self.assertRaises(OSError):self.step(job)
        self.assertEqual(self.calls['article_repair'],1)
        self.assertEqual(wf.load_state(job)['flags']['article_production_step'],'repair')
        self.finish(job)
        self.assertEqual(self.calls['article_repair'],1)
        self.assertEqual(self.calls['article_finalize'],1)
        self.assertEqual(wf.read_json(job/'production/article_finalized.json')['article_markdown'],self.repaired)

    def test_completed_repair_can_continue_with_title_and_manuscript_edits(self):
        self.needs_revision=True
        job=self.job();self.finish(job)
        before=(job/'production/article_finalized.json').read_bytes()
        request=self.root/'request.md';request.write_text('本轮只调整标题角度。')
        def continue_with(flag):
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(wf.load_state(job)['revision']),flag,str(request)])
            with patch.object(wf,'drive',return_value=0):
                with contextlib.redirect_stdout(io.StringIO()):wf.continue_workflow(args)
        previous=self.calls.copy();continue_with('--title-edits');self.finish(job)
        self.assertEqual((job/'production/article_finalized.json').read_bytes(),before)
        self.assertEqual(self.calls['article_finalize'],previous['article_finalize'])
        self.assertEqual(self.calls['article_repair'],previous['article_repair'])
        request.write_text('本轮修改开头，机构分段保持。')
        self.needs_revision=False
        self.edited_body=self.repaired.replace('根据实际材料完成的导语。','本轮新的具体导语。')
        continue_with('--manuscript-edits')
        frozen=manuscript_revision.current_revision(wf,job,p0=False)
        self.assertEqual(frozen['base_markdown'],self.repaired)
        self.finish(job)
        self.assertEqual(wf.read_json(job/'production/article_finalized.json')['article_markdown'],self.edited_body)
        self.assertEqual(self.calls['article_draft'],1)
        manuscript_revision.validate_completed_manuscript(wf,job,p0=False)

    def test_p0_keeps_style_pass_and_repair_uses_styled_body(self):
        self.needs_revision=True
        job=self.job('p0');self.finish(job,p0=True)
        self.assertEqual(self.calls['p0_style'],1)
        self.assertEqual(self.calls['p0_finalize'],1)
        self.assertEqual(self.calls['p0_repair'],1)
        self.assertEqual(wf.read_json(job/'production/p0_styled.json')['article_markdown'],self.body)
        self.assertEqual(wf.read_json(job/'production/p0_final_source.json')['candidate_source'],'deepseek_style')
        pack=job/'deliverables/Reference_Pack_v2.zip';pack.write_text('explicit offline pack fixture')
        state=wf.load_state(job)
        state['metadata']['reference_pack_delivery']={'portable_zip_path':str(pack),
            'portable_zip_sha256':'sha256:'+manuscript_revision.file_hash(pack),'pack_version':2}
        wf.save_state(job,state)
        published=Path(state['metadata']['delivery']['markdown']).read_bytes()
        with patch.object(wf,'validate_reference_pack',return_value={'status':'pass','readiness':{'p0_ready':True}}), \
             patch.object(wf,'reference_pack_root',return_value={'pack_id':'offline-pack','pack_version':2}), \
             patch.object(wf,'read_reference_member',return_value=published):
            manuscript_revision.validate_completed_manuscript(wf,job,p0=True)


class NaturalEditorFormatTests(unittest.TestCase):
    def test_separate_subject_bold_paragraphs_survive_html_and_word(self):
        names=[f'合成机构{i}有限公司' for i in range(1,12)]
        body='简短导语。\n\n'+'\n\n'.join(f'**{name}**\n\n{name}提供具体服务。' for name in names)
        html=wf.markdown_to_html(body,'专题正文')
        for name in names:self.assertIn('<strong>'+name+'</strong>',html)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'article.docx';wf.write_docx(body,path,'专题正文')
            with zipfile.ZipFile(path) as archive:
                xml=ET.fromstring(archive.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs=xml.findall('.//w:body/w:p',ns)
        for name in names:
            headings=[p for p in paragraphs if ''.join(p.itertext())==name]
            self.assertEqual(len(headings),1)
            p=headings[0]
            self.assertIsNotNone(p.find('w:r/w:rPr/w:b',ns))
            self.assertIsNotNone(p.find('w:pPr/w:keepNext',ns))
            index=paragraphs.index(p)
            self.assertEqual(''.join(paragraphs[index+1].itertext()),name+'提供具体服务。')


if __name__=='__main__':unittest.main()
