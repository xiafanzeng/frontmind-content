"""Offline request/Pack/selection regressions. Not a model writing-quality test."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from shared import model_runtime as runtime, p0_titles
from shared import question_bank_import as bank
from shared.writing_context import prompt_titles, prompt_title_review
from Reference_Pack_Workflow.shared import reference_pack_builder as builder
from scripts.tests_v411 import test_workflow_v411 as old

ROOT = Path(__file__).resolve().parents[2]
# Public regression fixtures are generated below; customer exports are never required.


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    return path


def row(q='问题甲', platform='平台甲', text='原始段落一。\n\n原始段落二。', date='2026-6-22', **extra):
    return {'监控问题':q,'AI大模型':platform,'回答内容':text,'监控日期':date, **extra}


class TitleContract4131Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.wf=SimpleNamespace(load_state=lambda _: {'metadata':{},'selected_pattern_id':'P03'})
        self.body='# 旧主标题\n\n机构品牌介绍。\n\n## 业务\n实际服务与必要条件。'
        self.titles={'canonical_title_id':'title_01','candidates':[{'title':f'候选{n}', 'angle':'整体机构'} for n in range(20)]}

    def test_p0_generator_actual_request_uses_brand_skill(self):
        p=prompt_titles(self.wf,self.root,p0=True,final_markdown=self.body)
        messages=runtime.build_payload('p0_titles',p)['messages']
        self.assertEqual(p0_titles.system('p0_titles'),messages[0]['content'])
        self.assertIn('同一篇成稿的替代主标题',messages[0]['content'])
        self.assertNotIn('旧主标题',p)
        self.assertIn(self.body.split('\n',1)[1],p)
        self.assertNotIn('品牌特点',self.body)  # never fabricate input from task schema

    def test_host_title_review_uses_same_genre_and_can_replace_whole_set(self):
        p=prompt_title_review(self.wf,self.root,p0=True,final_markdown=self.body,title_result=self.titles)
        self.assertTrue(p0_titles.matches('p0_title_review',p))
        messages=runtime._initial_messages('p0_title_review',p)
        self.assertIn('可以重拟全部20项',messages[0]['content'])
        self.assertIn('实际改过的完整20项',p)
        self.assertIn('单独调用submit_result',p)
        self.assertNotIn('旧主标题',p)

    def test_question_titles_do_not_get_brand_rules(self):
        p=prompt_titles(self.wf,self.root,p0=False,final_markdown=self.body)
        self.assertFalse(p0_titles.matches('article_titles',p))
        self.assertEqual(runtime.DEEPSEEK_TITLES_SYSTEM,runtime.build_payload('article_titles',p)['messages'][0]['content'])
        self.assertIn('问题优化提供20个标题',p)

    def test_legacy_unmarked_title_request_keeps_legacy_system(self):
        p='legacy saved title request'
        self.assertEqual(runtime.DEEPSEEK_TITLES_SYSTEM,runtime._initial_messages('p0_titles',p)[0]['content'])

    def test_empty_skill_fails_instead_of_silent_fallback(self):
        f=self.root/'skill.md';f.write_text('  ')
        with mock.patch.object(p0_titles,'RESOURCE',f):
            with self.assertRaises(ValueError):p0_titles.system('p0_titles')

    def test_title_source_does_not_require_blueprint_or_medical_brand_examples(self):
        skill=p0_titles.guidance()
        self.assertNotIn('台心',skill)
        self.assertIn('机构的归属',skill.replace('科室的归属','机构的归属'))
        self.assertIn('不是禁用词',skill)
        self.assertIn('不强制统一句长',skill)


class MonitoringImport4131Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from datetime import datetime
        from openpyxl import Workbook
        temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(temp.cleanup)
        cls.table = Path(temp.name) / 'synthetic-export-20260830.xlsx'
        workbook = Workbook(); sheet = workbook.active
        sheet.append(['监控问题', 'AI大模型', '回答内容', '监控日期'])
        for q in range(1, 34):
            for n in range(12 if q == 33 else 10):
                sheet.append([f'合成企业服务问题{q}', '平台甲' if n % 2 else '平台乙',
                              f'第{q}题第{n}份合成回答。\n\n完整第二段。', datetime(2026, 6, 22)])
        workbook.save(cls.table)
        cls.artifacts,cls.index,cls.report=bank.build_artifacts(cls.table,brand='合成企业')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def data(self,rows):return dump(self.root/'monitor.json',rows)

    def pack(self):
        f=self.root/'business.md';f.write_text('合成企业仅用于软件测试。')
        builder.create_reference_pack(brand_name='合成企业',knowledge_base=[f],output=self.root/'old')
        return self.root/'old'

    def test_synthetic_table_33_questions_332_answers(self):
        self.assertEqual((33,332,332),(self.report['question_count'],self.report['row_count'],self.report['answer_count']))
        self.assertEqual(33,len(self.index['questions']))

    def test_synthetic_dates_are_cell_dates_not_filename(self):
        self.assertEqual(['2026-06-22'],self.report['observed_dates'])
        self.assertEqual('2026-06-22',self.index['periods'][0]['observed_to'])

    def test_synthetic_platforms_provenance_and_full_answers(self):
        observed=[a for s in self.index['slices'] for a in self.artifacts[s['monitoring_path']]['answers']]
        raw=bank.export_rows(self.table)
        byrow={r['__frontmind_source_row__']:r for _,r in raw if r.get('监控问题') and r.get('回答内容')}
        self.assertEqual({'平台甲','平台乙'},{a['platform'] for a in observed})
        for a in observed:
            self.assertEqual(byrow[a['source_record']['row']]['回答内容'],a['answer_text'])
            self.assertTrue(a['source_record']['file_sha256'].startswith('sha256:'))
        self.assertEqual(332,len(observed))

    def test_synthetic_source_order_and_last_question_preserved(self):
        self.assertEqual('q000033',self.index['questions'][-1]['question_uid'])
        self.assertIn('合成企业服务问题33',self.index['questions'][-1]['question_text'])
        self.assertTrue(all(q['question_id'] is None for q in self.index['questions']))

    def test_no_source_workbook_needed_and_citations_not_invented(self):
        for record in self.index['slices']:
            c=self.artifacts[record['citation_path']]
            self.assertEqual('not_supplied',c['availability'])
            self.assertEqual([],c['cited_content_pool'])
            self.assertEqual(2,record['platform_count'])

    def test_distinct_dates_do_not_complete_each_other(self):
        a,i,s=bank.build_artifacts(self.data([row(date='2026-6-22'),row(platform='平台乙',date='2026-8-30')]),brand='')
        self.assertEqual(2,len(i['periods']))
        self.assertEqual({'q000001':False},bank.readiness_for(i,lambda m:a[m]))

    def test_unknown_platform_is_not_second_platform(self):
        a,i,s=bank.build_artifacts(self.data([row(),row(platform='详细表格')]),brand='')
        self.assertFalse(bank.readiness_for(i,lambda m:a[m])['q000001'])

    def test_exact_text_keeps_linebreaks(self):
        text='  # 标题\n\n第一段\r\n第二段。  '
        a,i,s=bank.build_artifacts(self.data([row(text=text),row(platform='平台乙')]),brand='')
        self.assertEqual(text,a[i['slices'][0]['monitoring_path']]['answers'][0]['answer_text'])

    def test_wrong_brand_rejected_explicit_alias_accepted(self):
        f=self.data([row(品牌名称='乙品牌')])
        with self.assertRaises(ValueError):bank.build_artifacts(f,brand='甲品牌')
        a,i,s=bank.build_artifacts(f,brand='甲品牌',aliases=['乙品牌'])
        self.assertEqual(1,len(i['questions']))

    def test_bad_date_rejected_not_guessed(self):
        with self.assertRaises(ValueError):bank.build_artifacts(self.data([row(date='无效日期')]),brand='')

    def test_empty_dates_explicitly_undated(self):
        a,i,s=bank.build_artifacts(self.data([row(date='')]),brand='')
        self.assertIsNone(i['periods'][0]['observed_to'])
        self.assertTrue(s['warnings'])

    def test_internal_ids_stable_on_append(self):
        a,i,_=bank.build_artifacts(self.data([row('问题乙'),row('问题甲')]),brand='')
        ids={q['question_text']:q['question_uid'] for q in i['questions']}
        a,j,_=bank.build_artifacts(self.data([row('问题甲',date='2026-8-30'),row('问题丙',date='2026-8-30')]),brand='',existing_index=i)
        self.assertEqual(ids['问题甲'],next(q['question_uid'] for q in j['questions'] if q['question_text']=='问题甲'))
        self.assertEqual(3,len(j['questions']))

    def test_question_ids_follow_input_order_across_interleaved_dates(self):
        a,i,s=bank.build_artifacts(self.data([row('第一题',date='2026-8-30'),row('第二题',date='2026-6-22'),row('第三题',date='2026-8-30')]),brand='')
        self.assertEqual(['第一题','第二题','第三题'],[q['question_text'] for q in i['questions']])
        self.assertEqual(['q000001','q000002','q000003'],[q['question_uid'] for q in i['questions']])

    def test_exact_duplicate_import_is_noop(self):
        f=self.data([row()]);a,i,s=bank.build_artifacts(f,brand='')
        b,j,t=bank.build_artifacts(f,brand='',existing_index=i)
        self.assertEqual({},b);self.assertEqual(i,j);self.assertEqual('already_imported',t['status'])

    def test_source_id_collision_rejected(self):
        with self.assertRaises(ValueError):
            bank.build_artifacts(self.data([row('甲',问题ID='x'),row('乙',问题ID='x')]),brand='')

    def test_retired_question_not_reactivated(self):
        f=self.data([row()]);a,i,s=bank.build_artifacts(f,brand='')
        i=bank.qr.retire_question(i,'q000001')
        a,j,_=bank.build_artifacts(self.data([row(date='2026-8-30')]),brand='',existing_index=i)
        self.assertFalse(j['questions'][0]['formal_question_eligible'])

    def test_immutable_import_preserves_original_pack_and_business_files(self):
        pack=self.pack();before={p.relative_to(pack).as_posix():p.read_bytes() for p in pack.rglob('*') if p.is_file()}
        result=bank.import_into_pack(pack=pack,monitoring_answers=self.data([row(),row(platform='平台乙')]),output=self.root/'new')
        self.assertEqual(2,result['pack_version']);self.assertTrue(result['readiness']['question_ready']['q000001'])
        for member,raw in before.items():
            self.assertEqual(raw,(pack/member).read_bytes())
            if member not in {'reference_pack.json','materials/index.json'}:
                self.assertEqual(raw,(self.root/'new'/member).read_bytes())
        again=bank.import_into_pack(pack=self.root/'new',monitoring_answers=self.root/'monitor.json',output=self.root/'unused')
        self.assertEqual('already_imported',again['status']);self.assertFalse((self.root/'unused').exists())

    def test_initial_mixed_intake_routes_answers_out_of_facts(self):
        f=self.root/'business.md';f.write_text('普通企业材料。')
        monitor=self.data([row(text='AI_OUTPUT_MUST_NOT_BECOME_BUSINESS_FACT'),row(platform='平台乙')])
        result=builder.create_reference_pack(brand_name='合成企业',knowledge_base=[f,monitor],output=self.root/'mixed')
        registry=(self.root/'mixed/registries/knowledge_registry.json').read_text()
        self.assertNotIn('AI_OUTPUT_MUST_NOT_BECOME_BUSINESS_FACT',registry)
        self.assertTrue(result['readiness']['question_ready']['q000001'])

    def test_old_add_materials_entry_redirects_monitoring_only(self):
        pack=self.pack()
        result=builder.add_materials(pack=pack,materials=[self.data([row(),row(platform='平台乙')])],output=self.root/'new')
        self.assertIn('question_import',result)
        self.assertNotIn('positioning_reconfirmation_required',result)


class SelectionFlow4131Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Complete synthetic lifecycle with offline fixture only, never APIs.
        old.WorkflowV411Tests.setUpClass()
        cls.base=old.WorkflowV411Tests.base
        cls.legacy_pack=old.WorkflowV411Tests.p0_pack
        f=cls.base/'question_rows.json';dump(f,[row(),row(platform='平台乙'),row('问题乙'),row('问题乙',platform='平台乙')])
        result=bank.import_into_pack(pack=cls.legacy_pack,monitoring_answers=f,output=cls.base/'with_questions')
        cls.pack=Path(result['pack_path'])
    @classmethod
    def tearDownClass(cls):old.WorkflowV411Tests.tearDownClass()

    def start(self,name,pack=None):
        job=self.base/name
        old.run_cli('article','--reference-pack',str(pack or self.pack),'--job-dir',str(job),'--offline-fixture')
        self.assertEqual('awaiting_reference_pack_route',old.state(job)['status'])
        old.resume(job,'--reference-pack-route','use')
        return job

    def test_no_id_start_route_selection_then_reuse_answers(self):
        job=self.start('choose-question')
        self.assertEqual('awaiting_question_selection',old.state(job)['status'])
        self.assertIn('问题甲',old.page(job));self.assertIn('问题乙',old.page(job))
        self.assertEqual([],old.schema_errors(job/'job_state.json',ROOT/'shared/job_state.schema.json'))
        old.resume(job,'--question-id','2')
        self.assertEqual('awaiting_response_brief',old.state(job)['status'])
        self.assertEqual('问题乙',old.state(job)['question']['question_text'])
        originals=json.loads((job/'inputs/question_observations.json').read_text())
        self.assertEqual(2,len(originals['answers']))
        self.assertIn('原始段落一。\n\n原始段落二。',(job/'inputs/answer_01.md').read_text())
        self.assertFalse((job/'provider/answer_analysis/result.json').exists())

    def test_selection_empty_continue_does_not_progress(self):
        job=self.start('selection-empty');before=old.state(job)
        old.run_cli('continue','--job-dir',str(job))
        self.assertEqual(before,old.state(job))

    def test_selection_stale_revision_rejected(self):
        job=self.start('selection-stale')
        old.resume(job,'--question-id','1',revision=-1,expect=2)
        self.assertEqual('awaiting_question_selection',old.state(job)['status'])

    def test_missing_bank_offers_table_not_question_id(self):
        job=self.start('selection-no-bank',pack=self.legacy_pack)
        self.assertEqual('awaiting_question_selection',old.state(job)['status'])
        self.assertIn('导入已有监控问答表',old.page(job))
        old.resume(job,'--monitoring-answers',str(self.base/'question_rows.json'))
        self.assertEqual('awaiting_question_selection',old.state(job)['status'])
        self.assertEqual(2,len(old.state(job)['metadata']['question_selection_catalog']))

    def test_catalog_ready_values_and_identity_mismatch(self):
        rows=old.CONTROLLER.question_catalog(self.pack)
        self.assertTrue(all(x['ready'] for x in rows))
        with self.assertRaises(old.CONTROLLER.WorkflowError):
            old.CONTROLLER.select_question(self.pack,'q000001','另一个问题')

    def test_p0_and_positioning_members_survive_question_import(self):
        for base in ('p0','strategy','research/brand_market'):
            for file in (self.legacy_pack/base).rglob('*'):
                if file.is_file():self.assertEqual(file.read_bytes(),(self.pack/file.relative_to(self.legacy_pack)).read_bytes())
        root=json.loads((self.pack/'reference_pack.json').read_text())
        self.assertTrue(root['readiness']['p0_ready']);self.assertTrue(root['readiness']['positioning_ready'])

    def test_completed_p0_handoff_uses_actual_pack_catalog(self):
        output=io.StringIO()
        with redirect_stdout(output):old.CONTROLLER.emit_completed_delivery({'status':'p0_ready','reference_pack':str(self.pack)}, {})
        data=json.loads(output.getvalue())
        self.assertEqual(2,data['next_step']['ready_question_count'])
        self.assertFalse(data['next_step']['question_id_required_at_start'])
        self.assertNotIn('--question-id',data['next_step']['command'])

    def test_past_only_question_requires_explicit_period(self):
        f=self.base/'subset.json';dump(f,[row(date='2026-8-30'),row(platform='平台乙',date='2026-8-30')])
        result=bank.import_into_pack(pack=self.pack,monitoring_answers=f,output=self.base/'subset_pack')
        pack=Path(result['pack_path'])
        self.assertEqual(1,len(old.CONTROLLER.question_catalog(pack)))
        self.assertEqual(2,len(old.CONTROLLER.question_catalog(pack,all_periods=True)))
        with self.assertRaises(old.CONTROLLER.WorkflowError):old.CONTROLLER.select_question(pack,'q000002')
        q=old.CONTROLLER.select_question(pack,'q000002',period_id='p000001')
        self.assertEqual('2026-06-22',q['observed_to'])
        self.assertEqual(2,len(old.CONTROLLER.question_periods(pack)))

    def test_question_with_insufficient_current_platforms_pauses_not_old_fallback(self):
        f=self.base/'oneplatform.json';dump(f,[row(date='2026-8-30')])
        updated=bank.import_into_pack(pack=self.pack,monitoring_answers=f,output=self.base/'oneplatform_pack')
        job=self.start('incomplete-platform',pack=Path(updated['pack_path']))
        old.resume(job,'--question-id','1')
        self.assertEqual('awaiting_question_research_inputs',old.state(job)['status'])
        self.assertFalse((job/'inputs/answer_01.md').exists())

if __name__=='__main__':unittest.main()
