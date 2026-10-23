"""Synthetic planning regression; no provider calls or business Jobs are used."""
from __future__ import annotations

from pathlib import Path
import tempfile
import contextlib
import hashlib
import io
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from shared import writing_context, writing_requirements


class P0BlueprintCommissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job = self.root / 'synthetic-p0'
        (self.job / 'blueprints').mkdir(parents=True)
        state = wf.make_state('synthetic-p0', 'p0')
        state.update(status='awaiting_p0_blueprint_confirmation', stage='blueprint', revision=3)
        state['reference_pack'] = {'brand': '合成品牌'}
        state['decisions']['blueprint_edits'] = 'USER_EDIT:围绕品牌产品与支持入口介绍。'
        state['metadata']['effective_writing_requirements'] = {'formatting': 'USER_FORMAT:使用自然段。'}
        wf.save_state(self.job, state)
        self.old_brief = 'MODEL_CANDIDATE_ONLY:仅允许名称、网址、品类三项事实，不采用产品资料。'
        wf.atomic_json(self.job / 'blueprints/p0_blueprint.json', {
            'kind': 'p0', 'article_brief': self.old_brief,
            'estimated_length': 'MODEL_CANDIDATE_LENGTH_ONLY',
            'writing_material_markdown': '合成品牌的旧名称。',
            'writing_material_sources': [{'source_ref': 'synthetic.md', 'use': '旧合成材料'}],
            'sections': [{'heading': '旧候选', 'task': '旧模型安排'}], 'opening': '介绍对象', 'ending': '结束',
        })

    def supplement(self):
        source = self.root / 'synthetic-products.md'
        source.write_text('SYNTHETIC_SOURCE:产品甲与配件支持信息，不含真实客户数据。')
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', str(wf.load_state(self.job)['revision']),
                                      '--p0-blueprint-supplement', str(source)])
        prompts = []
        with patch.object(wf, 'drive', side_effect=lambda job: prompts.append(wf.prompt_blueprint(job, p0=True)) or 0):
            wf.handle_p0_blueprint_pause(args, self.job)
        saved = next((self.job / 'inputs/user_materials/p0').rglob('synthetic-products.md'))
        self.assertEqual(saved.read_bytes(), source.read_bytes())
        return prompts[0]

    def test_supplement_replans_from_user_requirements_and_writer_keeps_confirmed_blueprint(self):
        prior = (self.job / 'blueprints/p0_blueprint.json').read_bytes()
        prompt = self.supplement()
        commission = prompt.split('<current_commission>', 1)[1].split('</current_commission>', 1)[0]
        self.assertNotIn(self.old_brief, commission)
        self.assertNotIn('MODEL_CANDIDATE_LENGTH_ONLY', commission)
        self.assertIn('USER_FORMAT', commission)
        self.assertIn('默认3500', commission)
        self.assertIn('USER_EDIT', prompt)
        self.assertIn('synthetic-products.md', prompt)
        self.assertIn('第三遍另行载入星源智与港隽两篇固定完整例文', prompt)
        self.assertEqual((self.job / 'blueprints/p0_blueprint.json').read_bytes(), prior)
        self.assertEqual(wf.load_state(self.job)['decisions']['blueprint_edits'], 'USER_EDIT:围绕品牌产品与支持入口介绍。')

        # A generated replacement is only used by writers after the real pause
        # is confirmed. This assertion exercises the unchanged writer builder.
        bp = wf.read_json(self.job / 'blueprints/p0_blueprint.json')
        bp['article_brief'] = 'CONFIRMED_BRIEF:介绍合成产品甲与支持入口。'
        bp['estimated_length'] = 'CONFIRMED_LENGTH'
        wf.atomic_json(self.job / 'blueprints/p0_blueprint.json', bp)
        state = wf.load_state(self.job)
        state.update(status='running_p0_production', revision=4)
        state['decisions']['p0_blueprint_confirmation'] = {'revision': 4, 'confirmed_at': 'synthetic'}
        wf.save_state(self.job, state)
        writer = writing_context.prompt_article(wf, self.job, p0=True)
        self.assertIn('CONFIRMED_BRIEF', writer)
        self.assertIn('CONFIRMED_LENGTH', writer)

    def test_unmarked_frozen_p0_keeps_legacy_planning_and_explicit_edits(self):
        state = wf.load_state(self.job)
        state['metadata'].pop('p0_blueprint_commission_mode')
        wf.save_state(self.job, state)
        prompt = self.supplement()
        commission = prompt.split('<current_commission>', 1)[1].split('</current_commission>', 1)[0]
        self.assertIn(self.old_brief, commission)
        self.assertIn('MODEL_CANDIDATE_LENGTH_ONLY', commission)
        self.assertIn('USER_EDIT', prompt)
        self.assertNotIn('p0_blueprint_commission_mode', wf.load_state(self.job)['metadata'])
        self.assertNotIn('p0_blueprint_commission_mode', wf.make_state('synthetic-article', 'article')['metadata'])
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', '3', '--accept-p0-blueprint'])
        with patch.object(wf, 'drive', return_value=0):
            wf.handle_p0_blueprint_pause(args, self.job)
        self.assertEqual(set(wf.load_state(self.job)['decisions']['p0_blueprint_confirmation']), {'revision', 'confirmed_at'})

    def test_replanning_keeps_only_the_snapshot_from_actual_native_accept(self):
        state = wf.load_state(self.job)
        state['metadata']['effective_writing_requirements'] = {}
        wf.save_state(self.job, state)
        bp = wf.read_json(self.job / 'blueprints/p0_blueprint.json')
        bp.update(article_brief='APPROVED_BRIEF:介绍产品与支持入口。', estimated_length='APPROVED_LENGTH',
                  formatting='APPROVED_FORMAT:业务段落单独加粗。')
        wf.atomic_json(self.job / 'blueprints/p0_blueprint.json', bp)
        approved_sha = hashlib.sha256((self.job / 'blueprints/p0_blueprint.json').read_bytes()).hexdigest()
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', '3', '--accept-p0-blueprint'])
        with patch.object(wf, 'drive', return_value=0):
            wf.handle_p0_blueprint_pause(args, self.job)
        approved = wf.load_state(self.job)['decisions']['p0_blueprint_confirmation']
        self.assertEqual(approved['blueprint_sha256'], approved_sha)
        self.assertEqual(approved['writing_requirements']['article_brief'], bp['article_brief'])
        self.assertEqual(approved['writing_requirements']['formatting'], bp['formatting'])

        # Generate another real native preview without accepting it. A leftover
        # confirmation flag must never approve this newly generated candidate.
        candidate = dict(bp, article_brief='UNAPPROVED_NEW_LIMIT:再限为三项事实。',
                         estimated_length='UNAPPROVED_LENGTH', formatting='UNAPPROVED_FORMAT')
        with patch.object(wf, 'ensure_action', return_value=candidate), contextlib.redirect_stdout(io.StringIO()):
            wf.run_p0_blueprint(self.job)
        self.assertEqual(wf.load_state(self.job)['revision'], 4)
        self.assertEqual(wf.read_json(self.job / 'blueprints/p0_blueprint.json')['article_brief'], candidate['article_brief'])
        prompt = self.supplement()
        current = prompt.split('<current_commission>', 1)[1].split('</current_commission>', 1)[0]
        context = prompt.split('<confirmed_p0_blueprint_context>', 1)[1].split('</confirmed_p0_blueprint_context>', 1)[0]
        self.assertIn('APPROVED_BRIEF', context)
        self.assertIn('APPROVED_FORMAT', context)
        self.assertIn('APPROVED_LENGTH', context)
        self.assertIn(approved_sha, context)
        self.assertNotIn('APPROVED_BRIEF', current)
        self.assertNotIn('APPROVED_LENGTH', current)
        self.assertNotIn('默认3500', current)
        self.assertNotIn('UNAPPROVED_NEW_LIMIT', prompt)
        self.assertNotIn('UNAPPROVED_FORMAT', prompt)
        self.assertIn('USER_EDIT', prompt)
        self.assertEqual(wf.load_state(self.job)['decisions']['p0_blueprint_confirmation'], approved)

    def test_explicit_durable_article_brief_still_overrides_model_candidate(self):
        state = wf.load_state(self.job)
        state['metadata']['effective_writing_requirements']['article_brief'] = 'USER_EXPLICIT_BRIEF:聚焦产品甲。'
        wf.save_state(self.job, state)
        commission = self.supplement().split('<current_commission>', 1)[1].split('</current_commission>', 1)[0]
        self.assertIn('USER_EXPLICIT_BRIEF', commission)
        self.assertNotIn(self.old_brief, commission)


if __name__ == '__main__':
    unittest.main()
