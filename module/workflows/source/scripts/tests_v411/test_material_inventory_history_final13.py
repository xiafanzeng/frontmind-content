"""Append supplemental inputs while retaining exactly what an older action read."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_natural_editor_flow_final12 as flow
from shared import manuscript_revision, material_inventory
from shared.host_tools import HostTools, ToolError


class InventoryHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job = self.root/'job'; self.job.mkdir()
        self.original = wf.save_user_material(self.job, 'Initial source fact.', 'question')[0]

    def host(self):
        return HostTools(self.root, self.job, 'article_blueprint')

    def consumed_state(self):
        host = self.host()
        host.execute('read_material', {'artifact_id': material_inventory.INDEX_PATH})
        host.execute('read_material', {'artifact_id': str(self.original)})
        return host.export_state(), (self.job/material_inventory.INDEX_PATH).read_bytes()

    def test_append_keeps_old_read_bytes_and_new_action_sees_new_inputs(self):
        saved, before = self.consumed_state()
        saved_json = json.dumps(saved, sort_keys=True)
        added = wf.save_user_material(self.job, 'New project mechanism.', 'question')[0]
        after = (self.job/material_inventory.INDEX_PATH).read_bytes()
        self.assertNotEqual(before, after)
        resumed = self.host(); resumed.restore_state(saved)
        result = resumed.execute('read_material', {'artifact_id': material_inventory.INDEX_PATH})
        self.assertEqual(result['text'].encode(), before)
        self.assertTrue(result['complete_read'])
        self.assertEqual(json.dumps(saved, sort_keys=True), saved_json)
        fresh = self.host()
        self.assertEqual(fresh.execute('read_material', {'artifact_id': material_inventory.INDEX_PATH})['text'].encode(), after)
        self.assertEqual(fresh.execute('read_material', {'artifact_id': str(added)})['text'], 'New project mechanism.\n')
        snapshot = self.job/material_inventory.SNAPSHOT_DIR/(hashlib.sha256(before).hexdigest()+'.json')
        self.assertEqual(snapshot.read_bytes(), before)
        self.original.write_text('Modified original fact.')
        with self.assertRaises(ToolError):
            self.host().restore_state(saved)

    def test_legacy_append_recovers_only_hash_identical_prefix(self):
        saved, before = self.consumed_state()
        # Reproduce the old controller which appended without preserving bytes.
        path = self.job/material_inventory.INDEX_PATH
        current = json.loads(before)
        current['items'].append({'path': 'inputs/new.md', 'kind': 'text', 'added_at': 'later'})
        (self.job/'inputs/new.md').write_text('New material.')
        wf.atomic_json(path, current)
        restored = self.host(); restored.restore_state(saved)
        self.assertEqual(restored.execute('read_material', {'artifact_id': material_inventory.INDEX_PATH})['text'].encode(), before)
        snapshot = material_inventory.historical_path(self.job, hashlib.sha256(before).hexdigest())
        self.assertEqual(snapshot.read_bytes(), before)
        snapshot.chmod(0o644); snapshot.write_text('Tampered snapshot')
        with self.assertRaises(ToolError):
            self.host().restore_state(saved)

    def test_changed_prior_item_cannot_be_reconstructed_from_current_catalog(self):
        saved, before = self.consumed_state()
        current = json.loads(before)
        current['items'][0]['path'] = 'inputs/another.md'
        current['items'].append({'path': 'inputs/new.md'})
        wf.atomic_json(self.job/material_inventory.INDEX_PATH, current)
        with self.assertRaises(ToolError):
            self.host().restore_state(saved)


class CompletedInventoryContinuationTests(unittest.TestCase):
    setUp = flow.NaturalEditorFlowTests.setUp
    job = flow.NaturalEditorFlowTests.job
    step = flow.NaturalEditorFlowTests.step
    until = flow.NaturalEditorFlowTests.until
    finish = flow.NaturalEditorFlowTests.finish

    def test_consumed_catalog_survives_completed_article_revision_and_keeps_old_base(self):
        job = self.job()
        state = wf.load_state(job)
        pack = Path(state['reference_pack']['path'])
        with zipfile.ZipFile(pack, 'w') as archive:
            archive.writestr('materials/facts.md', 'Synthetic reference facts.')
        state['reference_pack']['path'] = str(pack.resolve())
        wf.save_state(job, state)
        original = wf.save_user_material(job, 'Original factual input.', 'question')[0]
        self.until(job, 'finalize')
        # Use the real host reader, required manuscript coverage and saved state;
        # provider prose remains explicitly synthetic in this offline fixture.
        host = HostTools(self.root, job, 'article_finalize')
        host.execute('read_material', {'artifact_id': material_inventory.INDEX_PATH})
        host.execute('read_material', {'artifact_id': str(original)})
        for ident in list(host._required):
            host.execute('read_material', {'artifact_id': ident, 'limit': 24000})
        host.assert_required_reads_complete()
        saved = host.export_state()
        self.finish(job)
        wf.save_user_material(job, 'New mechanism supplied for this edit.', 'question')
        request = self.root/'edit.md'; request.write_text('沿用实际成稿，加入本轮提供的项目机制说明。')
        verify = manuscript_revision._verified_action
        def verify_with_historical_host(wf_arg, job_arg, action, production, validator, *, offline):
            if action == 'article_finalize':
                replay = HostTools(self.root, job_arg, action)
                replay.restore_state(saved)
                replay.assert_required_reads_complete()
            return verify(wf_arg, job_arg, action, production, validator, offline=offline)
        args = wf.parser().parse_args(['continue', '--job-dir', str(job), '--revision', str(wf.load_state(job)['revision']),
                                      '--manuscript-edits', str(request)])
        with patch.object(manuscript_revision, '_verified_action', side_effect=verify_with_historical_host), \
             patch.object(wf, 'drive', return_value=0) as drive:
            wf.continue_workflow(args)
            drive.assert_called_once()
        revision = manuscript_revision.current_revision(wf, job, p0=False)
        self.assertEqual(revision['base_markdown'], self.body)
        self.assertEqual(wf.load_state(job)['flags']['article_production_step'], 'edit')
        self.assertIn(request.read_text(), wf.prompt_edit(job, p0=False))
        original.write_text('Changed historical source')
        with self.assertRaises(ToolError):
            HostTools(self.root, job, 'article_finalize').restore_state(saved)


if __name__ == '__main__':
    unittest.main()
