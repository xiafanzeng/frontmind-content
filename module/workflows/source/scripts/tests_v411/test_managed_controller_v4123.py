"""Current Managed host + Pro wire adapters in legacy-P0 and question pipelines.

Synthetic model responses and DOCX stub: this verifies body/provenance routing,
not live service access, publication quality or rendered page quality.
"""
import json,unittest
from unittest.mock import patch
from shared import model_runtime as rt
from scripts.tests_v411 import test_controller_runtime_v4114 as fixture
from scripts.tests_v411.test_managed_runtime_v4123 import ManagedServer
from scripts.tests_v411.test_model_runtime import FakeTools

# 作者档位跟随本包 config/deepseek.json 的显式覆盖（用户2026-09-22定为high；缺省默认max）。
# 断言验证配置一致性，而不是钉死某一档位。
import json as _json
from pathlib import Path as _Path
try:
    _cfgf = _Path(__file__).resolve().parents[2] / 'config' / 'deepseek.json'
    _WRITER_EFFORT = (_json.loads(_cfgf.read_text()).get('reasoning_effort') or 'max') if _cfgf.exists() else 'max'
except Exception:
    _WRITER_EFFORT = 'max'


class ManagedControllerTests(unittest.TestCase):
    def setUp(self):
        legacy=rt.legacy_managed_routes();legacy.__enter__();self.addCleanup(legacy.__exit__,None,None,None)
    def run_route(self,prefix):
        current_profile=rt.profile_for
        f=fixture.ControllerRuntimeIntegration();f.setUp();self.addCleanup(f.doCleanups)
        wf=fixture.wf
        override=patch.object(rt,'profile_for',side_effect=current_profile);override.start();self.addCleanup(override.stop)
        servers=[]
        def execute(package,job,action,prompt,validator,**kwargs):
            if action in rt.DEEPSEEK_ACTIONS:return f.offline_run(package,job,action,prompt,validator,**kwargs)
            if action.endswith('_finalize'):
                result={'outcome':'revised','article_markdown':f.final,'editorial_notes':['改写开篇。'],'reason':''}
            else:
                source=wf.read_json(job/'production'/f'{prefix}_titles.json')
                titles=wf.validate_title_map(source,p0=prefix=='p0')
                result={'outcome':'revised','candidates':[{'title':t['title_text'],'angle':'业务阅读入口'} for t in titles['options']],
                        'canonical_title_id':'title_13' if prefix=='p0' else 'title_04','title_notes':['补充实际角度。'],'reason':''}
            server=ManagedServer(result=result);servers.append(server)
            return rt.run_action(package,job,action,prompt,validator,transport=server,offline=True,host_tools=FakeTools(),**kwargs)
        job=f.job(prefix)
        with patch.object(wf,'run_action',side_effect=execute):
            for _ in range(6):f.run_step(job,prefix=='p0')
        self.assertEqual((job/'deliverables'/f'{prefix}.md').read_text(),wf.title_publication.body_only(f.final))
        for stage in ('finalize','title_review'):
            record=rt.action_record(job,f'{prefix}_{stage}')
            self.assertEqual(record['requested_configuration']['wire_api'],'zhipu_managed_agents')
            self.assertEqual(record['execution_mode'],'offline_simulated')
            self.assertEqual(record['status'],'succeeded')
        for stage in ('draft','edit','titles'):
            record=rt.action_record(job,f'{prefix}_{stage}')
            self.assertEqual(record['requested_configuration']['model'],'deepseek-v4-pro')
            self.assertEqual(record['requested_configuration']['reasoning_effort'],_WRITER_EFFORT)
        self.assertEqual(len(servers),2)
    def test_legacy_p0_rerun_uses_current_managed_backend(self):self.run_route('p0')
    def test_question_pipeline_uses_managed_final_and_title_review(self):self.run_route('article')

if __name__=='__main__':unittest.main()
