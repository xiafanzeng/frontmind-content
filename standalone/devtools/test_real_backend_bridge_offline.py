# 依赖：Python 标准库，无需安装。仅离线测试，不启动 HTTP 服务，不读取网关凭据。
from __future__ import annotations

import copy
import importlib.util
import io
import json
import socket
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("bridge_under_test", HERE / "real_backend_bridge.py")
bridge_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge_module)


class FakeRemote:
    """只在内存中模拟保存/读回，绝不实例化真实 Remote。"""
    def __init__(self, mode="success"):
        self.mode, self.calls, self.rows = mode, [], {}

    def json(self, method, path, value=None):
        self.calls.append((method, path, copy.deepcopy(value)))
        if method == "GET" and path == "/api/content/conversations":
            if self.mode == "missing":
                return 200, []
            rows = copy.deepcopy(list(self.rows.values()))
            for row in rows:
                message = row["messages"][0]
                if self.mode.startswith("normalized"):
                    message["timestamp"] -= message["timestamp"] % 1000
                    for attachment in message.get("attachments", []):
                        attachment.update(expired=False, expiresAt="2026-11-23T00:00:00.000Z")
                if self.mode in {"changed_text", "normalized_changed_text"}:
                    message["content"] += "（错误改写）"
                elif self.mode in {"changed_attachment", "normalized_changed_attachment"}:
                    message["attachments"][0]["fileId"] = "asset_wrong"
                elif self.mode in {"changed_dispatch", "normalized_changed_dispatch"}:
                    message["generalChatDispatch"]["purpose"] = "enterprise_qa"
                elif self.mode == "unexpected_task":
                    row["taskId"] = "forbidden-task"
                elif self.mode == "normalized_expired":
                    message["attachments"][0]["expired"] = True
                elif self.mode == "normalized_timestamp_plus_1000":
                    message["timestamp"] = self.rows[row["id"]]["messages"][0]["timestamp"] + 1000
                elif self.mode == "normalized_timestamp_minus_1000":
                    message["timestamp"] = self.rows[row["id"]]["messages"][0]["timestamp"] - 1000
            return 200, rows
        if method == "PUT" and path.startswith("/api/content/conversations/"):
            self.rows[value["id"]] = copy.deepcopy(value)
            if self.mode == "unknown_put":
                raise bridge_module.BridgeError(502, "REMOTE_OUTCOME_UNCONFIRMED", "离线模拟：写入响应未知。")
            return 200, copy.deepcopy(value)
        raise AssertionError(f"离线测试遇到未预期调用：{method} {path}")

    @property
    def puts(self):
        return [call for call in self.calls if call[0] == "PUT"]


class BridgeOfflineTests(unittest.TestCase):
    def setUp(self):
        # 即使误写了测试客户端，也从 socket 层禁止一切真实连接。
        self.socket_guard = patch.object(socket.socket, "connect", side_effect=AssertionError("离线单测禁止真实网络连接"))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        self.temporary = tempfile.TemporaryDirectory(prefix="frontmind-bridge-offline-")
        self.addCleanup(self.temporary.cleanup)

    def fixture(self, mode="success", directory=None):
        remote = FakeRemote(mode)
        bridge = bridge_module.Bridge(remote, Path(directory or self.temporary.name))
        conversation_id = str(uuid.uuid4())
        snapshot = {"id": conversation_id, "title": "离线收件测试", "purpose": "content_production", "status": "idle", "messages": [], "createdAt": 1, "updatedAt": 1}
        bridge.create_conversation(conversation_id, snapshot, local_draft=True)
        subjects = {"schemaVersion": 1, "revision": 1, "folders": [{"id": "offline-subject", "name": "离线测试主体", "versions": []}], "bindings": {conversation_id: {"folderId": "offline-subject", "kind": "pack", "packVersionId": None, "generation": 0}}}
        bridge.save_subjects(subjects)
        asset_id = "asset_" + "a" * 30
        bridge.state["assets"][asset_id] = {"filename": "离线合成附件.txt", "sha256": "b" * 64, "size": 12, "mimeType": "text/plain"}
        bridge.persist()
        request = {"conversationId": conversation_id, "clientRequestId": str(uuid.uuid4()), "prompt": "仅供离线单元测试的合成文字", "localAssetIds": [asset_id], "contentProduction": {"mode": "new_reference_pack", "enterpriseName": "离线测试主体", "knowledgeSource": "files", "monitoringAnswerAssetIds": []}}
        return bridge, remote, snapshot, request

    def test_tasks_provider_messages_and_encoded_paths_never_open_network(self):
        remote = object.__new__(bridge_module.Remote)
        remote._authorization = "Basic offline-test-placeholder"
        remote.opener = Mock()
        remote.opener.open.side_effect = AssertionError("拒绝路径不应抵达出站调用")
        rejected = [
            ("POST", "/api/frontmind/v2/tasks"), ("GET", "/api/frontmind/v2/tasks/task-1"),
            ("POST", "/api/frontmind/v2/tasks/task-1/messages"), ("POST", "/api/frontmind/v2/messages"),
            ("POST", "/api/frontmind/tasks"), ("POST", "/api/frontmind/messages"),
            ("POST", "/api/provider/responses"), ("POST", "/api/frontmind/v2/provider/responses"),
            ("POST", "/api/responses"), ("POST", "/v1/responses"),
            ("POST", "/api/content/conversations/chat-1/messages"), ("DELETE", "/api/content/conversations/chat-1"),
            ("GET", "/api/frontmind/v2/%74asks"), ("PUT", "/api/content/conversations/%2e%2e"),
            ("PUT", "/api/content/conversations/chat%2fmessages"), ("PUT", "/api/content/conversations/chat%252fmessages"),
            ("GET", "/api/frontmind/v2/assets/../tasks"), ("GET", "/api/frontmind/v2/assets/%2e%2e/content"),
            ("GET", "/api/module/context?target=/tasks"), ("GET", "//elsewhere.invalid/api/module/context"),
            ("POST", "/api/frontmind/v2/assets/"), ("HEAD", "/api/module/context"),
        ]
        for method, path in rejected:
            with self.subTest(method=method, path=path), self.assertRaises(bridge_module.BridgeError) as caught:
                remote.open(method, path)
            self.assertEqual(caught.exception.status, 403)
        remote.opener.open.assert_not_called()

    def test_local_draft_is_explicit_and_never_put_remotely(self):
        bridge, remote, snapshot, _ = self.fixture()
        self.assertEqual(remote.puts, [])
        self.assertEqual(bridge.state["managedIds"][snapshot["id"]]["status"], "draft")
        rows = bridge.list_conversations()
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["localDraft"], True)
        self.assertEqual(rows[0]["messages"], [])
        status, duplicate = bridge.create_conversation(snapshot["id"], snapshot, local_draft=True)
        self.assertEqual(status, 200)
        self.assertIs(duplicate["localDraft"], True)
        self.assertEqual(remote.puts, [])

    def test_intake_is_one_native_put_and_verified_get_before_receipt(self):
        bridge, remote, snapshot, request = self.fixture()
        remote.calls.clear()
        receipt = bridge.intake(request)
        self.assertEqual([call[0] for call in remote.calls], ["GET", "PUT", "GET"])
        self.assertEqual(len(remote.puts), 1)
        saved = remote.puts[0][2]
        self.assertNotIn("localDraft", saved)
        self.assertNotIn("taskId", saved)
        message = saved["messages"][0]
        self.assertEqual(message["role"], "user")
        self.assertEqual(message["content"], request["prompt"])
        self.assertEqual(message["attachments"][0]["fileId"], request["localAssetIds"][0])
        envelope = message["generalChatDispatch"]
        self.assertEqual(envelope["kind"], "pending_user")
        self.assertEqual(envelope["purpose"], "content_production")
        self.assertIsNone(envelope["localTaskId"])
        self.assertEqual(envelope["providerPrompt"], request["prompt"])
        self.assertEqual(envelope["contentProduction"], request["contentProduction"])
        self.assertEqual(receipt["status"], "received")
        self.assertIs(receipt["executionStarted"], False)
        self.assertEqual(receipt["conversation"], remote.rows[snapshot["id"]])
        self.assertNotIn("localDraft", receipt["conversation"])
        previous_calls = len(remote.calls)
        self.assertEqual(bridge.intake(copy.deepcopy(request)), receipt)
        self.assertEqual(len(remote.calls), previous_calls)

    def test_missing_or_changed_readback_fails_and_never_retries(self):
        for mode in ("missing", "changed_text", "changed_attachment", "changed_dispatch", "unexpected_task"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=self.temporary.name) as directory:
                bridge, remote, _, request = self.fixture(mode, directory)
                with self.assertRaises(bridge_module.BridgeError) as caught:
                    bridge.intake(request)
                self.assertEqual(caught.exception.status, 409)
                self.assertEqual(len(remote.puts), 1)
                pending = bridge.state["intakes"][request["clientRequestId"]]
                self.assertEqual(pending["status"], "failed")
                self.assertNotIn("receipt", pending)
                calls = len(remote.calls)
                with self.assertRaises(bridge_module.BridgeError) as repeated:
                    bridge.intake(request)
                self.assertEqual(repeated.exception.code, "INTAKE_OUTCOME_UNCONFIRMED")
                self.assertEqual(len(remote.calls), calls)

    def test_seconds_truncation_and_added_attachment_validity_are_accepted(self):
        bridge, remote, _, request = self.fixture("normalized")
        # 999ms 是允许秒级截断的最大差值，固定时间避免偶发测不到边界。
        fixed = datetime(2026, 10, 23, 0, 0, 0, 999000, timezone.utc)
        with patch.object(bridge_module, "datetime") as clock:
            clock.now.return_value = fixed
            receipt = bridge.intake(request)
        expected = remote.puts[0][2]["messages"][0]
        returned = receipt["conversation"]["messages"][0]
        self.assertEqual(expected["timestamp"] - returned["timestamp"], 999)
        self.assertEqual(returned["timestamp"] % 1000, 0)
        self.assertIs(returned["attachments"][0]["expired"], False)
        self.assertIn("expiresAt", returned["attachments"][0])
        for key in ("id", "type", "name", "fileId"):
            self.assertEqual(returned["attachments"][0][key], expected["attachments"][0][key])
        self.assertEqual(returned["generalChatDispatch"], expected["generalChatDispatch"])
        self.assertEqual(receipt["status"], "received")
        self.assertIs(receipt["executionStarted"], False)
        self.assertEqual(len(remote.puts), 1)

    def test_normalization_never_accepts_content_expiry_or_1000ms_mismatch(self):
        modes = ("normalized_changed_text", "normalized_changed_attachment", "normalized_changed_dispatch", "normalized_expired", "normalized_timestamp_plus_1000", "normalized_timestamp_minus_1000")
        for mode in modes:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=self.temporary.name) as directory:
                bridge, remote, _, request = self.fixture(mode, directory)
                with self.assertRaises(bridge_module.BridgeError) as caught:
                    bridge.intake(request)
                self.assertEqual(caught.exception.status, 409)
                self.assertEqual(caught.exception.code, "REMOTE_READBACK_MISMATCH")
                pending = bridge.state["intakes"][request["clientRequestId"]]
                self.assertEqual(pending["status"], "failed")
                self.assertNotIn("receipt", pending)
                calls = len(remote.calls)
                with self.assertRaises(bridge_module.BridgeError):
                    bridge.intake(request)
                self.assertEqual(len(remote.calls), calls)
                self.assertEqual(len(remote.puts), 1)

    def test_unknown_write_stays_locked_after_local_restart(self):
        bridge, remote, _, request = self.fixture("unknown_put")
        with self.assertRaises(bridge_module.BridgeError) as caught:
            bridge.intake(request)
        self.assertEqual(caught.exception.status, 502)
        self.assertEqual(len(remote.puts), 1)
        restarted = bridge_module.Bridge(remote, Path(self.temporary.name))
        previous_calls = len(remote.calls)
        with self.assertRaises(bridge_module.BridgeError) as repeated:
            restarted.intake(request)
        self.assertEqual(repeated.exception.status, 409)
        self.assertEqual(repeated.exception.code, "INTAKE_OUTCOME_UNCONFIRMED")
        self.assertEqual(len(remote.calls), previous_calls)

    def test_same_request_id_different_content_is_conflict_without_second_put(self):
        bridge, remote, _, request = self.fixture()
        bridge.intake(request)
        changed = {**request, "prompt": request["prompt"] + "不同内容"}
        previous_calls = len(remote.calls)
        with self.assertRaises(bridge_module.BridgeError) as caught:
            bridge.intake(changed)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.code, "INTAKE_ID_CONFLICT")
        self.assertEqual(len(remote.calls), previous_calls)
        self.assertEqual(len(remote.puts), 1)


if __name__ == "__main__":
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BridgeOfflineTests))
    report = {"passed": result.wasSuccessful(), "testsRun": result.testsRun, "offlineOnly": True, "realBackendValidated": False, "externalNetworkConnections": 0, "modelCalls": 0, "details": stream.getvalue()}
    (HERE / "offline-bridge-tests-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(stream.getvalue())
    raise SystemExit(0 if result.wasSuccessful() else 1)
