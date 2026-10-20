"""Offline policy/integration tests; no remote model or real competitor claims."""
import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import frontmind_workflow as wf
from shared import p02_selection as p2, p01_expression as p1, writing_context_v16 as prose, writing_requirements as req, editorial_preparation

ROOT=Path(__file__).resolve().parents[2]

def candidate(name,relative='stronger',aliases=None):
    return {'id':name,'name':name,'aliases':aliases or [],'kind':'brand','category':'留学申请','research_notes':'合成测试事实',
            'source_urls':['https://example.com/facts'],'suggested_role':'comparison_target',
            'objective_strength':{'relative':relative,'tier':'合成档位','basis':'明确合成对比','source_urls':['https://example.com/facts']}}

class SelectionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.job=Path(temp.name)/'job'; wf.ensure_new_job(self.job,'article',offline=True)
        self.state=wf.load_state(self.job); self.state['selected_pattern_id']='P02'
        self.state['question']={'question_text':'英国硕士申请机构推荐','period_id':'p1'}
        (self.job/'inputs').mkdir(parents=True,exist_ok=True)
        material=self.job/'inputs/synthetic-company.md'
        material.write_text('仅供离线测试的合成企业资料。自己机构提供申请规划与材料整理服务。',encoding='utf-8')
        pack=wf.create_reference_pack(brand_name='自己机构',knowledge_base=[material],output=self.job/'00_input/synthetic-pack')
        self.state['reference_pack']={'brand':'自己机构','path':pack['portable_zip_path']}
        wf.save_state(self.job,self.state)
        self.data={'question_text':'英国硕士申请机构推荐','period_id':'p1','answers':[
            {'answer_id':'a1','platform':'豆包','answer_text':'自己机构、强甲、甲简称、强甲、强乙'},
            {'answer_id':'a2','platform':'豆包','answer_text':'强甲 强乙'},
            {'answer_id':'a3','platform':'DeepSeek','answer_text':'强甲 强乙'}]}
        wf.atomic_json(self.job/'inputs/question_observations.json',self.data)
        self.market={'brand_category':'留学申请','research_markdown':'合成研究','sources':[],
            'competitor_candidates':[candidate('强甲',aliases=['甲简称']),candidate('强乙'),candidate('未选机构','peer')]}
        self.market=p2.enrich(wf,self.job,self.market)
        wf.atomic_json(self.job/'research/brand_market/competitive_choice_map.json',self.market)
    def select(self,targets=None):
        return p2.freeze(wf,self.job,{'comparison_targets':targets or self.market['competitor_candidates'][:2],'peer_examples':[]})
    def test_all_observations_equal_platforms_and_alias_dedup(self):
        m=p2.visibility(self.data,[{'name':'自己机构'},candidate('强甲',aliases=['甲简称'])])
        self.assertEqual(m['自己机构']['equal_platform_mention_rate'],.25)
        self.assertEqual(m['强甲']['equal_platform_mention_rate'],1)
        self.assertEqual(sum(x['denominator'] for x in m['强甲']['platforms']),3)
        self.assertTrue(all(x['attributed_citations'] is None for x in m['强甲']['platforms']))
    def test_unknown_period_is_not_zero_visibility(self):
        data={**self.data,'period_id':None}
        self.assertIsNone(p2.visibility(data,[{'name':'强甲'}])['强甲']['equal_platform_mention_rate'])
    def test_different_period_and_duplicate_id_excluded(self):
        data=copy.deepcopy(self.data);data['answers'] += [data['answers'][0],{'answer_id':'old','platform':'豆包','period_id':'old','answer_text':'自己机构'}]
        m=p2.visibility(data,[{'name':'自己机构'}])['自己机构']
        self.assertEqual(sum(x['denominator'] for x in m['platforms']),3)
    def test_suggestions_only_dual_stronger_and_manual_peer_allowed(self):
        self.assertEqual([x['name'] for x in p2.suggested(self.market)['comparison_targets']],['强甲','强乙'])
        r=self.select([self.market['competitor_candidates'][0],self.market['competitor_candidates'][2]])
        self.assertEqual(r['entities'][2]['objective_strength']['relative'],'peer')
        self.assertFalse(r['entities'][2]['dual_stronger'])
    def test_zero_strong_does_not_fill_with_peers(self):
        for c in self.market['competitor_candidates']: c['dual_stronger']=False
        self.assertEqual(p2.suggested(self.market)['comparison_targets'],[])
    def test_exact_two_and_no_category_or_duplicate_alias(self):
        with self.assertRaises(ValueError): self.select(self.market['competitor_candidates'])
        bad=copy.deepcopy(self.market['competitor_candidates'][:2]);bad[1]['kind']='category'
        with self.assertRaises(ValueError): self.select(bad)
        bad[1]['kind']='brand';bad[1]['aliases']=['甲简称']
        with self.assertRaises(ValueError): self.select(bad)
    def test_scope_projects_into_preparation_and_all_commissions(self):
        r=self.select();state=wf.load_state(self.job)
        self.assertEqual(req.effective(wf,self.job,p0=False)['candidate_order'],['自己机构','强甲','强乙'])
        prep=prose.preparation_commission(wf,self.job); self.assertIn(r['selection_hash'],prep)
        commission=prose.commission(wf,self.job);self.assertIn(p2.GUIDANCE,commission)
        self.assertNotIn('未选机构',commission)
    def test_scope_change_requires_reselection_and_invalidates_confirmation(self):
        r=self.select();state=wf.load_state(self.job)
        state['question']['question_text']='美国本科申请机构推荐';wf.save_state(self.job,state)
        self.assertIsNone(p2.current(state))
        with self.assertRaises(ValueError): req.effective(wf,self.job,p0=False)
    def test_scope_hash_and_candidate_order_checked(self):
        r=self.select();state=wf.load_state(self.job)
        p2.check_scope(state,{'candidate_scope':['自己机构','强甲','强乙']})
        with self.assertRaises(ValueError): p2.check_scope(state,{'candidate_order':['强甲','自己机构','强乙']})
        r['entities'][1]['name']='篡改';
        with self.assertRaises(ValueError): p2.validate(r)
    def test_body_all_three_alias_order_and_fourth(self):
        self.select();state=wf.load_state(self.job)
        p2.check_body(state,'# 主标题\n自己机构提供服务。\n甲简称提供支持。\n强乙提供支持。医生张某与设备不计机构。')
        for body in ('自己机构 强甲','强甲 自己机构 强乙','自己机构 强甲 强乙 还推荐未选机构'):
            with self.subTest(body=body),self.assertRaises(ValueError): p2.check_body(state,body)
    def test_old_tasks_and_p0_do_not_opt_in(self):
        state=copy.deepcopy(self.state);state['metadata'].pop('p02_selection_policy');self.assertFalse(p2.enabled(state))
        state=wf.make_state('p0','p0');self.assertFalse(p2.research_enabled(state))
    def test_pack_update_preserves_every_existing_payload_and_readiness(self):
        self.select();record=p2.current(wf.load_state(self.job))
        source=Path(self.state['reference_pack']['path']);root=wf.reference_pack_root(source)
        result=p2.persist_pack(wf,self.job,record)
        self.assertEqual(result['readiness'],root['readiness'])
        with wf.PackageView(source) as before,wf.PackageView(Path(result['portable_zip_path'])) as after:
            for name in before.names():
                if name!='reference_pack.json': self.assertEqual(before.read_bytes(name),after.read_bytes(name),name)
            self.assertEqual(after.read_json(p2.MEMBER),record)
    def test_reuse_matching_pack_selection_without_new_confirmation(self):
        self.select();record=p2.current(wf.load_state(self.job));result=p2.persist_pack(wf,self.job,record)
        state=wf.load_state(self.job);state['metadata'].pop('p02_selection');state['reference_pack']['path']=result['portable_zip_path'];wf.save_state(self.job,state)
        self.assertTrue(p2.ensure_ready(wf,self.job));self.assertEqual(p2.current(wf.load_state(self.job))['selection_hash'],record['selection_hash'])
    def test_existing_page_confirms_pair_without_core_regeneration(self):
        state=wf.load_state(self.job);state['metadata']['p02_selection_pending']=p2.scope(state);wf.save_state(self.job,state)
        wf.atomic_json(self.job/'positioning/competitor_selection.json',p2.suggested(self.market))
        args=wf.parser().parse_args(['continue','--job-dir',str(self.job),'--revision',str(state['revision']),'--confirm-competitors'])
        with patch.object(wf,'drive',return_value=0),patch.object(wf,'clear_core_result',side_effect=AssertionError('must preserve core')):
            self.assertEqual(wf.handle_competitor_selection(args,self.job),0)
        after=wf.load_state(self.job);self.assertEqual(after['status'],'running_question_positioning');self.assertIsNotNone(p2.current(after))
    def test_new_research_retains_strength_fields_under_schema(self):
        normalized=wf.normalize_research_result(self.market,'自己机构');self.assertTrue(normalized['competitor_candidates'][0]['dual_stronger'])
    def test_selection_page_displays_denominators_and_self(self):
        state=wf.load_state(self.job);state['metadata']['p02_selection_pending']=p2.scope(state);wf.save_state(self.job,state)
        with contextlib.redirect_stdout(io.StringIO()): wf.render_competitor_selection(self.job)
        state=wf.load_state(self.job);text=Path(state['current_pause']['review_markdown_path']).read_text()
        for term in ('自己机构','双强候选','等平台均值','提及不等于','两家具体机构'): self.assertIn(term,text)

    def test_conflicting_scope_and_order_rejected(self):
        self.select()
        with self.assertRaises(ValueError):
            p2.check_scope(wf.load_state(self.job),{'candidate_scope':['自己机构','强甲','强乙'],'candidate_order':['自己机构','强乙','强甲']})
    def test_old_internal_h1_does_not_change_introduction_order(self):
        self.select();p2.check_body(wf.load_state(self.job),'# 强甲与自己机构的历史工作标题\n\n自己机构提供服务。强甲提供服务。强乙提供服务。')
    def test_unknown_fourth_in_plain_paragraph_fails_final_editor_inventory(self):
        self.select();state=wf.load_state(self.job)
        body='自己机构提供服务。强甲提供服务。强乙提供服务。另外，第四家星河留学机构提供申请服务。'
        mentions=[{'name':n,'quote':n+'提供服务。'} for n in ('自己机构','强甲','强乙')]
        mentions.append({'name':'星河留学机构','quote':'第四家星河留学机构提供申请服务。'})
        with self.assertRaises(ValueError): p2.validate_mentions(state,body,mentions,accepted=True)
        p2.validate_mentions(state,body,mentions,accepted=False)
    def test_inventory_binds_quotes_and_canonical_aliases(self):
        self.select();state=wf.load_state(self.job);body='自己机构提供服务。甲简称提供支持。强乙提供支持。'
        mentions=[{'name':n,'quote':n} for n in ('自己机构','甲简称','强乙')]
        p2.validate_mentions(state,body,mentions,accepted=True)
        mentions[1]['quote']='强甲提供服务'
        with self.assertRaises(ValueError): p2.validate_mentions(state,body,mentions,accepted=True)
    def test_final_review_requires_inventory_and_preserves_it(self):
        from shared import language_editor_v15 as editor
        self.select();state=wf.load_state(self.job);body='自己机构提供服务。强甲提供支持。强乙提供支持。'
        with patch.object(editor,'bound_input',return_value=body):
            with self.assertRaises(ValueError): editor.validate_action(wf,self.job,'article_finalize',{'needs_revision':False,'comments':[],'local_edits':[]})
            value=p2.fixture_review(state,body)
            self.assertEqual(editor.validate_action(wf,self.job,'article_finalize',value),value)
    def test_supplement_draft_is_bound_to_question_scope(self):
        state=wf.load_state(self.job);draft=p2.suggested(self.market)
        state['metadata'].update(p02_confirmed_draft=draft,p02_confirmed_draft_scope=p2.scope(state))
        self.assertEqual(p2.confirmed_draft(state),draft)
        state['question']['question_text']='另一个问题';wf.save_state(self.job,state)
        self.assertIsNone(p2.confirmed_draft(state))
        self.assertNotIn('强甲',p2.research_prompt(wf,self.job).split('如有用户已确认的补研名单')[1])
        with self.assertRaises(ValueError): p2.complete_selected_research(wf,self.job,self.market)
        self.assertFalse(p2.ensure_ready(wf,self.job))
        self.assertNotIn('p02_confirmed_draft',wf.load_state(self.job)['metadata'])
        self.assertTrue(list((self.job/'positioning').glob('superseded_draft_*.json')))

    def test_wrong_question_monitoring_is_not_comparable(self):
        state=wf.load_state(self.job);state['question']['question_text']='美国本科推荐';wf.save_state(self.job,state)
        market=p2.enrich(wf,self.job,self.market)
        self.assertFalse(market['brand_visibility']['comparable'])
        self.assertTrue(market['brand_visibility']['scope_mismatch'])
        self.assertEqual(p2.suggested(market)['comparison_targets'],[])
    def test_positioning_page_can_explicitly_reselect_two_competitors(self):
        self.select();state=wf.load_state(self.job);state['status']='awaiting_question_positioning_confirmation';wf.save_state(self.job,state)
        args=wf.parser().parse_args(['continue','--job-dir',str(self.job),'--revision',str(state['revision']),
            '--competitor-selection',json.dumps({'comparison_targets':['强甲','未选机构'],'peer_examples':[]}), '--confirm-competitors'])
        with patch.object(wf,'drive',return_value=0),patch.object(p2,'persist_pack',return_value={}):
            self.assertEqual(wf.handle_question_positioning_pause(args,self.job),0)
        self.assertEqual([e['name'] for e in p2.current(wf.load_state(self.job))['entities']],['自己机构','强甲','未选机构'])

class ExpressionTests(unittest.TestCase):
    def test_new_marker_scoped_to_p01_and_legacy_system_unchanged(self):
        for pattern in ('P01','P02','P03'):
            state=wf.make_state('a','article');state['selected_pattern_id']=pattern
            self.assertEqual(p1.enabled(state),pattern=='P01')
        old=prose.MARKER+'\n# 普通历史请求'
        fresh=prose.MARKER+'\n'+p1.MARKER+'\n# 新P01'
        self.assertNotIn(p1.GUIDANCE,prose.system('article_edit',old))
        edited=prose.system('article_edit',fresh)
        self.assertIn(p1.GUIDANCE,edited);self.assertNotIn('让段落在最后一项具体内容处收住',edited)
    def test_cross_industry_new_preparation_is_generic(self):
        for brand,question in [('医美甲','腰腹塑形机构推荐'),('留学甲','英国硕士机构推荐'),('电脑甲','移动办公电脑推荐')]:
            with self.subTest(brand=brand),tempfile.TemporaryDirectory() as tmp:
                job=Path(tmp)/'job';wf.ensure_new_job(job,'article',offline=True);state=wf.load_state(job)
                state.update(selected_pattern_id='P01',question={'question_text':question},reference_pack={'brand':brand})
                state['decisions']['response_brief']='介绍本次品牌，保留自然表达。';wf.save_state(job,state)
                with patch.object(wf,'load_examples',return_value=[]),patch.object(wf,'user_material_index',return_value=''):
                    prompt=prose.prompt_preparation(wf,job)
                self.assertTrue(p1.matches(prompt));self.assertIn(question,prompt)
                self.assertNotIn('腰腹是文章入口',prompt);self.assertNotIn('台心',prompt)
                self.assertIn('案例insight具体说明',prose.system('article_editorial_preparation',prompt))

    def test_writer_counter_survives_policy_prefixes_in_actual_payloads(self):
        from shared import model_runtime,writer_measure
        for pattern in ('P01','P02'):
            state=wf.make_state('a','article');state['selected_pattern_id']=pattern
            with patch.object(wf,'load_state',return_value=state): prompt=prose.wrap_for(wf,Path('/offline'),'正文',writer=True)
            for action in ('article_draft','article_edit','article_repair'):
                with self.subTest(pattern=pattern,action=action):
                    self.assertTrue(writer_measure.matches(action,prompt))
                    payload=model_runtime.build_payload(action,prompt)
                    self.assertIn('count_article',[t['function']['name'] for t in payload['tools']])
                    self.assertFalse(writer_measure.matches(action,'资料引用：'+prompt))
    def test_p02_review_schema_only_changes_exact_new_prefix(self):
        from shared import model_runtime,language_editor_v15
        for action in ('article_finalize','article_polish'):
            new=prose.MARKER+'\n'+p2.MARKER+'\n正文'
            old=prose.MARKER+'\n正文引用：'+p2.MARKER
            schema=model_runtime.submit_tool_for(action,prompt=new)['function']['parameters']['properties']['result']
            self.assertIn('entity_mentions',schema['required'])
            schema=model_runtime.submit_tool_for(action,prompt=old)['function']['parameters']['properties']['result']
            self.assertNotIn('entity_mentions',schema['properties'])
if __name__=='__main__': unittest.main()
