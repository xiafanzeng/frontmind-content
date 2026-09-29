"""Actual new-job requests and execution flow, with explicit offline responses."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import zipfile

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from scripts.tests_v411.agents_sdk_fake import bundle
from shared import model_runtime as runtime, natural_editor, writing_requirements as requirements, writing_context
from shared import writing_context_v14 as current
from shared.host_tools import HostTools, ToolError


class GeneralWritingTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp
    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def job(self, prefix="article"):
        job = flow.NaturalEditorFlowTests.job(self, prefix)
        state = wf.load_state(job)
        # Production initializer supplies the new mission without any upgrade
        # option, blueprint edits, manuscript revision or post-hoc patch prompt.
        state["metadata"] = wf.make_state("new-" + prefix, prefix)["metadata"]
        # Replay the historical v14 mission, not the new v15 commission.
        state["metadata"].pop("natural_prose_contract", None)
        state["metadata"].pop("title_strategy", None)  # pin historical v14 title requests
        state["reference_pack"]["path"] = str(Path(state["reference_pack"]["path"]).resolve())
        wf.save_state(job, state)
        with zipfile.ZipFile(job / "00_input/reference_pack.zip", "w") as archive:
            archive.writestr("materials/company.md", "合成机构提供资料中所述业务与服务。")
        return job

    test_no_comments_keeps_exact_body = flow.NaturalEditorFlowTests.test_no_comments_selects_exact_candidate_and_skips_writer_repair
    test_comments_only_one_repair_then_titles = flow.NaturalEditorFlowTests.test_comments_trigger_one_repair_then_titles_without_body_rereview
    test_interrupted_repair_does_not_repeat_review_or_writer = flow.NaturalEditorFlowTests.test_interruption_after_provider_result_recovers_without_duplicate_call
    test_final_body_survives_title_and_manuscript_revisions = flow.NaturalEditorFlowTests.test_completed_repair_can_continue_with_title_and_manuscript_edits
    test_p0_retains_its_third_pass = flow.NaturalEditorFlowTests.test_p0_keeps_style_pass_and_repair_uses_styled_body

    def test_empty_new_job_defaults_to_general_mission(self):
        job = wf.ensure_new_job(self.root / "brand-new", "article", offline=True)
        state = wf.load_state(job)
        self.assertTrue(current.enabled(state))
        self.assertFalse((job / "production").exists())
        self.assertNotIn("article_manuscript_revision", state["metadata"])
        self.assertEqual(state["decisions"], {})

    def test_new_body_requests_freeze_counter_opt_in_without_upgrading_old_jobs(self):
        from shared import writer_measure
        job = self.job()
        self.assertTrue(writer_measure.enabled(wf.load_state(job)))
        self.needs_revision = True
        self.finish(job)
        for action, prompt in self.prompts.items():
            self.assertEqual(writer_measure.matches(action, prompt), action in writer_measure.ACTIONS, action)
        state = wf.load_state(job)
        state["metadata"].pop("writer_count_contract")
        wf.save_state(job, state)
        self.assertNotIn(writer_measure.MARKER, wf.prompt_article(job, p0=False))
        self.assertNotIn("writer_count_contract", wf.load_state(job)["metadata"])
        self.assertNotIn("writer_count_contract", wf.make_state("old-p0", "p0")["metadata"])

    def test_previous_p01_mainlines_reach_real_requests_without_changing_other_patterns(self):
        job = self.job()
        state = wf.load_state(job)
        state["metadata"]["single_subject_writing_contract"] = current.SINGLE_SUBJECT_CONTRACT
        wf.save_state(job, state)
        # The fixture starts as P02. Its request stays byte-identical whether
        # the new article initializer's P01-only switch is present or absent.
        p02_before = wf.prompt_blueprint(job, p0=False)
        state = wf.load_state(job)
        self.assertEqual(state["metadata"].pop("single_subject_writing_contract"), current.SINGLE_SUBJECT_CONTRACT)
        wf.save_state(job, state)
        self.assertEqual(wf.prompt_blueprint(job, p0=False), p02_before)
        state["metadata"]["single_subject_writing_contract"] = current.SINGLE_SUBJECT_CONTRACT
        state["selected_pattern_id"] = "P01"
        wf.save_state(job, state)
        bp = wf.read_json(job / "blueprints/article_blueprint.json")
        bp["pattern_id"] = "P01"
        wf.atomic_json(job / "blueprints/article_blueprint.json", bp)
        blueprint = wf.prompt_blueprint(job, p0=False)
        self.needs_revision = True
        self.finish(job)
        for action, prompt in {"article_blueprint": blueprint, **self.prompts}.items():
            expected = action in {"article_blueprint", "article_draft", "article_edit", "article_finalize", "article_repair"}
            self.assertEqual(current.single_subject_request(prompt), expected, action)
            if expected:
                request = runtime._initial_messages(action, prompt)
                self.assertEqual(request[1]["content"].count(current.SINGLE_SUBJECT_PRINCIPLES), 1, action)
                self.assertIn(current.SINGLE_SUBJECT_PRINCIPLES, prompt.split("<current_commission>", 1)[1])
        fields = runtime.submit_tool_for("article_blueprint", prompt=blueprint)["function"]["parameters"]["properties"]["result"]["properties"]
        self.assertIn("相关原文的完整信息组成组保留", fields["writing_material_markdown"]["description"])
        self.assertIn("数量不固定", fields["sections"]["description"])
        state = wf.load_state(job)
        state["metadata"].pop("single_subject_writing_contract")
        wf.save_state(job, state)
        legacy = wf.prompt_blueprint(job, p0=False)
        self.assertFalse(current.single_subject_request(legacy))
        legacy_fields = runtime.submit_tool_for("article_blueprint", prompt=legacy)["function"]["parameters"]["properties"]["result"]["properties"]
        p02_fields = runtime.submit_tool_for("article_blueprint", prompt=p02_before)["function"]["parameters"]["properties"]["result"]["properties"]
        self.assertEqual(legacy_fields, p02_fields)
        p0 = self.job("p0")
        before = wf.prompt_blueprint(p0, p0=True)
        state = wf.load_state(p0)
        state["metadata"]["single_subject_writing_contract"] = current.SINGLE_SUBJECT_CONTRACT
        wf.save_state(p0, state)
        self.assertEqual(wf.prompt_blueprint(p0, p0=True), before)
        self.assertFalse(current.single_subject_request(before))

    def test_new_p01_profile_replaces_all_five_inputs_and_preserves_existing_interfaces(self):
        from shared import p01_writing_v2 as p01, writer_measure
        job = self.job()
        state = wf.load_state(job)
        self.assertEqual(state["metadata"]["single_subject_writing_contract"], p01.DEFAULT_CONTRACT)
        state["selected_pattern_id"] = "P01"
        wf.save_state(job, state)
        bp = wf.read_json(job / "blueprints/article_blueprint.json")
        bp.update(pattern_id="P01", estimated_length="V2_CURRENT_LENGTH_3000",
                  writing_material_markdown="V2_COMPLETE_SELECTED_GROUP 对象原文的完整说明。")
        wf.atomic_json(job / "blueprints/article_blueprint.json", bp)
        blueprint = wf.prompt_blueprint(job, p0=False)
        self.needs_revision = True
        self.finish(job)
        for action, prompt in {"article_blueprint": blueprint, **self.prompts}.items():
            body_stage = action in {"article_blueprint", "article_draft", "article_edit", "article_finalize", "article_repair"}
            self.assertEqual(p01.matches(prompt), body_stage, action)
            if not body_stage:
                continue
            messages = runtime._initial_messages(action, prompt)
            combined = "\n".join(x["content"] for x in messages)
            self.assertTrue(p01.current_request(prompt))
            self.assertEqual(messages[0]["content"], p01.system(action, prompt))
            self.assertIn("直接", messages[0]["content"])
            self.assertNotIn(current.CORE, combined)
            self.assertNotIn(current.SINGLE_SUBJECT_PRINCIPLES, combined)
            self.assertNotIn(current.BLUEPRINT_FIELDS, prompt)
            self.assertEqual(prompt.count("V2_CURRENT_LENGTH_3000"), 1)
            stage = action.rsplit("_", 1)[-1]
            self.assertNotIn(current.ROLES[stage], messages[0]["content"])
            self.assertEqual(combined.count(writer_measure.GUIDANCE), int(action in writer_measure.ACTIONS))
            if action in {"article_draft", "article_edit", "article_repair"}:
                self.assertTrue(writer_measure.matches(action, prompt))
                self.assertIn("V2_COMPLETE_SELECTED_GROUP", prompt)
                self.assertEqual([t["function"]["name"] for t in runtime.build_payload(action, prompt)["tools"]], ["count_article"])
            if action in {"article_edit", "article_finalize", "article_repair"}:
                self.assertIn(self.body, prompt)
            if action == "article_finalize":
                self.assertNotIn("V2_COMPLETE_SELECTED_GROUP", prompt)
                self.assertIn("不做事实检查，不判断来源或资料缺口", messages[0]["content"])
        fields = runtime.submit_tool_for("article_blueprint", prompt=blueprint)["function"]["parameters"]["properties"]["result"]["properties"]
        for name, description in p01.blueprint_descriptions(blueprint).items():
            self.assertEqual(fields[name]["description"], description)
        self.assertEqual(fields["sections"]["items"]["properties"]["task"]["description"], p01.section_task(blueprint))
        self.assertEqual(wf.read_json(job / "production/article_finalized.json")["article_markdown"], self.repaired)
        self.assertEqual(self.calls["article_finalize"], 1)
        self.assertEqual(self.calls["article_repair"], 1)
        state = wf.load_state(job)
        state["metadata"]["single_subject_writing_contract"] = p01.CONTRACT
        wf.save_state(job, state)
        previous = wf.prompt_blueprint(job, p0=False)
        self.assertTrue(p01.matches(previous))
        self.assertFalse(p01.current_request(previous))
        self.assertEqual(runtime._initial_messages("article_blueprint", previous)[0]["content"], p01.system("article_blueprint"))
        self.assertIn(p01.MISSION, runtime._initial_messages("article_blueprint", previous)[0]["content"])
        self.assertNotIn(p01.MISSION_V3, runtime._initial_messages("article_blueprint", previous)[0]["content"])
        previous_fields = runtime.submit_tool_for("article_blueprint", prompt=previous)["function"]["parameters"]["properties"]["result"]["properties"]
        for name, description in p01.BLUEPRINT_DESCRIPTIONS.items():
            self.assertEqual(previous_fields[name]["description"], description)
        state["metadata"]["single_subject_writing_contract"] = current.SINGLE_SUBJECT_CONTRACT
        wf.save_state(job, state)
        old_prompt = wf.prompt_blueprint(job, p0=False)
        self.assertFalse(p01.matches(old_prompt))
        self.assertTrue(current.single_subject_request(old_prompt))
        self.assertIn(current.CORE, runtime._initial_messages("article_blueprint", old_prompt)[0]["content"])

    def test_style_and_current_requirements_reach_entire_new_writing_chain(self):
        job = self.job()
        bp = wf.read_json(job / "blueprints/article_blueprint.json")
        bp.update(article_brief="CURRENT_BRIEF 面向普通读者的机构介绍。",
                  estimated_length="BODY_LENGTH_TEST", formatting="INLINE_BOLD_TEST",
                  recommendation_relationships="RELATIONSHIP_TEST",
                  writing_material_markdown="SELECTED_CONTENT 相关业务与接待服务。",
                  writing_material_sources=[{"source_ref": "inputs/facts.md", "use": "PRIVATE_SOURCE_COORDINATE"}],
                  material_adjustments=["OBSOLETE_CHECK_NOTE"])
        wf.atomic_json(job / "blueprints/article_blueprint.json", bp)
        self.needs_revision = True
        with patch.object(current, "_natural_examples", return_value="FULL_STYLE_REFERENCE_TEST"):
            blueprint = wf.prompt_blueprint(job, p0=False)
            self.finish(job)
        for action, prompt in {"article_blueprint": blueprint, **self.prompts}.items():
            self.assertTrue(current.matches(prompt), action)
        for action in ("article_draft", "article_edit", "article_finalize", "article_repair"):
            prompt = self.prompts[action]
            for value in ("CURRENT_BRIEF", "BODY_LENGTH_TEST", "INLINE_BOLD_TEST", "RELATIONSHIP_TEST", "FULL_STYLE_REFERENCE_TEST"):
                self.assertIn(value, prompt, action)
            self.assertEqual(prompt.count("CURRENT_BRIEF"), 1, action)
            self.assertEqual(prompt.count("BODY_LENGTH_TEST"), 1, action)
            self.assertNotIn("OBSOLETE_CHECK_NOTE", prompt)
            self.assertNotIn("PRIVATE_SOURCE_COORDINATE", prompt)
            payload = runtime.build_payload(action, prompt)
            self.assertEqual(runtime._initial_messages(action, prompt)[0]["content"], current.system(action, prompt))
            if action != "article_finalize":
                self.assertIn("SELECTED_CONTENT", prompt)
                self.assertEqual(payload["reasoning_effort"], "max")
            else:
                self.assertNotIn("SELECTED_CONTENT", prompt)
                self.assertIn(self.body, prompt)
        self.assertNotIn("article_manuscript_revision", wf.load_state(job)["metadata"])

    def test_pattern_tasks_are_generic_and_blueprint_schema_is_current(self):
        job = self.job()
        explicit_tasks = {
            "P03": "EXPLAIN_THE_PROCESS：解释具体技术方法，并按用户要求提供操作步骤。",
            "P04": "REPORT_THE_EVENT：报道事件参与者、已发生的进展及其过程。",
        }
        for pattern in ("P01", "P02", "P03", "P04", "P05", "P06"):
            state = wf.load_state(job)
            state["selected_pattern_id"] = pattern
            wf.save_state(job, state)
            if pattern in explicit_tasks:
                bp = wf.read_json(job / "blueprints/article_blueprint.json")
                bp["article_brief"] = explicit_tasks[pattern]
                wf.atomic_json(job / "blueprints/article_blueprint.json", bp)
            prompt = wf.prompt_blueprint(job, p0=False)
            from shared import p01_writing_v2 as p01
            if pattern == "P01":
                self.assertTrue(p01.matches(prompt))
                self.assertIn(p01.MISSION_V3, runtime._initial_messages("article_blueprint", prompt)[0]["content"])
            else:
                self.assertIn(current.PATTERNS[pattern], prompt)
            schema = runtime.submit_tool_for("article_blueprint", prompt=prompt)
            fields = schema["function"]["parameters"]["properties"]["result"]["properties"]
            if pattern == "P01":
                self.assertEqual(fields["opening"]["description"], p01.blueprint_descriptions(prompt)["opening"])
            else:
                self.assertIn("导语如何自然进入主题", fields["opening"]["description"])
            self.assertIn("作者不读取此字段", fields["materials"]["description"])
            if pattern == "P01":
                self.assertEqual(fields["writing_material_markdown"]["description"], p01.blueprint_descriptions(prompt)["writing_material_markdown"])
                self.assertEqual(fields["material_adjustments"]["description"], p01.blueprint_descriptions(prompt)["material_adjustments"])
            else:
                self.assertIn("作者唯一接收的选用内容全文", fields["writing_material_markdown"]["description"])
                self.assertEqual(fields["material_adjustments"]["description"], "当前额外写作约定；没有则使用空数组。")
            if pattern in explicit_tasks:
                # The explicit explanation/news commission reaches the actual
                # blueprint and author requests, with introduction-only limits
                # scoped consistently in the registered tool schema.
                for request in (prompt, wf.prompt_article(job, p0=False)):
                    self.assertEqual(request.count(explicit_tasks[pattern]), 1)
                    self.assertIn(explicit_tasks[pattern], request.split("<current_commission>", 1)[1])
                self.assertIn("机构介绍主要篇幅", fields["sections"]["description"])
                task_description = fields["sections"]["items"]["properties"]["task"]["description"]
                self.assertIn("机构介绍不安排读者操作提示", task_description)
                self.assertIn("解释、报道等任务按当前委托", task_description)
                self.assertIn("问题解释、事件报道、明确比较及评价任务按当前委托", current.system("article_draft"))
        self.assertFalse(any(value in current.CORE + str(current.PATTERNS) for value in ("台心", "医院", "3000", "4330", "11家")))
        # The first blueprint request has no earlier blueprint from which to
        # read an example-use plan; it is about to create that plan itself.
        (job / "blueprints/article_blueprint.json").unlink()
        self.assertTrue(current.matches(wf.prompt_blueprint(job, p0=False)))

    def test_blueprint_background_remains_readable_without_inline_answer_bodies(self):
        from shared.example_acquisition import ExampleStore
        job = self.job()
        answer_body = "ORIGINAL_ANSWER_BEGIN\n" + "旧回答中的分类、提醒和选择建议。" * 250 + "\nORIGINAL_ANSWER_END"
        answer_path = job / "inputs/answer_01.md"
        answer_path.write_text(answer_body, encoding="utf-8")
        background_body = "BACKGROUND_REFERENCE_BEGIN\n" + "只作背景的另一份原回答。" * 250 + "\nBACKGROUND_REFERENCE_END"
        background = ExampleStore(job).import_user_text(background_body, "已有问题背景")
        wf.atomic_json(job / "examples/question/index.json", {"examples": [
            {**background, "path": background["text_path"], "reference_role": "content_background"},
        ]})
        state = wf.load_state(job)
        state["selected_example_route"] = "A"
        wf.save_state(job, state)
        with patch.object(wf, "answer_texts", return_value=[answer_body]):
            prompt = wf.prompt_blueprint(job, p0=False)
        for marker in ("ORIGINAL_ANSWER_BEGIN", "ORIGINAL_ANSWER_END",
                       "BACKGROUND_REFERENCE_BEGIN", "BACKGROUND_REFERENCE_END"):
            self.assertNotIn(marker, prompt)
        host = HostTools(wf.ROOT, job, "article_blueprint")
        host.configure_for_prompt(prompt)
        self.assertEqual(host.execute("read_material", {"artifact_id": "answer_01.md"})["text"], answer_body)
        self.assertEqual(host.execute("read_material", {"artifact_id": background["artifact_id"]})["text"], background_body)
        self.assertEqual(answer_path.read_text(encoding="utf-8"), answer_body)

    def _blueprint_reference_policy_fixture(self):
        from shared.example_acquisition import ExampleStore
        job = self.job()
        (job / "inputs/answer_01.md").write_text("ANSWER_BODY only optional background.", encoding="utf-8")
        store = ExampleStore(job)
        records = {
            "style": store.import_user_text("STYLE_BODY 完整文风参考。" * 20, "确认的文风参考"),
            "content_background": store.import_user_text("BACKGROUND_BODY 原回答仅供背景参考。" * 20, "问题背景"),
            "length_only": store.import_user_text("LENGTH_BODY 仅供长度统计。" * 20, "篇幅参考"),
        }
        wf.atomic_json(job / "examples/question/index.json", {"examples": [
            {**record, "path": record["text_path"], "reference_role": role}
            for role, record in records.items()
        ]})
        state = wf.load_state(job)
        state["selected_example_route"] = "A"
        wf.save_state(job, state)
        return job, {role: record["artifact_id"] for role, record in records.items()}

    def test_blueprint_read_policy_keeps_only_style_mandatory_and_preserves_old_tools(self):
        job, refs = self._blueprint_reference_policy_fixture()
        host = HostTools(wf.ROOT, job, "article_blueprint")
        answer = host.resolve_artifact("answer_01.md")["artifact_id"]
        original_definitions = json.loads(json.dumps(list(host.definitions)))
        legacy_required = {answer, refs["style"], refs["content_background"]}
        self.assertEqual(set(host.export_state()["required"]), legacy_required)
        self.assertNotIn("request_optional_required", host.export_state())

        host.configure_for_prompt(current.wrap("本轮蓝图请求"))
        inventory = host.execute("list_materials", {"limit": 100})
        self.assertEqual(set(inventory["required_artifacts"]), {refs["style"]})
        for ident in (answer, refs["content_background"], refs["length_only"]):
            self.assertIn(ident, host.artifacts)
            self.assertFalse(host.artifacts[ident]["required"])
        with self.assertRaises(ToolError) as missing:
            host.validate_complete_reads()
        self.assertIn(refs["style"], str(missing.exception))
        self.assertNotIn(answer, str(missing.exception))
        self.assertNotIn(refs["content_background"], str(missing.exception))
        host.execute("read_material", {"artifact_id": refs["style"], "limit": 5})
        with self.assertRaises(ToolError):
            host.validate_complete_reads()
        host.execute("read_material", {"artifact_id": refs["style"]})
        self.assertTrue(host.validate_complete_reads())
        # Optional does not mean unavailable: a chosen source can be read in
        # relevant pages without importing all historical answer prose.
        page = host.execute("read_material", {"artifact_id": answer, "limit": 6})
        self.assertEqual(page["text"], "ANSWER")
        self.assertFalse(page["complete_read"])
        self.assertTrue(host.validate_complete_reads())
        self.assertTrue(host.validate_result_sources({"writing_material_sources": [{"source_ref": answer, "use": "所需片段"}]}))
        self.assertIn("BACKGROUND_BODY", host.execute("read_material", {"artifact_id": refs["content_background"]})["text"])
        self.assertIn("LENGTH_BODY", host.execute("read_material", {"artifact_id": refs["length_only"]})["text"])
        new_read = next(row for row in host.definitions if row["function"]["name"] == "read_material")
        self.assertIn("Original answers, content background and length-only references are optional", new_read["function"]["description"])
        self.assertNotIn("Required examples, answers and manuscripts", new_read["function"]["description"])
        self.assertEqual(host._original_definitions, original_definitions)

        host.configure_for_prompt(requirements.MISSION_MARKER + "\n旧版蓝图请求")
        self.assertEqual(list(host.definitions), original_definitions)
        self.assertEqual(set(host.export_state()["required"]), legacy_required)
        self.assertNotIn("request_optional_required", host.export_state())
        with self.assertRaises(ToolError) as missing:
            host.validate_complete_reads()
        self.assertIn(answer, str(missing.exception))

    def test_blueprint_read_policy_survives_restore_in_both_orders_and_old_requests(self):
        job, refs = self._blueprint_reference_policy_fixture()
        original = HostTools(wf.ROOT, job, "article_blueprint")
        answer = original.resolve_artifact("answer_01.md")["artifact_id"]
        frozen_old = json.loads(json.dumps(original.export_state()))
        current_prompt = current.wrap("本轮蓝图请求")
        old_prompt = requirements.MISSION_MARKER + "\n旧版蓝图请求"
        for configure_first in (True, False):
            with self.subTest(configure_first=configure_first):
                host = HostTools(wf.ROOT, job, "article_blueprint")
                if configure_first:
                    host.configure_for_prompt(current_prompt)
                host.restore_state(frozen_old)
                if not configure_first:
                    host.configure_for_prompt(current_prompt)
                self.assertEqual(set(host.export_state()["required"]), {refs["style"]})
                host.execute("read_material", {"artifact_id": refs["style"]})
                self.assertTrue(host.validate_complete_reads())
                self.assertNotIn(answer, host.read_ranges)
                self.assertNotIn(refs["content_background"], host.read_ranges)
                # Sources registered after request binding obey the same rule;
                # their legacy obligation must survive a saved new checkpoint.
                late = host.register_text("LATE_BACKGROUND_BODY", "后来登记的背景", "content_background", True)
                self.assertNotIn(late, host.export_state()["required"])
                frozen_current = json.loads(json.dumps(host.export_state()))
                resumed = HostTools(wf.ROOT, job, "article_blueprint")
                resumed.configure_for_prompt(current_prompt)
                resumed.restore_state(frozen_current)
                self.assertEqual(set(resumed.export_state()["required"]), {refs["style"]})
                self.assertTrue(resumed.validate_complete_reads())
                resumed.configure_for_prompt(old_prompt)
                self.assertEqual(set(resumed.export_state()["required"]), {answer, refs["style"], refs["content_background"], late})
                with self.assertRaises(ToolError):
                    resumed.validate_complete_reads()
                self.assertNotIn(refs["length_only"], resumed.export_state()["required"])
                old_restore = HostTools(wf.ROOT, job, "article_blueprint")
                old_restore.configure_for_prompt(old_prompt)
                old_restore.restore_state(frozen_current)
                self.assertIn(late, old_restore.export_state()["required"])
                self.assertIn(answer, old_restore.export_state()["required"])
                old_restore.configure_for_prompt(current_prompt)
                self.assertEqual(set(old_restore.export_state()["required"]), {refs["style"]})
        self.assertEqual(frozen_old["required"], original.export_state()["required"])

    def test_single_commission_follows_inputs_while_editing_base_precedes_references(self):
        self.body = "# 内部标题\n\nCOMPLETE_BASE_BEGIN\n" + "完整基稿中的机构业务介绍。" * 500 + "\nCOMPLETE_BASE_END"
        self.repaired = self.body.replace("COMPLETE_BASE_BEGIN", "REPAIRED_BASE_BEGIN")
        selected = "SELECTED_INFORMATION_BEGIN\n" + "可供选择的对象特点和服务。" * 300 + "\nSELECTED_INFORMATION_END"
        style = "FULL_STYLE_BEGIN\n" + "独立例文的完整段落。" * 300 + "\nFULL_STYLE_END"
        for prefix in ("article", "p0"):
            with self.subTest(prefix=prefix):
                job = self.job(prefix)
                bp_path = job / "blueprints" / (prefix + "_blueprint.json")
                bp = wf.read_json(bp_path)
                bp["article_brief"] = "CURRENT_COMMISSION_MARKER 按当前委托完成自然机构介绍。"
                bp["writing_material_markdown"] = selected
                wf.atomic_json(bp_path, bp)
                self.needs_revision = True
                with patch.object(current, "_natural_examples", return_value=style):
                    self.finish(job, p0=prefix == "p0")
                for stage in ("draft", "edit", "repair"):
                    prompt = self.prompts[prefix + "_" + stage]
                    self.assertEqual(prompt.count("CURRENT_COMMISSION_MARKER"), 1, stage)
                    commission_at = prompt.index("CURRENT_COMMISSION_MARKER")
                    self.assertEqual(prompt.count(selected), 1, stage)
                    self.assertGreater(commission_at, prompt.index(selected) + len(selected), stage)
                    data_blocks = re.findall(r"<reference_data\b[^>]*>(.*?)</reference_data>", prompt, flags=re.S)
                    self.assertTrue(any(selected in block for block in data_blocks), stage)
                    if prefix == "article":
                        self.assertEqual(prompt.count(style), 1, stage)
                        self.assertGreater(commission_at, prompt.index(style) + len(style), stage)
                    if stage in {"edit", "repair"}:
                        self.assertEqual(prompt.count(self.body), 1, stage)
                        base_end = prompt.index(self.body) + len(self.body)
                        self.assertGreater(commission_at, base_end, stage)
                        self.assertLess(base_end, prompt.index(selected), stage)
                        if prefix == "article":
                            self.assertLess(base_end, prompt.index(style), stage)
                repair = self.prompts[prefix + "_repair"]
                review = wf.read_json(job / "production" / (prefix + "_editorial_review.json"))
                self.assertTrue(review["comments"])
                for comment in review["comments"]:
                    self.assertEqual(repair.count(comment), 1)
                    self.assertGreater(repair.index(comment), repair.index(self.body) + len(self.body))

    def test_one_length_target_survives_each_stage_without_temporary_budget(self):
        cases = (
            "目标约3000个正文可见字符，按2850—3150字符安排。",
            "目标约4330个正文可见字符，按4110—4550字符安排。",
            "目标约3000字，上限3000字。",
            "不超过3000字。",
            "最多3000字。",
            "3000字以内。",
        )
        original_root = self.root
        for index, target in enumerate(cases):
            with self.subTest(target=target):
                self.root = original_root / ("budget-case-" + str(index))
                self.root.mkdir()
                job = self.job()
                bp_path = job / "blueprints/article_blueprint.json"
                bp = wf.read_json(bp_path)
                bp["estimated_length"] = target
                wf.atomic_json(bp_path, bp)
                self.needs_revision = True
                prompts = {}
                for stage, build in (
                    ("draft", lambda: wf.prompt_article(job, p0=False)),
                    ("edit", lambda: wf.prompt_edit(job, p0=False)),
                    ("finalize", lambda: writing_context.prompt_finalize(wf, job, p0=False)),
                    ("repair", lambda: writing_context.prompt_repair(wf, job, p0=False)),
                ):
                    if stage != "draft":
                        self.until(job, stage)
                    state_before = (job / "job_state.json").read_bytes()
                    blueprint_before = bp_path.read_bytes()
                    prompts[stage] = build()
                    self.assertEqual((job / "job_state.json").read_bytes(), state_before, stage)
                    self.assertEqual(bp_path.read_bytes(), blueprint_before, stage)
                    self.assertEqual(requirements.effective(wf, job, p0=False)["estimated_length"], target, stage)
                    self.assertEqual(prompts[stage].count(target), 1, stage)
                    self.assertNotIn("中间稿预算", prompts[stage], stage)
                    self.assertNotIn("为后续编辑留出余量", prompts[stage], stage)
        self.root = original_root

    def test_confirmed_examples_are_kept_without_third_fictional_demonstration(self):
        original_root = self.root
        for pattern in ("P00", "P01", "P02", "P03", "P04", "P05", "P06"):
            with self.subTest(pattern=pattern):
                self.root = original_root / ("demonstration-" + pattern)
                self.root.mkdir()
                p0 = pattern == "P00"
                prefix = "p0" if p0 else "article"
                job = self.job(prefix)
                state = wf.load_state(job)
                state["selected_pattern_id"] = pattern
                wf.save_state(job, state)
                self.needs_revision = True
                with patch.object(current, "_natural_examples", return_value="CONFIRMED_EXTERNAL_STYLE_REFERENCE"):
                    blueprint = wf.prompt_blueprint(job, p0=p0)
                    self.finish(job, p0=p0)
                prompts = {"blueprint": blueprint}
                prompts.update({stage: self.prompts[prefix + "_" + stage]
                                for stage in ("draft", "edit", "finalize", "repair")})
                if p0:
                    prompts["style"] = self.prompts["p0_style"]
                for stage, prompt in prompts.items():
                    self.assertNotIn("云杉共享办公", prompt, stage)
                    self.assertNotIn("通用段落组织示意", prompt, stage)
                    if not p0:
                        self.assertEqual(prompt.count("CONFIRMED_EXTERNAL_STYLE_REFERENCE"), 1, stage)
                for stage in ("titles", "title_review"):
                    self.assertNotIn("云杉共享办公", self.prompts[prefix + "_" + stage], stage)
                    self.assertNotIn("通用段落组织示意", self.prompts[prefix + "_" + stage], stage)
        self.root = original_root

    def test_editor_length_advice_uses_visible_count_range_and_explicit_caps(self):
        self.body = "# 主标题不计\n\n" + "## 业务\n\n**甲公司** 提供 A2 项服务。\n\n后续安排。\n\n" * 20
        self.repaired = self.body
        actual = natural_editor.character_count(self.body)
        self.assertEqual(actual, 360)
        cases = (
            ("目标约3000个正文可见字符。", True),
            ("目标约4,330字符。", True),
            ("目标约500字符，按400—550字符安排。", True),
            ("目标约370字符，按350—390字符安排。", False),
            ("目标约360字符。", False),
            ("目标约350字符。", False),
            ("目标约3000字，上限3000字。", False),
            ("目标约3000字，不超过3000字。", False),
            ("目标约3000字，最多3000字。", False),
            ("目标约3000字，保持3000字以内。", False),
        )
        original_root = self.root
        for index, (target, needs_expansion) in enumerate(cases):
            with self.subTest(target=target):
                self.root = original_root / ("length-difference-" + str(index))
                self.root.mkdir()
                job = self.job()
                bp_path = job / "blueprints/article_blueprint.json"
                bp = wf.read_json(bp_path)
                bp["estimated_length"] = target
                wf.atomic_json(bp_path, bp)
                self.needs_revision = True
                self.finish(job)
                self.assertNotIn("还需至少展开", self.prompts["article_draft"])
                for stage in ("edit", "repair"):
                    prompt = self.prompts["article_" + stage]
                    self.assertEqual(prompt.count(target), 1, stage)
                    self.assertIn("当前完整基稿的实际正文字符数：" + str(actual), prompt, stage)
                    if needs_expansion:
                        self.assertEqual(prompt.count("还需至少展开"), 1, stage)
                    else:
                        self.assertNotIn("还需至少展开", prompt, stage)
                    if "350—390" in target:
                        self.assertIn("当前稿已在委托篇幅范围内", prompt, stage)
                self.assertEqual(requirements.effective(wf, job, p0=False)["estimated_length"], target)
        self.root = original_root

    def test_request_scoped_tools_and_old_marker_restore(self):
        job = self.job()
        self.until(job, "finalize")
        review = HostTools(wf.ROOT, job, "article_finalize")
        old = list(review.definitions)
        review.configure_for_prompt(writing_context.prompt_finalize(wf, job, p0=False))
        self.assertEqual(review.definitions(), [])
        with self.assertRaises(ToolError):
            review.execute("read_material", {"artifact_id": "inputs/facts.md"})
        payload = runtime.build_payload("article_finalize", writing_context.prompt_finalize(wf, job, p0=False), tools=old)
        self.assertEqual([tool["function"]["name"] for tool in payload["tools"]], ["submit_result"])
        review.configure_for_prompt(requirements.MISSION_MARKER + "\nold request")
        self.assertEqual(review.definitions(), old)
        blueprint = HostTools(wf.ROOT, job, "article_blueprint")
        blueprint.configure_for_prompt(wf.prompt_blueprint(job, p0=False))
        self.assertEqual({tool["function"]["name"] for tool in blueprint.definitions},
                         {"list_materials", "read_material", "search_materials", "extract_document"})

    def test_real_sdk_plan_submits_without_any_lookup_and_caches(self):
        job = self.job()
        self.until(job, "finalize")
        prompt = writing_context.prompt_finalize(wf, job, p0=False)
        package = self.root / "offline-package"
        package.mkdir()
        tools = HostTools(package, job, "article_finalize")
        sdk, engine = bundle(fault="unread", result={"needs_revision": False, "comments": []})
        result = runtime.run_action(package, job, "article_finalize", prompt, natural_editor.validate_review,
                                    host_tools=tools, transport=sdk, offline=True)
        self.assertEqual(result, {"needs_revision": False, "comments": []})
        record = runtime.action_record(job, "article_finalize")
        attempt = job / "provider/article_finalize/runtime/attempts" / record["attempt_id"]
        plan = wf.read_json(attempt / "request_plan.json")
        self.assertEqual([tool["function"]["name"] for tool in plan["tools"]], ["submit_result"])
        calls = engine.calls
        self.assertEqual(runtime.run_action(package, job, "article_finalize", prompt, natural_editor.validate_review,
                         host_tools=HostTools(package, job, "article_finalize"), transport=sdk, offline=True), result)
        self.assertEqual(engine.calls, calls)

    def test_title_requests_keep_recommendation_task_and_p0_original_route(self):
        job = self.job()
        self.finish(job)
        prompt = writing_context.prompt_title_review(wf, job, p0=False)
        tools = HostTools(wf.ROOT, job, "article_title_review")
        tools.configure_for_prompt(prompt)
        tools.record_inline_inputs(runtime._initial_messages("article_title_review", prompt))
        self.assertTrue(tools.validate_complete_reads())
        self.assertEqual(tools.definitions(), [])
        for pattern in ("P01", "P02"):
            state = wf.load_state(job)
            state["selected_pattern_id"] = pattern
            wf.save_state(job, state)
            for action, request in (
                ("article_titles", current.prompt_titles(wf, job, p0=False)),
                ("article_title_review", current.prompt_title_review(wf, job, p0=False)),
            ):
                messages = runtime._initial_messages(action, request)
                self.assertIn(current.TITLE_RULES, messages[0]["content"], action)
                self.assertIn("同组应包含明确表达推荐任务", messages[0]["content"], action)
                self.assertIn('"pattern_id": "' + pattern + '"', messages[1]["content"], action)
                self.assertIn(self.body.split("\n", 1)[1], messages[1]["content"], action)
        # P0 keeps its established title skill and exact v13 user-request path.
        from shared import writing_context_v13 as previous
        p0_job = self.job("p0")
        self.finish(p0_job, p0=True)
        for action, request, original, system in (
            ("p0_titles", current.prompt_titles(wf, p0_job, p0=True),
             previous._natural_titles_prompt(wf, p0_job, p0=True), runtime.DEEPSEEK_TITLES_SYSTEM),
            ("p0_title_review", current.prompt_title_review(wf, p0_job, p0=True),
             previous._natural_title_review_prompt(wf, p0_job, p0=True), runtime.GLM_TITLE_REVIEW_SYSTEM),
        ):
            messages = runtime._initial_messages(action, request)
            self.assertEqual(messages[0]["content"], system, action)
            self.assertEqual(request.split("\n", 1)[1], original.split("\n", 1)[1], action)
            self.assertNotIn(current.TITLE_RULES, messages[0]["content"], action)

    def test_selected_content_and_example_use_reach_writers_without_full_source_reinjection(self):
        for prefix in ("article", "p0"):
            with self.subTest(prefix=prefix):
                job = self.job(prefix)
                source = job / "inputs/user_materials" / ("p0" if prefix == "p0" else "question") / "selected_company.md"
                source.parent.mkdir(parents=True)
                body = "FULL_ORIGINAL_START\n" + "具体业务内容。" * 4000 + "\nUNSELECTED_FAQ_INSTRUCTIONS\nFULL_ORIGINAL_END"
                source.write_text(body, encoding="utf-8")
                tools = HostTools(wf.ROOT, job, prefix + "_blueprint")
                source_id = tools.resolve_artifact(source.name)["artifact_id"]
                binary = source.with_name("brochure.pdf")
                binary.write_bytes(b"original binary fixture")
                binary_id = tools.register_file(binary.resolve())
                extracted = tools.register_text("EXTRACTED_CONTENT_END", "brochure text", "extracted_text")
                tools._derived[binary_id] = extracted
                blocked = []
                for role in ("example", "length_reference", "content_background", "answer", "brand_background", "manuscript"):
                    item = source.with_name(role + ".md")
                    item.write_text("BLOCKED_" + role)
                    blocked.append(tools.register_file(item.resolve(), role))
                config = source.with_name("current_commission.json")
                config.write_text('{"value":"BLOCKED_COMMISSION"}')
                blocked.append(tools.register_file(config.resolve()))
                old_report = job / "research/brand_market/old.md"
                old_report.parent.mkdir(parents=True)
                old_report.write_text("BLOCKED_OLD_REPORT")
                blocked.append(tools.register_file(old_report.resolve()))
                snapshot = tools.export_state()
                runtime_root = job / "provider" / (prefix + "_blueprint") / "runtime"
                attempt = runtime_root / "attempts/source-selection"
                attempt.mkdir(parents=True)
                wf.atomic_json(runtime_root / "latest.json", {"attempt_id": "source-selection"})
                if prefix == "article":
                    wf.atomic_json(attempt / "submission.json", {"tool_file": "tool_submit.json"})
                    wf.atomic_json(attempt / "tool_submit.json", {"host_state": snapshot})
                else:
                    wf.atomic_json(attempt / "checkpoint.json", {"host_tools": snapshot})
                # Later review/title actions legitimately replace this registry.
                wf.atomic_json(job / "artifacts/host_registry.json", {"artifacts": {}})
                bp_path = job / "blueprints" / (prefix + "_blueprint.json")
                bp = wf.read_json(bp_path)
                selected = "SELECTED_BUSINESS_START\n" + "主体已选的具体业务与服务内容。" * 250 + "\nSELECTED_BUSINESS_END"
                bp["writing_material_markdown"] = selected
                bp["example_use"] = "EXAMPLE_TRANSFER_GUIDE：主参考以具体业务动作连接段落；本篇用项目与服务事实完成相同推进。"
                bp["opening"] = "DRAFT_ONLY_OPENING 构思开篇的方式。"
                bp["sections"] = [{"heading": "SELECTED_SECTION_SCOPE", "task": "SELECTED_SECTION_TASK 按已有内容分配篇幅。"}]
                bp["ending"] = "DRAFT_ONLY_ENDING 完成本篇介绍。"
                bp["estimated_length"] = "ORIGINAL_LENGTH_TARGET：3000个正文可见字符。"
                refs = [source_id, source.name, binary_id, extracted, *blocked]
                bp["writing_material_sources"] = [{"source_ref": ref, "use": "PRIVATE_SOURCE_NOTE"} for ref in refs]
                bp["writing_material_sources"] += [source.relative_to(job).as_posix(), "legacy prose-only source note"]
                wf.atomic_json(bp_path, bp)
                self.needs_revision = True
                self.finish(job, p0=prefix == "p0")
                stages = ("draft", "edit", "repair", "style") if prefix == "p0" else ("draft", "edit", "repair")
                for stage in stages:
                    prompt = self.prompts[prefix + "_" + stage]
                    self.assertEqual(prompt.count(selected), 1, stage)
                    data_blocks = re.findall(r"<reference_data\b[^>]*>(.*?)</reference_data>", prompt, flags=re.S)
                    self.assertTrue(any(selected in block for block in data_blocks), stage)
                    if prefix == "article" or stage in {"style", "repair"}:
                        self.assertEqual(prompt.count("EXAMPLE_TRANSFER_GUIDE"), 1, stage)
                    else:
                        self.assertNotIn("EXAMPLE_TRANSFER_GUIDE", prompt, stage)
                    for marker in ("FULL_ORIGINAL_START", "FULL_ORIGINAL_END", "UNSELECTED_FAQ_INSTRUCTIONS", "EXTRACTED_CONTENT_END"):
                        self.assertNotIn(marker, prompt, stage)
                    self.assertNotIn("BLOCKED_", prompt, stage)
                    self.assertNotIn("PRIVATE_SOURCE_NOTE", prompt, stage)
                    self.assertEqual(prompt.count("ORIGINAL_LENGTH_TARGET"), 1, stage)
                    if stage in {"edit", "repair"}:
                        self.assertIn("当前完整基稿的实际正文字符数：" + str(natural_editor.character_count(self.body)), prompt, stage)
                    for marker in ("DRAFT_ONLY_OPENING", "SELECTED_SECTION_SCOPE", "DRAFT_ONLY_ENDING"):
                        if stage == "draft":
                            self.assertIn(marker, prompt, stage)
                            self.assertTrue(any(marker in block for block in data_blocks), stage)
                        else:
                            self.assertNotIn(marker, prompt, stage)
                review = self.prompts[prefix + "_finalize"]
                self.assertEqual(review.count("EXAMPLE_TRANSFER_GUIDE"), 1)
                for marker in ("SELECTED_SECTION_SCOPE", "SELECTED_SECTION_TASK"):
                    self.assertIn(marker, review)
                for marker in ("DRAFT_ONLY_OPENING", "DRAFT_ONLY_ENDING", "FULL_ORIGINAL_START",
                               "EXTRACTED_CONTENT_END", "SELECTED_BUSINESS_START", "UNSELECTED_FAQ_INSTRUCTIONS", "PRIVATE_SOURCE_NOTE"):
                    self.assertNotIn(marker, review)
                self.assertEqual(source.read_text(), body)

    def test_explicit_material_scope_keeps_current_sources_and_legacy_requests(self):
        job = self.job()
        original = job / "inputs/user_materials/question/source.md"
        original.parent.mkdir(parents=True)
        original.write_text("CURRENT_ORIGINAL")
        answer = job / "inputs/answer_01.md"
        answer.write_text("CURRENT_BACKGROUND")
        example = job / "examples/style.md"
        example.parent.mkdir(exist_ok=True)
        example.write_text("CURRENT_STYLE")
        report = job / "research/brand_market/old.md"
        report.parent.mkdir(parents=True)
        report.write_text("OLD_GENERATED_REPORT")
        state = wf.load_state(job)
        state["metadata"]["blueprint_material_roots"] = ["inputs/user_materials/question"]
        wf.save_state(job, state)
        tools = HostTools(wf.ROOT, job, "article_blueprint")
        self.assertEqual({Path(row["path"]).name for row in tools.artifacts.values()},
                         {"source.md", "answer_01.md", "style.md"})
        self.assertIn("CURRENT_ORIGINAL", tools.execute("read_material", {"artifact_id": "source.md"})["text"])
        for ref in ("old.md", "company.md"):
            with self.assertRaises(ToolError):
                tools.execute("read_material", {"artifact_id": ref})
        state["metadata"]["writing_mission_input_mode"] = requirements.WRITING_MISSION_INPUT_MODE
        wf.save_state(job, state)
        historical = HostTools(wf.ROOT, job, "article_blueprint")
        self.assertIn("OLD_GENERATED_REPORT", historical.execute("read_material", {"artifact_id": "old.md"})["text"])
        self.assertIn("合成机构", historical.execute("read_material", {"artifact_id": "company.md"})["text"])

    def test_scoped_blueprint_keeps_reference_roles_and_coherent_saved_dependencies(self):
        from shared.example_acquisition import ExampleStore
        job = self.job()
        original = job / "inputs/user_materials/question/business.md"
        original.parent.mkdir(parents=True)
        original.write_text("ACTUAL_BUSINESS_CONTENT")
        for index in (1, 2):
            (job / "inputs" / f"answer_{index:02}.md").write_text(f"CURRENT_ANSWER_{index}")
        with zipfile.ZipFile(job / "00_input/reference_pack.zip", "w") as archive:
            archive.writestr("materials/answer_old.md", "OLD_PACK_ANSWER")
            archive.writestr("materials/company.md", "OLD_PACK_BUSINESS")
        store = ExampleStore(job)
        length = store.import_user_text("LENGTH_ONLY_BODY", "Selected length sample")
        background = store.import_user_text("CURRENT_ANSWER_1", "Selected background")
        wf.atomic_json(job / "examples/question/index.json", {"examples": [
            {**length, "reference_role": "length_only"},
            {**background, "reference_role": "content_background"},
        ]})
        state = wf.load_state(job)
        state["selected_example_route"] = "A"
        state["metadata"]["blueprint_material_roots"] = ["inputs/user_materials/question"]
        wf.save_state(job, state)
        register_examples = HostTools._register_selected_examples

        def register_with_previous_reads(host):
            register_examples(host)
            old = host.resolve_artifact("answer_old.md")
            # A previously inspected item is removed by the explicit input
            # scope; none of its saved read/derivation references may remain.
            old_id = old["artifact_id"]
            host._read({"artifact_id": old_id})
            host.inline_reads[old_id] = {"sha256": old["sha256"]}
            host._derived[old_id] = old_id

        with patch.object(HostTools, "_register_selected_examples", register_with_previous_reads):
            host = HostTools(wf.ROOT, job, "article_blueprint")
        self.assertEqual(host.artifacts[length["artifact_id"]]["category"], "length_reference")
        self.assertEqual(host.artifacts[background["artifact_id"]]["category"], "content_background")
        self.assertEqual(host.execute("read_material", {"artifact_id": "business.md"})["text"], "ACTUAL_BUSINESS_CONTENT")
        self.assertEqual(host.execute("read_material", {"artifact_id": length["artifact_id"]})["text"], "LENGTH_ONLY_BODY")
        self.assertEqual(host.execute("read_material", {"artifact_id": background["artifact_id"]})["text"], "CURRENT_ANSWER_1")
        saved = host.export_state()
        valid = set(saved["artifacts"])
        for key in ("dependencies", "read_ranges", "inline_reads", "derived"):
            self.assertLessEqual(set(saved[key]), valid, key)
        self.assertLessEqual(set(saved["derived"].values()), valid)
        self.assertEqual({row["artifact_id"] for row in host.cache_dependencies()}, set(saved["dependencies"]))
        self.assertNotIn("OLD_PACK_", json.dumps(saved))
        for ref in ("answer_old.md", "company.md"):
            with self.assertRaises(ToolError):
                host.execute("read_material", {"artifact_id": ref})

    def test_v1_prompts_payloads_and_request_fingerprints_match_release_goldens(self):
        # Captured from the unmodified v13 package using this existing fixture.
        expected = {
            "article_blueprint": ("87acb9803a89233e374e4f662ee199d42d3293e36b591d4c4c7e7ed45222f78b", "4eaddebbedf3754853d61fe79802e7654a1af6fede0f74a82ed93a24291ddf4f", "ccca8c0d0d8a20ba44bdf198e2cca699b0e4c2cb05af67b58db350775f5945dc"),
            "article_draft": ("a22f9ee1b0a880cc1fa9b1662ae7661a930a56ab5938e13765a805da0408b0bc", "7d7674a80e572396ac48deb497f1ad981bf2009c039289867094a0e4d8446406", "690cde0aa76967814264843ef67e3a9e2cf15a6e9513864de7488cab5832f7c3"),
            "article_edit": ("0180762db8bd9d05e7b147fd6fdc1ce4dad6c8b7b9d6345fea5f2784b3de213f", "53c20908613bebcd0320a966efadb70bceb057b7c9101a3ac3623055bd1bf5d7", "664e164ff8716ba77cba691d5dc7ebc3692918732dada8278e25ef9e40b39f48"),
            "article_finalize": ("571717a856888a354633a7bf7c747f4d3fdf9f46b40b6458216e2a561582c1b8", "e56ec11f5a516b1f048aec53987338ddf01cd6c95841fa5a794e9199350c6b24", "e6a00fc1290f06dda70c2bba8ecb44fa1dde404557b9ae6c2df48bd0a469aec7"),
            "article_repair": ("cde1ac72533e1eabd233d8b6f47ac72be76e465907e660d1c265dd16745137c3", "31e0322cdd45b742a69da7a6da4b102b24477bedb0647e99e19cc7b8bc96e1b9", "2525171c5f6d3a06a195532a6d881aa54a4141f73ccbbc9368981c2728d2055f"),
        }
        job = flow.NaturalEditorFlowTests.job(self)
        state = wf.load_state(job)
        state["metadata"]["writing_mission_input_mode"] = requirements.WRITING_MISSION_INPUT_MODE
        wf.save_state(job, state)
        blueprint = wf.prompt_blueprint(job, p0=False)
        self.needs_revision = True
        self.finish(job)
        for action, prompt in {"article_blueprint": blueprint, **self.prompts}.items():
            if action not in expected:
                continue
            payload = runtime.build_payload(action, prompt)
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.assertEqual((hashlib.sha256(prompt.encode()).hexdigest(), hashlib.sha256(encoded.encode()).hexdigest(),
                              runtime.request_fingerprint(action, prompt)), expected[action], action)


if __name__ == "__main__":
    unittest.main()
