"""Synthetic event fixtures test the public projection, never provider success."""
from copy import deepcopy
try:
    import fcntl
except ImportError:  # Windows 使用不同的文件锁实现；Unix 锁专用用例跳过。
    fcntl = None
import importlib.util
import json
from pathlib import Path
import unittest
from tempfile import mkdtemp


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/export-managed-timeline.py"
SPEC = importlib.util.spec_from_file_location("managed_timeline_export", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def fixture_record(**updates):
    return {"execution_mode": "production", "requested_configuration": {
        "wire_api": "zhipu_managed_agents"}, "session_id": "fixture-session",
        "action": "positioning_market_research", **updates}


def event(number, kind, **fields):
    return {"id": f"fixture-{number}", "type": kind,
            "processed_at": f"2026-10-03T01:00:{number:02d}Z", **fields}


class ManagedTimelineTests(unittest.TestCase):
    def test_failed_attempt_with_generic_error_has_failed_public_reason(self):
        execution = {"attempts": [{"id": "attempt-1", "status": "failed",
                     "action": "positioning_market_research", "startedAt": 1,
                     "diagnosticCode": "execution_error"}], "timeline": []}
        process = exporter.conversation_projection(execution)[0]
        self.assertEqual(process['status'], 'failed')
        self.assertEqual(process['reason'], '本轮执行失败。')
        execution['attempts'][0]['status'] = 'unknown'
        self.assertEqual(exporter.conversation_projection(execution)[0]['reason'], '执行结果尚未确认。')

    def project(self, events, **record_updates):
        return exporter.project_attempt(fixture_record(**record_updates), events,
                                        task_id="local-test", turn_id="turn-1", user_sequence=3)

    def test_tool_return_is_paired_with_original_call(self):
        events = [event(1, "session.status_running"),
                  event(2, "agent.custom_tool_use", name="web_search", input={"query": "private query"}),
                  event(3, "session.status_idle", stop_reason={"type": "requires_action", "event_ids": ["fixture-2"]}),
                  event(4, "user.custom_tool_result", custom_tool_use_id="fixture-2", is_error=False, content=[{"text": "private result"}]),
                  event(5, "session.status_idle", stop_reason={"type": "end_turn"})]
        original = deepcopy(events)
        rows = self.project(events)
        tools = [row for row in rows if row["kind"] == "tool"]
        self.assertEqual(len(tools), 1)
        self.assertEqual((tools[0]["label"], tools[0]["status"]), ("搜索网页", "returned"))
        self.assertGreater(tools[0]["finishedAt"], tools[0]["timestamp"])
        self.assertNotIn("waiting", [row["status"] for row in rows])
        self.assertEqual(rows[-1]["status"], "ended")
        self.assertEqual(events, original)
        self.assertTrue(all(row["turnId"] == "turn-1" and row["userSequence"] == 3 for row in rows))

    def test_missing_result_remains_unconfirmed_and_orphan_return_is_not_a_call(self):
        rows = self.project([event(1, "agent.custom_tool_use", name="read_material"),
                             event(2, "user.custom_tool_result", custom_tool_use_id="absent", is_error=False)])
        self.assertEqual(rows[0]["status"], "unconfirmed")
        self.assertTrue(rows[1]["resultOnly"])
        self.assertFalse(any(row.get("isCurrent") for row in rows))

    def test_private_text_tool_payloads_and_unknown_names_never_escape(self):
        private = "SECRET_PRIVATE_PAYLOAD_7fa9"
        events = [event(1, "agent.thinking", thinkingText=private, content=private),
                  event(2, "agent.message", content=private, publicSummary=private),
                  event(3, "agent.custom_tool_use", name=private, input={"api_key": private}),
                  event(4, "user.custom_tool_result", custom_tool_use_id="fixture-3", is_error=True, content=private),
                  event(5, "session.error", error={"message": private}),
                  event(6, "span.model_request_end", model=private, reasoning=private)]
        events[2]["id"] = private
        events[3]["custom_tool_use_id"] = private
        rows = self.project(events, session_id=private, action=private)
        exported = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn(private, exported)
        self.assertNotIn("thinkingText", exported)
        self.assertNotIn("input", exported)
        self.assertEqual([row for row in rows if row["kind"] == "tool"][0]["status"], "failed")
        self.assertEqual(len(rows), 3)

    def test_replayed_identical_events_are_deduplicated_and_changed_events_rejected(self):
        source = event(1, "agent.custom_tool_use", name="read_material", input={"artifact_id": "one"})
        self.assertEqual(len(self.project([source, deepcopy(source)])), 1)
        changed = {**source, "input": {"artifact_id": "different"}}
        with self.assertRaisesRegex(exporter.ExportError, "MANAGED_EVENT_CHANGED"):
            self.project([source, changed])

    def test_offline_and_encrypted_evidence_cannot_be_presented_as_live(self):
        with self.assertRaisesRegex(exporter.ExportError, "MANAGED_PRODUCTION_EVIDENCE_REQUIRED"):
            self.project([event(1, "session.status_running")], execution_mode="offline_simulated")
        with self.assertRaisesRegex(exporter.ExportError, "MANAGED_EVENTS_ENCRYPTED"):
            self.project([event(1, "session.status_running", encrypted="private")])

    def test_result_before_call_is_rejected(self):
        with self.assertRaisesRegex(exporter.ExportError, "MANAGED_RESULT_PRECEDES_CALL"):
            self.project([event(1, "user.custom_tool_result", custom_tool_use_id="fixture-2"),
                          event(2, "agent.custom_tool_use", name="read_material")])

    def test_queued_user_text_and_unknown_events_do_not_invent_timeline_rows(self):
        self.assertEqual(self.project([{"id": "queued", "type": "user.message", "content": "private"},
                                       event(1, "unknown.event", content="private")]), [])

    def test_receipt_without_error_flag_means_returned_not_completed(self):
        rows = self.project([event(1, "agent.custom_tool_use", name="web_read"),
                             event(2, "user.custom_tool_result", custom_tool_use_id="fixture-1")])
        self.assertEqual(rows[0]["status"], "returned")

    def test_diagnostics_are_fixed_classes_without_raw_error_text(self):
        private = "PRIVATE_ERROR_PAYLOAD"
        rows = self.project([event(1, "agent.custom_tool_use", name="web_read"),
                             event(2, "user.custom_tool_result", custom_tool_use_id="fixture-1", is_error=True,
                                   content=[{"text": json.dumps({"error": "source_acquisition_failed",
                                              "message": "web URL resolves to a non-public address; " + private})}])])
        self.assertEqual(rows[0]["operation"], "web_read")
        self.assertEqual(rows[0]["diagnosticCode"], "non_public_address")
        self.assertNotIn(private, json.dumps(rows))

    def test_running_tools_require_live_process_evidence(self):
        events = [event(1, "agent.custom_tool_use", name="read_material")]
        record = fixture_record(status="running")
        self.assertEqual(exporter.project_attempt(record, events, task_id="test")[0]["status"], "unconfirmed")
        self.assertEqual(exporter.project_attempt(record, events, task_id="test", active=True)[0]["status"], "running")


class ExportJobTests(unittest.TestCase):
    def setUp(self):
        # Small synthetic evidence is left in the OS temporary directory.
        self.root = Path(mkdtemp(prefix="frontmind-timeline-test-"))

    def attempt(self, name, record, events=None):
        path = self.root / "provider" / record["action"] / "runtime" / "attempts" / name
        path.mkdir(parents=True)
        (path / "execution.json").write_text(json.dumps(record))
        if events is not None:
            (path / "events.json").write_text(json.dumps(events))
        return path

    def managed_record(self, name, minute=0, **updates):
        return fixture_record(attempt_id=name, session_id=name, action="p0_blueprint",
                              status="succeeded", started_at=f"2026-10-03T01:{minute:02d}:00Z",
                              finished_at=f"2026-10-03T01:{minute:02d}:30Z", **updates)

    def test_attempt_failure_wins_over_session_end_and_explicit_retry_is_distinct(self):
        failed = self.managed_record("old")
        failed.update(status="failed", error={"code": "invalid_result_contract", "message": "PRIVATE"})
        self.attempt("old", failed, [event(1, "session.status_idle", stop_reason={"type": "end_turn"})])
        retry = self.managed_record("new", minute=1)
        retry["retry_explicit"] = True
        self.attempt("new", retry, [event(2, "session.status_running")])
        value = exporter.export_job(self.root, task_id="test")
        self.assertEqual([row["status"] for row in value["attempts"]], ["failed", "succeeded"])
        self.assertEqual(value["attempts"][1]["recovery"], "new_attempt")
        self.assertEqual(value["attempts"][1]["recoveryDiagnosticCode"], "invalid_result")
        self.assertEqual(value["timeline"][0]["status"], "ended")
        self.assertNotIn("PRIVATE", json.dumps(value))
        anchored = exporter.export_job(self.root, task_id="test", turn_id="application-turn")
        self.assertTrue(all(row["turnId"] == "application-turn" for row in anchored["timeline"] + anchored["attempts"]))
        self.assertEqual(anchored["attempts"][1]["recovery"], "new_attempt")

    def test_same_session_resume_uses_saved_failure_without_duplicate_attempt(self):
        record = self.managed_record("one")
        record.update(resume_count=1, retry_explicit=True)
        path = self.attempt("one", record, [event(1, "session.status_running")])
        previous = {**record, "status": "failed", "error": {"code": "managed_network_error", "message": "PRIVATE"}}
        (path / "resume_001_previous_execution.json").write_text(json.dumps(previous))
        value = exporter.export_job(self.root, task_id="test")
        self.assertEqual(len(value["attempts"]), 1)
        self.assertEqual(value["attempts"][0]["recovery"], "same_session")
        self.assertEqual(value["attempts"][0]["recoveryDiagnosticCode"], "network_error")
        self.assertNotIn("diagnosticCode", value["attempts"][0])

    def test_writer_receipts_are_counted_once_without_invented_event_times(self):
        record = {"execution_mode": "production", "requested_configuration": {"provider": "deepseek"},
                  "action": "article_draft", "attempt_id": "writer", "status": "succeeded",
                  "started_at": "2026-10-03T01:00:00Z", "completed_at": "2026-10-03T01:01:00Z"}
        path = self.attempt("writer", record)
        (path / "round_01_response.json").write_text(json.dumps({"tool_calls": [{"id": "call-1"}, {"id": "call-2"}], "reasoning_content": "PRIVATE"}))
        (path / "tool_001.json").write_text(json.dumps({"tool_call_id": "call-1", "name": "count_article", "arguments": "PRIVATE", "result": {"body_characters": 1234}}))
        (path / "tool_002.json").write_text((path / "tool_001.json").read_text())
        value = exporter.export_job(self.root, task_id="test")
        self.assertEqual(value["timeline"], [])
        self.assertEqual(value["coverage"], "partial")
        self.assertEqual(value["sources"], ["deepseek_writer"])
        self.assertEqual(value["attempts"][0]["toolCounts"], {"calls": 2, "returned": 1, "failed": 0, "unconfirmed": 1})
        self.assertNotIn("PRIVATE", json.dumps(value))

    def test_stale_running_attempt_is_unknown_and_hash_mismatch_is_rejected(self):
        record = self.managed_record("stale")
        record.update(status="running", managed_evidence_sha256={"events.json": "wrong"})
        path = self.attempt("stale", record, [event(1, "session.status_running")])
        with self.assertRaisesRegex(exporter.ExportError, "MANAGED_EVENTS_HASH_MISMATCH"):
            exporter.export_job(self.root, task_id="test")
        record.pop("managed_evidence_sha256")
        (path / "execution.json").write_text(json.dumps(record))
        self.assertEqual(exporter.export_job(self.root, task_id="test")["attempts"][0]["status"], "unknown")
        self.assertEqual(exporter.export_job(self.root, task_id="test", active=True)["attempts"][0]["status"], "unknown")

    @unittest.skipIf(fcntl is None, '此用例专测 Unix flock')
    def test_job_lock_does_not_revive_stale_attempts_during_retry(self):
        old = self.managed_record("old")
        current = self.managed_record("current", minute=1)
        other = self.managed_record("other", minute=2)
        for record in (old, current, other):
            record.update(status="running")
            record.pop("finished_at")
        other["action"] = "article_blueprint"
        self.attempt("old", old, [event(1, "agent.custom_tool_use", name="web_read")])
        current_path = self.attempt("current", current, [event(2, "agent.custom_tool_use", name="web_read")])
        other_path = self.attempt("other", other, [event(3, "agent.custom_tool_use", name="web_read")])
        runtime, other_runtime = current_path.parents[1], other_path.parents[1]
        (runtime / "latest.json").write_text(json.dumps({"attempt_id": "current"}))
        (other_runtime / "latest.json").write_text(json.dumps({"attempt_id": "other"}))
        (other_runtime / "execution.lock").write_text("")
        with (runtime / "execution.lock").open("w+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            value = exporter.export_job(self.root, task_id="test", active=True)
            self.assertEqual([row["status"] for row in value["attempts"]], ["unknown", "running", "unknown"])
            self.assertEqual([row["status"] for row in value["timeline"]], ["unconfirmed", "running", "unconfirmed"])
            # Without the job lock, even a separately held action lock is not
            # evidence of an active workflow invocation.
            inactive = exporter.export_job(self.root, task_id="test")
            self.assertTrue(all(row["status"] == "unknown" for row in inactive["attempts"]))
        after = exporter.export_job(self.root, task_id="test", active=True)
        self.assertTrue(all(row["status"] == "unknown" for row in after["attempts"]))

    @unittest.skipIf(fcntl is None, '此用例专测 Unix flock')
    def test_managed_start_before_session_creation_keeps_attempt_identity(self):
        record = self.managed_record("starting")
        record.update(status="running")
        record.pop("session_id")
        record.pop("finished_at")
        path = self.attempt("starting", record)
        runtime = path.parents[1]
        (runtime / "latest.json").write_text(json.dumps({"attempt_id": "starting"}))
        with (runtime / "execution.lock").open("w+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Native startup writes this before adding session_id to the
            # execution record. This valid intermediate snapshot must load.
            (path / "events.json").write_text("[]")
            starting = exporter.export_job(self.root, task_id="test", active=True)
            self.assertEqual(starting["timeline"], [])
            self.assertEqual(starting["attempts"][0]["status"], "running")
            (path / "events.json").write_text(json.dumps([event(1, "session.status_running")]))
            awaiting_identity = exporter.export_job(self.root, task_id="test", active=True)
            self.assertEqual(awaiting_identity["timeline"], [])
            self.assertEqual(awaiting_identity["attempts"], starting["attempts"])
            record["session_id"] = "PRIVATE_SESSION_ID"
            (path / "execution.json").write_text(json.dumps(record))
            running = exporter.export_job(self.root, task_id="test", active=True)
        self.assertEqual(starting["attempts"][0]["id"], running["attempts"][0]["id"])
        self.assertEqual(starting["attempts"][0]["turnId"], running["attempts"][0]["turnId"])
        self.assertEqual(running["timeline"][0]["turnId"], running["attempts"][0]["turnId"])
        self.assertEqual(running["timeline"][0]["attemptId"], running["attempts"][0]["id"])
        self.assertNotIn("PRIVATE_SESSION_ID", json.dumps(running))

    def test_session_creation_failure_without_session_preserves_other_attempts(self):
        failed = self.managed_record("no-session")
        failed.pop("session_id")
        failed.update(status="failed", error={"code": "managed_network_error", "message": "PRIVATE"})
        self.attempt("no-session", failed)
        self.attempt("completed", self.managed_record("completed", minute=1), [event(1, "session.status_running")])
        value = exporter.export_job(self.root, task_id="test")
        self.assertEqual(len(value["attempts"]), 2)
        self.assertEqual(value["attempts"][0]["status"], "failed")
        self.assertEqual(value["attempts"][0]["diagnosticCode"], "network_error")
        self.assertEqual(len(value["timeline"]), 1)
        self.assertNotIn("PRIVATE", json.dumps(value))


if __name__ == "__main__":
    unittest.main()

class ConversationProjectionTests(unittest.TestCase):
    def test_only_fact_based_business_summaries_cross_boundary(self):
        record = fixture_record(attempt_id="one", started_at="2026-10-03T01:00:00Z", status="succeeded", finished_at="2026-10-03T01:01:00Z", action="article_blueprint")
        events = [event(1,"agent.thinking",content="PRIVATE_REASONING"),
                  event(2,"agent.custom_tool_use",name="read_material",input={"artifact_id":"PRIVATE_PATH"}),
                  event(3,"user.custom_tool_result",custom_tool_use_id="fixture-2",is_error=False,content=[{"text":"PRIVATE_BODY"}])]
        rows = exporter.project_attempt(record,events,task_id="test")
        attempt = exporter._attempt_summary(record,Path('/private/tmp/absent/execution.json'),active=False)
        attempt["thinking"] = exporter.project_thinking(record, events, rows)
        projected = exporter.conversation_projection({"attempts":[attempt],"timeline":rows})
        text = json.dumps(projected,ensure_ascii=False)
        self.assertNotIn("PRIVATE",text)
        self.assertNotIn("read_material",text)
        self.assertNotIn("operation",text)
        self.assertEqual(projected[0]["thinking"],[])
        self.assertIn("已完成读取登记材料。",text)
        self.assertEqual(projected[0]['status'],'completed')

    def test_no_session_or_tool_events_does_not_invent_reasoning(self):
        attempt={"id":"attempt-one","action":"article_draft","status":"running","startedAt":100}
        projection=exporter.conversation_projection({"attempts":[attempt],"timeline":[]})[0]
        self.assertEqual(len(projection['thinking']),0)
        self.assertEqual(projection['tools'],[])
        attempt['toolSummaries']=[{"id":"word-count","text":"已完成检查文章字数。","status":"completed","sequence":0}]
        projection=exporter.conversation_projection({"attempts":[attempt],"timeline":[]})[0]
        self.assertEqual(len(projection['tools']),1)
        self.assertNotIn('finishedAt',projection['tools'][0])

    def test_specific_new_error_is_distinct_from_generic_historical_error(self):
        for code in ['material_reference_missing','non_public_address','deterministic_tool_repeat','tool_request_rejected']:
            rows=exporter.project_attempt(fixture_record(attempt_id='one'),[
                event(1,'agent.custom_tool_use',name='read_material'),
                event(2,'user.custom_tool_result',custom_tool_use_id='fixture-1',is_error=True,content=[{'text':json.dumps({'error':code,'message':'PRIVATE_DIAGNOSTIC'})}])],task_id='test')
            projection=exporter.conversation_projection({'attempts':[{'id':rows[0]['attemptId'],'action':'article_blueprint','status':'failed','startedAt':100}], 'timeline':rows})[0]
            self.assertEqual(projection['tools'][0]['status'],'failed')
            self.assertNotIn('PRIVATE',json.dumps(projection))
            if code=='tool_request_rejected':self.assertIn('未保存具体原因',projection['tools'][0]['reason'])

    def test_raw_thinking_events_do_not_create_template_or_unverified_summaries(self):
        record=fixture_record(action="article_blueprint")
        events=[event(1,'agent.thinking',content='PRIVATE_THOUGHT',publicSummary='UNVERIFIED_SUMMARY'),event(2,'agent.custom_tool_use',name='read_material',input={'artifact_id':'PRIVATE_ID'}),event(3,'user.custom_tool_result',custom_tool_use_id='fixture-2',is_error=False,content=[{'text':'PRIVATE_BODY'}]),event(4,'agent.thinking',content='PRIVATE_THOUGHT')]
        rows=exporter.project_attempt(record,events,task_id='test')
        summaries=exporter.project_thinking(record,[*reversed(events),events[0]],rows)
        self.assertEqual(summaries,[])
        self.assertEqual(summaries,exporter.project_thinking(record,events,rows))
        self.assertNotIn('PRIVATE',json.dumps(summaries))
        self.assertNotIn('UNVERIFIED',json.dumps(summaries))

class DocumentCompletenessProjectionTests(unittest.TestCase):
    def test_native_text_extraction_retains_pending_images_after_model_summary(self):
        from unittest.mock import patch
        evidence = {"call": {"call_id":"synthetic-extract", "name":"extract_document"}, "receipt": {"status":"completed", "output":{"complete":False,"image_text_status":"not_extracted"}}, "sequence":1, "timestamp":None}
        with patch.object(exporter, "sdk_tool_records", return_value=[evidence]):
            rows = exporter.sdk_tool_summaries(Path("/synthetic/execution.json"), "attempt", active=False)
        model={"id":rows[0]["id"],"kind":"tool","text":"已取得文档全部原生文字。","revision":4}
        process=exporter.conversation_projection({"attempts":[{"id":"attempt","action":"positioning_market_research","status":"succeeded","startedAt":1,"toolSummaries":rows,"modelSummaries":[model]}]})[0]
        self.assertEqual(process["tools"][0]["status"],"completed")
        self.assertEqual(process["tools"][0]["text"], model["text"])
        self.assertTrue(process["tools"][0]["pendingImageText"])
