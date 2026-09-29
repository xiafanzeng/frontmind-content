import json
import hashlib
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
from host_tools import HostTools, ToolError
from example_acquisition import ExampleStore, AcquisitionError, ArticleParser, page_problem


class HostToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.package = self.root / 'package'; self.package.mkdir()
        self.job = self.root / 'job'; self.job.mkdir()
        (self.job/'inputs').mkdir()
        (self.job/'inputs'/'company_facts.md').write_text('Brand own facts', encoding='utf-8')
    def tearDown(self):
        self.tmp.cleanup()
    def tools(self,action='p0_blueprint'):
        return HostTools(self.package,self.job,action)

    def test_xty_credentials_never_become_materials_or_tool_text(self):
        (self.package / 'config').mkdir()
        secret = 'TEST-XTY-CREDENTIAL-NOT-MATERIAL'
        (self.package / 'config/xty.json').write_text(json.dumps({'api_key': secret}))
        (self.job / 'inputs/xty.json').write_text(json.dumps({'api_key': secret}))
        tools = self.tools()
        self.assertIn(secret, tools._secret_values)
        self.assertFalse(any(row['path'].endswith('xty.json') for row in tools.artifacts.values()))
        with self.assertRaises(ToolError):
            tools.execute('read_material', {'artifact_id': 'inputs/xty.json'})

    def activate_manuscript_revision(self, prefix, base):
        record_dir = self.job / 'production/manuscript_revisions'
        record_dir.mkdir(parents=True, exist_ok=True)
        record_path = record_dir / f'{prefix}-revision.json'
        record = {
            'contract': 'frontmind-manuscript-revision/4.11.5',
            'prefix': prefix,
            'base_markdown': base,
            'base_sha256': hashlib.sha256(base.encode('utf-8')).hexdigest(),
        }
        record_path.write_text(json.dumps(record), encoding='utf-8')
        state = {'metadata': {prefix + '_manuscript_revision': {
            'path': record_path.relative_to(self.job).as_posix(),
            'sha256': hashlib.sha256(record_path.read_bytes()).hexdigest(),
        }}}
        (self.job / 'job_state.json').write_text(json.dumps(state), encoding='utf-8')
    def test_p0_cannot_read_legacy_positioning_projection_but_questions_can(self):
        path = self.job/'inputs/own_brand_context.md'
        path.write_text('OLD_CORE_UNCONDITIONAL_CERTIFICATE_CLAIM', encoding='utf-8')
        for action in ('p0_example_discovery', 'p0_blueprint', 'p0_finalize'):
            tools = self.tools(action)
            self.assertFalse(any(r['path'].endswith('own_brand_context.md') for r in tools.artifacts.values()))
            self.assertEqual(tools.execute('search_materials', {'query': 'OLD_CORE_UNCONDITIONAL_CERTIFICATE_CLAIM'})['total_matches'], 0)
            with self.assertRaises(ToolError):
                tools.execute('read_material', {'artifact_id': 'inputs/own_brand_context.md'})
        tools = self.tools('article_blueprint')
        self.assertEqual(tools.execute('read_material', {'artifact_id': 'inputs/own_brand_context.md'})['text'], 'OLD_CORE_UNCONDITIONAL_CERTIFICATE_CLAIM')
    def test_edit_candidates_cannot_be_registered_or_used_instead_of_source_reading(self):
        source='inputs/company_facts.md'
        for prefix in ('p0','article'):
            path=self.job/'inputs'/f'{prefix}_blueprint_edit_outline.json'
            path.write_text(json.dumps({'revision_candidate':{'writing_material_markdown':'FROZEN_EDIT_CANDIDATE',
                            'writing_material_sources':[{'source_ref':source,'use':'business'}]}}))
        for action in ('p0_blueprint','article_blueprint'):
            tools=self.tools(action)
            for prefix in ('p0','article'):
                relative=f'inputs/{prefix}_blueprint_edit_outline.json'
                self.assertFalse(any(row['path']==relative for row in tools.artifacts.values()))
                with self.assertRaises(ToolError):tools.register_file(self.job/relative)
                with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':relative})
                with self.assertRaises(ToolError):tools.validate_result_sources({'writing_material_sources':[relative]})
            self.assertEqual(tools.execute('search_materials',{'query':'FROZEN_EDIT_CANDIDATE'})['total_matches'],0)
            tools.record_inline_inputs([{'role':'user','content':'Brand own facts\nFROZEN_EDIT_CANDIDATE'}])
            with self.assertRaises(ToolError):tools.validate_result_sources({'writing_material_sources':[source]})
            tools.execute('read_material',{'artifact_id':source})
            self.assertTrue(tools.validate_result_sources({'writing_material_sources':[source]}))
    def test_directory_bound_pack_respects_p0_scope_and_adjacent_conditions(self):
        pack=self.job/'00_input/reference_pack'
        for name in ['materials','registries','strategy','research/brand_market']:(pack/name).mkdir(parents=True,exist_ok=True)
        (pack/'materials/service.md').write_text('A service with dated conditions',encoding='utf-8')
        (pack/'strategy/core_positioning.json').write_text('competitive strategy',encoding='utf-8')
        (pack/'research/brand_market/competitor.md').write_text('competitor background',encoding='utf-8')
        (pack/'registries/source_registry.json').write_text(json.dumps({'sources':[{'file_path':'materials/service.md','source_type':'first_party_internal','published_at':'2025-08-23','scope':'service-specific','needs_verification':True}]}),encoding='utf-8')
        tools=self.tools(); paths=[r['path'] for r in tools.artifacts.values()]
        self.assertFalse(any('strategy/' in x or 'brand_market/' in x for x in paths))
        ident=next(k for k,r in tools.artifacts.items() if r['path'].endswith('materials/service.md'))
        result=tools.execute('read_material',{'artifact_id':ident})
        self.assertEqual(result['source_conditions']['source_date'],'2025-08-23')
        self.assertEqual(result['source_conditions']['scope'],'service-specific')
        self.assertTrue(result['source_conditions']['needs_verification'])
    def test_selected_acquired_example_is_required_outside_examples_directory(self):
        record=ExampleStore(self.job).import_user_text('FIRST MIDDLE LAST','Chosen full example')
        (self.job/'examples/p0').mkdir(parents=True)
        (self.job/'examples/p0/index.json').write_text(json.dumps({'examples':[record]}),encoding='utf-8')
        (self.job/'job_state.json').write_text(json.dumps({'selected_example_route':'top20'}),encoding='utf-8')
        tools=self.tools();ident=record['artifact_id']
        self.assertTrue(tools.artifacts[ident]['required'])
        with self.assertRaises(ToolError):tools.validate_complete_reads()
        tools.execute('read_material',{'artifact_id':ident})
        self.assertTrue(tools.validate_complete_reads())
    def test_production_history_not_registered_or_required(self):
        path=self.job/'production/history/old/p0_draft.json';path.parent.mkdir(parents=True);path.write_text('{"article_markdown":"old"}')
        current=self.job/'production/p0_draft.json';current.write_text('{"article_markdown":"current"}')
        tools=self.tools('p0_finalize')
        self.assertFalse(any('/history/' in r['path'] for r in tools.artifacts.values()))
        self.assertEqual(len(tools._required),1)

    def test_manuscript_revision_requires_frozen_base_instead_of_historical_draft(self):
        for prefix in ('p0', 'article'):
            with self.subTest(prefix=prefix):
                production = self.job / 'production'; production.mkdir(exist_ok=True)
                (production / f'{prefix}_draft.json').write_text(json.dumps({'article_markdown': 'HISTORICAL DRAFT'}), encoding='utf-8')
                (production / f'{prefix}_edited.json').write_text(json.dumps({'article_markdown': 'CURRENT E8 CANDIDATE'}), encoding='utf-8')
                base = f'# Frozen {prefix}\n\nThe previous GLM final manuscript.'
                self.activate_manuscript_revision(prefix, base)
                tools = self.tools(prefix + '_finalize')
                draft = next(row for row in tools.artifacts.values() if row['path'] == f'production/{prefix}_draft.json')
                self.assertFalse(draft['required'])
                frozen = [row for row in tools.artifacts.values() if row.get('title') == f'{prefix} frozen manuscript base']
                self.assertEqual(len(frozen), 1)
                self.assertTrue(frozen[0]['required'])
                tools.record_inline_inputs([{'role': 'user', 'content': 'Read the frozen base and current candidate:\n' + base + '\nCURRENT E8 CANDIDATE'}])
                self.assertTrue(tools.validate_complete_reads())

    def test_manuscript_revision_without_frozen_base_fails_closed_for_both_routes(self):
        for prefix in ('p0', 'article'):
            with self.subTest(prefix=prefix):
                production = self.job / 'production'; production.mkdir(exist_ok=True)
                (production / f'{prefix}_draft.json').write_text(json.dumps({'article_markdown': 'HISTORICAL DRAFT'}), encoding='utf-8')
                (self.job / 'job_state.json').write_text(json.dumps({'metadata': {
                    prefix + '_manuscript_revision': {'path': 'production/manuscript_revisions/missing.json', 'sha256': 'missing'}
                }}), encoding='utf-8')
                with self.assertRaises(ToolError):
                    self.tools(prefix + '_finalize')

    def test_manuscript_revision_requires_full_current_candidate_for_both_routes(self):
        for prefix in ('p0', 'article'):
            with self.subTest(prefix=prefix):
                production = self.job / 'production'; production.mkdir(exist_ok=True)
                (production / f'{prefix}_edited.json').write_text(json.dumps({'article_markdown': 'CURRENT E8 CANDIDATE'}), encoding='utf-8')
                base = f'# Frozen {prefix}\n\nThe previous GLM final manuscript.'
                self.activate_manuscript_revision(prefix, base)
                tools = self.tools(prefix + '_finalize')
                tools.record_inline_inputs([{'role': 'user', 'content': base}])
                with self.assertRaises(ToolError):
                    tools.validate_complete_reads()

    def test_revision_format_error_fallback_can_read_frozen_base_without_edited_file(self):
        production = self.job / 'production'; production.mkdir()
        (production / 'p0_draft.json').write_text(json.dumps({'article_markdown': 'HISTORICAL DRAFT'}), encoding='utf-8')
        (production / 'p0_edit_failure.json').write_text(json.dumps({'code': 'invalid_result_json'}), encoding='utf-8')
        base = '# Frozen p0\n\nThe previous GLM final manuscript.'
        self.activate_manuscript_revision('p0', base)
        tools = self.tools('p0_finalize')
        tools.record_inline_inputs([{'role': 'user', 'content': base}])
        self.assertTrue(tools.validate_complete_reads())

    def test_restored_revision_checkpoint_does_not_readd_historical_draft(self):
        production = self.job / 'production'; production.mkdir()
        (production / 'p0_draft.json').write_text(json.dumps({'article_markdown': 'HISTORICAL DRAFT'}), encoding='utf-8')
        (production / 'p0_edited.json').write_text(json.dumps({'article_markdown': 'CURRENT E8 CANDIDATE'}), encoding='utf-8')
        base = '# Frozen p0\n\nThe previous GLM final manuscript.'
        self.activate_manuscript_revision('p0', base)
        fresh = self.tools('p0_finalize')
        saved = fresh.export_state()
        draft_id = next(key for key, row in fresh.artifacts.items() if row['path'] == 'production/p0_draft.json')
        saved['required'].append(draft_id)
        restored = self.tools('p0_finalize')
        restored.restore_state(saved)
        self.assertNotIn(draft_id, restored._required)
        restored.record_inline_inputs([{'role': 'user', 'content': 'Frozen base and candidate:\n' + base + '\nCURRENT E8 CANDIDATE'}])
        self.assertTrue(restored.validate_complete_reads())
    def test_configured_credential_in_source_cannot_enter_context(self):
        (self.package/'config').mkdir();(self.package/'config/zhipu.json').write_text(json.dumps({'api_key':'secret-unique-fixture'}))
        path=self.job/'inputs/accidental.md';path.write_text('accidental secret-unique-fixture text')
        tools=self.tools();ident=next(k for k,r in tools.artifacts.items() if r['path'].endswith('accidental.md'))
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':ident})
        with self.assertRaises(ToolError):tools.execute('search_materials',{'query':'accidental'})
    def test_exact_registered_id_path_title_and_filename_resolve_same_source(self):
        path=self.job/'inputs/company-facts.md';path.write_text('Exact original facts',encoding='utf-8')
        tools=self.tools();ident=tools.register_file(path.resolve(),title='企业事实原文')
        for ref in [ident,'inputs/company-facts.md','company-facts.md','企业事实原文']:
            result=tools.execute('read_material',{'artifact_id':ref})
            self.assertEqual(result['artifact_id'],ident)
            self.assertEqual(result['text'],'Exact original facts')
    def test_ambiguous_filename_lists_canonical_candidates_without_read(self):
        for folder in ['inputs/a','inputs/b']:
            path=self.job/folder/'same.md';path.parent.mkdir();path.write_text(folder,encoding='utf-8')
        tools=self.tools()
        with self.assertRaises(ToolError) as error:tools.execute('read_material',{'artifact_id':'same.md'})
        message=str(error.exception);self.assertIn('ambiguous',message)
        for record in tools.artifacts.values():
            if record['path'].endswith('/same.md'):self.assertIn(record['artifact_id'],message)
        self.assertEqual(tools.read_ranges,{})
        self.assertEqual(tools.dependencies,{})
    def test_constructed_hash_id_gives_advice_without_substitution(self):
        path=self.job/'inputs/0031da436eeab67d_company-profile.md';path.write_text('Actual source',encoding='utf-8')
        tools=self.tools();record=next(r for r in tools.artifacts.values() if r['path'].endswith(path.name))
        with self.assertRaises(ToolError) as error:tools.execute('read_material',{'artifact_id':'file_0031da436eeab67d'})
        self.assertIn(record['artifact_id'],str(error.exception));self.assertIn('never build one',str(error.exception))
        self.assertEqual(tools.dependencies,{})
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':'company-profile'})
    def test_search_and_terms_across_content_title_and_path(self):
        path=self.job/'inputs/一航软件测评中心.md';path.write_text('取得 CMA，相关测试认可范围涉及 CNAS。',encoding='utf-8')
        (self.job/'inputs/missing-term.md').write_text('一航软件测评中心 CMA only',encoding='utf-8')
        tools=self.tools();result=tools.execute('search_materials',{'query':'一航软件测评中心 CMA CNAS'})
        self.assertEqual(result['total_matches'],1);self.assertTrue(result['results'][0]['path'].endswith(path.name))
        self.assertEqual(result['query_terms'],['一航软件测评中心','cma','cnas'])
        self.assertEqual(tools.read_ranges,{})
    def test_search_binary_filename_returns_extraction_instruction(self):
        path=self.job/'inputs/CCRC证书.pdf';path.write_bytes(b'%PDF-1.4 offline filename fixture')
        tools=self.tools();result=tools.execute('search_materials',{'query':'CCRC证书'})
        self.assertEqual(result['total_matches'],1);self.assertTrue(result['results'][0]['requires_extraction'])
        self.assertEqual(result['results'][0]['snippet'],'');self.assertIsNone(result['results'][0]['offset'])
    def test_material_inventory_default_is_compact_and_paginated(self):
        for index in range(30):(self.job/'inputs'/f'file-{index:02d}.md').write_text(str(index))
        tools=self.tools();result=tools.execute('list_materials',{})
        self.assertEqual(len(result['artifacts']),25);self.assertEqual(result['next_offset'],25)
        self.assertEqual(result['total'],31)
        self.assertNotIn('sha256',result['artifacts'][0]);self.assertNotIn('source_conditions',result['artifacts'][0])
    def test_result_sources_require_body_read_not_search_or_registration(self):
        tools=self.tools();ident=tools.register_text('A source body with actual facts','Facts')
        value={'writing_material_sources':[{'source_ref':ident,'use':'facts'}]}
        with self.assertRaises(ToolError):tools.validate_result_sources(value)
        tools.execute('search_materials',{'query':'actual facts'})
        self.assertIn(ident,tools.dependencies)
        with self.assertRaises(ToolError):tools.validate_result_sources(value)
        tools.execute('read_material',{'artifact_id':ident,'offset':2,'limit':8})
        self.assertTrue(tools.validate_result_sources(value))
    def test_result_sources_reject_existing_unregistered_provider_file(self):
        path=self.job/'provider/fake/result.json';path.parent.mkdir(parents=True);path.write_text('{"article_markdown":"private result"}')
        tools=self.tools()
        with self.assertRaises(ToolError):tools.validate_result_sources({'writing_material_sources':[{'source_ref':'provider/fake/result.json','use':'facts'}]})
    def test_result_sources_accept_parent_when_derived_body_was_read(self):
        path=self.job/'inputs/source.docx'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Actual source text.</w:t></w:r></w:p></w:body></w:document>')
        tools=self.tools();original=next(r['artifact_id'] for r in tools.artifacts.values() if r['path'].endswith('source.docx'))
        with patch.object(tools,'_api',side_effect=AssertionError('text extraction must not invoke OCR')):
            extracted=tools.execute('extract_document',{'artifact_id':original})
        value={'writing_material_sources':[{'source_ref':original,'use':'source facts'}]}
        with self.assertRaises(ToolError):tools.validate_result_sources(value)
        tools.execute('read_material',{'artifact_id':extracted['artifact_id']})
        self.assertTrue(tools.validate_result_sources(value))
        saved=tools.export_state();restored=self.tools();restored.restore_state(saved)
        self.assertTrue(restored.validate_result_sources(value))
    def test_result_sources_empty_page_is_not_source_read(self):
        tools=self.tools();ident=tools.register_text('Nonempty facts','Facts')
        tools.execute('read_material',{'artifact_id':ident,'offset':14})
        with self.assertRaises(ToolError):tools.validate_result_sources({'writing_material_sources':[ident]})
    def test_blueprint_generation_excludes_own_outputs_without_changing_input_fingerprint(self):
        for action in ['p0_blueprint','article_blueprint']:
            with self.subTest(action=action):
                for directory in ['blueprints','production']:
                    parent=self.job/directory
                    if parent.exists():
                        import shutil
                        shutil.rmtree(parent)
                before=self.tools(action).fingerprint_dependencies()
                (self.job/'blueprints').mkdir();(self.job/'production').mkdir()
                (self.job/'blueprints'/f"{action}.json").write_text('{"old":"complete prior blueprint"}')
                (self.job/'production/old_draft.json').write_text('{"article_markdown":"downstream draft"}')
                (self.job/'production/p0_draft.json').write_text('{"article_markdown":"downstream draft"}')
                tools=self.tools(action)
                self.assertEqual(tools.fingerprint_dependencies(),before)
                (self.job/"blueprints"/f"{action}.json").write_text('{"new":"just-written generated blueprint"}')
                self.assertEqual(self.tools(action).fingerprint_dependencies(),before)
                self.assertFalse(any(r['path'].startswith(('blueprints/','production/')) for r in tools.artifacts.values()))
                with self.assertRaises(ToolError):tools.register_file('blueprints/'+action+'.json')
                with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':'blueprints/'+action+'.json'})
    def test_restore_cannot_reintroduce_blueprint_own_output(self):
        (self.job/'blueprints').mkdir();(self.job/'production').mkdir()
        (self.job/'blueprints/p0_blueprint.json').write_text('{"old":"prior blueprint"}')
        (self.job/'production/p0_draft.json').write_text('{"article_markdown":"draft"}')
        saved=self.tools('p0_finalize').export_state()
        saved['action']='p0_blueprint'
        with self.assertRaises(ToolError):self.tools('p0_blueprint').restore_state(saved)
        clean=self.tools('p0_blueprint').export_state();clean['schema']='frontmind-host-tools/v1'
        with self.assertRaises(ToolError):self.tools('p0_blueprint').restore_state(clean)
    def test_finalize_retains_upstream_blueprint_and_manuscripts(self):
        (self.job/'blueprints').mkdir();(self.job/'production').mkdir()
        (self.job/'blueprints/p0_blueprint.json').write_text('{"confirmed":"blueprint"}')
        (self.job/'production/p0_draft.json').write_text('{"article_markdown":"draft"}')
        tools=self.tools('p0_finalize');paths={r['path'] for r in tools.artifacts.values()}
        self.assertIn('blueprints/p0_blueprint.json',paths);self.assertIn('production/p0_draft.json',paths)
    def test_article_blueprint_keeps_pack_p0_and_current_answers(self):
        (self.job/'00_input').mkdir()
        with zipfile.ZipFile(self.job/'00_input/reference_pack.zip','w') as archive:
            archive.writestr('p0/p0.md','Confirmed upstream company article')
            archive.writestr('materials/company.md','Original source')
        (self.job/'inputs/answer_01.md').write_text('Current full AI answer one')
        (self.job/'inputs/answer_02.md').write_text('Current full AI answer two')
        tools=self.tools('article_blueprint');paths={r['path'] for r in tools.artifacts.values()}
        self.assertTrue(any(path.endswith('/p0/p0.md') for path in paths))
        self.assertIn('inputs/answer_01.md',paths);self.assertIn('inputs/answer_02.md',paths)
    def test_tool_surface_is_bounded(self):
        tools=self.tools()
        self.assertEqual(len(tools.definitions()),7)
        for name in ['shell','read_file','continue','approve','submit_result']:
            with self.assertRaises(ToolError): tools.execute(name,{})
        with self.assertRaises(ToolError): tools.execute('read_material',{'artifact_id':'../secret'})
        with self.assertRaises(ToolError): tools.execute('list_materials',{'path':'/'})

    def test_absolute_job_root_path_resolves_to_registered_artifact(self):
        tools=self.tools();path=self.job/'inputs/company_facts.md'
        relative=tools.resolve_artifact('inputs/company_facts.md')
        result=tools.execute('read_material',{'artifact_id':str(path)})
        self.assertEqual(result['artifact_id'],relative['artifact_id'])
        self.assertEqual(result['text'],'Brand own facts')
        outside=self.root/'outside.md';outside.write_text('outside')
        with self.assertRaises(ToolError):tools.execute('read_material',{'artifact_id':str(outside)})

    def test_loose_answer_intake_copies_are_not_required_duplicates(self):
        (self.job/'00_input').mkdir()
        for index,suffix in ((1,'.md'),(2,'.txt')):
            text=f'Complete independent answer {index}'
            (self.job/'00_input'/f'loose_answer_{index:02d}{suffix}').write_text(text)
            (self.job/'inputs'/f'answer_{index:02d}.md').write_text(text)
        tools=self.tools('answer_analysis')
        self.assertFalse(any(r['path'].startswith('00_input/loose_answer_') for r in tools.artifacts.values()))
        self.assertEqual({tools.artifacts[k]['path'] for k in tools._required},
                         {'inputs/answer_01.md','inputs/answer_02.md'})
        with self.assertRaises(ToolError):tools.validate_complete_reads()
        tools.execute('read_material',{'artifact_id':'inputs/answer_01.md'})
        with self.assertRaises(ToolError):tools.validate_complete_reads()
        tools.execute('read_material',{'artifact_id':'inputs/answer_02.md'})
        self.assertTrue(tools.validate_complete_reads())
    def test_credential_other_job_and_symlink_denied(self):
        (self.job/'config').mkdir(); secret=self.job/'config'/'zhipu.json';secret.write_text('secret')
        sibling=self.root/'other.md';sibling.write_text('private')
        (self.job/'inputs'/'link.md').symlink_to(sibling)
        tools=self.tools()
        for path in [secret,sibling,self.job/'inputs'/'link.md']:
            with self.assertRaises(ToolError):tools.register_file(path)
        self.assertEqual(len(tools.artifacts),1)
    def test_required_full_read_cannot_use_search_or_skip_middle(self):
        tools=self.tools(); ident=tools.register_text('FIRST'+('中'*60)+'LAST','Example','example',True)
        tools.execute('search_materials',{'query':'FIRST'})
        with self.assertRaises(ToolError):tools.validate_complete_reads()
        tools.execute('read_material',{'artifact_id':ident,'offset':0,'limit':5})
        tools.execute('read_material',{'artifact_id':ident,'offset':65,'limit':4})
        with self.assertRaises(ToolError):tools.validate_complete_reads()
        tools.execute('read_material',{'artifact_id':ident,'offset':5,'limit':60})
        self.assertTrue(tools.validate_complete_reads())
    def test_actual_inline_full_bodies_satisfy_required_without_fake_tool_reads(self):
        tools=self.tools('article_finalize')
        for category in ['example','answer','manuscript']:
            tools.register_text(category+' FIRST\r\nMIDDLE\nLAST\n',category,category,True)
        tools.record_inline_inputs([{'role':'user','content':'Context\n'+'\n'.join(category+' FIRST\nMIDDLE\nLAST' for category in ['example','answer','manuscript'])+'\nEnd context'}])
        self.assertTrue(tools.validate_complete_reads())
        self.assertEqual(tools.read_ranges,{})
        self.assertEqual(len(tools.inline_reads),3)
        self.assertTrue(all(row['normalization'].startswith('CRLF/CR') for row in tools.inline_reads.values()))
    def test_inline_summary_and_assistant_claim_do_not_count_as_full_input(self):
        tools=self.tools();ident=tools.register_text('FIRST MIDDLE LAST','Example','example',True)
        tools.record_inline_inputs([{'role':'user','content':'FIRST LAST'},{'role':'assistant','content':'FIRST MIDDLE LAST'}])
        self.assertNotIn(ident,tools.inline_reads)
        with self.assertRaises(ToolError):tools.validate_complete_reads()
    def test_inline_ordinary_sources_never_replace_blueprint_original_body_reads(self):
        tools=self.tools();ident=tools.register_text('Complete facts','Facts','material',True)
        tools.record_inline_inputs([{'role':'user','content':'Complete facts'}])
        with self.assertRaises(ToolError):tools.validate_complete_reads()
        with self.assertRaises(ToolError):tools.validate_result_sources({'writing_material_sources':[ident]})
    def test_inline_manuscript_checks_complete_article_field_and_registered_hash(self):
        path=self.job/'production/p0_draft.json';path.parent.mkdir()
        path.write_text(json.dumps({'article_markdown':'# Title\n\nBody beginning middle end','metadata':'backend only'}))
        tools=self.tools('p0_finalize');ident=next(k for k,r in tools.artifacts.items() if r['path'].endswith('p0_draft.json'))
        tools.record_inline_inputs([{'role':'user','content':'Read this article:\n# Title\n\nBody beginning middle end'}])
        self.assertTrue(tools.validate_complete_reads());self.assertEqual(tools.inline_reads[ident]['field'],'article_markdown')
        path.write_text(json.dumps({'article_markdown':'changed'}))
        with self.assertRaises(ToolError):tools.record_inline_inputs([{'role':'user','content':'changed'}])
    def test_saved_inline_claim_needs_actual_messages_revalidation(self):
        tools=self.tools();ident=tools.register_text('Entire example','Example','example',True)
        messages=[{'role':'user','content':'Entire example'}];tools.record_inline_inputs(messages)
        restored=self.tools();restored.restore_state(tools.export_state())
        with self.assertRaises(ToolError):restored.validate_complete_reads()
        restored.record_inline_inputs(messages)
        self.assertTrue(restored.validate_complete_reads());self.assertIn(ident,restored.inline_reads)
    def test_read_state_resume_and_tamper(self):
        tools=self.tools(); ident=tools.register_text('ABCDEF','Answer','answer',True)
        tools.execute('read_material',{'artifact_id':ident,'offset':0,'limit':3})
        saved=tools.export_state(); restored=self.tools();restored.restore_state(saved)
        restored.execute('read_material',{'artifact_id':ident,'offset':3,'limit':3})
        self.assertTrue(restored.validate_complete_reads())
        path=self.job/tools.artifacts[ident]['path'];path.chmod(0o644);path.write_text('changed')
        with self.assertRaises(ToolError):self.tools().restore_state(saved)
    def test_new_supplement_does_not_invalidate_unread_inventory(self):
        inventory=self.job/'inputs/user_materials/index.json'
        inventory.parent.mkdir();inventory.write_text('{"items": []}')
        tools=self.tools();saved=tools.export_state()
        self.assertTrue(any(r['path']=='inputs/user_materials/index.json' for r in saved['artifacts'].values()))
        inventory.write_text('{"items": [{"path": "new.md"}]}')
        (inventory.parent/'new.md').write_text('Additional source')
        self.tools().restore_state(saved)
        (self.job/'inputs/company_facts.md').write_text('Changed original fact')
        with self.assertRaises(ToolError):self.tools().restore_state(saved)

    def test_consumed_supplement_inventory_retains_byte_checks(self):
        inventory=self.job/'inputs/user_materials/index.json'
        inventory.parent.mkdir();inventory.write_text('{"items": []}')
        tools=self.tools()
        ident=next(k for k,r in tools.artifacts.items() if r['path']=='inputs/user_materials/index.json')
        tools.execute('read_material',{'artifact_id':ident})
        saved=tools.export_state();inventory.write_text('{"items": ["changed"]}')
        with self.assertRaises(ToolError):self.tools().restore_state(saved)
    def test_p0_never_registers_strategy_or_old_p0(self):
        (self.job/'00_input').mkdir()
        with zipfile.ZipFile(self.job/'00_input'/'reference_pack.zip','w') as archive:
            archive.writestr('materials/brand.md','Own actual material')
            archive.writestr('strategy/core_positioning.json','competitor details')
            archive.writestr('research/brand_market/competitive_choice_map.md','competitors')
            archive.writestr('p0/p0.md','old manuscript')
        (self.job/'inputs'/'reference_context.md').write_text('old full projection')
        tools=self.tools(); paths=[r['path'] for r in tools.artifacts.values()]
        self.assertTrue(any('brand.md' in p for p in paths))
        self.assertFalse(any('strategy' in p or 'competitive_choice' in p or 'p0.md' in p or 'reference_context' in p for p in paths))
    def test_pack_zip_traversal_and_symlink_denied(self):
        (self.job/'00_input').mkdir()
        pack=self.job/'00_input'/'reference_pack.zip'
        with zipfile.ZipFile(pack,'w') as archive:archive.writestr('../escape.md','evil')
        with self.assertRaises(ToolError):self.tools()
        with zipfile.ZipFile(pack,'w') as archive:
            info=zipfile.ZipInfo('materials/link.md');info.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(info,'/tmp')
        with self.assertRaises(ToolError):self.tools()
    def test_model_cannot_write_arbitrary_example(self):
        tools=self.tools()
        with self.assertRaises(ToolError):tools.execute('web_read',{'url':'https://example.org','markdown':'invented'})
    def test_user_text_has_honest_provenance_and_hash(self):
        store=ExampleStore(self.job);record=store.import_user_text('First\r\nMiddle\r\nLast','User example','https://example.org')
        self.assertEqual(record['obtained_via'],'user_text');self.assertIsNone(record['final_url'])
        self.assertEqual(store.resolve(record['artifact_id'])['text_sha256'],record['text_sha256'])
        path=self.job/record['text_path'];path.chmod(0o644);path.write_text('rewritten')
        with self.assertRaises(AcquisitionError):store.resolve(record['artifact_id'])
    def test_error_login_snippet_and_unclosed_not_complete(self):
        for text in ['403 Forbidden','请登录后查看','Access denied','正常正文，阅读全文']:
            self.assertTrue(page_problem(text))
        store=ExampleStore(self.job)
        record=store.import_user_text('请登录后查看','Login page')
        with self.assertRaises(AcquisitionError):store.resolve(record['artifact_id'])
        parser=ArticleParser();parser.feed('<article><p>start</p>')
        self.assertFalse(parser.result()[1])
    def test_html_article_only_no_rewrite(self):
        parser=ArticleParser();parser.feed('<html><nav>MENU</nav><title>Title</title><div id="entry-content"><p>First.</p><p>Middle.</p><p>Last.</p></div><aside>ADS</aside></html>')
        text,complete,title=parser.result();self.assertTrue(complete);self.assertEqual(title,'Title')
        self.assertIn('First.',text);self.assertIn('Middle.',text);self.assertIn('Last.',text);self.assertNotIn('MENU',text);self.assertNotIn('ADS',text)
    def test_reader_provenance_and_flags(self):
        store=ExampleStore(self.job)
        with patch('example_acquisition.public_url',lambda x:x):
            record=store.acquire_reader('https://example.org',lambda endpoint,body:{'reader_result':{'content':'Article first\nMiddle\nLast','title':'Title','url':'https://example.org'}})
            self.assertEqual(record['obtained_via'],'zhipu_reader');self.assertEqual(record['content_type'],'application/json');store.resolve(record['artifact_id'])
            record=store.acquire_reader('https://example.org',lambda endpoint,body:{'reader_result':{'content':'Snippet','is_truncated':True}})
            with self.assertRaises(AcquisitionError):store.resolve(record['artifact_id'])

if __name__=='__main__':unittest.main()
