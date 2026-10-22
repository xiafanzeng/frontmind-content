"""Confirmed positioning reaches planning; old requests remain immutable.

All inputs are synthetic and all request construction is offline.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from shared import editorial_preparation, model_runtime, p02_selection
from shared import question_positioning_handoff as handoff
from shared import writing_context_v16 as prose


class PositioningHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.job = Path(temporary.name) / 'job'
        wf.ensure_new_job(self.job, 'article', offline=True)
        state = wf.load_state(self.job)
        # Pin the historical direct-handoff contract; v16.5 carries selected
        # positioning content onward through preparation instead.
        state['metadata']['natural_prose_contract'] = prose.CONTRACT
        state['selected_pattern_id'] = 'P01'
        state['question'] = {'question_text': '合成企业提供怎样的设计服务？', 'period_id': 'current'}
        state['reference_pack'] = {'brand': '合成企业', 'path': str(self.job / '00_input/reference_pack.zip')}
        # Exercise positioning independently; pool ingestion/selection has its
        # own integration fixtures and must not be bypassed in a real new job.
        state['metadata'].pop('article_pool_policy', None)
        state['metadata'][handoff.METADATA_KEY] = handoff.CONTRACT
        state['metadata']['effective_writing_requirements'] = {
            'article_brief': 'CURRENT_COMMISSION 介绍合成企业的设计业务。',
            'estimated_length': '2800—3100字',
        }
        state['decisions']['response_brief'] = '介绍合成企业。'
        state['decisions']['question_positioning_confirmation'] = {'confirmed': True, 'pattern_id': 'P01'}
        wf.save_state(self.job, state)
        self.positioning = {
            'schema_version': '4.11', 'artifact_type': 'frontmind_question_positioning',
            'pattern_id': 'P01', 'question': state['question']['question_text'],
            'brand': '合成企业', 'natural_analysis': 'CONFIRMED_FOCUS 以跨部门协作的具体业务安排体现差异。',
            'candidate_scope': ['合成企业'], 'material_adjustments': ['POSITIONING_ADJUSTMENT 简述企业背景。'],
        }
        self.write_positioning()
        prepared = editorial_preparation.fixture()
        prepared['writing_material_markdown'] = 'CLEAN_FACTS 合成企业提供设计服务。'
        editorial_preparation.freeze(wf, self.job, prepared)
        blueprint = {
            'kind': 'article', 'pattern_id': 'P01', 'question': state['question']['question_text'],
            'article_brief': 'BLUEPRINT_BRIEF', 'opening': '介绍设计需求。',
            'sections': [{'heading': '代表业务', 'task': '介绍业务细节。'}],
            'ending': '最后一项业务完成后收束。', 'candidate_order': ['合成企业'],
        }
        wf.atomic_json(self.job / 'blueprints/article_blueprint.json',
                       editorial_preparation.bind_blueprint(self.job, blueprint))
        examples = patch('shared.writing_context_v14.examples', return_value='KINGDEE_THINKPAD_UNCHANGED')
        examples.start()
        self.addCleanup(examples.stop)

    def write_positioning(self):
        wf.atomic_json(self.job / handoff.PATH, self.positioning)

    def prompts(self):
        return {
            'article_editorial_preparation': prose.prompt_preparation(wf, self.job),
            'article_blueprint': prose.prompt_blueprint(wf, self.job),
        }

    def test_confirmed_meaning_and_adjustments_reach_both_planning_requests(self):
        for action, prompt in self.prompts().items():
            with self.subTest(action=action):
                self.assertEqual(prompt.count('CONFIRMED_FOCUS'), 1)
                self.assertEqual(prompt.count('POSITIONING_ADJUSTMENT'), 1)
                self.assertIn('CURRENT_COMMISSION', prompt)
                self.assertIn(handoff.GUIDANCE, prompt)
        # The author receives the resulting formal blueprint and original
        # prose examples, not another raw positioning/research dossier.
        draft = prose.prompt_article(wf, self.job)
        self.assertNotIn('CONFIRMED_FOCUS', draft)
        self.assertIn('KINGDEE_THINKPAD_UNCHANGED', draft)
        self.assertIn('CLEAN_FACTS', draft)

    def test_explicit_current_requirements_stay_authoritative_and_unmodified(self):
        state = wf.load_state(self.job)
        state['metadata']['effective_writing_requirements'].update(
            brand_positioning_use='LATEST_POSITIONING 改以交付速度为重点。',
            candidate_order=['合成企业'],
        )
        state['decisions']['blueprint_edits'] = 'LATEST_BLUEPRINT 代表业务优先，企业背景放后。'
        wf.save_state(self.job, state)
        before = (self.job / 'job_state.json').read_bytes()
        for prompt in self.prompts().values():
            self.assertIn('LATEST_POSITIONING', prompt)
            self.assertIn('CONFIRMED_FOCUS', prompt)
            self.assertIn('当前明确写作要求、本轮构思修改及已确认的P02三家名单与顺序优先', prompt)
        self.assertIn('LATEST_BLUEPRINT', prose.prompt_blueprint(wf, self.job))
        self.assertEqual((self.job / 'job_state.json').read_bytes(), before)
        current = json.loads(prose.preparation_commission(wf, self.job).split('\n', 1)[1].rsplit('\n', 1)[0])
        self.assertEqual(current['brand_positioning_use'], state['metadata']['effective_writing_requirements']['brand_positioning_use'])
        self.assertNotIn('natural_analysis', current)

    def test_reconfirmed_positioning_is_not_overridden_by_previous_blueprint_fields(self):
        state = wf.load_state(self.job)
        state['metadata']['effective_writing_requirements'].pop('article_brief')
        state['decisions']['response_brief'] = 'CURRENT_RESPONSE_BRIEF 介绍当前已确认的业务方向。'
        wf.save_state(self.job, state)
        path = self.job / 'blueprints/article_blueprint.json'
        blueprint = wf.read_json(path)
        blueprint.update(
            article_brief='OLD_GENERATED_BRIEF',
            brand_positioning_use='OLD_GENERATED_POSITIONING',
            recommendation_relationships='OLD_GENERATED_RELATIONSHIPS',
            candidate_order=['OLD_GENERATED_CANDIDATE'],
            formatting='RETAIN_FORMATTING', reference_roles='RETAIN_REFERENCE_ROLE',
        )
        wf.atomic_json(path, blueprint)
        body_commission = prose.commission(wf, self.job)
        prompt = prose.prompt_blueprint(wf, self.job)
        for value in ('OLD_GENERATED_BRIEF', 'OLD_GENERATED_POSITIONING',
                      'OLD_GENERATED_RELATIONSHIPS', 'OLD_GENERATED_CANDIDATE'):
            self.assertNotIn(value, prompt)
        for value in ('CURRENT_RESPONSE_BRIEF', 'CONFIRMED_FOCUS', '2800—3100字',
                      'RETAIN_FORMATTING', 'RETAIN_REFERENCE_ROLE'):
            self.assertIn(value, prompt)
        self.assertEqual(prose.commission(wf, self.job), body_commission)
        self.assertEqual(wf.read_json(path), blueprint)
        state['metadata']['effective_writing_requirements'].update(
            brand_positioning_use='EXPLICIT_USER_POSITIONING',
            recommendation_relationships='EXPLICIT_USER_RELATIONSHIPS',
            candidate_order=['EXPLICIT_USER_CANDIDATE'],
        )
        wf.save_state(self.job, state)
        prompt = prose.prompt_blueprint(wf, self.job)
        for value in ('EXPLICIT_USER_POSITIONING', 'EXPLICIT_USER_RELATIONSHIPS', 'EXPLICIT_USER_CANDIDATE'):
            self.assertIn(value, prompt)

    def test_unconfirmed_or_other_question_brand_pattern_never_leaks(self):
        original = wf.load_state(self.job)
        for confirmation in (None, {}, {'confirmed': False}, {'confirmed': 'true'},
                             {'confirmed': True, 'pattern_id': 'P02'}):
            state = copy.deepcopy(original)
            if confirmation is None:
                state['decisions'].pop('question_positioning_confirmation', None)
            else:
                state['decisions']['question_positioning_confirmation'] = confirmation
            wf.save_state(self.job, state)
            with self.subTest(confirmation=confirmation):
                self.assertEqual(handoff.context(wf, self.job), '')
        wf.save_state(self.job, original)
        for field, value in (('question', '另一问题'), ('brand', '另一品牌'), ('pattern_id', 'P02')):
            changed = {**self.positioning, field: value}
            wf.atomic_json(self.job / handoff.PATH, changed)
            with self.subTest(field=field):
                self.assertTrue(all('CONFIRMED_FOCUS' not in prompt for prompt in self.prompts().values()))
        (self.job / handoff.PATH).unlink()
        self.assertEqual(handoff.context(wf, self.job), '')

    def test_old_unmarked_requests_and_saved_payloads_remain_unchanged(self):
        state = wf.load_state(self.job)
        state['metadata'].pop(handoff.METADATA_KEY)
        wf.save_state(self.job, state)
        original = self.prompts()
        payloads = {action: model_runtime.build_payload(action, prompt) for action, prompt in original.items()}
        fingerprints = {action: model_runtime.request_fingerprint(action, prompt, offline=True)
                        for action, prompt in original.items()}
        self.positioning['natural_analysis'] += ' CHANGED_LATER'
        self.write_positioning()
        self.assertEqual(self.prompts(), original)
        self.assertTrue(all('CONFIRMED_FOCUS' not in prompt for prompt in original.values()))
        # Enabling the new contract changes only newly built prompts. A saved
        # prompt still resolves to exactly its prior system, schema and input.
        state['metadata'][handoff.METADATA_KEY] = handoff.CONTRACT
        wf.save_state(self.job, state)
        for action, prompt in self.prompts().items():
            self.assertNotEqual(model_runtime.request_fingerprint(action, prompt, offline=True), fingerprints[action])
            self.assertEqual(model_runtime.build_payload(action, original[action]), payloads[action])

    def test_only_supported_new_article_contracts_opt_in(self):
        state = wf.load_state(self.job)
        for patch_value in (
            {'job_kind': 'p0'}, {'selected_pattern_id': 'P03'},
            {'metadata': {**state['metadata'], 'natural_prose_contract': 'frontmind-natural-prose/15'}},
        ):
            with self.subTest(patch_value=patch_value):
                self.assertFalse(handoff.enabled({**state, **patch_value}))

    def test_p02_requires_matching_confirmation_hash_and_exact_three_entity_scope(self):
        state = wf.load_state(self.job)
        state['selected_pattern_id'] = 'P02'
        state['metadata']['p02_selection_policy'] = p02_selection.CONTRACT
        wf.save_state(self.job, state)
        targets = [{'name': name, 'aliases': [], 'kind': 'brand'} for name in ('合成甲', '合成乙')]
        record = p02_selection.freeze(wf, self.job, {'comparison_targets': targets, 'peer_examples': []})
        names = [entity['name'] for entity in record['entities']]
        self.positioning.update(pattern_id='P02', candidate_scope=names)
        self.write_positioning()
        state = wf.load_state(self.job)
        state['decisions']['question_positioning_confirmation'] = {
            'confirmed': True, 'pattern_id': 'P02', 'p02_selection_hash': record['selection_hash'],
        }
        wf.save_state(self.job, state)
        for prompt in self.prompts().values():
            self.assertIn('CONFIRMED_FOCUS', prompt)
            self.assertIn(p02_selection.GUIDANCE, prompt)
            self.assertIn(record['selection_hash'], prompt)
        for stale_scope in (names + ['旧第四家'], list(reversed(names)), None):
            self.positioning['candidate_scope'] = stale_scope
            self.write_positioning()
            with self.subTest(stale_scope=stale_scope):
                self.assertEqual(handoff.context(wf, self.job), '')
        self.positioning['candidate_scope'] = names
        self.write_positioning()
        state['decisions']['question_positioning_confirmation']['p02_selection_hash'] = 'old-selection'
        wf.save_state(self.job, state)
        self.assertEqual(handoff.context(wf, self.job), '')

    def test_selected_pool_reading_is_planning_only_and_does_not_replace_style_examples(self):
        with patch('shared.article_pool.prompt_references', return_value='SELECTED_POOL_ARTICLE_FULL_TEXT'):
            for prompt in self.prompts().values():
                self.assertEqual(prompt.count('SELECTED_POOL_ARTICLE_FULL_TEXT'), 1)
            draft = prose.prompt_article(wf, self.job)
        self.assertNotIn('SELECTED_POOL_ARTICLE_FULL_TEXT', draft)
        self.assertIn('KINGDEE_THINKPAD_UNCHANGED', draft)


if __name__ == '__main__':
    unittest.main()
