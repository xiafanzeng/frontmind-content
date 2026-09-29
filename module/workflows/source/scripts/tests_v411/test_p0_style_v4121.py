"""P0-only fixed examples and third-pass input/contract regressions.

Examples are synthetic and network calls are mocked; this suite establishes
runtime behavior, not the writing quality of a real provider response.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared import p0_style, writing_context, model_runtime
from shared.editorial_contracts import EditorialContractError


class P0StyleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package, self.job = self.root / "pkg", self.root / "job"
        self.resources = self.package / "resources/p0_style"
        self.resources.mkdir(parents=True)
        self.job.mkdir()
        self.star = "STAR_COMPLETE_START\n\n具体技术方法和必要适用条件。\n\nSTAR_COMPLETE_END\n"
        self.gang = "GANGJUN_COMPLETE_START\n\n长期服务方法与事实解释。\n\nGANGJUN_COMPLETE_END\n"
        self.put(self.resources / "gangjun.md", self.gang)
        self.put(self.resources / "xingyuanzhi_guide.md", "只学习方法的解释，不移植事实。")
        self.put(self.resources / "gangjun_guide.md", "只学习具体服务的展开，不复制目录。")
        self.manifest = {"contract_version": p0_style.P0_STYLE_CONTRACT_VERSION, "examples": [
            {"id": "xingyuanzhi", "title": "星源智模拟例文", "fetch": {"url": "https://tech.china.com/test.html", "content_sha256": p0_style.sha256(self.star)}, "guide_path": "xingyuanzhi_guide.md"},
            {"id": "gangjun", "title": "港隽模拟例文", "body_path": "gangjun.md", "content_sha256": p0_style.sha256(self.gang), "guide_path": "gangjun_guide.md"}]}
        self.put(self.resources / "manifest.json", self.manifest)
        self.state = {"job_kind": "p0", "metadata": {"p0_style_contract": p0_style.P0_STYLE_CONTRACT_VERSION}, "decisions": {}, "selected_example_route": "workflow", "reference_pack": {"brand": "本品牌"}}
        self.put(self.job / "job_state.json", self.state)
        self.blueprint = {"kind": "p0", "sections": [{"heading": "具体方法", "task": "解释业务"}], "article_brief": "理解具体方法", "example_use": "参考解释和展开", "writing_material_markdown": "本品牌提供软件测试，按照项目约定提交结果。", "writing_material_sources": ["inputs/fact.md"]}
        self.put(self.job / "blueprints/p0_blueprint.json", self.blueprint)
        self.draft = {"article_markdown": "# 本品牌\n\n## 具体方法\n\n本品牌提供软件测试。", "requires_blueprint_reconfirmation": False, "reconfirmation_reason": ""}
        self.edit = {**self.draft, "edit_status": "accepted", "editorial_notes": []}
        self.put(self.job / "production/p0_draft.json", self.draft)
        self.put(self.job / "production/p0_edited.json", self.edit)
        self.wf = SimpleNamespace(load_state=lambda job: self.state, load_examples=lambda job, scope: [], user_material_text=lambda *args: "")
        self.module_path = patch.object(writing_context, "__file__", str(self.package / "shared/writing_context.py"))
        self.module_path.start()
        self.addCleanup(self.module_path.stop)

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def freeze(self):
        with patch.object(p0_style, "_fetch", return_value=self.star) as fetch:
            result = p0_style.freeze_examples(self.package, self.job)
        return result

    def use_legacy_contract(self):
        """Keep historical refinement assertions on their actual old contract."""
        self.state["metadata"]["p0_style_contract"] = p0_style.LEGACY_STYLE_CONTRACT_VERSION
        self.put(self.job / "job_state.json", self.state)
        legacy_resources = self.package / "resources/p0_style_legacy_v4121"
        for name in ("gangjun.md", "xingyuanzhi_guide.md", "gangjun_guide.md"):
            self.put(legacy_resources / name, (self.resources / name).read_text(encoding="utf-8"))
        self.put(legacy_resources / "manifest.json", {**self.manifest, "contract_version": p0_style.LEGACY_STYLE_CONTRACT_VERSION})

    def test_only_new_p0_marker_enables_contract(self):
        self.assertTrue(p0_style.is_enabled(self.state))
        self.assertFalse(p0_style.is_enabled({"job_kind": "p0", "metadata": {}}))
        self.assertFalse(p0_style.is_enabled({**self.state, "job_kind": "article"}))
        with self.assertRaisesRegex(EditorialContractError, "无法识别"):
            p0_style.is_enabled({"job_kind": "p0", "metadata": {"p0_style_contract": "unknown"}})

    def test_freeze_once_keeps_complete_fixed_pair_and_never_refetches(self):
        records = self.freeze()
        self.assertEqual([x["id"] for x in records], ["xingyuanzhi", "gangjun"])
        self.assertEqual([x["text"] for x in records], [self.star, self.gang])
        with patch.object(p0_style, "_fetch", side_effect=AssertionError("must not refetch")):
            self.assertEqual(records, p0_style.freeze_examples(self.package, self.job))

    def test_read_without_snapshot_does_not_create_or_fetch(self):
        with patch.object(p0_style, "_fetch", side_effect=AssertionError("must not fetch")):
            with self.assertRaises(EditorialContractError):
                p0_style.job_examples(self.package, self.job)
        self.assertFalse((self.job / p0_style.SNAPSHOT_RELATIVE).exists())

    def test_source_failure_does_not_create_partial_snapshot_or_use_guide(self):
        with patch.object(p0_style, "_fetch", side_effect=EditorialContractError("failure", "停止")):
            with self.assertRaises(EditorialContractError):
                p0_style.freeze_examples(self.package, self.job)
        self.assertFalse((self.job / "inputs/p0_style_examples").exists())

    def test_acquired_text_digest_mismatch_stops(self):
        with patch.object(p0_style, "_fetch", return_value=self.star + "变更"):
            with self.assertRaises(EditorialContractError):
                p0_style.freeze_examples(self.package, self.job)

    def test_body_and_snapshot_digest_tampering_is_detected(self):
        self.freeze()
        folder = self.job / "inputs/p0_style_examples"
        self.put(folder / "xingyuanzhi.md", "已换成另一篇")
        manifest = json.loads((folder / "manifest.json").read_text())
        manifest["examples"][0]["sha256"] = p0_style.sha256("已换成另一篇")
        self.put(folder / "manifest.json", manifest)
        with self.assertRaises(EditorialContractError):
            p0_style.job_examples(self.package, self.job)

    def test_all_five_p0_stages_receive_full_pair_despite_workflow_route(self):
        self.freeze()
        self.put(self.job / "production/p0_styled.json", p0_style.fixture_style_result(self.edit["article_markdown"]))
        for builder in (writing_context.prompt_blueprint, writing_context.prompt_article, writing_context.prompt_edit, writing_context.prompt_finalize):
            prompt = builder(self.wf, self.job, p0=True)
            self.assertIn(self.star, prompt)
            self.assertIn(self.gang, prompt)
        prompt = writing_context.prompt_p0_style(self.wf, self.job)
        self.assertIn(self.star, prompt)
        self.assertIn(self.gang, prompt)
        self.assertIn(self.edit["article_markdown"], prompt)

    def test_user_example_is_additive_not_replacement(self):
        self.freeze()
        extra = "USER_EXTRA_START\n用户本篇补充例文\nUSER_EXTRA_END"
        self.put(self.job / "examples/additional.md", extra)
        self.state["selected_example_route"] = "top20"
        self.wf.load_examples = lambda *args: [{"title": "行业补充", "path": "examples/additional.md"}]
        text = writing_context.selected_examples_markdown(self.wf, self.job, p0=True)
        for expected in (self.star, self.gang, extra):
            self.assertIn(expected, text)

    def test_article_and_legacy_p0_do_not_read_fixed_resources(self):
        self.state["metadata"] = {}
        with patch.object(p0_style, "job_examples", side_effect=AssertionError("not permitted")):
            self.assertEqual(writing_context.selected_examples_markdown(self.wf, self.job, p0=True), "本篇使用工作流自然写作规范。")
            self.assertEqual(writing_context.selected_examples_markdown(self.wf, self.job, p0=False), "本篇使用工作流自然写作规范。")

    def test_style_cannot_bypass_e8_failure(self):
        self.freeze()
        self.put(self.job / "production/p0_edit_failure.json", {"error_code": "bad_format"})
        with self.assertRaises(EditorialContractError):
            writing_context.prompt_p0_style(self.wf, self.job)

    def test_revision_instruction_complete_in_style_and_finalization(self):
        self.freeze()
        revision = {"base_markdown": self.draft["article_markdown"], "edits_markdown": "FIRST_REQUIREMENT\n保留用户完整要求和实际服务范围。\nLAST_REQUIREMENT"}
        self.put(self.job / "production/p0_styled.json", p0_style.fixture_style_result(self.edit["article_markdown"]))
        with patch("shared.manuscript_revision.current_revision", return_value=revision):
            for prompt in (writing_context.prompt_p0_style(self.wf, self.job), writing_context.prompt_finalize(self.wf, self.job, p0=True)):
                self.assertIn(revision["edits_markdown"], prompt)

    def test_style_contract_rejects_claimed_revision_without_real_change(self):
        result = p0_style.fixture_style_result("# 稿件\n正文")
        result.update(edit_status="revised", editorial_notes=["声称已修改"])
        with self.assertRaises(EditorialContractError):
            p0_style.validate_style_result(result, result["article_markdown"])

    def test_live_revision_supersedes_old_rewrite_commands_without_losing_scope_or_facts(self):
        self.use_legacy_contract()
        self.freeze()
        self.state["decisions"] = {"response_brief": "OLD_RESPONSE_TASK：正文不得列价格。", "blueprint_edits": "旧稿仅保留为历史，不是本轮待改文字。OLD_START_OVER。必须保留项目适用条件段落。"}
        self.blueprint["article_brief"] = "OLD_EXPAND_EVERY_TOPIC"
        self.blueprint["example_use"] = "OLD_RESTORE_ALL_DETAILS"
        self.blueprint["estimated_length"] = "OLD_LENGTH_TARGET"
        self.put(self.job / "blueprints/p0_blueprint.json", self.blueprint)
        revision = {"base_markdown": self.draft["article_markdown"], "edits_markdown": "CURRENT_BEGIN\n调整现稿段落，保留必要业务条件。\nCURRENT_END"}
        with patch("shared.manuscript_revision.current_revision", return_value=revision):
            prompt = writing_context.prompt_p0_style(self.wf, self.job)
        self.assertIn(revision["edits_markdown"], prompt)
        for stale in ("OLD_EXPAND_EVERY_TOPIC", "OLD_RESTORE_ALL_DETAILS", "OLD_LENGTH_TARGET"):
            self.assertNotIn(stale, prompt)
        for retained in (self.blueprint["writing_material_markdown"], self.blueprint["sections"][0]["heading"], self.edit["article_markdown"], self.star, self.gang):
            self.assertIn(retained, prompt)
        self.assertIn("受保护决定", prompt)
        self.assertIn("历史背景", prompt)
        # The same commission remains the active input for a genuinely new
        # manuscript, which has no later manuscript-revision request.
        fresh = writing_context.prompt_p0_style(self.wf, self.job)
        for active in ("OLD_RESPONSE_TASK", "OLD_START_OVER", "OLD_EXPAND_EVERY_TOPIC", "OLD_RESTORE_ALL_DETAILS", "OLD_LENGTH_TARGET"):
            self.assertIn(active, fresh)

    def test_revision_precedence_is_consistent_in_e8_style_and_finalize(self):
        self.use_legacy_contract()
        self.freeze()
        self.state["decisions"] = {"response_brief": "OLD_RESPONSE_TASK：正文不得列价格。", "blueprint_edits": "旧稿仅保留为历史，不是本轮待改文字。OLD_START_OVER。必须保留项目适用条件段落。"}
        self.blueprint.update(article_brief="OLD_EXPAND_EVERY_TOPIC", example_use="OLD_RESTORE_ALL_DETAILS", estimated_length="OLD_LENGTH_TARGET")
        self.put(self.job / "blueprints/p0_blueprint.json", self.blueprint)
        revision = {"base_markdown": self.draft["article_markdown"] + "\nFROZEN_REVISION_BASE", "edits_markdown": "CURRENT_BEGIN\n调整现稿段落，保留必要业务条件。\nCURRENT_END"}
        self.edit.update(edit_status="revised", editorial_notes=["已落实上一编辑阶段的调整"])
        self.put(self.job / "production/p0_edited.json", self.edit)
        self.put(self.job / "production/p0_styled.json", p0_style.fixture_style_result(self.edit["article_markdown"]))
        with patch("shared.manuscript_revision.current_revision", return_value=revision):
            prompts = [writing_context.prompt_edit(self.wf, self.job, p0=True), writing_context.prompt_p0_style(self.wf, self.job), writing_context.prompt_finalize(self.wf, self.job, p0=True)]
            for prompt in prompts:
                self.assertIn(revision["edits_markdown"], prompt)
                self.assertIn(self.state["decisions"]["response_brief"], prompt)
                self.assertIn("<inherited_content_requirements>", prompt)
                history = prompt.split("<historical_blueprint_request>\n", 1)[1].split("\n</historical_blueprint_request>", 1)[0]
                self.assertEqual(history, self.state["decisions"]["blueprint_edits"])
                current = prompt.split("本轮唯一当前修改委托", 1)[1]
                self.assertNotIn("OLD_START_OVER", current)
                self.assertNotIn("旧稿仅保留为历史", current)
                for stale in ("OLD_EXPAND_EVERY_TOPIC", "OLD_RESTORE_ALL_DETAILS", "OLD_LENGTH_TARGET"):
                    self.assertNotIn(stale, prompt)
                for retained in (self.blueprint["writing_material_markdown"], self.blueprint["sections"][0]["heading"], self.star, self.gang):
                    self.assertIn(retained, prompt)
            for prompt in prompts:
                self.assertIn(revision["base_markdown"], prompt)
            self.assertIn("已交付全文的冻结对照稿（不是本轮待编辑稿）", prompts[1])
            self.assertIn("本轮唯一待编辑稿：E8 全文", prompts[1])
            self.assertIn(self.edit["article_markdown"], prompts[1])
            self.assertIn(self.edit["article_markdown"], prompts[2])
            # An unupgraded historical P0 retains its old prompt contract.
            self.state["metadata"] = {}
            legacy = writing_context.natural_author_context(self.wf, self.job, p0=True, editing=True)
            self.assertIn("OLD_START_OVER", legacy)
            self.assertIn("OLD_EXPAND_EVERY_TOPIC", legacy)

    def test_style_explicit_note_array_contract_rejects_string_without_coercion(self):
        self.freeze()
        prompt = writing_context.prompt_p0_style(self.wf, self.job)
        self.assertIn("editorial_notes 必须是 JSON 字符串数组", prompt)
        self.assertIn('"editorial_notes": ["实际已落实的修改"]', prompt)
        result = p0_style.fixture_style_result("# 稿件\n正文")
        result["editorial_notes"] = "声称完成修改但类型错误"
        with self.assertRaises(EditorialContractError):
            p0_style.validate_style_result(result, result["article_markdown"])
        self.assertEqual(result["editorial_notes"], "声称完成修改但类型错误")

    def test_style_requires_editing_decision_without_changing_business_scope(self):
        result = p0_style.fixture_style_result("# 稿件\n正文")
        result.pop("editorial_plan")
        with self.assertRaisesRegex(EditorialContractError, "editorial_plan"):
            p0_style.validate_style_result(result, result["article_markdown"])
        self.freeze()
        prompt = writing_context.prompt_p0_style(self.wf, self.job)
        # Real full examples and factual basis precede the actual candidate;
        # old E8 self-assessments no longer shape the new editor's decisions.
        self.assertLess(prompt.index(self.star), prompt.index(self.blueprint["writing_material_markdown"]))
        self.assertLess(prompt.index(self.blueprint["writing_material_markdown"]), prompt.index(self.edit["article_markdown"]))

    def test_style_contract_requires_concrete_audit_but_no_score(self):
        result = p0_style.fixture_style_result("# 稿件\n正文")
        self.assertEqual(p0_style.validate_style_result(result, result["article_markdown"]), result)
        result["style_audit"].pop("fact_check")
        with self.assertRaises(EditorialContractError):
            p0_style.validate_style_result(result, result["article_markdown"])

    def test_style_uses_existing_writer_profile_without_article_action(self):
        self.assertEqual(model_runtime.profile_for("p0_style"), model_runtime.profile_for("p0_edit"))
        self.assertNotIn("article_style", model_runtime.DEEPSEEK_ACTIONS)

    def test_fixed_examples_cannot_be_cited_as_p0_business_facts(self):
        self.freeze()
        relative = "inputs/p0_style_examples/xingyuanzhi.md"
        self.put(self.job / "inputs/fact.md", "本企业的真实事实。")
        self.put(self.job / "artifacts/host_registry.json", {"artifacts": {
            "fixed_example_artifact": {"path": relative, "sha256": p0_style.sha256(self.star), "category": "example"},
            "brand_fact_artifact": {"path": "inputs/fact.md", "sha256": p0_style.sha256("本企业的真实事实。"), "category": "material"}}})
        for ref in (relative, "fixed_example_artifact"):
            poisoned = {**self.blueprint, "writing_material_sources": [{"source_ref": ref, "use": "错误地当作本企业事实"}]}
            with self.assertRaisesRegex(EditorialContractError, "不能作为本企业事实来源"):
                writing_context.validate_writing_material_sources(self.wf, self.job, poisoned, artifact_ids={ref})
        actual = {**self.blueprint, "writing_material_sources": [{"source_ref": "brand_fact_artifact", "use": "本企业的业务事实"}]}
        self.assertEqual(writing_context.validate_writing_material_sources(self.wf, self.job, actual), actual)

    def test_style_same_fingerprint_and_explicit_retry_reuse_one_model_call(self):
        self.freeze()
        result = p0_style.fixture_style_result(self.edit["article_markdown"])
        prompt = writing_context.prompt_p0_style(self.wf, self.job)
        calls = []
        def transport(profile, key, payload):
            calls.append(payload)
            yield {"model": "deepseek-v4-pro", "choices": [{"index": 0, "delta": {"content": json.dumps(result, ensure_ascii=False)}, "finish_reason": "stop"}]}
            yield "[DONE]"
        validator = lambda value: p0_style.validate_style_result(value, self.edit["article_markdown"])
        with patch.object(model_runtime, "__file__", str(self.package / "shared/model_runtime.py")):
            first = model_runtime.run_action(self.package, self.job, "p0_style", prompt, validator, transport=transport, offline=True)
            second = model_runtime.run_action(self.package, self.job, "p0_style", prompt, validator, transport=transport, offline=True)
            third = model_runtime.run_action(self.package, self.job, "p0_style", prompt, validator, retry=True, transport=transport, offline=True)
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(len(calls), 1)

    def test_completed_style_validation_binds_saved_request_to_actual_e8(self):
        from shared.manuscript_revision import _verified_action
        self.freeze()
        self.wf.ROOT = self.package
        self.wf.read_json = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
        result = p0_style.fixture_style_result(self.edit["article_markdown"])
        attempt = self.job / "provider/p0_style/runtime/attempts/attempt_one"
        self.put(attempt / "execution.json", {"status": "succeeded", "execution_mode": "production", "action": "p0_style", "requested_configuration": model_runtime.profile_for("p0_style")})
        self.put(attempt / "prompt.md", writing_context.prompt_p0_style(self.wf, self.job))
        self.put(self.job / "provider/p0_style/runtime/latest.json", {"attempt_id": "attempt_one"})
        self.put(self.job / "provider/p0_style/result.json", result)
        production = self.job / "production/p0_styled.json"
        self.put(production, result)
        with patch.object(model_runtime, "_saved_result", return_value=result):
            verified = _verified_action(self.wf, self.job, "p0_style", production, lambda value: value, offline=False)
            self.assertEqual(verified["action"], "p0_style")
            # Both E8 bodies can be legal; authentic old style output must not
            # be spliced onto a different E8 simply because it is revised.
            changed = {**self.edit, "edit_status": "revised", "article_markdown": self.edit["article_markdown"] + "\n新增但不同的 E8。", "editorial_notes": ["调整本稿"]}
            self.put(self.job / "production/p0_edited.json", changed)
            with self.assertRaisesRegex(ValueError, "未绑定当前完整 E8"):
                _verified_action(self.wf, self.job, "p0_style", production, lambda value: value, offline=False)

    def test_canonical_html_extraction_preserves_inline_words_and_excludes_boilerplate(self):
        paragraphs = "".join(f"<p>正文{i}：<span>端</span>侧部署说明具体动作及其作用，" + "真实事实。" * 25 + "</p>" for i in range(3))
        html = '<h1>页面标题</h1><div id="chan_newsDetail"><p><strong>分节标题</strong></p>' + paragraphs + '<p>免责声明：不属于例文正文</p><p>更多推荐</p></div>'
        text = p0_style.extract_china_article(html)
        self.assertTrue(text.startswith("## 分节标题\n\n"))
        self.assertIn("端侧部署", text)
        self.assertNotIn("免责声明", text)
        self.assertNotIn("更多推荐", text)


if __name__ == "__main__":
    unittest.main()
