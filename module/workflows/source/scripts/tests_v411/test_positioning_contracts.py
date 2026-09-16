"""Two-action contracts with explicit scope confirmation, not semantic evidence."""
from __future__ import annotations
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import tempfile
import unittest
from unittest import mock
from scripts.tests_v411.test_workflow_v411 import CONTROLLER as C, ROOT, state, page
from scripts.tests_v411.positioning_provider_samples import core_output, market_map, BRAND

ACTIONS = ('positioning_market_research', 'positioning_value_synthesis')
RESEARCH = {
    'research_markdown': '用户希望持续完成任务。甲提供专门服务，乙也有相似能力；另一种方式适合临时需求。此处不作总排名。',
    'sources': [],
    'brand_category': '持续服务商',
    'competitor_candidates': [
        {'name': '按次服务', 'category': '按次服务商', 'kind': 'category',
         'research_notes': '临时任务按次委托处理。', 'source_urls': [],
         'suggested_role': 'comparison_target'},
        {'name': '持续服务乙', 'category': '持续服务商', 'kind': 'brand',
         'research_notes': '与甲提供相似的持续服务。', 'source_urls': [],
         'suggested_role': 'peer_example'},
    ],
}
CORE = {'user_choice_value': '为持续任务提供适配的专门服务', 'core_positioning_paragraph': '甲面向需要持续完成这类任务的人，提供与工作方式匹配的专门服务。', 'advantage_explanation': '与临时处理相比，甲有持续服务安排；乙也提供类似条件，没有材料证明甲独有。'}

class PositioningControllerContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='frontmind-two-step-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.job = self.base / 'job'
        self.material = self.base / 'company.md'
        self.material.write_text('材料标记 ORIGINAL_FACTS。甲提供持续服务，乙提供临时服务。')
        with mock.patch.object(C, 'invoke_external_provider', return_value=False):
            self.command('reference-pack', 'create', '--brand', BRAND, '--input', str(self.material), '--job-dir', str(self.job))
        self.assertEqual(ACTIONS[0], state(self.job)['pending_action']['action'])

    def command(self,*args):
        ns=C.parser().parse_args(list(args))
        with redirect_stdout(io.StringIO()): return ns.func(ns)

    def cont(self,*args):
        return self.command('continue','--job-dir',str(self.job),'--revision',str(state(self.job)['revision']),*args)

    def read(self,member): return json.loads((self.job/member).read_text())

    def run_provider(self,research=None,core=None,callback=None,observe=None):
        outputs={ACTIONS[0]:RESEARCH if research is None else research,ACTIONS[1]:CORE if core is None else core}
        calls=[]
        def provider(request_path,request,job):
            action=request['action'];self.assertIn(action,ACTIONS)
            prompt=(job/request['prompt_path']).read_text();calls.append((action,prompt))
            if observe:observe(action,prompt)
            C.atomic_json(job/request['expected_output'],deepcopy(outputs[action]));return True
        with mock.patch.object(C,'invoke_external_provider',side_effect=provider),redirect_stdout(io.StringIO()):
            result=callback() if callback else C.drive(self.job)
        self.assertEqual(0,result)
        return calls

    def finish_positioning(self, **provider_kwargs):
        """Drive research, then explicitly confirm the fixture's proposed scope."""
        calls = self.run_provider(**provider_kwargs)
        self.assertEqual([ACTIONS[0]], [a for a, _ in calls])
        self.assertEqual('awaiting_competitor_selection', state(self.job)['status'])
        self.assertFalse((self.job/'positioning/core_positioning.json').exists())
        calls += self.run_provider(callback=lambda:self.cont('--confirm-competitors'), **provider_kwargs)
        self.assertEqual('awaiting_core_positioning_confirmation', state(self.job)['status'])
        return calls

    def test_two_actions_stop_for_explicit_competitor_confirmation(self):
        calls=self.run_provider()
        research_state=state(self.job)
        self.assertEqual([ACTIONS[0]],[a for a,_ in calls])
        self.assertEqual('awaiting_competitor_selection',research_state['status'])
        self.assertEqual(1,research_state['revision'])
        self.assertTrue(research_state['current_pause']['must_stop'])
        self.assertIsNone(research_state['pending_action'])
        self.assertFalse((self.job/'positioning/core_positioning.json').exists())
        calls += self.run_provider(callback=lambda:self.cont('--confirm-competitors'))
        self.assertEqual(list(ACTIONS),[a for a,_ in calls])
        self.assertEqual('awaiting_core_positioning_confirmation',state(self.job)['status'])
        self.assertEqual(research_state['revision']+1,state(self.job)['revision'])
        self.assertEqual(2,len(list((self.job/'reviews').glob('*.md'))))
        self.assertFalse((self.job/'positioning/core_positioning.generated.json').exists())

    def test_model_only_supplies_small_payload_controller_owns_metadata(self):
        self.finish_positioning()
        research=self.read('research/brand_market/competitive_choice_map.json')
        core=self.read('positioning/core_positioning.json')
        self.assertEqual(set(RESEARCH)|{'schema_version','artifact_type','brand'},set(research))
        self.assertEqual(set(CORE)|{'schema_version','artifact_type','brand','comparison_scope'},set(core))
        self.assertEqual(state(self.job)['decisions']['comparison_scope'],core['comparison_scope'])
        self.assertTrue(core['comparison_scope']['confirmed'])
        self.assertNotIn('comparison_scope',CORE)
        for index, item in enumerate(research['competitor_candidates'], 1):
            self.assertEqual(f'c{index:03d}',item['id'])
            self.assertEqual(RESEARCH['competitor_candidates'][index-1],{k:v for k,v in item.items() if k!='id'})
        self.assertEqual(BRAND,core['brand'])
        self.assertEqual(RESEARCH['research_markdown'],research['research_markdown'])

    def test_no_rank_and_no_unique_advantage_can_confirm(self):
        self.finish_positioning()
        text=page(self.job)
        for token in ('第1档','品牌自然落位','企业投入','没有排名','尚不能证明品牌唯一首选'):
            self.assertNotIn(token,text)
        self.cont('--confirm-core-positioning')
        self.assertEqual('positioning_ready',state(self.job)['status'])

    def test_result_precedes_research_and_no_placeholder_sections(self):
        self.finish_positioning()
        text=page(self.job)
        sections=['## 核心定位','## 与已确认竞品的比较','## 您可以选择']
        positions=[text.index(k) for k in sections]
        self.assertEqual(sorted(positions),positions)
        self.assertNotIn('## 适用条件与研究限制',text)
        self.assertNotIn('当前没有额外内容',text)

    def test_notes_are_separate_from_unchanged_paragraph(self):
        value={**CORE,'applicability_notes':['范围改变后重新比较。']}
        self.finish_positioning(core=value)
        stored=self.read('positioning/core_positioning.json')
        self.assertEqual(CORE['core_positioning_paragraph'],stored['core_positioning_paragraph'])
        self.assertNotIn('范围改变后重新比较。',page(self.job))
        self.assertIn('范围改变后重新比较。',C.positioning_context_markdown(stored))

    def test_short_natural_prose_and_single_advantage_are_valid(self):
        value={**CORE,'user_choice_value':'单项适配','core_positioning_paragraph':'这项服务适合需要持续支持的客户。','advantage_explanation':'支持安排与客户任务相符。'}
        self.finish_positioning(core=value)
        self.assertEqual(value['core_positioning_paragraph'],self.read('positioning/core_positioning.json')['core_positioning_paragraph'])

    def test_invalid_payload_shapes_fail_without_filling_fields(self):
        for value in ({'research_markdown':'ok'}, {'research_markdown':[],'sources':[]}):
            with self.subTest(value=value),self.assertRaises(C.WorkflowError):C.normalize_research_result(value,BRAND)
        for value in ({'user_choice_value':'a','core_positioning_paragraph':'b'}, {**CORE,'applicability_notes':'not an array'}, {**CORE,'advantage_explanation':''}):
            with self.subTest(value=value),self.assertRaises(C.WorkflowError):C.normalize_core_result(value,BRAND)

    def test_non_actionable_provider_flag_does_not_pollute_canonical_core(self):
        for flag in (False, None):
            raw = {**CORE, 'needs_input': flag}
            normalized = C.normalize_core_result(raw, BRAND)
            self.assertNotIn('needs_input', normalized)
            self.assertIn('needs_input', raw)
            self.assertEqual(CORE['core_positioning_paragraph'], normalized['core_positioning_paragraph'])
        for flag in (True, 0, '', 'missing facts'):
            with self.subTest(flag=flag), self.assertRaises(C.WorkflowError):
                C.normalize_core_result({**CORE, 'needs_input': flag}, BRAND)

    def test_complete_historical_objects_remain_readable(self):
        old=core_output()
        self.assertEqual(old,C.validate_core_positioning(old,BRAND))
        self.assertEqual(market_map(),C.validate_choice_map(market_map(),BRAND))
        rendered=C.core_positioning_markdown(old)
        for item in old['brand_placement']['comparisons']:
            self.assertIn(item['brand_advantage'],rendered)
        self.assertNotIn(old['supporting_proof'][0],rendered)
        self.assertIn(old['supporting_proof'][0],C.positioning_context_markdown(old))

    def test_original_complete_objects_without_tiers_remain_readable(self):
        old=core_output()
        for key in ('market_tiers','tier_order_reason','brand_placement','combination_value','supporting_proof'):
            old.pop(key,None)
        C.validate_core_positioning(old,BRAND)
        self.assertIn(old['core_positioning_paragraph'],C.core_positioning_markdown(old))
        market=market_map()
        market['alternative_routes']=[{'route_name':t['name'],'named_examples':t['named_examples'],
            'dominant_value':t['dominant_value'],'routine_strengths':t['tier_strengths'],
            'complex_scenario_response':t['tier_high_stakes_response'],'failure_scenario_response':t['tier_failure_response'],
            'limitations':t['tier_limitations'],'best_fit':t['tier_best_fit'],'better_than_brand_when':t['tier_can_move_ahead_when']}
            for t in market['market_tiers']]
        for field in ('decisive_consequence_chains','brand_difference_mechanisms','positioning_opportunities'):
            market[field]=[]
        for key in ('market_tiers','tier_order_reason','ranking_scope','brand_placement'):
            market.pop(key,None)
        C.validate_choice_map(market,BRAND)
        rendered=C.competitive_choice_map_markdown(market)
        self.assertNotIn('第1档',rendered)
        self.assertIn(market['alternative_routes'][0]['route_name'],rendered)

    def test_legacy_projection_has_no_fabricated_chain_or_business_decision(self):
        def observe(action,_):
            if action==ACTIONS[1]:self.assertFalse((self.job/'positioning/core_positioning_directions.json').exists())
        self.finish_positioning(observe=observe)
        item=self.read('positioning/core_positioning_directions.json')['directions'][0]
        self.assertEqual(CORE['core_positioning_paragraph'],item['core_positioning_paragraph'])
        self.assertNotIn('decisive_consequence_chain',item)
        self.assertNotIn('strategic_tradeoffs',item)
        C.validate_structure(self.read('positioning/core_positioning_directions.json'),'core_positioning_directions.schema.json')

    def test_edits_supplements_and_exploration_respect_confirmed_scope(self):
        self.finish_positioning()
        scope=deepcopy(self.read('positioning/core_positioning.json')['comparison_scope'])
        for flag,text,expected in [
            ('--core-positioning-edits','新要求 EDIT_MARK',[ACTIONS[1]]),
            ('--positioning-supplement','新增事实 SUPPLEMENT_MARK',list(ACTIONS)),
        ]:
            calls=self.run_provider(callback=lambda:self.cont(flag,text))
            self.assertEqual(expected,[a for a,_ in calls])
            for _,prompt in calls:self.assertIn(text,prompt)
            self.assertEqual(scope,self.read('positioning/core_positioning.json')['comparison_scope'])
            self.assertEqual('awaiting_core_positioning_confirmation',state(self.job)['status'])
        calls=self.run_provider(callback=lambda:self.cont('--explore-positioning-alternatives'))
        self.assertEqual([ACTIONS[0]],[a for a,_ in calls])
        self.assertEqual('awaiting_competitor_selection',state(self.job)['status'])
        self.assertFalse(state(self.job)['decisions'].get('comparison_scope',{}).get('confirmed'))
        self.assertFalse((self.job/'positioning/core_positioning.json').exists())
        self.assertIn('是否重新探索其他经营位置：是',calls[0][1])
        calls += self.run_provider(callback=lambda:self.cont('--confirm-competitors'))
        self.assertEqual(list(ACTIONS),[a for a,_ in calls])

    def test_custom_intent_is_sent_to_both_actions(self):
        self.finish_positioning()
        calls=self.run_provider(callback=lambda:self.cont('--core-positioning-custom','聚焦持续合作'))
        self.assertEqual([ACTIONS[0]],[a for a,_ in calls])
        self.assertEqual('awaiting_competitor_selection',state(self.job)['status'])
        calls += self.run_provider(callback=lambda:self.cont('--confirm-competitors'))
        self.assertEqual(list(ACTIONS),[a for a,_ in calls])
        for _,prompt in calls:self.assertIn('聚焦持续合作',prompt)

    def test_old_result_not_reintroduced_as_material_on_refresh(self):
        self.finish_positioning(core={**CORE,'core_positioning_paragraph':'OLD_CONCLUSION_NOT_A_FACT'})
        self.run_provider(callback=lambda:self.cont('--rerun-positioning-research'))
        context=(self.job/'inputs/reference_context.md').read_text()
        self.assertIn('ORIGINAL_FACTS',context)
        self.assertNotIn('OLD_CONCLUSION_NOT_A_FACT',context)

    def test_missing_information_uses_existing_page_and_clears_stale_core(self):
        self.finish_positioning()
        self.run_provider(core={'needs_input':'仅知道名称，请补充实际服务。'},callback=lambda:self.cont('--core-positioning-edits','改变服务范围'))
        self.assertEqual('awaiting_core_positioning_confirmation',state(self.job)['status'])
        self.assertFalse((self.job/'positioning/core_positioning.json').exists())
        with self.assertRaises(C.WorkflowError):self.cont('--confirm-core-positioning')
        self.run_provider(callback=lambda:self.cont('--positioning-supplement','实际服务资料'))
        self.assertFalse(state(self.job)['metadata'].get('positioning_needs_input'))

    def test_old_pending_action_requires_explicit_refresh(self):
        C.set_status(self.job,'running_positioning_positioning_polish','positioning')
        with self.assertRaisesRegex(C.WorkflowError,'重新研究'):C.drive(self.job)
        calls=self.run_provider(callback=lambda:self.cont('--rerun-positioning-research'))
        self.assertEqual([ACTIONS[0]],[a for a,_ in calls])
        self.assertEqual('awaiting_competitor_selection',state(self.job)['status'])
        calls += self.run_provider(callback=lambda:self.cont('--confirm-competitors'))
        self.assertEqual(list(ACTIONS),[a for a,_ in calls])

    def test_context_and_pack_export_use_the_same_final_value(self):
        value={**CORE,'applicability_notes':['NOTE_FOR_WRITING']}
        self.finish_positioning(core=value)
        C.atomic_json(self.job/'blueprints/p0_blueprint.json',{'kind':'p0','opening':'从需求展开','sections':[{'heading':'价值','task':'解释选择'}],'ending':'适用人群'})
        for content in [C.natural_author_context(self.job,p0=True),C.selected_competitive_context_markdown(self.job)]:
            for field in ('core_positioning_paragraph','advantage_explanation'):self.assertIn(value[field],content)
            self.assertIn('NOTE_FOR_WRITING',content)
            self.assertNotIn(RESEARCH['research_markdown'],content)
        self.cont('--confirm-core-positioning')
        saved=self.read('deliverables/Reference_Pack_v1/strategy/core_positioning.json')
        self.assertEqual(self.read('positioning/core_positioning.json'),saved)

    def test_provider_prompt_does_not_load_full_legacy_schemas(self):
        calls=self.finish_positioning()
        for _,prompt in calls:
            self.assertNotIn('.schema.json',prompt)
            self.assertNotIn('brand_placement',prompt)
            self.assertNotIn('checks',prompt)
        self.assertIn('research_markdown',calls[0][1])
        self.assertIn('advantage_explanation',calls[1][1])

if __name__=='__main__':unittest.main()
