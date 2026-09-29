"""Effective 4.12.7 request tests, not claims about generated prose quality."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from shared import brand_references as br, brand_stage as bs, reader_editing as reader
from shared import prose_only as po, model_runtime as rt, p0_style, writing_context as wc
from shared import editorial_contracts as ec

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
BODY = '# 合成接口测试\n\n这是测试用正文，不代表实际客户或写作质量。\n\n## 合成业务\n\n' + '此处只用于离线验证文字传递、阶段绑定和完整正文保存，不提供任何实际业务结论。' * 10 + '\n'
BAD = BODY + '\n这是台心医美一贯坚持的沟通口径。\n'
CLEAN = BODY + '\n此段标记仅用于区分已修改的离线测试候选。\n'
REASON = '结尾“这是台心医美一贯坚持的沟通口径”是内部宣传说明；删除该说明并通读全文，保留必要事实条件。'
REFERENCES = [dict(id=i, title=i + '合成测试例文', text='FIRST_' + i + '\nMIDDLE_' + i + '\nLAST_' + i,
                   guide='GUIDE_DO_NOT_COPY', source_url='offline://fixture', publication='offline')
              for i in ('xingyuanzhi', 'gangjun')]


def make_job(job: Path, *, contract=reader.CONTRACT, rejected=False):
    job.mkdir(parents=True)
    state = wf.make_state('reader-fixture', 'p0')
    state['metadata'].pop('writing_editor_contract', None)  # Historical fixture.
    state['metadata']['p0_style_contract'] = contract
    state.update(reference_pack={'brand': '合成测试品牌'}, revision=7)
    state['flags']['offline_fixture'] = True
    state['decisions']['response_brief'] = 'CURRENT_REQUIREMENT：不要编造业务事实。'
    bp = dict(kind='p0', article_brief='BRIEF_FOCUS：介绍具体业务；机构背景仅作辅助。',
              opening='OPENING_SCRIPT_EXCLUDED', ending='ENDING_SCRIPT_EXCLUDED',
              sections=[dict(heading='章节脚本排除', task='SECTION_SCRIPT_EXCLUDED')],
              estimated_length='LENGTH_PLAN_EXCLUDED', example_use='EXAMPLE_GUIDE_EXCLUDED',
              material_adjustments=['FACT_CONDITION：历史项目不能改为当前；必要范围保留。'],
              writing_material_markdown='MATERIAL_START\n这里只包含本篇选定的合成事实，不是全文目录。\nMATERIAL_END',
              writing_material_sources=['synthetic_source'])
    wf.save_state(job, state)
    wf.atomic_json(job / 'blueprints/p0_blueprint.json', bp)
    wf.atomic_json(job / 'production/p0_draft.json', dict(article_markdown=BODY, requires_blueprint_reconfirmation=False, reconfirmation_reason=''))
    wf.atomic_json(job / 'production/p0_edited.json', dict(article_markdown=BODY, edit_status='accepted', editorial_notes=[], requires_blueprint_reconfirmation=False, reconfirmation_reason=''))
    wf.atomic_json(job / 'production/p0_styled.json', {'article_markdown': BAD if rejected else BODY})
    if rejected:
        state.update(status='running_p0_production', stage='p0_production', pending_action={
            'action': 'p0_finalize', 'error': {'code': 'host_incomplete', 'message': REASON}})
        state['flags']['p0_production_step'] = 'finalize'
        wf.save_state(job, state)
        wf.atomic_json(wf.action_paths(job, 'p0_style')[2], {'article_markdown': BAD})
        wf.atomic_json(wf.action_paths(job, 'p0_finalize')[2], dict(outcome='incomplete', article_markdown='', editorial_notes=[], reason=REASON))
    return state, bp


class ReaderEditingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.job = Path(tmp.name) / 'job'
        self.state, self.bp = make_job(self.job)

    def style(self):
        with patch.object(br, 'job_examples', return_value=REFERENCES):
            return wc.prompt_p0_style(wf, self.job)

    def test_default_is_versioned_without_changing_question_jobs(self):
        state = wf.make_state('new', 'p0')
        self.assertEqual(state['metadata']['p0_style_contract'], p0_style.DEFAULT_P0_STYLE_CONTRACT)
        self.assertTrue(bs.enabled(state)); self.assertTrue(po.enabled(state)); self.assertTrue(p0_style.is_deep(state))
        self.assertFalse(reader.enabled(wf.make_state('question', 'article')))
        schema = json.loads((ROOT / 'shared/job_state.schema.json').read_text())
        for version in (reader.CONTRACT, po.CONTRACT, bs.CONTRACT):
            self.assertIn(version, schema['properties']['metadata']['properties']['p0_style_contract']['enum'])

    def test_common_editing_standards_reach_actual_first_two_system_messages(self):
        for action, builder in (('p0_draft', bs.draft_prompt), ('p0_edit', bs.edit_prompt)):
            prompt = builder(wf, self.job)
            messages = rt._initial_messages(action, prompt)
            self.assertTrue(prompt.startswith(reader.BRAND_MARKER + '\n'))
            self.assertIn(reader.COMMON, messages[0]['content'])
            self.assertNotIn(reader.COMMON, messages[1]['content'])  # No repeated rule stack.
            self.assertIn('JSON', messages[0]['content'])
        self.assertIn('不留给第三遍补救', rt._initial_messages('p0_edit', bs.edit_prompt(wf, self.job))[0]['content'])

    def test_selection_distinguishes_facts_conditions_and_writing_instructions(self):
        messages = rt._initial_messages('p0_blueprint', bs.blueprint_prompt(wf, self.job))
        self.assertIn(reader.SELECTION, messages[0]['content'])
        self.assertIn('一至两句', messages[0]['content'])
        self.assertIn('source_ref', messages[1]['content'])
        self.assertNotIn('article_brief 与 example_use 将传给作者与编辑', messages[1]['content'])
        self.assertIn('必要日期、范围和限制须在对应业务处保留', bs.draft_prompt(wf, self.job))

    def test_no_reference_acquisition_in_blueprint_draft_or_e8(self):
        with patch.object(br, 'job_examples', side_effect=AssertionError('premature examples')):
            self.assertEqual(p0_style.freeze_examples(ROOT, self.job), [])
            for action, builder in (('p0_blueprint', bs.blueprint_prompt), ('p0_draft', bs.draft_prompt), ('p0_edit', bs.edit_prompt)):
                self.assertNotIn('<reference_text>', builder(wf, self.job))
                self.assertNotIn('<reference_text>', rt._initial_messages(action, builder(wf, self.job))[0]['content'])

    def test_normal_third_pass_has_complete_e8_task_facts_and_two_full_examples(self):
        prompt = self.style()
        for text in (BODY, self.bp['article_brief'], self.bp['writing_material_markdown'], 'CURRENT_REQUIREMENT', 'FACT_CONDITION'):
            self.assertIn(text, prompt)
        for ref in REFERENCES:
            self.assertIn(ref['text'], prompt)
        self.assertEqual(prompt.count('<reference_text>'), 2)
        self.assertIn('本篇已确认任务与主次（文章任务，不是品牌事实）', prompt)
        for forbidden in ('OPENING_SCRIPT_EXCLUDED', 'ENDING_SCRIPT_EXCLUDED', 'SECTION_SCRIPT_EXCLUDED',
                          'LENGTH_PLAN_EXCLUDED', 'EXAMPLE_GUIDE_EXCLUDED', 'GUIDE_DO_NOT_COPY',
                          'editorial_plan', 'style_audit', 'reference_alignment', 'unresolved_issues'):
            self.assertNotIn(forbidden, prompt)

    def test_raw_markdown_wire_and_real_author_identity_unchanged(self):
        payload = rt.build_payload('p0_style', self.style())
        self.assertNotIn('response_format', payload)
        self.assertEqual(payload['model'], 'deepseek-v4-pro')
        self.assertEqual(payload['thinking'], {'type': 'enabled'})
        self.assertEqual(payload['reasoning_effort'], _WRITER_EFFORT)
        self.assertEqual(payload['messages'][0]['content'], reader.STYLE_SYSTEM)
        self.assertEqual(rt.parse_writer_content('p0_style', self.style(), BODY), {'article_markdown': BODY})

    def test_reference_warnings_are_in_the_effective_system_not_rewritten_examples(self):
        payload = rt.build_payload('p0_style', self.style())
        self.assertIn('不是每句话都应模仿的质量标准', payload['messages'][0]['content'])
        for phrase in ('对外表述', '对外口径', '表达原则', '另一句空话补位'):
            self.assertIn(phrase, payload['messages'][0]['content'])
        for ref in REFERENCES:
            self.assertIn('<reference_text>\n' + ref['text'] + '\n</reference_text>', payload['messages'][1]['content'])

    def test_review_is_reader_facing_but_still_only_four_fields(self):
        with patch.object(br, 'job_examples', side_effect=AssertionError('no review examples')):
            prompt = bs.finalize_prompt(wf, self.job)
        self.assertEqual(rt._initial_messages('p0_finalize', prompt)[0]['content'], reader.REVIEW_SYSTEM)
        for phrase in ('不属于个人措辞偏好', '位置、原句和具体问题', '不能因为没有事实冲突就放行'):
            self.assertIn(phrase, reader.REVIEW_SYSTEM)
        self.assertIn(self.bp['article_brief'], prompt)
        self.assertIn('FACT_CONDITION', prompt)
        self.assertNotIn('<reference_text>', prompt)
        tool = rt.submit_tool_for('p0_finalize', prompt=prompt)
        schema = tool['function']['parameters']['properties']['result']
        self.assertEqual(set(schema['required']), {'outcome', 'article_markdown', 'editorial_notes', 'reason'})
        self.assertEqual(schema['properties']['editorial_notes']['maxItems'], 0)
        self.assertNotIn('revised', schema['properties']['outcome']['enum'])
        self.assertFalse(schema['additionalProperties'])

    def test_no_lexical_detector_or_silent_body_rewrite_added(self):
        # Both can pass structure. Real prose judgment belongs to the editor;
        # this test explicitly does NOT say the bad prose is publishable.
        for body in (BAD, BODY + '\n本报告的统计口径为本篇给定的合成定义。\n'):
            wf.validate_article_markdown(body)
            self.assertEqual(po.validate_style({'article_markdown': body}, BODY)['article_markdown'], body)
        self.assertIn('这不是禁词表', reader.COMMON)
        self.assertIn('必要限制', reader.COMMON)
        self.assertIn('不把自然表达等同于短句', reader.COMMON)

    def test_final_host_cannot_patch_or_fall_back_to_e8(self):
        v = dict(outcome='accepted', article_markdown=BODY, editorial_notes=[], reason='')
        self.assertEqual(po.validate_final(v, BODY), v)
        for changed in (CLEAN, BODY + '\n'):
            with self.assertRaises(ec.EditorialContractError):
                po.validate_final({**v, 'article_markdown': changed}, BODY)
        with self.assertRaises(ec.EditorialContractError):
            po.validate_final({**v, 'outcome': 'revised', 'article_markdown': CLEAN, 'editorial_notes': ['Changed']}, BODY)

    def test_incomplete_or_business_reconfirmation_remain_small_verdicts(self):
        for outcome in ('incomplete', 'requires_blueprint_reconfirmation'):
            v = dict(outcome=outcome, article_markdown='', editorial_notes=[], reason=REASON)
            self.assertEqual(po.validate_final(v, BODY), v)
        with self.assertRaises(ec.EditorialContractError):
            po.validate_final(dict(outcome='incomplete', article_markdown='', editorial_notes=[], reason=''), BODY)

    def test_legacy_4126_still_uses_legacy_prompts_and_omits_brief(self):
        state = wf.load_state(self.job); state['metadata']['p0_style_contract'] = po.CONTRACT; wf.save_state(self.job, state)
        style = self.style()
        self.assertTrue(style.startswith(po.MARKER + '\n'))
        self.assertNotIn('BRIEF_FOCUS', style)
        self.assertEqual(rt._initial_messages('p0_style', style)[0]['content'], po.STYLE_SYSTEM)
        self.assertEqual(rt._initial_messages('p0_finalize', bs.finalize_prompt(wf, self.job))[0]['content'], po.REVIEW_SYSTEM)
        for action, builder in (('p0_blueprint', bs.blueprint_prompt), ('p0_draft', bs.draft_prompt), ('p0_edit', bs.edit_prompt)):
            self.assertTrue(builder(wf, self.job).startswith(bs.MARKER + '\n'))
            self.assertNotIn(reader.COMMON, rt._initial_messages(action, builder(wf, self.job))[0]['content'])

    def test_versioned_fingerprints_prevent_legacy_output_reuse(self):
        new = self.style()
        state = wf.load_state(self.job); state['metadata']['p0_style_contract'] = po.CONTRACT; wf.save_state(self.job, state)
        old = self.style()
        self.assertNotEqual(rt.request_fingerprint('p0_style', old), rt.request_fingerprint('p0_style', new))
        self.assertEqual(po.contract_for_prompt(old), po.CONTRACT)
        self.assertEqual(po.contract_for_prompt(new), reader.CONTRACT)

    def test_regression_cases_have_counterexamples_and_no_fake_quality_pass(self):
        data = json.loads((ROOT / 'acceptance_fixtures/p0_reader_editing_v4127/cases.json').read_text())
        self.assertEqual(data['live_quality_status'], 'not_run')
        self.assertGreaterEqual(len(data['cases']), 8)
        self.assertTrue(any(c['kind'] == 'preserve' for c in data['cases']))
        self.assertTrue(any('沟通口径' in c['input'] for c in data['cases']))
        self.assertTrue(all(c.get('review_expectation') for c in data['cases']))


if __name__ == '__main__':
    unittest.main()
