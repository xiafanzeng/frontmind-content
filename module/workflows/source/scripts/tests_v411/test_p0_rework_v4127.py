"""Synthetic rejected-body recovery tests; no paid APIs and no quality scoring."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from shared import brand_references as br, brand_stage as bs, reader_editing as reader
from shared import prose_only as po, model_runtime as rt, p0_rework as rw
from shared import editorial_contracts as ec, writing_context as wc
from scripts.tests_v411.test_reader_editing_v4127 import make_job, BODY, BAD, CLEAN, REASON
from scripts.tests_v411.test_model_runtime import stream, FakeTools
from scripts.tests_v411.test_managed_runtime_v4123 import ManagedServer

ROOT = Path(__file__).resolve().parents[2]


class P0ReworkTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        # macOS tempdirs are reached through a /var -> /private/var symlink; the
        # workflow resolves job paths, so fixtures must start from the resolved
        # form or path-equality assertions fail on this platform.
        self.job = (Path(tmp.name) / 'job').resolve()
        self.state, self.bp = make_job(self.job, rejected=True)
        br.job_examples(ROOT, self.job, freeze=True)  # Explicit synthetic resource fixture.
        state = wf.load_state(self.job)
        state['metadata']['p0_production_bindings'] = {s: wf.production_signature(self.job, 'p0', s) for s in ('draft', 'edit', 'style')}
        wf.save_state(self.job, state)
        self.upstream = {name: (self.job / name).read_bytes() for name in ('blueprints/p0_blueprint.json', 'production/p0_draft.json', 'production/p0_edited.json')}

    def args(self, *extra, revision=None):
        if revision is None: revision = wf.load_state(self.job)['revision']
        return wf.parser().parse_args(['continue', '--job-dir', str(self.job), '--revision', str(revision), *extra])

    def begin(self, route='style'):
        with patch.object(wf, 'drive', return_value=31) as drive:
            self.assertEqual(wf.continue_workflow(self.args('--p0-rework', route)), 31)
        drive.assert_called_once_with(self.job)
        return wf.load_state(self.job)

    def ensure(self, job_root, action, prompt, **kwargs):
        if action == 'p0_edit':
            return dict(article_markdown=CLEAN, edit_status='revised', editorial_notes=['仅模拟替换测试候选'], requires_blueprint_reconfirmation=False, reconfirmation_reason='')
        if action == 'p0_style':
            return {'article_markdown': CLEAN}
        if action == 'p0_finalize':
            return dict(outcome='accepted', article_markdown=CLEAN, editorial_notes=[], reason='')
        raise AssertionError('unexpected action: ' + action)

    def test_style_repair_archives_exact_candidate_and_reason_without_resetting_e8(self):
        original = wf.load_state(self.job)
        state = self.begin('style')
        self.assertEqual(state['revision'], 8); self.assertIsNone(state['pending_action'])
        self.assertEqual(state['flags']['p0_production_step'], 'style')
        for name, content in self.upstream.items(): self.assertEqual((self.job / name).read_bytes(), content)
        for stage in ('draft', 'edit'):
            self.assertEqual(state['metadata']['p0_production_bindings'][stage], original['metadata']['p0_production_bindings'][stage])
        self.assertNotIn('style', state['metadata']['p0_production_bindings'])
        history = state['metadata']['p0_quality_rework_history'][-1]
        self.assertEqual(wf.read_json(self.job / history['candidate_path']), {'article_markdown': BAD})
        self.assertEqual(wf.read_json(self.job / history['result_path'])['reason'], REASON)
        self.assertEqual(history['result_sha256'], wf.sha256_file(self.job / history['result_path']))
        self.assertEqual(rw.current(wf, self.job, 'style')['candidate_markdown'], BAD)
        _prompt = bs.style_prompt(wf, self.job)
        self.assertIn('基稿开头两段已按返工规则删除', _prompt)
        self.assertIn('## 合成业务', _prompt); self.assertIn(REASON, _prompt)
        self.assertNotIn(BAD.split('\n\n## ')[0], _prompt)
        self.assertEqual(bs.style_prompt(wf, self.job).count('<reference_text>'), 2)
        self.assertFalse(wf.action_paths(self.job, 'p0_finalize')[2].exists())
        self.assertNotIn('retry_current_action', state['flags'])

    def test_style_repair_driver_calls_only_style_and_finalize_before_titles(self):
        self.begin()
        with patch.object(wf, 'ensure_action', side_effect=self.ensure) as provider:
            self.assertIsNone(wf.run_production(self.job, p0=True))
            self.assertIsNone(wf.run_production(self.job, p0=True))
        self.assertEqual([c.args[1] for c in provider.call_args_list], ['p0_style', 'p0_finalize'])
        self.assertEqual(wf.load_state(self.job)['flags']['p0_production_step'], 'titles')
        self.assertEqual(wf.read_json(self.job / 'production/p0_finalized.json')['article_markdown'], CLEAN)
        for name, content in self.upstream.items(): self.assertEqual((self.job / name).read_bytes(), content)

    def test_edit_repair_uses_rejected_candidate_as_e8_base_and_then_real_new_e8(self):
        self.begin('edit')
        self.assertEqual(ec.edit_base_input(wf, self.job, p0=True)['article_markdown'], BAD)
        self.assertIn(REASON, bs.edit_prompt(wf, self.job))
        with patch.object(wf, 'ensure_action', side_effect=self.ensure) as provider:
            for _ in range(3): self.assertIsNone(wf.run_production(self.job, p0=True))
        self.assertEqual([c.args[1] for c in provider.call_args_list], ['p0_edit', 'p0_style', 'p0_finalize'])
        self.assertIn(CLEAN, provider.call_args_list[1].args[2])
        self.assertEqual((self.job / 'production/p0_draft.json').read_bytes(), self.upstream['production/p0_draft.json'])
        self.assertEqual(wf.load_state(self.job)['flags']['p0_production_step'], 'titles')

    def test_later_style_repair_does_not_erase_previous_e8_repair_input(self):
        self.begin('edit')
        with patch.object(wf, 'ensure_action', side_effect=self.ensure):
            wf.run_production(self.job, p0=True); wf.run_production(self.job, p0=True)
        prior_edit = wf.production_signature(self.job, 'p0', 'edit')
        prior_prompt = bs.edit_prompt(wf, self.job)
        state = wf.load_state(self.job)
        state['pending_action'] = {'action':'p0_finalize','error':{'code':'host_incomplete','message':'测试第二次拒稿'}}
        wf.save_state(self.job, state)
        wf.atomic_json(wf.action_paths(self.job, 'p0_finalize')[2], dict(outcome='incomplete', article_markdown='', editorial_notes=[], reason='测试第二次拒稿。'))
        self.begin('style')
        self.assertEqual(wf.production_signature(self.job, 'p0', 'edit'), prior_edit)
        self.assertEqual(bs.edit_prompt(wf, self.job), prior_prompt)
        self.assertEqual(rw.current(wf, self.job, 'edit')['candidate_markdown'], BAD)
        self.assertEqual(rw.current(wf, self.job, 'style')['candidate_markdown'], CLEAN)
        with patch.object(wf, 'ensure_action', side_effect=self.ensure) as provider:
            wf.run_production(self.job, p0=True)
        self.assertEqual(provider.call_args.args[1], 'p0_style')

    def test_new_request_epoch_invalidates_downstream_not_upstream_context(self):
        old = {a: rt.context_fingerprint(self.job, a) for a in ('p0_blueprint', 'p0_draft', 'p0_edit', 'p0_style', 'p0_finalize', 'p0_titles', 'p0_title_review')}
        self.begin('style')
        for action in ('p0_blueprint', 'p0_draft', 'p0_edit'):
            self.assertEqual(old[action], rt.context_fingerprint(self.job, action))
        for action in ('p0_style', 'p0_finalize', 'p0_titles', 'p0_title_review'):
            self.assertNotEqual(old[action], rt.context_fingerprint(self.job, action))

    def test_stale_or_mixed_request_never_changes_state_or_rejection(self):
        before = (self.job / 'job_state.json').read_bytes()
        rejected = wf.action_paths(self.job, 'p0_finalize')[2].read_bytes()
        args = [self.args('--p0-rework','style',revision=6), self.args('--p0-rework','style','--retry-current-action'),
                self.args('--p0-rework','edit','--p0-blueprint-edits','改变任务'), self.args('--p0-rework','style','--accept-p0-blueprint')]
        for a in args:
            with self.subTest(args=a), patch.object(wf, 'drive') as driver:
                with self.assertRaises(wf.WorkflowError): wf.continue_workflow(a)
                driver.assert_not_called()
                self.assertEqual((self.job / 'job_state.json').read_bytes(), before)
                self.assertEqual(wf.action_paths(self.job, 'p0_finalize')[2].read_bytes(), rejected)

    def test_only_incomplete_current_prose_jobs_can_use_repair(self):
        for outcome in ('accepted', 'requires_blueprint_reconfirmation'):
            body = BAD if outcome == 'accepted' else ''
            wf.atomic_json(wf.action_paths(self.job, 'p0_finalize')[2], dict(outcome=outcome, article_markdown=body, editorial_notes=[], reason='' if body else REASON))
            with self.assertRaises(wf.WorkflowError):
                wf.continue_workflow(self.args('--p0-rework','style'))
        self.assertNotIn(rw.POINTERS, wf.load_state(self.job)['metadata'])

    def test_current_four_field_result_does_not_need_brand_review(self):
        self.assertEqual(set(rw.rejected_input(wf, self.job)['result']), {'outcome','article_markdown','editorial_notes','reason'})
        state = wf.load_state(self.job); state['metadata']['p0_style_contract'] = po.CONTRACT; wf.save_state(self.job,state)
        self.begin('style')
        self.assertEqual(rw.current(wf, self.job, 'style')['job_contract'], po.CONTRACT)
        self.assertTrue(bs.style_prompt(wf, self.job).startswith(po.MARKER + '\n'))

    def test_four_field_blueprint_rework_works_for_4126_and_4127(self):
        for contract in (po.CONTRACT, reader.CONTRACT):
            with self.subTest(contract=contract), tempfile.TemporaryDirectory() as tmp:
                job = Path(tmp) / 'job'; make_job(job, contract=contract, rejected=True)
                args = wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--p0-blueprint-edits','保留业务决定，重新整理本篇原件。'])
                with patch.object(wf,'drive',return_value=11): self.assertEqual(wf.continue_workflow(args),11)
                state=wf.load_state(job)
                self.assertEqual(state['status'],'running_p0_blueprint')
                self.assertEqual(state['metadata']['p0_quality_rework_history'][-1]['requested_route'],'blueprint_edits')
                self.assertEqual(wf.read_json(job / state['metadata']['p0_quality_rework_history'][-1]['candidate_path'])['article_markdown'],BAD)
                self.assertNotIn('p0_blueprint_confirmation',state['decisions'])

    def test_four_field_material_supplement_routes_to_existing_blueprint(self):
        with patch.object(wf,'drive',return_value=12):
            self.assertEqual(wf.continue_workflow(self.args('--p0-blueprint-supplement','合成新增原件，仅用于测试。')),12)
        state=wf.load_state(self.job)
        self.assertEqual(state['status'],'running_p0_blueprint')
        self.assertEqual(state['metadata']['p0_quality_rework_history'][-1]['requested_route'],'blueprint_supplement')

    def test_frozen_record_tampering_fails_without_silently_reusing_old_e8(self):
        state=self.begin()
        path=self.job/state['metadata'][rw.POINTERS]['style']['path']
        path.write_text(path.read_text()+' ')
        with self.assertRaises(ec.EditorialContractError): bs.style_prompt(wf,self.job)

    def test_upstream_change_invalidates_repair(self):
        self.begin()
        path=self.job/'production/p0_edited.json'; value=wf.read_json(path); value['article_markdown']=CLEAN; wf.atomic_json(path,value)
        with self.assertRaises(ec.EditorialContractError): rw.current(wf,self.job,'style')

    def test_explicit_upstream_reset_clears_inputs_but_preserves_history(self):
        self.begin('edit')
        history=copy.deepcopy(wf.load_state(self.job)['metadata']['p0_quality_rework_history'])
        wf.invalidate_action(self.job,'p0_blueprint')
        self.assertNotIn(rw.POINTERS,wf.load_state(self.job)['metadata'])
        self.assertEqual(wf.load_state(self.job)['metadata']['p0_quality_rework_history'],history)
        self.assertIsNone(rw.current(wf,self.job,'edit'))

    def test_normal_resume_does_not_silently_author_a_repair(self):
        with patch.object(wf,'drive',return_value=17): wf.continue_workflow(self.args())
        self.assertNotIn(rw.POINTERS,wf.load_state(self.job)['metadata'])
        self.assertEqual(wf.read_json(self.job/'production/p0_styled.json')['article_markdown'],BAD)

    def test_missing_production_evidence_is_not_treated_as_a_real_run(self):
        state=wf.load_state(self.job);state['flags']['offline_fixture']=False;wf.save_state(self.job,state)
        with self.assertRaises(Exception): rw.begin(wf,self.job,'style')
        self.assertNotIn(rw.POINTERS,wf.load_state(self.job)['metadata'])
        self.assertFalse((self.job/'production/quality_rejections').exists())

    def test_same_native_rejection_is_cached_but_repaired_candidate_gets_new_review(self):
        legacy=rt.legacy_managed_routes();legacy.__enter__();self.addCleanup(legacy.__exit__,None,None,None)
        tools=FakeTools()
        reject=dict(outcome='incomplete',article_markdown='',editorial_notes=[],reason=REASON)
        server=ManagedServer(result=reject)
        prompt=bs.finalize_prompt(wf,self.job)
        validator=lambda v:wf.validate_action_result(self.job,'p0_finalize',v)
        first=rt.run_action(ROOT,self.job,'p0_finalize',prompt,validator,host_tools=tools,transport=server,offline=True)
        calls=len(server.calls)
        again=rt.run_action(ROOT,self.job,'p0_finalize',prompt,validator,host_tools=tools,transport=server,offline=True)
        self.assertEqual(first,again);self.assertEqual(calls,len(server.calls))
        self.begin('style')
        # Real transport adapter under an explicit offline stream, not host authorship.
        new_prompt=bs.style_prompt(wf,self.job)
        def author(profile,key,payload): return stream(content=CLEAN)
        styled=rt.run_action(ROOT,self.job,'p0_style',new_prompt,lambda v:wf.validate_action_result(self.job,'p0_style',v),transport=author,offline=True)
        wf.atomic_json(self.job/'production/p0_styled.json',styled)
        accepted=dict(outcome='accepted',article_markdown=CLEAN,editorial_notes=[],reason='')
        fresh=ManagedServer(result=accepted)
        final=rt.run_action(ROOT,self.job,'p0_finalize',bs.finalize_prompt(wf,self.job),validator,host_tools=FakeTools(),transport=fresh,offline=True)
        self.assertEqual(final,accepted);self.assertGreater(len(fresh.calls),0)
        self.assertEqual(len(list((self.job/'provider/p0_finalize/runtime/attempts').iterdir())),2)


if __name__=='__main__': unittest.main()
