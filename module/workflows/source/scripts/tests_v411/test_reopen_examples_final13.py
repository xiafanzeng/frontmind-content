"""Explicit replacement examples on completed blueprint revisions.

All articles and HTTP responses are synthetic. These exercise acquisition and
controller ordering, not model prose quality or external provider execution.
"""
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from shared import example_acquisition, manuscript_revision, recommendation_references

ROOT = Path(__file__).resolve().parents[2]


class ReopenExamplesTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp
    job = flow.NaturalEditorFlowTests.job
    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def p01_job(self, *, completed=True, route='A'):
        job = self.job()
        state = wf.load_state(job)
        state['selected_pattern_id'] = 'P01'
        state['selected_example_route'] = route
        state['question']['answers'] = []
        state['decisions']['example_route'] = {'route': route, 'confirmed_at': 'original'}
        wf.save_state(job, state)
        blueprint = wf.read_json(job/'blueprints/article_blueprint.json')
        blueprint['pattern_id'] = 'P01'
        wf.atomic_json(job/'blueprints/article_blueprint.json', blueprint)
        wf.save_examples(job, [{'title': '原例文', 'markdown': '原例文完整内容，仅用于旧稿。'}], 'question')
        if completed:
            self.finish(job)
        return job

    def args(self, job, *, urls=None, extra=()):
        values = ['continue', '--job-dir', str(job), '--revision', str(wf.load_state(job)['revision']),
                  '--blueprint-edits', '当前新委托：按新例文重新构思正文。', '--upgrade-writing-editor']
        for url in urls or self.urls():
            values += ['--example-url', url]
        return wf.parser().parse_args(values + list(extra))

    @staticmethod
    def urls():
        return [row['url'] for row in wf.read_json(ROOT/'resources/p01_recommendation/manifest.json')['examples']]

    @staticmethod
    def inventory(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    @staticmethod
    def register_synthetic_pair(module, package, job):
        return module.save_examples(job, [
            {'title': '新主例文', 'markdown': '新主例文全文。', 'reference_role': 'style_primary'},
            {'title': '新辅助例文', 'markdown': '新辅助例文全文。', 'reference_role': 'style_secondary'}], 'question')

    def test_completed_reopen_validates_and_snapshots_old_examples_before_acquisition(self):
        job = self.p01_job()
        before = self.inventory(job)
        events = []
        validate = manuscript_revision.validate_completed_manuscript
        snapshot = wf.snapshot_completed_job_for_writing

        def check_source(*args, **kwargs):
            self.assertEqual(self.inventory(job), before)
            result = validate(*args, **kwargs)
            events.append('validate')
            return result

        def copy_source(*args, **kwargs):
            self.assertEqual(events, ['validate'])
            self.assertEqual(self.inventory(job), before)
            result = snapshot(*args, **kwargs)
            self.assertEqual(self.inventory(Path(result['archive_path'])), before)
            events.append('snapshot')
            return result

        def acquire(*args):
            self.assertEqual(events, ['validate', 'snapshot'])
            events.append('acquire')
            return self.register_synthetic_pair(*args)

        dispatched = []
        def drive(target):
            self.assertEqual(events, ['validate', 'snapshot', 'acquire'])
            dispatched.append(wf.load_state(target)['status'])
            self.assertIn('当前新委托', wf.load_state(target)['decisions']['blueprint_edits'])
            self.assertEqual([r['title'] for r in wf.load_examples(target, 'question')], ['新主例文', '新辅助例文'])
            return 0

        with patch.object(manuscript_revision, 'validate_completed_manuscript', side_effect=check_source), \
             patch.object(wf, 'snapshot_completed_job_for_writing', side_effect=copy_source), \
             patch.object(recommendation_references, 'register', side_effect=acquire), \
             patch.object(wf, 'drive', side_effect=drive), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wf.continue_workflow(self.args(job)), 0)
        self.assertEqual(dispatched, ['running_article_blueprint'])
        state = wf.load_state(job)
        self.assertEqual(state['selected_example_route'], 'A')
        self.assertEqual(state['decisions']['example_route']['route'], 'A')
        self.assertEqual((job/'production/article_finalized.json').read_bytes(), before['production/article_finalized.json'])
        self.assertEqual(len(state['metadata']['writing_reruns']), 1)

    def test_changed_final_never_replaces_examples_or_snapshots(self):
        job = self.p01_job()
        delivery = wf.load_state(job)['metadata']['delivery']
        Path(delivery['markdown']).write_text('Changed outside the completed chain')
        before = self.inventory(job)
        with patch.object(recommendation_references, 'register') as acquire, \
             patch.object(wf, 'snapshot_completed_job_for_writing') as snapshot, \
             patch.object(wf, 'drive') as drive:
            with self.assertRaises((ValueError, wf.WorkflowError)):
                wf.continue_workflow(self.args(job))
            acquire.assert_not_called(); snapshot.assert_not_called(); drive.assert_not_called()
        self.assertEqual(self.inventory(job), before)

    def test_failed_acquisition_uses_existing_example_page_and_keeps_new_commission(self):
        job = self.p01_job()
        supplement = self.root/'new-facts.md'
        supplement.write_text('NEW_FACTS_WITH_EXAMPLE_REPLACEMENT')
        with patch.object(recommendation_references, 'register', side_effect=example_acquisition.AcquisitionError('synthetic HTTP failure')), \
             patch.object(wf, 'drive') as drive, contextlib.redirect_stdout(io.StringIO()):
            wf.continue_workflow(self.args(job, extra=('--blueprint-supplement', str(supplement))))
            drive.assert_not_called()
        state = wf.load_state(job)
        self.assertEqual(state['status'], 'awaiting_example_confirmation')
        self.assertIn('当前新委托', state['decisions']['blueprint_edits'])
        self.assertTrue(state['metadata']['example_acquisition_errors'])
        self.assertEqual(wf.load_examples(job, 'question'), [])
        entries = wf.read_json(job/'inputs/user_materials/index.json')['items']
        self.assertEqual(len(entries), 1)
        self.assertEqual((job/entries[0]['path']).read_text(), supplement.read_text())
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(state['revision']), '--example-route', 'B'])
        with patch.object(wf, 'drive', return_value=0) as drive:
            wf.continue_workflow(args)
            drive.assert_called_once_with(job.resolve())
        self.assertEqual(wf.load_state(job)['selected_example_route'], 'B')
        self.assertIn('当前新委托', wf.load_state(job)['decisions']['blueprint_edits'])
        self.assertEqual(wf.read_json(job/'inputs/user_materials/index.json')['items'], entries)
        self.assertIn(entries[0]['path'], wf.prompt_blueprint(job, p0=False))

    def test_previously_selected_b_returns_to_existing_example_page(self):
        job = self.p01_job(route='B')
        with patch.object(recommendation_references, 'register', side_effect=self.register_synthetic_pair), \
             patch.object(wf, 'drive') as drive, contextlib.redirect_stdout(io.StringIO()):
            wf.continue_workflow(self.args(job))
            drive.assert_not_called()
        self.assertEqual(wf.load_state(job)['status'], 'awaiting_example_confirmation')
        self.assertEqual(wf.load_state(job)['selected_example_route'], 'B')

    def test_explicit_pair_uses_registered_encoding_article_region_and_roles(self):
        job = self.p01_job(completed=False)
        state = wf.load_state(job); state['flags']['offline_fixture'] = False; wf.save_state(job, state)
        package = self.root/'portable'
        folder = package/'resources/p01_recommendation'; folder.mkdir(parents=True)
        manifest = wf.read_json(ROOT/'resources/p01_recommendation/manifest.json')
        wf.atomic_json(folder/'manifest.json', manifest)
        responses = {}
        for i, row in enumerate(manifest['examples']):
            responses[row['url']] = (f'<html><title>合成例文{i}</title><body>导航'
                f'<div class="{row["article_tokens"][0]}"><p>完整开始{i}。</p><p>正文结束{i}。</p></div>'
                '<aside>多余页尾</aside></body></html>').encode(row['encoding'])
        fetched = []
        class Response:
            status = 200
            headers = {'Content-Type': 'text/html'}
            def __init__(self, url): self.url = url
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return responses[self.url]
            def geturl(self): return self.url
        def open_http(request, **kwargs):
            fetched.append(request.full_url)
            return Response(request.full_url)
        with patch.object(wf, 'ROOT', package), \
             patch.object(example_acquisition, 'public_url', side_effect=lambda url: url), \
             patch.object(example_acquisition, 'build_opener', return_value=SimpleNamespace(open=open_http)):
            wf.ingest_supplied_examples(self.args(job, urls=list(reversed(self.urls()))), job, p0=False)
        rows = wf.load_examples(job, 'question')
        self.assertEqual(fetched, self.urls())
        self.assertEqual([r['role'] for r in rows], ['style_primary', 'style_secondary'])
        self.assertEqual([r['style_analysis'] for r in rows], [r['style_analysis'] for r in manifest['examples']])
        for i, row in enumerate(rows):
            text = Path(row['path']).read_text()
            self.assertIn(f'完整开始{i}。', text); self.assertIn(f'正文结束{i}。', text)
            self.assertNotIn('导航', text); self.assertNotIn('多余页尾', text); self.assertNotIn('\ufffd', text)

    def test_other_user_reference_uses_original_file_acquisition(self):
        job = self.p01_job(completed=False)
        state = wf.load_state(job); state['flags']['offline_fixture'] = False; wf.save_state(job, state)
        example = self.root/'user-example.md'; example.write_text('# 用户自己的例文\n\n正文开始。正文结束。')
        args = SimpleNamespace(example_file=[example], example_url=[])
        with patch.object(recommendation_references, 'register', side_effect=AssertionError('not the confirmed pair')):
            wf.ingest_supplied_examples(args, job, p0=False)
        rows = wf.load_examples(job, 'question')
        self.assertEqual(len(rows), 1)
        self.assertEqual(Path(rows[0]['path']).read_text().strip(), example.read_text().strip())
        self.assertEqual(rows[0]['role'], '文风参考')
        self.assertTrue(wf.load_state(job)['metadata']['examples_user_specified'])


if __name__ == '__main__':
    unittest.main()
