"""Offline intake/selection integration. No network or model quality claims."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from openpyxl import Workbook
from scripts import frontmind_workflow as wf
from shared import article_pool as pool, example_acquisition as acquisition, question_bank_import as bank
from shared.example_acquisition import ExampleStore, AcquisitionError
from Reference_Pack_Workflow.shared import reference_pack_builder as builder


class ArticlePoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.job = self.root / 'job'; self.job.mkdir()
        business = self.root / 'business.md'; business.write_text('合成品牌的业务资料，仅用于软件测试。')
        builder.create_reference_pack(brand_name='合成品牌', knowledge_base=[business], output=self.root/'pack')
        self.answers = self.root / 'answers.json'
        self.answers.write_text(json.dumps([
            {'监控问题': '服务机构推荐', 'AI大模型': platform, '回答内容': '完整回答。\n\n保留原始段落。', '监控日期': '2026-10-01'}
            for platform in ['平台甲', '平台乙']], ensure_ascii=False))
        bank.import_into_pack(pack=self.root/'pack', monitoring_answers=self.answers, output=self.root/'with_answers')
        state = wf.make_state('pool-test', 'article')
        state['metadata'].update(question_selector='服务机构推荐', question_text='服务机构推荐')
        wf.atomic_json(self.job/'job_state.json', state)
        wf.bind_reference_pack(self.job, self.root/'with_answers')

    def rows(self, n=25):
        rows = [{'问题': '服务机构推荐', '日期': '2026-10-01', '文章链接': f'https://example.com/article/{i}',
                 '标题': f'完整案例第{i}篇', '媒体': '合成媒体'} for i in range(1, n+1)]
        return [*rows, *([dict(rows[0])] * 2)]

    def upload(self, rows=None, *, suffix='.json', period=None):
        path = self.root / ('sources' + suffix)
        rows = self.rows() if rows is None else rows
        if suffix == '.xlsx':
            wb = Workbook(); ws = wb.active; ws.title = '明细'
            ws.append(list(rows[0])); [ws.append([x.get(k) for k in rows[0]]) for x in rows]
            wb.save(path)
        else:
            path.write_text(json.dumps(rows, ensure_ascii=False))
        pool.stage_source(wf, self.job, path, period)
        return path

    def prepared(self, **kwargs):
        self.upload(**kwargs)
        return wf.prepare_question(self.job)

    def state(self, **values):
        state = wf.load_state(self.job); state.update(values); wf.save_state(self.job, state); return state

    def selected_body(self, n=1):
        file = self.root / f'full{n}.md'
        file.write_text('# 实际上传的完整合成例文\n\n' + '先介绍机构的业务，再展开不同服务特点，按内容安排详略。\n\n' * 30)
        return file

    def test_new_article_policy_p0_and_unmarked_legacy_preserved(self):
        self.assertTrue(pool.enabled(wf.make_state('a', 'article')))
        self.assertFalse(pool.enabled(wf.make_state('p', 'p0')))
        state = wf.load_state(self.job); state['metadata'].pop('article_pool_policy'); wf.save_state(self.job, state)
        q = wf.prepare_question(self.job)
        self.assertEqual(2, len(q['answers']))
        self.assertFalse((self.job/pool.PATH).exists())

    def test_missing_sources_is_mandatory_user_pause_no_model(self):
        state = wf.load_state(self.job); state['reference_pack']['readiness']['p0_ready'] = True; wf.save_state(self.job, state)
        with patch.object(wf, 'run_action', side_effect=AssertionError('model must not run')), contextlib.redirect_stdout(io.StringIO()):
            wf.enter_response_brief(self.job)
        state = wf.load_state(self.job)
        self.assertEqual('awaiting_question_research_inputs', state['status'])
        self.assertTrue(state['current_pause']['must_stop'])
        self.assertIn('信源', Path(state['current_pause']['review_markdown_path']).read_text())

    def test_source_upload_preserves_answers_and_previous_pack(self):
        original = wf.load_state(self.job)['reference_pack']['path']
        q = self.prepared()
        self.assertEqual(2, len(q['answers']))
        state = wf.load_state(self.job)
        self.assertNotEqual(original, state['reference_pack']['path'])
        self.assertTrue(Path(original).is_dir())
        self.assertEqual('pass', wf.validate_reference_pack(Path(state['reference_pack']['path']))['status'])
        self.assertIn('question_source_delivery', state['metadata'])
        self.assertNotIn('pending_citation_input', state['metadata'])

    def test_missing_answers_cannot_be_replaced_with_sources(self):
        wf.bind_reference_pack(self.job, self.root/'pack')
        self.upload()
        with self.assertRaisesRegex(wf.WorkflowError, '两个不同'):
            wf.prepare_question(self.job)
        self.assertFalse((self.job/pool.PATH).exists())

    def test_rank_top20_and_full_pool_no_two_candidate_limit(self):
        self.prepared(); value = pool.load(wf, self.job)
        self.assertEqual(25, len(value['articles']))
        self.assertEqual(3, value['articles'][0]['citation_count'])
        top = (self.job/'research/article_pool/top20.md').read_text()
        all_text = (self.job/'research/article_pool/all_articles.md').read_text()
        self.assertIn('完整案例第20篇', top); self.assertNotIn('完整案例第21篇', top)
        self.assertIn('完整案例第25篇', all_text)

    def test_public_titles_and_urls_do_not_trigger_internal_jargon_guard(self):
        self.prepared(rows=[dict(x, 标题='Scorecard coverage 企业案例', 文章链接='https://example.com/scores') for x in self.rows(1)])
        page = pool.display(wf, self.job)
        wf.assert_public_review(page)
        import html
        self.assertIn('Scorecard coverage 企业案例', html.unescape(page))

    def test_fewer_than20_is_honest_not_filled(self):
        self.prepared(rows=self.rows(3)); page = pool.display(wf, self.job)
        self.assertIn('共 3 篇', page); self.assertIn('前 3 篇', page)

    def test_other_question_and_other_period_not_mixed(self):
        rows = self.rows(2) + [{'问题': '另一问题', '日期': '2026-10-01', '文章链接': 'https://wrong.test/x'},
            {'问题': '服务机构推荐', '日期': '2026-09-01', '文章链接': 'https://wrong.test/y'}]
        self.prepared(rows=rows)
        self.assertEqual(2, len(pool.load(wf, self.job)['articles']))

    def test_wrong_question_upload_rejected(self):
        self.upload([dict(x, 问题='另一问题') for x in self.rows(2)])
        with self.assertRaisesRegex(wf.WorkflowError, '没有当前正式问题'):
            wf.prepare_question(self.job)

    def test_wrong_period_upload_rejected(self):
        self.upload([dict(x, 日期='2026-09-01') for x in self.rows(2)])
        with self.assertRaisesRegex(wf.WorkflowError, '其他期次'):
            wf.prepare_question(self.job)

    def test_unknown_date_requires_explicit_period_not_guessing(self):
        rows = [dict(x, 日期='') for x in self.rows(2)]
        self.upload(rows)
        with self.assertRaisesRegex(wf.WorkflowError, 'source-period'):
            wf.prepare_question(self.job)
        self.upload(rows, period='p000001'); wf.prepare_question(self.job)
        self.assertEqual(2, len(pool.load(wf, self.job)['articles']))

    def test_explicit_other_period_rejected(self):
        self.upload(period='p999999')
        with self.assertRaisesRegex(wf.WorkflowError, '期次不一致'):
            wf.prepare_question(self.job)

    def test_xlsx_uploaded_same_question_details(self):
        self.prepared(suffix='.xlsx')
        self.assertEqual(25, len(pool.load(wf, self.job)['articles']))

    def test_repeated_url_fragments_are_one_article(self):
        rows = self.rows(1); rows[1]['文章链接'] += '#one'; rows[2]['文章链接'] += '#two'
        self.prepared(rows=rows)
        self.assertEqual(1, len(pool.load(wf, self.job)['articles']))
        self.assertEqual(3, pool.load(wf, self.job)['articles'][0]['citation_count'])

    def test_aggregated_counts_do_not_fake_observations(self):
        self.upload([dict(x, 引用次数=35) for x in self.rows(1)])
        with self.assertRaisesRegex(wf.WorkflowError, '逐条引用明细'):
            wf.prepare_question(self.job)

    def test_xlsx_aggregate_and_invalid_date_rejected(self):
        for change, message in [({'引用次数': 50}, '逐条引用明细'), ({'日期': '错误日期'}, '无法解析')]:
            with self.subTest(change=change):
                self.upload([dict(x, **change) for x in self.rows(1)], suffix='.xlsx')
                with self.assertRaisesRegex(wf.WorkflowError, message):
                    wf.prepare_question(self.job)

    def test_resume_after_source_pack_created_before_binding(self):
        self.upload()
        before = wf.load_state(self.job)['reference_pack']['pack_version']
        with patch.object(wf, 'bind_reference_pack', side_effect=RuntimeError('simulated interruption')):
            with self.assertRaisesRegex(RuntimeError, 'interruption'):
                wf.prepare_question(self.job)
        wf.prepare_question(self.job)
        self.assertEqual(before + 1, wf.load_state(self.job)['reference_pack']['pack_version'])
        self.assertEqual(25, len(pool.load(wf, self.job)['articles']))
        self.assertEqual('recovered', wf.load_state(self.job)['metadata']['question_source_delivery']['status'])

    def test_resume_after_source_pack_binding_before_receipt(self):
        self.upload()
        original = wf.bind_reference_pack
        def bind_then_interrupt(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('simulated interruption')
        with patch.object(wf, 'bind_reference_pack', side_effect=bind_then_interrupt):
            with self.assertRaisesRegex(RuntimeError, 'interruption'):
                wf.prepare_question(self.job)
        before = wf.load_state(self.job)['reference_pack']['path']
        wf.prepare_question(self.job)
        self.assertEqual(before, wf.load_state(self.job)['reference_pack']['path'])
        self.assertNotIn('pending_citation_input', wf.load_state(self.job)['metadata'])

    def test_other_patterns_receive_selected_pool_in_blueprint(self):
        self.prepared(); self.state(selected_pattern_id='P03')
        # This is the frozen v16.4 P03 route. New six-genre planning has its
        # own integration coverage and includes pool references internally.
        state = wf.load_state(self.job)
        state['metadata']['natural_prose_contract'] = 'frontmind-natural-prose/16'
        wf.save_state(self.job, state)
        pool.choose(wf, self.job, '2', [self.selected_body()])
        with patch.object(wf, 'prepare_own_brand_context'), patch.object(wf.writing_context, 'prompt_blueprint', return_value='原专用蓝图'):
            prompt = wf.prompt_blueprint(self.job, p0=False)
        self.assertIn('原专用蓝图', prompt)
        self.assertIn('完整合成例文', prompt)

    def test_repeat_prepare_reuses_pool_without_new_pack(self):
        self.prepared(); before = wf.load_state(self.job)['reference_pack']['path']
        before_pool = (self.job/pool.PATH).read_bytes()
        wf.prepare_question(self.job)
        self.assertEqual(before, wf.load_state(self.job)['reference_pack']['path'])
        self.assertEqual(before_pool, (self.job/pool.PATH).read_bytes())

    def test_selected_article_beyond_top20_fulltext_and_primary_pair_unchanged(self):
        self.prepared()
        self.state(selected_pattern_id='P01')
        index = self.job/'examples/question/index.json'
        wf.atomic_json(index, {'examples': [{'title':'金蝶'}, {'title':'ThinkPad'}]})
        before = index.read_bytes()
        pool.choose(wf, self.job, '25', [self.selected_body()])
        text = pool.prompt_references(wf, self.job)
        self.assertIn('完整合成例文', text)
        self.assertEqual([25], wf.load_state(self.job)['decisions']['article_pool_selection']['ranks'])
        self.assertEqual(before, index.read_bytes())

    def test_selected_remote_article_acquisition_and_unread_failure(self):
        self.prepared()
        record = ExampleStore(self.job).import_user_file(self.selected_body())
        with patch.object(ExampleStore, 'acquire_http', return_value=record):
            self.assertTrue(pool.choose(wf, self.job, '2'))
        with patch.object(ExampleStore, 'acquire_http', side_effect=AcquisitionError('无法取得完整正文')):
            self.assertFalse(pool.choose(wf, self.job, '3'))
        with self.assertRaisesRegex(wf.WorkflowError, '完整正文'):
            pool.require_selection(wf, self.job)
        self.assertTrue(pool.choose(wf, self.job, '3', [self.selected_body(2)]))
        pool.require_selection(wf, self.job)

    def test_27sem_article_token_is_scoped_to_known_host_and_path(self):
        urls = ['https://27sem.com/article/18043', 'https://www.27sem.com/article/18043',
                'https://27sem.com/category/12', 'https://27sem.com/article-other/18043',
                'https://27sem.com.example.org/article/18043', 'https://example.com/article/18043']
        self.prepared(rows=[dict(self.rows(1)[0], 文章链接=url) for url in urls])
        record = ExampleStore(self.job).import_user_file(self.selected_body())
        for n, url in enumerate(urls, 1):
            with self.subTest(url=url), patch.object(ExampleStore, 'acquire_http', return_value=record) as acquire:
                self.assertTrue(pool.choose(wf, self.job, str(n)))
                if n <= 2:
                    acquire.assert_called_once_with(url, article_tokens=('paragraph_img',))
                else:
                    acquire.assert_called_once_with(url)

    def mocked_http(self, html, url='https://27sem.com/article/18043'):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = html.encode('utf-8')
        response.status = 200
        response.geturl.return_value = url
        response.headers = {'Content-Type': 'text/html; charset=utf-8'}
        opener = MagicMock(); opener.open.return_value = response
        return opener

    def test_27sem_closed_body_preserves_ending_and_excludes_page_controls(self):
        self.prepared(rows=[dict(self.rows(1)[0], 文章链接='https://27sem.com/article/18043')])
        html = ('<html><title>合成选型指南</title><body><nav>菜单</nav>'
                '<div class="advertising">广告内容</div><div class="paragraph_img">'
                '<h2>正文标题</h2><p>正文开始。</p><p>完整中段与<strong>重点</strong>。</p>'
                '<h3>免责声明</h3><p>正文结束，包含完整声明。</p></div>'
                '<div class="copyright_notice">版权控制</div>'
                '<div class="related_recommendation_content">相关推荐</div></body></html>')
        with patch.object(acquisition, 'public_url', side_effect=lambda url: url), \
                patch.object(acquisition, 'build_opener', return_value=self.mocked_http(html)):
            self.assertTrue(pool.choose(wf, self.job, '1'))
        example = pool.selected(wf, self.job)['examples'][0]
        record = ExampleStore(self.job).resolve(example['artifact_id'], require_complete=True)
        self.assertEqual('http', record['obtained_via'])
        self.assertEqual('complete', record['completeness'])
        self.assertTrue(record['article_region_closed'])
        body = (self.job / record['text_path']).read_text()
        for expected in ['正文开始。', '完整中段与重点。', '免责声明', '正文结束，包含完整声明。']:
            self.assertIn(expected, body)
        for excluded in ['菜单', '广告内容', '版权控制', '相关推荐']:
            self.assertNotIn(excluded, body)

    def test_27sem_unclosed_body_still_blocks_selection(self):
        self.prepared(rows=[dict(self.rows(1)[0], 文章链接='https://27sem.com/article/18043')])
        html = '<html><title>合成选型指南</title><body><div class="paragraph_img"><p>截断正文。</p>'
        with patch.object(acquisition, 'public_url', side_effect=lambda url: url), \
                patch.object(acquisition, 'build_opener', return_value=self.mocked_http(html)):
            self.assertFalse(pool.choose(wf, self.job, '1'))
        self.assertFalse((self.job / pool.SELECTION).exists())
        state = wf.load_state(self.job)
        self.assertTrue(state['metadata']['article_pool_selection_pending'])
        self.assertIn('incomplete', state['metadata']['article_pool_acquisition_errors'][0])
        record_path = next((self.job / 'artifacts/acquired_sources').glob('*/record.json'))
        record = json.loads(record_path.read_text())
        self.assertEqual('partial', record['completeness'])
        self.assertEqual('incomplete', record['acquisition_status'])
        self.assertFalse(record['article_region_closed'])
        with self.assertRaisesRegex(wf.WorkflowError, '完整正文'):
            pool.require_selection(wf, self.job)

    def test_shunqi_mobile_blog_inner_body_excludes_news_and_stays_scoped(self):
        urls = ['https://m.11467.com/blog/d19899247.htm',
                'https://blog.11467.com/b19899247.htm', 'https://m.11467.com/product/123.htm']
        self.prepared(rows=[dict(self.rows(1)[0], 文章链接=url) for url in urls])
        # The enclosing main is deliberately longer than the article, matching
        # the page layout that otherwise pulls unrelated news into the body.
        html = ('<html><title>合成便携设备分析</title><body><main><article>'
                '<section class="blog-detail-content"><h2>正文标题</h2><p>正文开始。</p>'
                '<p>完整中段。</p><p>正文结束，参数有效期完整保留。</p></section></article>'
                '<section class="blog-detail-panel"><h2>公司新闻</h2>'
                '<p>' + '无关新闻条目。' * 30 + '</p></section>'
                '<section><h2>相关新闻</h2><p>无关页栏末段</p></section></main></body></html>')
        with patch.object(acquisition, 'public_url', side_effect=lambda url: url), \
                patch.object(acquisition, 'build_opener', return_value=self.mocked_http(html, urls[0])):
            self.assertTrue(pool.choose(wf, self.job, '1'))
        example = pool.selected(wf, self.job)['examples'][0]
        record = ExampleStore(self.job).resolve(example['artifact_id'], require_complete=True)
        self.assertEqual('complete', record['completeness'])
        self.assertTrue(record['article_region_closed'])
        body = (self.job / record['text_path']).read_text()
        for expected in ['正文开始。', '完整中段。', '正文结束，参数有效期完整保留。']:
            self.assertIn(expected, body)
        for excluded in ['公司新闻', '相关新闻', '无关新闻条目', '无关页栏末段']:
            self.assertNotIn(excluded, body)
        for n, url in enumerate(urls[1:], 2):
            with self.subTest(url=url), patch.object(ExampleStore, 'acquire_http', return_value=record) as acquire:
                self.assertTrue(pool.choose(wf, self.job, str(n)))
                acquire.assert_called_once_with(url)

    def test_invalid_selection_keeps_old_selection(self):
        self.prepared(); pool.choose(wf, self.job, 'none')
        before = (self.job/pool.SELECTION).read_bytes()
        for value in ('0', '26', '1,1', '1,2,3', 'bad'):
            with self.assertRaises(wf.WorkflowError): pool.choose(wf, self.job, value)
        self.assertEqual(before, (self.job/pool.SELECTION).read_bytes())

    def test_empty_continue_or_style_choice_cannot_skip_pool_choice(self):
        self.prepared(); self.state(status='awaiting_example_confirmation', selected_pattern_id='P03')
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', str(wf.load_state(self.job)['revision']), '--example-route', 'B'])
        with self.assertRaisesRegex(wf.WorkflowError, '文章池'):
            wf.continue_workflow(args)
        with patch.object(wf, 'drive', return_value=0):
            args.pool_selection = 'none'; wf.continue_workflow(args)
        self.assertEqual('B', wf.load_state(self.job)['selected_example_route'])

    def test_selection_not_carried_into_different_question(self):
        self.prepared(); pool.choose(wf, self.job, 'none')
        state = wf.load_state(self.job); state['question']['period_id'] = 'p000002'; wf.save_state(self.job, state)
        with self.assertRaisesRegex(wf.WorkflowError, '当前问题与期次'):
            pool.require_selection(wf, self.job)

    def test_source_tampering_detected_before_import(self):
        self.upload(); pending = wf.load_state(self.job)['metadata']['pending_citation_input']
        (self.job/pending['path']).write_text('[]')
        with self.assertRaisesRegex(wf.WorkflowError, '发生变化'):
            wf.prepare_question(self.job)

    def test_pool_print_cli(self):
        self.prepared()
        command = [sys.executable, str(wf.ROOT/'scripts/frontmind_workflow.py'), 'article-pool', '--job-dir', str(self.job)]
        top = subprocess.run(command, capture_output=True, text=True, check=True).stdout
        full = subprocess.run(command + ['--all'], capture_output=True, text=True, check=True).stdout
        self.assertIn('完整案例第20篇', top); self.assertNotIn('完整案例第25篇', top)
        self.assertIn('完整案例第25篇', full)

    def test_answer_analysis_never_replaces_uploaded_pool_with_search(self):
        self.prepared(); prompt = wf.prompt_answer_analysis(self.job)
        self.assertIn('固定返回空数组', prompt)
        self.assertNotIn('最多两篇真实取得例文', prompt)

    def test_blueprint_cannot_run_before_source_gate(self):
        self.state(selected_pattern_id='P01')
        with patch.object(wf, 'ensure_action', side_effect=AssertionError('must not call')), contextlib.redirect_stdout(io.StringIO()):
            wf.run_article_blueprint(self.job)
        self.assertEqual('awaiting_question_research_inputs', wf.load_state(self.job)['status'])


class ArticlePoolCliIntegrationTests(unittest.TestCase):
    """Real launcher and immutable Pack transitions, deterministic model fixtures."""
    @classmethod
    def setUpClass(cls):
        from scripts.tests_v411 import test_workflow_v411 as legacy
        cls.legacy = legacy
        legacy.WorkflowV411Tests.setUpClass()
        cls.base = legacy.WorkflowV411Tests.base
        cls.pack = legacy.WorkflowV411Tests.p0_pack

    @classmethod
    def tearDownClass(cls):
        cls.legacy.WorkflowV411Tests.tearDownClass()

    def new_job(self, name):
        job = self.base / name
        self.legacy.run_cli('article', '--reference-pack', str(self.pack), '--job-dir', str(job),
                            '--question-id', '服务机构推荐', '--question', '服务机构推荐', '--offline-fixture')
        self.legacy.resume(job, '--reference-pack-route', 'use')
        self.assertEqual('awaiting_question_research_inputs', self.legacy.state(job)['status'])
        # These CLI fixtures reproduce the v16.4 direct positioning handoff.
        current = wf.load_state(job)
        current['metadata']['natural_prose_contract'] = 'frontmind-natural-prose/16'
        wf.save_state(job, current)
        return job

    def inputs(self, name):
        answer = self.base / (name + '-answers.json')
        source = self.base / (name + '-sources.json')
        answer.write_text(json.dumps([{'问题':'服务机构推荐', '平台':platform, '回答内容':'合成完整答案，仅用于流程验证。', '日期':'2026-10-01'}
                                     for platform in ['平台甲','平台乙']], ensure_ascii=False))
        source.write_text(json.dumps([{'问题':'服务机构推荐', '文章链接':f'https://example.com/case/{n}',
                                       '日期':'2026-10-01', '标题':f'实际信源第{n}篇'} for n in range(1,24)], ensure_ascii=False))
        return answer, source

    def test_source_first_then_answers_selection_and_positioning_to_blueprint(self):
        job = self.new_job('v164-source-first')
        answer, source = self.inputs('source-first')
        self.legacy.resume(job, '--source-workbook', str(source))
        self.assertEqual('awaiting_question_research_inputs', self.legacy.state(job)['status'])
        self.assertIn('pending_citation_input', self.legacy.state(job)['metadata'])
        self.legacy.resume(job, '--monitoring-answers', str(answer))
        self.assertEqual('awaiting_response_brief', self.legacy.state(job)['status'])
        self.assertIn('实际信源第20篇', self.legacy.page(job))
        self.legacy.resume(job, '--no-extra-response-requirements', '--ai-brand-recognition', 'insufficient')
        self.legacy.resume(job, '--pattern', 'P01')
        self.assertEqual('awaiting_example_confirmation', self.legacy.state(job)['status'])
        self.assertIn('实际信源第20篇', self.legacy.page(job))
        from shared import recommendation_references
        recommendation_references.register(wf, wf.ROOT, job)
        self.legacy.resume(job, '--example-route', 'A', expect=2)
        full = self.base / 'v164-full.md'
        full.write_text('# 选择的完整文章\n\n' + '从机构业务切入，按核心特点安排详略。\n\n' * 50)
        self.legacy.resume(job, '--pool-selection', '23', '--pool-example-file', str(full), '--example-route', 'A')
        self.assertEqual('awaiting_question_positioning_confirmation', self.legacy.state(job)['status'])
        self.legacy.resume(job, '--confirm-question-positioning')
        self.assertEqual('awaiting_blueprint_confirmation', self.legacy.state(job)['status'])
        prompt = wf.prompt_blueprint(job, p0=False)
        from shared import writing_context_v16
        preparation = writing_context_v16.prompt_preparation(wf, job)
        for value in (prompt, preparation):
            self.assertIn('<confirmed_question_positioning>', value)
            self.assertIn('选择的完整文章', value)
        style = (job/'examples/question/index.json').read_text()
        self.assertIn('ThinkPad', style)
        self.assertIn('金蝶', style)

    def test_answers_first_source_only_resume_and_same_pack_reuse(self):
        job = self.new_job('v164-answer-first')
        answer, source = self.inputs('answer-first')
        self.legacy.resume(job, '--monitoring-answers', str(answer))
        self.assertEqual('awaiting_question_research_inputs', self.legacy.state(job)['status'])
        self.assertIn('信源', self.legacy.page(job))
        self.legacy.resume(job, '--source-workbook', str(source))
        self.assertEqual('awaiting_response_brief', self.legacy.state(job)['status'])
        enriched = Path(self.legacy.state(job)['reference_pack']['path'])
        second = self.base / 'v164-reuse'
        self.legacy.run_cli('article', '--reference-pack', str(enriched), '--job-dir', str(second),
                            '--question-id', '服务机构推荐', '--question', '服务机构推荐', '--offline-fixture')
        self.legacy.resume(second, '--reference-pack-route', 'use')
        self.assertEqual('awaiting_response_brief', self.legacy.state(second)['status'])
        self.assertEqual(23, len(pool.load(wf, second)['articles']))
        self.assertNotIn('question_source_delivery', self.legacy.state(second)['metadata'])


if __name__ == '__main__':
    unittest.main()
