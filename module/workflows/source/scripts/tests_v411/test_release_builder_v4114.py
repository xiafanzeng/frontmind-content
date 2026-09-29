"""Package checks must not fabricate model, prose or document acceptance."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

SPEC = importlib.util.spec_from_file_location("frontmind_release_builder", Path(__file__).resolve().parents[1] / "build_release.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ReleaseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.put("scripts/frontmind", "#!/bin/sh\nexit 0\n", 0o755)
        self.put("config/deepseek.json", json.dumps({"api_key": "synthetic-deepseek-key-0123456789"}), 0o600)
        self.put("config/zhipu.json", json.dumps({"api_key": "synthetic-auxiliary-key-0123456789"}), 0o600)
        self.put("config/xty.json", json.dumps({"api_key": "synthetic-xty-key-0123456789"}), 0o600)
        self.files = {"scripts/frontmind", "config/zhipu.json", "config/deepseek.json", "config/xty.json"}

    def put(self, relative, content, mode=0o644):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(mode)
        return path

    def test_permissions_preserved_in_zip_and_extraction(self):
        path = self.root / "release.zip"
        builder.audit_projection(self.source, self.files)
        builder.write_zip(self.source, path)
        report = builder.inspect_release_zip(path)
        self.assertEqual(report["credential_modes"]["config/deepseek.json"], "0600")
        extracted = builder.extract_zip(path, self.root / "extract")
        builder.audit_projection(extracted, self.files)
        for relative in builder.CREDENTIAL_FILES:
            self.assertEqual(stat.S_IMODE((extracted / relative).stat().st_mode), 0o600)
        self.assertEqual(builder.verify_file_hashes(self.source, extracted, self.files)["status"], "pass")

    def test_readable_credential_permissions_rejected(self):
        (self.source / "config/zhipu.json").chmod(0o644)
        with self.assertRaises(builder.ReleaseError):
            builder.audit_projection(self.source, self.files)

    def test_credential_outside_configuration_rejected_without_disclosure(self):
        self.put("README.md", "accidental synthetic-auxiliary-key-0123456789")
        with self.assertRaises(builder.ReleaseError) as error:
            builder.audit_projection(self.source, self.files | {"README.md"})
        self.assertNotIn("synthetic-host-key", str(error.exception))

    def test_original_web_fragment_is_not_a_workstation_path(self):
        source = 'linkurl="https://example.com/?q=1#/' + 'home/index"'
        source += '$.post("/' + 'home/search", {keywords: query});'
        path = self.put("original.html", source)
        builder.audit_projection(self.source, self.files | {"original.html"})
        self.assertEqual(path.read_text(), source)
        private_paths = ("/" + "home/alice/private", "/" + "Users/alice/private", "file:///" + "home/alice/private")
        for private in private_paths:
            path.write_text(source + private)
            with self.subTest(private=private), self.assertRaises(builder.ReleaseError):
                builder.audit_projection(self.source, self.files | {"original.html"})

    def test_zip_permission_tampering_is_rejected_before_extraction(self):
        path = self.root / "tampered.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for relative in self.files:
                info = zipfile.ZipInfo(f"{builder.RELEASE_ROOT_NAME}/{relative}")
                info.external_attr = (stat.S_IFREG | (0o755 if relative == "scripts/frontmind" else 0o644)) << 16
                archive.writestr(info, (self.source / relative).read_bytes())
        with self.assertRaises(builder.ReleaseError):
            builder.extract_zip(path, self.root / "unsafe")
        self.assertFalse((self.root / "unsafe").exists())

    def test_file_hash_change_is_rejected(self):
        self.put("test.md", "one")
        with mock.patch.object(builder, "RELEASE_FILES", self.files | {"test.md"}), mock.patch.object(builder, "RELEASE_TREE_ROOTS", ()):
            copied = builder.copy_projection(self.source, self.root / "copy")
        (self.root / "copy/test.md").write_text("two")
        with self.assertRaises(builder.ReleaseError):
            builder.verify_file_hashes(self.source, self.root / "copy", copied)

    def test_packaged_runtime_preserves_configured_effort_including_repair(self):
        # Run the packaged check against isolated profiles: both preserved
        # effort settings are valid, but retries or a repair drift are not.
        for index, (retries, effort, repair_effort, valid) in enumerate((
            (0, "max", "max", True), (0, "high", "high", True),
            (1, "max", "max", False), (0, "high", "max", False),
        )):
            package = self.root / f"runtime_{index}"
            shared = package / "shared"
            shared.mkdir(parents=True)
            (shared / "__init__.py").write_text("")
            (shared / "model_runtime.py").write_text(
                "HOST_ACTIONS = {'article_finalize', 'article_polish', 'article_editorial_preparation'} | {f'host_{i}' for i in range(10)}\n"
                "DEEPSEEK_ACTIONS = {'article_draft', 'article_repair', 'p0_repair'} | {f'writer_{i}' for i in range(6)}\n"
                "def profile_for(action):\n"
                "    host = action in HOST_ACTIONS\n"
                f"    effort = {repair_effort!r} if action.endswith('_repair') else {effort!r}\n"
                "    return {'model': 'gpt-4o' if host else 'deepseek-v4-pro', "
                f"**({{'provider':'xty','wire_api':'openai_agents_sdk','automatic_retries':{retries},'tracing_disabled':True}} if host else {{'reasoning_effort':effort,'thinking':{{'type':'enabled'}}}})}}\n"
                "def configuration_status(root):\n"
                "    return {'xty': {'configured': True}, 'deepseek': {'configured': True}}\n"
            )
            with self.subTest(retries=retries, effort=effort, repair_effort=repair_effort):
                if valid:
                    result = builder.validate_model_runtime(package, sys.executable)
                    self.assertEqual(result["status"], "pass")
                    self.assertEqual(result["deepseek_action_count"], 9)
                    self.assertFalse(result["paid_api_called"])
                else:
                    with self.assertRaises(builder.ReleaseError):
                        builder.validate_model_runtime(package, sys.executable)

    def build_minimal(self, *, candidate=False, validation_report=None):
        source_result = {"preflight": {"status": "pass"}, "validation": {"status": "pass", "tests": {"status": "pass", "test_count": 7}}}
        clean_result = {"preflight": {"status": "pass"}, "validation": {"status": "pass"},
                        "runtime": {"status": "pass", "host_action_count": 11, "deepseek_action_count": 7, "paid_api_called": False}, "tests_repeated": False}
        with mock.patch.object(builder, "RELEASE_FILES", self.files), mock.patch.object(builder, "RELEASE_TREE_ROOTS", ()), \
             mock.patch.object(builder, "ROOT_DOCUMENTS", ()), mock.patch.object(builder, "choose_python", return_value="python3"), \
             mock.patch.object(builder, "validate_source", return_value=source_result), mock.patch.object(builder, "run_json", return_value={"status": "pass"}), \
             mock.patch.object(builder, "validate_clean_extraction", return_value=clean_result), mock.patch.object(builder, "validate_acceptance") as legacy:
            report = builder.build(self.source, output_dir=self.root / "output", candidate=candidate, validation_report=validation_report)
            legacy.assert_not_called()
        return report

    def test_default_build_does_not_require_old_fixture_or_claim_content_pass(self):
        report = self.build_minimal()
        self.assertEqual(report["acceptance"]["status"], "not_requested")
        self.assertEqual(report["validation_scope"], "program_and_package_only")
        self.assertEqual(report["content_acceptance"], "not_assessed_by_builder")
        text = (self.root / "output" / builder.REPORT_NAME).read_text()
        self.assertIn("不表示业务文章", text)
        self.assertNotIn("八份 DOCX 渲染与逐页检查：`pass`", text)
        self.assertNotIn("本次真实 glm-5.3 集中表达修订", text)

    def test_candidate_uses_candidate_filename_and_keeps_checks(self):
        report = self.build_minimal(candidate=True)
        self.assertEqual(report["zip_filename"], builder.CANDIDATE_ZIP_NAME)
        self.assertTrue((self.root / "output" / builder.CANDIDATE_ZIP_NAME).is_file())
        self.assertFalse((self.root / "output" / builder.FINAL_ZIP_NAME).exists())
        self.assertIn("候选程序包，内容尚未验收", (self.root / "output" / builder.REPORT_NAME).read_text())

    def test_external_report_is_byte_identical_and_not_a_quality_pass(self):
        external = self.root / "quality.md"
        body = b"Content: pending\r\nModels: fail\r\n"
        external.write_bytes(body)
        report = self.build_minimal(validation_report=external)
        info = report["external_validation_report"]
        self.assertEqual((self.root / "output" / info["filename"]).read_bytes(), body)
        self.assertFalse(info["semantic_validation_by_builder"])
        self.assertEqual(report["content_acceptance"], "not_assessed_by_builder")
        with zipfile.ZipFile(self.root / "output" / report["zip_filename"]) as archive:
            self.assertFalse(any(info["filename"] in name for name in archive.namelist()))


if __name__ == "__main__":
    unittest.main()
