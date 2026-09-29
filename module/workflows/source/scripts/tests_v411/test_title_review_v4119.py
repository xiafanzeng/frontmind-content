"""One independent title editor; synthetic behavior checks, never live calls."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from shared import title_publication as publication, manuscript_revision as revisions
from scripts.tests_v411 import test_manuscript_revision as fixtures

wf = fixtures.wf


def original_titles():
    return {'candidates': [{'title': f'合成企业的服务实践{i}', 'angle': f'业务观察{i}'} for i in range(1, 21)],
            'canonical_title_id': 'title_01'}


def reviewed_titles(raw=None, *, change=True):
    raw = copy.deepcopy(raw or original_titles())
    value = {'outcome': 'revised' if change else 'accepted', **raw,
             'title_notes': ['删除结果保证，改为全文支持的服务实践。'] if change else [], 'reason': ''}
    if change:
        value['candidates'][0]['title'] = '从测试依据到结果复核：合成企业的服务实践'
    return value


class TitleReviewContractTests(unittest.TestCase):
    def test_accepted_and_revised_have_real_corresponding_candidates(self):
        raw = original_titles()
        for change in (True, False):
            value = reviewed_titles(raw, change=change)
            self.assertEqual(publication.validate_title_review_result(value, raw, p0=True), value)
        for value in (
            {**reviewed_titles(raw, change=False), 'title_notes': ['已修改']},
            {**reviewed_titles(raw), 'outcome': 'accepted', 'title_notes': []},
            {**reviewed_titles(raw, change=False), 'outcome': 'revised', 'title_notes': ['声称修改']},
            {**reviewed_titles(raw), 'title_notes': []},
            {**reviewed_titles(raw), 'article_markdown': '# 偷改正文'},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                publication.validate_title_review_result(value, raw, p0=True)
        value = reviewed_titles(raw, change=False)
        value.update(outcome='revised', title_notes=['只加空格'])
        value['candidates'][0]['title'] += ' '
        with self.assertRaises(ValueError):
            publication.validate_title_review_result(value, raw, p0=True)

    def test_incomplete_cannot_publish_and_only_uses_empty_recommendation(self):
        raw = original_titles()
        incomplete = {'outcome': 'incomplete', 'candidates': [], 'canonical_title_id': '',
                      'title_notes': [], 'reason': '未能完成全文编辑。'}
        self.assertEqual(publication.validate_title_review_result(incomplete, raw, p0=True), incomplete)
        with self.assertRaises(ValueError):
            publication.validate_title_review_result({**incomplete, 'canonical_title_id': None}, raw, p0=True)
        with self.assertRaises(ValueError):
            publication.publication('# 内部标题\n\n## 内容\n正文\n', raw, p0=True, title_review=incomplete)

    def test_reviewed_candidates_bind_both_model_results_without_changing_body(self):
        source = '# 内部主标题\r\n\r\n## 小标题\r\n原正文。\r\n'
        raw = original_titles(); before = copy.deepcopy(raw); review = reviewed_titles(raw)
        body, title_map, binding = publication.publication(source, raw, p0=True, title_review=review)
        self.assertEqual(body, publication.body_only(source))
        self.assertEqual(raw, before)
        self.assertEqual(title_map['options'][0]['title_text'], review['candidates'][0]['title'])
        self.assertEqual(binding['title_result_sha256'], publication.payload_hash(raw))
        self.assertEqual(binding['title_review_result_sha256'], publication.payload_hash(review))
        self.assertNotIn('canonical_title', binding)
        self.assertEqual(publication.verify_publication(source, raw, body, binding, p0=True, title_review=review), title_map)
        changed_raw = original_titles(); changed_raw['candidates'][3]['title'] += '被篡改'
        changed_review = copy.deepcopy(review); changed_review['candidates'][2]['title'] += '被篡改'
        for original, edited in ((raw, None), (changed_raw, review), (raw, changed_review)):
            with self.subTest(edited=edited), self.assertRaises(ValueError):
                publication.verify_publication(source, original, body, binding, p0=True, title_review=edited)
        old_body, old_map, old_binding = publication.publication(source, raw, p0=True)
        self.assertEqual(publication.verify_publication(source, raw, old_body, old_binding, p0=True), old_map)


class TitleReviewControllerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ManuscriptRevisionTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def start(self, prefix='article'):
        job = self.fixture.completed(prefix)
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(self.fixture.args(job, '--title-edits', str(self.fixture.request)))
        return job

    def actions(self, raw, review):
        calls = []
        real = wf.ensure_action
        def ensure(job, action, prompt, **kwargs):
            calls.append(action)
            if action.endswith('_titles'):
                return copy.deepcopy(raw)
            if action.endswith('_title_review'):
                return copy.deepcopy(review)
            return real(job, action, prompt, **kwargs)
        return calls, ensure

    def test_title_only_run_calls_one_editor_persists_both_results_and_freezes_reviewed_delivery(self):
        job = self.start(); raw = original_titles(); review = reviewed_titles(raw)
        source = job / 'production/article_finalized.json'; before = source.read_bytes()
        calls, ensure = self.actions(raw, review)
        with patch.object(wf, 'ensure_action', side_effect=ensure), contextlib.redirect_stdout(io.StringIO()) as output:
            wf.drive(job)
        self.assertEqual(calls, ['article_titles', 'article_title_review'])
        self.assertEqual(wf.load_state(job)['status'], 'completed')
        self.assertEqual(wf.read_json(job / 'production/article_titles.json'), raw)
        self.assertEqual(wf.read_json(job / 'production/article_title_review.json'), review)
        self.assertEqual(source.read_bytes(), before)
        delivery = wf.load_state(job)['metadata']['delivery']
        self.assertIn(review['candidates'][0]['title'], Path(delivery['title_options']).read_text())
        self.assertIn(review['candidates'][0]['title'], output.getvalue())
        self.assertEqual(Path(delivery['markdown']).read_text(), publication.body_only(self.fixture.fixture.final))
        binding = wf.read_json(Path(delivery['publication']))
        self.assertEqual(binding['title_review_result_file_sha256'], wf.sha256_file(job / 'production/article_title_review.json'))
        frozen = revisions.validate_completed_manuscript(wf, job, p0=False)
        self.assertEqual(frozen['source']['actions'][-1]['action'], 'article_title_review')
        self.assertEqual(frozen['base_markdown'], self.fixture.fixture.final)
        with patch.object(wf, 'ensure_action', side_effect=AssertionError('finished task must not call a model')), contextlib.redirect_stdout(io.StringIO()):
            wf.continue_workflow(self.fixture.args(job))

    def test_incomplete_editor_does_not_deliver_original_candidates_or_retry_automatically(self):
        job = self.start(); raw = original_titles()
        review = {'outcome': 'incomplete', 'candidates': [], 'canonical_title_id': '', 'title_notes': [], 'reason': '无法完成。'}
        before = copy.deepcopy(wf.load_state(job)['metadata']['delivery'])
        calls, ensure = self.actions(raw, review)
        with patch.object(wf, 'ensure_action', side_effect=ensure), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(wf.WorkflowError, '标题编辑未完成'):
                wf.drive(job)
        state = wf.load_state(job)
        self.assertEqual(calls, ['article_titles', 'article_title_review'])
        self.assertEqual(state['flags']['article_production_step'], 'title_review')
        self.assertEqual(state['pending_action']['error']['code'], 'title_review_incomplete')
        self.assertEqual(state['metadata']['delivery'], before)
        self.assertFalse(wf.writing_delivery_root(job).exists())

    def test_p0_pack_binds_reviewed_titles_and_raw_result_separately(self):
        job = self.fixture.completed('p0'); raw = original_titles(); review = reviewed_titles(raw)
        wf.atomic_json(job / 'production/p0_titles.json', raw)
        wf.atomic_json(job / 'production/p0_title_review.json', review)
        delivery = wf.deliver_article(job, self.fixture.fixture.final, raw, prefix='p0', title_review=review)
        with patch.object(wf, 'create_next_reference_pack_version', return_value={'readiness': {'p0_ready': True}, 'pack_version': 5}) as commit:
            wf.commit_p0_pack(job, delivery)
        artifacts = commit.call_args.kwargs['artifacts']
        record = json.loads(artifacts[wf.P0_MEMBERS['p0_record']])
        self.assertEqual(record['publication']['title_result_sha256'], publication.payload_hash(raw))
        self.assertEqual(record['publication']['title_review_result_sha256'], publication.payload_hash(review))
        self.assertEqual(wf.read_json(Path(artifacts[wf.P0_MEMBERS['p0_title_map']]))['options'][0]['title_text'], review['candidates'][0]['title'])
        from shared.scripts.validate_json_instance import validate_instance
        schema_path = wf.ROOT / 'shared/p0_record.schema.json'; schema = json.loads(schema_path.read_text())
        record.update(pack_id='rp_0123456789abcdef', route='create')
        self.assertEqual(validate_instance(record, schema, schema_path), [])
        broken = copy.deepcopy(record); broken['publication'].pop('title_review_result_file_sha256')
        self.assertTrue(validate_instance(broken, schema, schema_path))
        wf.atomic_json(job / 'production/p0_title_review.json', reviewed_titles(raw, change=False))
        with self.assertRaises(ValueError):
            wf.commit_p0_pack(job, delivery)


if __name__ == '__main__':
    unittest.main()
