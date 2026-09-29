"""Durable intent in real prompts and controller transitions; all data synthetic.

These tests establish input preservation and deterministic format conversion.
They do not grade prose, impose character gates, or call external providers.
"""
from collections import Counter
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from scripts.tests_v411 import test_natural_writing_context_final12 as legacy
from shared import model_runtime, natural_editor, manuscript_revision, writing_context
from shared import writing_context_v13 as current, writing_requirements as req

ROOT = Path(__file__).resolve().parents[2]
QUESTION = '合成地区的专项服务机构推荐'
TARGET = '本篇目标3000个正文可见非空白字符'
RELATION = '按综合支持与预约服务优先，其次按专业需求，再介绍专门服务机构'
FORMAT = '三个分档独立加粗；11个机构段首行内加粗，名称后正文紧接不换行'
NAMES = [f'合成机构{i}有限公司' for i in range(1, 12)]


class WritingRequirementsFlowTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp
    job = flow.NaturalEditorFlowTests.job
    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def recommendation_job(self, pattern='P02'):
        job = self.job()
        state = wf.load_state(job)
        state['question']['question_text'] = QUESTION
        state['selected_pattern_id'] = pattern
        state['metadata']['writing_requirements_contract'] = req.CONTRACT
        wf.save_state(job, state)
        bp = wf.read_json(job/'blueprints/article_blueprint.json')
        bp.update(question=QUESTION, pattern_id=pattern, estimated_length=TARGET,
                  candidate_order=NAMES if pattern == 'P02' else NAMES[:1],
                  brand_positioning_use=RELATION, recommendation_relationships=RELATION,
                  formatting=FORMAT, reference_roles={'primary': 'style', 'budget': 'user_explicit'})
        wf.atomic_json(job/'blueprints/article_blueprint.json', bp)
        return job

    def revise(self, job, flag, message, requirements=None):
        request = self.root/'edit.md'; request.write_text(message)
        argv = ['continue', '--job-dir', str(job), '--revision', str(wf.load_state(job)['revision']), flag, str(request)]
        if requirements:
            path = self.root/'requirements.json'; path.write_text(json.dumps(requirements, ensure_ascii=False))
            argv += ['--writing-requirements', str(path)]
        with patch.object(wf, 'drive', return_value=0), contextlib.redirect_stdout(io.StringIO()):
            wf.continue_workflow(wf.parser().parse_args(argv))

    def assert_commission(self, prompt, target=TARGET):
        for content in (QUESTION, target, RELATION, FORMAT):
            self.assertIn(content, prompt)

    def test_complete_chain_payloads_retain_question_length_and_recommendation(self):
        job = self.recommendation_job()
        self.needs_revision = True
        self.finish(job)
        self.assertEqual(self.actions, ['article_draft', 'article_edit', 'article_finalize',
                                      'article_repair', 'article_titles', 'article_title_review'])
        self.assertEqual(self.calls['article_finalize'], 1)
        self.assertEqual(self.calls['article_repair'], 1)
        for action, prompt in self.prompts.items():
            self.assertTrue(prompt.startswith(req.MARKER+'\n'), action)
            self.assert_commission(prompt)
            actual_payload = model_runtime.build_payload(action, prompt)
            wire = json.dumps(actual_payload, ensure_ascii=False)
            for content in (QUESTION, TARGET, RELATION, FORMAT):
                self.assertIn(content, wire, action)
        self.assertEqual(wf.read_json(job/'production/article_final_source.json')['action'], 'article_repair')

    def test_manuscript_and_title_revisions_keep_requirements_and_real_base(self):
        job = self.recommendation_job(); self.finish(job)
        self.revise(job, '--manuscript-edits', '只改导语的重复表达。')
        frozen = manuscript_revision.current_revision(wf, job, p0=False)
        self.assertEqual(frozen['base_markdown'], self.body)
        self.assertEqual(frozen['effective_writing_requirements']['estimated_length'], TARGET)
        self.edited_body = self.body.replace('简短导语。', '新的合成导语。')
        self.finish(job)
        for action in ('article_edit', 'article_finalize', 'article_titles', 'article_title_review'):
            self.assert_commission(self.prompts[action])
        before = (job/'production/article_finalized.json').read_bytes()
        counts = self.calls.copy()
        self.revise(job, '--title-edits', '标题继续回答原推荐问题。')
        self.finish(job)
        for action in ('article_titles', 'article_title_review'):
            self.assert_commission(self.prompts[action])
            self.assertIn('新的合成导语。', self.prompts[action])
        self.assertEqual(self.calls['article_finalize'], counts['article_finalize'])
        self.assertEqual(self.calls['article_draft'], 1)
        self.assertEqual((job/'production/article_finalized.json').read_bytes(), before)

    def test_explicit_target_change_does_not_erase_other_requirements(self):
        job = self.recommendation_job(); self.finish(job)
        changed = '用户新目标3200个正文可见非空白字符'
        self.revise(job, '--manuscript-edits', '按新增的目标充分展开已确认业务。', {'estimated_length': changed})
        effective = req.effective(wf, job, p0=False)
        self.assertEqual(effective['estimated_length'], changed)
        self.assertEqual(effective['candidate_order'], NAMES)
        self.assertEqual(effective['recommendation_relationships'], RELATION)
        self.assert_commission(wf.prompt_edit(job, p0=False), changed)

    def test_identity_fields_cannot_be_silently_changed_as_writing_preferences(self):
        path = self.root/'changes.json'
        for change in ({'question': '不同的正式问题'}, {'pattern_id': 'P03'}):
            path.write_text(json.dumps(change, ensure_ascii=False))
            with self.assertRaises(ValueError):
                req.read_changes(path)
        path.write_text(json.dumps({'estimated_length': TARGET, 'formatting': FORMAT}, ensure_ascii=False))
        self.assertEqual(req.read_changes(path), {'estimated_length': TARGET, 'formatting': FORMAT})

    def test_ai_background_never_counts_as_length_and_short_style_keeps_target(self):
        job = self.recommendation_job('P01')
        state = wf.load_state(job); state['selected_example_route'] = 'A'; wf.save_state(job, state)
        ai = 'AI_BACKGROUND_ONLY_' + '合成答案内容。'*1000
        style = 'SHORT_STYLE_ONLY：单个产品的具体介绍。'
        length = 'EXPLICIT_LENGTH_ONLY：' + '合成篇幅。'*80
        rows = []
        for name, text, role in [('ai', ai, 'content_background'), ('style', style, 'style_primary'), ('length', length, 'length_only')]:
            path = job/'inputs'/f'{name}.md'; path.write_text(text)
            rows.append({'title': name, 'path': str(path), 'role': role})
        originals = {r['path']: Path(r['path']).read_bytes() for r in rows}
        with patch.object(wf, 'load_examples', return_value=rows), patch.object(wf, 'answer_texts', return_value=[ai]):
            budget = current.reference_length_budget(wf, job, p0=False)
            self.assertEqual(budget['samples'], [{'title': 'length', 'characters': natural_editor.character_count(length)}])
            self.assertEqual(budget['longest_sample_characters'], natural_editor.character_count(length))
            blueprint = wf.prompt_blueprint(job, p0=False)
            self.assertEqual(blueprint.count(ai), 1)
            self.assertIn(TARGET, blueprint)
            prompt = wf.prompt_article(job, p0=False)
            self.assertEqual(prompt.count(style), 1)
            self.assertNotIn(ai, prompt)
            self.assertNotIn(length, prompt)
            self.assertIn(TARGET, prompt)
        self.assertEqual({p: Path(p).read_bytes() for p in originals}, originals)

    def test_replacing_examples_preserves_only_matching_confirmed_positioning(self):
        job = self.recommendation_job()
        qpath = job/'question_positioning/question_positioning.json'
        state = wf.load_state(job); state['status'] = 'awaiting_example_confirmation'
        state['decisions']['question_positioning_confirmation'] = {'revision': 1, 'confirmed_at': 'synthetic'}
        wf.save_state(job, state)
        record = {'pattern_id': 'P02', 'question': QUESTION, 'brand': state['reference_pack']['brand'], 'natural_analysis': RELATION}
        wf.atomic_json(qpath, record); original = qpath.read_bytes()
        for field, changed, expected in [(None, None, 'running_article_blueprint'),
                                         ('question', '另一个正式问题', 'running_question_positioning'),
                                         ('pattern_id', 'P01', 'running_question_positioning'),
                                         ('brand', '其他品牌', 'running_question_positioning')]:
            row = dict(record)
            if field: row[field] = changed
            wf.atomic_json(qpath, row)
            args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(wf.load_state(job)['revision']), '--example-route', 'A'])
            with patch.object(wf, 'load_examples', return_value=[{'title': '新例文'}]), patch.object(wf, 'drive', return_value=0), \
                 patch.object(wf, 'ensure_action', side_effect=AssertionError('confirmation transition must not call a provider')):
                wf.handle_example_pause(args, job, p0=False)
            self.assertEqual(wf.load_state(job)['status'], expected)
            self.assertEqual(wf.read_json(qpath), row)
        wf.atomic_json(qpath, record)
        self.assertEqual(qpath.read_bytes(), original)

    def test_bundled_p01_examples_register_full_bodies_as_style_only(self):
        from shared import recommendation_references, example_acquisition
        job = self.recommendation_job('P01')
        state = wf.load_state(job)
        state['flags']['offline_fixture'] = False
        state['selected_example_route'] = 'A'
        wf.save_state(job, state)
        # The distributed package need not include publisher text; simulate
        # an already frozen pair without depending on unshipped source files.
        folder = self.root/'frozen/resources/p01_recommendation'; folder.mkdir(parents=True)
        manifest = wf.read_json(ROOT/'resources/p01_recommendation/manifest.json')
        for i, item in enumerate(manifest['examples']):
            body = f'SYNTHETIC_ORIGINAL_BEGIN_{i}\n完整合成正文。\nSYNTHETIC_ORIGINAL_END_{i}\n'.encode()
            path = folder/item['body']; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
            (folder/item['raw']).write_bytes(b'<html>explicit offline source fixture</html>')
            item['sha256'] = hashlib.sha256(body).hexdigest()
        wf.atomic_json(folder/'manifest.json', manifest)
        with patch.object(example_acquisition.ExampleStore, 'acquire_http', side_effect=AssertionError('frozen reference is local')):
            records = recommendation_references.register(wf, folder.parents[1], job)
            reloaded = wf.load_examples(job, 'question')
        self.assertEqual(records, reloaded)
        self.assertEqual([r['role'] for r in records], ['style_primary', 'style_secondary'])
        for item, record in zip(manifest['examples'], records):
            source = (folder/item['body']).read_bytes()
            self.assertEqual(Path(record['path']).read_bytes(), source)
            self.assertEqual(record['text_sha256'], item['sha256'])
            self.assertEqual(record['completeness'], 'complete')
        refs = current._natural_reference_sets(wf, job, p0=False)
        self.assertEqual(len(refs['style']), 2)
        self.assertEqual(refs['length'], [])
        self.assertIn(TARGET, wf.prompt_article(job, p0=False))

    def test_portable_reference_registration_decodes_and_selects_full_article(self):
        from shared import example_acquisition as acquisition, recommendation_references
        job = self.recommendation_job('P01')
        state = wf.load_state(job); state['flags']['offline_fixture'] = False; wf.save_state(job, state)
        folder = self.root/'portable/resources/p01_recommendation'; folder.mkdir(parents=True)
        manifest = wf.read_json(ROOT/'resources/p01_recommendation/manifest.json')
        wf.atomic_json(folder/'manifest.json', manifest)
        responses = {}
        for i, item in enumerate(manifest['examples']):
            body = f'<html><title>合成例文{i}</title><body><div>无关导航内容</div><div class="{item["article_tokens"][0]}"><p>原文开头{i}。</p><p>完整中段{i}。</p><p>原文结束{i}。</p></div><aside>不应注入的页尾</aside></body></html>'
            responses[item['url']] = body.encode(item['encoding'])
        calls = []
        class Response:
            status = 200
            headers = {'Content-Type': 'text/html'}
            def __init__(self, url): self.url = url
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return responses[self.url]
            def geturl(self): return self.url
        def open_http(request, **kwargs):
            calls.append(request.full_url)
            return Response(request.full_url)
        with patch.object(acquisition, 'public_url', side_effect=lambda url: url), \
             patch.object(acquisition, 'build_opener', return_value=SimpleNamespace(open=open_http)):
            records = recommendation_references.register(wf, folder.parents[1], job)
            self.assertEqual(calls, [item['url'] for item in manifest['examples']])
            for i, record in enumerate(records):
                self.assertEqual(record['completeness'], 'complete')
                text = Path(record['path']).read_text()
                for paragraph in (f'原文开头{i}。', f'完整中段{i}。', f'原文结束{i}。'):
                    self.assertIn(paragraph, text)
                self.assertNotIn('无关导航内容', text)
                self.assertNotIn('不应注入', text)
                self.assertNotIn('\ufffd', text)
            # An extension belongs to this call, not to the global parser.
            # The previous no-options API still refuses an unknown region.
            default = acquisition.ExampleStore(job).acquire_http(manifest['examples'][0]['url'])
            self.assertEqual(default['completeness'], 'partial')
            self.assertIn('No complete', default['integrity_note'])

    def test_p03_through_p06_keep_distinct_tasks(self):
        job = self.recommendation_job()
        for pattern in ('P03', 'P04', 'P05', 'P06'):
            state = wf.load_state(job); state['selected_pattern_id'] = pattern; wf.save_state(job, state)
            prompt = wf.prompt_article(job, p0=False)
            self.assertIn(current.NATURAL_PATTERN_GUIDANCE[pattern], prompt)
            self.assertNotIn(current.NATURAL_PATTERN_GUIDANCE['P01'], prompt)
            self.assertNotIn(current.NATURAL_PATTERN_GUIDANCE['P02'], prompt)

    def test_hashseed_changes_do_not_change_actual_prompt(self):
        script = '''from scripts.tests_v411.test_writing_requirements_final13 import WritingRequirementsFlowTests
from scripts import frontmind_workflow as wf
import hashlib
t=WritingRequirementsFlowTests();t.setUp()
try:
 j=t.recommendation_job();print(hashlib.sha256(wf.prompt_article(j,p0=False).encode()).hexdigest())
finally:t.doCleanups()
'''
        hashes = []
        for seed in ('1', '7', '99'):
            hashes.append(subprocess.check_output([sys.executable, '-c', script], cwd=ROOT,
                          env={**os.environ, 'PYTHONHASHSEED': seed}, text=True).strip())
        self.assertEqual(len(set(hashes)), 1, hashes)


class PatternTaskInputTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            'metadata': {'writing_editor_contract': natural_editor.CONTRACT},
            'question': {'question_text': '合成城市的专项服务机构推荐', 'answers': [
                {'full_text_path': '/synthetic/answer1.md'}, {'full_text_path': '/synthetic/answer2.md'}]},
            'reference_pack': {'brand': '合成品牌'}, 'decisions': {}, 'selected_pattern_id': 'P01'}
        self.job = Path('/synthetic/job')
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        for name, value in {
            'load_state': self.state,
            'brand_content_context': {'core_positioning': '合成核心定位', 'p0': '合成品牌P0', 'brand_inputs': '合成品牌输入'},
            'write_reference_context': Path('/synthetic/facts.md'),
            'answer_texts': ['合成答案一', '合成答案二'], 'user_material_text': '合成补充',
            'read_json': {'recommended_pattern_id': 'P01', 'pattern_reasons': {x: '合成原因'+x for x in wf.QUESTION_PATTERN_IDS}},
            'emit_pause': 0,
        }.items():
            self.stack.enter_context(patch.object(wf, name, return_value=value))
        self.paused = self.stack.enter_context(patch.object(wf, 'set_pause'))

    def test_legacy_pattern_input_and_request_identity_are_unchanged(self):
        # Captured before changing the Pattern dispatcher, with these exact
        # synthetic inputs. The original bodies remain the legacy branch.
        expected = {
            'answer_analysis': ('e8d3cb0f71e7ff413642e0407b5a2c2b312266fc1f7201dada673aa86734c0ae',
                                '5db640f5311179bc757c0d01739b2ab99585b861c1c860812060d33a26640500'),
            'question_positioning': ('6e47205ab9ac8640bd5dc56424e074a23e6110e306e71552ce65f7fd13b5d029',
                                     'b8ce623edd613623a2c17378257fa1e1abee82bceb6d863d4799ecc8852ec425'),
        }
        for action, pair in expected.items():
            prompt = getattr(wf, 'prompt_'+action)(self.job)
            # Prompt compatibility is independent of the intentionally updated host profile.
            self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), pair[0])
            self.assertEqual(model_runtime.build_payload(action, prompt)["profile"]["reasoning_effort"], "high")
        wf.render_pattern_confirmation(self.job)
        self.assertEqual(hashlib.sha256(self.paused.call_args.args[2].encode()).hexdigest(),
                         'f4cfe16e46f53eddbfbaff7a584e7e10512b47f9f05e945b14624c4cd8809c7c')

    def test_current_upstream_model_inputs_keep_commission_without_legacy_missions(self):
        self.state['metadata']['writing_requirements_contract'] = req.CONTRACT
        self.state['metadata']['effective_writing_requirements'] = {
            'estimated_length': TARGET, 'recommendation_relationships': RELATION, 'formatting': FORMAT}
        self.state['decisions']['response_brief'] = '本篇为新闻品宣专题，按具体业务展开。'
        for pattern in ('P01', 'P02'):
            self.state['selected_pattern_id'] = pattern
            for action in ('answer_analysis', 'question_positioning'):
                prompt = getattr(wf, 'prompt_'+action)(self.job)
                payload = json.dumps(model_runtime.build_payload(action, prompt), ensure_ascii=False)
                self.assertIn(self.state['decisions']['response_brief'], payload)
                self.assertIn(self.state['question']['question_text'], payload)
                self.assertNotIn('P01 用自然段写清本题选择、企业为何适合、替代路径与适合人群', payload)
                self.assertNotIn('正文从当前需求解释选择标准与顺序', payload)
                if action == 'question_positioning':
                    for value in (TARGET, RELATION, FORMAT):
                        self.assertIn(value, payload)
                    self.assertIn('P01 围绕主推荐对象回答正式问题', payload)
                    self.assertIn('已确认分类用于组织选材', payload)

    def test_current_pattern_page_presents_actual_recommendation_tasks(self):
        self.state['metadata']['writing_requirements_contract'] = req.CONTRACT
        wf.render_pattern_confirmation(self.job)
        page = self.paused.call_args.args[2]
        self.assertIn('以具体业务、人员、方法和服务介绍一个主要推荐对象', page)
        self.assertIn('保留本篇选定的推荐关系、重点和顺序', page)
        self.assertNotIn('建立多主体范围、自然分层或选择方法', page)
        for pattern in ('P00', 'P03', 'P04', 'P05', 'P06'):
            self.assertEqual(wf.patterns_for_state(self.state)[pattern], wf.PATTERNS[pattern])


class BlueprintMaterialInputTests(unittest.TestCase):
    def setUp(self):
        self.case = WritingRequirementsFlowTests(); self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.job = self.case.recommendation_job()
        self.root = self.job/'inputs/user_materials/question/frozen'
        self.root.mkdir(parents=True)
        (self.root/'body.md').write_text('SYNTHETIC_FACT_FULL_BODY\n已有事实。')
        (self.root/'original.html').write_text('<html>SYNTHETIC_FACT_FULL_BODY</html>')
        (self.root/'source.json').write_text('{"title":"合成来源","beginning":"SYNTHETIC_RESEARCH_EXCERPT"}')

    def unmark(self, *, v12=False):
        state = wf.load_state(self.job)
        state['metadata'].pop('blueprint_material_input_mode', None)
        if v12: state['metadata'].pop('writing_requirements_contract', None)
        wf.save_state(self.job, state)
        return state

    def tools(self):
        from shared.host_tools import HostTools
        # Replace only the fixture's intentionally invalid export stub.
        with zipfile.ZipFile(self.job/'00_input/reference_pack.zip', 'w') as archive:
            archive.writestr('materials/synthetic.md', '合成资料包原文')
        state = wf.load_state(self.job)
        state['reference_pack']['path'] = str((self.job/'00_input/reference_pack.zip').resolve())
        wf.save_state(self.job, state)
        return HostTools(ROOT, self.job, 'article_blueprint')

    def test_unmarked_v13_blueprint_prompt_and_request_identity_are_unchanged(self):
        self.unmark()
        prompt = wf.prompt_blueprint(self.job, p0=False)
        # Captured before the source-index branch with the exact fixture above.
        self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(),
                         '2d6942119d1936bd91294b0a10e9129c5079f652e68c19eee46bdd57bb11b203')
        # Provider identity is covered by runtime tests; this fixture stubs its profile.

    def test_actual_model_input_has_only_index_and_existing_reader_reads_original(self):
        originals = {p: p.read_bytes() for p in self.root.iterdir()}
        prompt = wf.prompt_blueprint(self.job, p0=False)
        payload = json.dumps(model_runtime.build_payload('article_blueprint', prompt), ensure_ascii=False)
        for excluded in ('SYNTHETIC_FACT_FULL_BODY', 'SYNTHETIC_RESEARCH_EXCERPT', '<html>'):
            self.assertNotIn(excluded, payload)
        rows = json.loads(wf.user_material_index(self.job, 'question'))
        self.assertEqual(len(rows), 3)
        tools = self.tools()
        for row in rows:
            self.assertIn(row['path'], prompt)
            self.assertEqual(row['title'], '合成来源')
            self.assertEqual(tools.resolve_artifact(row['path'])['path'], row['path'])
        selected = next(row for row in rows if row['name'] == 'body.md')
        result = tools.execute('read_material', {'artifact_id': selected['path']})
        self.assertIn('SYNTHETIC_FACT_FULL_BODY', json.dumps(result))
        self.assertTrue(tools.validate_result_sources({'writing_material_sources': [{'source_ref': selected['path']}]}))
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)

    def test_office_attachment_is_readable_without_injecting_extracted_body(self):
        from openpyxl import Workbook
        source = self.root/'service.xlsx'
        book = Workbook(); book.active.append(['SYNTHETIC_OFFICE_DETAIL', '服务明细']); book.save(source)
        original = source.read_bytes()
        state = wf.load_state(self.job)
        wf.prepare_blueprint_material_index(self.job, state, p0=False)
        wf.save_state(self.job, state)
        rows = json.loads(wf.user_material_index(self.job, 'question'))
        derived = next(row for row in rows if row['name'].endswith('.readable.md'))
        with patch.object(wf, 'extract_safe_material_text', side_effect=AssertionError('same frozen source is extracted only once')):
            wf.prepare_blueprint_material_index(self.job, state, p0=False)
        self.assertEqual(json.loads(wf.user_material_index(self.job, 'question')), rows)
        self.assertNotIn('SYNTHETIC_OFFICE_DETAIL', wf.prompt_blueprint(self.job, p0=False))
        tools = self.tools()
        read = tools.execute('read_material', {'artifact_id': derived['path']})
        self.assertIn('SYNTHETIC_OFFICE_DETAIL', json.dumps(read))
        self.assertEqual(source.read_bytes(), original)

    def test_new_blueprint_edit_and_supplement_opt_in_but_legacy_v12_does_not(self):
        for v12, flag in ((True, '--blueprint-edits'), (False, '--blueprint-edits'), (False, '--blueprint-supplement')):
            state = self.unmark(v12=v12)
            if not v12: state['metadata']['writing_requirements_contract'] = req.CONTRACT
            state['status'] = 'awaiting_blueprint_confirmation'; wf.save_state(self.job, state)
            args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', str(state['revision']), flag, '明确的新委托'])
            with patch.object(wf, 'drive', return_value=0):
                wf.handle_article_blueprint_pause(args, self.job)
            mode = wf.load_state(self.job)['metadata'].get('blueprint_material_input_mode')
            self.assertEqual(mode, None if v12 else req.BLUEPRINT_MATERIAL_INPUT_MODE)
        for kind in ('p0', 'article'):
            self.assertEqual(wf.make_state('new', kind)['metadata']['blueprint_material_input_mode'], req.BLUEPRINT_MATERIAL_INPUT_MODE)

    def test_explicit_upgrade_sets_mode_after_preserving_original_snapshot(self):
        self.case.finish(self.job)
        old = self.unmark(v12=True)
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', str(old['revision']),
                                      '--blueprint-edits', '按当前委托重新选材', '--upgrade-writing-editor'])
        with patch.object(wf, 'drive', return_value=0), contextlib.redirect_stdout(io.StringIO()):
            wf.continue_workflow(args)
        state = wf.load_state(self.job)
        self.assertEqual(state['metadata']['blueprint_material_input_mode'], req.BLUEPRINT_MATERIAL_INPUT_MODE)
        snapshot = Path(state['metadata']['writing_reruns'][-1]['archive_path'])
        self.assertNotIn('blueprint_material_input_mode', wf.load_state(snapshot)['metadata'])
        self.assertNotIn('writing_requirements_contract', wf.load_state(snapshot)['metadata'])
        for name in ('body.md', 'original.html', 'source.json'):
            relative = (self.root/name).relative_to(self.job)
            self.assertEqual((snapshot/relative).read_bytes(), (self.job/relative).read_bytes())

    def test_retry_does_not_change_unmarked_request_or_materials(self):
        state = self.unmark()
        state.update(status='running_article_blueprint', pending_action={'action': 'article_blueprint', 'error': {'code': 'interrupted_attempt'}})
        wf.save_state(self.job, state)
        before = wf.prompt_blueprint(self.job, p0=False)
        originals = {p: p.read_bytes() for p in self.root.iterdir()}
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', str(state['revision']), '--retry-current-action'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        self.assertNotIn('blueprint_material_input_mode', wf.load_state(self.job)['metadata'])
        self.assertEqual(wf.prompt_blueprint(self.job, p0=False), before)
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)


class WritingRequirementsFormatTests(unittest.TestCase):
    def test_three_bold_tiers_and_eleven_inline_names_survive_export(self):
        tiers = ['第一档 合成综合服务', '第二档 合成公共服务', '第三档 合成专门服务']
        groups = (NAMES[:3], NAMES[3:7], NAMES[7:])
        paragraphs = ['简短合成导语。']
        for tier, group in zip(tiers, groups):
            paragraphs.append(f'**{tier}**')
            paragraphs.extend(f'**{name}** 该机构提供具体的合成服务。' for name in group)
        body = '\n\n'.join(paragraphs)
        rendered = wf.markdown_to_html(body, '合成专题')
        for tier in tiers:
            self.assertIn(f'<strong>{tier}</strong>', rendered)
        for name in NAMES:
            self.assertIn(f'<strong>{name}</strong> 该机构提供具体的合成服务。', rendered)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'article.docx'; wf.write_docx(body, path, '合成专题')
            with zipfile.ZipFile(path) as archive:
                root = ET.fromstring(archive.read('word/document.xml'))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        ps = root.findall('.//w:body/w:p', ns)
        texts = [''.join(p.itertext()) for p in ps]
        for tier in tiers:
            p = ps[texts.index(tier)]
            self.assertIsNotNone(p.find('w:r/w:rPr/w:b', ns))
            self.assertIsNotNone(p.find('w:pPr/w:keepNext', ns))
        for name in NAMES:
            matches = [p for p in ps if ''.join(p.itertext()).startswith(name)]
            self.assertEqual(len(matches), 1)
            p = matches[0]
            self.assertEqual(''.join(p.itertext()), name+' 该机构提供具体的合成服务。')
            bold = [''.join(r.itertext()) for r in p.findall('w:r', ns) if r.find('w:rPr/w:b', ns) is not None]
            self.assertEqual(bold, [name])
            self.assertNotIn(name, texts)
        self.assertEqual(body, '\n\n'.join(paragraphs))


class LegacyRequestIdentityTests(unittest.TestCase):
    def test_v12_prompts_and_request_fingerprints_match_original_release(self):
        # Captured by executing this synthetic fixture with the original v12
        # source and runtime, before running it under the v13 dispatcher.
        expected = {
            'blueprint': ('4931fa9cc516ab0bc912826885dfdd741356e3ce8d16d0eec095ea711080322f', '9681f9ea3e8df1f9a1d16fdd14b90df7cca5d96c8d49be37639341d8c393ce8f'),
            'draft': ('d00420b1929b605dbf22a28c58ea59352cf6c7d860ee7fbc5b478245ec33638e', '97f2b2dfbcd46f139ebc229f275460e3265686742d06e3573975b5bebddbc70e'),
            'edit': ('882f166feac174764f74ee512af378748d169aa4063fa1c75a2e6338f8529d07', '1c970a22d5dc07215d1c8fc735087ff4f596d097671f2218b90d70cfcd7ca8a6'),
            'finalize': ('1f9fb2659bf3c77c28dc8d8842680220733c0386c3c37e45aff46ef9767d80cc', '16e7aecaf9bc587bc7e17191342ae9d38f523996b1ad99836551459f5d19b152'),
            'repair': ('7d1550a0dcdf455c536c72feca9012df7c035713aeee49ea2aa7d6b0805d1ce0', '0233f8b9b1eda038a7c517dea2c0023c4209e6136a2a6feea2e9fe977697865f'),
            'titles': ('376c15ab1c5c6c43219a44ec6fbe5627463cadf9f098624990988a2233220b5a', '78f157348889d01534a605983b10842bcdb0ff476ea6d2f6865c52d331eac0b4'),
            'title_review': ('9d342fe10ca43efcb81e41c88c38e90f95d0c98679636a96512c4b01fb31b69b', '368fefe4d72c716a4a954fe963347226a483f926161e8c577660603290f6cde9'),
        }
        case = legacy.NaturalWritingContextTests(); case.setUp(); self.addCleanup(case.doCleanups)
        c = case.case
        c.put('production/article_editorial_review.json', {'needs_revision': True, 'comments': ['固定合成编辑意见。']})
        c.put('production/article_finalized.json', {'outcome': 'accepted', 'article_markdown': c.body})
        c.put('production/article_titles.json', {'candidates': [{'title': f'合成甲服务介绍{i:02}', 'angle': '业务'} for i in range(20)], 'canonical_title_id': 'title_01'})
        for stage, builder in [('blueprint', writing_context.prompt_blueprint), ('draft', writing_context.prompt_article),
                               ('edit', writing_context.prompt_edit), ('finalize', writing_context.prompt_finalize),
                               ('repair', writing_context.prompt_repair), ('titles', writing_context.prompt_titles),
                               ('title_review', writing_context.prompt_title_review)]:
            prompt = builder(c.wf, c.job, p0=False)
            actual = (hashlib.sha256(prompt.encode()).hexdigest(),
                      model_runtime.request_fingerprint('article_'+stage, prompt, offline=True))
            self.assertEqual(actual, expected[stage], stage)


if __name__ == '__main__':
    unittest.main()
