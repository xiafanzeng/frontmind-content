"""新写作边界与型号一致性的离线回归；不调用模型。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import article_focus, fdnv2_guidance, industry_roundup, writing_context_v16


class Fdnv2FocusRoundupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        (self.job / 'inputs').mkdir()
        (self.job / 'inputs/models.md').write_text(
            '美的 FG207 转速 11.5 万转。\n美的 FZ105 噪音 58 分贝。\n'
            '飞科 FH6371 转速 10 万转。\n飞科 FH6371 噪音 62 分贝。\n'
            '徕芬 Swift 4 转速 11.5 万转。\n徕芬 Swift 4 噪音 59 分贝。\n', encoding='utf-8')
        self.state = {'selected_pattern_id': 'P02', 'reference_pack': {'brand': '徕芬'}, 'metadata': {}}
        article_focus.configure(self.state, focus='高速吹风机的转速与噪音',
                                reader_questions=['三款机型噪音怎样比较？'],
                                excluded_topics=['电动牙刷'])
        industry_roundup.configure(self.state, 'industry_roundup', ['徕芬', '美的', '飞科'],
                                   dimensions=['转速', '噪音'])

    def claim(self, ident, subject, model, quote):
        return {'id': ident, 'subject': subject, 'model': model, 'claim': quote,
                'source_ref': 'inputs/models.md', 'source_quote': quote, 'as_of': '未注明'}

    def blueprint(self):
        names = ['徕芬', '美的', '飞科']
        models = ['Swift 4', 'FG207', 'FH6371']
        claims = [self.claim('F01', '徕芬', 'Swift 4', '徕芬 Swift 4 转速 11.5 万转。'),
                  self.claim('F02', '美的', 'FG207', '美的 FG207 转速 11.5 万转。'),
                  self.claim('F03', '飞科', 'FH6371', '飞科 FH6371 转速 10 万转。')]
        rows = [{'subject': name, 'model': model,
                 'cells': {'转速': claim['claim'], '噪音': '未知'},
                 'evidence_ids': {'转速': [claim['id']], '噪音': []}}
                for name, model, claim in zip(names, models, claims)]
        return {'genre': 'industry_roundup', 'subject_scope': names,
                'comparison_dimensions': ['转速', '噪音'], 'comparison_matrix': rows,
                'fact_claims': claims, 'sections': [{'heading': '横向比较'}],
                'reader_questions': [{'question': '三款机型噪音怎样比较？', 'section': '横向比较'}],
                'selection_rules': ['重视噪音时先看同条件实测，缺失则不下结论']}

    def test_frozen_focus_and_dynamic_dimensions(self):
        self.assertEqual(industry_roundup.dimensions(self.state), ('转速', '噪音'))
        self.assertIn('电动牙刷', article_focus.context(self.state))
        self.assertTrue(fdnv2_guidance.matches(writing_context_v16.MARKER + '\n' + article_focus.MARKER))
        industry_roundup.validate_blueprint(self.state, self.blueprint(), self.job)
        old = {'metadata': {}, 'selected_pattern_id': 'P02'}
        self.assertFalse(article_focus.enabled(old))

    def test_mixed_model_in_one_row_is_rejected(self):
        bp = self.blueprint()
        bp['fact_claims'].append(self.claim('F04', '美的', 'FZ105', '美的 FZ105 噪音 58 分贝。'))
        bp['comparison_matrix'][1]['cells']['噪音'] = '58 分贝'
        bp['comparison_matrix'][1]['evidence_ids']['噪音'] = ['F04']
        with self.assertRaisesRegex(ValueError, '混用了不同型号'):
            industry_roundup.validate_blueprint(self.state, bp, self.job)

    def test_ambiguous_model_quote_is_rejected(self):
        (self.job / 'inputs/models.md').write_text('美的高速款噪音 58 分贝。', encoding='utf-8')
        claims = [self.claim('F01', '美的', 'FG207', '美的高速款噪音 58 分贝。')]
        with self.assertRaisesRegex(ValueError, '型号标识'):
            industry_roundup.validate_claims(self.job, claims, ['美的'], strict_model=True)

    def test_new_blueprint_and_draft_prompts_keep_old_jobs_frozen(self):
        class Workflow:
            def __init__(self, state):
                self.state = state

            def load_state(self, _job):
                return self.state

        workflow = Workflow(self.state)
        bp = {'comparison_dimensions': ['转速', '噪音'], 'comparison_matrix': [],
              'reader_questions': [], 'selection_rules': [], 'fact_claims': [{'id': 'F77'}]}
        prepared = {'writing_material_markdown': '相关事实材料', 'blueprint_suggestions': '按问题比较',
                    'fact_claims': []}
        with (patch.object(writing_context_v16, 'commission', return_value='COMMISSION'),
              patch.object(writing_context_v16, 'references', return_value='REFERENCE F77'),
              patch.object(writing_context_v16, '_blueprint', return_value=bp),
              patch.object(writing_context_v16, 'preparation', return_value=prepared),
              patch('shared.writing_context_v14.examples', return_value='STYLE')):
            blueprint = writing_context_v16.prompt_blueprint(workflow, self.job)
            draft = writing_context_v16.prompt_article(workflow, self.job)
            self.assertIn('技术路线／方案类别', blueprint)
            self.assertIn('主品牌与竞品用相同维度', blueprint)
            self.assertIn('不能把不同测试条件的数值写成直接排名', draft)
            self.assertEqual(draft.count('F77'), 1)
            self.assertIn(article_focus.DRAFT_MARKER, draft)
            self.assertIn('先解释路线及适用边界', writing_context_v16.system('article_draft', draft))
            self.state['metadata']['prompt_revision'] = article_focus.PREVIOUS_PROMPT_REVISION
            previous = writing_context_v16.prompt_article(workflow, self.job)
            self.assertNotIn(article_focus.DRAFT_MARKER, previous)
            self.assertEqual(previous.count('F77'), 2)
            self.state['metadata']['prompt_revision'] = article_focus.PROMPT_REVISION
            self.state['metadata'].pop('article_spec')
            self.state['selected_pattern_id'] = 'P01'
            single = writing_context_v16.prompt_article(workflow, self.job)
            self.assertIn('只选与本篇主题和读者问题相关的事实', single)
            self.assertNotIn('行业盘点成文要求', single)


if __name__ == '__main__':
    unittest.main()
