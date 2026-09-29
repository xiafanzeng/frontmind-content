"""Offline Job backup, reconciliation and parallel-runtime behavior."""
import json, tempfile, unittest, zipfile, stat
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from shared import agents_runtime as ar, model_runtime as rt
from scripts import agents_sessions as sessions
from scripts import probe_live_apis as probe
from scripts.tests_v411.agents_sdk_fake import bundle
from scripts.tests_v411.test_agents_runtime_v4130 import CountingTools
from scripts.tests_v411.test_model_runtime import FakeTools, valid

class AgentsSessionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.pkg=self.root/'pkg';self.pkg.mkdir();self.job=self.root/'job';self.job.mkdir()
    def runit(self,sdk,tools=None,retry=False,job=None):
        return rt.run_action(self.pkg,job or self.job,'p0_blueprint','current task',valid,retry=retry,host_tools=tools or FakeTools(),transport=sdk,offline=True)
    def test_inspect_never_networks_or_expires(self):
        sdk,e=bundle();self.runit(sdk);n=e.calls
        info=sessions.inspect_job(self.job)
        self.assertFalse(info['automatic_expiry']);self.assertFalse(info['remote_resource_mutation'])
        self.assertEqual(info['actions'][0]['status'],'succeeded');self.assertEqual(n,e.calls)
    def test_backup_preserves_full_history_and_uses_private_mode(self):
        sdk,e=bundle();self.runit(sdk);target=self.root/'backup.zip'
        self.assertEqual(sessions.main(['--job-dir',str(self.job),'backup','--output',str(target)]),0)
        with zipfile.ZipFile(target) as z:
            self.assertTrue(any(x.endswith('session.sqlite3') for x in z.namelist()))
            for name in z.namelist():
                self.assertEqual(z.read(name),(self.job/Path(name).relative_to('job')).read_bytes())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
    def test_backup_rejects_inside_job_and_overwrite(self):
        with self.assertRaises(ValueError):sessions.backup(self.job,self.job/'backup.zip')
        target=self.root/'old.zip';target.write_bytes(b'old')
        with self.assertRaises(ValueError):sessions.backup(self.job,target)
        self.assertEqual(target.read_bytes(),b'old')
    def test_backup_does_not_follow_symlink(self):
        (self.root/'private').write_text('private');(self.job/'link').symlink_to(self.root/'private')
        with self.assertRaises(ValueError):sessions.backup(self.job,self.root/'backup.zip')
    def test_reconcile_unknown_read_then_resume_explicitly(self):
        sdk,e=bundle()
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk,CountingTools(fail_after=True))
        count=e.calls
        with self.assertRaises(ValueError):sessions.reconcile(self.job,'p0_blueprint','read_material_1','checked',False)
        report=sessions.reconcile(self.job,'p0_blueprint','read_material_1','已核对，可以再次读取',True)
        self.assertEqual(report['status'],'retry_authorized_not_executed');self.assertEqual(e.calls,count)
        t=CountingTools();self.assertEqual(self.runit(sdk,t,retry=True),{'ok':True});self.assertEqual(t.executions,1)
    def test_reconcile_cannot_replay_successful_submit(self):
        sdk,e=bundle();self.runit(sdk)
        with self.assertRaises(ValueError):sessions.reconcile(self.job,'p0_blueprint','submit_result_1','checked',True)
    def test_different_jobs_really_execute_in_parallel(self):
        jobs=[self.root/'one',self.root/'two']
        for j in jobs:j.mkdir()
        def run(j):
            sdk,e=bundle();result=self.runit(sdk,job=j);return result,e.calls
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(run,jobs)),[({'ok':True},3),({'ok':True},3)])  # read, submit, post-submit final turn
        self.assertNotEqual(rt.action_record(jobs[0],'p0_blueprint')['session_id'],rt.action_record(jobs[1],'p0_blueprint')['session_id'])
    def test_invalid_port_is_structured_configuration_error(self):
        (self.pkg/'config').mkdir();(self.pkg/'config/xty.json').write_text('{"base_url":"https://example.test:wrong/v1"}')
        with self.assertRaises(rt.ProviderActionError) as ex:ar.public_profile(self.pkg)
        self.assertEqual(ex.exception.code,'invalid_gateway_url')
    def test_local_provider_probe_no_requests(self):
        with patch.object(probe,'check_models') as x,patch.object(probe.managed,'ManagedClient') as z:
            self.assertEqual(probe.main([]),0);x.assert_not_called();z.assert_not_called()
    def test_default_live_probe_no_managed_resources(self):
        with patch.object(probe,'check_models',return_value={'status':'pass'}),patch.object(probe.managed,'ManagedClient') as z,patch.object(probe.urllib.request,'build_opener',side_effect=OSError('offline')):
            self.assertEqual(probe.main(['--live']),1);z.assert_not_called()

if __name__=='__main__':unittest.main()
