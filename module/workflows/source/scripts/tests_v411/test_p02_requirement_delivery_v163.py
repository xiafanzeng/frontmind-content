"""New scope submissions use the existing selection route; Pack output is explicit."""
import copy
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_selection_expression_v163 as selection
from scripts.tests_v411 import test_title_input_scope_final13 as flow
from shared import p02_selection as p2, writing_requirements as requirements


class RequirementScopeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = selection.SelectionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.job = self.fixture.job
        self.record = self.fixture.select()
        self.names = [item['name'] for item in self.record['entities']]
        self.blueprint = {'kind': 'article', 'pattern_id': 'P02',
                          'question': '英国硕士申请机构推荐', 'article_brief': '英国硕士申请服务介绍。',
                          'opening': '从申请需求进入。', 'ending': '介绍最后一家后收束。',
                          'sections': [{'heading': '机构特点', 'task': '展开三家各自业务。'}],
                          'candidate_order': self.names, 'estimated_length': '3000字',
                          'writing_material_markdown': '合成企业提供申请服务。',
                          'writing_material_sources': ['inputs/material.md'], 'example_use': '自然组织介绍。'}
        wf.atomic_json(self.job / 'blueprints/article_blueprint.json', self.blueprint)
        state = wf.load_state(self.job)
        # This fixture resumes an already-completed v16.3 article. Its prior
        # intake has no v16.4 article-pool or positioning-handoff contract.
        state['metadata'].pop('article_pool_policy', None)
        state['metadata'].pop('question_positioning_handoff', None)
        state['question']['answers'] = []
        state['status'] = 'completed'
        state['decisions']['question_positioning_confirmation'] = {'confirmed': True, 'p02_selection_hash': self.record['selection_hash']}
        state['decisions']['blueprint_confirmation'] = {'confirmed': True}
        wf.save_state(self.job, state)
        self.original_binding = copy.deepcopy(state['reference_pack'])
        self.original_pack = Path(state['reference_pack']['path']).read_bytes()
        self.core = self.job / 'positioning/core_positioning.json'
        self.core.write_text('{"core":"previously confirmed"}')

    def submit(self, changes, flag='--manuscript-edits', extra=()):
        request = self.job / 'inputs/new-edit.txt'
        request.write_text('按本次新的范围要求重新组织正文。')
        change_file = self.job / 'inputs/new-requirements.json'
        change_file.write_text(json.dumps(changes, ensure_ascii=False))
        state = wf.load_state(self.job)
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', str(state['revision']),
                                      flag, str(request), '--writing-requirements', str(change_file), *extra])
        # Upstream provenance is an independent, already-tested gate; this
        # fixture exercises actual snapshotting, requirements and routing.
        with patch.object(wf.manuscript_revision, 'validate_completed_manuscript', return_value={'base_markdown': '旧正文'}), \
             patch.object(wf, 'drive', return_value=0) as drive, \
             patch.object(wf, 'clear_core_result', side_effect=AssertionError('must preserve P0/core')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wf.continue_workflow(args), 0)
        return drive

    def assert_reselection(self, changes):
        state = wf.load_state(self.job)
        self.assertEqual(state['status'], 'running_question_positioning')
        self.assertIsNone(p2.current(state))
        self.assertEqual(state['metadata']['p02_scope_requirements'], changes)
        for key, value in changes.items():
            self.assertEqual(state['metadata']['effective_writing_requirements'][key], value)
        self.assertNotIn('question_positioning_confirmation', state['decisions'])
        self.assertNotIn('article_production_step', state['flags'])
        self.assertNotIn('article_manuscript_revision', state['metadata'])
        self.assertEqual(state['reference_pack'], self.original_binding)
        self.assertEqual(Path(self.original_binding['path']).read_bytes(), self.original_pack)
        self.assertEqual(self.core.read_text(), '{"core":"previously confirmed"}')
        snapshot = Path(state['metadata']['writing_reruns'][-1]['archive_path'])
        self.assertEqual(wf.read_json(snapshot / 'blueprints/article_blueprint.json'), self.blueprint)
        self.assertNotIn('p02_scope_requirements', wf.load_state(snapshot)['metadata'])
        # The real next step enters research/selection, rather than running a
        # body writer with the previous three entities.
        self.assertFalse(p2.ensure_ready(wf, self.job))
        current = wf.load_state(self.job)
        self.assertEqual(current['status'], 'running_positioning_market_research')
        self.assertEqual(current['metadata']['p02_selection_pending'], p2.scope(current))

    def test_explicit_new_names_are_saved_and_reselected_before_manuscript_edit(self):
        changes = {'candidate_order': ['自己机构', '新甲', '新乙']}
        self.submit(changes)
        self.assert_reselection(changes)
        state = wf.load_state(self.job)
        self.assertIsNone(p2.current(state))  # Supplying order is not confirmation.
        new = [selection.candidate('新甲'), selection.candidate('新乙')]
        fresh = p2.freeze(wf, self.job, {'comparison_targets': new, 'peer_examples': []})
        self.assertEqual(fresh['scope'], p2.scope(wf.load_state(self.job)))
        self.assertEqual(requirements.effective(wf, self.job, p0=False)['candidate_order'], changes['candidate_order'])

    def test_article_brief_change_routes_blueprint_revision_through_reselection(self):
        changes = {'article_brief': '改为介绍伦敦院校申请服务及对应机构。'}
        self.submit(changes, '--blueprint-edits')
        self.assert_reselection(changes)

    def test_recommendation_scope_change_is_not_ignored(self):
        changes = {'recommendation_relationships': '改为围绕艺术专业申请选取机构。'}
        self.submit(changes)
        self.assert_reselection(changes)

    def test_format_length_and_identical_scope_do_not_invalidate_selection(self):
        for changes in ({'estimated_length': '3200字', 'formatting': '机构名加粗'},
                        {'candidate_order': self.names},
                        {'article_brief': self.blueprint['article_brief']}):
            self.assertEqual(requirements.p02_scope_changes(wf, self.job, changes), {})
        self.assertEqual(p2.current(wf.load_state(self.job))['selection_hash'], self.record['selection_hash'])

    def test_malformed_explicit_order_is_rejected_before_snapshot_or_state_mutation(self):
        before = (self.job / 'job_state.json').read_bytes()
        with self.assertRaises(ValueError):
            self.submit({'candidate_order': '自己机构、新甲、新乙'})
        self.assertEqual((self.job / 'job_state.json').read_bytes(), before)
        self.assertFalse(wf.load_state(self.job)['metadata'].get('writing_reruns'))

    def test_historical_jobs_do_not_acquire_new_scope_requirements(self):
        state = wf.load_state(self.job)
        state['metadata'].pop('p02_selection_policy')
        wf.save_state(self.job, state)
        self.assertEqual(requirements.p02_scope_changes(wf, self.job, {'candidate_order': ['历史甲', '历史乙']}), {})
        self.assertNotIn('p02_scope_requirements', wf.load_state(self.job)['metadata'])

    def test_scope_change_preserves_supplement_and_failed_example_confirmation(self):
        state = wf.load_state(self.job)
        state['selected_example_route'] = 'A'
        wf.save_state(self.job, state)
        supplement = self.job / 'inputs/new-facts.md'
        supplement.write_text('本次范围补充事实。')

        def failed_acquisition(args, job, *, p0):
            state = wf.load_state(job)
            state['metadata']['example_acquisition_errors'] = ['合成获取失败']
            wf.save_state(job, state)

        changes = {'candidate_order': ['自己机构', '新甲', '新乙']}
        with patch.object(wf, 'ingest_supplied_examples', side_effect=failed_acquisition):
            drive = self.submit(changes, '--blueprint-edits',
                ('--example-url', 'https://example.com/reference', '--blueprint-supplement', str(supplement)))
        drive.assert_not_called()
        state = wf.load_state(self.job)
        self.assertEqual(state['status'], 'awaiting_example_confirmation')
        self.assertEqual(state['metadata']['p02_scope_requirements'], changes)
        self.assertIsNone(p2.current(state))
        items = wf.read_json(self.job / 'inputs/user_materials/index.json')['items']
        self.assertEqual((self.job / items[0]['path']).read_text(), supplement.read_text())
        args = wf.parser().parse_args(['continue', '--job-dir', str(self.job),
            '--revision', str(state['revision']), '--example-route', 'B'])
        with patch.object(wf, 'drive', return_value=0):
            wf.continue_workflow(args)
        self.assertEqual(wf.load_state(self.job)['status'], 'running_question_positioning')
        self.assertFalse(p2.ensure_ready(wf, self.job))

    def test_scope_change_keeps_existing_example_route_after_success(self):
        state = wf.load_state(self.job)
        state['selected_example_route'] = 'A'
        state['flags']['offline_fixture'] = False  # Exercise local-file acquisition.
        wf.save_state(self.job, state)
        example = self.job / 'inputs/example.md'
        example.write_text('# 新例文\n\n' + '用具体内容展开服务介绍。' * 20)
        changes = {'candidate_order': ['自己机构', '新甲', '新乙']}
        drive = self.submit(changes, '--blueprint-edits', ('--example-file', str(example)))
        drive.assert_called_once_with(self.job.resolve())
        self.assert_reselection(changes)
        state = wf.load_state(self.job)
        self.assertEqual(state['decisions']['example_route']['route'], 'A')
        self.assertEqual(len(wf.load_examples(self.job, 'question')), 1)


class PackDeliveryTests(unittest.TestCase):
    setUp = flow.TitleInputScopeTests.setUp
    job = flow.TitleInputScopeTests.job
    step = flow.TitleInputScopeTests.step
    until = flow.TitleInputScopeTests.until

    def test_completed_payload_exposes_latest_selection_pack_and_retains_source_binding(self):
        job = self.job()
        self.until(job, 'deliver')
        state = wf.load_state(job)
        original = copy.deepcopy(state['reference_pack'])
        latest = {'pack_id': original['pack_id'], 'pack_version': original['pack_version'] + 1,
                  'pack_path': str(job / 'deliverables/selection-pack'),
                  'portable_zip_path': str(job / 'deliverables/selection-pack.zip'),
                  'readiness': {'p0_ready': True}, 'portable_zip_sha256': 'sha256:synthetic'}
        state['metadata']['p02_reference_pack_delivery'] = latest
        state['metadata']['reference_pack_delivery'] = {'p0': 'existing provenance'}
        wf.save_state(job, state)
        with patch.object(wf, 'emit_completed_delivery', return_value=0) as emit:
            self.step(job)
        payload = emit.call_args.args[0]
        self.assertEqual(payload['p02_reference_pack_delivery'], latest)
        self.assertEqual(payload['reference_pack']['pack_version'], latest['pack_version'])
        self.assertEqual(payload['reference_pack']['portable_zip'], latest['portable_zip_path'])
        self.assertEqual(payload['reference_pack']['path'], latest['pack_path'])
        self.assertEqual(payload['source_reference_pack'], {key: original[key] for key in ('pack_id', 'pack_version')})
        after = wf.load_state(job)
        self.assertEqual(after['reference_pack'], original)
        self.assertEqual(after['metadata']['reference_pack_delivery'], {'p0': 'existing provenance'})

    def test_completion_without_selection_pack_preserves_previous_payload(self):
        job = self.job()
        self.until(job, 'deliver')
        state = wf.load_state(job)
        with patch.object(wf, 'emit_completed_delivery', return_value=0) as emit:
            self.step(job)
        payload = emit.call_args.args[0]
        self.assertNotIn('p02_reference_pack_delivery', payload)
        self.assertNotIn('source_reference_pack', payload)
        self.assertEqual(payload['reference_pack'], {key: state['reference_pack'][key] for key in ('pack_id', 'pack_version')})


if __name__ == '__main__':
    unittest.main()
