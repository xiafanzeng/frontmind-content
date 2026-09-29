"""Headline adoption and provenance; synthetic fixtures, no paid calls."""
import contextlib
import copy
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from shared import title_publication as publication, manuscript_revision as revisions
from shared.model_runtime import request_fingerprint
from scripts.tests_v411 import test_manuscript_revision as legacy

# 作者档位跟随本包 config/deepseek.json 的显式覆盖（用户2026-09-22定为high；缺省默认max）。
# 断言验证配置一致性，而不是钉死某一档位。
import json as _json
from pathlib import Path as _Path
try:
    _cfgf = _Path(__file__).resolve().parents[2] / 'config' / 'deepseek.json'
    _WRITER_EFFORT = (_json.loads(_cfgf.read_text()).get('reasoning_effort') or 'max') if _cfgf.exists() else 'max'
except Exception:
    _WRITER_EFFORT = 'max'


wf = legacy.wf


def titles(*, p0=True):
    return {"families": {
        "decision_search": [{"title": f"合成任务的第{i}种问题观察"} for i in range(1, 11)],
        "media_pr": [{"title": f"合成品牌的第{i}种媒体观察", "h1": f"可选副题{i}，不能补主标题条件"} for i in range(1, 11)]},
        "canonical_title_id": "media_title_06" if p0 else "decision_title_07"}


class TitleContractTests(unittest.TestCase):
    def test_new_title_result_requires_explicit_valid_selection(self):
        for selected in (None, "", "media_title_00", "media_title_11", "decision_title_99", "invented"):
            value = titles();value['canonical_title_id'] = selected
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                publication.validate_title_map(value, p0=True)
        value=titles();value.pop('canonical_title_id')
        with self.assertRaises(ValueError):publication.validate_title_map(value)

    def test_recommendation_can_come_from_either_compatibility_group(self):
        result=publication.validate_title_map(titles(),p0=True)
        self.assertEqual(result['selected_title_id'],'media_title_06')
        self.assertEqual(result['selected_title'],'合成品牌的第6种媒体观察')
        self.assertEqual(publication.validate_title_map(titles(p0=False),p0=True)['selected_title_id'],'decision_title_07')
        self.assertEqual(publication.validate_title_map(titles(p0=False))['selected_title_id'],'decision_title_07')
        self.assertEqual(publication.validate_title_map(titles())['selected_title_id'],'media_title_06')

    def test_legacy_validation_is_explicit_and_not_a_new_action_default(self):
        value=titles();value.pop('canonical_title_id')
        result=publication.validate_title_map(value,legacy=True)
        self.assertEqual(result['title_adoption_mode'],'legacy_unchanged_manuscript')
        self.assertIsNone(result['canonical_title_id'])
        with self.assertRaises(ValueError):publication.publication('# 旧标题\n\n正文\n',value,p0=True)

    def test_duplicate_or_multiline_headline_is_rejected(self):
        value=titles();value['families']['media_pr'][5]['title']='标题\n## 额外段落'
        with self.assertRaises(ValueError):publication.validate_title_map(value,p0=True)
        value=titles();value['families']['media_pr'][5]['title']='![图片](untrusted.png)'
        with self.assertRaises(ValueError):publication.validate_title_map(value,p0=True)
        value=titles();value['families']['media_pr'][5]['title']=value['families']['decision_search'][0]['title']
        with self.assertRaises(ValueError):publication.validate_title_map(value,p0=True)

    def test_legacy_only_first_h1_changes_with_all_other_bytes_and_line_endings_retained(self):
        for body in ('# 原标题\n\n## 节\n正文。\n# 后面的标题不变\n',
                     '前置内容\r\n# 原标题\r\n\r\n## 节\r\n正文。\r\n# 其余不变\r\n'):
            with self.subTest(body=body):
                result,title_map,binding=publication._legacy_publication(body,titles(),p0=True)
                self.assertEqual(result,body.replace('# 原标题','# 合成品牌的第6种媒体观察',1))
                self.assertNotIn('可选副题',result)
                self.assertEqual(publication.without_first_h1(body),publication.without_first_h1(result))
                self.assertEqual(binding['host_final_markdown_sha256'],publication.text_hash(body))
                self.assertEqual(binding['published_markdown_sha256'],publication.text_hash(result))
                self.assertNotEqual(binding['host_final_markdown_sha256'],binding['published_markdown_sha256'])
                self.assertEqual(publication.verify_publication(body,titles(),result,binding,p0=True),title_map)

    def test_publication_rejects_changed_body_selection_or_binding(self):
        base='# 原标题\n\n## 节\n正文。\n';original=titles()
        result,title_map,binding=publication.publication(base,original,p0=True)
        self.assertEqual(publication.verify_publication(base,original,result,binding,p0=True),title_map)
        altered=copy.deepcopy(original);altered['canonical_title_id']='media_title_07'
        for candidate,payload,record in ((result+'新内容',original,binding),(result,altered,binding),
                                           (result,original,{**binding,'body_without_h1_sha256':'bad'})):
            with self.assertRaises(ValueError):publication.verify_publication(base,payload,candidate,record,p0=True)

    def test_current_title_request_is_single_headline_per_option_and_keeps_complete_final(self):
        from types import SimpleNamespace
        from shared.writing_context import prompt_titles
        final='# 合成终稿\n\n## 当前事项\n甲项服务用于设备维护，乙项仅适用指定条件。\n'
        workflow=SimpleNamespace(load_state=lambda job:{'metadata':{},'selected_pattern_id':'P03'})
        for p0 in (True,False):
            with self.subTest(p0=p0):
                prompt=prompt_titles(workflow,Path('controlled_fixture'),p0=p0,final_markdown=final)
                self.assertIn(publication.body_only(final),prompt)
                self.assertNotIn('# 合成终稿',prompt)
                self.assertIn('每项含 title 和 angle',prompt)
                self.assertIn('为同一篇完整文章拟定20个独立发布标题候选',prompt)
                self.assertIn('candidates 是20项的数组',prompt)
                self.assertNotIn('families.decision_search',prompt)
                self.assertIn('避免旧标题锚定',prompt)
                self.assertIn('不另生成 h1 或副题',prompt)
                self.assertIn('每个候选都必须独立、准确地成立',prompt)
                self.assertIn('同一事项的对象、用途及全部必要条件',prompt)
                self.assertNotIn('可选 h1',prompt)
                self.assertIn('canonical_title_id',prompt)
                value=titles(p0=p0)
                for rows in value['families'].values():
                    for row in rows:row.pop('h1',None)
                self.assertEqual(publication.validate_title_map(value,p0=p0)['selected_title_id'],value['canonical_title_id'])

    def test_title_editor_role_changes_only_two_requests_and_their_fingerprints(self):
        from shared import model_runtime as runtime
        actions=runtime.HOST_ACTIONS|runtime.DEEPSEEK_ACTIONS
        selected=runtime.system_prompt_for
        current={a:runtime.build_payload(a,'same complete task') for a in actions}
        current_hash={a:runtime.request_fingerprint(a,'same complete task') for a in actions}
        with patch.object(runtime,'system_prompt_for',side_effect=lambda action, **kwargs:
                          runtime.DEEPSEEK_SYSTEM if action.endswith('_titles') else selected(action)):
            old={a:runtime.build_payload(a,'same complete task') for a in actions}
            old_hash={a:runtime.request_fingerprint(a,'same complete task') for a in actions}
        self.assertEqual({a for a in actions if current[a]!=old[a]},{'p0_titles','article_titles'})
        self.assertEqual({a for a in actions if current_hash[a]!=old_hash[a]},{'p0_titles','article_titles'})
        for action in ('p0_titles','article_titles'):
            self.assertEqual(current[action]['messages'][0]['content'],runtime.DEEPSEEK_TITLES_SYSTEM)
            self.assertNotIn('使用本篇自然事实素材组织文章',current[action]['messages'][0]['content'])
            self.assertEqual(current[action]['model'],'deepseek-v4-pro')
            self.assertEqual(current[action]['reasoning_effort'],_WRITER_EFFORT)
            current[action]['messages'][0]=old[action]['messages'][0]
            self.assertEqual(current[action],old[action])

    def test_title_role_rebuilds_title_cache_without_recalling_completed_draft(self):
        import tempfile
        from shared import model_runtime as runtime
        from scripts.tests_v411.test_model_runtime import stream,valid
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'package';root.mkdir();job=Path(temporary)/'job';job.mkdir()
            calls=[]
            def transport(profile,key,payload):
                calls.append(payload)
                return stream(model='deepseek-v4-pro')
            def execute(action):
                return runtime.run_action(root,job,action,'same final manuscript',valid,transport=transport,offline=True)
            execute('p0_draft')
            selector=runtime.system_prompt_for
            with patch.object(runtime,'system_prompt_for',side_effect=lambda action, **kwargs:
                              runtime.DEEPSEEK_SYSTEM if action=='p0_titles' else selector(action)):
                execute('p0_titles')
            original=runtime.action_record(job,'p0_titles')['attempt_id']
            execute('p0_titles')
            self.assertEqual(len(calls),3)
            self.assertNotEqual(runtime.action_record(job,'p0_titles')['attempt_id'],original)
            self.assertTrue((job/'provider/p0_titles/runtime/attempts'/original/'execution.json').is_file())
            execute('p0_draft');execute('p0_titles')
            self.assertEqual(len(calls),3)

    def test_contract_is_part_of_title_cache_fingerprint(self):
        before=request_fingerprint('p0_titles','相同正文与请求')
        with patch('shared.workflow_versions.TITLE_CONTRACT_VERSION','future-contract'):
            self.assertNotEqual(before,request_fingerprint('p0_titles','相同正文与请求'))
        with patch('shared.workflow_versions.TITLE_CONTRACT_VERSION','future-contract'):
            self.assertEqual(request_fingerprint('p0_draft','相同请求'),request_fingerprint('p0_draft','相同请求'))


class PublicationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=legacy.ManuscriptRevisionTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def publish(self,prefix='article'):
        job=self.fixture.completed(prefix)
        payload=titles(p0=prefix=='p0')
        source=job/'production'/f'{prefix}_finalized.json';before=source.read_bytes()
        wf.atomic_json(job/'production'/f'{prefix}_titles.json',payload)
        captured={}
        def docx(body,path,title):
            captured.update(body=body,title=title);path.write_text('synthetic-docx')
        with patch.object(wf,'write_docx',side_effect=docx):
            delivery=wf.deliver_article(job,self.fixture.fixture.final,payload,prefix=prefix)
        state=wf.load_state(job);state['metadata']['delivery']=delivery;wf.save_state(job,state)
        self.assertEqual(source.read_bytes(),before)
        return job,delivery,captured

    def test_all_body_exports_omit_article_h1_preserving_host_result(self):
        for prefix in ('p0','article'):
            with self.subTest(prefix=prefix):
                job,delivery,captured=self.publish(prefix)
                body=Path(delivery['markdown']).read_text()
                title_map=wf.read_json(Path(delivery['title_map']))
                record=wf.read_json(Path(delivery['publication']))
                neutral_title='品宣正文' if prefix=='p0' else '问题文章正文'
                self.assertEqual(body,publication.body_only(self.fixture.fixture.final))
                self.assertNotIn('selected_title',title_map)
                self.assertEqual(title_map['recommended_title_id'],titles(p0=prefix=='p0')['canonical_title_id'])
                self.assertIn('<title>'+neutral_title+'</title>',Path(delivery['html']).read_text())
                self.assertNotIn('<h1',Path(delivery['html']).read_text())
                self.assertEqual(captured,{'body':body,'title':neutral_title})
                self.assertEqual(title_map['publication'],record)
                self.assertEqual(record['finalized_result_file_sha256'],wf.sha256_file(job/f'production/{prefix}_finalized.json'))
                self.assertEqual(record['titles_result_file_sha256'],wf.sha256_file(job/f'production/{prefix}_titles.json'))
                self.assertEqual(record['body_without_h1_sha256'],publication.text_hash(body))

    def test_revision_retains_full_internal_host_base_and_verifies_external_body(self):
        job,delivery,_=self.publish()
        frozen=revisions.validate_completed_manuscript(wf,job,p0=False)
        self.assertEqual(frozen['base_markdown'],self.fixture.fixture.final)
        self.assertEqual(frozen['base_source'],'previous_host_final')
        self.assertEqual(frozen['source']['host_final_markdown_sha256'],revisions.text_hash(self.fixture.fixture.final))
        self.assertEqual(frozen['base_sha256'],frozen['source']['host_final_markdown_sha256'])
        self.assertEqual(publication.body_only(frozen['base_markdown']),Path(delivery['markdown']).read_text())
        self.fixture.start(job)
        base=legacy.contracts.edit_base_input(wf,job,p0=False)
        self.assertEqual(base['article_markdown'],frozen['base_markdown'])
        self.assertEqual(base['source'],'previous_host_final')

    def test_title_only_revision_accepts_internal_base_without_inserting_recommendation(self):
        job,delivery,_=self.publish()
        args=self.fixture.args(job,'--title-edits',str(self.fixture.request))
        before=(job/'production/article_finalized.json').read_bytes()
        with patch.object(wf,'drive',return_value=0):wf.continue_workflow(args)
        frozen=revisions.current_title_revision(wf,job,p0=False)
        self.assertEqual(frozen['base_markdown'],self.fixture.fixture.final)
        prompt=wf.prompt_titles(job,p0=False)
        self.assertIn(publication.body_only(frozen['base_markdown']),prompt)
        self.assertIn(publication.body_only(self.fixture.fixture.final),prompt)
        self.assertNotIn('# 合成任务的第7种问题观察',prompt)
        self.assertEqual((job/'production/article_finalized.json').read_bytes(),before)
        self.assertEqual(wf.load_state(job)['flags']['article_production_step'],'titles')

    def test_p0_completed_pack_must_contain_actual_published_body(self):
        job,delivery,_=self.publish('p0');body=Path(delivery['markdown']).read_text()
        with patch.object(wf,'read_reference_member',return_value=body.encode()):
            frozen=revisions.validate_completed_manuscript(wf,job,p0=True)
        self.assertEqual(frozen['base_markdown'],self.fixture.fixture.final)
        self.assertEqual(publication.body_only(frozen['base_markdown']),body)
        with patch.object(wf,'read_reference_member',return_value=self.fixture.fixture.final.encode()):
            with self.assertRaisesRegex(ValueError,'资料包正文'):revisions.validate_completed_manuscript(wf,job,p0=True)

    def test_p0_pack_commit_copies_body_binding_without_adopting_title(self):
        job,delivery,_=self.publish('p0')
        with patch.object(wf,'create_next_reference_pack_version',return_value={"readiness":{"p0_ready":True},"pack_version":4}) as commit:
            wf.commit_p0_pack(job,delivery)
        artifacts=commit.call_args.kwargs['artifacts']
        import json
        record=json.loads(artifacts[wf.P0_MEMBERS['p0_record']])
        self.assertNotIn('canonical_title_id',record)
        self.assertEqual(record['publication'],wf.read_json(Path(delivery['publication'])))
        self.assertEqual(Path(artifacts[wf.P0_MEMBERS['p0_brand_article']]).read_text(),Path(delivery['markdown']).read_text())
        Path(delivery['markdown']).write_text(Path(delivery['markdown']).read_text()+'new unsupported text')
        with patch.object(wf,'create_next_reference_pack_version') as commit:
            with self.assertRaises(wf.WorkflowError):wf.commit_p0_pack(job,delivery)
            commit.assert_not_called()

    def test_p0_record_schema_accepts_legacy_and_precisely_binds_optional_publication(self):
        import json
        from shared.scripts.validate_json_instance import validate_instance
        schema_path=wf.ROOT/'shared/p0_record.schema.json'
        schema=json.loads(schema_path.read_text())
        errors=lambda value: validate_instance(value,schema,schema_path)
        base={'schema_version':'4.11','artifact_type':'frontmind_p0_record','pack_id':'rp_0123456789abcdef',
              'source_pack_version':11,'pack_version':12,'route':'create','created_at':'2026-09-15T00:00:00Z','paths':{}}
        self.assertEqual(errors(base),[])
        job,delivery,_=self.publish('p0')
        binding=wf.read_json(Path(delivery['publication']))
        current={**base,'publication':binding}
        self.assertEqual(errors(current),[])
        _,_,historical_binding=publication._legacy_publication(self.fixture.fixture.final,titles(),p0=True)
        historical_binding.update({key:binding[key] for key in ('finalized_result_file_sha256','titles_result_file_sha256')})
        historical={**base,'canonical_title_id':'media_title_06','publication':historical_binding}
        self.assertEqual(errors(historical),[])
        for invalid in ({**base,'canonical_title_id':'media_title_06'},
                        {**base,'publication':historical_binding},
                        {**current,'canonical_title_id':'media_title_06'},
                        {**current,'canonical_title_id':'decision_title_01'},
                        {**current,'publication':{**binding,'published_markdown_sha256':'bad'}},
                        {**current,'publication':{**binding,'extra_unknown':'not allowed'}}):
            with self.subTest(invalid=invalid):
                self.assertTrue(errors(invalid))

    def test_completion_rejects_missing_tampered_publication_and_title_records(self):
        job,delivery,_=self.publish();original=wf.read_json(Path(delivery['publication']))
        wf.atomic_json(Path(delivery['publication']),{**original,'published_markdown_sha256':'tampered'})
        with self.assertRaises(ValueError):revisions.validate_completed_manuscript(wf,job,p0=False)
        wf.atomic_json(Path(delivery['publication']),original)
        state=wf.load_state(job);state['metadata']['delivery'].pop('publication');wf.save_state(job,state)
        with self.assertRaisesRegex(ValueError,'缺少独立发布来源'):revisions.validate_completed_manuscript(wf,job,p0=False)

    def test_completed_legacy_remains_readable_without_rewriting(self):
        job=self.fixture.completed('article')
        before={str(path.relative_to(job)):path.read_bytes() for path in job.rglob('*') if path.is_file()}
        frozen=revisions.validate_completed_manuscript(wf,job,p0=False)
        self.assertEqual(frozen['base_source'],'previous_glm_final')
        self.assertEqual(frozen['base_markdown'],self.fixture.fixture.final)
        self.assertEqual(before,{str(path.relative_to(job)):path.read_bytes() for path in job.rglob('*') if path.is_file()})


if __name__=='__main__':unittest.main()
