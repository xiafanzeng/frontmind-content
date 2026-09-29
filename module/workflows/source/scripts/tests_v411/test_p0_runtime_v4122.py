"""New-P0 dispatch and blocked delivery; no production model calls."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts.tests_v411 import test_p0_style_controller_v4121 as fixture
from shared import p0_style, model_runtime as runtime, editorial_contracts as contracts

wf = fixture.wf


class P0RuntimeV4122Tests(unittest.TestCase):
    def test_runtime_dispatch_changes_only_prefixed_p0(self):
        legacy=runtime.legacy_managed_routes();legacy.__enter__();self.addCleanup(legacy.__exit__,None,None,None)
        prefix = runtime.P0_DEEP_PROMPT_PREFIX
        old = runtime.build_payload('p0_finalize', 'legacy input')
        new = runtime.build_payload('p0_finalize', prefix + 'new input')
        def result_schema(payload):
            tools = payload['agent']['tools'] if 'agent' in payload else payload['tools']
            tool = next(t for t in tools if t.get('name') == 'submit_result' or (t.get('function') or {}).get('name') == 'submit_result')
            return (tool.get('input_schema') or tool.get('parameters') or tool['function']['parameters'])['properties']['result']
        self.assertNotIn('quality_review', result_schema(old)['required'])
        self.assertIn('quality_review', result_schema(new)['required'])
        self.assertFalse(runtime._deep_prompt('article_finalize', prefix + 'not P0'))
        self.assertFalse(runtime._deep_prompt('p0_finalize', 'user text ' + prefix))
        self.assertEqual(runtime.profile_for('p0_finalize')['model'], 'glm-5.3')
        self.assertEqual(runtime.profile_for('p0_style')['model'], 'deepseek-v4-pro')

    def test_current_commission_is_bound_before_first_blueprint(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        job = Path(temp.name)
        state = wf.make_state('new', 'p0'); state['revision'] = 2
        args = SimpleNamespace(revision=2, p0_route='create', p0_blueprint_edits='本次重新选材并充分展开四节。', blueprint_edits=None, example_file=[], example_url=[])
        with patch.object(wf, 'load_state', return_value=state), patch.object(wf, 'save_state') as save, patch.object(wf, 'archive_blueprint_edit_outline'), patch.object(wf, 'set_status'), patch.object(wf, 'drive', return_value=0):
            self.assertEqual(wf.submit_p0_route(args, job), 0)
        self.assertEqual(state['decisions']['blueprint_edits'], args.p0_blueprint_edits)
        self.assertEqual(state['metadata']['blueprint_material_input_mode'], wf.writing_requirements.BLUEPRINT_MATERIAL_INPUT_MODE)
        self.assertTrue(save.called)

    def test_incomplete_quality_blocks_titles_and_delivery(self):
        f = fixture.P0StyleControllerTests(); f.setUp(); self.addCleanup(f.doCleanups)
        job = f.job(); state = wf.load_state(job)
        state['metadata']['p0_style_contract'] = p0_style.P0_STYLE_CONTRACT_VERSION
        wf.save_state(job, state)
        for _ in range(3):
            f.step(job)
        original = f.action
        def action(job, name, prompt, *, fixture_builder):
            if name != 'p0_finalize':
                return original(job, name, prompt, fixture_builder=fixture_builder)
            candidate = contracts.prepare_finalize_input(wf, job, p0=True)['candidate_markdown']
            quality = p0_style.fixture_quality_review(candidate)
            quality['article_quality']['passed'] = False
            quality['article_quality']['checks'][1]['passed'] = False
            quality['unresolved_issues'] = ['重点仍是服务目录，返回写作补足解释。']
            return wf.validate_action_result(job, name, {'outcome': 'incomplete', 'article_markdown': '', 'editorial_notes': [], 'reason': quality['unresolved_issues'][0], 'quality_review': quality})
        with patch.object(wf, 'ensure_action', side_effect=action), self.assertRaisesRegex(wf.WorkflowError, '宿主验读未完成'):
            f.step(job)
        state = wf.load_state(job)
        self.assertEqual(state['pending_action']['error']['code'], 'host_incomplete')
        self.assertEqual(state['flags']['p0_production_step'], 'finalize')
        self.assertNotIn('p0_titles', f.calls)
        self.assertFalse((job / 'production/p0_finalized.json').exists())
        self.assertNotIn('delivery', state['metadata'])
