"""4.12.5 isolation and provenance tests. Synthetic prose is not a quality sample."""
from __future__ import annotations
import copy,json,socket,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.error import URLError
from scripts import frontmind_workflow as wf, rewrite_p0_live as runner
from shared import brand_stage as bs,brand_references as br,p0_style as ps,writing_context as wc
from shared import model_runtime as rt,managed_runtime as managed
from shared.editorial_contracts import EditorialContractError
from shared.host_tools import HostTools,ToolError
ROOT=Path(__file__).resolve().parents[2]
BODY='# 合成流程测试\n\n这段合成正文仅用于测试接口与阶段衔接，不代表任何真实客户或写作质量。\n\n## 合成测试内容\n\n这里的文字用于核对实际引用和正文一致，不能作为品宣验收样本。\n'

class BrandStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.job=Path(self.tmp.name)/'job';self.job.mkdir()
        state=wf.make_state('unit','p0');state['metadata'].pop('writing_editor_contract',None);state['metadata']['p0_style_contract']=bs.CONTRACT;state['flags']['offline_fixture']=True;state['reference_pack']={'brand':'合成测试品牌'}
        wf.save_state(self.job,state)
        self.bp={'kind':'p0','article_brief':'只核对合成流程','sections':[{'heading':'合成主题','task':'合成内容'}],
            'opening':'测试开头','ending':'测试结尾','estimated_length':'仅测试','material_adjustments':[],
            'writing_material_markdown':'这是合成事实素材，用于核对原样输入与处理，不能解释为真实业务事实。',
            'writing_material_sources':['source_fixture']}
        rt._atomic(self.job/'blueprints/p0_blueprint.json',self.bp)
        rt._atomic(self.job/'production/p0_draft.json',{'article_markdown':BODY,'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''})
        rt._atomic(self.job/'production/p0_edited.json',dict(article_markdown=BODY,edit_status='accepted',editorial_notes=[],requires_blueprint_reconfirmation=False,reconfirmation_reason=''))
    def style(self):
        value=bs.fixture_style(BODY);rt._atomic(self.job/'production/p0_styled.json',value);return value
    def final(self):
        return dict(outcome='accepted',article_markdown=BODY,editorial_notes=[],reason='',brand_review=bs.fixture_review(BODY))
    def test_new_default_is_versioned_and_legacy_stays_recognized(self):
        self.assertTrue(bs.enabled(wf.load_state(self.job)))
        self.assertTrue(ps.is_deep(wf.load_state(self.job)))
        old=wf.load_state(self.job);old['metadata']['p0_style_contract']='frontmind-p0-style/4.12.2'
        self.assertTrue(ps.is_enabled(old));self.assertFalse(bs.enabled(old))
    def test_creation_does_not_fetch_reference_text(self):
        with patch.object(br,'_fetch',side_effect=AssertionError('network before third pass')):
            self.assertEqual(ps.freeze_examples(ROOT,self.job),[])
        self.assertFalse((self.job/br.SNAPSHOT).exists())
    def test_first_two_and_blueprint_do_not_receive_examples(self):
        with patch.object(br,'job_examples',side_effect=AssertionError('early examples')):
            prompts=[bs.blueprint_prompt(wf,self.job),bs.draft_prompt(wf,self.job),bs.edit_prompt(wf,self.job)]
        for p in prompts:
            self.assertNotIn('<reference_text>',p);self.assertNotIn('突破1亿用户',p);self.assertNotIn('盛宇投资',p)
        self.assertIn(self.bp['writing_material_markdown'],prompts[1]);self.assertIn(BODY,prompts[2])
    def test_third_pass_contains_both_full_synthetic_references(self):
        records=[dict(id=k,title='合成示例',source_url='offline://fixture',publication='offline',text=f'FIRST_{k}\nMIDDLE_{k}\nLAST_{k}',guide='合成测试指南') for k in bs.REFERENCE_IDS]
        with patch.object(br,'job_examples',return_value=records):p=bs.style_prompt(wf,self.job)
        self.assertIn(BODY,p)
        for k in bs.REFERENCE_IDS:
            for mark in ('FIRST','MIDDLE','LAST'):self.assertIn(mark+'_'+k,p)
    def test_shared_prompt_dispatch_uses_new_stages(self):
        self.assertEqual(wc.prompt_article(wf,self.job,p0=True),bs.draft_prompt(wf,self.job))
        self.assertEqual(wc.prompt_edit(wf,self.job,p0=True),bs.edit_prompt(wf,self.job))
    def test_finalizer_has_candidate_not_template_bodies(self):
        self.style()
        with patch.object(br,'job_examples',side_effect=AssertionError('review template')):
            p=bs.finalize_prompt(wf,self.job)
        self.assertIn(BODY,p);self.assertNotIn('<reference_text>',p);self.assertIn('不返回revised',p)
    def test_stage_specific_roles_reach_actual_wire(self):
        for action in ('p0_blueprint','p0_draft','p0_edit','p0_style','p0_finalize'):
            messages=rt._initial_messages(action,bs.MARKER+'\n合成测试')
            self.assertIn(bs.role(action),messages[0]['content'])
    def test_two_real_quote_alignments_are_required(self):
        value=self.style();bs.validate_style(value,BODY)
        value['reference_alignment'][1]['example_id']='other'
        with self.assertRaises(EditorialContractError):bs.validate_style(value,BODY)
    def test_nonexistent_comparison_quote_rejected(self):
        value=self.style();value['reference_alignment'][0]['article_quote']='根本没有出现在任何一份真实候选中的引文文本'
        with self.assertRaises(EditorialContractError):bs.validate_style(value,BODY)
    def test_host_cannot_rewrite_even_when_it_says_accepted(self):
        value=self.final();value['article_markdown']=BODY+'宿主增加的一句话。'
        with self.assertRaises(EditorialContractError):bs.validate_final(value,BODY)
    def test_host_cannot_return_revised(self):
        value=self.final();value.update(outcome='revised',article_markdown=BODY+'新增句子。',editorial_notes=['合成修改'])
        with self.assertRaises(EditorialContractError):bs.validate_final(value,BODY)
    def test_failed_genre_check_cannot_publish(self):
        value=self.final();value['brand_review']['genre_check']['passed']=False
        with self.assertRaises(EditorialContractError):bs.validate_final(value,BODY)
    def test_incomplete_keeps_issue_and_no_body(self):
        value=self.final();value.update(outcome='incomplete',article_markdown='',reason='合成体裁问题')
        value['brand_review']['genre_check']['passed']=False;value['brand_review']['unresolved_issues']=['合成体裁问题']
        bs.validate_final(value,BODY)
    def test_unresolved_issue_cannot_be_accepted(self):
        value=self.final();value['brand_review']['unresolved_issues']=['合成未解决问题']
        with self.assertRaises(EditorialContractError):bs.validate_final(value,BODY)
    def test_private_reference_hash_tampering_stops(self):
        values=br.job_examples(ROOT,self.job,freeze=True)
        self.assertEqual(len(values),2)
        Path(values[0]['path']).write_text('tampered')
        with self.assertRaises(EditorialContractError):br.job_examples(ROOT,self.job)
    def test_offline_reference_cannot_be_used_in_production(self):
        br.job_examples(ROOT,self.job,freeze=True)
        state=wf.load_state(self.job);state['flags']['offline_fixture']=False;wf.save_state(self.job,state)
        with self.assertRaises(EditorialContractError):br.job_examples(ROOT,self.job)
    def test_fetch_failure_does_not_fabricate_body_or_delete_e8(self):
        state=wf.load_state(self.job);state['flags']['offline_fixture']=False;wf.save_state(self.job,state)
        with patch.object(br,'_fetch',side_effect=EditorialContractError('synthetic_failure','test')):
            with self.assertRaises(EditorialContractError):bs.style_prompt(wf,self.job)
        self.assertFalse((self.job/br.SNAPSHOT).exists());self.assertEqual(json.loads((self.job/'production/p0_edited.json').read_text())['article_markdown'],BODY)
    def test_host_file_tools_cannot_read_stage_three_examples(self):
        values=br.job_examples(ROOT,self.job,freeze=True)
        tools=HostTools(ROOT,self.job,'p0_blueprint')
        for x in values:self.assertFalse(tools._allowed_file(Path(x['path'])))
        self.assertFalse(any(v['category']=='example' for v in tools.artifacts.values()))
    def test_early_cache_does_not_change_after_reference_capture(self):
        before=rt.context_fingerprint(self.job,'p0_draft')
        br.job_examples(ROOT,self.job,freeze=True)
        after=rt.context_fingerprint(self.job,'p0_draft')
        self.assertEqual(before,after)
    def test_host_finalizer_registers_only_third_pass_manuscript(self):
        self.style()
        tools=HostTools(ROOT,self.job,'p0_finalize')
        rows=[r for r in tools.artifacts.values() if r['category']=='manuscript']
        self.assertEqual([Path(r['path']).name for r in rows],['p0_styled.json'])
    def test_host_cannot_fetch_fixed_template_through_web_tool(self):
        tools=HostTools(ROOT,self.job,'p0_blueprint')
        spec=json.loads((ROOT/'resources/p0_brand_stage/manifest.json').read_text())['examples'][0]
        with self.assertRaises(ToolError):tools.execute('web_read',{'url':spec['source_url']})
    def test_live_runner_refuses_changed_source_on_resume(self):
        source=Path(self.tmp.name)/'source.md';source.write_text(BODY);dest=Path(self.tmp.name)/'rewrite'
        runner.prepare(source,'测试',dest,'当前明确委托')
        source.write_text(BODY+'变化')
        with self.assertRaises(ValueError):runner.prepare(source,'测试',dest,'当前明确委托')
    def test_live_runner_never_exports_after_api_failure(self):
        source=Path(self.tmp.name)/'source.md';source.write_text(BODY);dest=Path(self.tmp.name)/'rewrite'
        with patch.object(rt,'run_action',side_effect=rt.ProviderActionError('synthetic_dns','explicit offline failure simulation')):
            report=runner.run(source,'测试',dest,'当前明确委托')
        self.assertFalse(report['article_generated']);self.assertEqual(report['error_code'],'synthetic_dns');self.assertFalse((dest/'deliverables').exists())
    def test_scoped_export_wiring_with_explicit_synthetic_providers(self):
        # This is an isolated unit fixture, not a live API or prose-quality test.
        source=Path(self.tmp.name)/'fixture_source.md';source.write_text(BODY)
        dest=Path(self.tmp.name)/'synthetic_export'
        runner.prepare(source,'合成测试品牌',dest,'只验证离线导出接线')
        state=wf.load_state(dest);state['metadata'].pop('writing_editor_contract',None);state['metadata']['p0_style_contract']=bs.CONTRACT;state['flags']['offline_fixture']=True;wf.save_state(dest,state)
        calls=[]
        fixture_body=BODY+'\n'+('此段仅用于验证字数、正文传递和导出，不包含真实客户事实。'*18)+'\n'
        def fake_api(package,job,action,prompt,validator,**kwargs):
            calls.append(action)
            if action=='p0_blueprint':
                value=wf.fixture_blueprint(job,p0=True)
                value.update(writing_material_markdown='此为明确标记的合成素材，仅检查接口，没有真实客户事实。',writing_material_sources=['synthetic_source'])
            elif action=='p0_draft':value=dict(article_markdown=fixture_body,requires_blueprint_reconfirmation=False,reconfirmation_reason='')
            elif action=='p0_edit':value=dict(article_markdown=fixture_body,edit_status='accepted',editorial_notes=[],requires_blueprint_reconfirmation=False,reconfirmation_reason='')
            elif action=='p0_style':
                base=json.loads((job/'production/p0_edited.json').read_text())['article_markdown']
                value=bs.fixture_style(base)
            elif action=='p0_finalize':
                body=json.loads((job/'production/p0_styled.json').read_text())['article_markdown']
                value=dict(outcome='accepted',article_markdown=body,editorial_notes=[],reason='',brand_review=bs.fixture_review(body))
            elif action=='p0_titles':value=wf.fixture_titles(job,p0=True)
            elif action=='p0_title_review':
                value=json.loads((job/'production/p0_titles.json').read_text())
                value.update(outcome='accepted',title_notes=[],reason='')
            else:raise AssertionError(action)
            return validator(value)
        with patch.object(rt,'run_action',side_effect=fake_api):
            report=runner.run(source,'合成测试品牌',dest,'只验证离线导出接线')
        self.assertTrue(report['article_generated'],report)
        self.assertEqual(calls,['p0_blueprint','p0_draft','p0_edit','p0_style','p0_finalize','p0_titles','p0_title_review'])
        self.assertEqual(report['visual_qa'],'not_run')
        from shared import title_publication
        third=json.loads((dest/'production/p0_styled.json').read_text())['article_markdown']
        body=(dest/'deliverables/article.md').read_text()
        self.assertEqual(body,title_publication.body_only(third))
        from docx import Document
        d=Document(dest/'deliverables/article.docx')
        self.assertGreater(len(d.paragraphs),0)
        self.assertEqual(len(json.loads((dest/'deliverables/titles.json').read_text())['candidates']),20)

    def test_live_entry_rejects_symlink(self):
        original=Path(self.tmp.name)/'real.md';original.write_text(BODY);link=Path(self.tmp.name)/'alias.md';link.symlink_to(original)
        with self.assertRaises(ValueError):runner.prepare(link,'测试',Path(self.tmp.name)/'new','测试委托')

class ReferenceParserTests(unittest.TestCase):
    def setUp(self):
        self.spec=dict(title='合成文章题',title_key='合成文章题',section_keys=['合成段落甲','合成段落乙'],end_key='合成末句')
        self.raw=('<html><head><meta charset="utf-8"><title>合成文章题</title></head><body><div><p>合成首段'+('仅供解析测试。'*50)+'</p><p>合成段落甲'+('甲内容。'*60)+'</p><p>合成段落乙'+('乙内容。'*60)+'</p><p>'+('合成正文。'*60)+'</p><p>合成末句</p><p>免责声明：测试页</p></div></body></html>').encode()
    def test_article_region_extracts_complete_synthetic_text(self):
        text=br.extract(self.raw,self.spec);self.assertIn('合成首段',text);self.assertTrue(text.endswith('合成末句\n'));self.assertNotIn('免责声明',text)
    def test_search_snippet_not_complete_original(self):
        with self.assertRaises(EditorialContractError):br.extract(b'<html><title>search</title><p>summary</p></html>',self.spec)
    def test_missing_closing_anchor_is_not_complete(self):
        with self.assertRaises(EditorialContractError):br.extract(self.raw.replace('合成末句'.encode(),b'absent'),self.spec)
    def test_reprint_or_credential_url_rejected(self):
        for url in ('https://example.org/page','https://name:pass@china.com/a','http://china.com/a'):
            with self.assertRaises(EditorialContractError):br._valid_url(url)

class DNSTests(unittest.TestCase):
    def test_dns_failure_is_not_auth_failure(self):
        client=managed.ManagedClient('synthetic-test-key');client.opener=Mock()
        client.opener.open.side_effect=URLError(socket.gaierror(-3,'synthetic DNS'))
        with self.assertRaises(rt.ProviderActionError) as e:client.request('POST','/v1/agents',{'test':True})
        self.assertEqual(e.exception.code,'managed_dns_unresolved')
    def test_dns_pre_send_clears_pending_post_but_not_unknown_ack(self):
        for code,expected in [('managed_dns_unresolved',None),('managed_write_outcome_unknown','pending')]:
            with tempfile.TemporaryDirectory() as t:
                state={'completed_writes':{}};client=Mock();client.request.side_effect=rt.ProviderActionError(code,'synthetic')
                with self.assertRaises(rt.ProviderActionError):managed._write(client,Path(t),state,'agent','/v1/agents',{'test':True})
                self.assertEqual(state.get('pending_write') is None,expected is None)

if __name__=='__main__':unittest.main()
