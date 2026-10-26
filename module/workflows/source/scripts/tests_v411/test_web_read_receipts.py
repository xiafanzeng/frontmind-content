"""Known source rejection is feedback; ambiguous supplier outcomes stay closed."""
import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.example_acquisition import AcquisitionError
from shared.host_tools import HostTools, ToolError, ToolOutcomeUnknown
from shared import agents_runtime as ar


class WebReadReceiptTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        path = Path(root.name)
        package, job = path / 'package', path / 'job'
        package.mkdir(); job.mkdir(); (job / 'inputs').mkdir()
        self.root = path
        self.tools = HostTools(package, job, 'positioning_market_research')

    def test_known_read_failure_is_model_visible_feedback(self):
        with patch.object(self.tools.store, 'acquire_reader', side_effect=AcquisitionError('public egress validation failed')):
            with self.assertRaises(AcquisitionError) as error:
                self.tools.execute('web_read', {'url': 'https://example.com', 'method': 'reader'})
        self.assertFalse(getattr(error.exception, 'outcome_unknown', False))
        self.assertEqual(str(error.exception), 'public egress validation failed')

    def test_unknown_paid_reader_outcome_still_propagates_without_replay(self):
        ambiguous = ToolOutcomeUnknown('Reader transport failed after dispatch')
        with patch.object(self.tools.store, 'acquire_reader', side_effect=ambiguous) as reader:
            with self.assertRaises(ToolOutcomeUnknown) as error:
                self.tools.execute('web_read', {'url': 'https://example.com', 'method': 'reader'})
        self.assertIs(error.exception, ambiguous)
        self.assertEqual(reader.call_count, 1)

    def test_explicit_http_failure_does_not_switch_to_a_paid_reader(self):
        with patch.object(self.tools.store, 'acquire_http', side_effect=AcquisitionError('HTTP unavailable')), patch.object(self.tools.store, 'acquire_reader') as reader:
            with self.assertRaises(AcquisitionError):
                self.tools.execute('web_read', {'url': 'https://example.com', 'method': 'http'})
        reader.assert_not_called()

    def test_source_error_code_survives_receipt_replay_and_public_projection(self):
        script = Path(__file__).resolve().parents[3] / 'scripts/export-managed-timeline.py'
        spec = importlib.util.spec_from_file_location('web_read_timeline', script)
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)
        cases = [
            (AcquisitionError('public web egress validation failed (OSError)'),
             'source_acquisition_failed', '来源读取失败。'),
            (AcquisitionError('web URL resolves to a non-public address'),
             'non_public_address', '来源地址未通过公网校验。'),
            (ToolError('unknown webpage acquisition method'),
             'invalid_tool_arguments', '读取要求不符合约定。'),
        ]
        for number, (error, expected_code, expected_reason) in enumerate(cases):
            with self.subTest(code=expected_code):
                attempt = self.root / f'attempt-{number}'
                attempt.mkdir()
                arguments = json.dumps({'url': 'https://example.com', 'method': 'reader'})
                call = {'type': 'function_call', 'name': 'web_read',
                        'call_id': f'read-{number}', 'arguments': arguments}
                (attempt / 'model_0001_response.json').write_text(json.dumps({'output': [call]}))
                (attempt / 'request_plan.json').write_text(json.dumps({'instructions': 'test', 'input': []}))
                record = {'requested_configuration': {'max_tool_calls': 10}}
                journal = ar.ToolJournal(attempt, record, self.tools, lambda value: value, [])
                with patch.object(self.tools.store, 'acquire_reader', side_effect=error) as reader:
                    result = json.loads(asyncio.run(journal.invoke('web_read', call['call_id'], arguments)))
                    replay = json.loads(asyncio.run(journal.invoke('web_read', call['call_id'], arguments)))
                self.assertEqual(reader.call_count, 1)
                self.assertEqual(result['error'], expected_code)
                self.assertFalse(result['ok'])
                self.assertEqual(replay, result)
                receipt = json.loads(next(attempt.glob('tool_*.json')).read_text())
                self.assertEqual(receipt['status'], 'completed')
                self.assertEqual(receipt['output'], result)
                rows = exporter.sdk_tool_summaries(attempt / 'execution.json', 'attempt', active=False)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['status'], 'failed')
                self.assertEqual(rows[0]['reason'], expected_reason)
