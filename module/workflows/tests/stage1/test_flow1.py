from pathlib import Path
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'source/v16_25_1/stage1'
sys.path.insert(0, str(ROOT / 'scripts'))
import workflow
import engine as w
import kb_positioning as kp
import author_prompt as author


class FlowOne(unittest.TestCase):
    def setUp(self):
        configuration=patch.object(w,'provider_config',lambda path:{**json.loads(Path(path).read_text(encoding='utf-8')),'api_key':'offline-fixture-not-a-real-key'})
        configuration.start();self.addCleanup(configuration.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.kb = self.base / 'knowledge.zip'
        with zipfile.ZipFile(self.kb, 'w') as z:
            z.writestr('nodes/brand.md', '# 测试企业\n\n提供非临床康养采集、报告与档案服务。')
            z.writestr('evidence/manual.md', '# 完整手册\n\n独有细节ABC：支持按项目对接和核心部件质保。')
            z.writestr('BUNDLE.json', json.dumps({'documents': ['nodes/brand.md', 'evidence/manual.md']}))
        self.project = self.base / 'project'
        workflow.initialize(self.project, '测试企业', self.kb)

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, name, value):
        path = self.base / name
        path.write_text(json.dumps(value, ensure_ascii=False))
        return path

    def position(self):
        kp.prepare(w, self.project)
        proposal = {'category_options': [{'id': 'c1', 'label': '非临床康养评估',
                   'scope': '体质与养生参考，不承担诊断处方。', 'reason': '知识库提供采集与报告。',
                   'fact_ids': ['k0001']}],
                   'optimization_questions': [{'question_text': '测试企业适合哪些康养场景？',
                                                'category': '产品场景', 'reason': '材料支持'}]}
        kp.submit(w, self.project, self.write_json('position.json', proposal), 'offline_fixture_host')
        kp.confirm(w, self.project, 'c1', 'user', '离线合成选择，不冒充真实企业确认')

    def advantages(self):
        self.position()
        w.ad.prepare(w, self.project)
        draft = {'advantages': [
            {'id': 'adv1', 'title': '组合采集', 'customer_value': '统一采集与查看', 'suggested_wording': '采集与报告组合。'},
            {'id': 'adv2', 'title': '机构系统对接', 'customer_value': '按项目接入业务', 'suggested_wording': '按项目接口配置。'}]}
        w.ad.submit(w, self.project, self.write_json('advantages.json', draft), 'offline_fixture_host')
        w.ad.confirm(w, self.project, ['adv2', 'adv1'], False, 'user', '离线合成顺序')

    def test_complete_source_import_no_summary(self):
        self.assertEqual(w.wp.ensure_knowledge(w, self.project).read_bytes(), self.kb.read_bytes())
        text = w.wp.snapshot(w, self.project)['writing_material_markdown']
        self.assertIn('独有细节ABC', text)
        self.assertIn('提供非临床康养采集', text)
        self.assertFalse(list(self.project.rglob('资料整合说明.md')))
        self.assertEqual(workflow.screen(self.project)['status'], 'ready_positioning')

    def test_pause_a_then_c_with_full_knowledge(self):
        kp.prepare(w, self.project)
        source = (w.stepdir(self.project, 2) / 'prompts/positioning/user.md').read_text()
        self.assertIn('独有细节ABC', source)
        self.advantages()
        prompt = (w.ad.folder(self.project) / 'prompts/user.md').read_text()
        self.assertIn('独有细节ABC', prompt)
        self.assertEqual(w.ad.snapshot(w, self.project)['selected_ids'], ['adv2', 'adv1'])

    def test_three_item_pack_preserves_kb_and_question_catalog(self):
        self.advantages()
        out = self.base / 'pack.zip'
        w.export_pack(self.project, out)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(set(z.namelist()), {'Reference_Pack/' + n for n in w.wp.PACK_FILES})
            self.assertEqual(z.read('Reference_Pack/知识库.zip'), self.kb.read_bytes())
            self.assertIn('测试企业适合哪些康养场景？', z.read('Reference_Pack/定位.md').decode())
        restored = self.base / 'restored'
        report = w.wp.import_pack(w, restored, out)
        self.assertEqual(report['questions'], 1)
        self.assertEqual(report['advantages'], 2)
        self.assertFalse(w.done(restored, 3))
        w.confirmed(restored, 2)

    def test_p0_prepared_from_kb_in_confirmed_order_without_paid_call(self):
        self.advantages()
        folder = w.prepare(self.project, 3, None, 'writer')
        user = (folder / 'user.md').read_text()
        self.assertIn('独有细节ABC', user)
        self.assertLess(user.index('## 1 机构系统对接'), user.index('## 2 组合采集'))
        self.assertIn('每项各设一个三级小标题', user)
        self.assertNotIn('brand_materials', user)
        self.assertFalse((w.stepdir(self.project, 3) / 'writer_runs').exists())

    def test_new_question_after_position_does_not_reposition(self):
        self.position()
        old = w.hashfile(w.stepdir(self.project, 2) / 'result.json')
        workflow.add_question(self.project, '新增用户问题是什么？')
        w.confirmed(self.project, 2)
        self.assertEqual(old, w.hashfile(w.stepdir(self.project, 2) / 'result.json'))

    def test_changed_source_blocks_stale_proposal(self):
        self.position()
        proposal = w.stepdir(self.project, 2) / 'positioning_proposal.json'
        proposal.write_text(proposal.read_text() + '\n')
        with self.assertRaises(ValueError):
            w.confirmed(self.project, 2)

    def test_malicious_knowledge_path_is_rejected(self):
        path = self.base / 'bad.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('../outside.md', 'bad')
        with self.assertRaises(ValueError):
            workflow.initialize(self.base / 'bad_project', '错误', path)

    def test_cli_does_not_expose_second_flow_or_summary_commands(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/workflow.py'), '--help'], text=True, capture_output=True, check=True)
        for forbidden in ['prepare-materials', 'submit-materials', 'choose-task', 'acquire', 'import-writing-pack']:
            self.assertNotIn(forbidden, result.stdout)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/workflow.py'), 'prepare', '--project', str(self.project), '--step', '8'], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_hosted_positioning_waits_and_preserves_business_choice(self):
        waiting={'status':'waiting','session_id':'session_offline_fixture','model':'kimi-k3.1-pro','reasoning_effort':'high'}
        with patch('kimi_hosted.run_prepared',return_value=waiting) as runner:
            result=w.run_agent(self.project,'positioning',0)
        self.assertEqual(result['status'],'waiting')
        self.assertFalse((w.stepdir(self.project,2)/'positioning_proposal.json').exists())
        args,kwargs=runner.call_args
        self.assertEqual(args[1],self.project.resolve())
        self.assertEqual(args[3],'positioning')
        self.assertEqual(kwargs['wait_seconds'],0)
        self.assertEqual(kwargs['resource_paths'][0].read_bytes(),self.kb.read_bytes())

    def test_hosted_result_is_submitted_before_pause_a(self):
        proposal={'category_options':[{'id':'c1','label':'非临床康养评估','scope':'体质与养生参考。','reason':'离线知识库fixture。','fact_ids':['k0001']}],
                  'optimization_questions':[{'question_text':'机构怎样组织评估？','category':'产品场景'}]}
        path=self.write_json('hosted_offline_proposal.json',proposal)
        result={'status':'succeeded','result_file':str(path),'run_dir':'offline_fixture_only','session_id':'session_offline_fixture','model':'kimi-k3.1-pro','reasoning_effort':'high'}
        with patch('kimi_hosted.run_prepared',return_value=result):w.run_agent(self.project,'positioning',0)
        self.assertEqual(workflow.screen(self.project)['status'],'awaiting_positioning_choice')
        self.assertFalse(w.done(self.project,2))
        self.assertEqual(w.read(w.stepdir(self.project,2)/'proposal_record.json')['actual_model'],'kimi-k3.1-pro/high session:session_offline_fixture')

    def mock_article(self,suffix='初稿'):
        return '# 离线合成'+suffix+'\n\n## 差异化优势\n\n### 机构系统对接\n\n'+('这是离线合成的机构连接说明，不代表真实产品执行结果。'*12)+'\n\n### 组合采集\n\n'+('这是离线合成的采集与报告说明，不代表真实产品执行结果。'*12)+'\n'

    def mock_response(self,body):
        return {'content':body,'models':['gemini-4-argon'],'finish_reason':'stop','usage':{'offline_fixture':True},'request_id':'offline_fixture_only'}

    def test_http_writer_and_one_short_targeted_edit(self):
        self.advantages()
        with patch('provider_http.chat_completion',return_value=self.mock_response(self.mock_article())) as transport:
            w.run_writer(self.project,3)
        payload=transport.call_args.args[1]
        self.assertEqual((payload['model'],payload['reasoning_effort']),('gemini-4-argon','high'))
        self.assertIn('轻润色原则',payload['messages'][0]['content'])
        _,meta=w.candidate(self.project,3,None)
        w.write(w.stepdir(self.project,3)/'latest_review.json',{'article_sha256':meta['sha256'],'prose_review':{'pass':False,'issues':[{'original':'离线原句','problem':'离线重复收尾','revision_direction':'删除重复文字'}]}})
        notes=self.base/'notes.txt';notes.write_text('仅修正离线原句，保留必要条件。')
        with patch('provider_http.chat_completion',return_value=self.mock_response(self.mock_article('修订稿'))) as edit_transport:
            w.run_writer(self.project,3,edit_notes=notes)
        user=edit_transport.call_args.args[1]['messages'][1]['content']
        self.assertIn('当前完整稿',user);self.assertIn('仅修正离线原句',user)
        self.assertNotIn('完整文风例文',user);self.assertNotIn('独有细节ABC',user);self.assertNotIn('Sepia',user)
        _,edited=w.candidate(self.project,3,None)
        self.assertEqual(edited['edit_count'],1)
        prepared=w.prepare(self.project,3,None,'review');data=w.read(prepared/'inputs.json')
        self.assertEqual(data['review_kind'],'style_changes_check')
        self.assertIn('before',data['changed_text_diff'])
        self.assertIn('不再启动新的文风轮次',data['instruction'])
        with self.assertRaisesRegex(ValueError,'一次定向编辑'):w.run_writer(self.project,3,edit_notes=notes)

    def test_failed_http_writer_is_not_automatically_retried(self):
        from provider_http import ProviderError
        self.advantages()
        with patch('provider_http.chat_completion',side_effect=ProviderError('HTTP_524',524,True)) as transport:
            with self.assertRaises(ValueError):w.run_writer(self.project,3)
            with self.assertRaisesRegex(ValueError,'明确--retry'):w.run_writer(self.project,3)
            self.assertEqual(transport.call_count,1)
        self.assertFalse((w.stepdir(self.project,3)/'candidate.json').exists())

    def test_explicit_peer_pool_survives_pack_roundtrip(self):
        peers=self.base/'confirmed_positioning.md'
        peers.write_text('# 旧已确认定位\n\n## 已确认同类竞品\n\n### 方案乙\n\n对应产品：乙组合\n用途：非临床康养。\n\n### 方案甲\n\n对应产品：甲平台\n用途：非临床康养。\n')
        kp.confirmed_peers(w,self.project,peers,'explicit_prior_choice','离线模拟：沿用用户此前确认顺序。')
        self.advantages()
        self.assertEqual([x['display_name'] for x in w.accepted(self.project,2)['positioning_snapshot']['selected_candidates']],['方案乙','方案甲'])
        out=self.base/'with_peers.zip';w.export_pack(self.project,out)
        with zipfile.ZipFile(out) as z:
            pos=z.read('Reference_Pack/定位.md').decode()
            self.assertIn('## 已确认同类竞品',pos)
            self.assertLess(pos.index('### 方案乙'),pos.index('### 方案甲'))
        restored=self.base/'peers_restored';report=w.wp.import_pack(w,restored,out)
        self.assertEqual(report['confirmed_peers'],2)
        self.assertEqual([x['display_name'] for x in w.accepted(restored,2)['positioning_snapshot']['selected_candidates']],['方案乙','方案甲'])

    def test_vendor_mentions_do_not_become_confirmed_peer_pool(self):
        mentioned=self.base/'mentions.md';mentioned.write_text('# 企业知识\n\n行业里提到方案甲、乙厂家。')
        with self.assertRaisesRegex(ValueError,'已确认同类竞品'):kp.confirmed_peers(w,self.project,mentioned,'user','离线模拟用户确认。')

    def test_model_policy_uses_hosted_analysis_and_http_writer(self):
        policy=w.state(self.project)['model_policy']
        self.assertEqual(policy['research'],'kimi-k3.1-pro')
        self.assertEqual(policy['research_transport'],'kimi_hosted_agents_rest')
        self.assertEqual(policy['writer_provider'],'xty_http')
        self.assertEqual(policy['max_targeted_edits'],1)

    def test_no_issue_keeps_initial_draft_and_exports_exact_requests(self):
        self.advantages()
        with patch('provider_http.chat_completion',return_value=self.mock_response(self.mock_article())):
            w.run_writer(self.project,3)
        body,meta=w.candidate(self.project,3,None)
        review={'article_sha256':meta['sha256'],'prose_review':{'pass':True,'issues':[]}}
        file=self.write_json('offline_review.json',review)
        hosted={'status':'succeeded','result_file':str(file),'run_dir':'offline_fixture_only','session_id':'session_offline_fixture','model':'kimi-k3.1-pro','reasoning_effort':'high'}
        with patch('kimi_hosted.run_prepared',return_value=hosted) as runner,patch('export_support.write_docx'):
            w.run_agent(self.project,'p0_check',0)
        self.assertEqual(runner.call_args.kwargs['resource_paths'],())
        self.assertTrue(w.done(self.project,3))
        self.assertEqual((w.stepdir(self.project,3)/'final.md').read_text(),body)
        self.assertEqual(len(list((w.stepdir(self.project,3)/'writer_runs').iterdir())),1)
        original=w.read(w.stepdir(self.project,3)/'writer_runs'/meta['model']['attempt']/'request.json')
        exported=self.project/'deliveries/P0/Gemini写作Prompt与返回'/meta['model']['attempt']
        self.assertEqual((exported/'02_User_Prompt.txt').read_text(),original['messages'][1]['content'])
        self.assertTrue((self.project/'deliveries/P0/VISUAL_QA_PENDING.md').exists())

    def test_visual_agent_does_not_pass_without_actual_page_manifest(self):
        with patch.object(w,'done',return_value=True):
            with self.assertRaisesRegex(ValueError,'真实渲染页清单'):
                w.run_agent(self.project,'p0_visual_check',0)


    def test_style_review_has_no_knowledge_or_fact_gate_input(self):
        self.advantages()
        with patch('provider_http.chat_completion',return_value=self.mock_response(self.mock_article())):
            w.run_writer(self.project,3)
        with patch.object(w,'material_snapshot',side_effect=AssertionError('style review must not expand knowledge')), \
             patch.object(w,'advantage_snapshot',side_effect=AssertionError('style review must not read claims')):
            prepared=w.prepare(self.project,3,None,'review')
        data=w.read(prepared/'inputs.json');contract=w.prompt_contract(3,'review')
        self.assertEqual(data['review_kind'],'initial_style_check')
        self.assertEqual(set(contract),{'article_sha256','prose_review','notes'})
        for key in ['writing_material_markdown','approved_advantages','positioning_scope','reference_pack','full_extracted_materials']:
            self.assertNotIn(key,data)
        self.assertNotIn('advantage_coverage',str(contract))
        self.assertIn('不核验事实',data['instruction'])

    def test_fact_review_result_is_rejected_in_style_only_step(self):
        self.advantages()
        with patch('provider_http.chat_completion',return_value=self.mock_response(self.mock_article())):
            w.run_writer(self.project,3)
        _,meta=w.candidate(self.project,3,None);w.prepare(self.project,3,None,'review')
        value={'article_sha256':meta['sha256'],'prose_review':{'pass':True,'issues':[]},'fact_review':{'pass':True,'issues':[]}}
        with self.assertRaisesRegex(ValueError,'仅文风'):
            w.review(self.project,3,None,self.write_json('forbidden_fact_review.json',value),'offline_fixture')
        self.assertFalse(w.done(self.project,3))


if __name__ == '__main__':
    unittest.main()
