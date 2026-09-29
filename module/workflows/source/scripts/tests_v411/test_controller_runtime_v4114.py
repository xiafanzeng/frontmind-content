from scripts.tests_v411.historical_profiles import historical_profile
"""Two controller routes through explicit simulated API streams; never paid calls.

These integration tests establish routing, persistence and delivery body identity,
not model prose quality or Word rendering quality.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location('frontmind_controller_runtime_v4114', ROOT/'scripts/frontmind_workflow.py')
wf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wf
SPEC.loader.exec_module(wf)
from shared import model_runtime as runtime, natural_editor


def stream(model, content):
    yield {'id':'offline-integration','model':model,'choices':[{'index':0,'delta':{'reasoning_content':'offline test reasoning'},'finish_reason':None}]}
    yield {'id':'offline-integration','model':model,'choices':[{'index':0,'delta':{'content':content},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}}
    yield '[DONE]'


def tool_stream(name, arguments):
    encoded=json.dumps(arguments,ensure_ascii=False)
    item={'id':'offline-item-'+name,'type':'function_call','call_id':'offline-call-'+name,
          'name':name,'arguments':encoded,'status':'completed'}
    yield {'type':'response.created','response':{'id':'offline-response-'+name,'model':'gpt-6-astra','status':'in_progress'}}
    yield {'type':'response.output_item.added','output_index':0,'item':{**item,'arguments':'','status':'in_progress'}}
    yield {'type':'response.function_call_arguments.delta','output_index':0,'delta':encoded}
    yield {'type':'response.output_item.done','output_index':0,'item':item}
    yield {'type':'response.completed','response':{'id':'offline-response-'+name,'model':'gpt-6-astra','status':'completed','output':[item],
           'usage':{'input_tokens':10,'output_tokens':10,'total_tokens':20}}}


class RequiredReadTools:
    """Simulated text artifact tool, marked explicitly in runtime transport mode."""
    def __init__(self, body):self.body=body;self.read=False
    def definitions(self):
        return [{'type':'function','function':{'name':'read_current','description':'Read complete candidate fixture','parameters':{'type':'object','properties':{},'additionalProperties':False}}}]
    def execute(self,name,args):
        if name!='read_current' or args:raise ValueError('unsupported simulated tool')
        self.read=True
        return {'text':self.body,'complete_read':True}
    def assert_required_reads_complete(self):
        if not self.read:raise ValueError('candidate has not been read')
    def cache_dependencies(self):return []
    def export_state(self):return {'read':self.read}
    def restore_state(self,state):self.read=state['read']


class ControllerRuntimeIntegration(unittest.TestCase):
    def setUp(self):
        archived=patch.object(runtime, "profile_for", side_effect=historical_profile)
        archived.start(); self.addCleanup(archived.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.draft='# 合成品牌\n\n初稿特征。\n\n## 服务实施\n\n'+('合成企业先了解项目目标，再安排测试动作与交付检查。这是离线流程材料。'*14)
        self.final=self.draft.replace('初稿特征。','终稿专属内容。')
        self.payloads=[]
        self.counts={}
        self.errors={}
        self.edit_payload=None
        self.final_outcome='revised'
        self.expected_candidate=self.draft
        self.addCleanup(patch.stopall)
        patch.object(wf,'brand_content_context',return_value={'p0':'历史企业介绍完整文本'}).start()
        patch.object(wf,'answer_texts',return_value=['答案一首段\n答案一中段\n答案一结尾','答案二首段\n答案二中段\n答案二结尾']).start()
        patch.object(wf,'write_docx',side_effect=lambda body,path,title:(path.parent.mkdir(parents=True,exist_ok=True),path.write_text('Offline DOCX export stub',encoding='utf-8'))).start()
        patch.object(wf,'run_action',side_effect=self.offline_run).start()
    def job(self,prefix='p0'):
        job=self.base/prefix;job.mkdir()
        for name in ['blueprints','inputs','production']:(job/name).mkdir()
        state={'workflow_version':'4.11','job_id':'integration-'+prefix,'job_kind':'p0' if prefix=='p0' else 'article','status':'running_p0_production' if prefix=='p0' else 'running_article_production','stage':'production','revision':7,'flags':{prefix+'_production_step':'draft'},'metadata':{},'decisions':{},'reference_pack':{'brand':'合成品牌','pack_id':'synthetic-pack','pack_version':1},'question':{'question_text':'这个场景怎样完成软件测试？'},'selected_pattern_id':'P00' if prefix=='p0' else 'P03','selected_example_route':'default','pending_action':None,'current_pause':None}
        wf.atomic_json(job/'job_state.json',state)
        wf.atomic_text(job/'inputs/company_facts.md','合成品牌处理软件项目测试。')
        wf.atomic_json(job/'blueprints'/f'{prefix}_blueprint.json',{'kind':prefix if prefix=='p0' else 'article','opening':'建立企业身份','sections':[{'heading':'服务实施','task':'解释测试动作'}],'ending':'结束业务叙述','writing_material_markdown':'合成企业了解目标后安排测试与交付检查。','writing_material_sources':[{'source_ref':'inputs/company_facts.md','use':'企业业务事实'}],'material_adjustments':[]})
        return job
    def offline_run(self,package,job,action,prompt,validator,**kwargs):
        """Only injection point uses offline=True; controller remains production-routed."""
        expected=self.expected_candidate
        tools=RequiredReadTools(expected) if action.endswith(('_finalize','_title_review')) else None
        def transport(profile,key,payload):
            self.payloads.append((action,json.loads(json.dumps(payload,ensure_ascii=False))))
            self.counts[action]=self.counts.get(action,0)+1
            failure=self.errors.get(action)
            if failure:
                if isinstance(failure,str):return stream(profile['model'],failure)
                raise runtime.ProviderActionError(failure[0],failure[1],action=action)
            if action.endswith('_draft'):
                result={'article_markdown':self.draft,'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''}
            elif action.endswith('_edit'):
                result=self.edit_payload or {'edit_status':'accepted','article_markdown':self.draft,'editorial_notes':[],'requires_blueprint_reconfirmation':False,'reconfirmation_reason':''}
            elif action.endswith('_titles'):
                result={'canonical_title_id':'media_title_03' if action.startswith('p0_') else 'decision_title_04','families':{'decision_search':[{'title':f'合成品牌业务观察{i}'} for i in range(10)],'media_pr':[{'title':f'项目测试工作介绍{i}'} for i in range(10)]}}
            elif action.endswith('_title_review'):
                raw=wf.read_json(Path(job)/'production'/('p0_titles.json' if action.startswith('p0_') else 'article_titles.json'))
                normalized=wf.validate_title_map(raw,p0=action.startswith('p0_'))
                result={'outcome':'revised','candidates':[{'title':item['title_text'],'angle':'实际补充的阅读角度'} for item in normalized['options']],
                        'canonical_title_id':'title_13' if action.startswith('p0_') else 'title_04','title_notes':['为全部候选补充切入角度。'],'reason':''}
                if not tools.read:return tool_stream('read_current',{})
                return tool_stream('submit_result',{'result':result})
            elif action.endswith('_finalize') and natural_editor.matches(prompt):
                result={'needs_revision':False,'comments':[]}
                if not tools.read:return tool_stream('read_current',{})
                return tool_stream('submit_result',{'result':result})
            else:
                result={'outcome':self.final_outcome,'article_markdown':self.final if self.final_outcome=='revised' else expected if self.final_outcome=='accepted' else '', 'editorial_notes':['改写开篇。'] if self.final_outcome=='revised' else [],'reason':'无法完成，需要补充事实。' if self.final_outcome=='incomplete' else ''}
                if not tools.read:return tool_stream('read_current',{})
                if payload.get('tool_choice')!='none':return tool_stream('submit_result',{'result':result})
            return stream(profile['model'],json.dumps(result,ensure_ascii=False))
        return runtime.run_action(package,job,action,prompt,validator,transport=transport,offline=True,host_tools=tools,**kwargs)
    def run_step(self,job,p0):
        with contextlib.redirect_stdout(io.StringIO()):return wf.run_production(job,p0=p0)

    def completed_job(self,prefix):
        job=self.job(prefix);state=wf.load_state(job)
        state['status']='p0_ready' if prefix=='p0' else 'completed'
        state['flags'].pop(prefix+'_production_step',None)
        state['decisions'][prefix+'_blueprint_confirmation']={'revision':7,'confirmed_at':'original-confirmation'}
        state['reference_pack']['path']=str(job/'00_input/reference_pack.zip')
        wf.save_state(job,state)
        for name,text in {'00_input/reference_pack.zip':'original bound pack',
                          f'deliverables/{prefix}.md':'old published manuscript',
                          'deliverables/Reference_Pack_v4/record.json':'old delivered pack',
                          f'production/{prefix}_draft.json':'original draft bytes',
                          f'provider/{prefix}_draft/runtime/attempts/original/response.json':'original API bytes'}.items():
            path=job/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        return job

    def test_completed_writing_rerun_requires_current_revision_and_empty_continue_is_readonly(self):
        for prefix in ('p0','article'):
            job=self.completed_job(prefix)
            before={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()}
            siblings=set(job.parent.iterdir())
            for argv in ([],['--accept-blueprint','--revision','6'],
                         ['--blueprint-edits','重新按篇选材。','--revision','6']):
                args=wf.parser().parse_args(['continue','--job-dir',str(job),*argv])
                with contextlib.redirect_stdout(io.StringIO()):
                    if argv:
                        with self.assertRaises(wf.WorkflowError):wf.continue_workflow(args)
                    else:self.assertEqual(wf.continue_workflow(args),0)
                self.assertEqual(set(job.parent.iterdir()),siblings)
                self.assertEqual({str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()},before)
            self.assertEqual(self.payloads,[])

    def test_explicit_completed_rerun_snapshots_all_bytes_and_keeps_upstream_unchanged(self):
        for prefix in ('p0','article'):
            job=self.completed_job(prefix)
            original_state=wf.load_state(job)
            before={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()}
            flag='--accept-p0-blueprint' if prefix=='p0' else '--accept-blueprint'
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7',flag])
            with patch.object(wf,'drive',return_value=0):self.assertEqual(wf.continue_workflow(args),0)
            state=wf.load_state(job);record=state['metadata']['writing_reruns'][-1];archive=Path(record['archive_path'])
            self.assertEqual(archive.parent,job.parent.resolve());self.assertFalse(archive.is_relative_to(job.resolve()))
            self.assertEqual({str(p.relative_to(archive)):p.read_bytes() for p in archive.rglob('*') if p.is_file()},before)
            self.assertEqual(state['reference_pack'],original_state['reference_pack'])
            for name in ('00_input/reference_pack.zip',f'blueprints/{prefix}_blueprint.json',f'provider/{prefix}_draft/runtime/attempts/original/response.json'):
                self.assertEqual((job/name).read_bytes(),before[name])
                self.assertFalse(os.path.samefile(job/name,archive/name))
            self.assertEqual(state['flags'][prefix+'_production_step'],'draft')
            self.assertEqual(state['status'],'running_p0_production' if prefix=='p0' else 'running_article_production')
            self.assertTrue(Path(record['manifest_path']).is_file());self.assertEqual(self.payloads,[])
            (job/'production'/f'{prefix}_draft.json').write_text('new downstream result')
            self.assertEqual((archive/'production'/f'{prefix}_draft.json').read_bytes(),before[f'production/{prefix}_draft.json'])
            titles={'canonical_title_id':'media_title_03' if prefix=='p0' else 'decision_title_04','families':{'decision_search':[{'title':f'业务观察{i}'} for i in range(10)],'media_pr':[{'title':f'项目说明{i}'} for i in range(10)]}}
            delivery=wf.deliver_article(job,self.final,titles,prefix=prefix)
            output=job/'deliverables'/record['rerun_id']
            self.assertTrue(all(Path(path).parent==output.resolve() and Path(path).is_file() for path in delivery.values()))
            self.assertEqual((job/'deliverables'/f'{prefix}.md').read_bytes(),before[f'deliverables/{prefix}.md'])
            directory,portable=wf._pack_output_targets(job,4)
            self.assertEqual(directory,output/'Reference_Pack_v4');self.assertEqual(portable,output/'Reference_Pack_v4.zip')
            self.assertFalse(directory.exists());self.assertEqual((job/'deliverables/Reference_Pack_v4/record.json').read_text(),'old delivered pack')

    def test_completed_blueprint_edits_snapshot_then_reenter_original_confirmation_flow(self):
        for prefix in ('p0','article'):
            job=self.completed_job(prefix)
            # Keep both a previous edit and its action evidence to verify normal
            # invalidation archives them rather than replacing the paid record.
            state=wf.load_state(job);state['decisions']['blueprint_edits']='此前的修改要求。'
            wf.save_state(job,state)
            old_outline=job/'inputs'/f'{prefix}_blueprint_edit_outline.json'
            wf.atomic_json(old_outline,{'headings':['旧主题'],'edit_sha256':'old-edit'})
            old_result=job/'provider'/f'{prefix}_blueprint/result.json'
            wf.atomic_json(old_result,{'previous':'blueprint-result'})
            original_state=wf.load_state(job)
            before={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()}
            edit='从知识库重新选取本篇事实，总结成自然段落，保留服务实施主题。'
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--blueprint-edits',edit])
            handler='handle_p0_blueprint_pause' if prefix=='p0' else 'handle_article_blueprint_pause'
            with patch.object(wf,handler,wraps=getattr(wf,handler)) as original_handler, patch.object(wf,'drive',return_value=0):
                self.assertEqual(wf.continue_workflow(args),0)
                original_handler.assert_called_once_with(args,job.resolve())
            state=wf.load_state(job);record=state['metadata']['writing_reruns'][-1];archive=Path(record['archive_path'])
            self.assertEqual({str(p.relative_to(archive)):p.read_bytes() for p in archive.rglob('*') if p.is_file()},before)
            self.assertFalse(os.path.samefile(job/'job_state.json',archive/'job_state.json'))
            self.assertEqual(state['status'],f'running_{prefix}_blueprint')
            self.assertEqual(state['decisions']['blueprint_edits'],edit)
            self.assertEqual(state['decisions'][prefix+'_blueprint_confirmation'],original_state['decisions'][prefix+'_blueprint_confirmation'])
            self.assertEqual(state['flags'],original_state['flags'])
            self.assertEqual(state['reference_pack'],original_state['reference_pack'])
            for name in (f'blueprints/{prefix}_blueprint.json',f'production/{prefix}_draft.json',f'deliverables/{prefix}.md'):
                self.assertEqual((job/name).read_bytes(),before[name])
            frozen=wf.read_json(old_outline)
            self.assertEqual(frozen['revision_candidate']['writing_material_markdown'],wf.read_json(job/f'blueprints/{prefix}_blueprint.json')['writing_material_markdown'])
            self.assertFalse(old_result.exists())
            invalidated=job/'provider'/f'{prefix}_blueprint/invalidated'
            self.assertTrue(any(p.read_bytes()==before[str(old_outline.relative_to(job))] for p in invalidated.rglob(old_outline.name)))
            self.assertTrue(any(p.read_bytes()==before[str(old_result.relative_to(job))] for p in invalidated.rglob('result.json')))
            rerun_output=wf.writing_delivery_root(job)
            self.assertEqual(rerun_output,job/'deliverables'/record['rerun_id'])
            # The existing blueprint page still requires its own acceptance;
            # accepting there uses this rerun, without a second snapshot.
            with contextlib.redirect_stdout(io.StringIO()):wf.render_blueprint_confirmation(job,p0=prefix=='p0')
            paused=wf.load_state(job)
            self.assertEqual(paused['status'],'awaiting_p0_blueprint_confirmation' if prefix=='p0' else 'awaiting_blueprint_confirmation')
            accept=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(paused['revision']),'--accept-blueprint'])
            with patch.object(wf,'drive',return_value=0):self.assertEqual(wf.continue_workflow(accept),0)
            self.assertEqual(len(wf.load_state(job)['metadata']['writing_reruns']),1)
            self.assertEqual(wf.writing_delivery_root(job),rerun_output)
            self.assertEqual(wf.load_state(job)['flags'][prefix+'_production_step'],'draft')
            self.assertEqual(self.payloads,[])

    def test_completed_blueprint_edit_alias_and_conflicting_accept_do_not_silently_start_writer(self):
        job=self.completed_job('p0')
        before={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()}
        siblings=set(job.parent.iterdir())
        conflict=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--p0-blueprint-edits','重新选材。','--accept-p0-blueprint'])
        with self.assertRaisesRegex(wf.WorkflowError,'不能同时提交'):wf.continue_workflow(conflict)
        self.assertEqual(set(job.parent.iterdir()),siblings)
        self.assertEqual({str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()},before)
        alias=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--p0-blueprint-edits','重新选材。'])
        with patch.object(wf,'drive',return_value=0):self.assertEqual(wf.continue_workflow(alias),0)
        self.assertEqual(wf.load_state(job)['status'],'running_p0_blueprint')
        self.assertNotIn('p0_production_step',wf.load_state(job)['flags'])
        self.assertEqual(self.payloads,[])

    def test_completed_rerun_rejects_unsafe_snapshot_sources_without_mutation(self):
        job=self.completed_job('p0');external=self.base/'outside.txt';external.write_text('outside')
        (job/'linked').symlink_to(external)
        before=(job/'job_state.json').read_bytes();siblings=set(job.parent.iterdir())
        args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--accept-blueprint'])
        with self.assertRaises(wf.WorkflowError):wf.continue_workflow(args)
        self.assertEqual((job/'job_state.json').read_bytes(),before);self.assertEqual(set(job.parent.iterdir()),siblings)
        self.assertEqual(external.read_text(),'outside');self.assertEqual(self.payloads,[])

    def test_completed_rerun_copy_failure_does_not_update_job_or_start_writer(self):
        job=self.completed_job('article');before=(job/'job_state.json').read_bytes();siblings=set(job.parent.iterdir())
        args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--accept-blueprint'])
        with patch.object(wf.shutil,'copytree',side_effect=OSError('simulated copy failure')):
            with self.assertRaises(wf.WorkflowError):wf.continue_workflow(args)
        self.assertEqual((job/'job_state.json').read_bytes(),before);self.assertEqual(set(job.parent.iterdir()),siblings)
        self.assertEqual(self.payloads,[])

    def test_blueprint_edit_freezes_projected_candidate_and_preserves_each_revision(self):
        for prefix in ('p0', 'article'):
            job = self.job(prefix)
            prior_path = job / 'blueprints' / f'{prefix}_blueprint.json'
            before = prior_path.read_bytes()
            prior = wf.read_json(prior_path)
            prior.update(research_markdown='UNRELATED_RESEARCH', comparison_scope={'all':'UNRELATED_COMPARISON'}, core_positioning='OLD_CORE')
            wf.atomic_json(prior_path, prior)
            before = prior_path.read_bytes()
            wf.freeze_blueprint_edit_outline(job, p0=prefix == 'p0', new_edits='same edit')
            outline = wf.read_json(job / 'inputs' / f'{prefix}_blueprint_edit_outline.json')
            self.assertEqual(outline['headings'], ['服务实施'])
            self.assertEqual(outline['revision_candidate']['writing_material_markdown'], prior['writing_material_markdown'])
            self.assertEqual(outline['revision_candidate']['writing_material_sources'], prior['writing_material_sources'])
            self.assertNotIn('UNRELATED', json.dumps(outline))
            self.assertNotIn('OLD_CORE', json.dumps(outline))
            self.assertEqual(prior_path.read_bytes(), before)
            state = wf.load_state(job)
            state['decisions']['blueprint_edits'] = 'same edit'
            wf.save_state(job, state)
            prior = wf.read_json(prior_path)
            prior['sections'] = [{'heading': '新生成的主题', 'task': '新任务'}]
            wf.atomic_json(prior_path, prior)
            wf.freeze_blueprint_edit_outline(job, p0=prefix == 'p0', new_edits='same edit')
            self.assertEqual(wf.read_json(job / 'inputs' / f'{prefix}_blueprint_edit_outline.json'), outline)
            wf.freeze_blueprint_edit_outline(job, p0=prefix == 'p0', new_edits='next edit')
            current = wf.read_json(job / 'inputs' / f'{prefix}_blueprint_edit_outline.json')
            self.assertEqual(current['revision_candidate']['sections'][0]['heading'], '新生成的主题')
            archives=list((job/'provider'/f'{prefix}_blueprint'/'invalidated').glob(f'*/{prefix}_blueprint_edit_outline.json'))
            self.assertEqual([wf.read_json(p) for p in archives], [outline])

    def test_explicit_edit_keeps_candidate_but_supplement_archives_it_on_both_routes(self):
        for prefix in ('p0', 'article'):
            job=self.job(prefix); p0=prefix=='p0'
            handler=wf.handle_p0_blueprint_pause if p0 else wf.handle_article_blueprint_pause
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--blueprint-edits','具体修改意见'])
            with patch.object(wf,'drive',return_value=0):handler(args,job)
            frozen_path=job/'inputs'/f'{prefix}_blueprint_edit_outline.json'
            frozen=frozen_path.read_bytes()
            self.assertIn('revision_candidate',wf.read_json(frozen_path))
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--blueprint-supplement','新的事实材料'])
            with patch.object(wf,'drive',return_value=0), patch.object(wf,'save_user_material') as save:
                handler(args,job)
            self.assertTrue(save.called);self.assertFalse(frozen_path.exists())
            self.assertEqual(wf.load_state(job)['decisions']['blueprint_edits'],'具体修改意见')
            archives=(job/'provider'/f'{prefix}_blueprint'/'invalidated').glob(f'*/{prefix}_blueprint_edit_outline.json')
            self.assertTrue(any(path.read_bytes()==frozen for path in archives))

    def test_example_route_change_discards_active_edit_candidate_but_keeps_history(self):
        for prefix in ('p0', 'article'):
            job=self.job(prefix);p0=prefix=='p0'
            wf.freeze_blueprint_edit_outline(job,p0=p0,new_edits='old edit')
            path=job/'inputs'/f'{prefix}_blueprint_edit_outline.json'; original=path.read_bytes()
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision','7','--example-route','workflow' if p0 else 'B'])
            with patch.object(wf,'drive',return_value=0):wf.handle_example_pause(args,job,p0=p0)
            self.assertFalse(path.exists())
            archives=(job/'provider'/f'{prefix}_blueprint'/'invalidated').glob(f'*/{prefix}_blueprint_edit_outline.json')
            self.assertTrue(any(p.read_bytes()==original for p in archives))
    def test_both_routes_full_runtime_chain_delivers_body_and_separate_titles(self):
        for prefix in ['p0','article']:
            with self.subTest(prefix=prefix):
                job=self.job(prefix)
                for unused in range(6):self.run_step(job,prefix=='p0')
                published=(job/'deliverables'/f'{prefix}.md').read_text()
                self.assertEqual(published,wf.title_publication.body_only(self.final))
                title_map=wf.read_json(job/'deliverables'/f'{prefix}_title_map.json')
                self.assertNotIn('selected_title',title_map)
                self.assertEqual(title_map['recommended_title_id'],'title_13' if prefix=='p0' else 'title_04')
                options=(job/'deliverables'/f'{prefix}_title_options.md').read_text()
                for option in title_map['options']:
                    self.assertIn(option['title_text'],options)
                self.assertEqual(wf.read_json(job/'production'/f'{prefix}_finalized.json')['article_markdown'],self.final)
                self.assertEqual(wf.read_json(job/'production'/f'{prefix}_edited.json')['article_markdown'],self.draft)
                actions=[action for action,payload in self.payloads if action.startswith(prefix+'_')]
                self.assertEqual(set(actions),{prefix+'_'+step for step in ['draft','edit','finalize','titles','title_review']})
                title_prompt=next(payload['messages'][1]['content'] for action,payload in self.payloads if action==prefix+'_titles')
                self.assertIn(wf.title_publication.body_only(self.final),title_prompt);self.assertNotIn('初稿特征。',title_prompt)
                self.assertFalse(any('visual' in path.name or path.suffix.lower() in {'.png','.jpg','.jpeg'} for path in job.rglob('*')))
                for action,payload in self.payloads:
                    if action.endswith(('_finalize','_title_review')):
                        self.assertEqual(payload['reasoning'],{'effort':'high'})
                        self.assertNotIn('thinking',payload)
                        self.assertNotIn('reasoning_effort',payload)
                        self.assertFalse(payload['store'])
                    else:self.assertEqual(payload['reasoning_effort'],'max')
                    self.assertEqual(payload['model'],'gpt-6-astra' if action.endswith(('_finalize','_title_review')) else 'deepseek-v4-pro')
    def test_malformed_complete_e8_falls_back_to_current_draft_for_host(self):
        for prefix in ['p0','article']:
            job=self.job(prefix);self.errors[prefix+'_edit']='not valid JSON'
            self.run_step(job,prefix=='p0')
            self.run_step(job,prefix=='p0')
            self.assertEqual(wf.load_state(job)['flags'][prefix+'_production_step'],'finalize')
            self.run_step(job,prefix=='p0')
            context=wf.editorial_contracts.prepare_finalize_input(wf,job,p0=prefix=='p0')
            self.assertEqual(context['candidate_markdown'],self.draft)
            self.assertEqual(context['candidate_source'],'deepseek_draft_after_edit_format_error')
            self.assertTrue((job/'production'/f'{prefix}_edit_failure.json').is_file())
    def test_unreadable_new_e8_never_reuses_stale_candidate(self):
        job=self.job();self.run_step(job,True)
        wf.atomic_json(job/'production/p0_edited.json',{'article_markdown':'# STALE prior candidate'})
        self.errors['p0_edit']='not JSON'
        self.run_step(job,True)
        context=wf.editorial_contracts.prepare_finalize_input(wf,job,p0=True)
        self.assertEqual(context['candidate_markdown'],self.draft)
        self.assertTrue(any(path.name=='p0_edited.json' for path in (job/'production/history').rglob('*')))
    def test_api_auth_and_network_failures_stop_before_host(self):
        for code in ['authentication_error','network_timeout']:
            prefix='p0' if code=='authentication_error' else 'article';job=self.job(prefix)
            self.errors[prefix+'_edit']=(code,'offline simulated API failure')
            self.run_step(job,prefix=='p0')
            with self.assertRaises(runtime.ProviderActionError):self.run_step(job,prefix=='p0')
            self.assertEqual(wf.load_state(job)['flags'][prefix+'_production_step'],'edit')
            self.assertNotIn(prefix+'_finalize',self.counts)
            self.assertFalse((job/'production'/f'{prefix}_edit_failure.json').exists())
    def test_continue_requires_explicit_current_revision_retry(self):
        job=self.job();self.errors['p0_draft']=('network_timeout','offline timeout')
        with self.assertRaises(runtime.ProviderActionError):self.run_step(job,True)
        with patch.object(wf,'drive',side_effect=lambda target:self.run_step(target,True)):
            args=wf.parser().parse_args(['continue','--job-dir',str(job)])
            with self.assertRaises(runtime.ProviderActionError):wf.continue_workflow(args)
            self.assertEqual(self.counts['p0_draft'],1)
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--retry-current-action','--revision','6'])
            with self.assertRaises(wf.WorkflowError):wf.continue_workflow(args)
            self.assertEqual(self.counts['p0_draft'],1)
            self.errors.pop('p0_draft')
            args=wf.parser().parse_args(['continue','--job-dir',str(job),'--retry-current-action','--revision','7'])
            wf.continue_workflow(args)
            self.assertEqual(self.counts['p0_draft'],2)
            attempts=list((job/'provider/p0_draft/runtime/attempts').glob('*/execution.json'))
            self.assertEqual(len(attempts),2)
    def test_host_incomplete_does_not_generate_titles_or_loop_paid_calls(self):
        job=self.job();self.final_outcome='incomplete'
        self.run_step(job,True);self.run_step(job,True)
        with self.assertRaises(wf.WorkflowError):self.run_step(job,True)
        before=self.counts['p0_finalize']
        with self.assertRaises(wf.WorkflowError):self.run_step(job,True)
        self.assertEqual(self.counts['p0_finalize'],before)
        self.assertNotIn('p0_titles',self.counts)
        self.assertFalse((job/'deliverables').exists())
    def test_tampered_saved_draft_recovers_original_api_body_without_new_call(self):
        for prefix in ['p0','article']:
            with self.subTest(prefix=prefix):
                job=self.job(prefix);p0=prefix=='p0'
                self.run_step(job,p0)
                original_calls=self.counts[prefix+'_draft']
                path=job/'production'/f'{prefix}_draft.json';changed=wf.read_json(path)
                changed['article_markdown']=changed['article_markdown'].replace('初稿特征。','UNTRUSTED MANUAL CHANGE。')
                wf.atomic_json(path,changed)
                self.run_step(job,p0)
                self.assertEqual(wf.load_state(job)['flags'][prefix+'_production_step'],'draft')
                self.run_step(job,p0)
                self.assertEqual(self.counts[prefix+'_draft'],original_calls)
                self.assertEqual(wf.read_json(path)['article_markdown'],self.draft)
                self.run_step(job,p0)
                edit_prompt=next(payload['messages'][1]['content'] for action,payload in self.payloads if action==prefix+'_edit')
                self.assertIn(self.draft,edit_prompt);self.assertNotIn('UNTRUSTED MANUAL CHANGE',edit_prompt)
    def test_tampered_final_recovers_glm_record_before_generating_titles(self):
        for prefix in ['p0','article']:
            with self.subTest(prefix=prefix):
                job=self.job(prefix);p0=prefix=='p0'
                for unused in range(3):self.run_step(job,p0)
                original_calls=self.counts[prefix+'_finalize']
                path=job/'production'/f'{prefix}_finalized.json';changed=wf.read_json(path)
                changed['article_markdown']=changed['article_markdown'].replace('终稿专属内容。','UNTRUSTED FINAL CHANGE。')
                wf.atomic_json(path,changed)
                self.run_step(job,p0)
                self.assertEqual(wf.load_state(job)['flags'][prefix+'_production_step'],'finalize')
                self.run_step(job,p0)
                self.assertEqual(self.counts[prefix+'_finalize'],original_calls)
                self.assertEqual(wf.read_json(path)['article_markdown'],self.final)
                self.run_step(job,p0)
                title_prompt=next(payload['messages'][1]['content'] for action,payload in self.payloads if action==prefix+'_titles')
                self.assertIn(wf.title_publication.body_only(self.final),title_prompt);self.assertNotIn('UNTRUSTED FINAL CHANGE',title_prompt)
    def test_image_markup_is_rejected(self):
        for token in ['![图片](x.png)','![图片][source]','![图片]','<img src="x.png">','<svg></svg>','<picture></picture>','[图片引用 1]','【图片引用2】','[图片占位：证书]','【配图：团队】','[插图:项目流程]']:
            with self.assertRaises(wf.WorkflowError):wf.validate_article_markdown(self.draft+'\n'+token)

    def test_normal_business_mentions_of_images_remain_valid_text(self):
        statement='系统支持图片存储与读取，软件测试包括上传和显示功能。'
        self.assertIn(statement,wf.validate_article_markdown(self.draft+'\n'+statement))


if __name__=='__main__':unittest.main()
