"""行业盘点契约的关键回归测试；不调用付费模型。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shared import industry_roundup, p02_selection
from scripts import frontmind_workflow as wf


class IndustryRoundupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        (self.job / 'inputs').mkdir()
        (self.job / 'inputs/source.md').write_text('Swift 4 最高转速 11.5 万转。\n', encoding='utf-8')
        self.state = {'job_kind': 'article', 'selected_pattern_id': 'P02',
                      'reference_pack': {'brand': '徕芬'},
                      'metadata': {'p02_selection_policy': p02_selection.CONTRACT}}
        industry_roundup.configure(self.state, 'industry_roundup', ['徕芬', '戴森', '追觅'])

    def test_genre_overrides_three_entity_policy(self):
        self.assertFalse(p02_selection.research_enabled(self.state))
        self.assertEqual(industry_roundup.validate_scope(self.state), ['徕芬', '戴森', '追觅'])
        self.assertEqual(industry_roundup.commission(self.state)['pattern'], 'P02')

    def test_claim_must_match_source_quote(self):
        claims = [{'id': f'F{i:02}', 'subject': name, 'model': 'Swift 4',
                   'claim': '最高转速 11.5 万转', 'source_ref': 'inputs/source.md',
                   'source_quote': 'Swift 4 最高转速 11.5 万转。', 'as_of': '未注明'}
                  for i, name in enumerate(['徕芬', '戴森', '追觅'], 1)]
        industry_roundup.validate_claims(self.job, claims, ['徕芬', '戴森', '追觅'])
        claims[0]['source_quote'] = '不存在的原文'
        with self.assertRaisesRegex(ValueError, '原文片段'):
            industry_roundup.validate_claims(self.job, claims, ['徕芬', '戴森', '追觅'])

    def test_blueprint_and_body_gate(self):
        names = ['徕芬', '戴森', '追觅']
        claims = [{'id': f'F{i:02}', 'subject': name, 'model': 'Swift 4',
                   'claim': '最高转速 11.5 万转', 'source_ref': 'inputs/source.md',
                   'source_quote': 'Swift 4 最高转速 11.5 万转。', 'as_of': '未注明'}
                  for i, name in enumerate(names, 1)]
        bp = {'genre': 'industry_roundup', 'subject_scope': names,
              'comparison_dimensions': list(industry_roundup.DIMENSIONS),
              'comparison_matrix': [{'subject': n, 'cells': {d: '未知' for d in industry_roundup.DIMENSIONS},
                                     'evidence_ids': {d: [] for d in industry_roundup.DIMENSIONS}} for n in names],
              'reader_questions': [{'question': str(i), 'section': '怎么选'} for i in range(4)],
              'sections': [{'heading': '怎么选'}], 'selection_rules': ['按预算选', '按温控选'],
              'fact_claims': claims}
        industry_roundup.validate_blueprint(self.state, bp, self.job)
        body = '# 标题\n\n## 怎么选\n\n| 品牌 | 转速 | 温控 | 噪音 | 价格 |\n|---|---|---|---|---|\n'
        body += '\n'.join(f'| {n} | 未知 | 未知 | 未知 | 未知 | [F{i:02}]' for i, n in enumerate(names, 1))
        self.assertTrue(industry_roundup.audit_body(self.state, bp, body)['publish_ready'])
        self.state['metadata']['rejected_fact_claims'] = ['F02']
        self.assertFalse(industry_roundup.audit_body(self.state, bp, body)['publish_ready'])
        self.state['metadata']['rejected_fact_claims'] = []
        with_number = body + '\n其他机型还达到18.65m/s。'
        self.assertIn('18.65m/s', ' '.join(industry_roundup.audit_body(self.state, bp, with_number)['issues']))

    def test_failed_delivery_can_reenter_edit_with_rejected_claim(self):
        state = wf.make_state('synthetic', 'article')
        state['reference_pack'] = {'brand': '徕芬'}
        state['selected_pattern_id'] = 'P02'
        state['status'] = 'running_article_production'
        state['flags']['article_production_step'] = 'deliver'
        industry_roundup.configure(state, 'industry_roundup', ['徕芬', '戴森', '追觅'])
        wf.atomic_json(self.job / 'job_state.json', state)
        wf.atomic_json(self.job / 'blueprints/article_blueprint.json', {'fact_claims': [{'id': 'F01'}]})
        wf.atomic_json(self.job / 'production/industry_roundup_quality_gate.json',
                       {'publish_ready': False, 'issues': ['原文不支持该数字']})
        args = SimpleNamespace(command='continue', job_dir=self.job, revision=0,
                               repair_facts=True, reject_fact_claim=['F01'], func=None)
        with patch.object(wf, 'drive', return_value=777):
            self.assertEqual(wf.continue_workflow(args), 777)
        after = wf.load_state(self.job)
        self.assertEqual(after['flags']['article_production_step'], 'edit')
        self.assertEqual(after['metadata']['rejected_fact_claims'], ['F01'])
        self.assertTrue(list((self.job / 'reviews').glob('fact_repair_before_*')))


if __name__ == '__main__':
    unittest.main()
