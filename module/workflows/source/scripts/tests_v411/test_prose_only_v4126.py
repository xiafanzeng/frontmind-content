"""Prose-only P0 contract tests. All prose and transports here are synthetic."""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import frontmind_workflow as wf, rewrite_p0_live as runner
from shared import prose_only as po, brand_stage as bs, brand_references as br
from shared import model_runtime as rt, editorial_contracts as ec, writing_context as wc, p0_style
from scripts.tests_v411.test_model_runtime import stream

# 作者档位跟随本包 config/deepseek.json 的显式覆盖（用户2026-09-22定为high；缺省默认max）。
# 断言验证配置一致性，而不是钉死某一档位。
import json as _json
from pathlib import Path as _Path
try:
    _cfgf = _Path(__file__).resolve().parents[2] / 'config' / 'deepseek.json'
    _WRITER_EFFORT = (_json.loads(_cfgf.read_text()).get('reasoning_effort') or 'max') if _cfgf.exists() else 'max'
except Exception:
    _WRITER_EFFORT = 'max'


ROOT = Path(__file__).resolve().parents[2]
BODY = '# 合成接口测试\n\n这是用于测试字段传递的合成文章，不代表真实客户或成稿质量。\n\n## 合成主题\n\n' + ('这段合成文字仅供离线验证正文保留与导出衔接，不涉及任何真实业务。' * 10) + '\n'
REFERENCES = [dict(id=i, title=i + '合成例文', text=f'FIRST_{i}\nMIDDLE_{i}\nLAST_{i}', guide='GUIDE_MUST_NOT_REACH_AUTHOR', source_url='offline://fixture', publication='offline') for i in ('xingyuanzhi', 'gangjun')]


class ProseOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name) / 'job'
        self.job.mkdir()
        self.state = wf.make_state('synthetic', 'p0')
        self.state['metadata'].pop('writing_editor_contract', None)  # Historical fixture.
        self.state['metadata']['p0_style_contract'] = po.CONTRACT  # Preserve the 4.12.6 fixture.
        self.state['flags']['offline_fixture'] = True
        self.state['reference_pack'] = {'brand': '合成测试品牌'}
        self.state['decisions']['response_brief'] = '只核对合成内容。CURRENT_EXPLICIT_REQUIREMENT'
        wf.save_state(self.job, self.state)
        self.bp = dict(kind='p0', article_brief='BLUEPRINT_NOT_AN_EXTRA_WRITING_INPUT',
            opening='OPENING_PLAN_NOT_AN_EXTRA_INPUT', ending='ENDING_PLAN_NOT_AN_EXTRA_INPUT',
            sections=[{'heading': '合成主题', 'task': 'SECTION_PLAN_NOT_AN_EXTRA_INPUT'}],
            estimated_length='LENGTH_PLAN_NOT_AN_EXTRA_INPUT',
            writing_material_markdown='本篇合成事实完整保留。FACT_START\nFACT_MIDDLE\nFACT_END',
            writing_material_sources=['synthetic_source'], material_adjustments=['历史年份不能改为当前。FACT_CONDITION'])
        rt._atomic(self.job / 'blueprints/p0_blueprint.json', self.bp)
        rt._atomic(self.job / 'production/p0_draft.json', dict(article_markdown=BODY, requires_blueprint_reconfirmation=False, reconfirmation_reason=''))
        rt._atomic(self.job / 'production/p0_edited.json', dict(article_markdown=BODY, edit_status='accepted', editorial_notes=[], requires_blueprint_reconfirmation=False, reconfirmation_reason=''))

    def style_prompt(self):
        with patch.object(br, 'job_examples', return_value=REFERENCES):
            return bs.style_prompt(wf, self.job)

    def final_value(self):
        return dict(outcome='accepted', article_markdown=BODY, editorial_notes=[], reason='')

    def put_style(self):
        rt._atomic(self.job / 'production/p0_styled.json', {'article_markdown': BODY})

    def test_preserved_4126_jobs_use_prose_only_contract(self):
        self.assertEqual(self.state['metadata']['p0_style_contract'], po.CONTRACT)
        self.assertTrue(bs.enabled(self.state)); self.assertTrue(p0_style.is_deep(self.state)); self.assertTrue(po.enabled(self.state))
        self.assertFalse(po.enabled(wf.make_state('question', 'article')))

    def test_job_schema_accepts_new_and_preserved_contracts(self):
        schema = json.loads((ROOT / 'shared/job_state.schema.json').read_text())
        allowed = schema['properties']['metadata']['properties']['p0_style_contract']['enum']
        self.assertIn(po.CONTRACT, allowed)
        self.assertIn(bs.CONTRACT, allowed)
        self.assertIn(self.state['metadata']['p0_style_contract'], allowed)

    def test_old_jobs_keep_legacy_contract(self):
        old = copy.deepcopy(self.state); old['metadata']['p0_style_contract'] = bs.CONTRACT
        self.assertTrue(bs.enabled(old)); self.assertTrue(p0_style.is_deep(old)); self.assertFalse(po.enabled(old))
        bs.validate_style(bs.fixture_style(BODY), BODY, state=old)
        with self.assertRaises(ec.EditorialContractError): bs.validate_style({'article_markdown': BODY}, BODY, state=old)

    def test_no_reference_acquisition_before_third_pass(self):
        with patch.object(br, 'job_examples', side_effect=AssertionError('too early')):
            self.assertEqual(p0_style.freeze_examples(ROOT, self.job), [])
            for p in (bs.blueprint_prompt(wf, self.job), bs.draft_prompt(wf, self.job), bs.edit_prompt(wf, self.job)):
                self.assertNotIn('<reference_text>', p)

    def test_only_e8_facts_and_full_references_in_third_payload(self):
        prompt = self.style_prompt()
        self.assertIn(BODY, prompt); self.assertIn(self.bp['writing_material_markdown'], prompt)
        for ref in REFERENCES: self.assertIn(ref['text'], prompt)
        self.assertEqual(prompt.count('<reference_text>'), 2)
        for unwanted in ('BLUEPRINT_NOT', 'OPENING_PLAN_NOT', 'ENDING_PLAN_NOT', 'SECTION_PLAN_NOT', 'LENGTH_PLAN_NOT', 'GUIDE_MUST_NOT', 'editorial_plan', 'style_audit', 'reference_alignment', 'unresolved_issues', 'edit_status'):
            self.assertNotIn(unwanted, prompt)

    def test_current_requirements_and_factual_conditions_are_preserved(self):
        prompt = self.style_prompt()
        self.assertIn('CURRENT_EXPLICIT_REQUIREMENT', prompt); self.assertIn('FACT_CONDITION', prompt)

    def test_shared_dispatch_uses_actual_prose_only_prompt(self):
        with patch.object(br, 'job_examples', return_value=REFERENCES):
            self.assertEqual(wc.prompt_p0_style(wf, self.job), po.style_prompt(wf, self.job))

    def test_writer_wire_has_raw_markdown_not_json_mode(self):
        prompt = self.style_prompt(); payload = rt.build_payload('p0_style', prompt)
        self.assertNotIn('response_format', payload)
        self.assertEqual(payload['model'], 'deepseek-v4-pro')
        self.assertEqual(payload['thinking'], {'type': 'enabled'}); self.assertEqual(payload['reasoning_effort'], _WRITER_EFFORT)
        self.assertEqual(payload['messages'][0]['content'], po.STYLE_SYSTEM)
        self.assertEqual(payload['messages'][1]['content'], prompt)
        self.assertNotIn('tools', payload)

    def test_json_mode_unchanged_for_other_stages_and_legacy_style(self):
        for action in ('p0_draft', 'p0_edit', 'p0_titles', 'article_draft', 'article_edit', 'article_titles'):
            self.assertEqual(rt.build_payload(action, 'synthetic task')['response_format'], {'type': 'json_object'})
        self.assertEqual(rt.build_payload('p0_style', bs.MARKER + '\nlegacy')['response_format'], {'type': 'json_object'})

    @unittest.skipUnless((ROOT/"customer_inputs/yihang/rewrite_requirements.md").is_file(), "Private upstream customer material is intentionally excluded from public source")
    def test_bundled_rewrite_requirements_do_not_restore_old_reports(self):
        text=(ROOT/'customer_inputs/yihang/rewrite_requirements.md').read_text()
        for phrase in ('第三遍须对照','给出对应段落的实际编辑说明','editorial_plan','reference_alignment'):
            self.assertNotIn(phrase,text)
        self.assertIn('2021年12月21日至23日',text)
        self.assertIn("runs/yihang_v4.12.8",(ROOT/'scripts/rewrite_p0_live.py').read_text())

    def test_host_uses_sdk_with_unchanged_review_contract(self):
        p = rt.profile_for('p0_finalize')
        self.assertEqual(p['wire_api'], 'openai_agents_sdk'); self.assertEqual(p['provider'], 'xty'); self.assertEqual(p['model_api'], 'chat_completions')

    def test_parser_wraps_only_exact_body(self):
        self.assertEqual(rt.parse_writer_content('p0_style', po.MARKER + '\ntask', BODY), {'article_markdown': BODY})
        self.assertEqual(po.validate_style({'article_markdown': BODY}, BODY), {'article_markdown': BODY})

    def test_author_no_longer_has_to_change_a_good_article(self):
        self.assertEqual(wf.validate_action_result(self.job, 'p0_style', {'article_markdown': BODY}), {'article_markdown': BODY})

    def test_actual_edit_does_not_need_edit_notes(self):
        edited = BODY.replace('合成主题', '修改后的合成主题')
        self.assertEqual(wf.validate_action_result(self.job, 'p0_style', {'article_markdown': edited})['article_markdown'], edited)

    def test_bad_raw_outputs_are_not_silently_accepted(self):
        for bad in ('', '```markdown\n' + BODY + '```', json.dumps({'article_markdown': BODY}), '以下是我的编辑计划。'):
            with self.subTest(bad=bad[:20]), self.assertRaises(ec.EditorialContractError): po.parse_article(bad)

    def test_legacy_self_reports_rejected_by_new_contract(self):
        for k in ('editorial_plan', 'style_audit', 'reference_alignment', 'unresolved_issues', 'editorial_notes', 'edit_status'):
            with self.subTest(field=k), self.assertRaises(ec.EditorialContractError):
                wf.validate_action_result(self.job, 'p0_style', {'article_markdown': BODY, k: []})

    def test_final_input_reads_body_without_requiring_removed_reports(self):
        self.put_style(); value = ec.prepare_finalize_input(wf, self.job, p0=True)
        self.assertEqual(value['candidate_markdown'], BODY)
        self.assertEqual(value['candidate_source'], 'deepseek_style')

    def test_final_prompt_is_simple_no_examples_or_self_audit(self):
        self.put_style()
        with patch.object(br, 'job_examples', side_effect=AssertionError('no final example reread')):
            prompt = bs.finalize_prompt(wf, self.job)
        self.assertIn(BODY, prompt)
        for forbidden in ('<reference_text>', 'style_audit', 'brand_review', 'reference_alignment', 'editorial_plan', 'article_quote'):
            self.assertNotIn(forbidden, prompt)
        self.assertEqual(rt._initial_messages('p0_finalize', prompt)[0]['content'], po.REVIEW_SYSTEM)

    def test_simple_final_accepts_without_extra_report(self):
        self.put_style(); self.assertEqual(wf.validate_action_result(self.job, 'p0_finalize', self.final_value()), self.final_value())

    def test_final_cannot_rewrite_even_one_character(self):
        v = self.final_value(); v['article_markdown'] += '\n'
        with self.assertRaises(ec.EditorialContractError): po.validate_final(v, BODY)
        v.update(outcome='revised', editorial_notes=['修改说明'])
        with self.assertRaises(ec.EditorialContractError): po.validate_final(v, BODY)

    def test_final_incomplete_is_a_small_specific_verdict(self):
        v = dict(outcome='incomplete', article_markdown='', editorial_notes=[], reason='第二节项目年份与本篇事实不一致。')
        self.assertEqual(po.validate_final(v, BODY), v)
        v['reason'] = ''
        with self.assertRaises(ec.EditorialContractError): po.validate_final(v, BODY)

    def test_final_reconfirmation_keeps_existing_business_route(self):
        v = dict(outcome='requires_blueprint_reconfirmation', article_markdown='', editorial_notes=[], reason='当前委托明确禁止的业务范围需要变更，须用户决定。')
        self.assertEqual(po.validate_final(v, BODY), v)

    def test_final_no_extra_report_or_contradictory_acceptance(self):
        v = {**self.final_value(), 'brand_review': {}}
        with self.assertRaises(ec.EditorialContractError): po.validate_final(v, BODY)
        v = self.final_value(); v['reason'] = '有未解决问题'
        with self.assertRaises(ec.EditorialContractError): po.validate_final(v, BODY)

    def test_managed_submit_schema_matches_simple_review(self):
        prompt = po.MARKER + '\n验读'
        tool = rt.submit_tool_for('p0_finalize', prompt=prompt)
        schema = tool['function']['parameters']['properties']['result']
        self.assertEqual(set(schema['required']), {'outcome', 'article_markdown', 'editorial_notes', 'reason'})
        self.assertNotIn('revised', schema['properties']['outcome']['enum'])
        self.assertEqual(schema['properties']['editorial_notes']['maxItems'], 0)
        self.assertFalse(schema['additionalProperties'])
        self.assertIn('revised', rt.submit_tool_for('p0_finalize')['function']['parameters']['properties']['result']['properties']['outcome']['enum'])

    def test_native_managed_review_tool_roundtrip_and_cached_acceptance(self):
        legacy=rt.legacy_managed_routes();legacy.__enter__();self.addCleanup(legacy.__exit__,None,None,None)
        from scripts.tests_v411.test_managed_runtime_v4123 import ManagedServer
        from scripts.tests_v411.test_model_runtime import FakeTools
        self.put_style();br.job_examples(ROOT,self.job,freeze=True)
        prompt=bs.finalize_prompt(wf,self.job);server=ManagedServer(result=self.final_value())
        validator=lambda v:wf.validate_action_result(self.job,'p0_finalize',v)
        result=rt.run_action(ROOT,self.job,'p0_finalize',prompt,validator,host_tools=FakeTools(),transport=server,offline=True)
        self.assertEqual(result,self.final_value())
        plan=rt.build_payload('p0_finalize',prompt,tools=FakeTools().definitions())
        self.assertEqual(server.resources['agent']['tools'],plan['agent']['tools'])
        calls=len(server.calls)
        restored=rt.run_action(ROOT,self.job,'p0_finalize',prompt,validator,host_tools=FakeTools(),transport=server,offline=True)
        self.assertEqual(restored,result);self.assertEqual(calls,len(server.calls))

    def test_new_request_fingerprint_cannot_reuse_legacy_output(self):
        old = rt.request_fingerprint('p0_style', bs.MARKER + '\n同一任务', offline=True)
        new = rt.request_fingerprint('p0_style', po.MARKER + '\n同一任务', offline=True)
        self.assertNotEqual(old, new)

    def test_streamed_prose_saved_and_recovered_without_paid_call(self):
        # Acquire only synthetic references into the private offline test Job.
        br.job_examples(ROOT, self.job, freeze=True)
        prompt = self.style_prompt(); payloads = []
        def transport(profile, key, payload):
            self.assertNotIn('response_format', profile); self.assertNotIn('response_format', payload)
            payloads.append(copy.deepcopy(payload)); return stream(content=BODY)
        validator = lambda v: wf.validate_action_result(self.job, 'p0_style', v)
        result = rt.run_action(ROOT, self.job, 'p0_style', prompt, validator, transport=transport, offline=True)
        self.assertEqual(result, {'article_markdown': BODY}); self.assertEqual(len(payloads), 1)
        record = rt.action_record(self.job, 'p0_style')
        attempt = self.job / 'provider/p0_style/runtime/attempts' / record['attempt_id']
        self.assertEqual((attempt/'raw_content.txt').read_text(), BODY)
        self.assertNotIn('response_format', record['requested_configuration'])
        def no_call(*args): raise AssertionError('saved response must recover without API')
        recovered = rt.run_action(ROOT, self.job, 'p0_style', prompt, validator, transport=no_call, offline=True)
        self.assertEqual(recovered, result)

    def test_network_failure_stays_failure_no_body_fallback(self):
        br.job_examples(ROOT, self.job, freeze=True)
        prompt = self.style_prompt(); calls=[]
        def fail(*args): calls.append(1); raise OSError('offline synthetic failure')
        for _ in range(2):
            with self.assertRaises(rt.ProviderActionError):
                rt.run_action(ROOT, self.job, 'p0_style', prompt, lambda v: wf.validate_action_result(self.job, 'p0_style', v), transport=fail, offline=True)
        self.assertEqual(len(calls), 1)
        self.assertFalse((self.job/'production/p0_styled.json').exists())
        self.assertFalse(list(self.job.rglob('validated_result.json')))

    def test_tampered_stored_prose_is_not_reused(self):
        br.job_examples(ROOT, self.job, freeze=True); prompt=self.style_prompt()
        validator=lambda v: wf.validate_action_result(self.job,'p0_style',v)
        rt.run_action(ROOT,self.job,'p0_style',prompt,validator,transport=lambda *a: stream(content=BODY),offline=True)
        record=rt.action_record(self.job,'p0_style')
        attempt=self.job/'provider/p0_style/runtime/attempts'/record['attempt_id']
        rt._atomic(attempt/'parsed_result.json',{'article_markdown':BODY+'篡改'})
        with self.assertRaises(rt.ProviderActionError):
            rt.run_action(ROOT,self.job,'p0_style',prompt,validator,transport=lambda *a: (_ for _ in ()).throw(AssertionError('no auto rerun')),offline=True)

    def test_scoped_three_pass_export_uses_only_the_new_body(self):
        source=Path(self.tmp.name)/'synthetic.md'; source.write_text(BODY)
        dest=Path(self.tmp.name)/'export'; runner.prepare(source,'合成测试品牌',dest,'仅验证离线导出')
        state=wf.load_state(dest);state['metadata'].pop('writing_editor_contract',None);state['flags']['offline_fixture']=True;wf.save_state(dest,state)
        calls=[]
        def fake(package,job,action,prompt,validator,**kwargs):
            calls.append(action)
            if action=='p0_blueprint':
                value=wf.fixture_blueprint(job,p0=True)
                value.update(writing_material_markdown='合成素材，仅供接口测试。',writing_material_sources=['synthetic'])
            elif action=='p0_draft': value=dict(article_markdown=BODY,requires_blueprint_reconfirmation=False,reconfirmation_reason='')
            elif action=='p0_edit': value=dict(article_markdown=BODY,edit_status='accepted',editorial_notes=[],requires_blueprint_reconfirmation=False,reconfirmation_reason='')
            elif action=='p0_style':
                self.assertNotIn('editorial_plan',prompt);value=rt.parse_writer_content(action,prompt,BODY)
            elif action=='p0_finalize': value=self.final_value()
            elif action=='p0_titles': value=wf.fixture_titles(job,p0=True)
            elif action=='p0_title_review':
                value=json.loads((job/'production/p0_titles.json').read_text());value.update(outcome='accepted',title_notes=[],reason='')
            else: raise AssertionError(action)
            return validator(value)
        with patch.object(rt,'run_action',side_effect=fake):report=runner.run(source,'合成测试品牌',dest,'仅验证离线导出')
        self.assertTrue(report['article_generated'],report)
        self.assertEqual(calls,['p0_blueprint','p0_draft','p0_edit','p0_style','p0_finalize','p0_titles','p0_title_review'])
        self.assertEqual(json.loads((dest/'production/p0_styled.json').read_text()), {'article_markdown':BODY})
        self.assertEqual(json.loads((dest/'production/p0_finalized.json').read_text())['article_markdown'],BODY)
        self.assertTrue((dest/'deliverables/article.docx').is_file())
        self.assertEqual(len(json.loads((dest/'deliverables/titles.json').read_text())['candidates']),20)


if __name__=='__main__': unittest.main()
