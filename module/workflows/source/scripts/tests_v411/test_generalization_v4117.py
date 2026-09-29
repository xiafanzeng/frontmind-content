"""Cross-industry input and genre regressions, not an automatic prose score."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared import writing_context as wc
from shared.editorial_contracts import validate_edit_result, validate_finalize_result, EditorialContractError
from shared.model_runtime import request_fingerprint, system_prompt_for

FIXTURES = ROOT / 'acceptance_fixtures/v4.11.7_generalization'
MANIFEST = json.loads((FIXTURES / 'manifest.json').read_text())
CASES = {row['id']: json.loads((FIXTURES / row['path']).read_text()) for row in MANIFEST['cases']}

class GeneralizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        self.example = (FIXTURES / MANIFEST['example_path']).read_text()
        self.put('examples/example.md', self.example)
        self.state = {'workflow_version':'4.11','revision':1,'reference_pack':{'brand':'合成'},
                      'selected_pattern_id':'P00','selected_example_route':'top20','decisions':{},
                      'question':{'question_text':'合成正式问题'}}
        self.wf = SimpleNamespace(load_state=lambda job:self.state,
            load_examples=lambda job,scope:[{'path':'examples/example.md','title':'合成文风示例'}],
            answer_texts=lambda job:['ANSWER_ONE_BEGIN\n必要步骤和建议\nANSWER_ONE_END',
                                    'ANSWER_TWO_BEGIN\n同维度对象与限制\nANSWER_TWO_END'],
            brand_content_context=lambda job:{'p0':'BACKGROUND_FULL_BEGIN\n合成企业背景\nBACKGROUND_FULL_END',
                                            'core_positioning':'QUESTION_POSITIONING_ONLY'},
            user_material_text=lambda *args:'',read_json=lambda path:json.loads(Path(path).read_text()))

    def put(self, path, value):
        p = self.job / path; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False))

    def prepare(self, identity):
        case = CASES[identity]
        self.state['reference_pack']['brand'] = case['brand']
        self.state['selected_pattern_id'] = case['pattern']
        self.state['question']['question_text'] = case['task']
        self.state['decisions']['response_brief'] = case['task']
        self.blueprint = {'kind':'p0' if case['pattern']=='P00' else 'article',
            'opening':'BLUEPRINT_OPENING_MUST_STAY_PRIVATE','ending':'BLUEPRINT_ENDING_MUST_STAY_PRIVATE',
            'sections':[{'heading':t,'task':'BLUEPRINT_PREWRITTEN_SENTENCE'} for t in case['topics']],
            'writing_material_markdown':case['writing_material_markdown'],
            'writing_material_sources':[{'source_ref':'inputs/original.md','use':'合成材料'}],
            'material_adjustments':['BACKSTAGE_SOURCE_REVIEW'], 'estimated_length':'依本篇任务',
            'brand_positioning_use':'本题对象与适用条件','answer_use':'保留必要答案、步骤与比较'}
        self.put('inputs/original.md',case['source_markdown']+'\nRAW_ORIGINAL_FIELD_ORDER')
        for prefix in ('p0','article'):
            self.put('blueprints/'+prefix+'_blueprint.json',self.blueprint)
            self.put('production/'+prefix+'_draft.json',{'article_markdown':'# 合成初稿\n\n## 本篇主题\n\n真实进入编辑的完整段落。',
                'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''})
            self.put('production/'+prefix+'_edited.json',{'edit_status':'accepted',
                'article_markdown':'# 合成初稿\n\n## 本篇主题\n\n真实进入编辑的完整段落。',
                'editorial_notes':[],'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''})
        return case

    def assert_case_route(self, identity):
        c = self.prepare(identity); p0 = c['pattern']=='P00'
        for builder in (wc.prompt_article,wc.prompt_edit,wc.prompt_finalize):
            with self.subTest(stage=builder.__name__):
                prompt=builder(self.wf,self.job,p0=p0)
                self.assertIn(c['writing_material_markdown'],prompt)
                self.assertIn(c['task'],prompt)
                self.assertIn(self.example,prompt)
                self.assertIn(wc.PATTERN_GUIDANCE[c['pattern']],prompt)
                self.assertNotIn('RAW_ORIGINAL_FIELD_ORDER',prompt)
                for token in ('BLUEPRINT_OPENING_MUST_STAY_PRIVATE','BLUEPRINT_ENDING_MUST_STAY_PRIVATE','BLUEPRINT_PREWRITTEN_SENTENCE'):
                    self.assertNotIn(token,prompt)
                for condition in c['required_conditions']:
                    self.assertIn(condition,prompt)
                if not p0:
                    for token in ('ANSWER_ONE_BEGIN','ANSWER_ONE_END','ANSWER_TWO_BEGIN','ANSWER_TWO_END','BACKGROUND_FULL_BEGIN','BACKGROUND_FULL_END'):
                        self.assertIn(token,prompt)
                else:
                    self.assertNotIn('QUESTION_POSITIONING_ONLY',prompt)
                    self.assertNotIn('ANSWER_ONE_BEGIN',prompt)

    def test_fixture_material_forms_are_distinct_and_explicitly_synthetic(self):
        self.assertEqual(len(CASES),8)
        self.assertEqual(len({c['material_form'] for c in CASES.values()}),8)
        for c in CASES.values():
            self.assertIs(c['synthetic'],True)
            self.assertIn('合成',c['source_markdown'])
            self.assertTrue(c['unsupported_outcomes'])
            self.assertTrue(c['human_review_questions'])
        self.assertEqual({r['id'] for r in MANIFEST['cases'] if r['real_model_sample']},
                         {'manufacturing','education','professional_service'})

    def test_shared_prompts_have_no_single_customer_examples_or_fixed_endings(self):
        self.prepare('education')
        prompts=[wc.prompt_blueprint(self.wf,self.job,p0=True),wc.prompt_article(self.wf,self.job,p0=True),
                 wc.prompt_edit(self.wf,self.job,p0=True),wc.prompt_finalize(self.wf,self.job,p0=True),
                 wc.prompt_titles(self.wf,self.job,p0=True,final_markdown='合成终稿')]
        for p in prompts:
            for token in ('一航','港隽','混合交易','气体回收','固定五节','在案例原件结论处停笔'):
                self.assertNotIn(token,p)

    def test_material_conditions_are_shared_but_original_layout_is_not_an_instruction(self):
        self.prepare('manufacturing')
        for p0 in (True,False):
            for builder in (wc.prompt_blueprint,wc.prompt_article,wc.prompt_edit,wc.prompt_finalize):
                self.assertIn(wc.source_and_structure_guidance(),builder(self.wf,self.job,p0=p0))
        self.assertIn('单位、范围、条件和时间状态不能丢失',wc.source_and_structure_guidance())
        self.assertIn('原件没有案例、人物或结果，不补造',wc.source_and_structure_guidance())

    def test_commission_edit_stays_in_its_own_job(self):
        self.prepare('manufacturing')
        before=wc.prompt_article(self.wf,self.job,p0=True)
        self.state['decisions']['blueprint_edits']='LOCAL_ONLY_DO_NOT_EXPORT：只修改第二主题内部承接。'
        changed=wc.prompt_article(self.wf,self.job,p0=True)
        self.assertNotEqual(request_fingerprint('p0_draft',before,offline=True),request_fingerprint('p0_draft',changed,offline=True))
        self.assertIn('LOCAL_ONLY_DO_NOT_EXPORT',changed)
        self.state['decisions'].pop('blueprint_edits')
        self.prepare('education')
        for builder in (wc.prompt_blueprint,wc.prompt_article,wc.prompt_edit,wc.prompt_finalize):
            self.assertNotIn('LOCAL_ONLY_DO_NOT_EXPORT',builder(self.wf,self.job,p0=True))

    def test_editors_do_not_receive_the_author_composition_command(self):
        for identity in ('manufacturing','scenario_solution','event_news','named_comparison'):
            c=self.prepare(identity); p0=c['pattern']=='P00'
            for builder in (wc.prompt_edit,wc.prompt_finalize):
                p=builder(self.wf,self.job,p0=p0)
                self.assertNotIn('执笔任务：',p)
                self.assertNotIn(wc.manuscript_composition_guidance(c['pattern']),p)
                self.assertIn(wc.focused_editorial_guidance(),p)
                self.assertIn('本次新增句',p)

    def test_news_keeps_event_task_instead_of_generic_question_essay_instruction(self):
        self.prepare('event_news')
        p=wc.prompt_article(self.wf,self.job,p0=False)
        self.assertIn('围绕本次事件及实际进展展开的新闻',p)
        self.assertNotIn('写一篇直接回答本题、让读者理解判断理由的文章。',p)
        self.assertIn('不把新闻写成企业通史',p)

    def test_useful_steps_answers_and_comparisons_survive_shared_edit_requirements(self):
        for identity in ('scenario_solution','event_news','named_comparison'):
            self.prepare(identity)
            for builder in (wc.prompt_edit,wc.prompt_finalize):
                p=builder(self.wf,self.job,p0=False)
                self.assertIn('必要步骤、直接回答和共同维度比较',p)
                self.assertIn('不一律删除总结或因果句',p)

    def test_heading_count_and_end_scope_are_only_task_inputs(self):
        self.prepare('education')
        self.blueprint['sections']=[{'heading':'一个主题','task':'不预写句子'}]
        self.put('blueprints/p0_blueprint.json',self.blueprint)
        p=wc.prompt_article(self.wf,self.job,p0=True)
        self.assertIn('一个主题',p)
        self.assertNotIn('课堂记录与家庭沟通',p)
        self.assertIn('不固定开篇、章节数量或顺序',p)
        self.assertIn('不让原件最后一句自动成为文章最后一句',p)

    def test_final_body_change_invalidates_titles_and_full_text_stays_bound(self):
        self.prepare('professional_service')
        first='TITLE_INPUT_START\n尚待确认。\nTITLE_INPUT_END'
        second='TITLE_INPUT_START\n尚待确认，下一步计划复盘。\nTITLE_INPUT_END'
        a=wc.prompt_titles(self.wf,self.job,p0=True,final_markdown=first)
        b=wc.prompt_titles(self.wf,self.job,p0=True,final_markdown=second)
        self.assertIn(first,a);self.assertIn(second,b)
        self.assertNotEqual(request_fingerprint('p0_titles',a),request_fingerprint('p0_titles',b))
        self.assertIn('事实压缩保持同一事项的对象、用途及全部必要条件',b)
        self.assertIn('正文中共同起作用的条件不得漏掉',b)

    def test_edit_contract_does_not_require_cosmetic_changes_for_prose_acceptance(self):
        body='# 合成稿\n\n## 产品内容\n\n准确而自然的一段文字。'
        draft={'article_markdown':body,'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''}
        self.assertEqual(validate_edit_result({**draft,'edit_status':'accepted','editorial_notes':[]},body)['article_markdown'],body)
        self.assertEqual(validate_finalize_result({'outcome':'accepted','article_markdown':body,'editorial_notes':[],'reason':''},body)['article_markdown'],body)
        with self.assertRaises(EditorialContractError):
            validate_edit_result({**draft,'edit_status':'revised','editorial_notes':['声称改写，实际同文。']},body)

    def test_generalization_rules_change_cache_inputs_not_models_or_business_state(self):
        self.prepare('medical_service'); state=json.dumps(self.state,sort_keys=True)
        before=wc.prompt_article(self.wf,self.job,p0=True)
        with patch.object(wc,'source_and_structure_guidance',return_value='CHANGED_SHARED_RULE'):
            after=wc.prompt_article(self.wf,self.job,p0=True)
        self.assertNotEqual(request_fingerprint('p0_draft',before),request_fingerprint('p0_draft',after))
        self.assertEqual(state,json.dumps(self.state,sort_keys=True))

def _test_for(identity):
    def test(self): self.assert_case_route(identity)
    return test

for _identity in CASES:
    setattr(GeneralizationTests,'test_input_route_'+_identity,_test_for(_identity))

if __name__=='__main__': unittest.main()
