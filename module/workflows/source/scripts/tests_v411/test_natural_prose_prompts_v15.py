"""Request-level coverage for natural prose and the deliberately small copy edit."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from shared import writing_context, writing_context_v15 as prose, model_runtime, writer_measure


class ProsePromptTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp

    def job(self, pattern="P02"):
        job = flow.NaturalEditorFlowTests.job(self)
        state = wf.load_state(job)
        state["selected_pattern_id"] = pattern
        state["metadata"]["natural_prose_contract"] = prose.CONTRACT
        state["metadata"]["writer_count_contract"] = writer_measure.CONTRACT
        wf.save_state(job, state)
        bp = wf.read_json(job / "blueprints/article_blueprint.json")
        bp.update(pattern_id=pattern, article_brief="CURRENT_SCOPE 自然机构推荐文章。",
                  writing_material_markdown="SOURCE_ONLY 书店设有儿童阅读区和靠窗座位。",
                  sections=[{"heading": "BLUEPRINT_ONLY", "task": "取舍材料。"}],
                  estimated_length="LENGTH_ONCE 约3000字")
        wf.atomic_json(job / "blueprints/article_blueprint.json", bp)
        wf.atomic_json(job / "production/article_draft.json", {
            "article_markdown": self.body, "requires_blueprint_reconfirmation": False,
            "reconfirmation_reason": ""})
        wf.atomic_json(job / "production/article_edited.json", {
            "edit_status": "accepted", "article_markdown": self.body,
            "editorial_notes": [], "requires_blueprint_reconfirmation": False,
            "reconfirmation_reason": ""})
        return job

    def test_both_patterns_use_the_new_writer_and_counter(self):
        job = self.job()
        for pattern in ("P01", "P02"):
            state = wf.load_state(job)
            state["selected_pattern_id"] = pattern
            wf.save_state(job, state)
            with patch("shared.writing_context_v14.examples", return_value="FULL_STYLE_EXAMPLE"):
                for action, builder in (("article_draft", writing_context.prompt_article),
                                        ("article_edit", writing_context.prompt_edit)):
                    prompt = builder(wf, job, p0=False)
                    self.assertTrue(prose.matches(prompt))
                    self.assertTrue(writer_measure.matches(action, prompt))
                    self.assertEqual(prompt.count("LENGTH_ONCE"), 1)
                    self.assertIn("SOURCE_ONLY", prompt)
                    self.assertIn("FULL_STYLE_EXAMPLE", prompt)
                    self.assertNotIn("还需至少展开", prompt)
                    self.assertEqual(model_runtime._initial_messages(action, prompt)[0]["content"], prose.system(action, prompt))

    def test_copy_editor_reads_only_current_body_and_commission(self):
        job = self.job()
        with patch("shared.writing_context_v14.examples", return_value="FULL_STYLE_EXAMPLE"):
            prompt = writing_context.prompt_finalize(wf, job, p0=False)
        self.assertTrue(prose.matches(prompt))
        self.assertIn(self.body, prompt)
        self.assertIn("CURRENT_SCOPE", prompt)
        for excluded in ("SOURCE_ONLY", "BLUEPRINT_ONLY", "FULL_STYLE_EXAMPLE"):
            self.assertNotIn(excluded, prompt)
        self.assertIn("local_edits", prompt)

    def test_final_polish_reads_the_repaired_manuscript(self):
        job = self.job()
        wf.atomic_json(job / "production/article_repaired.json", {"article_markdown": "# 正文\n\nAFTER_REPAIR 唯一的新基稿。"})
        prompt = prose.prompt_finish(wf, job, after_repair=True)
        self.assertIn("AFTER_REPAIR", prompt)
        self.assertNotIn(self.body, prompt)
        self.assertIn("已经完成过一次结构返工", prompt)

    def test_frozen_jobs_and_other_patterns_do_not_opt_in(self):
        job = self.job()
        state = wf.load_state(job)
        state["metadata"].pop("natural_prose_contract")
        wf.save_state(job, state)
        self.assertFalse(prose.matches(writing_context.prompt_article(wf, job, p0=False)))
        state["metadata"]["natural_prose_contract"] = prose.CONTRACT
        for pattern in ("P03", "P04", "P05", "P06"):
            state["selected_pattern_id"] = pattern
            self.assertFalse(prose.enabled(state))
        state["selected_pattern_id"] = "P01"
        self.assertFalse(prose.enabled(state, p0=True))


if __name__ == "__main__":
    unittest.main()
