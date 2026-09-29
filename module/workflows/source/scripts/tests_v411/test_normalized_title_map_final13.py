"""A title-only model response can reuse the public normalized title artifact."""
import copy
import unittest

from shared import title_publication as titles


def candidates():
    return {'candidates': [{'title': f'合成品牌的完整服务实践{i}', 'angle': f'服务细节{i}'} for i in range(1, 21)],
            'canonical_title_id': 'title_17'}


class NormalizedTitleMapTests(unittest.TestCase):
    def test_article_and_publicity_normalization_are_idempotent_without_mutation(self):
        for p0 in (False, True):
            with self.subTest(p0=p0):
                value = titles.validate_title_map(candidates(), p0=p0)
                value['publication'] = {'contract': titles.PUBLICATION_CONTRACT, 'source': 'previous_delivery'}
                before = copy.deepcopy(value)
                result = titles.validate_title_map(value, p0=p0)
                self.assertEqual(result, value)
                self.assertEqual(titles.validate_title_map(result, p0=p0), value)
                result['options'][0]['title_text'] = '独立副本'
                result['publication']['source'] = '修改副本'
                self.assertEqual(value, before)

    def test_normalized_response_passes_real_title_review_and_body_only_publication(self):
        for p0 in (False, True):
            raw = candidates()
            value = titles.validate_title_map(raw, p0=p0)
            neutral = titles.title_review_input(value, p0=p0)
            self.assertEqual(neutral, raw)
            review = {'outcome': 'accepted', **neutral, 'title_notes': [], 'reason': ''}
            self.assertEqual(titles.validate_title_review_result(review, value, p0=p0), review)
            body = '# 内部标题\n\n正文与**粗体主体**。\n'
            delivered, result, binding = titles.publication(body, value, p0=p0, title_review=review)
            self.assertEqual(delivered, '\n正文与**粗体主体**。\n')
            self.assertEqual(titles.verify_publication(body, value, delivered, binding, p0=p0, title_review=review), result)
            with self.assertRaises(ValueError):
                titles._legacy_publication(body, value, p0=p0)

    def test_inconsistent_order_family_copies_counts_and_recommendations_are_rejected(self):
        def bad(change):
            value = titles.validate_title_map(candidates())
            value['families']['article']['options'] = copy.deepcopy(value['options'])
            change(value)
            return value
        invalid = [
            bad(lambda v: v['options'].reverse()),
            bad(lambda v: v['options'][0].update(title_id='title_02')),
            bad(lambda v: v['options'][0].update(family='publicity')),
            bad(lambda v: v['families']['article']['options'][4].update(title_text='不一致的标题')),
            bad(lambda v: v['families']['article'].update(count=19)),
            bad(lambda v: v.update(total_count=19)),
            bad(lambda v: v.update(requested_count='20')),
            bad(lambda v: v.update(canonical_title_id='title_21')),
            bad(lambda v: v.update(recommended_title_id='title_01')),
            bad(lambda v: v.update(recommended_title='推荐文字与候选不符')),
            bad(lambda v: v['options'][0].update(angle='')),
            bad(lambda v: v['options'][1].update(title_text=v['options'][0]['title_text'])),
            bad(lambda v: v.update(title_adoption_mode='model_selected_canonical_h1')),
            bad(lambda v: v['families'].update(decision_search=[])),
            bad(lambda v: v.update(candidates=candidates()['candidates'])),
            bad(lambda v: v.update(publication='不是对象')),
        ]
        for index, value in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(ValueError):
                titles.validate_title_map(value)
        with self.assertRaises(ValueError):
            titles.validate_title_map(titles.validate_title_map(candidates(), p0=True), p0=False)

    def test_legacy_ten_plus_ten_contract_and_legacy_default_remain_unchanged(self):
        value = {'families': {
            'decision_search': [f'历史决策标题{i}' for i in range(1, 11)],
            'media_pr': [f'历史媒体标题{i}' for i in range(1, 11)]},
            'canonical_title_id': 'media_title_07'}
        result = titles.validate_title_map(value, p0=True)
        self.assertEqual(result['selected_title_id'], 'media_title_07')
        self.assertEqual([x['title_id'] for x in result['options'][:2]], ['decision_title_01', 'decision_title_02'])
        value.pop('canonical_title_id')
        self.assertEqual(titles.validate_title_map(value, legacy=True)['selected_title_id'], 'decision_title_01')
        with self.assertRaises(ValueError):
            titles.validate_title_map(value)


if __name__ == '__main__':
    unittest.main()
