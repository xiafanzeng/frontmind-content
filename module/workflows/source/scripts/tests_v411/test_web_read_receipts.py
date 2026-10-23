"""Known source rejection is feedback; ambiguous supplier outcomes stay closed."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.example_acquisition import AcquisitionError
from shared.host_tools import HostTools, ToolError, ToolOutcomeUnknown


class WebReadReceiptTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        path = Path(root.name)
        package, job = path / 'package', path / 'job'
        package.mkdir(); job.mkdir(); (job / 'inputs').mkdir()
        self.tools = HostTools(package, job, 'positioning_market_research')

    def test_known_read_failure_is_model_visible_feedback(self):
        with patch.object(self.tools.store, 'acquire_reader', side_effect=AcquisitionError('public egress validation failed')):
            with self.assertRaises(ToolError) as error:
                self.tools.execute('web_read', {'url': 'https://example.com', 'method': 'reader'})
        self.assertFalse(getattr(error.exception, 'outcome_unknown', False))
        self.assertIn('Web source unavailable', str(error.exception))

    def test_unknown_paid_reader_outcome_still_propagates_without_replay(self):
        ambiguous = ToolOutcomeUnknown('Reader transport failed after dispatch')
        with patch.object(self.tools.store, 'acquire_reader', side_effect=ambiguous) as reader:
            with self.assertRaises(ToolOutcomeUnknown) as error:
                self.tools.execute('web_read', {'url': 'https://example.com', 'method': 'reader'})
        self.assertIs(error.exception, ambiguous)
        self.assertEqual(reader.call_count, 1)

    def test_explicit_http_failure_does_not_switch_to_a_paid_reader(self):
        with patch.object(self.tools.store, 'acquire_http', side_effect=AcquisitionError('HTTP unavailable')), patch.object(self.tools.store, 'acquire_reader') as reader:
            with self.assertRaises(ToolError):
                self.tools.execute('web_read', {'url': 'https://example.com', 'method': 'http'})
        reader.assert_not_called()
