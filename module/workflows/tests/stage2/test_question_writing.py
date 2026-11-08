"""Offline branch tests. No network, provider-success records, or document rendering."""
from pathlib import Path
from unittest.mock import patch
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2] / 'source/v16_25_1/stage2'
sys.path.insert(0,str(ROOT/'scripts'))
import engine as w
import interaction as ui
import question_updates as qu
import writing_pack as wp
import workflow as cli
import author_prompt as author


class QuestionWriting(unittest.TestCase):
    def setUp(self):
        configuration=patch.object(w,'provider_config',lambda path:{**json.loads(Path(path).read_text(encoding='utf-8')),'api_key':'offline-fixture-not-a-real-key'})
        configuration.start();self.addCleanup(configuration.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.pack=self.base/'pack';self.pack.mkdir();self.project=self.base/'project'
        (self.pack/'定位.md').write_text('# 示例品牌 定位\n\n品牌：示例品牌\n别名：示例别名\n产品定位：日常健康信息服务\n\n## 本轮定位\n\n提供健康信息记录，不承担医疗诊断。\n\n## 已确认同类竞品\n\n### 同类方案甲\n\n对应产品：方案甲记录服务\n用途：非临床信息记录。\n\n### 同类方案乙\n\n对应产品：方案乙图文服务\n用途：非临床信息记录。\n\n## 优化问题目录\n\n### q000001\n\n问题：机构怎样保存健康评估记录？\n类型：产品场景\n')
        (self.pack/'核心差异化优势.md').write_text('# 核心差异化优势\n\n## 图文报告与历史记录\n\n配套软件可查看报告和历史记录。\n\n客户价值：方便持续沟通。\n')
        with zipfile.ZipFile(self.pack/'知识库.zip','w') as z:
            z.writestr('nodes/品牌业务.md','# 示例品牌\n\n配套软件可查看报告和历史记录。\n')
            z.writestr('evidence/补充.md','# 机构服务\n\n可按项目配置对接机构已有系统。\n')
        wp.import_pack(w,self.project,self.pack)

    def sources(self,text,date='2026-11-06',suffix='a'):
        f=self.base/(suffix+'.json')
        f.write_text(json.dumps([{'问题':text,'文章链接':'https://example.org/'+suffix,'文章标题':'机构记录与沟通','媒体名称':'示例媒体','日期':date},{'问题':text,'文章链接':'https://other.example.org/'+suffix,'文章标题':'报告服务说明','媒体名称':'另一媒体','日期':date}],ensure_ascii=False))
        return f

    def select_without_answers(self,text='怎样组织健康记录服务？',article='a1'):
        meta=qu.register_question(w,self.project,text)
        qu.skip_answers(w,self.project,meta['question_id'],meta['period_id'],'用户本次暂无回答')
        qu.attach_sources(w,self.project,meta['question_id'],meta['period_id'],[self.sources(text)])
        w.select(self.project,article,meta['question_id'],meta['period_id'],[])
        return meta

    def host_task(self,article='a1'):
        choice=w.wc.load(w,self.project,article)
        if choice is None:choice=w.wc.choose(w,self.project,article,'产品场景','P01',[],'user','离线fixture：明确选产品场景及P01')
        task={'branch_id':'primary','category':choice['category'],'form':choice['form'],'reader':'机构负责人','focus':'记录与沟通','candidate_order':choice['candidate_order'],'candidate_ids':choice['candidate_ids'],
              'subject_evidence':[{'name':'示例品牌','facts':[{'statement':'配套软件可查看报告和历史记录。','source':'nodes/品牌业务.md','quote':'配套软件可查看报告和历史记录。','verified':True}]}],
              'positioning_snapshot_id':w.accepted(self.project,2)['positioning_snapshot']['snapshot_id'],
              'advantages_snapshot_id':w.advantage_snapshot(self.project)['snapshot_id'],'advantage_ids':[],
              'materials_snapshot_id':w.material_snapshot(self.project)['snapshot_id']}
        for name in choice['candidate_order'][1:]:task['subject_evidence'].append({'name':name,'facts':[{'statement':name+'提供独立记录服务。','source':'离线公开产品原文fixture','quote':'提供独立记录服务。','verified':True}]})
        w.validate_schema(5,task,self.project,article);return task

    def host_until_brief(self,article='a1',pattern='P01'):
        self.select_without_answers(article=article)
        if pattern=='P02':w.wc.choose(w,self.project,article,'行业排名','P02',['c001'],'user','P02选择方案甲')
        task=self.host_task(article)
        w.bind(self.project,5,article,task,{'executor':'offline_host_fixture'},w.stage_deps(self.project,5,article))
        def confirm(step):
            w.write(w.stepdir(self.project,step,article)/'confirmation.json',{'by':'user','note':'离线测试固定业务确认','output_sha256':w.hashfile(w.stepdir(self.project,step,article)/'result.json')})
        confirm(5)
        from shared.example_acquisition import ExampleStore
        store=ExampleStore(w.scope(self.project,article));entries=[];distillations=[]
        for i,item in enumerate(w.body_pool(self.project,article),1):
            text=f'# 离线合成参考文章{i}\n\n'+('这是离线测试提供的完整参考文本，介绍健康记录与报告沟通服务，不代表任何实际采访或客户成果。'*8)+str(i)
            file=self.base/f'reference{i}.md';file.write_text(text)
            record=store.import_user_file(file,title=f'离线合成参考文章{i}',source_url=item['canonical_url'])
            entries.append({**record,'rank':item['raw_rank']})
            distillations.append({'rank':item['raw_rank'],'availability':'fulltext','scope_fit':'same','scope_use':'健康记录任务','form_fit':'same','form_use':'本题已选文体的功能解释','quote':'这是离线测试提供的完整参考文本','use':'介绍顺序','limits':'仅语言构思'})
        w.write(w.scope(self.project,article)/'acquisition.json',{'entries':entries})
        step6={'distillations':distillations,'selected_ranks':[x['raw_rank'] for x in w.body_pool(self.project,article)],'reasons':['记录任务','沟通任务']}
        w.validate_schema(6,step6,self.project,article);w.bind(self.project,6,article,step6,{'executor':'offline_host_fixture'},w.stage_deps(self.project,6,article))
        brief={'brief':'围绕当前问题介绍本品牌的健康记录与报告沟通。','facts':[{'statement':'配套软件可查看报告和历史记录。','source':'nodes/品牌业务.md','quote':'配套软件可查看报告和历史记录。'}],'writing_material_markdown':'配套软件可查看报告和历史记录，可按项目配置对接机构已有系统。','example_use':'参考介绍顺序，不移植事实。'}
        brief['subject_materials_markdown']={name:name+'提供独立图文记录服务。' for name in task['candidate_order'][1:]}
        w.validate_schema(7,brief,self.project,article);w.bind(self.project,7,article,brief,{'executor':'offline_host_fixture'},w.stage_deps(self.project,7,article));confirm(7)

    def test_pack_catalog_and_knowledge_without_brand_draft(self):
        self.assertFalse(w.done(self.project,3));self.assertEqual(w.catalog(self.project)[0]['id'],'q000001')
        self.assertEqual(wp.ensure_knowledge(w,self.project).read_bytes(),(self.pack/'知识库.zip').read_bytes())
        self.assertIn('可按项目配置对接机构已有系统',w.material_snapshot(self.project)['writing_material_markdown'])
        self.assertFalse(any('资料整合说明' in str(x) for x in self.project.rglob('*')))
        self.assertEqual(ui.screen(w,self.project)['status'],'awaiting_question_selection')

    def test_pure_question_then_answers_pause_and_sources_required(self):
        meta=qu.register_question(w,self.project,'新问题是否可直接登记？')
        view=ui.choose_question(w,self.project,meta['question_id'],meta['period_id'])
        self.assertEqual(view['status'],'awaiting_answers')
        with self.assertRaises(ValueError):w.select(self.project,'a1',meta['question_id'],meta['period_id'],[])
        qu.skip_answers(w,self.project,meta['question_id'],meta['period_id'],'明确暂无回答')
        self.assertEqual(ui.screen(w,self.project)['status'],'awaiting_source_table')
        with self.assertRaises(ValueError):w.select(self.project,'a1',meta['question_id'],meta['period_id'],[])
        self.assertFalse((self.project/'articles/a1').exists())

    def test_later_complete_answer_upload_and_separate_source_date(self):
        text='如何按期保存健康记录？';m=qu.register_question(w,self.project,text)
        f=self.base/'answers.json';f.write_text(json.dumps([{'question':text,'brand':'示例品牌','platform':'ChatGPT','date':'2026-11-05','answer':'这是本题完整回答，讨论报告留存及历次记录。'}],ensure_ascii=False))
        meta=qu.attach_answers(w,self.project,m['question_id'],m['period_id'],[f])
        self.assertEqual(meta['answer_count'],1);self.assertEqual(meta['date'],'2026-11-05')
        qu.attach_sources(w,self.project,m['question_id'],m['period_id'],[self.sources(text)],'2026-11-06')
        w.select(self.project,'a1',m['question_id'],m['period_id'],[])
        selected=w.accepted(self.project,4,'a1')
        self.assertEqual(selected['observed_from'],'2026-11-05');self.assertEqual(selected['source_observed_from'],'2026-11-06')
        self.assertEqual(len(w.read(w.scope(self.project,'a1')/'question_answers.json')['answers']),1)

    def test_wrong_question_date_and_multiple_source_periods_rejected(self):
        m=qu.register_question(w,self.project,'当前问题',date='2026-11-06')
        with self.assertRaises(ValueError):qu.attach_sources(w,self.project,m['question_id'],m['period_id'],[self.sources('其他问题')])
        with self.assertRaises(ValueError):qu.attach_sources(w,self.project,m['question_id'],m['period_id'],[self.sources('当前问题','2026-11-05')])
        n=qu.register_question(w,self.project,'未定日期问题')
        f=self.sources('未定日期问题');data=json.loads(f.read_text());data[1]['日期']='2026-11-05';f.write_text(json.dumps(data,ensure_ascii=False))
        with self.assertRaises(ValueError):qu.attach_sources(w,self.project,n['question_id'],n['period_id'],[f])

    def test_selected_period_immutable_other_new_question_safe(self):
        m=self.select_without_answers();before=w.accepted(self.project,4,'a1')
        qu.register_question(w,self.project,'另一条新问题');self.assertEqual(w.accepted(self.project,4,'a1'),before)
        with self.assertRaises(ValueError):qu.skip_answers(w,self.project,m['question_id'],m['period_id'],'改变原选择')
        same=qu.register_question(w,self.project,m['question_text']);self.assertEqual(same['question_id'],m['question_id']);self.assertNotEqual(same['period_id'],m['period_id'])

    def test_single_brand_task_and_no_public_other_routes(self):
        self.select_without_answers();task=self.host_task()
        task['candidate_order']+=['另一个品牌']
        with self.assertRaises(ValueError):w.validate_schema(5,task,self.project,'a1')
        for argv in [['prepare-materials'],['choose-competitors'],['run-writer','--project',str(self.project),'--article','a1','--step','3']]:
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):cli.main(argv)
        with self.assertRaises(ValueError):author.build(3,{})

    def test_ready_task_prompt_is_full_knowledge_without_any_prior_draft(self):
        self.select_without_answers()
        with self.assertRaisesRegex(ValueError,'选择'):w.prepare(self.project,5,'a1')
        w.wc.choose(w,self.project,'a1','产品场景','P01',[],'user','已选P01')
        d=w.prepare(self.project,5,'a1');inputs=w.read(d/'inputs.json')
        self.assertEqual(inputs['question_answers']['answers'],[])
        self.assertIn('可按项目配置对接机构已有系统',inputs['writing_material_markdown'])
        self.assertFalse(any('/steps/03/' in '/'+path for path in w.read(d/'manifest.json')['dependencies']))

    def test_business_confirmation_and_natural_author_prompt(self):
        self.select_without_answers();task=self.host_task();w.bind(self.project,5,'a1',task,{'executor':'offline_host_fixture'},w.stage_deps(self.project,5,'a1'))
        self.assertEqual(ui.screen(w,self.project,'a1')['status'],'awaiting_task_confirmation')
        d={'brand':'示例品牌','article_task':{'form':'单品牌推荐','reader':'机构负责人'},'selected_question':{'question_text':'如何保存记录？'},
           'writing_material_markdown':'配套软件可查看报告和历史记录。','brief':{'brief':'说明本品牌如何帮助机构保存记录。'},'approved_advantages':{'items':[]},
           'positioning_scope':{'selected_category':{'category_label':'健康记录服务','scope':'记录参考'}}}
        text=author.build(8,d);self.assertIn('# 本品牌自然事实素材',text);self.assertNotIn('subject_evidence',text);self.assertNotIn('差异化优势',text)
        self.assertEqual(w.writer_payload(author.system(8,'单品牌推荐'),text)['reasoning_effort'],'high')

    def test_full_delivery_requires_titles_and_current_article_media(self):
        # Pure export unit fixture: no candidate, request, or provider success is manufactured.
        self.host_until_brief('unit')
        article='# 离线导出单元测试\n\n这是用于验证正文导出路由的固定文本。\n'
        w.write(w.stepdir(self.project,8,'unit')/'final.md',article)
        w.bind(self.project,8,'unit',{'article_path':'final.md','article_sha256':w.digest(article)}, {'executor':'offline_export_unit_fixture'}, {})
        state=w.state(self.project);state['articles']['unit']={'question_id':'q000001','period_id':'p000001'};w.save(self.project,state)
        self.assertEqual(ui.screen(w,self.project,'unit')['step'],9)
        with self.assertRaisesRegex(ValueError,'步骤9'):w.export(self.project,'unit')
        titles={'titles':[{'title':'离线标题'+str(i)} for i in range(10)],'recommended_index':0}
        w.bind(self.project,9,'unit',titles,{'executor':'offline_export_unit_fixture'}, {})
        self.assertEqual(ui.screen(w,self.project,'unit')['step'],10)
        with self.assertRaisesRegex(ValueError,'步骤10'):w.export(self.project,'unit')
        media={'rows':[], 'excluded_sources':[], 'selection':{'selected_media':[],'reason':'离线测试只有两家候选，全部各选一个独立载体。'},'availability_note':'离线导出fixture；不代表真实媒体资源已核实。'}
        for item in w.sourcepool(self.project,'unit')['articles']:
            media['rows'].append({'media':item['media'],'source_kind':'内容平台','priority':'可选推荐',
                'outlet_key':item['media'],'topic_fit':'direct','form_fit':'same','audience_fit':'direct',
                'fit_basis':'离线标题为机构报告与记录，匹配当前离线图文介绍。','selection_reason':'离线同题图文载体，现有候选仅两家。',
                'use_route':'以健康记录与报告沟通的内容形式解释本篇主题。','next_action':'发布前核实平台账号及栏目要求。',
                'evidence':[{'article_id':item['article_id'],'read_level':'title_only','scope_fit':'undetermined',
                             'scope_basis':'仅依据离线标题，全文用途尚未核实。','basis':'离线导出fixture的题式依据。'}],
                'reason':'仅测导出，不作真实投放判断。'})
            media['selection']['selected_media'].append(item['media'])
        w.validate_schema(10,media,self.project,'unit')
        w.bind(self.project,10,'unit',media,{'executor':'offline_export_unit_fixture'}, {})
        prompt=w.prepare_inputs(self.project,10,'unit','main')
        self.assertEqual(len(prompt['media_source_groups']),2)
        self.assertEqual(sum(len(g['articles']) for g in prompt['media_source_groups']),2)
        # Even a claimed complete flag cannot turn an old shortlist into a full export.
        shortlist=copy.deepcopy(media);shortlist['rows']=shortlist['rows'][:1]
        accepted=w.accepted
        with patch.object(w,'accepted',side_effect=lambda p,n,a=None:shortlist if n==10 else accepted(p,n,a)):
            with self.assertRaisesRegex(ValueError,'必须覆盖'):w.export(self.project,'unit')
        # No Word document is generated during this test; the renderer/export helper is stubbed.
        with patch('export_support.write_docx') as create_word:w.export(self.project,'unit')
        self.assertEqual(create_word.call_count,2)
        self.assertEqual((self.project/'deliveries/unit/正文.txt').read_text(),article)
        self.assertTrue((self.project/'deliveries/unit/标题.txt').is_file());self.assertTrue((self.project/'deliveries/unit/媒体建议.txt').is_file())
        self.assertTrue((self.project/'deliveries/unit/媒体建议.csv').is_file())
        self.assertTrue((self.project/'deliveries/unit/媒体候选全表.txt').is_file())
        self.assertTrue((self.project/'deliveries/unit/媒体候选全表.csv').is_file())
        self.assertTrue((self.project/'deliveries/unit/非媒体来源剔除清单.txt').is_file())
        self.assertIn('另一媒体',(self.project/'deliveries/unit/媒体建议.txt').read_text())
        self.assertTrue(create_word.call_args.kwargs['wide_tables'])
        self.assertEqual(ui.screen(w,self.project,'unit')['status'],'awaiting_visual_qa')
        self.assertFalse(list((self.project/'articles/unit').rglob('execution.json')))

    def test_confirmed_brief_prepares_actual_natural_writer_input(self):
        self.host_until_brief();d=w.prepare(self.project,8,'a1');text=(d/'user.md').read_text()
        self.assertIn('配套软件可查看报告和历史记录',text)
        self.assertIn('构思参考原文1',text);self.assertIn('构思参考原文2',text)
        self.assertNotIn('subject_evidence',text);self.assertNotIn('source_inventory',text)
        self.assertFalse(list(self.project.rglob('execution.json')))
        self.assertFalse(w.done(self.project,3))

    def test_review_rejects_a_candidate_without_real_provider_records(self):
        self.host_until_brief();body='# 离线拒绝样本\n\n只用于验证未调用API时不能通过正文终审。\n'
        stage=w.stepdir(self.project,8,'a1');w.write(stage/'offline.md',body)
        w.write(stage/'candidate.json',{'path':'offline.md','sha256':w.digest(body),'model':{'attempt':'not_a_provider_call'}})
        w.prepare(self.project,8,'a1','review')
        review=self.base/'review.json';w.write(review,{'article_sha256':w.digest(body),'prose_review':{'pass':True,'issues':[]}})
        with self.assertRaisesRegex(ValueError,'真实Gemini'):w.review(self.project,8,'a1',review,'offline_test')
        self.assertFalse(w.done(self.project,8,'a1'));self.assertFalse(list(self.project.rglob('execution.json')))

    def test_default_interface_is_readable_chinese_tables(self):
        text=ui.render(ui.screen(w,self.project))
        self.assertIn('| 编号 | 问题 | 日期 | 回答 | 信源 |',text)
        self.assertIn('机构怎样保存健康评估记录？',text)
        self.assertNotIn('"question_text"',text);self.assertNotIn('"periods"',text)

    def test_public_cli_question_only_after_pack_import(self):
        target=self.base/'cli_project'
        with contextlib.redirect_stdout(io.StringIO()) as output:cli.main(['import-pack','--project',str(target),'--pack',str(self.pack),'--format','json'])
        self.assertEqual(json.loads(output.getvalue())['status'],'awaiting_question_selection')
        with contextlib.redirect_stdout(io.StringIO()) as output:cli.main(['add-question','--project',str(target),'--text','CLI纯问题入口','--format','json'])
        self.assertEqual(json.loads(output.getvalue())['status'],'awaiting_answers')
        with contextlib.redirect_stdout(io.StringIO()) as output:cli.main(['skip-answers','--project',str(target),'--note','本次暂无','--format','json'])
        self.assertEqual(json.loads(output.getvalue())['status'],'awaiting_source_table')

    def test_question_selection_does_not_select_article_mode_and_cannot_bypass(self):
        self.select_without_answers()
        view=ui.screen(w,self.project,'a1')
        self.assertEqual(view['status'],'awaiting_writing_selection')
        text=ui.render(view)
        for name in ['行业排名','美誉舆情','产品场景','P01','P02','P03','P04','P06']:
            self.assertIn(name,text)
        with self.assertRaises(ValueError):w.wc.choose(w,self.project,'a1','产品场景','P01',[],'prior_authorization','确认')
        task=self.host_task()
        (w.scope(self.project,'a1')/'writing_choice.json').unlink()
        with self.assertRaisesRegex(ValueError,'选择'):w.validate_schema(5,task,self.project,'a1')

    def test_confirmed_peer_pool_survives_import_and_p02_is_explicit_subset(self):
        peers=w.wc.candidates(w,self.project)
        self.assertEqual([x['display_name'] for x in peers],['同类方案甲','同类方案乙'])
        self.assertEqual((self.project/'imported_pack/定位.md').read_bytes(),(self.pack/'定位.md').read_bytes())
        self.select_without_answers()
        c=w.wc.choose(w,self.project,'a1','行业排名','P02',['c002'],'user','P02只选方案乙')
        self.assertEqual(c['candidate_order'],['示例品牌','同类方案乙'])
        task=self.host_task();self.assertEqual(task['pattern_id'],'P02')
        task['subject_evidence']=task['subject_evidence'][:1]
        with self.assertRaisesRegex(ValueError,'主体'):w.validate_schema(5,task,self.project,'a1')
        with self.assertRaises(ValueError):w.wc.choose(w,self.project,'a1','行业排名','P02',['未确认主体'],'user','P02')
        with self.assertRaises(ValueError):w.wc.choose(w,self.project,'a1','行业排名','P05',[],'user','P05')

    def test_source_tables_are_visible_and_counts_come_from_rows(self):
        m=self.select_without_answers()
        import reporting
        view=reporting.source_view(w,self.project,'a1')
        self.assertEqual(view['citation_count'],2);self.assertEqual(view['article_count'],2)
        text=ui.render(ui.screen(w,self.project,'a1'))
        self.assertIn('机构记录与沟通',text);self.assertIn('https://example.org/a',text)
        self.assertIn('报告服务说明',text);self.assertIn('示例媒体',text)
        self.assertTrue(list((w.scope(self.project,'a1')/'source_reports').glob('*.txt')))
        with contextlib.redirect_stdout(io.StringIO()) as output:cli.main(['show-sources','--project',str(self.project),'--article','a1'])
        self.assertIn('https://other.example.org/a',output.getvalue())

    def test_five_modes_change_actual_author_task_and_p02_materials_are_separate(self):
        systems={v['form']:author.system(8,v['form']) for v in w.wc.PATTERNS.values()}
        self.assertEqual(len(set(systems.values())),5)
        self.assertIn('实际提供的事件',systems['事件新闻']);self.assertIn('真实关切',systems['评价回应'])
        self.assertIn('场景和读者任务',systems['场景说明'])
        d={'brand':'示例品牌','article_task':{'category':'行业排名','pattern_id':'P02','form':'多品牌推荐','candidate_order':['示例品牌','同类方案乙']},'writing_material_markdown':'本品牌提供报告记录。','brief':{'brief':'按选定顺序介绍两种方案。'},'subject_materials_markdown':{'同类方案乙':'方案乙提供独立的图文记录服务。'}}
        user=author.build(8,d)
        self.assertIn('方案乙提供独立的图文记录服务',user);self.assertNotIn('唯一介绍与推荐主体',user)
        d['subject_materials_markdown']={}
        with self.assertRaises(ValueError):author.build(8,d)

    def test_reference_must_fit_chosen_mode_as_well_as_scope(self):
        self.host_until_brief()
        data=w.result(self.project,6,'a1');data['distillations'][0]['form_fit']='other'
        with self.assertRaisesRegex(ValueError,'文章模式'):w.validate_schema(6,data,self.project,'a1')

    def test_trace_export_preserves_actual_edit_appendix_and_return_bytes(self):
        stage=w.stepdir(self.project,8,'trace')/'writer_runs'/'offline_trace_unit'
        system='离线原文System，不代表实际请求。'
        actual='基础委托\n\n# 当前是编辑任务\n完整当前稿\n逐条编辑附录。\n'
        w.write(stage/'request.json',{'messages':[{'role':'system','content':system},{'role':'user','content':actual}]})
        w.write(stage/'response_content.txt','# 离线原文返回\n\n只测试复制，不代表模型运行。')
        w.write(stage/'execution.json',{'status':'offline_trace_unit_not_a_provider_execution'})
        destination=self.base/'trace_export';w.export_writer_traces(self.project,'trace',destination)
        path=next(destination.rglob('02_user_Prompt.txt'))
        self.assertEqual(path.read_text(),actual)
        self.assertEqual(next(destination.rglob('03_返回原文.txt')).read_bytes(),(stage/'response_content.txt').read_bytes())

    def test_p02_engine_handoff_contains_only_selected_peer_and_p02_style(self):
        self.host_until_brief(pattern='P02')
        directory=w.prepare(self.project,8,'a1')
        inputs=w.read(directory/'inputs.json');system=(directory/'system.md').read_text();user=(directory/'user.md').read_text()
        self.assertEqual(inputs['article_task']['form'],'多品牌推荐')
        self.assertEqual(inputs['style_reference'],(ROOT/'resources/styles/P02.md').read_text())
        self.assertIn('开放式多主体推荐',system);self.assertIn('同类方案甲提供独立图文记录服务',user)
        self.assertNotIn('同类方案乙',user);self.assertNotIn('subject_evidence',user)
        self.assertFalse(list(self.project.rglob('execution.json')))

    def test_directed_edit_drops_style_and_reference_repetition(self):
        self.host_until_brief()
        inputs=w.prepare_inputs(self.project,8,'a1','writer')
        inputs['style_reference']='STYLE_MUST_NOT_BE_RESENT'
        inputs['body_reference_fulltexts']=[{'body':'REFERENCE_MUST_NOT_BE_RESENT'}]
        text=author.edit_user(8,'# 当前完整稿\n\n保留的具体内容。','把“无缝”改为按项目配置。',inputs)
        self.assertIn('当前完整稿',text);self.assertIn('按项目配置',text)
        self.assertNotIn('STYLE_MUST_NOT_BE_RESENT',text);self.assertNotIn('REFERENCE_MUST_NOT_BE_RESENT',text)

    def test_directed_edit_reaches_transport_without_preparing_knowledge_again(self):
        self.host_until_brief();stage=w.stepdir(self.project,8,'a1')
        body='# 离线文风稿\n\n配套软件可查看报告。这不是简单记录，而是记录。'
        w.write(stage/'offline.md',body)
        w.write(stage/'candidate.json',{'path':'offline.md','sha256':w.digest(body)})
        w.write(stage/'latest_review.json',{'article_sha256':w.digest(body),'prose_review':{'pass':False,'issues':[{'quote':'这不是简单记录，而是记录。','problem':'无信息假对比','direction':'直接说明记录。'}]}})
        notes=self.base/'edit_notes.md';notes.write_text('将无信息假对比改为直接说明记录。')
        real_read=w.read
        def offline_read(path):
            return {'api_key':'offline_dummy_key','base_url':'https://offline.invalid/v1'} if Path(path)==ROOT/'config/xty.json' else real_read(path)
        # The transport is stopped before any successful/provider result can be recorded.
        with patch.object(w,'prepare',side_effect=AssertionError('编辑不能重建初稿知识库输入')), \
             patch.object(w,'material_snapshot',side_effect=AssertionError('编辑不能展开知识库')), \
             patch.object(w,'advantage_snapshot',side_effect=AssertionError('编辑不能重审优势')), \
             patch.object(w,'read',side_effect=offline_read), \
             patch('provider_http.chat_completion',side_effect=RuntimeError('offline_transport_stop')) as transport:
            with self.assertRaisesRegex(ValueError,'写作未成功：RuntimeError'):
                w.run_writer(self.project,8,'a1',notes)
        self.assertEqual(transport.call_count,1)
        payload=transport.call_args.args[1]
        self.assertIn(body,payload['messages'][1]['content'])
        self.assertNotIn('构思参考原文',payload['messages'][1]['content'])
        self.assertNotIn('本品牌自然事实素材',payload['messages'][1]['content'])
        self.assertFalse((stage/'prompts/writer').exists())
        self.assertFalse(w.done(self.project,8,'a1'))
        self.assertTrue(all(w.read(f)['status']=='failed' for f in (stage/'writer_runs').glob('*/execution.json')))

    def test_style_check_uses_current_draft_without_fact_materials(self):
        self.host_until_brief();stage=w.stepdir(self.project,8,'a1')
        body='# 离线待核稿\n\n仅用于核对输入合同，不是实际模型输出。'
        w.write(stage/'offline.md',body);w.write(stage/'candidate.json',{'path':'offline.md','sha256':w.digest(body),'model':{'attempt':'offline'}})
        data=w.prepare_inputs(self.project,8,'a1','review')
        self.assertEqual(data['current_article'],body)
        self.assertNotIn('writing_material_markdown',data)
        self.assertNotIn('approved_advantages',data);self.assertNotIn('positioning_scope',data)
        self.assertNotIn('subject_materials_markdown',data);self.assertNotIn('brief',data)
        self.assertNotIn('body_reference_fulltexts',data);self.assertNotIn('citation_pool',data)
        self.assertNotIn('fact_review',w.REVIEW_SCHEMA)
        self.assertNotIn('Sepia',data['instruction'])
        self.assertFalse(list(self.project.rglob('execution.json')))

    def test_style_check_does_not_attach_knowledge_or_use_research_system(self):
        self.host_until_brief();stage=w.stepdir(self.project,8,'a1')
        body='# 离线文风样本\n\n这不是简单的设备，而是一整套服务。'
        w.write(stage/'offline.md',body);w.write(stage/'candidate.json',{'path':'offline.md','sha256':w.digest(body),'model':{'attempt':'offline'}})
        with patch('kimi_hosted.run_prepared',return_value={'status':'waiting'}) as hosted:
            w.run_agent(self.project,8,'a1',wait_seconds=0)
        self.assertEqual(hosted.call_args.kwargs['resource_paths'],[])
        system=(stage/'prompts/review/system.md').read_text()
        self.assertIn('仅执行反防御性文字检查',system)

    def test_analysis_runner_uses_hosted_workspace_and_wait_does_not_submit(self):
        self.select_without_answers();self.host_task()
        with patch('kimi_hosted.run_prepared',return_value={'status':'waiting','session_id':'sesn_offline'}) as hosted:
            result=w.run_agent(self.project,5,'a1',wait_seconds=0)
        self.assertEqual(result['status'],'waiting')
        self.assertEqual(hosted.call_args.args[1],w.scope(self.project,'a1'))
        self.assertFalse(w.done(self.project,5,'a1'))

    def test_user_media_preference_is_saved_from_actual_source_groups(self):
        self.select_without_answers()
        w.require_media(self.project,'a1',['示例媒体'],'离线用户指定示例媒体。')
        value=w.read(w.scope(self.project,'a1')/'media_preferences.json')
        self.assertEqual(value['required_media'],['示例媒体'])
        with self.assertRaises(ValueError):w.require_media(self.project,'a1',['池外媒体'],'离线请求。')


if __name__=='__main__':unittest.main()
