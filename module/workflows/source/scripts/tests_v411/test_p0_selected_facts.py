"""P0 input regression; synthetic responses do not prove factual prose quality."""
import unittest

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from shared import model_runtime, writing_context, writing_context_v14, writing_requirements


class P0SelectedFactsTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp
    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def job(self):
        job = flow.NaturalEditorFlowTests.job(self, 'p0')
        state = wf.load_state(job)
        state['metadata']['writing_mission_input_mode'] = writing_context_v14.MODE
        wf.save_state(job, state)
        return job

    def test_same_selected_facts_reach_all_writers_and_actual_editor(self):
        job = self.job()
        facts = '合成机构开展项目甲。材料仅登记项目名称，未记载操作步骤。'
        bp = wf.read_json(job / 'blueprints/p0_blueprint.json')
        bp['writing_material_markdown'] = facts
        wf.atomic_json(job / 'blueprints/p0_blueprint.json', bp)
        self.needs_revision = True
        self.finish(job, p0=True)
        for action in ('p0_draft', 'p0_edit', 'p0_style', 'p0_finalize', 'p0_repair'):
            prompt = self.prompts[action]
            self.assertIn(writing_context_v14.P0_SELECTED_FACTS_MARKER, prompt.split('\n')[:4])
            self.assertEqual(prompt.count(facts), 1, action)
            system = model_runtime._initial_messages(action, prompt)[0]['content']
            self.assertIn(writing_context_v14.P0_FACTS_GUIDANCE, system)
            if action == 'p0_finalize':
                self.assertNotIn('不核查事实', system)
                self.assertNotIn('不作事实检查', prompt)
                self.assertIn(self.body, prompt)
        self.assertEqual(self.calls['p0_finalize'], 1)
        self.assertEqual(self.calls['p0_repair'], 1)
        self.assertEqual(wf.read_json(job / 'production/p0_finalized.json')['article_markdown'], self.repaired)

    def test_unmarked_frozen_p0_retains_original_editor_input_and_system(self):
        job = self.job()
        state = wf.load_state(job)
        state['metadata'].pop('p0_selected_facts_mode')
        wf.save_state(job, state)
        self.until(job, 'finalize', p0=True)
        before = writing_context.prompt_finalize(wf, job, p0=True)
        before_fingerprint = model_runtime.request_fingerprint('p0_finalize', before)
        self.assertNotIn(writing_context_v14.P0_SELECTED_FACTS_MARKER, before)
        self.assertIn('不作事实检查', before)
        self.assertIn('不核查事实', model_runtime._initial_messages('p0_finalize', before)[0]['content'])
        state['metadata']['p0_selected_facts_mode'] = writing_requirements.P0_SELECTED_FACTS_MODE
        wf.save_state(job, state)
        self.assertIn(writing_context_v14.P0_SELECTED_FACTS_MARKER, writing_context.prompt_finalize(wf, job, p0=True))
        self.assertEqual(model_runtime.request_fingerprint('p0_finalize', before), before_fingerprint)
        self.assertNotIn('p0_selected_facts_mode', wf.make_state('synthetic-article', 'article')['metadata'])


if __name__ == '__main__':
    unittest.main()
