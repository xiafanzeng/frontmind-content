"""P0 4.12.8 request/transport tests; no generated-prose quality claims."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import frontmind_workflow as wf, build_release as release
from shared import p0_prose_editor as editor, reader_editing as reader
from shared import brand_stage as bs, brand_references as br, prose_only as po
from shared import p0_style, p0_rework as rw, model_runtime as rt
from shared import writing_context as wc, editorial_contracts as ec
from scripts.tests_v411.test_reader_editing_v4127 import make_job, REFERENCES, BODY, BAD, CLEAN, REASON
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


def request_hash(action, prompt):
    value = {'messages': rt._initial_messages(action, prompt),
             'tool': rt.submit_tool_for(action, prompt=prompt)}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class P0ProseEditorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name); self.job = self.temp / 'job'
        self.state, self.bp = make_job(self.job, contract=editor.CONTRACT)

    def style(self):
        with patch.object(br, 'job_examples', return_value=REFERENCES):
            return wc.prompt_p0_style(wf, self.job)

    def update_bp(self, **changes):
        self.bp.update(changes)
        wf.atomic_json(self.job / 'blueprints/p0_blueprint.json', self.bp)

    def test_current_default_and_schema_accept_current_and_legacy(self):
        current = wf.make_state('current', 'p0')
        self.assertEqual(current['metadata']['p0_style_contract'], editor.CONTRACT)
        self.assertTrue(editor.enabled(current)); self.assertTrue(bs.enabled(current))
        self.assertTrue(po.enabled(current)); self.assertTrue(p0_style.is_deep(current))
        allowed = json.loads((ROOT / 'shared/job_state.schema.json').read_text())['properties']['metadata']['properties']['p0_style_contract']['enum']
        self.assertTrue(p0_style.SUPPORTED_CONTRACTS.issubset(allowed))

    def test_non_p0_job_never_enables_skill_even_with_marker(self):
        state = wf.make_state('question', 'article')
        state['metadata']['p0_style_contract'] = editor.CONTRACT
        self.assertFalse(editor.enabled(state)); self.assertFalse(po.enabled(state))
        self.assertFalse(bs.enabled(state)); self.assertFalse(p0_style.is_deep(state))

    def test_runtime_loads_skill_body_exactly_once_without_frontmatter(self):
        payload = rt.build_payload('p0_style', self.style())
        body = editor.skill_body()
        self.assertEqual(payload['messages'][0]['content'], editor.style_system())
        self.assertEqual(payload['messages'][0]['content'].count(body), 1)
        self.assertNotIn('workflow_contract:', payload['messages'][0]['content'])
        self.assertNotIn('metadata:', payload['messages'][0]['content'])
        self.assertNotIn('原始研究中的来源', str(payload))
        self.assertNotIn(reader.COMMON, payload['messages'][0]['content'])
        self.assertNotIn(body, payload['messages'][1]['content'])

    def test_skill_file_has_real_edit_operations_not_only_forbidden_words(self):
        body = editor.skill_body()
        for phrase in ('问题遍及整段就重写整段', '单方声称', '真实的比较问题',
                       '不设字数', '不能只删除它后面的限定', '准确自然的内容保留'):
            self.assertIn(phrase, body)
        self.assertIn('有用内容', body)
        self.assertNotIn('台心', body)  # No actual client identity in generic author instructions.

    def test_skill_hash_metadata_and_body_are_checked(self):
        directory = self.temp / 'skill'; shutil.copytree(editor.RESOURCE_DIR, directory)
        self.assertEqual(editor.skill_body(directory), editor.skill_body())
        manifest_path = directory / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = '0.0.0'; manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ec.EditorialContractError) as err:
            editor.skill_body(directory)
        self.assertEqual(err.exception.code, 'p0_prose_skill_unavailable')

    def test_missing_or_modified_skill_does_not_silently_use_old_prompt(self):
        directory = self.temp / 'skill'; shutil.copytree(editor.RESOURCE_DIR, directory)
        path = directory / 'SKILL.md'; path.write_text(path.read_text() + '\nmodified')
        with patch.object(editor, 'RESOURCE_DIR', directory), self.assertRaises(ec.EditorialContractError):
            rt.build_payload('p0_style', self.style())
        path.unlink()
        with self.assertRaises(ec.EditorialContractError): editor.skill_body(directory)

    def test_malformed_manifest_empty_body_and_symlink_are_rejected(self):
        directory = self.temp / 'skill'; shutil.copytree(editor.RESOURCE_DIR, directory)
        (directory / 'manifest.json').write_text('[]')
        with self.assertRaises(ec.EditorialContractError): editor.skill_body(directory)
        shutil.rmtree(directory); shutil.copytree(editor.RESOURCE_DIR, directory)
        text = '---\nversion: "1.0.0"\nworkflow_contract: "' + editor.CONTRACT + '"\n---\n'
        (directory / 'SKILL.md').write_text(text)
        manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['sha256'] = hashlib.sha256(text.encode()).hexdigest()
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ec.EditorialContractError): editor.skill_body(directory)
        (directory / 'SKILL.md').unlink()
        (directory / 'SKILL.md').symlink_to(editor.RESOURCE_DIR / 'SKILL.md')
        with self.assertRaises(ec.EditorialContractError): editor.skill_body(directory)

    def test_first_draft_role_is_unchanged_and_e8_does_not_load_skill(self):
        with patch.object(editor, 'skill_body', side_effect=AssertionError('third pass only')):
            self.assertEqual(editor.stage_role('p0_draft'), reader.stage_role('p0_draft'))
            for action, builder in (('p0_blueprint', bs.blueprint_prompt), ('p0_draft', bs.draft_prompt), ('p0_edit', bs.edit_prompt)):
                messages = rt._initial_messages(action, builder(wf, self.job))
                self.assertTrue(messages[1]['content'].startswith(editor.BRAND_MARKER + '\n'))
                self.assertIn(reader.stage_role(action), messages[0]['content'])
        self.assertIn(editor.EDIT_FOCUS, rt._initial_messages('p0_edit', bs.edit_prompt(wf, self.job))[0]['content'])
        self.assertNotIn(editor.EDIT_FOCUS, rt._initial_messages('p0_draft', bs.draft_prompt(wf, self.job))[0]['content'])

    def test_no_new_writer_action_or_external_calls_for_skill(self):
        expected = {'p0_draft', 'p0_edit', 'p0_style', 'p0_titles', 'article_draft', 'article_edit', 'article_titles'}
        self.assertEqual(set(rt.DEEPSEEK_ACTIONS), expected | {'p0_repair', 'article_repair'})
        with patch('urllib.request.urlopen', side_effect=AssertionError('skill must be local')):
            editor.skill_body()
            self.assertNotIn('tools', rt.build_payload('p0_style', self.style()))

    def test_no_examples_in_selection_initial_draft_or_e8(self):
        with patch.object(br, 'job_examples', side_effect=AssertionError('premature examples')):
            self.assertEqual(p0_style.freeze_examples(ROOT, self.job), [])
            for builder in (bs.blueprint_prompt, bs.draft_prompt, bs.edit_prompt):
                self.assertNotIn('<reference_text>', builder(wf, self.job))

    def test_selection_submit_description_does_not_claim_example_reading(self):
        prompt = bs.blueprint_prompt(wf, self.job)
        schema = rt.submit_tool_for('p0_blueprint', prompt=prompt)['function']['parameters']['properties']['result']
        self.assertIn('本阶段不使用品宣例文', schema['properties']['example_use']['description'])
        self.assertIn('必要日期、范围、状态与归因随事实保留', schema['properties']['writing_material_markdown']['description'])
        self.assertNotIn('material_adjustments', schema['required'])
        self.assertEqual(schema['properties']['material_adjustments']['items'], {'type': 'string'})

    def test_complete_e8_task_facts_and_both_original_examples_reach_third(self):
        prompt = self.style()
        self.assertTrue(prompt.startswith(editor.PROSE_MARKER + '\n'))
        for value in (BODY, self.bp['article_brief'], self.bp['writing_material_markdown'], 'CURRENT_REQUIREMENT', 'FACT_CONDITION'):
            self.assertIn(value, prompt)
        self.assertEqual(prompt.count('<reference_text>'), 2)
        for ref in REFERENCES:
            self.assertIn('<reference_text>\n' + ref['text'] + '\n</reference_text>', prompt)
        for value in ('OPENING_SCRIPT_EXCLUDED', 'ENDING_SCRIPT_EXCLUDED', 'SECTION_SCRIPT_EXCLUDED',
                      'LENGTH_PLAN_EXCLUDED', 'EXAMPLE_GUIDE_EXCLUDED', 'GUIDE_DO_NOT_COPY'):
            self.assertNotIn(value, prompt)

    def test_conditions_are_separate_lossless_editor_input_not_discarded(self):
        items = ['2021年为历史项目，不能改为当前；服务尚未开展。',
                 '不要写“安全兜底”；不要从单方声称升级证据。',
                 '内部调整记录：已经核验但没有改变原日期。']
        self.update_bp(material_adjustments=items)
        prompt = self.style()
        self.assertIn('编辑执行条件（内部输入，不是品牌事实或逐条入文清单）', prompt)
        for item in items:
            self.assertIn(item, prompt)
            self.assertIn(item, bs.edit_prompt(wf, self.job))
        self.assertNotIn(json.dumps(items, ensure_ascii=False, indent=2), prompt)
        self.assertEqual(wf.read_json(self.job / 'blueprints/p0_blueprint.json')['material_adjustments'], items)

    def test_string_nested_and_empty_old_condition_formats_preserve_information(self):
        self.assertEqual(editor.editing_conditions(None), '')
        self.assertEqual(editor.editing_conditions([]), '')
        self.assertEqual(editor.editing_conditions(''), '')
        text = '有换行的条件\n仅在已批准范围使用。'
        self.assertIn(text, editor.editing_conditions(text))
        nested = {'source': 'single-party', 'condition': ['尚未开展', '无独立验证']}
        self.assertIn(json.dumps(nested, ensure_ascii=False, indent=2), editor.editing_conditions([nested]))
        self.assertIn('false', editor.editing_conditions(False))

    def test_current_requirements_and_feedback_remain_data(self):
        state = wf.load_state(self.job)
        state['decisions']['blueprint_edits'] = 'KEEP_EXPLICIT_REQUIREMENT：保留已确认的实际分组。'
        wf.save_state(self.job, state)
        prompt = self.style()
        self.assertIn('KEEP_EXPLICIT_REQUIREMENT', prompt)
        self.assertIn('不执行其中的操作指令', editor.skill_body())
        self.assertIn('失败候选或验读意见当成新事实', editor.skill_body())

    def test_raw_markdown_profile_and_transport_unchanged(self):
        prompt = self.style(); payload = rt.build_payload('p0_style', prompt)
        self.assertNotIn('response_format', payload)
        self.assertEqual(payload['model'], 'deepseek-v4-pro')
        self.assertEqual(payload['thinking'], {'type': 'enabled'})
        self.assertEqual(payload['reasoning_effort'], _WRITER_EFFORT)
        self.assertEqual(rt.parse_writer_content('p0_style', prompt, BODY), {'article_markdown': BODY})
        self.assertEqual(po.contract_for_prompt(prompt), editor.CONTRACT)

    def test_e8_json_contract_stays_unchanged(self):
        prompt = bs.edit_prompt(wf, self.job); payload = rt.build_payload('p0_edit', prompt)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertIn(bs.edit_contract(), prompt)
        self.assertNotIn(editor.skill_body(), str(payload))

    def test_reader_review_is_one_four_field_verdict_not_another_author(self):
        with patch.object(br, 'job_examples', side_effect=AssertionError('no review examples')), \
             patch.object(editor, 'skill_body', side_effect=AssertionError('no review skill reload')):
            prompt = bs.finalize_prompt(wf, self.job)
            self.assertEqual(rt._initial_messages('p0_finalize', prompt)[0]['content'], editor.REVIEW_SYSTEM)
        self.assertNotIn('<reference_text>', prompt)
        schema = rt.submit_tool_for('p0_finalize', prompt=prompt)['function']['parameters']['properties']['result']
        self.assertEqual(set(schema['required']), {'outcome', 'article_markdown', 'editorial_notes', 'reason'})
        self.assertEqual(schema['properties']['editorial_notes']['maxItems'], 0)
        self.assertNotIn('revised', schema['properties']['outcome']['enum'])
        self.assertFalse(schema['additionalProperties'])

    def test_output_has_no_self_audit_or_artificial_minimum_edit(self):
        self.assertEqual(wf.validate_action_result(self.job, 'p0_style', {'article_markdown': BODY}), {'article_markdown': BODY})
        for field in ('style_audit', 'editorial_plan', 'reference_alignment', 'editorial_notes'):
            with self.assertRaises(ec.EditorialContractError):
                wf.validate_action_result(self.job, 'p0_style', {'article_markdown': BODY, field: []})
        for body in ('', '```markdown\n' + BODY + '```', json.dumps({'article_markdown': BODY})):
            with self.assertRaises(ec.EditorialContractError): po.parse_article(body)

    def test_final_accepts_only_exact_candidate_and_failure_remains_short(self):
        value = {'outcome': 'accepted', 'article_markdown': BODY, 'editorial_notes': [], 'reason': ''}
        self.assertEqual(wf.validate_action_result(self.job, 'p0_finalize', value), value)
        with self.assertRaises(ec.EditorialContractError): po.validate_final({**value, 'article_markdown': BODY + '\n'}, BODY)
        with self.assertRaises(ec.EditorialContractError): po.validate_final({**value, 'outcome': 'revised'}, BODY)
        failure = dict(outcome='incomplete', article_markdown='', editorial_notes=[], reason='末段仍在评论资料，缺少实际服务介绍。')
        self.assertEqual(po.validate_final(failure, BODY), failure)

    def test_structural_validation_does_not_pretend_to_detect_style(self):
        # Deliberately passes structure even with bad style: humans/model read
        # whole prose. This is not a false claim of quality detection.
        for body in (BAD, BODY + '\n本报告统计口径为已完成项目。\n'):
            wf.validate_article_markdown(body)
            self.assertEqual(po.validate_style({'article_markdown': body}, BODY)['article_markdown'], body)

    def test_skill_text_changes_existing_request_fingerprint(self):
        prompt = self.style()
        original = rt.request_fingerprint('p0_style', prompt, offline=True)
        with patch.object(editor, 'style_system', return_value=editor.style_system() + '\nSYNTHETIC_SKILL_CHANGE'):
            self.assertNotEqual(original, rt.request_fingerprint('p0_style', prompt, offline=True))
        state = wf.load_state(self.job); state['metadata']['p0_style_contract'] = reader.CONTRACT; wf.save_state(self.job, state)
        self.assertNotEqual(original, rt.request_fingerprint('p0_style', self.style(), offline=True))

    def test_old_jobs_do_not_depend_on_new_skill_resource(self):
        state = wf.load_state(self.job); state['metadata']['p0_style_contract'] = reader.CONTRACT; wf.save_state(self.job, state)
        with patch.object(editor, 'RESOURCE_DIR', self.temp / 'missing'):
            self.assertEqual(rt.build_payload('p0_style', self.style())['messages'][0]['content'], reader.STYLE_SYSTEM)
            self.assertEqual(rt._initial_messages('p0_finalize', bs.finalize_prompt(wf, self.job))[0]['content'], reader.REVIEW_SYSTEM)

    def test_23_legacy_request_snapshots_match_actual_baseline(self):
        expected = json.loads((ROOT / 'acceptance_fixtures/p0_prose_editor_v4128/legacy_request_sha256.json').read_text())['sha256']
        actual = {}
        for version in ('4.12.5', '4.12.6', '4.12.7'):
            job = self.temp / version
            state, _ = make_job(job, contract='frontmind-p0-style/' + version)
            if version == '4.12.5': wf.atomic_json(job / 'production/p0_styled.json', bs.fixture_style(BODY, state=state))
            with patch.object(br, 'job_examples', return_value=REFERENCES):
                for action, builder in (('p0_blueprint', bs.blueprint_prompt), ('p0_draft', bs.draft_prompt), ('p0_edit', bs.edit_prompt), ('p0_style', bs.style_prompt), ('p0_finalize', bs.finalize_prompt)):
                    actual[version + '/' + action] = request_hash(action, builder(wf, job))
        for action in ('article_blueprint', 'article_draft', 'article_edit', 'article_finalize', 'article_titles', 'article_title_review', 'p0_titles', 'p0_title_review'):
            actual['unchanged/' + action] = request_hash(action, 'synthetic compatibility request')
        self.assertEqual(actual, expected)

    def test_packaging_includes_runtime_skill_manifest_and_manual_cases(self):
        # The hosted distribution intentionally excludes private customer trees.
        public_roots = tuple(p for p in release.RELEASE_TREE_ROOTS if not p.startswith("customer_inputs/"))
        with patch.object(release, "RELEASE_TREE_ROOTS", public_roots):
            files = release.release_file_set(ROOT)
        for relative in ('shared/p0_prose_editor.py', 'resources/p0_prose_editor/SKILL.md',
                         'resources/p0_prose_editor/manifest.json', 'resources/p0_prose_editor/ADAPTATION.md',
                         'acceptance_fixtures/p0_prose_editor_v4128/cases.json',
                         'acceptance_fixtures/p0_prose_editor_v4128/legacy_request_sha256.json'):
            self.assertIn(relative, files)
        self.assertFalse(any(Path(p).suffix.lower() in {'.ttf', '.otf', '.ttc', '.woff', '.woff2'} for p in files))

    def test_manual_cases_cover_negatives_and_protected_conditions_not_fake_scores(self):
        data = json.loads((ROOT / 'acceptance_fixtures/p0_prose_editor_v4128/cases.json').read_text())
        self.assertEqual(data['live_quality_status'], 'not_run')
        self.assertEqual(len(data['cases']), 15)
        self.assertGreaterEqual(len({x['domain'] for x in data['cases']}), 6)
        self.assertTrue(any(x['kind'] == 'rewrite' for x in data['cases']))
        self.assertTrue(any(x['kind'] == 'preserve' for x in data['cases']))
        self.assertTrue(any(x['kind'] == 'narrow_claim' for x in data['cases']))
        for case in data['cases']:
            self.assertTrue(case['source_facts']); self.assertTrue(case['review_expectation'])
            self.assertNotIn('passed', case); self.assertNotIn('score', case)
        unseen = next(x for x in data['cases'] if x['id'] == 'unseen_summary_variant')
        self.assertNotIn(unseen['input'], editor.skill_body())
        self.assertNotIn('source_identity_matters', self.style())

    def test_new_raw_author_response_and_cache_are_recorded_as_simulated(self):
        # Synthetic transport checks real dispatch and receipt, not model prose.
        br.job_examples(ROOT, self.job, freeze=True)
        prompt = wc.prompt_p0_style(wf, self.job)
        sent = []
        def transport(profile, key, payload):
            sent.append(copy.deepcopy(payload))
            return stream(model=profile['model'], content=CLEAN)
        value = rt.run_action(ROOT, self.job, 'p0_style', prompt,
            lambda v: wf.validate_action_result(self.job, 'p0_style', v),
            transport=transport, offline=True)
        self.assertEqual(value, {'article_markdown': CLEAN})
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['messages'][0]['content'], editor.style_system())
        self.assertNotIn('response_format', sent[0])
        record = rt.action_record(self.job, 'p0_style')
        self.assertEqual(record['execution_mode'], 'offline_simulated')
        self.assertEqual(record['status'], 'succeeded')
        cached = rt.run_action(ROOT, self.job, 'p0_style', prompt,
            lambda v: wf.validate_action_result(self.job, 'p0_style', v),
            transport=transport, offline=True)
        self.assertEqual(cached, value); self.assertEqual(len(sent), 1)

    def test_same_contract_skill_change_does_not_reuse_old_author_response(self):
        br.job_examples(ROOT, self.job, freeze=True)
        prompt = wc.prompt_p0_style(wf, self.job); calls = []
        def transport(profile, key, payload):
            calls.append(payload['messages'][0]['content'])
            return stream(model=profile['model'], content=CLEAN)
        validator = lambda v: wf.validate_action_result(self.job, 'p0_style', v)
        rt.run_action(ROOT, self.job, 'p0_style', prompt, validator, transport=transport, offline=True)
        with patch.object(editor, 'style_system', return_value=editor.style_system() + '\nSYNTHETIC_RESOURCE_CHANGE'):
            rt.run_action(ROOT, self.job, 'p0_style', prompt, validator, transport=transport, offline=True)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0], calls[1])

    def test_current_style_repair_keeps_e8_and_uses_new_skill(self):
        self.job = self.temp / 'rejected'
        make_job(self.job, contract=editor.CONTRACT, rejected=True)
        br.job_examples(ROOT, self.job, freeze=True)
        e8 = (self.job / 'production/p0_edited.json').read_bytes()
        rw.begin(wf, self.job, 'style')
        prompt = wc.prompt_p0_style(wf, self.job)
        # 返工基稿开头按v1.1.5规则剥离：正文与上轮问题必须在，旧开头必须不在
        self.assertIn('基稿开头两段已按返工规则删除', prompt)
        self.assertIn('## 合成业务', prompt); self.assertIn(REASON, prompt)
        self.assertNotIn(BAD.split('\n\n## ')[0], prompt)
        self.assertIn('返工基稿', prompt)
        self.assertEqual((self.job / 'production/p0_edited.json').read_bytes(), e8)
        self.assertEqual(rt._initial_messages('p0_style', prompt)[0]['content'], editor.style_system())
        self.assertEqual(wf.load_state(self.job)['flags']['p0_production_step'], 'style')

    def test_current_edit_repair_uses_rejected_candidate_before_new_style(self):
        self.job = self.temp / 'rejected'
        make_job(self.job, contract=editor.CONTRACT, rejected=True)
        br.job_examples(ROOT, self.job, freeze=True)
        rw.begin(wf, self.job, 'edit')
        self.assertEqual(ec.edit_base_input(wf, self.job, p0=True)['article_markdown'], BAD)
        prompt = bs.edit_prompt(wf, self.job)
        self.assertIn(REASON, prompt)
        self.assertIn(editor.EDIT_FOCUS, rt._initial_messages('p0_edit', prompt)[0]['content'])
        edited = dict(article_markdown=CLEAN, edit_status='revised', editorial_notes=['模拟内容编辑'], requires_blueprint_reconfirmation=False, reconfirmation_reason='')
        wf.atomic_json(self.job / 'production/p0_edited.json', edited)
        self.assertIn(CLEAN, wc.prompt_p0_style(wf, self.job))


if __name__ == '__main__':
    unittest.main()
