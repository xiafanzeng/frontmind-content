"""Focused offline checks for revising a completed manuscript, never paid calls."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.tests_v411 import test_controller_runtime_v4114 as integration
from shared import editorial_contracts as contracts, manuscript_revision as revisions
wf = integration.wf


class ManuscriptRevisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=integration.ControllerRuntimeIntegration();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.base
        self.request=self.root/'edits.md';self.request.write_text('仅删除旁白和拔高总结，保留已自然的事实与段落。')
        self.pack_roots={}
        self.addCleanup(patch.stopall)
        patch.object(wf,'validate_reference_pack',return_value={'status':'pass','readiness':{'p0_ready':True}}).start()
        patch.object(wf,'reference_pack_root',side_effect=lambda path:self.pack_roots[str(Path(path).resolve())]).start()
        patch.object(wf,'read_reference_member',side_effect=lambda path,member:self.fixture.final.encode()).start()

    def completed(self,prefix):
        job=self.fixture.job(prefix);state=wf.load_state(job)
        state.update(status='p0_ready' if prefix=='p0' else 'completed',p0_route='generate')
        state['flags']={'offline_fixture':True}
        state['decisions'][prefix+'_blueprint_confirmation']={'revision':7,'confirmed_at':'original-confirmation'}
        original_pack=job/'00_input/reference_pack.zip';original_pack.parent.mkdir();original_pack.write_text('original input pack v3')
        state['reference_pack'].update(path=str(original_pack),pack_version=3)
        wf.save_state(job,state)
        draft={'article_markdown':self.fixture.draft,'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''}
        edit={**draft,'edit_status':'accepted','editorial_notes':[]}
        final={'outcome':'revised','article_markdown':self.fixture.final,'editorial_notes':['原终审已改写开篇。'],'reason':''}
        titles={'families':{'decision_search':[{'title':f'品牌服务{i}'} for i in range(10)],'media_pr':[{'title':f'项目业务{i}'} for i in range(10)]}}
        for name,value in [('draft',draft),('edited',edit),('finalized',final),('titles',titles),
                           ('final_source',{'source':'offline_fixture','body_sha256':revisions.text_hash(self.fixture.final)})]:
            wf.atomic_json(job/'production'/f'{prefix}_{name}.json',value)
        delivery=wf.deliver_article(job,self.fixture.final,titles,prefix=prefix,legacy=True)
        state=wf.load_state(job);state['metadata']['delivery']=delivery
        if prefix=='p0':
            latest=job/'deliverables/Reference_Pack_v4.zip';latest.write_text('most recent delivered v4 with all prior materials')
            state['metadata']['reference_pack_delivery']={'portable_zip_path':str(latest),'portable_zip_sha256':'sha256:'+revisions.file_hash(latest),'pack_id':'synthetic-pack','pack_version':4}
            self.pack_roots[str(latest.resolve())]={'pack_id':'synthetic-pack','pack_version':4}
            self.pack_roots[str(original_pack.resolve())]={'pack_id':'synthetic-pack','pack_version':3}
        wf.save_state(job,state)
        return job

    def args(self,job,*extra):
        return wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(wf.load_state(job)['revision']),*extra])

    def start(self,job):
        with patch.object(wf,'drive',return_value=0):
            return wf.continue_workflow(self.args(job,'--manuscript-edits',str(self.request)))

    def test_title_only_revision_calls_only_titles_and_preserves_body_both_routes(self):
        for prefix in ('p0','article'):
            with self.subTest(prefix=prefix):
                job=self.completed(prefix)
                original={name:(job/f'production/{prefix}_{name}.json').read_bytes() for name in ('draft','edited','finalized')}
                with patch.object(wf,'drive',return_value=0):
                    wf.continue_workflow(self.args(job,'--title-edits',str(self.request)))
                frozen=revisions.current_title_revision(wf,job,p0=prefix=='p0')
                self.assertEqual(frozen['base_markdown'],self.fixture.final)
                self.assertTrue(Path(frozen['source_snapshot']).is_dir())
                self.assertEqual(wf.load_state(job)['flags'][prefix+'_production_step'],'titles')
                titles={'canonical_title_id':'media_title_03' if prefix=='p0' else 'decision_title_04','families':{'decision_search':[{'title':f'业务{i}'} for i in range(10)],'media_pr':[{'title':f'项目{i}'} for i in range(10)]}}
                with patch.object(wf,'ensure_action',return_value=titles) as action:
                    wf.run_production(job,p0=prefix=='p0')
                self.assertEqual(action.call_args.args[1],prefix+'_titles')
                self.assertIn(self.request.read_text(),action.call_args.args[2])
                self.assertIn(wf.title_publication.body_only(self.fixture.final),action.call_args.args[2])
                self.assertEqual(action.call_count,1)
                for name,body in original.items():
                    self.assertEqual((job/f'production/{prefix}_{name}.json').read_bytes(),body)
                if prefix=='p0':
                    self.assertEqual(frozen['source_pack']['pack_version'],4)

    def test_title_only_rejects_conflicting_args_and_changed_base(self):
        job=self.completed('p0')
        with self.assertRaises(wf.WorkflowError):
            wf.continue_workflow(self.args(job,'--title-edits',str(self.request),'--manuscript-edits',str(self.request)))
        with patch.object(wf,'drive',return_value=0):
            wf.continue_workflow(self.args(job,'--title-edits',str(self.request)))
        value=wf.read_json(job/'production/p0_finalized.json');value['article_markdown']+='changed'
        wf.atomic_json(job/'production/p0_finalized.json',value)
        with self.assertRaises(ValueError):
            revisions.current_title_revision(wf,job,p0=True)

    def test_both_routes_freeze_final_request_and_full_snapshot_without_changing_upstream(self):
        for prefix in ('p0','article'):
            with self.subTest(prefix=prefix):
                job=self.completed(prefix);old_state=wf.load_state(job)
                before={p.relative_to(job).as_posix():p.read_bytes() for p in job.rglob('*') if p.is_file()}
                self.assertEqual(self.start(job),0)
                state=wf.load_state(job);frozen=revisions.current_revision(wf,job,p0=prefix=='p0')
                archive=Path(state['metadata']['writing_reruns'][-1]['archive_path'])
                self.assertEqual({p.relative_to(archive).as_posix():p.read_bytes() for p in archive.rglob('*') if p.is_file()},before)
                self.assertEqual(frozen['base_markdown'],self.fixture.final)
                self.assertNotEqual(frozen['base_markdown'],self.fixture.draft)
                self.assertEqual(frozen['edits_markdown'],self.request.read_text())
                self.assertEqual(state['revision'],old_state['revision']+1)
                self.assertEqual(state['flags'][prefix+'_production_step'],'edit')
                self.assertEqual(state['reference_pack'],old_state['reference_pack'])
                self.assertEqual(state['decisions'],old_state['decisions'])
                for name in (f'production/{prefix}_draft.json',f'blueprints/{prefix}_blueprint.json'):
                    self.assertEqual((job/name).read_bytes(),before[name])
                self.assertEqual(self.fixture.payloads,[])

    def test_edit_and_finalize_compare_against_previous_final_and_preserve_original_draft(self):
        job=self.completed('article');self.start(job)
        accepted={'edit_status':'accepted','article_markdown':self.fixture.final,'editorial_notes':[],
                  'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''}
        wf.validate_action_result(job,'article_edit',accepted)
        with self.assertRaises(contracts.EditorialContractError):
            wf.validate_action_result(job,'article_edit',{**accepted,'article_markdown':self.fixture.draft})
        wf.atomic_json(job/'production/article_edited.json',accepted)
        context=contracts.prepare_finalize_input(wf,job,p0=False)
        self.assertEqual(context['draft_markdown'],self.fixture.draft)
        self.assertEqual(context['edit_base_markdown'],self.fixture.final)
        self.assertEqual(context['edit_base_source'],'previous_glm_final')
        self.assertTrue(context['diff']['identical'])
        self.assertEqual(context['diff']['before_sha256'],revisions.text_hash(self.fixture.final))
        (job/'production/article_edited.json').unlink()
        wf.atomic_json(job/'production/article_edit_failure.json',{'code':'invalid_result_json','action':'article_edit'})
        fallback=contracts.prepare_finalize_input(wf,job,p0=False)
        self.assertEqual(fallback['candidate_markdown'],self.fixture.final)
        self.assertEqual(fallback['candidate_source'],'previous_glm_final_after_edit_format_error')

    def test_new_draft_prompt_does_not_restart_upstream_and_empty_continue_stays_readonly(self):
        job=self.completed('article');before=(job/'production/article_draft.json').read_bytes();self.start(job)
        actions=[];real=wf.ensure_action
        def run(*args,**kwargs):
            actions.append(args[1]);return real(*args,**kwargs)
        with patch.object(wf,'ensure_action',side_effect=run),patch.object(wf,'prompt_article',side_effect=AssertionError('draft must not be assembled')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(wf.drive(job),0)
        self.assertEqual(actions,['article_edit','article_finalize','article_titles','article_title_review'])
        self.assertEqual((job/'production/article_draft.json').read_bytes(),before)
        self.assertEqual(wf.load_state(job)['status'],'completed')
        before_state=(job/'job_state.json').read_bytes();counts=len(actions)
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(wf.continue_workflow(self.args(job)),0)
        self.assertEqual((job/'job_state.json').read_bytes(),before_state);self.assertEqual(len(actions),counts)
        self.assertEqual(self.fixture.payloads,[])

    def test_p0_inherits_latest_pack_not_original_input_and_preserves_new_delivery_directory(self):
        job=self.completed('p0');input_binding=wf.load_state(job)['reference_pack'].copy();self.start(job)
        inherited=Path(revisions.current_revision(wf,job,p0=True)['source_pack']['path'])
        captured={}
        def commit(**kwargs):
            captured.update(kwargs)
            return {'readiness':{'p0_ready':True},'pack_version':5,'pack_id':'synthetic-pack'}
        with patch.object(wf,'create_next_reference_pack_version',side_effect=commit):
            result=wf.commit_p0_pack(job,wf.load_state(job)['metadata']['delivery'])
        self.assertEqual(result['pack_version'],5)
        self.assertEqual(captured['pack'],inherited)
        self.assertEqual(captured['output'],wf.writing_delivery_root(job)/'Reference_Pack_v5')
        self.assertEqual(captured['portable_zip'],wf.writing_delivery_root(job)/'Reference_Pack_v5.zip')
        self.assertEqual(wf.load_state(job)['reference_pack'],input_binding)

    def rewritten_p0(self):
        job=self.completed('p0');state=wf.load_state(job)
        latest=state['metadata']['reference_pack_delivery'];latest['pack_version']=5
        self.pack_roots[str(Path(latest['portable_zip_path']).resolve())]['pack_version']=5
        wf.save_state(job,state)
        with patch.object(wf,'drive',return_value=0):
            wf.continue_workflow(self.args(job,'--p0-blueprint-edits','保留业务范围，重新自然叙述。'))
        self.assertNotIn('p0_manuscript_revision',wf.load_state(job)['metadata'])
        return job

    def test_full_p0_rewrite_extends_latest_v5_to_v6_without_rebinding_original_pack(self):
        job=self.rewritten_p0();state=wf.load_state(job);binding=state['reference_pack'].copy()
        latest=Path(state['metadata']['reference_pack_delivery']['portable_zip_path']);before=latest.read_bytes()
        with patch.object(wf,'create_next_reference_pack_version',return_value={'readiness':{'p0_ready':True},'pack_version':6}) as commit:
            result=wf.commit_p0_pack(job,state['metadata']['delivery'])
        self.assertEqual(result['pack_version'],6)
        self.assertEqual(commit.call_args.kwargs['pack'],latest)
        self.assertEqual(commit.call_args.kwargs['portable_zip'],wf.writing_delivery_root(job)/'Reference_Pack_v6.zip')
        p0_record=json.loads(commit.call_args.kwargs['artifacts'][wf.P0_MEMBERS['p0_record']])
        self.assertEqual((p0_record['source_pack_version'],p0_record['pack_version']),(5,6))
        self.assertEqual(wf.load_state(job)['reference_pack'],binding)
        self.assertEqual(latest.read_bytes(),before)
        self.assertTrue(Path(state['metadata']['writing_reruns'][-1]['archive_path']).is_dir())

    def test_full_p0_rewrite_rejects_missing_changed_cross_series_or_wrong_version_pack(self):
        job=self.rewritten_p0();state=wf.load_state(job);saved=json.loads(json.dumps(state));latest=Path(state['metadata']['reference_pack_delivery']['portable_zip_path'])
        original=latest.read_bytes();root=self.pack_roots[str(latest.resolve())].copy()
        cases=('missing_metadata','changed_bytes','other_series','wrong_version')
        for case in cases:
            with self.subTest(case=case):
                state=json.loads(json.dumps(saved));latest.write_bytes(original);self.pack_roots[str(latest.resolve())]=root.copy()
                if case=='missing_metadata':state['metadata'].pop('reference_pack_delivery')
                elif case=='changed_bytes':latest.write_text('changed archive')
                elif case=='other_series':self.pack_roots[str(latest.resolve())]['pack_id']='other-pack'
                else:self.pack_roots[str(latest.resolve())]['pack_version']=4
                wf.save_state(job,state)
                with patch.object(wf,'create_next_reference_pack_version') as commit:
                    with self.assertRaises(wf.WorkflowError):wf.commit_p0_pack(job,state['metadata']['delivery'])
                commit.assert_not_called()

    def test_first_p0_still_extends_original_input_pack(self):
        job=self.completed('p0');state=wf.load_state(job)
        state['metadata'].pop('reference_pack_delivery');wf.save_state(job,state)
        source=Path(state['reference_pack']['path'])
        with patch.object(wf,'create_next_reference_pack_version',return_value={'readiness':{'p0_ready':True},'pack_version':4}) as commit:
            result=wf.commit_p0_pack(job,state['metadata']['delivery'])
        self.assertEqual(result['pack_version'],4);self.assertEqual(commit.call_args.kwargs['pack'],source)

    def test_stale_conflicting_and_uncompleted_requests_fail_before_snapshot(self):
        job=self.completed('article');before={p.relative_to(job).as_posix():p.read_bytes() for p in job.rglob('*') if p.is_file()};siblings=set(job.parent.iterdir())
        bad=[self.args(job,'--manuscript-edits',str(self.request),'--accept-blueprint'),
             self.args(job,'--manuscript-edits',str(self.request),'--retry-current-action')]
        stale=self.args(job,'--manuscript-edits',str(self.request));stale.revision-=1;bad.append(stale)
        with patch.object(wf,'snapshot_completed_job_for_writing',side_effect=AssertionError('must not snapshot')):
            for args in bad:
                with self.assertRaises(wf.WorkflowError):wf.continue_workflow(args)
        self.assertEqual({p.relative_to(job).as_posix():p.read_bytes() for p in job.rglob('*') if p.is_file()},before)
        self.assertEqual(set(job.parent.iterdir()),siblings)
        state=wf.load_state(job);state['status']='awaiting_blueprint_confirmation';wf.save_state(job,state)
        with self.assertRaises(wf.WorkflowError):self.start(job)

    def test_production_rejects_missing_actual_model_chain_and_mismatched_final(self):
        job=self.completed('article');state=wf.load_state(job);state['flags']['offline_fixture']=False;wf.save_state(job,state)
        with self.assertRaises(wf.WorkflowError):self.start(job)
        self.assertNotIn('writing_reruns',wf.load_state(job)['metadata'])
        state=wf.load_state(job);state['flags']['offline_fixture']=True;wf.save_state(job,state)
        Path(state['metadata']['delivery']['markdown']).write_text('manually changed final')
        with self.assertRaisesRegex(wf.WorkflowError,'终稿'):self.start(job)
        self.assertNotIn('writing_reruns',wf.load_state(job)['metadata'])

    def test_frozen_request_or_original_draft_tampering_stops_without_paid_call(self):
        job=self.completed('article');self.start(job)
        pointer=wf.load_state(job)['metadata']['article_manuscript_revision'];path=job/pointer['path'];original=path.read_bytes()
        value=json.loads(original);value['edits_markdown']='unrecorded request';wf.atomic_json(path,value)
        with self.assertRaises(ValueError):contracts.edit_base_input(wf,job,p0=False)
        path.write_bytes(original)
        wf.atomic_json(job/'production/article_draft.json',{'article_markdown':'changed original'})
        with self.assertRaises(ValueError):wf.run_production(job,p0=False)
        self.assertEqual(self.fixture.payloads,[])

    def test_explicit_blueprint_restart_clears_local_mode_and_retains_its_record(self):
        job=self.completed('article');self.start(job)
        pointer=wf.load_state(job)['metadata']['article_manuscript_revision'].copy()
        args=self.args(job,'--blueprint-edits','重新调整原主题。')
        with patch.object(wf,'drive',return_value=0):wf.handle_article_blueprint_pause(args,job)
        state=wf.load_state(job)
        self.assertNotIn('article_manuscript_revision',state['metadata'])
        self.assertEqual(state['metadata']['article_manuscript_revision_history'][-1],pointer)
        self.assertTrue((job/pointer['path']).is_file())
        self.assertEqual(state['status'],'running_article_blueprint')

    def test_paid_failure_requires_explicit_retry_and_then_resumes_edit_only(self):
        job=self.completed('article');self.start(job)
        state=wf.load_state(job);state['flags']['offline_fixture']=False;wf.save_state(job,state)
        changed=self.fixture.final.replace('终稿专属内容。','完成指定局部修订。')
        self.fixture.edit_payload={'edit_status':'revised','article_markdown':changed,
            'editorial_notes':['删除指定旁白。'],'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''}
        self.fixture.expected_candidate=changed;self.fixture.final_outcome='accepted'
        self.fixture.errors['article_edit']=('network_timeout','synthetic timeout')
        with self.assertRaises(integration.runtime.ProviderActionError):self.fixture.run_step(job,False)
        count=self.fixture.counts['article_edit']
        # Empty continue sees the saved failed attempt; it does not call the
        # simulated transport again or revert to an original-draft action.
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(integration.runtime.ProviderActionError):wf.continue_workflow(self.args(job))
        self.assertEqual(self.fixture.counts['article_edit'],count)
        del self.fixture.errors['article_edit']
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wf.continue_workflow(self.args(job,'--retry-current-action')),0)
        self.assertEqual(wf.load_state(job)['status'],'completed')
        self.assertNotIn('article_draft',self.fixture.counts)
        self.assertEqual(wf.read_json(job/'production/article_finalized.json')['article_markdown'],changed)
        attempts=job/'provider/article_edit/runtime/attempts'
        statuses=[wf.read_json(path/'execution.json')['status'] for path in attempts.iterdir() if path.is_dir()]
        self.assertCountEqual(statuses,['failed','succeeded'])
        calls=len(self.fixture.payloads)
        with contextlib.redirect_stdout(io.StringIO()):wf.continue_workflow(self.args(job))
        self.assertEqual(len(self.fixture.payloads),calls)


if __name__=='__main__':unittest.main()
