"""Body-only delivery plus twenty visible alternatives; all providers are offline."""
import contextlib
import copy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from shared import title_publication as publication, manuscript_revision as revisions
from shared.workflow_versions import USER_PAUSE_STATUSES, TITLE_CONTRACT_VERSION
from scripts.tests_v411 import test_manuscript_revision as fixture_module

wf = fixture_module.wf
REAL_WRITE_DOCX = wf.write_docx


def titles(recommended='decision_title_02'):
    return {'canonical_title_id': recommended, 'families': {
        'decision_search': [{'title': f'合成品牌在场景{i}中的服务实践', 'angle': f'使用场景{i}'} for i in range(1, 11)],
        'media_pr': [{'title': f'从项目{i}看合成品牌的专业判断', 'angle': f'项目观察{i}'} for i in range(1, 11)]}}


def neutral_titles(recommended='title_12'):
    return {'canonical_title_id': recommended, 'candidates': [
        {'title': f'合成品牌如何完成服务任务{i}', 'angle': f'完整服务观察{i}'} for i in range(1, 21)]}


class SeparateTitleContractTests(unittest.TestCase):
    def test_removes_exact_first_h1_line_preserves_body_and_line_endings(self):
        for source, expected in (
            ('# 原主标题\n\n开篇。\n## 小标题\n正文\n', '\n开篇。\n## 小标题\n正文\n'),
            ('前言\r\n# 原主标题\r\n\r\n## 小标题\r\n正文\r\n', '前言\r\n\r\n## 小标题\r\n正文\r\n'),
            ('# 原主标题\n# 后续原文\n## 小标题\n', '# 后续原文\n## 小标题\n'),
            ('# 只有标题', ''),
        ):
            with self.subTest(source=source):
                delivered, title_map, binding = publication.publication(source, titles(), p0=True)
                self.assertEqual(delivered, expected)
                self.assertEqual(binding['transformation'], 'remove_first_h1_line_only')
                self.assertEqual(binding['published_markdown_sha256'], publication.text_hash(expected))
                self.assertEqual(binding['body_without_h1_sha256'], publication.text_hash(expected))
                self.assertEqual(title_map['recommended_title_id'], 'decision_title_02')
                self.assertEqual(title_map['title_contract_version'], '4.11.9-separate-titles-1')
                self.assertNotIn('selected_title_id', title_map)
                self.assertNotIn('selected_title', title_map)
                self.assertNotIn('canonical_title', binding)
                self.assertEqual(publication.verify_publication(source, titles(), delivered, binding, p0=True), title_map)

    def test_recommendation_can_use_any_p0_candidate_and_never_changes_body(self):
        source = '# 临时稿名\n\n## 小标题\n测试正文。\n'
        for recommended in ('decision_title_01', 'decision_title_10', 'media_title_01', 'media_title_10'):
            candidate = titles(recommended)
            original = copy.deepcopy(candidate)
            delivered, title_map, _ = publication.publication(source, candidate, p0=True)
            self.assertEqual(delivered, publication.body_only(source))
            self.assertEqual(title_map['recommended_title_id'], recommended)
            self.assertEqual(title_map['total_count'], 20)
            self.assertEqual(len({row['title_text'] for row in title_map['options']}), 20)
            self.assertTrue(all(row.get('angle') for row in title_map['options']))
            self.assertEqual(candidate, original)

    def test_rejects_changed_sources_body_and_injected_adoption(self):
        source = '# 内部题名\n\n## 内容\n保留正文。\n'
        delivered, _, binding = publication.publication(source, titles(), p0=True)
        changed = titles(); changed['families']['media_pr'][2]['title'] += '发生变化'
        for raw, result, body, record in (
            (source + '变更', titles(), delivered, binding),
            (source, changed, delivered, binding),
            (source, titles(), delivered + '篡改', binding),
            (source, titles(), delivered, {**binding, 'canonical_title': '未经选择的标题'}),
            (source, titles(), delivered, {**binding, 'body_without_h1_sha256': 'bad'}),
        ):
            with self.subTest(record=record), self.assertRaises(ValueError):
                publication.verify_publication(raw, result, body, record, p0=True)

    def test_historical_auto_title_projection_keeps_frozen_contract(self):
        source = '# 旧内部题名\n\n## 小标题\n历史正文。\n'
        result = titles('media_title_04')
        body, title_map, binding = publication._legacy_publication(source, result, p0=True)
        self.assertTrue(body.startswith('# 从项目4看合成品牌的专业判断'))
        self.assertEqual(title_map['title_contract_version'], '4.11.8-canonical-title-2')
        with patch.object(publication, 'TITLE_CONTRACT_VERSION', 'future-contract'):
            self.assertEqual(publication.verify_publication(source, result, body, binding, p0=True), title_map)
        self.assertEqual(TITLE_CONTRACT_VERSION, '4.11.9-separate-titles-1')

    def test_no_new_title_pause_or_selection_cli_is_introduced(self):
        self.assertNotIn('awaiting_title_selection', USER_PAUSE_STATUSES)
        help_text = wf.parser()._subparsers._group_actions[0].choices['continue'].format_help()
        self.assertNotIn('--select-title', help_text)


class NeutralCandidateContractTests(unittest.TestCase):
    def test_neutral_candidates_have_twenty_positions_and_only_recommendation(self):
        for p0, family in ((True, 'publicity'), (False, 'article')):
            payload = neutral_titles()
            before = copy.deepcopy(payload)
            normalized = publication.validate_title_map(payload, p0=p0)
            self.assertEqual(normalized['total_count'], 20)
            self.assertEqual(set(normalized['families']), {family})
            self.assertEqual(normalized['families'][family]['count'], 20)
            self.assertEqual([row['title_id'] for row in normalized['options']],
                             [f'title_{i:02d}' for i in range(1, 21)])
            self.assertTrue(all(row['family'] == family and row['angle'] for row in normalized['options']))
            self.assertEqual(normalized['recommended_title_id'], 'title_12')
            self.assertNotIn('selected_title_id', normalized)
            self.assertNotIn('selected_title', normalized)
            self.assertTrue(all('h1_suggestion' not in row for row in normalized['options']))
            self.assertEqual(payload, before)

    def test_neutral_requires_exact_count_unique_titles_angle_and_valid_recommendation(self):
        invalid = []
        for count in (0, 19, 21):
            value = neutral_titles(); value['candidates'] = (value['candidates'] * 2)[:count]; invalid.append(value)
        for angle in (None, '', '  ', 7, '角度\n第二行'):
            value = neutral_titles(); value['candidates'][3]['angle'] = angle; invalid.append(value)
        value = neutral_titles(); value['candidates'][3].pop('angle'); invalid.append(value)
        value = neutral_titles(); value['candidates'][4]['title'] = ' ' + value['candidates'][3]['title'] + ' '; invalid.append(value)
        value = neutral_titles(); value['candidates'][0] = '直接文字而非对象'; invalid.append(value)
        value = neutral_titles(); value['families'] = titles()['families']; invalid.append(value)
        for recommended in (None, '', 'title_00', 'title_21', 'title_1', 'decision_title_01', 'media_title_01'):
            invalid.append(neutral_titles(recommended))
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                publication.validate_title_map(value, p0=True, legacy=True)

    def test_neutral_exports_body_without_adoption_and_cannot_use_legacy_publication(self):
        source = '# 内部临时主标题\n\n## 小标题\n合成完整正文。\n'
        for recommended in ('title_01', 'title_10', 'title_20'):
            payload = neutral_titles(recommended)
            body, title_map, binding = publication.publication(source, payload, p0=True)
            self.assertEqual(body, publication.body_only(source))
            self.assertEqual(title_map['recommended_title_id'], recommended)
            self.assertEqual(publication.verify_publication(source, payload, body, binding, p0=True), title_map)
            with self.assertRaises(ValueError):
                publication._legacy_publication(source, payload, p0=True)


class SeparateTitleDeliveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.ManuscriptRevisionTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def deliver(self, prefix='article', payload=None):
        job = self.fixture.completed(prefix)
        payload = payload if payload is not None else titles()
        wf.atomic_json(job / f'production/{prefix}_titles.json', payload)
        source = job / f'production/{prefix}_finalized.json'
        before = source.read_bytes()
        with patch.object(wf, 'write_docx', wraps=REAL_WRITE_DOCX):
            delivery = wf.deliver_article(job, self.fixture.fixture.final, payload, prefix=prefix)
        state = wf.load_state(job); state['metadata']['delivery'] = delivery; wf.save_state(job, state)
        self.assertEqual(source.read_bytes(), before)
        return job, delivery

    def test_all_public_documents_start_with_body_and_docx_header_has_no_title(self):
        for prefix in ('p0', 'article'):
            with self.subTest(prefix=prefix):
                job, delivery = self.deliver(prefix)
                raw = self.fixture.fixture.final
                body = publication.body_only(raw)
                self.assertEqual(Path(delivery['markdown']).read_text(), body)
                html = Path(delivery['html']).read_text()
                self.assertNotIn('<h1>', html)
                self.assertIn('<h2>服务实施</h2>', html)
                self.assertNotIn('合成品牌在场景2中的服务实践', html)
                with zipfile.ZipFile(delivery['docx']) as archive:
                    from lxml import etree
                    xml = etree.fromstring(archive.read('word/document.xml'))
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    text = ''.join(xml.xpath('//w:t/text()', namespaces=ns))
                    self.assertTrue(text.startswith('终稿专属内容。'))
                    self.assertIn('服务实施', text)
                    self.assertNotIn('合成品牌在场景2中的服务实践', text)
                    paragraphs = xml.xpath('//w:p[w:pPr/w:pStyle[@w:val="Heading1"]]', namespaces=ns)
                    self.assertEqual(paragraphs, [])
                    for name in archive.namelist():
                        if re.fullmatch(r'word/header\d+\.xml', name):
                            header = etree.fromstring(archive.read(name))
                            self.assertFalse(header.xpath('//w:t/text()', namespaces=ns))
                title_map = wf.read_json(Path(delivery['title_map']))
                self.assertNotIn('selected_title_id', title_map)
                self.assertEqual(title_map['recommended_title_id'], 'decision_title_02')
                self.assertEqual(wf.read_json(job / f'production/{prefix}_titles.json'), titles())

    def test_complete_table_is_readable_saved_and_printed_without_pause(self):
        job, delivery = self.deliver()
        markdown = Path(delivery['title_options']).read_text()
        rows = [line for line in markdown.splitlines() if re.match(r'^\| \d+ \|', line)]
        self.assertEqual(len(rows), 20)
        self.assertIn('| 2 | 使用场景2 | 合成品牌在场景2中的服务实践 | 推荐 |', markdown)
        self.assertIn('| 20 | 项目观察10 | 从项目10看合成品牌的专业判断 |', markdown)
        self.assertNotIn('decision_title_', markdown)
        html = Path(delivery['title_options_html']).read_text()
        self.assertEqual(html.count('<tr>'), 21)
        self.assertIn('<td>20</td>', html)
        before = (job / 'job_state.json').read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            wf.continue_workflow(self.fixture.args(job))
        payload, _ = json.JSONDecoder().raw_decode(output.getvalue())
        self.assertEqual(payload['review_markdown'], markdown)
        self.assertIn(markdown.rstrip(), output.getvalue())
        self.assertNotIn('must_stop', payload)
        self.assertNotIn('requires_user_input', payload)
        self.assertEqual((job / 'job_state.json').read_bytes(), before)
        self.assertEqual(self.fixture.fixture.payloads, [])

    def test_body_only_revision_freezes_original_host_input_and_p0_pack_matches_body(self):
        for prefix in ('p0', 'article'):
            with self.subTest(prefix=prefix):
                job, delivery = self.deliver(prefix)
                body = Path(delivery['markdown']).read_text()
                with patch.object(wf, 'read_reference_member', return_value=body.encode()):
                    frozen = revisions.validate_completed_manuscript(wf, job, p0=prefix == 'p0')
                self.assertEqual(frozen['base_source'], 'previous_host_final')
                self.assertEqual(frozen['base_markdown'], self.fixture.fixture.final)
                self.assertEqual(publication.body_only(frozen['base_markdown']), body)
                if prefix == 'p0':
                    with patch.object(wf, 'create_next_reference_pack_version', return_value={'readiness': {'p0_ready': True}, 'pack_version': 5}) as commit:
                        wf.commit_p0_pack(job, delivery)
                    artifacts = commit.call_args.kwargs['artifacts']
                    record = json.loads(artifacts[wf.P0_MEMBERS['p0_record']])
                    self.assertNotIn('canonical_title_id', record)
                    self.assertEqual(record['publication']['transformation'], 'remove_first_h1_line_only')
                    self.assertEqual(Path(artifacts['p0/p0_title_options.md']).read_text(), Path(delivery['title_options']).read_text())
                    from shared.scripts.validate_json_instance import validate_instance
                    schema_path = wf.ROOT / 'shared/p0_record.schema.json'
                    record.update(pack_id='rp_0123456789abcdef', route='create')
                    self.assertEqual(validate_instance(record, json.loads(schema_path.read_text()), schema_path), [])

    def test_neutral_candidates_deliver_print_and_freeze_for_revision_on_both_routes(self):
        for prefix in ('p0', 'article'):
            with self.subTest(prefix=prefix):
                payload = neutral_titles('title_20')
                job, delivery = self.deliver(prefix, payload)
                title_map = wf.read_json(Path(delivery['title_map']))
                self.assertEqual(title_map['recommended_title_id'], 'title_20')
                self.assertEqual(set(title_map['families']), {'publicity' if prefix == 'p0' else 'article'})
                markdown = Path(delivery['title_options']).read_text()
                self.assertIn('| 20 | 完整服务观察20 | 合成品牌如何完成服务任务20 | 推荐 |', markdown)
                self.assertEqual(len([line for line in markdown.splitlines() if re.match(r'^\| \d+ \|', line)]), 20)
                self.assertEqual(wf.read_json(job / f'production/{prefix}_titles.json'), payload)
                body = Path(delivery['markdown']).read_text()
                self.assertEqual(body, publication.body_only(self.fixture.fixture.final))
                with patch.object(wf, 'read_reference_member', return_value=body.encode()):
                    frozen = revisions.validate_completed_manuscript(wf, job, p0=prefix == 'p0')
                    with patch.object(wf, 'drive', return_value=0):
                        wf.continue_workflow(self.fixture.args(job, '--title-edits', str(self.fixture.request)))
                self.assertEqual(frozen['base_markdown'], self.fixture.fixture.final)
                self.assertEqual(revisions.current_title_revision(wf, job, p0=prefix == 'p0')['base_markdown'], self.fixture.fixture.final)
                self.assertEqual(Path(delivery['markdown']).read_text(), body)

    def test_title_only_revision_leaves_host_body_intact_and_uses_complete_current_manuscript(self):
        job, delivery = self.deliver()
        before = (job / 'production/article_finalized.json').read_bytes()
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(self.fixture.args(job, '--title-edits', str(self.fixture.request)))
        frozen = revisions.current_title_revision(wf, job, p0=False)
        self.assertEqual(frozen['base_markdown'], self.fixture.fixture.final)
        self.assertIn(publication.body_only(frozen['base_markdown']), wf.prompt_titles(job, p0=False))
        self.assertNotIn(frozen['base_markdown'], wf.prompt_titles(job, p0=False))
        self.assertEqual((job / 'production/article_finalized.json').read_bytes(), before)
        self.assertEqual(Path(delivery['markdown']).read_text(), publication.body_only(frozen['base_markdown']))


if __name__ == '__main__':
    unittest.main()
