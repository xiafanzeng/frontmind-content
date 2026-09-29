"""Offline title input, task-mode and model-boundary regressions.

These tests verify the actual requests and frozen inputs. They do not claim
that a provider generated good headlines; semantic quality needs real output.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from shared import manuscript_revision as revisions, model_runtime as runtime, p0_titles
from shared.editorial_contracts import EditorialContractError
from shared.writing_context import PATTERN_GUIDANCE, prompt_titles

# 作者档位跟随本包 config/deepseek.json 的显式覆盖（用户2026-09-22定为high；缺省默认max）。
# 断言验证配置一致性，而不是钉死某一档位。
import json as _json
from pathlib import Path as _Path
try:
    _cfgf = _Path(__file__).resolve().parents[2] / 'config' / 'deepseek.json'
    _WRITER_EFFORT = (_json.loads(_cfgf.read_text()).get('reasoning_effort') or 'max') if _cfgf.exists() else 'max'
except Exception:
    _WRITER_EFFORT = 'max'



class TitleGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.job = Path(self.temporary.name)
        self.state = {"metadata": {}, "selected_pattern_id": "P03"}
        self.workflow = SimpleNamespace(
            load_state=lambda job: self.state,
            read_json=lambda path: json.loads(path.read_text(encoding="utf-8")),
        )

    def save(self, relative, value):
        path = self.job / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def prompt(self, body=None, *, p0=True):
        return prompt_titles(self.workflow, self.job, p0=p0, final_markdown=body)

    def test_body_and_task_determine_request_without_reading_old_blueprint_or_pack(self):
        self.save("blueprints/p0_blueprint.json", {"title": "过时蓝图标题", "article_brief": "过时品牌通稿安排"})
        self.save("materials/archive.json", {"source": "原件中未采用的客户体验与宣传承诺"})
        body = "# 旧的流程科普标题\n\n## 服务\n合成企业甲提供不同服务。\n\n## 案例\n案例仍处测试阶段，尚未完成交付。\n"
        prompt = self.prompt(body)
        # Full text and end-of-article qualification travel together; neither
        # old H1 nor archive items replace the actual final manuscript.
        self.assertEqual(prompt.count(body.split("\n", 1)[1]), 1)
        self.assertNotIn("旧的流程科普标题", prompt)
        self.assertNotIn("过时蓝图标题", prompt)
        self.assertNotIn("过时品牌通稿安排", prompt)
        self.assertNotIn("原件中未采用的客户体验与宣传承诺", prompt)
        self.assertIn("仅去除了首个文章H1行，避免旧标题锚定", prompt)
        self.assertIn("P0 的20项全部是品牌品宣标题，均可供用户选择", prompt)
        self.assertIn("整家品牌为介绍主体", prompt)
        self.assertIn("问句不是禁用词", p0_titles.guidance())

    def test_each_question_pattern_retains_its_own_task_and_never_receives_p0_only_rule(self):
        body = "# 合成问题\n\n本题比较甲和乙；按当前需求优先考虑乙。\n"
        prompts = {}
        for pattern in ("P01", "P02", "P03", "P04", "P05", "P06"):
            with self.subTest(pattern=pattern):
                self.state["selected_pattern_id"] = pattern
                prompts[pattern] = self.prompt(body, p0=False)
                self.assertIn(f"Pattern：{pattern}", prompts[pattern])
                self.assertIn(PATTERN_GUIDANCE[pattern], prompts[pattern])
                self.assertNotIn(PATTERN_GUIDANCE["P00"], prompts[pattern])
                self.assertNotIn("P0 的20项全部是品牌品宣标题", prompts[pattern])
                self.assertIn("问题优化提供20个标题", prompts[pattern])
                self.assertIn("不因拟标题另改推荐顺序", prompts[pattern])
                self.assertIn(body.split("\n", 1)[1], prompts[pattern])
        # Mode is selected by the route, not inferred from the H1 punctuation.
        self.state["selected_pattern_id"] = "P01"
        self.assertIn("Pattern：P00", self.prompt(body, p0=True))
        self.assertEqual(len(set(prompts.values())), 6)

    def test_same_editorial_rules_handle_different_industries_and_author_perspectives(self):
        bodies = (
            "# 服务介绍\n\n合成机构开展项目评估；本文说明如何形成结论，附一个项目的实际复核过程。\n",
            "# 门店介绍\n\n合成门店位于某社区，提供包间，接受生日聚餐预订；资料没有作者到访记录。\n",
            "# 真实使用记录\n\n作者实际使用合成设备一周，本文逐项记录已观察到的体验与限制。\n",
        )
        envelopes = []
        for body in bodies:
            prompt = self.prompt(body)
            body_without_h1 = body.split("\n", 1)[1]
            self.assertEqual(prompt.count(body_without_h1), 1)
            envelopes.append(prompt.replace(body_without_h1, "<FULL_MANUSCRIPT>"))
        self.assertEqual(envelopes[0], envelopes[1])
        self.assertEqual(envelopes[1], envelopes[2])
        common = envelopes[0]
        self.assertIn("不按行业公式或固定角度配额", runtime.DEEPSEEK_TITLES_SYSTEM)
        self.assertIn("既不虚构第一人称体验，也不一律排除正文已有的真实作者体验", runtime.DEEPSEEK_TITLES_SYSTEM)
        self.assertIn("不把项目问答、合规限制或逐章小题当作品牌长文标题", common)

    def test_old_headline_has_no_effect_and_full_body_without_h1_is_also_supported(self):
        body = "\r\n## 章节\r\n完整内容。\r\n# 后续正文标题保留\r\n最后条件。\r\n"
        first = self.prompt("# 旧标题甲\r\n" + body)
        second = self.prompt("# 完全不同的旧标题乙\r\n" + body)
        self.assertEqual(first, second)
        self.assertIn(body, first)
        self.assertNotIn("旧标题甲", first)
        no_h1 = "FINAL_TITLE_BEGIN\n\n## 完整章节\n内容及适用条件。\nFINAL_TITLE_END"
        self.assertIn(no_h1, self.prompt(no_h1))
        with self.assertRaises(EditorialContractError):
            self.prompt("# 只有标题\n")

    def test_current_verified_full_final_precedes_stale_provider_final_for_both_routes(self):
        for prefix in ("p0", "article"):
            with self.subTest(prefix=prefix):
                body = f"# 当前{prefix}\n\n首段。\n\n最后限定：只适用于本项目的当前阶段。\n"
                self.save(f"production/{prefix}_finalized.json", {"outcome": "revised", "article_markdown": body})
                self.save(f"provider/{prefix}_finalize/result.json", {"outcome": "accepted", "article_markdown": "# 过时供应商稿\n\n旧版内容。\n"})
                prompt = self.prompt(p0=prefix == "p0")
                self.assertIn(body.split("\n", 1)[1], prompt)
                self.assertNotIn("过时供应商稿", prompt)

    def test_title_revision_uses_verified_published_body_without_old_h1_and_current_request(self):
        host = "# 原宿主H1\n\n不可更改的完整正文。\n"
        published = host.replace("原宿主H1", "用户上一轮实际选定的H1")
        finalized = self.save("production/p0_finalized.json", {"outcome": "accepted", "article_markdown": host})
        request = "保留客观语气，增加不同读者关切的标题供我选择。"
        self.state["metadata"]["p0_title_revision"] = {
            "base_markdown": published,
            "base_sha256": revisions.text_hash(published),
            "edits_markdown": request,
            "edits_sha256": revisions.text_hash(request),
            "source": {"finalized_sha256": revisions.file_hash(finalized),
                       "host_final_markdown_sha256": revisions.text_hash(host)},
        }
        # An explicit stale argument must not override the frozen revision.
        prompt = self.prompt("# 不该使用的传入稿\n\n旧正文。\n")
        self.assertIn(published.split("\n", 1)[1], prompt)
        self.assertNotIn("用户上一轮实际选定的H1", prompt)
        self.assertIn(request, prompt)
        self.assertNotIn("不该使用的传入稿", prompt)
        self.assertNotIn(host, prompt)
        self.state["metadata"]["p0_title_revision"]["base_markdown"] += "篡改正文"
        with self.assertRaises(ValueError):
            self.prompt()

    def test_no_titles_without_a_successfully_finalized_complete_manuscript(self):
        for p0 in (True, False):
            prefix = "p0" if p0 else "article"
            with self.subTest(p0=p0):
                self.save(f"production/{prefix}_finalized.json", {"outcome": "incomplete", "article_markdown": "# 未通过稿\n\n不应直接拟题。"})
                with self.assertRaises(EditorialContractError) as error:
                    self.prompt(p0=p0)
                self.assertEqual(error.exception.code, "final_article_missing")

    def test_actual_title_payloads_keep_writer_identity_and_recommendation_is_not_selection(self):
        body = "# 合成文章\n\n这是当前完整终稿。\n"
        for p0 in (True, False):
            action = "p0_titles" if p0 else "article_titles"
            with self.subTest(action=action):
                prompt = self.prompt(body, p0=p0)
                payload = runtime.build_payload(action, prompt)
                self.assertEqual(payload["messages"], [
                    {"role": "system", "content": p0_titles.system(action) if p0 else runtime.DEEPSEEK_TITLES_SYSTEM},
                    {"role": "user", "content": prompt},
                ])
                self.assertEqual(payload["model"], "deepseek-v4-pro")
                if p0:
                    self.assertIn("不要求20种传播主题", payload["messages"][0]["content"])
                    self.assertIn("角度可重复", payload["messages"][0]["content"])
                else:
                    self.assertIn("不要求20个不同传播主题", payload["messages"][0]["content"])
                    self.assertIn("angle可以重复", payload["messages"][0]["content"])
                self.assertEqual(payload["thinking"], {"type": "enabled"})
                self.assertEqual(payload["reasoning_effort"], _WRITER_EFFORT)
                self.assertEqual(payload["response_format"], {"type": "json_object"})
                self.assertFalse({"speed", "service_tier", "temperature"} & payload.keys())
                self.assertIn("candidates 是20项的数组，每项含 title 和 angle", prompt)
                self.assertIn("按数组位置编号 title_01 至 title_20", prompt)
                self.assertNotIn("families", prompt)
                self.assertNotIn("decision_title_", prompt)
                self.assertNotIn("media_title_", prompt)
                self.assertIn("它只是模型推荐", prompt)
                self.assertIn("供用户发布时自行选用", prompt)
                self.assertIn("不将推荐项或候选表回填到正文文档", prompt)
                self.assertIn("angle 只是表内说明，不是标题的一部分", prompt)
                self.assertNotIn("必须从 media_pr 组选择", prompt)


if __name__ == "__main__":
    unittest.main()
