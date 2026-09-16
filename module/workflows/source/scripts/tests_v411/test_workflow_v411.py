#!/usr/bin/env python3
"""Offline flow regression tests for the v4.11 single-Pack workflow.

Deterministic fixtures exercise wiring, never provider research or semantic quality.
Production controller contracts use controlled outputs in test_positioning_contracts.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.docx_font_embedding import audit_docx_embedded_fonts  # noqa: E402


LAUNCHER = ROOT / "scripts/frontmind"
FIXTURE = ROOT / "acceptance_fixtures/v4.11_synthetic"
CROSS_INDUSTRY_FIXTURE = ROOT / "acceptance_fixtures/v4.11_cross_industry"
PYTHON = Path(os.environ.get("FRONTMIND_PYTHON") or os.sys.executable)

SHORT_POSITIONING_FIELDS = {
    "one_sentence", "one_sentence_draft", "one_sentence_positioning",
}
PRODUCTION_POSITIONING_FILES = (
    ROOT / "scripts/frontmind_workflow.py",
    ROOT / "Reference_Pack_Workflow/shared/reference_pack_builder.py",
    ROOT / "shared/competitive_choice_map.schema.json",
    ROOT / "shared/core_positioning_directions.schema.json",
    ROOT / "shared/core_positioning.schema.json",
    ROOT / "shared/positioning_direction_review.schema.json",
    ROOT / "shared/core_positioning_review.schema.json",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTROLLER = load_module("frontmind_v411_controller", ROOT / "scripts/frontmind_workflow.py")
BUILDER = load_module(
    "frontmind_v411_builder", ROOT / "Reference_Pack_Workflow/shared/reference_pack_builder.py",
)


class CommandError(AssertionError):
    pass


def run_cli(*arguments: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(LAUNCHER), *arguments], cwd=ROOT, text=True, capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False,
    )
    if result.returncode != expect:
        raise CommandError(
            f"expected {expect}, got {result.returncode}: {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def state(job: Path) -> dict:
    return json.loads((job / "job_state.json").read_text(encoding="utf-8"))


def resume(job: Path, *arguments: str, revision: int | None = None, expect: int = 0) -> subprocess.CompletedProcess[str]:
    current_revision = state(job)["revision"] if revision is None else revision
    return run_cli(
        "continue", "--job-dir", str(job), "--revision", str(current_revision),
        *arguments, expect=expect,
    )


def confirm_competitors(job: Path) -> None:
    """Submit the fixture user's scope confirmation through the public CLI."""
    current = state(job)
    if current["status"] != "awaiting_competitor_selection":
        raise CommandError(f"expected competitor selection, got {current['status']}")
    if not current["current_pause"]["must_stop"] or (job / "positioning/core_positioning.json").exists():
        raise CommandError("research must pause before producing the core positioning")
    resume(job, "--confirm-competitors")
    if state(job)["status"] != "awaiting_core_positioning_confirmation":
        raise CommandError("confirmed competitors did not advance to final positioning confirmation")


def page(job: Path) -> str:
    current = state(job)["current_pause"]
    return Path(current["review_markdown_path"]).read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def schema_errors(instance_path: Path, schema_path: Path) -> list:
    from shared.scripts.validate_json_instance import load_json, validate_instance

    return validate_instance(load_json(instance_path), load_json(schema_path), schema_path)


def write_sparse_zip(path: Path, member_size: int) -> None:
    """Create a valid sparse stored ZIP without allocating member_size bytes."""

    name = b"large.bin"
    crc = 0
    zero = b"\0" * (1024 * 1024)
    remaining = member_size
    while remaining:
        block = zero if remaining >= len(zero) else zero[:remaining]
        crc = zlib.crc32(block, crc)
        remaining -= len(block)
    local = struct.pack(
        "<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 0,
        crc & 0xFFFFFFFF, member_size, member_size, len(name), 0,
    ) + name
    central = struct.pack(
        "<IHHHHHHIIIHHHHHII", 0x02014B50, 0x0314, 20, 0, 0, 0, 0,
        crc & 0xFFFFFFFF, member_size, member_size, len(name), 0, 0, 0, 0,
        (stat.S_IFREG | 0o644) << 16, 0,
    ) + name
    with path.open("wb") as handle:
        handle.write(local)
        handle.seek(member_size, os.SEEK_CUR)
        central_offset = handle.tell()
        handle.write(central)
        central_size = len(central)
        handle.write(struct.pack(
            "<IHHHHIIH", 0x06054B50, 0, 0, 1, 1,
            central_size, central_offset, 0,
        ))


def direction_fixture(path: Path, count: int, *, source: Path | None = None) -> Path:
    """Write an explicit offline fixture with zero to five candidate opportunities."""

    text = (source or FIXTURE / "brand_material.md").read_text(encoding="utf-8")
    lines = [
        line for line in text.splitlines()
        if not line.startswith("方向数量：") and not line.startswith("定位机会：")
    ]
    opportunity_names = (
        "复杂情况后的连续响应",
        "常规需求中的专项效率",
        "长期使用中的持续负责",
        "跨主体任务的统一协调",
        "高频轻量需求的便利交付",
    )
    lines.append(f"方向数量：{count}")
    lines.extend(f"定位机会：{name}" for name in opportunity_names[:count])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def contains_key(value: object, keys: set[str]) -> bool:
    if isinstance(value, dict):
        return bool(keys.intersection(value)) or any(contains_key(item, keys) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, keys) for item in value)
    return False


class WorkflowV411Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="frontmind-v411-tests-")
        cls.base = Path(cls.temp.name)
        cls.manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
        cls.brand = cls.manifest["brand"]

        cls.rp_job = cls.base / "reference-pack-job"
        run_cli(
            "reference-pack", "create", "--brand", cls.brand,
            "--input", str(FIXTURE / "brand_material.md"),
            "--job-dir", str(cls.rp_job), "--offline-fixture",
        )
        confirm_competitors(cls.rp_job)
        resume(cls.rp_job, "--confirm-core-positioning")
        cls.positioning_pack = cls.rp_job / "deliverables/Reference_Pack_v1"

        cls.p0_job = cls.base / "p0-job"
        run_cli(
            "p0", "--reference-pack", str(cls.positioning_pack),
            "--job-dir", str(cls.p0_job), "--offline-fixture",
        )
        resume(cls.p0_job, "--reference-pack-route", "use")
        resume(cls.p0_job, "--p0-route", "create")
        resume(cls.p0_job, "--accept-p0-example-route", "top20")
        resume(cls.p0_job, "--accept-p0-blueprint")
        cls.p0_pack = cls.p0_job / "deliverables/Reference_Pack_v2"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def start_article(self, name: str, case: dict, *, answers: bool = True) -> Path:
        job = self.base / name
        command = [
            "article", "--reference-pack", str(self.p0_pack), "--job-dir", str(job),
            "--question-id", case["question_id"], "--question", case["question"],
            "--offline-fixture",
        ]
        if answers:
            command.extend([
                "--answer", str(FIXTURE / "answer_01.md"),
                "--answer", str(FIXTURE / "answer_02.md"),
            ])
        run_cli(*command)
        return job

    def advance_to_pattern(self, job: Path) -> None:
        resume(job, "--reference-pack-route", "use")
        resume(job, "--no-extra-response-requirements", "--ai-brand-recognition", "insufficient")

    def start_direction_job(self, name: str, count: int) -> Path:
        material = direction_fixture(self.base / f"{name}.md", count)
        job = self.base / name
        run_cli(
            "reference-pack", "create", "--brand", self.brand,
            "--input", str(material), "--job-dir", str(job), "--offline-fixture",
        )
        confirm_competitors(job)
        return job

    def test_01_version_identity_and_removed_foundation_cli(self) -> None:
        self.assertEqual("4.11.0", CONTROLLER.RELEASE_VERSION)
        self.assertEqual("4.11", CONTROLLER.WORKFLOW_VERSION)
        self.assertEqual("4.1", CONTROLLER.REFERENCE_PACK_VERSION)
        help_text = run_cli("--help").stdout
        self.assertIn("reference-pack", help_text)
        self.assertIn("p0", help_text)
        self.assertNotIn("foundation", help_text.casefold())
        failed = run_cli("foundation", "validate", "/tmp/no-pack", expect=2)
        self.assertIn("invalid choice", failed.stderr)

    def test_01a_no_argument_startup_is_a_standard_four_choice_page(self) -> None:
        direct = json.loads(run_cli().stdout)
        explicit = json.loads(run_cli("start").stdout)
        self.assertEqual(explicit, direct)
        self.assertEqual("frontmind-startup/v1", direct["contract"])
        self.assertEqual("awaiting_workflow_task", direct["startup_type"])
        self.assertTrue(direct["requires_user_input"])
        self.assertTrue(direct["must_stop"])
        self.assertTrue(direct["no_job_created"])
        self.assertEqual(
            ["reference-pack", "reference-pack-refresh", "p0", "article"],
            [item["id"] for item in direct["available_choices"]],
        )
        hinted = json.loads(run_cli("start", "--brand", self.brand).stdout)
        self.assertEqual("startup_choice_required", hinted["status"])
        self.assertIn("只收到品牌名称", "\n".join(hinted["rules"]))

    def test_02_p0_and_article_always_start_at_reference_pack_route(self) -> None:
        for kind, extra in (
            ("p0", []),
            ("article", ["--question-id", "q000001", "--question", "示例问题"]),
        ):
            job = self.base / f"route-{kind}"
            run_cli(
                kind, "--reference-pack", str(self.p0_pack), "--job-dir", str(job),
                *extra, "--offline-fixture",
            )
            current = state(job)
            self.assertEqual("awaiting_reference_pack_route", current["status"])
            self.assertTrue(current["current_pause"]["requires_user_input"])
            self.assertIn("创建新的 Reference Pack", page(job))

    def test_03_empty_continue_has_no_side_effect(self) -> None:
        job = self.start_article("empty-continue", self.manifest["cases"][0])
        before_state = (job / "job_state.json").read_bytes()
        before_page = page(job)
        replay = run_cli("continue", "--job-dir", str(job))
        self.assertEqual(before_state, (job / "job_state.json").read_bytes())
        self.assertIn(before_page.strip(), replay.stdout)

    def test_04_direct_create_confirms_competitors_then_positioning(self) -> None:
        first = state(self.rp_job)
        self.assertEqual("positioning_ready", first["status"])
        self.assertFalse((self.rp_job / "reviews/awaiting_core_positioning_direction.r1.md").exists())
        self.assertTrue((self.rp_job / "reviews/awaiting_competitor_selection.r1.md").is_file())
        self.assertTrue((self.rp_job / "reviews/awaiting_core_positioning_confirmation.r2.md").is_file())
        self.assertFalse((self.rp_job / "reviews/awaiting_reference_pack_route.r1.md").exists())
        decision = json.loads((self.rp_job / "decisions/positioning_direction_decision.json").read_text())
        self.assertEqual("single_clear", decision["decision_source"])
        self.assertEqual("direction_1", decision["primary"])
        self.assertIsNone(decision["secondary"])

    def test_05_final_projection_has_only_supported_fields(self) -> None:
        value = json.loads((self.rp_job / "positioning/core_positioning_directions.json").read_text())
        self.assertEqual("single_clear", value["routing"])
        self.assertEqual(1, len(value["directions"]))
        item = value["directions"][0]
        self.assertIn("advantage_explanation", item)
        self.assertNotIn("decisive_consequence_chain", item)
        self.assertNotIn("strategic_tradeoffs", item)
        self.assertEqual([], schema_errors(self.rp_job / "positioning/core_positioning_directions.json", ROOT / "shared/core_positioning_directions.schema.json"))

    def test_06_lightweight_core_has_no_manufactured_ranking(self) -> None:
        core = json.loads((self.rp_job / "positioning/core_positioning.json").read_text())
        self.assertIn(self.brand, core["core_positioning_paragraph"])
        self.assertIn("advantage_explanation", core)
        for key in ("market_tiers", "brand_placement", "decisive_consequence_chain", "operating_commitments"):
            self.assertNotIn(key, core)
        self.assertEqual([], schema_errors(self.rp_job / "positioning/core_positioning.json", ROOT / "shared/core_positioning.schema.json"))

    def test_07_user_edit_reenters_value_synthesis(self) -> None:
        job = self.start_direction_job("positioning-edit", 1)
        edit = "把企业输给公立医院的条件写得更清楚"
        resume(job, "--core-positioning-edits", edit)
        self.assertEqual("awaiting_core_positioning_confirmation", state(job)["status"])
        self.assertIn(edit, page(job))

    def test_07a_positioning_runs_two_internal_actions_with_scope_confirmation(self) -> None:
        actions = (
            "positioning_market_research", "positioning_value_synthesis",
        )
        for action in actions:
            root = self.rp_job / "provider" / action
            for member in ("prompt.md", "request.json", "result.json"):
                self.assertTrue((root / member).is_file(), f"{action}/{member}")
        self.assertFalse(any("critique" in path.name for path in (self.rp_job / "reviews").glob("*.md")))
        self.assertFalse((self.rp_job / "positioning/positioning_direction_review.json").exists())
        self.assertFalse((self.rp_job / "positioning/core_positioning_review.json").exists())

    def test_07b_production_positioning_has_no_obsolete_short_field(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in PRODUCTION_POSITIONING_FILES)
        for field in SHORT_POSITIONING_FIELDS:
            self.assertNotIn(field, combined)

    def test_07c_positioning_projection_contains_natural_material_only(self) -> None:
        context = (self.rp_job / "inputs/reference_context.md").read_text(encoding="utf-8")
        self.assertIn("高代价场景", context)
        self.assertIn("替代路径响应", context)
        for token in ("manifest", "sha256", "source_hash", "source_id", "registry"):
            self.assertNotIn(token.casefold(), context.casefold())

    def test_07d_materials_reach_provider_without_cross_case_leakage(self) -> None:
        cases = {"b2b_software.md": "订单状态中断", "manufacturing.md": "产线停工", "education.md": "频繁更换老师", "professional_service.md": "历史数据口径"}
        for filename, marker in cases.items():
            job = self.base / f"cross-{Path(filename).stem}"
            run_cli("reference-pack", "create", "--brand", f"匿名{Path(filename).stem}企业", "--input", str(CROSS_INDUSTRY_FIXTURE / filename), "--job-dir", str(job), "--offline-fixture")
            context = (job / "inputs/reference_context.md").read_text()
            self.assertIn(marker, context)
            for other in set(cases.values()) - {marker}:
                self.assertNotIn(other, context)

    def test_07e_no_rank_is_normal_confirmation(self) -> None:
        job = self.start_direction_job("no-forced-rank", 0)
        self.assertEqual("awaiting_core_positioning_confirmation", state(job)["status"])
        self.assertFalse(state(job)["metadata"].get("positioning_needs_input"))
        self.assertNotIn("## 市场竞争分档", page(job))

    def test_07f_core_edits_and_supplement_return_to_final_confirmation(self) -> None:
        job = self.start_direction_job("core-revision-loop", 1)
        self.assertEqual("awaiting_core_positioning_confirmation", state(job)["status"])
        initial_revision = state(job)["revision"]
        original_scope = state(job)["decisions"]["comparison_scope"]
        resume(job, "--core-positioning-edits", "把企业需要放弃的低价竞争写得更清楚")
        current = state(job)
        self.assertEqual("awaiting_core_positioning_confirmation", current["status"])
        self.assertEqual(initial_revision + 1, current["revision"])
        self.assertEqual(original_scope, current["decisions"]["comparison_scope"])
        self.assertIn("把企业需要放弃的低价竞争写得更清楚", page(job))
        stale_revision = current["revision"]
        resume(job, "--positioning-supplement", "高代价场景：跨环节任务临时发生重大变化")
        current = state(job)
        self.assertEqual("awaiting_core_positioning_confirmation", current["status"])
        self.assertEqual(stale_revision + 1, current["revision"])
        refreshed_scope = current["decisions"]["comparison_scope"]
        # Supplement research may refresh notes and sources, but not the user's selection.
        for key in ("brand_category", "mode", "scope_statement", "confirmed", "revision"):
            self.assertEqual(original_scope[key], refreshed_scope[key], key)
        for role in ("comparison_targets", "peer_examples"):
            def identities(scope: dict) -> list[dict]:
                return [{key: item[key] for key in ("id", "name", "category", "kind")}
                        for item in scope[role]]
            self.assertEqual(identities(original_scope), identities(refreshed_scope), role)
        stored_core = json.loads((job / "positioning/core_positioning.json").read_text())
        self.assertEqual(refreshed_scope, stored_core["comparison_scope"])
        self.assertIn("跨环节任务临时发生重大变化", page(job))
        failed = resume(job, "--confirm-core-positioning", revision=stale_revision, expect=2)
        self.assertIn(f"当前 revision={current['revision']}", failed.stderr)

    def test_07g_explore_alternatives_returns_to_competitor_confirmation(self) -> None:
        job = self.start_direction_job("explore-alternatives", 1)
        before = (job / "provider/positioning_market_research/prompt.md").read_text()
        self.assertIn("是否重新探索其他经营位置：否", before)
        previous_revision = state(job)["revision"]
        resume(job, "--explore-positioning-alternatives")
        current = state(job)
        self.assertEqual("awaiting_competitor_selection", current["status"])
        self.assertEqual(previous_revision + 1, current["revision"])
        self.assertFalse(current["decisions"].get("comparison_scope", {}).get("confirmed"))
        prompt = (job / "provider/positioning_market_research/prompt.md").read_text()
        self.assertNotEqual(before, prompt)
        self.assertIn("是否重新探索其他经营位置：是", prompt)
        confirm_competitors(job)
        self.assertEqual(current["revision"] + 1, state(job)["revision"])

    def test_08_positioning_confirmation_exports_v1_and_ends(self) -> None:
        current = state(self.rp_job)
        self.assertEqual("positioning_ready", current["status"])
        confirmation = json.loads((self.rp_job / "decisions/core_positioning_confirmation.json").read_text())
        self.assertEqual(current["revision"], confirmation["positioning_revision"])
        self.assertEqual(current["decisions"]["comparison_scope"], confirmation["comparison_scope"])
        root = json.loads((self.positioning_pack / "reference_pack.json").read_text())
        self.assertEqual(1, root["pack_version"])
        self.assertTrue(root["readiness"]["positioning_ready"])
        self.assertFalse(root["readiness"]["p0_ready"])
        self.assertFalse((self.rp_job / "deliverables/p0.md").exists())

    def test_09_positioning_pack_contains_research_and_strategy(self) -> None:
        required = [
            "research/brand_market/positioning_research_review.md",
            "research/brand_market/competitive_choice_map.json",
            "research/brand_market/competitive_choice_map.md",
            "research/brand_market/competitor_landscape.md",
            "strategy/positioning_directions.json",
            "strategy/core_positioning.md",
            "strategy/core_positioning.json",
            "strategy/core_positioning_confirmation.json",
        ]
        for member in required:
            self.assertTrue((self.positioning_pack / member).is_file(), member)
        self.assertFalse((self.positioning_pack / "foundation").exists())

    def test_10_p0_is_independent_and_writes_same_pack_series_v2(self) -> None:
        current = state(self.p0_job)
        self.assertEqual("p0_ready", current["status"])
        one = json.loads((self.positioning_pack / "reference_pack.json").read_text())
        two = json.loads((self.p0_pack / "reference_pack.json").read_text())
        self.assertEqual(one["pack_id"], two["pack_id"])
        self.assertEqual(2, two["pack_version"])
        self.assertEqual(1, two["parent_pack_version"])
        self.assertTrue(two["readiness"]["positioning_ready"])
        self.assertTrue(two["readiness"]["p0_ready"])
        for member in ("p0_brand_article.md", "p0.html", "p0.docx", "p0_title_map.json", "p0_record.json"):
            self.assertTrue((self.p0_pack / "p0" / member).is_file())
        self.assertEqual([], schema_errors(
            self.p0_pack / "p0/p0_record.json", ROOT / "shared/p0_record.schema.json",
        ))
        font_audit = audit_docx_embedded_fonts(self.p0_pack / "p0/p0.docx")
        self.assertTrue(font_audit["passed"], font_audit["issues"])
        self.assertFalse(font_audit["external_font_dependency"])

    def test_11_article_rejects_positioning_only_pack_before_e1(self) -> None:
        job = self.base / "positioning-only-article"
        run_cli(
            "article", "--reference-pack", str(self.positioning_pack),
            "--job-dir", str(job), "--question-id", "q000001",
            "--question", "本地机构推荐有哪些？", "--offline-fixture",
        )
        resume(job, "--reference-pack-route", "use")
        self.assertEqual("awaiting_reference_pack_input", state(job)["status"])
        self.assertIn("先运行 ./scripts/frontmind p0", page(job))
        self.assertFalse((job / "reviews/awaiting_response_brief.r2.md").exists())

    def test_12_missing_question_answers_uses_existing_input_pause(self) -> None:
        job = self.start_article("missing-question", self.manifest["cases"][0], answers=False)
        resume(job, "--reference-pack-route", "use")
        self.assertEqual("awaiting_question_research_inputs", state(job)["status"])
        text = page(job)
        self.assertIn("P0 与核心定位仍然有效", text)
        self.assertNotIn("Foundation", text)

    def test_13_loose_answers_create_v3_and_enter_real_e1_pause(self) -> None:
        job = self.start_article("article-e1", self.manifest["cases"][0])
        resume(job, "--reference-pack-route", "use")
        current = state(job)
        self.assertEqual("awaiting_response_brief", current["status"])
        self.assertEqual(3, current["reference_pack"]["pack_version"])
        self.assertEqual(
            json.loads((self.p0_pack / "reference_pack.json").read_text())["pack_id"],
            current["reference_pack"]["pack_id"],
        )
        text = page(job)
        for token in ("Reference Pack ID", "Reference Pack 版本", "核心定位修订", "P0 修订"):
            self.assertIn(token, text)

    def test_14_e1_cannot_be_skipped_or_partially_filled(self) -> None:
        job = self.start_article("e1-required", self.manifest["cases"][0])
        resume(job, "--reference-pack-route", "use")
        before = (job / "job_state.json").read_bytes()
        run_cli("continue", "--job-dir", str(job))
        self.assertEqual(before, (job / "job_state.json").read_bytes())
        failed = resume(job, "--no-extra-response-requirements", expect=2)
        self.assertIn("必须由用户选择 AI 品牌认知", failed.stderr)
        self.assertEqual("awaiting_response_brief", state(job)["status"])

    def test_15_pattern_page_shows_p00_through_p06(self) -> None:
        job = self.start_article("pattern-table", self.manifest["cases"][0])
        self.advance_to_pattern(job)
        text = page(job)
        for pattern in ("P00", "P01", "P02", "P03", "P04", "P05", "P06"):
            self.assertIn(pattern, text)
        self.assertIn("不可选", text)
        self.assertIn("推荐", text)

    def test_16_example_pause_links_two_examples_and_two_answers(self) -> None:
        job = self.start_article("example-links", self.manifest["cases"][0])
        self.advance_to_pattern(job)
        resume(job, "--pattern", "P02")
        current = state(job)
        self.assertEqual("awaiting_example_confirmation", current["status"])
        self.assertEqual(4, len(current["current_pause"]["full_text_links"]))
        text = page(job)
        self.assertIn("方案 A", text)
        self.assertIn("方案 B", text)
        self.assertIn("AI 答案一", text)
        self.assertIn("AI 答案二", text)

    def test_17_p02_question_positioning_is_natural_market_analysis(self) -> None:
        case = self.manifest["cases"][2]
        job = self.start_article("p02-positioning", case)
        self.advance_to_pattern(job)
        resume(job, "--pattern", "P02")
        resume(job, "--example-route", "A")
        self.assertEqual("awaiting_question_positioning_confirmation", state(job)["status"])
        text = page(job)
        for token in ("本题需求", "替代选择", "其他路径", "并列说明"):
            self.assertIn(token, text)
        for token in CONTROLLER.PUBLIC_FORBIDDEN_TOKENS:
            self.assertNotIn(token.casefold(), text.casefold())

    def test_18_p03_to_p06_skip_question_positioning(self) -> None:
        case = self.manifest["cases"][1]
        job = self.start_article("p06-no-positioning", case)
        self.advance_to_pattern(job)
        resume(job, "--pattern", "P06")
        resume(job, "--example-route", "A")
        self.assertEqual("awaiting_blueprint_confirmation", state(job)["status"])
        self.assertFalse((job / "question_positioning/question_positioning.json").exists())

    def test_19_edits_return_to_same_business_pause_with_new_revision(self) -> None:
        case = self.manifest["cases"][2]
        job = self.start_article("qpos-edits", case)
        self.advance_to_pattern(job)
        resume(job, "--pattern", "P02")
        resume(job, "--example-route", "A")
        previous_revision = state(job)["revision"]
        resume(job, "--question-positioning-edits", "让每一档的取舍更清楚")
        current = state(job)
        self.assertEqual("awaiting_question_positioning_confirmation", current["status"])
        self.assertEqual(previous_revision + 1, current["revision"])
        self.assertIn("让每一档的取舍更清楚", page(job))

    def test_20_stale_revision_cannot_confirm_new_content(self) -> None:
        case = self.manifest["cases"][2]
        job = self.start_article("stale-revision", case)
        self.advance_to_pattern(job)
        resume(job, "--pattern", "P02")
        resume(job, "--example-route", "A")
        stale_revision = state(job)["revision"]
        resume(job, "--question-positioning-edits", "修改当前表述")
        current = state(job)
        failed = resume(job, "--confirm-question-positioning", revision=stale_revision, expect=2)
        self.assertIn(f"当前 revision={current['revision']}", failed.stderr)
        self.assertEqual("awaiting_question_positioning_confirmation", state(job)["status"])

    def test_21_schema_contracts_validate_real_outputs(self) -> None:
        self.assertEqual([], schema_errors(
            self.positioning_pack / "reference_pack.json", ROOT / "shared/reference_pack.schema.json",
        ))
        self.assertEqual([], schema_errors(
            self.p0_job / "00_input/reference_pack_binding.json",
            ROOT / "shared/reference_pack_binding.schema.json",
        ))
        self.assertEqual([], schema_errors(
            self.p0_job / "job_state.json", ROOT / "shared/job_state.schema.json",
        ))

    def test_22_add_materials_reopens_positioning_and_preserves_question_research(self) -> None:
        case = self.manifest["cases"][0]
        job = self.start_article("pack-with-question", case)
        resume(job, "--reference-pack-route", "use")
        source = Path(state(job)["reference_pack"]["path"])
        source_root = json.loads((source / "reference_pack.json").read_text())
        material = self.base / "new-brand-material.md"
        material.write_text("新增的普通品牌事实，需要重新确认定位。\n", encoding="utf-8")
        output = self.base / "Reference_Pack_material_update"
        result = BUILDER.add_materials(pack=source, materials=[material], output=output)
        updated = json.loads((output / "reference_pack.json").read_text())
        self.assertEqual(source_root["pack_id"], updated["pack_id"])
        self.assertFalse(updated["readiness"]["positioning_ready"])
        self.assertFalse(updated["readiness"]["p0_ready"])
        self.assertEqual(source_root["readiness"]["question_ready"], updated["readiness"]["question_ready"])
        self.assertTrue((output / "research/question_research/index.json").is_file())
        self.assertFalse((output / "strategy/core_positioning.md").exists())
        self.assertEqual(1, result["material_count_added"])

    def test_23_version_commit_rolls_back_directory_when_zip_build_fails(self) -> None:
        output = self.base / "failed-version"
        before = sha256(self.positioning_pack / "reference_pack.json")
        with mock.patch.object(BUILDER, "write_portable_zip", side_effect=OSError("injected ZIP failure")):
            with self.assertRaises(OSError):
                BUILDER.create_next_reference_pack_version(
                    pack=self.positioning_pack, output=output,
                    readiness_updates={"p0_ready": False},
                )
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".zip").exists())
        self.assertEqual(before, sha256(self.positioning_pack / "reference_pack.json"))

    def test_24_pack_38_is_rejected_with_rebuild_instruction(self) -> None:
        old = self.base / "old-pack"
        old.mkdir()
        (old / "reference_pack.json").write_text(
            json.dumps({"schema_version": "3.8", "profile": "frontmind-content-reference-pack"}),
            encoding="utf-8",
        )
        result = run_cli("reference-pack", "validate", str(old), expect=1)
        self.assertIn("重新构建", result.stdout)
        self.assertIn("4.1", result.stdout)

    def test_24a_pack_40_refresh_preserves_inputs_and_rebuilds_positioning(self) -> None:
        root = self.base / "pack-40-upgrade"
        root.mkdir()
        base_pack = root / "Reference_Pack_v1"
        BUILDER.create_reference_pack(
            brand_name="旧版匿名企业",
            knowledge_base=[CROSS_INDUSTRY_FIXTURE / "manufacturing.md"],
            output=base_pack,
        )
        monitor = root / "monitor.json"
        monitor.write_text(json.dumps({
            "question": "旧问题",
            "captured_at": "2026-09-03",
            "answers": [
                {"platform": "平台甲", "answer_text": "第一篇完整回答。"},
                {"platform": "平台乙", "answer_text": "第二篇完整回答。"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "详细表格"
        sheet.append(["引用日期", "监控问题", "内容标题", "内容链接", "媒体名称"])
        workbook.save(root / "citations.xlsx")
        old = root / "Reference_Pack_v7"
        BUILDER.update_research(
            pack=base_pack, monitoring_answers=monitor,
            source_workbook=root / "citations.xlsx", questions=["旧问题"], output=old,
        )
        old_root = json.loads((old / "reference_pack.json").read_text())
        old_root["schema_version"] = "4.0"
        old_root["pack_version"] = 7
        old_root["parent_pack_version"] = 6
        old_root["readiness"].update({
            "brand_market_research_ready": True,
            "positioning_ready": True,
            "p0_ready": True,
        })
        (old / "reference_pack.json").write_text(
            json.dumps(old_root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        (old / "strategy").mkdir(exist_ok=True)
        (old / "strategy/core_positioning.md").write_text("旧定位，不得沿用。\n", encoding="utf-8")
        (old / "p0").mkdir(exist_ok=True)
        (old / "p0/p0_brand_article.md").write_text("旧 P0，不得沿用。\n", encoding="utf-8")

        job = root / "refresh-job"
        run_cli(
            "reference-pack", "refresh-market", "--pack", str(old),
            "--job-dir", str(job), "--offline-fixture",
        )
        self.assertEqual("awaiting_competitor_selection", state(job)["status"])
        self.assertTrue(state(job)["metadata"]["upgraded_from_reference_pack_4_0"])
        staged = job / "working/reference_pack_4_1_refresh_base"
        staged_root = json.loads((staged / "reference_pack.json").read_text())
        self.assertEqual("4.1", staged_root["schema_version"])
        self.assertEqual(7, staged_root["pack_version"])
        self.assertTrue(staged_root["readiness"]["question_ready"]["q000001"])
        self.assertTrue((staged / "research/question_research/index.json").is_file())
        self.assertFalse((staged / "strategy/core_positioning.md").exists())
        self.assertFalse((staged / "p0/p0_brand_article.md").exists())

        confirm_competitors(job)
        resume(job, "--confirm-core-positioning")
        upgraded = job / "deliverables/Reference_Pack_v8"
        value = json.loads((upgraded / "reference_pack.json").read_text())
        self.assertEqual("4.1", value["schema_version"])
        self.assertEqual(8, value["pack_version"])
        self.assertTrue(value["readiness"]["positioning_ready"])
        self.assertFalse(value["readiness"]["p0_ready"])
        self.assertTrue(value["readiness"]["question_ready"]["q000001"])

    def test_25_zip_has_no_legacy_byte_ceilings(self) -> None:
        archive = self.base / "sparse-large.zip"
        write_sparse_zip(archive, 513 * 1024 * 1024)
        infos = CONTROLLER.inspect_zip(archive)
        self.assertEqual(1, len(infos))
        self.assertGreater(archive.stat().st_size, 512 * 1024 * 1024)
        self.assertGreater(infos[0].file_size, 512 * 1024 * 1024)

    def test_26_zip_rejects_nested_traversal_duplicate_symlink_and_ratio(self) -> None:
        cases: list[tuple[str, callable, str]] = []

        def nested(path: Path) -> None:
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("inner.zip", b"PK\x05\x06" + b"\0" * 18)

        def traversal(path: Path) -> None:
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escape.txt", "x")

        def duplicate(path: Path) -> None:
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("A.txt", "one")
                archive.writestr("a.txt", "two")

        def symlink(path: Path) -> None:
            with zipfile.ZipFile(path, "w") as archive:
                info = zipfile.ZipInfo("link")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "target")

        def ratio(path: Path) -> None:
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("bomb.txt", b"0" * (2 * 1024 * 1024))

        cases.extend([
            ("nested", nested, "嵌套 ZIP"), ("traversal", traversal, "不安全路径"),
            ("duplicate", duplicate, "重复规范化路径"), ("symlink", symlink, "符号链接"),
            ("ratio", ratio, "压缩比超过 200"),
        ])
        for name, writer, message in cases:
            with self.subTest(name=name):
                path = self.base / f"unsafe-{name}.zip"
                writer(path)
                with self.assertRaisesRegex(CONTROLLER.WorkflowError, message):
                    CONTROLLER.inspect_zip(path)

    def test_27_zip_rejects_5001_members_encryption_and_special_files(self) -> None:
        too_many = self.base / "unsafe-too-many.zip"
        with zipfile.ZipFile(too_many, "w", compression=zipfile.ZIP_STORED) as archive:
            for index in range(5001):
                archive.writestr(f"items/{index:04d}.txt", b"")
        with self.assertRaisesRegex(CONTROLLER.WorkflowError, "超过 5,000"):
            CONTROLLER.inspect_zip(too_many)

        special = self.base / "unsafe-special.zip"
        with zipfile.ZipFile(special, "w") as archive:
            info = zipfile.ZipInfo("pipe")
            info.create_system = 3
            info.external_attr = (stat.S_IFIFO | 0o644) << 16
            archive.writestr(info, b"")
        with self.assertRaisesRegex(CONTROLLER.WorkflowError, "特殊文件"):
            CONTROLLER.inspect_zip(special)

        encrypted = self.base / "unsafe-encrypted.zip"
        with zipfile.ZipFile(encrypted, "w") as archive:
            archive.writestr("secret.txt", "content")
        raw = bytearray(encrypted.read_bytes())
        local = raw.find(b"PK\x03\x04")
        central = raw.find(b"PK\x01\x02")
        self.assertGreaterEqual(local, 0)
        self.assertGreaterEqual(central, 0)
        struct.pack_into("<H", raw, local + 6, struct.unpack_from("<H", raw, local + 6)[0] | 1)
        struct.pack_into("<H", raw, central + 8, struct.unpack_from("<H", raw, central + 8)[0] | 1)
        encrypted.write_bytes(raw)
        with self.assertRaisesRegex(CONTROLLER.WorkflowError, "加密成员"):
            CONTROLLER.inspect_zip(encrypted)

    def test_28_update_research_is_immutable_and_question_ready_without_citation_count_gate(self) -> None:
        root = self.base / "research-update"
        root.mkdir()
        material = root / "material.md"
        material.write_text("匿名示例企业提供专业服务。\n", encoding="utf-8")
        created = BUILDER.create_reference_pack(
            brand_name="匿名示例企业", knowledge_base=[material], output=root / "Reference_Pack_v1",
        )
        question = "匿名示例企业怎么选？"
        monitor = root / "monitor.json"
        monitor.write_text(json.dumps({
            "question": question, "captured_at": "2026-09-03",
            "answers": [
                {"platform": "平台甲", "answer_text": "平台甲完整回答。"},
                {"platform": "平台乙", "answer_text": "平台乙完整回答。"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "详细表格"
        sheet.append(["引用日期", "监控问题", "内容标题", "内容链接", "媒体名称"])
        workbook.save(root / "citations.xlsx")
        before = sha256(root / "Reference_Pack_v1/reference_pack.json")
        updated = BUILDER.update_research(
            pack=root / "Reference_Pack_v1", monitoring_answers=monitor,
            source_workbook=root / "citations.xlsx", questions=[question],
            output=root / "Reference_Pack_v2",
        )
        self.assertEqual(created["pack_id"], updated["pack_id"])
        self.assertEqual(2, updated["pack_version"])
        self.assertTrue(updated["readiness"]["question_ready"]["q000001"])
        self.assertEqual(before, sha256(root / "Reference_Pack_v1/reference_pack.json"))
        self.assertFalse((root / "Reference_Pack_v2/workspace_data").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
