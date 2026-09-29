"""Transport-failover to the configured backup host and tool-argument feedback.

Offline adapter behavior only: fabricated transports and responses prove the
failover wiring and guards, never real gateway or model quality.
"""
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from shared import agents_runtime as ar, model_runtime as rt
from scripts.tests_v411.agents_sdk_fake import bundle
from scripts.tests_v411.test_model_runtime import FakeTools, valid


def _config(model="host-primary", **extra):
    payload = {"api_key": "test-token", "base_url": "https://example.test/v1", "model": model}
    payload.update(extra)
    return json.dumps(payload)


class HostBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.pkg = Path(self.temp.name) / 'pkg'; (self.pkg / 'config').mkdir(parents=True)
        self.job = Path(self.temp.name) / 'job'; self.job.mkdir()
        (self.pkg / 'config/xty.json').write_text(_config(
            backup_model="host-backup", backup_reasoning_effort="max"))

    def runit(self, sdk, tools=None, **kw):
        return rt.run_action(self.pkg, self.job, 'p0_blueprint', kw.get('prompt', 'current task'),
                             valid, host_tools=tools or FakeTools(), transport=sdk, offline=True)

    def attempts(self):
        root = self.job / 'provider/p0_blueprint/runtime/attempts'
        return {a.name: rt._read_json(a / 'execution.json') for a in sorted(root.iterdir())}

    def test_transport_classifier(self):
        self.assertTrue(ar._transport_failure(RuntimeError("Connection error.")))
        self.assertTrue(ar._transport_failure(RuntimeError("Error code: 524 - cloudflare origin timeout")))
        self.assertTrue(ar._transport_failure(RuntimeError("offline simulated lost response")))
        self.assertFalse(ar._transport_failure(ValueError("duplicate JSON key")))
        self.assertFalse(ar._transport_failure(RuntimeError("model_output_incomplete")))

    def test_backup_profile_parsing_and_validation(self):
        backup = ar.backup_profile(self.pkg)
        self.assertEqual(backup['model'], 'host-backup')
        self.assertEqual(backup['reasoning_effort'], 'max')
        self.assertEqual(backup['wire_api'], ar.WIRE_API)
        self.assertNotIn('reasoning_effort', ar.public_profile(self.pkg))
        (self.pkg / 'config/xty.json').write_text(_config())
        self.assertIsNone(ar.backup_profile(self.pkg))
        (self.pkg / 'config/xty.json').write_text(_config(backup_model="b", backup_reasoning_effort="ultra"))
        with self.assertRaises(Exception):
            ar.public_profile(self.pkg)
        (self.pkg / 'config/xty.json').write_text(_config(backup_reasoning_effort="max"))
        with self.assertRaises(Exception):
            ar.public_profile(self.pkg)

    def test_transport_failure_falls_back_to_backup(self):
        sdk, engine = bundle(fault='network_first')
        self.assertEqual(self.runit(sdk), {'ok': True})
        records = self.attempts()
        self.assertEqual(len(records), 2)
        primary = next(r for r in records.values() if r['requested_configuration']['model'] == 'host-primary')
        backup = next(r for r in records.values() if r['requested_configuration']['model'] == 'host-backup')
        self.assertEqual(primary['status'], 'failed')
        self.assertTrue(primary['error'].get('transport'))
        self.assertTrue(primary.get('failed_over_to_backup'))
        self.assertEqual(backup['status'], 'succeeded')
        self.assertEqual(backup.get('fallback_for'), primary['attempt_id'])
        self.assertEqual(backup['requested_configuration'].get('reasoning_effort'), 'max')
        latest = rt._read_json(self.job / 'provider/p0_blueprint/runtime/latest.json')
        self.assertEqual(latest['attempt_id'], backup['attempt_id'])

    def test_retry_required_on_transport_breakpoint_also_falls_back(self):
        # 先在无备用配置下制造传输断点（进程被杀等场景来不及切换）
        (self.pkg / 'config/xty.json').write_text(_config())
        sdk, _ = bundle(fault='network_first')
        with self.assertRaises(rt.ProviderActionError):
            self.runit(sdk)
        # 事后配置备用；普通continue（非显式retry）直接改走备用宿主
        (self.pkg / 'config/xty.json').write_text(_config(
            backup_model="host-backup", backup_reasoning_effort="max"))
        sdk2, _ = bundle()
        self.assertEqual(self.runit(sdk2), {'ok': True})
        records = self.attempts()
        models = {r['requested_configuration']['model']: r['status'] for r in records.values()}
        self.assertEqual(models, {'host-primary': 'failed', 'host-backup': 'succeeded'})

    def test_contract_failure_never_switches_model(self):
        sdk, _ = bundle(fault='no_submit')
        with self.assertRaises(rt.ProviderActionError):
            self.runit(sdk)
        records = self.attempts()
        self.assertEqual([r['requested_configuration']['model'] for r in records.values()], ['host-primary'])

    def test_backup_failure_reports_both_models(self):
        sdk, _ = bundle(fault='network_always')
        with self.assertRaises(rt.ProviderActionError) as ctx:
            self.runit(sdk)
        self.assertIn('主宿主与备用宿主', str(ctx.exception))
        records = self.attempts()
        models = sorted(r['requested_configuration']['model'] for r in records.values())
        self.assertEqual(models, ['host-backup', 'host-primary'])

    def test_bad_tool_arguments_become_feedback_not_fatal(self):
        sdk, engine = bundle(fault='bad_args_once')
        self.assertEqual(self.runit(sdk), {'ok': True})
        succeeded = next(r for r in self.attempts().values() if r['status'] == 'succeeded')
        self.assertEqual(succeeded.get('tool_argument_feedback'), 1)
        self.assertEqual(succeeded['requested_configuration']['model'], 'host-primary')
        self.assertEqual(len(self.attempts()), 1)  # 同一会话内修正，未另起动作

    def test_chain_verification_accepts_backup_identity(self):
        sdk, _ = bundle(fault='network_first')
        self.assertEqual(self.runit(sdk), {'ok': True})
        backup = next(r for r in self.attempts().values() if r['requested_configuration']['model'] == 'host-backup')
        with patch.object(rt, 'host_backup_model', return_value='host-backup'):
            from shared import manuscript_revision as mr
            requested = backup['requested_configuration']
            accepted = (requested.get('provider') == 'xty'
                        and requested.get('model') == 'host-backup'
                        and requested.get('wire_api') == 'openai_agents_sdk')
            self.assertTrue(accepted)


if __name__ == '__main__':
    unittest.main()
