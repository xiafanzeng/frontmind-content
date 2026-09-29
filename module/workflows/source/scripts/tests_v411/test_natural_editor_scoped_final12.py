"""New scoped P0 runner routes through the same one-comment/one-repair chain."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf, rewrite_p0_live as runner
from shared import model_runtime as rt, natural_editor as ne
from scripts.tests_v411.test_reader_editing_v4127 import BODY


class NaturalScopedTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.source=self.root/'source.md';self.source.write_text(BODY)
        self.job=self.root/'job';self.requirements='保留事实，完成自然企业专题。'
        runner.prepare(self.source,'合成企业',self.job,self.requirements)
        state=wf.load_state(self.job);state['flags']['offline_fixture']=True;wf.save_state(self.job,state)
        self.counts=Counter();self.comments=False;self.fail_titles=False
        self.final=BODY+'\n\n本段仅区别这份模拟返工结果。'
        self.prompts={}

    def fake(self,package,job,action,prompt,validator,**kwargs):
        self.prompts[action]=prompt
        path=wf.action_paths(job,action)[2]
        if path.exists():return validator(wf.read_json(path))
        if action=='p0_titles' and self.fail_titles:
            self.fail_titles=False;raise OSError('offline title interruption')
        self.counts[action]+=1
        if action=='p0_blueprint':
            value=wf.fixture_blueprint(job,p0=True)
            value.update(article_brief='自然企业专题。',writing_material_markdown='合成企业提供相关业务。',writing_material_sources=['synthetic'])
        elif action=='p0_draft':value=dict(article_markdown=BODY,requires_blueprint_reconfirmation=False,reconfirmation_reason='')
        elif action=='p0_edit':value=dict(article_markdown=BODY,edit_status='accepted',editorial_notes=[],requires_blueprint_reconfirmation=False,reconfirmation_reason='')
        elif action=='p0_style':value=rt.parse_writer_content(action,prompt,BODY)
        elif action=='p0_finalize':value={'needs_revision':self.comments,'comments':['调整收尾。'] if self.comments else []}
        elif action=='p0_repair':value={'article_markdown':self.final}
        elif action=='p0_titles':value=wf.fixture_titles(job,p0=True)
        elif action=='p0_title_review':
            value=wf.read_json(job/'production/p0_titles.json');value.update(outcome='accepted',title_notes=[],reason='')
        else:raise AssertionError(action)
        value=validator(value);wf.atomic_json(path,value);return value

    def run_scoped(self):
        with patch.object(rt,'run_action',side_effect=self.fake):
            return runner.run(self.source,'合成企业',self.job,self.requirements)

    def test_new_scoped_no_comments_keeps_third_pass_exactly(self):
        report=self.run_scoped()
        self.assertTrue(report['article_generated'],report)
        self.assertEqual(wf.read_json(self.job/'production/p0_finalized.json')['article_markdown'],BODY)
        self.assertNotIn('p0_repair',self.counts)
        self.assertEqual(wf.read_json(self.job/'production/p0_final_source.json')['action'],'p0_style')
        for action,prompt in self.prompts.items():self.assertTrue(ne.matches(prompt),action)

    def test_one_scoped_repair_and_resume_reuse_saved_results(self):
        self.comments=True;self.fail_titles=True
        first=self.run_scoped();self.assertFalse(first['article_generated'])
        self.assertEqual(self.counts['p0_finalize'],1);self.assertEqual(self.counts['p0_repair'],1)
        second=self.run_scoped();self.assertTrue(second['article_generated'],second)
        self.assertEqual(self.counts['p0_finalize'],1);self.assertEqual(self.counts['p0_repair'],1)
        self.assertIn('本段仅区别这份模拟返工结果。',self.prompts['p0_titles'])
        self.assertEqual(wf.read_json(self.job/'production/p0_finalized.json')['article_markdown'],self.final)
        self.assertEqual(wf.read_json(self.job/'production/p0_styled.json')['article_markdown'],BODY)
        self.assertEqual(wf.read_json(self.job/'production/p0_final_source.json')['action'],'p0_repair')
        self.assertNotEqual((self.job/'deliverables/article.md').read_text(),BODY)

if __name__=='__main__':unittest.main()
