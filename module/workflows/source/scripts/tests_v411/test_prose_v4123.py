"""New P0 publication roles, exact full-input transport and offline isolation."""
import json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from shared import brand_prose,p0_style,model_runtime as rt,docx_system_fonts
from shared.editorial_contracts import EditorialContractError
from scripts.tests_v411 import test_p0_context_v4122 as context_fixture
ROOT=Path(__file__).resolve().parents[2]

class ProseContractTests(unittest.TestCase):
    def fixture(self):
        f=context_fixture.DeepContextTests();f.setUp();self.addCleanup(f.doCleanups)
        f.state['metadata']['p0_style_contract']=p0_style.P0_STYLE_CONTRACT_VERSION
        return f
    def test_all_five_actual_prompts_and_provider_systems_use_new_roles(self):
        f=self.fixture()
        for stage,prompt in f.prompts().items():
            action='p0_'+('draft' if stage=='article' else stage)
            self.assertEqual(prompt.splitlines()[1],brand_prose.MARKER)
            self.assertIn(f.examples,prompt)
            payload=rt.build_payload(action,prompt)
            system=payload['instructions'] if action in rt.HOST_ACTIONS else payload['messages'][0]['content']
            self.assertIn(brand_prose.CORE,system)
            self.assertIn(brand_prose.ROLES[action.removeprefix('p0_')],system)
            actual_input=payload['input'][0]['content'] if action in rt.HOST_ACTIONS else payload['messages'][1]['content']
            self.assertIn(f.examples,actual_input)
            if stage!='blueprint':
                self.assertIn(f.blueprint['writing_material_markdown'],actual_input)
                self.assertNotIn('WHOLE_RESEARCH_MUST_NOT_LEAK',actual_input)
    def test_old_p0_and_question_prompts_do_not_receive_new_prose_marker(self):
        f=self.fixture();f.state['metadata']['p0_style_contract']='frontmind-p0-style/4.12.2'
        self.assertTrue(all(brand_prose.MARKER not in p for p in f.prompts().values()))
        f.state['job_kind']='article';f.state['metadata']={}
        self.assertTrue(all(brand_prose.MARKER not in p for p in f.prompts(p0=False).values()))
    def test_stage_system_is_bound_in_cache_fingerprint(self):
        f=self.fixture();p=f.prompts()['article'];a=rt.request_fingerprint('p0_draft',p)
        self.assertNotEqual(a,rt.request_fingerprint('p0_draft',p.replace(brand_prose.MARKER,'')))
    def test_prose_policy_adds_no_runtime_actions(self):
        self.assertEqual(len(rt.HOST_ACTIONS - {"article_polish", "article_editorial_preparation"}),11);self.assertEqual(len(rt.DEEPSEEK_ACTIONS - {"p0_repair", "article_repair"}),7)
        self.assertEqual(set(brand_prose.ROLES),{'blueprint','draft','edit','style','finalize'})
    def test_explicit_offline_examples_never_call_network_and_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp);state={'flags':{'offline_fixture':True},'metadata':{'p0_style_contract':p0_style.P0_STYLE_CONTRACT_VERSION}}
            (job/'job_state.json').write_text(json.dumps(state))
            with patch.object(p0_style,'_fetch',side_effect=AssertionError('network forbidden')):
                rows=p0_style.job_examples(ROOT,job,freeze=True)
            self.assertEqual(len(rows),2)
            manifest=json.loads((job/'inputs/p0_style_examples/manifest.json').read_text())
            self.assertEqual(manifest['execution_mode'],'offline_fixture')
            state['flags']['offline_fixture']=False;(job/'job_state.json').write_text(json.dumps(state))
            with self.assertRaises(EditorialContractError) as ctx:p0_style.job_examples(ROOT,job)
            self.assertEqual(ctx.exception.code,'p0_fixture_mode_mismatch')
    def test_production_examples_cannot_use_fixture_on_network_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp);(job/'job_state.json').write_text(json.dumps({'flags':{},'metadata':{'p0_style_contract':p0_style.P0_STYLE_CONTRACT_VERSION}}))
            with patch.object(p0_style,'_fetch',side_effect=OSError('network unavailable')) as fetch:
                with self.assertRaises(OSError):p0_style.job_examples(ROOT,job,freeze=True)
            self.assertTrue(fetch.called);self.assertFalse((job/'inputs/p0_style_examples/manifest.json').exists())
    def test_system_font_export_contains_no_font_binary_and_declares_dependency(self):
        from docx import Document
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'sample.docx';d=Document();d.add_paragraph('一航软件测评中心');d.save(p)
            report=docx_system_fonts.enforce_docx_font_contract(p)
            self.assertTrue(report['passed']);self.assertTrue(report['external_font_dependency']);self.assertFalse(report['visual_quality_verified'])
            with zipfile.ZipFile(p) as z:self.assertFalse(any(Path(n).suffix in docx_system_fonts.FONT_EXTENSIONS for n in z.namelist()))
    def test_skill_yaml_is_not_interrupted_by_current_contract(self):
        s=(ROOT/'00.FrontMind内容制作总控.skill/SKILL.md').read_text()
        front=s.split('---',2)[1];self.assertIn('name:',front);self.assertNotIn('##',front)

if __name__=='__main__':unittest.main()
