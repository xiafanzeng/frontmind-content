#!/usr/bin/env python3
# 依赖：Python 3.11+ 标准库；无需 pip 安装。
"""本机真实收件桥：只保存会话、附件及待执行信封，绝不创建或执行任务。

运行后只监听 127.0.0.1:5174。首次导入本模块不会读凭据、建文件或联网。
授权只保留在本进程；日志不记录正文、附件原文或凭据。
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import socket
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REMOTE_ORIGIN = "https://content.frontmind.cn"
BIND_HOST, BIND_PORT = "127.0.0.1", 5174
DATA_DIRECTORY = Path(__file__).resolve().parent / ".local-state"
CREDENTIAL_FILE = Path.home() / ".codex" / "frontmind-private" / "content-gateway.json"
ALLOWED_ORIGINS = frozenset(f"http://{host}:{port}" for host in ("127.0.0.1", "localhost") for port in (5173, 5174))
ALLOWED_HOSTS = frozenset(f"{host}:{port}" for host in ("127.0.0.1", "localhost") for port in (5173, 5174))
MAX_JSON_BYTES, MAX_ASSET_BYTES = 2 * 1024 * 1024, 512 * 1024 * 1024
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
EMPTY_SUBJECTS = {"schemaVersion": 1, "revision": 0, "folders": [], "bindings": {}}
MODES = {"new_reference_pack", "refresh_reference_pack", "p0", "foundation_article", "import_foundation", "single_article"}


def configured_path(variable: str, default: Path) -> Path:
    """路径配置只读环境；不检查文件、不创建目录，也不读取凭据。"""
    value = os.environ.get(variable, "").strip()
    return Path(value).expanduser().resolve() if value else default


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


class BridgeError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def require(condition, code="INVALID_INPUT", message="输入格式无效。", status=400):
    if not condition:
        raise BridgeError(status, code, message)


def text(value, maximum=200, *, empty=False):
    return isinstance(value, str) and len(value) <= maximum and (empty or bool(value.strip()))


def identifier(value):
    return isinstance(value, str) and bool(SAFE_ID.fullmatch(value))


def forbid_execution_fields(value):
    if isinstance(value, dict):
        forbidden = {"taskId", "executionKind", "generalChatDispatch", "contentProductionAction", "modelProfile", "providerPrompt", "execution", "processes"}
        require(not forbidden.intersection(value), "EXECUTION_FIELDS_FORBIDDEN", "此收件桥不接受客户端的任务、派发或执行字段。", 403)
        for nested in value.values():
            forbid_execution_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            forbid_execution_fields(nested)


def validate_content_production(value, owned_assets):
    require(isinstance(value, dict), message="缺少内容制作收件配置。")
    permitted = {"mode", "enterpriseName", "knowledgeSource", "entry", "questionId", "question", "genre", "subjectScope", "articleFocus", "readerQuestions", "excludedTopics", "comparisonDimensions", "monitoringAnswerAssetIds", "sourceWorkbookAssetId"}
    require(not set(value) - permitted, message="内容制作配置存在未知字段。")
    require(value.get("mode") in MODES and text(value.get("enterpriseName")), message="内容制作类型或主体名称无效。")
    require(value.get("knowledgeSource") in {"files", "published"}, message="知识来源无效。")
    enums = {"entry": {"industry_ranking", "competitor_comparison", "reputation", "product_scenario"}, "genre": {"default", "industry_roundup"}}
    for key, allowed in enums.items():
        require(key not in value or value[key] in allowed, message=f"{key} 无效。")
    for key, maximum in (("questionId", 200), ("question", 20000), ("articleFocus", 300)):
        require(key not in value or text(value[key], maximum, empty=key != "questionId"), message=f"{key} 无效。")
    for key, lower, upper, length in (("subjectScope", 3, 12, 200), ("readerQuestions", 0, 8, 300), ("excludedTopics", 0, 12, 300), ("comparisonDimensions", 2, 8, 100)):
        if key in value:
            items = value[key]
            require(isinstance(items, list) and lower <= len(items) <= upper and all(text(item, length) for item in items), message=f"{key} 无效。")
            require(len({item.strip().casefold() for item in items}) == len(items), message=f"{key} 不能重复。")
    if value.get("genre") == "industry_roundup":
        names = value.get("subjectScope", [])
        require(value["mode"] == "single_article" and len(names) >= 3 and names[0].strip().casefold() == value["enterpriseName"].strip().casefold() and len(value.get("comparisonDimensions", [])) >= 2, message="行业盘点配置不完整。")
    else:
        require(not value.get("subjectScope") and not value.get("comparisonDimensions"), message="主体名单和对比维度仅用于行业盘点。")
    require(value["mode"] == "single_article" or not any(value.get(key) for key in ("articleFocus", "readerQuestions", "excludedTopics")), message="本篇聚焦设置仅用于问题文章。")
    asset_ids = value.get("monitoringAnswerAssetIds", [])
    require(isinstance(asset_ids, list) and len(asset_ids) <= 16 and all(identifier(item) and len(item) <= 36 and item in owned_assets for item in asset_ids), "ASSET_NOT_MANAGED", "监控附件必须由本桥真实上传。", 403)
    source = value.get("sourceWorkbookAssetId")
    require(source is None or identifier(source) and len(source) <= 36 and source in owned_assets, "ASSET_NOT_MANAGED", "信源附件必须由本桥真实上传。", 403)
    return copy.deepcopy(value)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BridgeError(502, "REMOTE_REDIRECT_REFUSED", "远端重定向已拒绝，未转发网关鉴权。")


class Remote:
    def __init__(self, credential_file=None):
        credential_file = Path(credential_file).expanduser() if credential_file is not None else configured_path("FRONTMIND_REAL_BACKEND_CREDENTIAL_FILE", CREDENTIAL_FILE)
        try:
            credentials = json.loads(credential_file.read_text(encoding="utf-8-sig"))
            require(text(credentials.get("username"), 1000) and text(credentials.get("password"), 4000), message="既有网关凭据格式无效。")
            self._authorization = "Basic " + base64.b64encode(f"{credentials['username']}:{credentials['password']}".encode()).decode("ascii")
        except (OSError, ValueError) as error:
            raise BridgeError(500, "GATEWAY_CREDENTIAL_UNAVAILABLE", "不能读取既有网关凭据；没有联网。") from error
        self.opener = build_opener(NoRedirect())

    def open(self, method, path, body=None, headers=None):
        require(path.startswith("/api/") and not urlsplit(path).query and not urlsplit(path).netloc, "REMOTE_PATH_REFUSED", "远端路径被拒绝。", 403)
        allowed = (
            method == "GET" and path in {"/api/module/context", "/api/version", "/api/content/conversations"}
            or method == "GET" and re.fullmatch(r"/api/frontmind/v2/assets/[A-Za-z0-9_-]{1,128}/content", path)
            or method == "PUT" and re.fullmatch(r"/api/content/conversations/[A-Za-z0-9_-]{1,128}", path)
            or method == "POST" and path == "/api/frontmind/v2/assets"
        )
        require(allowed, "REMOTE_ROUTE_FORBIDDEN", "后端任务、模型与 Runner 路由在出站层同样禁用。", 403)
        request_headers = {"Authorization": self._authorization, "Accept": "application/json", "Origin": REMOTE_ORIGIN, "Sec-Fetch-Site": "same-origin", **(headers or {})}
        request = Request(REMOTE_ORIGIN + path, data=body, method=method, headers=request_headers)
        try:
            return self.opener.open(request, timeout=60)
        except HTTPError as error:
            # 不转发远端错误正文，避免日志或响应包含后端内部信息。
            raise BridgeError(502, "REMOTE_HTTP_ERROR", f"真实后端返回 HTTP {error.code}；本桥没有自动重试。") from error
        except (URLError, TimeoutError, OSError, socket.timeout) as error:
            raise BridgeError(502, "REMOTE_OUTCOME_UNCONFIRMED", "真实后端响应未确认；可能已经写入，本桥不会自动重试。") from error

    def json(self, method, path, value=None):
        body = encoded(value) if value is not None else None
        with self.open(method, path, body, {"Content-Type": "application/json"} if body else None) as response:
            raw = response.read(MAX_JSON_BYTES + 1)
            require(len(raw) <= MAX_JSON_BYTES, "REMOTE_RESPONSE_TOO_LARGE", "后端 JSON 回执过大。", 502)
            try:
                return response.status, json.loads(raw)
            except (ValueError, UnicodeError) as error:
                raise BridgeError(502, "REMOTE_JSON_INVALID", "后端没有返回有效 JSON 回执。") from error


class Bridge:
    def __init__(self, remote, data_directory=None):
        self.remote = remote
        self.directory = Path(data_directory).expanduser() if data_directory is not None else configured_path("FRONTMIND_REAL_BACKEND_DATA_DIR", DATA_DIRECTORY)
        self.lock = threading.RLock()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state_path = self.directory / "state.json"
        if self.state_path.exists():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
                require(self.state.get("schemaVersion") == 1 and all(isinstance(self.state.get(key), dict) for key in ("managedIds", "assets", "uploads", "intakes", "subjectWorkspace")), message="本机桥状态格式无效，已停止；不会覆盖。")
            except (OSError, ValueError) as error:
                raise BridgeError(500, "LOCAL_STATE_INVALID", "本机桥状态不可读取，已停止；不会重建或覆盖。") from error
        else:
            self.state = {"schemaVersion": 1, "managedIds": {}, "assets": {}, "uploads": {}, "intakes": {}, "subjectWorkspace": copy.deepcopy(EMPTY_SUBJECTS)}
            self.persist()

    def persist(self):
        temporary = self.directory / "state.json.next"
        with temporary.open("wb") as output:
            output.write(encoded(self.state))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.state_path)

    def audit(self, method, path, status, digest=None):
        event = {"at": now(), "method": method, "path": path, "status": status}
        if digest:
            event["sha256"] = digest
        with self.lock, (self.directory / "audit.jsonl").open("ab") as output:
            output.write(encoded(event) + b"\n")

    def remote_conversations(self):
        _, rows = self.remote.json("GET", "/api/content/conversations")
        require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "REMOTE_CONVERSATIONS_INVALID", "后端会话列表格式无效。", 502)
        return rows

    def managed(self, conversation_id):
        require(identifier(conversation_id) and conversation_id in self.state["managedIds"], "CONVERSATION_NOT_MANAGED", "只能操作本桥新建的测试会话。", 403)
        return self.state["managedIds"][conversation_id]

    def list_conversations(self):
        # 远端会话来自真实 GET；尚未确认的本机草稿明确标记 localDraft。
        rows = [row for row in self.remote_conversations() if row.get("id") in self.state["managedIds"]]
        remote_ids = {row["id"] for row in rows}
        drafts = [copy.deepcopy(record["createdSnapshot"]) for cid, record in self.state["managedIds"].items() if record.get("status") == "draft" and cid not in remote_ids]
        return [*rows, *drafts]

    def create_conversation(self, conversation_id, value, *, local_draft=False):
        forbid_execution_fields(value)
        require(isinstance(value, dict) and not set(value) - {"id", "title", "purpose", "status", "messages", "createdAt", "updatedAt"}, message="新会话字段无效。")
        try:
            parsed = uuid.UUID(conversation_id)
            valid_uuid = str(parsed) == conversation_id and parsed.version == 4
        except (ValueError, TypeError):
            valid_uuid = False
        require(valid_uuid and value.get("id") == conversation_id and value.get("purpose") == "content_production" and value.get("status") == "idle" and value.get("messages") == [] and text(value.get("title"), 200), message="只能新建空白内容制作测试会话。")
        require(all(type(value.get(key)) is int and value[key] > 0 for key in ("createdAt", "updatedAt")), message="会话时间格式无效。")
        digest = fingerprint(value)
        record = self.state["managedIds"].get(conversation_id)
        if record:
            require(record.get("fingerprint") == digest, "CONVERSATION_CREATE_CONFLICT", "此会话编号已使用，不能通过创建接口修改。", 409)
            require(record.get("status") in {"created", "draft"}, "CREATE_OUTCOME_UNCONFIRMED", "此创建操作曾失败或结果未知，不会再次写入。", 409)
            return 200, copy.deepcopy(record["createdSnapshot"])
        require(not any(row.get("id") == conversation_id for row in self.remote_conversations()), "REMOTE_CONVERSATION_ALREADY_EXISTS", "该会话已存在于真实后端，禁止接管或修改。", 409)
        if local_draft:
            snapshot = {**copy.deepcopy(value), "localDraft": True}
            self.state["managedIds"][conversation_id] = {"status": "draft", "fingerprint": digest, "createdAt": now(), "createdSnapshot": snapshot}
            self.persist()
            return 200, snapshot
        record = {"status": "creating", "fingerprint": digest, "createdAt": now()}
        self.state["managedIds"][conversation_id] = record
        self.persist()
        try:
            status, result = self.remote.json("PUT", f"/api/content/conversations/{conversation_id}", value)
            require(isinstance(result, dict) and result.get("id") == conversation_id and result.get("messages") == [], "REMOTE_CREATE_RECEIPT_INVALID", "真实创建回执与请求不符；不会自动重试。", 409)
            require(not result.get("taskId") and not result.get("executionKind"), "REMOTE_EXECUTION_UNEXPECTED", "后端意外返回执行字段，已停止。", 409)
            # 这里返回的就是真实 PUT 回执；不能声称已通过 GET 读取。
            record.update(status="created", createdSnapshot=copy.deepcopy(result), acceptedAt=now())
            self.persist()
            return status, result
        except BridgeError as error:
            record.update(status="failed", errorCode=error.code)
            self.persist()
            raise

    def save_subjects(self, value):
        require(isinstance(value, dict) and set(value) == {"schemaVersion", "revision", "folders", "bindings"} and value.get("schemaVersion") == 1, message="主体资料库格式无效。")
        previous = self.state["subjectWorkspace"]
        require(type(value.get("revision")) is int and value["revision"] == previous["revision"] + 1, "SUBJECT_REVISION_CONFLICT", "主体资料已变化，请刷新；未覆盖新状态。", 409)
        require(isinstance(value.get("folders"), list) and len(value["folders"]) <= 200 and isinstance(value.get("bindings"), dict), message="主体目录格式无效。")
        folder_ids, names = set(), set()
        for folder in value["folders"]:
            require(isinstance(folder, dict) and not set(folder) - {"id", "name", "expanded", "versions"} and identifier(folder.get("id")) and text(folder.get("name"), 128) and folder.get("versions") == [], "PACK_VERSIONS_FORBIDDEN", "此收件桥不能生成或登记资料包版本。", 403)
            require(folder["id"] not in folder_ids and folder["name"].strip().casefold() not in names, message="主体名称或标识重复。")
            require("expanded" not in folder or type(folder["expanded"]) is bool, message="目录展开状态无效。")
            folder_ids.add(folder["id"])
            names.add(folder["name"].strip().casefold())
        for conversation_id, binding in value["bindings"].items():
            record = self.managed(conversation_id)
            require(record.get("status") in {"created", "draft"} and isinstance(binding, dict) and not set(binding) - {"folderId", "kind", "packVersionId", "pinned", "archived", "generation", "restartRequired"}, message="聊天归属格式无效。")
            require(binding.get("folderId") in folder_ids and binding.get("kind") in {"pack", "article"} and binding.get("packVersionId") is None and binding.get("generation") == 0 and type(binding.get("generation")) is int and binding.get("restartRequired", False) is False, message="只能归档已创建聊天，不能伪造资料包引用或运行代次。")
            require(all(key not in binding or type(binding[key]) is bool for key in ("pinned", "archived", "restartRequired")), message="聊天元数据无效。")
            old = previous["bindings"].get(conversation_id)
            require(not old or old["folderId"] == binding["folderId"] and old["kind"] == binding["kind"], "SUBJECT_BINDING_CONFLICT", "已有测试聊天不能变更主体或用途。", 409)
        require(set(previous["bindings"]).issubset(value["bindings"]), message="此收件桥不删除已有聊天归属。")
        self.state["subjectWorkspace"] = copy.deepcopy(value)
        self.persist()
        return value

    def intake(self, value):
        forbid_execution_fields(value)
        require(isinstance(value, dict) and set(value) == {"conversationId", "clientRequestId", "prompt", "localAssetIds", "contentProduction"}, message="收件字段不完整或存在未知字段。")
        conversation_id, request_id = value["conversationId"], value["clientRequestId"]
        record = self.managed(conversation_id)
        require(record.get("status") in {"created", "draft"}, "CONVERSATION_CREATE_UNCONFIRMED", "测试会话草稿未保存，不能继续写入。", 409)
        require(identifier(request_id) and text(value["prompt"], 20000, empty=True), message="收件编号或文字无效。")
        assets = value["localAssetIds"]
        require(isinstance(assets, list) and len(assets) <= 16 and len(set(item for item in assets if isinstance(item, str))) == len(assets) and all(identifier(item) and item in self.state["assets"] for item in assets), "ASSET_NOT_MANAGED", "附件必须由本桥上传且不能重复。", 403)
        require(value["prompt"].strip() or assets, message="请输入文字或选择附件。")
        config = validate_content_production(value["contentProduction"], self.state["assets"])
        binding = self.state["subjectWorkspace"]["bindings"].get(conversation_id)
        require(binding is not None, "CONVERSATION_NOT_BOUND", "请先将测试聊天归入主体目录。", 409)
        folder = next((item for item in self.state["subjectWorkspace"]["folders"] if item["id"] == binding["folderId"]), None)
        require(folder and config["enterpriseName"].strip() == folder["name"].strip(), message="收件主体与聊天归属不一致。")
        digest = fingerprint(value)
        previous = self.state["intakes"].get(request_id)
        if previous:
            require(previous.get("fingerprint") == digest, "INTAKE_ID_CONFLICT", "同一收件编号不能提交不同内容。", 409)
            require(previous.get("status") == "received", "INTAKE_OUTCOME_UNCONFIRMED", "此收件曾失败或结果未知，不会再次写入。请人工核对。", 409)
            return copy.deepcopy(previous["receipt"])
        rows = self.remote_conversations()
        conversation = next((row for row in rows if row.get("id") == conversation_id), None)
        if conversation is None:
            # 空聊天可能被当前后端的 purpose 投影过滤。首次收件只沿用真实 PUT
            # 已返回的空快照；写后仍必须由真实 GET 读回，不补造 GET 结果。
            initial = record.get("createdSnapshot", {})
            require(initial.get("messages") == [] and not any(item.get("conversationId") == conversation_id for item in self.state["intakes"].values()), "REMOTE_CONTENT_CONVERSATION_NOT_READABLE", "真实 GET 找不到此会话，可能丢失了 purpose；已停止，不能伪造读取成功。", 409)
            conversation = copy.deepcopy(initial)
        require(conversation.get("id") == conversation_id and isinstance(conversation.get("messages"), list) and not conversation.get("taskId") and not conversation.get("executionKind") and not conversation.get("execution"), "REMOTE_EXECUTION_UNEXPECTED", "会话已有任务或执行上下文，禁止继续写入。", 409)
        require(all(isinstance(message, dict) and message.get("role") == "user" for message in conversation["messages"]), "REMOTE_ASSISTANT_UNEXPECTED", "此收件桥不接管含助手回复的会话。", 409)
        require(not any(message.get("id") == request_id for message in conversation["messages"]), "REMOTE_MESSAGE_ID_CONFLICT", "真实会话已含同编号消息，尚未确认来源，不能重复写入。", 409)
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        dispatch = {"schemaVersion": 1, "kind": "pending_user", "clientRequestId": request_id, "providerPrompt": value["prompt"], "localAssetIds": list(assets), "localTaskId": None, "modelProfile": "frontmind-base", "purpose": "content_production", "contentProduction": config}
        message = {"id": request_id, "role": "user", "content": value["prompt"], "timestamp": timestamp, "generalChatDispatch": dispatch}
        if assets:
            message["attachments"] = [{"id": asset_id, "type": "file", "name": self.state["assets"][asset_id]["filename"], "fileId": asset_id} for asset_id in assets]
        updated = {key: copy.deepcopy(conversation[key]) for key in ("id", "title", "createdAt", "status") if key in conversation}
        updated.update(purpose="content_production", updatedAt=timestamp, messages=[*copy.deepcopy(conversation["messages"]), message])
        pending = {"status": "writing", "fingerprint": digest, "conversationId": conversation_id, "startedAt": now()}
        self.state["intakes"][request_id] = pending
        self.persist()
        try:
            self.remote.json("PUT", f"/api/content/conversations/{conversation_id}", updated)
            actual = next((row for row in self.remote_conversations() if row.get("id") == conversation_id), None)
            require(actual is not None and actual.get("purpose") == "content_production", "REMOTE_CONTENT_CONVERSATION_NOT_READABLE", "保存后真实 GET 仍找不到内容制作会话，可能丢失 purpose；未确认成功，不自动重试。", 409)
            require(not actual.get("taskId") and not actual.get("executionKind") and not actual.get("execution"), "REMOTE_EXECUTION_UNEXPECTED", "真实会话出现意外执行字段，未确认收件成功。", 409)
            require(len(actual.get("messages", [])) == len(updated["messages"]), "REMOTE_READBACK_MISMATCH", "真实读回的消息数量不一致，未确认成功。", 409)
            for expected, returned in zip(updated["messages"], actual["messages"]):
                # Core 按秒保存时间戳，并为附件追加有效期信息；只允许这些服务端规范化。
                same = isinstance(returned, dict) and all(returned.get(key) == expected.get(key) for key in ("id", "role", "content", "generalChatDispatch"))
                same = same and isinstance(returned.get("timestamp"), (int, float)) and abs(returned["timestamp"] - expected["timestamp"]) < 1000
                expected_files, returned_files = expected.get("attachments", []), returned.get("attachments", [])
                same = same and len(expected_files) == len(returned_files) and all(isinstance(got, dict) and not got.get("expired", False) and all(got.get(key) == wanted.get(key) for key in ("id", "type", "name", "fileId")) for wanted, got in zip(expected_files, returned_files))
                require(same, "REMOTE_READBACK_MISMATCH", "真实读回的文字、附件或待执行收件信封不一致，未确认成功。", 409)
            receipt = {"id": request_id, "conversationId": conversation_id, "status": "received", "executionStarted": False, "acceptedAt": timestamp, "conversation": actual}
            pending.update(status="received", receipt=receipt)
            record["status"] = "created"
            self.persist()
            return receipt
        except BridgeError as error:
            pending.update(status="failed", errorCode=error.code)
            self.persist()
            raise


class Handler(BaseHTTPRequestHandler):
    server_version = "FrontMindLocalIntake/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    @property
    def bridge(self):
        return self.server.bridge

    def guard(self):
        require(self.client_address[0] == BIND_HOST and self.headers.get("Host", "") in ALLOWED_HOSTS, "LOCAL_HOST_REQUIRED", "仅接受本机地址请求。", 403)
        origin = self.headers.get("Origin")
        require(origin is None or origin in ALLOWED_ORIGINS, "ORIGIN_REFUSED", "请求来源不是本机工作区。", 403)
        require(self.command == "GET" or origin in ALLOWED_ORIGINS, "ORIGIN_REQUIRED", "写入请求必须携带本机工作区 Origin。", 403)
        parsed = urlsplit(self.path)
        require(not parsed.scheme and not parsed.netloc and not parsed.query and not parsed.fragment and "%" not in parsed.path and ".." not in parsed.path, "PATH_REFUSED", "路径或查询参数不在许可范围。", 403)
        require(not self.headers.get("Transfer-Encoding"), "TRANSFER_ENCODING_REFUSED", "请使用明确 Content-Length。", 400)
        return parsed.path

    def json_body(self):
        require(self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() == "application/json", message="请提交 JSON。", status=415)
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        require(0 < length <= MAX_JSON_BYTES, "BODY_SIZE_INVALID", "JSON 请求大小无效。", 413)
        raw = self.rfile.read(length)
        require(len(raw) == length, message="请求正文不完整。")
        self.request_digest = hashlib.sha256(raw).hexdigest()
        try:
            return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError) as error:
            raise BridgeError(400, "JSON_INVALID", "JSON 正文无效。") from error

    def send_json(self, status, value):
        body = encoded(value)
        self.send_response(status)
        self.common_headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)

    def common_headers(self, content_type, length):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.send_header("Connection", "close")
        self.close_connection = True
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def upload(self):
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            declared = int(self.headers.get("X-FrontMind-Size", "-1"))
            filename = unquote(self.headers.get("X-FrontMind-Filename", ""), errors="strict")
        except (ValueError, UnicodeError):
            raise BridgeError(400, "ASSET_HEADERS_INVALID", "附件大小或文件名无效。")
        require(0 < length <= MAX_ASSET_BYTES and declared == length, "ASSET_SIZE_INVALID", "附件大小无效或与声明不符。", 413)
        require(text(filename, 255) and not any(char in filename for char in ("/", "\\", "\r", "\n", "\x00")) and filename not in {".", ".."}, message="附件文件名无效。")
        mime = self.headers.get("X-FrontMind-Mime", "application/octet-stream")
        require(bool(re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", mime)), message="附件类型无效。")
        attempt_id, digest = str(uuid.uuid4()), hashlib.sha256()
        with tempfile.TemporaryFile(dir=self.bridge.directory) as staged:
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                require(chunk, message="附件正文不完整。")
                digest.update(chunk)
                staged.write(chunk)
                remaining -= len(chunk)
            self.request_digest = digest.hexdigest()
            staged.seek(0)
            attempt = {"status": "uploading", "sha256": digest.hexdigest(), "size": length, "startedAt": now()}
            self.bridge.state["uploads"][attempt_id] = attempt
            self.bridge.persist()
            try:
                headers = {"Content-Type": "application/octet-stream", "Content-Length": str(length), "X-FrontMind-Mime": mime, "X-FrontMind-Filename": quote(filename, safe=""), "X-FrontMind-Size": str(length)}
                with self.bridge.remote.open("POST", "/api/frontmind/v2/assets", staged, headers) as response:
                    status = response.status
                    raw = response.read(MAX_JSON_BYTES + 1)
                    require(len(raw) <= MAX_JSON_BYTES, "REMOTE_ASSET_RECEIPT_INVALID", "上传回执过大。", 502)
                    result = json.loads(raw)
                asset_id = result.get("localAssetId") if isinstance(result, dict) else None
                require(identifier(asset_id) and result.get("bytes") == length and result.get("sha256") == digest.hexdigest() and text(result.get("filename"), 255), "REMOTE_ASSET_RECEIPT_MISMATCH", "真实上传回执的编号、大小或 SHA256 不一致；不自动重试。", 409)
                self.bridge.state["assets"][asset_id] = {"sha256": digest.hexdigest(), "size": length, "filename": result["filename"], "mimeType": result.get("mimeType", mime), "uploadedAt": now()}
                attempt.update(status="uploaded", assetId=asset_id)
                self.bridge.persist()
                return status, result
            except (ValueError, UnicodeError) as error:
                attempt.update(status="failed", errorCode="REMOTE_ASSET_RECEIPT_INVALID")
                self.bridge.persist()
                raise BridgeError(502, "REMOTE_ASSET_RECEIPT_INVALID", "真实上传回执不是有效 JSON；不自动重试。") from error
            except BridgeError as error:
                attempt.update(status="failed", errorCode=error.code)
                self.bridge.persist()
                raise

    def asset_content(self, asset_id):
        asset = self.bridge.state["assets"].get(asset_id)
        require(asset is not None, "ASSET_NOT_MANAGED", "仅可读取本桥真实上传的附件。", 403)
        with self.bridge.remote.open("GET", f"/api/frontmind/v2/assets/{asset_id}/content") as response:
            # 先落临时文件核对大小和散列，再向浏览器返回真实内容。
            with tempfile.TemporaryFile(dir=self.bridge.directory) as staged:
                digest, size = hashlib.sha256(), 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    require(size <= asset["size"], "ASSET_READBACK_MISMATCH", "真实附件内容大小不一致。", 409)
                    digest.update(chunk)
                    staged.write(chunk)
                require(size == asset["size"] and digest.hexdigest() == asset["sha256"], "ASSET_READBACK_MISMATCH", "真实附件内容大小或 SHA256 不一致。", 409)
                staged.seek(0)
                self.send_response(200)
                self.common_headers(asset["mimeType"], size)
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(asset["filename"], safe=""))
                self.end_headers()
                while chunk := staged.read(1024 * 1024):
                    self.wfile.write(chunk)

    def handle_request(self):
        status, path = 500, urlsplit(self.path).path
        self.request_digest = None
        try:
            self.connection.settimeout(60)
            path = self.guard()
            with self.bridge.lock:
                if self.command == "OPTIONS":
                    self.send_response(204)
                    self.common_headers("application/json", 0)
                    self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, X-FrontMind-Mime, X-FrontMind-Filename, X-FrontMind-Size")
                    self.end_headers()
                    status = 204
                    return
                if self.command == "GET" and path in {"/api/module/context", "/api/version"}:
                    status, result = self.bridge.remote.json("GET", path)
                elif self.command == "GET" and path == "/api/content/conversations":
                    status, result = 200, self.bridge.list_conversations()
                elif self.command == "GET" and re.fullmatch(r"/api/frontmind/v2/assets/[A-Za-z0-9_-]{1,128}/content", path):
                    self.asset_content(path.split("/")[-2])
                    status = 200
                    return
                elif path == "/api/content/subject-workspace" and self.command == "GET":
                    status, result = 200, copy.deepcopy(self.bridge.state["subjectWorkspace"])
                elif path == "/api/content/subject-workspace" and self.command == "PUT":
                    status, result = 200, self.bridge.save_subjects(self.json_body())
                elif self.command == "PUT" and re.fullmatch(r"/api/content/conversations/[A-Za-z0-9_-]{1,128}", path):
                    status, result = self.bridge.create_conversation(path.rsplit("/", 1)[-1], self.json_body())
                elif self.command == "PUT" and re.fullmatch(r"/api/content/drafts/[A-Za-z0-9_-]{1,128}", path):
                    status, result = self.bridge.create_conversation(path.rsplit("/", 1)[-1], self.json_body(), local_draft=True)
                elif self.command == "POST" and path == "/api/frontmind/v2/assets":
                    status, result = self.upload()
                elif self.command == "POST" and path == "/api/content/intake":
                    status, result = 200, self.bridge.intake(self.json_body())
                else:
                    raise BridgeError(403, "ROUTE_FORBIDDEN", "此桥仅接收会话和附件；任务、模型、Runner 及其他写入路由全部禁用。")
                self.send_json(status, result)
        except BridgeError as error:
            status = error.status
            self.send_json(status, {"error": error.code, "message": error.message, "executionStarted": False})
        except (BrokenPipeError, ConnectionResetError):
            status = 499
        except Exception:
            status = 500
            self.send_json(status, {"error": "BRIDGE_INTERNAL_ERROR", "message": "本机收件异常，结果未确认；没有自动重试。", "executionStarted": False})
        finally:
            self.bridge.audit(self.command, path, status, self.request_digest)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request
    do_PATCH = handle_request
    do_OPTIONS = handle_request


def main():
    bridge = Bridge(Remote())
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    server.daemon_threads = True
    server.bridge = bridge
    print(f"FrontMind 本机真实收件桥：http://{BIND_HOST}:{BIND_PORT}；所有任务执行路由已禁用。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
