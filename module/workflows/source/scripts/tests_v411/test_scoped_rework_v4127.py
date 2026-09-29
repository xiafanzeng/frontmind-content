"""Scoped runner repair checks: synthetic responses, no external services."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import frontmind_workflow as wf, rewrite_p0_live as runner
from shared import model_runtime as rt, p0_rework as rw
from scripts.tests_v411.test_reader_editing_v4127 import BAD, CLEAN, REASON

class ScopedReworkTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.source=Path(tmp.name)/'source.md'; self.source.write_text(BAD,encoding='utf-8')
        self.job=Path(tmp.name)/'job'; self.brand='合成测试品牌'; self.requirements='只验证模拟流程，不代表成稿质量。'
        runner.prepare(self.source,self.brand,self.job,self.requirements)
        state=wf.load_state(self.job); state['metadata'].pop('writing_editor_contract',None); state['flags']['offline_fixture']=True; wf.save_state(self.job,state)
        self.reject=True; self.prompts={}

    def fake(self, package,job,action,prompt,validator,**kwargs):
        self.prompts[action]=prompt
        if action=='p0_blueprint':
            value=wf.fixture_blueprint(job,p0=True)
            value.update(writing_material_markdown='仅用于模拟接口测试的事实。',writing_material_sources=['synthetic'])
        elif action=='p0_draft': value=dict(article_markdown=BAD,requires_blueprint_reconfirmation=False,reconfirmation_reason='')
        elif action=='p0_edit':
            repaired=rw.current(wf,job,'edit') is not None
            value=dict(article_markdown=CLEAN if repaired else BAD,edit_status='revised' if repaired else 'accepted',editorial_notes=['删除测试中的内部说明。'] if repaired else [],requires_blueprint_reconfirmation=False,reconfirmation_reason='')
        elif action=='p0_style': value={'article_markdown':BAD if self.reject else CLEAN}
        elif action=='p0_finalize':
            value=dict(outcome='incomplete' if self.reject else 'accepted',article_markdown='' if self.reject else CLEAN,editorial_notes=[],reason=REASON if self.reject else '')
        elif action=='p0_titles': value=wf.fixture_titles(job,p0=True)
        elif action=='p0_title_review':
            value=wf.read_json(job/'production/p0_titles.json'); value.update(outcome='accepted',title_notes=[],reason='')
        else: raise AssertionError(action)
        result=validator(value)
        wf.atomic_json(wf.action_paths(job,action)[2],result) # Simulates runtime's saved response.
        return result

    def run_scoped(self, **kwargs):
        with patch.object(rt,'run_action',side_effect=self.fake):
            return runner.run(self.source,self.brand,self.job,self.requirements,**kwargs)

    def test_rejection_stores_state_required_for_explicit_repair(self):
        result=self.run_scoped()
        self.assertFalse(result['article_generated'])
        self.assertEqual(wf.load_state(self.job)['pending_action']['error']['code'],'host_incomplete')
        self.assertEqual(wf.load_state(self.job)['status'],'running_p0_production')
        self.assertEqual(wf.read_json(self.job/'provider/p0_finalize/result.json')['reason'],REASON)
        self.assertFalse((self.job/'deliverables/article.md').exists())

    def test_scoped_style_repair_exports_only_repaired_candidate(self):
        self.run_scoped(); self.reject=False
        result=self.run_scoped(rework='style')
        self.assertTrue(result['article_generated'],result)
        _sp = self.prompts['p0_style']
        self.assertIn('基稿开头两段已按返工规则删除', _sp)
        self.assertIn('## 合成业务', _sp); self.assertIn(REASON, _sp)
        self.assertNotIn(BAD.split('\n\n## ')[0], _sp)
        self.assertEqual(wf.read_json(self.job/'production/p0_finalized.json')['article_markdown'],CLEAN)
        self.assertEqual(wf.read_json(self.job/'production/p0_edited.json')['article_markdown'],BAD)
        self.assertIsNone(wf.load_state(self.job)['pending_action'])
        self.assertEqual(len(wf.load_state(self.job)['metadata']['p0_quality_rework_history']),1)

    def test_scoped_edit_repair_uses_new_e8_before_style(self):
        self.run_scoped(); self.reject=False
        result=self.run_scoped(rework='edit')
        self.assertTrue(result['article_generated'],result)
        self.assertIn(REASON,self.prompts['p0_edit']); self.assertIn(BAD,self.prompts['p0_edit'])
        self.assertIn(CLEAN,self.prompts['p0_style'])
        self.assertEqual(wf.read_json(self.job/'production/p0_edited.json')['article_markdown'],CLEAN)
        self.assertEqual(wf.read_json(self.job/'production/p0_draft.json')['article_markdown'],BAD)

    def test_scoped_repair_does_not_allow_mixed_retry(self):
        self.run_scoped()
        before=wf.load_state(self.job)
        result=self.run_scoped(retry=True,rework='style')
        self.assertFalse(result['article_generated']); self.assertIn('不能同时提交',result['message'])
        self.assertEqual(wf.load_state(self.job),before)

if __name__=='__main__': unittest.main()
