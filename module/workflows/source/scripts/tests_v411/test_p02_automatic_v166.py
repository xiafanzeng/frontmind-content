from scripts.tests_v411.synthetic_pack import reference_pack
"""Automatic P02 selection behavior; synthetic evidence, no real strength claims."""
import copy
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from scripts import frontmind_workflow as wf
from shared import p02_selection as p2


def candidate(name, *, relative='stronger', margin='clear', aliases=None):
    return {'name':name,'category':'合成测试产品','kind':'brand','aliases':aliases or [],
        'research_notes':'测试原件介绍产品及交付','source_urls':['https://example.org/'+name],
        'suggested_role':'comparison_target','objective_strength':{'relative':relative,
        'advantage_level':margin,'tier':'合成位置','basis':'测试用综合比较理由',
        'source_urls':['https://example.org/'+name]}}


class AutomaticSelectionTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.job=Path(t.name)/'job'; wf.ensure_new_job(self.job,'article',offline=True)
        s=wf.load_state(self.job)
        self.assertEqual(s['metadata']['p02_selection_policy'],p2.AUTO_CONTRACT)
        s.update(selected_pattern_id='P02',question={'question_text':'合成终端推荐','period_id':'current'},
            reference_pack={'brand':'自己','path':str(reference_pack())})
        s['metadata']['p02_selection_pending']=p2.scope(s)
        wf.save_state(self.job,s)
        self.data={'question_text':'合成终端推荐','period_id':'current','answers':[
            {'platform':'豆包','answer_id':'1','answer_text':'高声量同级 强甲 甲简称 强乙'},
            {'platform':'豆包','answer_id':'2','answer_text':'自己 高声量同级 强甲 强乙'},
            {'platform':'豆包','answer_id':'3','answer_text':'高声量同级 强甲'},
            {'platform':'DeepSeek','answer_id':'4','answer_text':'高声量同级 强乙 强丙'}]}
        wf.atomic_json(self.job/'inputs/question_observations.json',self.data)
        self.market={'brand_category':'合成测试产品','research_markdown':'测试研究','sources':[],
            'brand_assessment':{'relative':'self','tier':'自身','basis':'测试原件','source_urls':[]},
            'competitor_candidates':[candidate('高声量同级',relative='peer'),
                candidate('强甲',aliases=['甲简称']),candidate('强乙'),candidate('强丙'),
                candidate('未知',relative='unknown'),candidate('不明显',margin='modest')]}

    def enriched(self):
        return p2.enrich(wf,self.job,self.market)

    def test_two_axes_exclude_high_voice_peer_and_rank_valid_candidates(self):
        market=self.enriched()
        self.assertFalse(market['competitor_candidates'][0]['dual_stronger'])
        # Platforms are equally weighted;甲/丙 tie at .5 and use stable name order.
        self.assertEqual([x['name'] for x in p2.ranked_automatic_candidates(market)],['强乙','强丙','强甲'])
        self.assertFalse(market['competitor_candidates'][4]['dual_stronger'])
        self.assertFalse(market['competitor_candidates'][5]['dual_stronger'])

    def test_real_controller_selects_without_competitor_confirmation(self):
        wf.atomic_text(self.job/'positioning/core_positioning.json','保留旧核心')
        wf.atomic_text(self.job/'production/p0_finalized.json','保留P0')
        with patch.object(wf,'ensure_action',return_value=copy.deepcopy(self.market)), \
             patch.object(p2,'persist_pack',return_value={}), \
             patch.object(wf,'render_competitor_selection') as pause:
            self.assertIsNone(wf.run_positioning_market_research(self.job))
        s=wf.load_state(self.job); record=p2.current(s)
        self.assertEqual(s['status'],'running_question_positioning')
        pause.assert_not_called()
        self.assertEqual([e['name'] for e in record['entities']],['自己','强乙','强丙'])
        self.assertEqual(record['decision_source'],'automatic_dual_strength')
        self.assertFalse(record['automatic_basis']['user_confirmation_required'])
        self.assertTrue((self.job/'decisions/p02_automatic_selection.json').is_file())
        self.assertEqual((self.job/'positioning/core_positioning.json').read_text(),'保留旧核心')
        self.assertEqual((self.job/'production/p0_finalized.json').read_text(),'保留P0')

    def test_insufficient_candidates_supplement_then_request_missing_input(self):
        m=self.enriched()
        for x in m['competitor_candidates']: x['dual_stronger']=False
        self.assertFalse(p2.complete_automatic_research(wf,self.job,m))
        self.assertEqual(wf.load_state(self.job)['status'],'running_positioning_market_research')
        self.assertIsNone(p2.complete_automatic_research(wf,self.job,m))
        self.assertNotIn('p02_selection',wf.load_state(self.job)['metadata'])

    def test_source_evidence_unknown_monitoring_and_same_brand_do_not_qualify(self):
        self.market['competitor_candidates'][1]['objective_strength']['source_urls']=[]
        m=self.enriched()
        self.assertFalse(m['competitor_candidates'][1]['dual_stronger'])
        bad=copy.deepcopy(self.data);bad['period_id']='other'
        wf.atomic_json(self.job/'inputs/question_observations.json',bad)
        self.assertEqual(p2.ranked_automatic_candidates(self.enriched()),[])

    def test_duplicate_aliases_do_not_form_two_competitors(self):
        m=self.enriched()
        m['competitor_candidates'][2]['aliases']=['强甲']
        self.assertEqual([x['name'] for x in p2.ranked_automatic_candidates(m)],['强乙','强丙'])

    def test_own_alias_candidates_are_resolved_before_visibility_baseline(self):
        self.market['competitor_candidates']=[candidate('自己'),candidate('简称',aliases=['自己']),
            candidate('强甲'),candidate('强乙')]
        data=copy.deepcopy(self.data)
        data['answers']=[{'platform':p,'answer_id':p+str(n),'answer_text':
            ('简称 ' if n==0 else '')+'强甲 强乙'} for p in ('豆包','元宝') for n in (0,1)]
        wf.atomic_json(self.job/'inputs/question_observations.json',data)
        m=self.enriched()
        self.assertEqual([x['name'] for x in m['competitor_candidates']],['强甲','强乙'])
        self.assertEqual(m['brand_aliases'],['简称'])
        self.assertEqual(m['brand_visibility']['equal_platform_mention_rate'],.5)
        self.assertEqual({x['name'] for x in p2.ranked_automatic_candidates(m)},{'强甲','强乙'})

    def test_new_p02_research_policy_does_not_enter_other_patterns(self):
        for pattern in ('P01','P03','P04','P05','P06'):
            s=wf.load_state(self.job);s['selected_pattern_id']=pattern;wf.save_state(self.job,s)
            self.assertFalse(p2.research_enabled(s))
            self.assertEqual(p2.research_prompt(wf,self.job),'')

    def test_insufficient_input_page_has_no_routine_confirmation(self):
        m=self.enriched();wf.atomic_json(self.job/'research/brand_market/competitive_choice_map.json',m)
        with patch.object(wf,'set_pause') as pause,patch.object(wf,'emit_pause',return_value=0):
            wf.render_competitor_selection(self.job)
        self.assertEqual(pause.call_args.kwargs['choices'],['补充资料后继续','直接指定两家','重新研究'])
        draft=wf.read_json(self.job/'positioning/competitor_selection.json')
        self.assertEqual(draft['comparison_targets'],[])

    def test_missing_input_supplement_is_saved_and_restarts_research(self):
        state=wf.load_state(self.job)
        args=SimpleNamespace(positioning_supplement='团队规模及实际产品交付的新资料',revision=state['revision'])
        with patch.object(wf,'drive',return_value=0):
            p2.handle_selection(wf,args,self.job)
        self.assertEqual(wf.load_state(self.job)['status'],'running_positioning_market_research')
        self.assertIn('团队规模及实际产品交付的新资料',wf.user_material_text(self.job,'positioning'))

    def test_explicit_rerun_has_fresh_identity_and_preserves_core_and_p0(self):
        wf.atomic_text(self.job/'positioning/core_positioning.json','既有核心定位')
        wf.atomic_text(self.job/'production/p0_finalized.json','既有P0')
        identities=[]
        for _ in range(2):
            state=wf.load_state(self.job)
            args=SimpleNamespace(positioning_supplement=None,rerun_positioning_research=True,
                revision=state['revision'])
            with patch.object(wf,'drive',return_value=0):p2.handle_selection(wf,args,self.job)
            identities.append(wf.load_state(self.job)['flags']['model_action_epochs']['positioning_market_research'])
        self.assertNotEqual(*identities)
        self.assertEqual((self.job/'positioning/core_positioning.json').read_text(),'既有核心定位')
        self.assertEqual((self.job/'production/p0_finalized.json').read_text(),'既有P0')

    def test_explicit_two_names_need_no_second_confirmation(self):
        m=self.enriched();wf.atomic_json(self.job/'research/brand_market/competitive_choice_map.json',m)
        state=wf.load_state(self.job)
        args=SimpleNamespace(positioning_supplement='同时提交的本题产品补料',rerun_positioning_research=False,
            competitor_selection='{"comparison_targets":["高声量同级","强甲"]}',
            confirm_competitors=False,revision=state['revision'])
        with patch.object(p2,'persist_pack',return_value={}),patch.object(wf,'drive',return_value=0), \
             patch.object(wf,'render_competitor_selection') as pause:
            p2.handle_selection(wf,args,self.job)
        pause.assert_not_called()
        self.assertEqual([x['name'] for x in p2.current(wf.load_state(self.job))['entities']],
            ['自己','高声量同级','强甲'])
        self.assertEqual(wf.load_state(self.job)['status'],'running_question_positioning')
        self.assertIn('同时提交的本题产品补料',wf.user_material_text(self.job,'positioning'))

    def test_writer_context_does_not_forward_strength_or_visibility(self):
        m=self.enriched();wf.atomic_json(self.job/'research/brand_market/competitive_choice_map.json',m)
        with patch.object(p2,'persist_pack',return_value={}):
            self.assertTrue(p2.complete_automatic_research(wf,self.job,m))
        text=p2.context(wf.load_state(self.job))
        self.assertIn('强丙',text);self.assertIn('强乙',text)
        for field in ('objective_strength','ai_visibility','source_urls','automatic_basis','测试用综合比较理由'):
            self.assertNotIn(field,text)
        from shared import writing_context_v165 as writing
        state=wf.load_state(self.job)
        state['metadata']['effective_writing_requirements']={'article_brief':'本题产品介绍',
            'material_input_note':'后台来源恢复说明，不属于作者内容'}
        wf.save_state(self.job,state)
        self.assertNotIn('后台来源恢复说明',writing.commission(wf,self.job))
        self.assertNotIn('后台来源恢复说明',writing.commission(wf,self.job,editor=True))
        self.assertNotIn('后台来源恢复说明',writing.commission(wf,self.job,planning=True))

    def test_legacy_manual_contract_and_scope_are_unchanged(self):
        s=wf.load_state(self.job);s['metadata']['p02_selection_policy']=p2.CONTRACT
        wf.save_state(self.job,s)
        self.assertNotIn('selection_policy',p2.scope(s))
        self.assertFalse(p2.automatic(s))
        m=self.enriched();wf.atomic_json(self.job/'research/brand_market/competitive_choice_map.json',m)
        record=p2.freeze(wf,self.job,{'comparison_targets':m['competitor_candidates'][:2],'peer_examples':[]})
        self.assertEqual(record['contract'],p2.CONTRACT)
        self.assertEqual(record['decision_source'],'user_selected_two')


if __name__=='__main__': unittest.main()
