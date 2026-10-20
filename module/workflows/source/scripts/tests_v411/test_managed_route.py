"""Local routing and official event contract regressions; no provider requests."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import model_runtime as rt, managed_runtime as managed
from shared.example_acquisition import AcquisitionError
from shared.runtime_credentials import PROXY_BASE
from scripts import check_runtime_dependencies as preflight
from scripts.tests_v411.test_managed_runtime_v4123 import ManagedServer
from scripts.tests_v411.test_model_runtime import FakeTools, valid


class ManagedRouteTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"FRONTMIND_CONTENT_HOST_PROVIDER": "zhipu"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pkg = self.root / "package"
        self.job = self.root / "job"
        self.pkg.mkdir()
        self.job.mkdir()

    def test_explicit_managed_runs_existing_tool_loop(self):
        server = ManagedServer()
        tools = FakeTools()
        result = rt.run_action(self.pkg, self.job, "p0_blueprint", "unchanged request", valid,
                               host_tools=tools, transport=server, offline=True)
        self.assertEqual(result, {"ok": True})
        self.assertTrue(tools.read)
        self.assertEqual(rt.action_record(self.job, "p0_blueprint")["requested_configuration"]["provider"], "zhipu")
        count = len(server.calls)
        self.assertEqual(rt.run_action(self.pkg, self.job, "p0_blueprint", "unchanged request", valid,
                                      host_tools=FakeTools(), transport=server, offline=True), result)
        self.assertEqual(len(server.calls), count)

    def test_existing_attempt_cannot_silently_change_provider(self):
        rt.run_action(self.pkg, self.job, "p0_blueprint", "unchanged request", valid,
                      host_tools=FakeTools(), transport=ManagedServer(), offline=True)
        with patch.dict(os.environ, {"FRONTMIND_CONTENT_HOST_PROVIDER": "xty"}):
            with self.assertRaises(rt.ProviderActionError) as caught:
                rt.run_action(self.pkg, self.job, "p0_blueprint", "unchanged request", valid)
        self.assertEqual(caught.exception.code, "frozen_host_provider_mismatch")

    def test_invalid_provider_and_private_proxy_stop_before_any_network(self):
        with patch.dict(os.environ, {"FRONTMIND_CONTENT_HOST_PROVIDER": "unexpected"}):
            with self.assertRaises(rt.ProviderActionError) as caught:
                rt.profile_for("p0_blueprint")
            self.assertEqual(caught.exception.code, "invalid_host_provider")
        with patch.dict(os.environ, {"FRONTMIND_CONTENT_PROVIDER_PROXY": PROXY_BASE}), \
                patch.object(managed, "ManagedClient") as client, patch.object(rt, "load_configuration") as credentials:
            with self.assertRaises(rt.ProviderActionError) as caught:
                rt.run_action(self.pkg, self.job, "p0_blueprint", "request", valid)
            self.assertEqual(caught.exception.code, "managed_proxy_unsupported")
            client.assert_not_called()
            credentials.assert_not_called()

    def test_preflight_managed_needs_no_xty_or_agents_sdk(self):
        models = {name: {"configured": name != "xty"} for name in ("xty", "zhipu", "deepseek")}
        with patch.object(preflight, "configuration_status", return_value=models), \
                patch.object(preflight, "probe", return_value={"available": True}) as probe, \
                patch("builtins.print") as output:
            self.assertEqual(preflight.main(), 0)
        modules = [call.args[0] for call in probe.call_args_list]
        self.assertNotIn("agents", modules)
        self.assertNotIn("openai", modules)
        self.assertEqual(json.loads(output.call_args.args[0])["host_provider"], "zhipu")

    def test_contract_failure_keeps_actionable_detail_and_redacts_credentials(self):
        def reject(_):
            raise ValueError("source_ref is not registered; fixture-private-key")
        with patch.object(rt, "load_configuration", return_value={"api_key": "fixture-private-key", "source": "test"}):
            with self.assertRaises(rt.ProviderActionError) as caught:
                rt.run_action(self.pkg, self.job, "p0_blueprint", "unchanged request", reject,
                              host_tools=FakeTools(), transport=ManagedServer(), offline=True)
        self.assertEqual(caught.exception.code, "invalid_result_contract")
        self.assertIn("source_ref is not registered", str(caught.exception))
        self.assertNotIn("fixture-private-key", str(caught.exception))
        record = rt.action_record(self.job, "p0_blueprint")
        self.assertNotIn("fixture-private-key", json.dumps(record))

    def test_acquisition_failure_explains_shared_url_guard_without_retrying(self):
        server, tools = ManagedServer(), FakeTools()
        tools.read = True  # This fixture has no unread business materials.
        with patch.object(tools, "execute", side_effect=AcquisitionError("web URL resolves to a non-public address")) as execute:
            rt.run_action(self.pkg, self.job, "p0_blueprint", "request", valid,
                          host_tools=tools, transport=server, offline=True)
        execute.assert_called_once()
        output = next(e for e in server.events if e["type"] == "user.custom_tool_result")
        self.assertTrue(output["is_error"])
        result = json.loads(output["content"][0]["text"])
        self.assertEqual(result["error"], "non_public_address")
        self.assertIn("non-public address", result["message"])
        self.assertIn("HTTP and Reader share", result["message"])
        self.assertIn("Do not retry", result["message"])

    def test_acquisition_diagnostic_is_bounded_and_redacts_credentials(self):
        server, tools = ManagedServer(), FakeTools()
        tools.read = True
        with patch.object(rt, "load_configuration", return_value={"api_key": "fixture-private-key", "source": "test"}), \
                patch.object(tools, "execute", side_effect=AcquisitionError("incomplete: fixture-private-key " + "x" * 2000)):
            rt.run_action(self.pkg, self.job, "p0_blueprint", "request", valid,
                          host_tools=tools, transport=server, offline=True)
        output = next(e for e in server.events if e["type"] == "user.custom_tool_result")
        result = json.loads(output["content"][0]["text"])
        self.assertTrue(output["is_error"])
        self.assertNotIn("fixture-private-key", json.dumps(output))
        self.assertLessEqual(len(result["message"]), 1000)

    def test_history_merges_queued_event_and_keeps_nonempty_boundary(self):
        processed = {"id": "first", "type": "session.status_running", "processed_at": "2026-10-03T01:00:00Z"}
        queued = {"id": "queued", "type": "user.message", "content": [{"type": "text", "text": "task"}]}
        class Page:
            def __init__(self, data): self.data, self.path = data, None
            def request(self, method, path):
                self.path = path
                return {"data": self.data, "has_more": False}
        initial = managed.read_history(Page([processed, queued]), "session", [])
        page = Page([{**queued, "processed_at": "2026-10-03T01:00:01Z"}])
        result = managed.read_history(page, "session", initial)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["processed_at"], "2026-10-03T01:00:01Z")
        self.assertIn("created_at%5Bgte%5D=2026-10-03T01%3A00%3A00Z", page.path)
        result = managed.read_history(Page([{**queued, "processed_at": None}]), "session", result)
        self.assertEqual(result[1]["processed_at"], "2026-10-03T01:00:01Z")

    def test_launcher_reads_only_required_keys_without_copying_configuration(self):
        path = Path(__file__).resolve().parents[3] / "scripts" / "run_managed.py"
        spec = importlib.util.spec_from_file_location("run_managed", path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        for name in ("zhipu", "deepseek"):
            (self.root / (name + ".json")).write_text(json.dumps({"api_key": "fixture-" + name, "unused_secret": "never-inject"}))
        with patch.dict(os.environ, {}, clear=True), patch.object(launcher.os, "execve") as execute, patch.object(launcher.subprocess,"call",return_value=0) as call:
            self.assertEqual(launcher.main(["--config-dir", str(self.root), "--", "preflight"]), 0)
        if os.name == 'nt':
            execute.assert_not_called()
            arguments=call.call_args.args[0]
            environment=call.call_args.kwargs['env']
        else:
            call.assert_not_called()
            executable, arguments, environment = execute.call_args.args
        self.assertEqual(environment["FRONTMIND_CONTENT_ZHIPU_API_KEY"], "fixture-zhipu")
        self.assertEqual(environment["FRONTMIND_CONTENT_DEEPSEEK_API_KEY"], "fixture-deepseek")
        self.assertNotIn("never-inject", environment.values())
        self.assertEqual(arguments[-1], str(launcher.SOURCE / "scripts/check_runtime_dependencies.py"))


if __name__ == "__main__":
    unittest.main()

class DeterministicToolFailureTests(unittest.TestCase):
    def test_exact_error_codes_and_safe_recovery_guidance(self):
        from shared.host_tools import MaterialReferenceError, MaterialBoundaryError, ToolError
        for error, code in [(MaterialReferenceError('PRIVATE_PATH'),'material_reference_missing'),(MaterialBoundaryError('PRIVATE_PATH'),'material_boundary_rejected'),(ToolError('PRIVATE'),'invalid_tool_arguments')]:
            result=managed.tool_failure(error,[])
            self.assertEqual(result['error'],code)
            self.assertNotIn('PRIVATE',json.dumps(result))

    def test_method_and_offset_changes_cannot_repeat_same_deterministic_request(self):
        self.assertEqual(managed.deterministic_request_key('web_read',{'url':'https://example.com/a/','method':'http'}), managed.deterministic_request_key('web_read',{'url':'https://example.com/a#top','method':'reader'}))
        self.assertEqual(managed.deterministic_request_key('read_material',{'artifact_id':'wrong','offset':0}), managed.deterministic_request_key('read_material',{'artifact_id':'wrong','offset':200}))

    def test_repeated_model_request_stops_before_second_tool_execution(self):
        from shared.host_tools import MaterialReferenceError
        class RepeatServer(ManagedServer):
            def request(self, method, path, payload=None):
                result=super().request(method,path,payload)
                if method=='POST' and path.endswith('/events') and any(e['type']=='user.custom_tool_result' for e in (payload or {}).get('events',[])):
                    self.events=self.events[:-4]
                    self.tool('read_material',{'artifact_id':'one','offset':20})
                return result
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'FRONTMIND_CONTENT_HOST_PROVIDER':'zhipu'}):
            root=Path(folder);pkg=root/'pkg';pkg.mkdir();job=root/'job';job.mkdir();tools=FakeTools()
            with patch.object(tools,'execute',side_effect=MaterialReferenceError('wrong ref')) as execute:
                with self.assertRaises(rt.ProviderActionError) as caught:
                    rt.run_action(pkg,job,'p0_blueprint','request',valid,host_tools=tools,transport=RepeatServer(),offline=True)
                self.assertEqual(caught.exception.code,'deterministic_tool_repeat')
                execute.assert_called_once()
