"""A single blueprint commission can carry both edits and actual supplements."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_editorial_mission_final13 as mission


class CombinedBlueprintMaterialsTests(unittest.TestCase):
    setUp = mission.EditorialMissionTests.setUp
    job = mission.EditorialMissionTests.job
    step = mission.EditorialMissionTests.step
    until = mission.EditorialMissionTests.until
    finish = mission.EditorialMissionTests.finish

    def commission(self, *, p0, completed):
        kind='p0' if p0 else 'article'
        job=self.job(kind)
        if completed:
            self.finish(job,p0=p0)
        else:
            state=wf.load_state(job)
            state['status']='awaiting_p0_blueprint_confirmation' if p0 else 'awaiting_blueprint_confirmation'
            wf.save_state(job,state)
        before=(job/'job_state.json').read_bytes()
        supplement=self.root/'new-facts';supplement.mkdir()
        (supplement/'writing_materials.json').write_text(json.dumps({'writing_material_markdown':'NEW_FACT_BODY'},ensure_ascii=False))
        book=Workbook();book.active.append(['NEW_SPREADSHEET_DETAIL','new business']);book.save(supplement/'new-service.xlsx')
        edits=self.root/'new-blueprint.md';edits.write_text('NEW_EXPLICIT_BLUEPRINT_COMMISSION')
        edit_flag='--p0-blueprint-edits' if p0 else '--blueprint-edits'
        supplement_flag='--p0-blueprint-supplement' if p0 else '--blueprint-supplement'
        args=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(wf.load_state(job)['revision']),
                                    edit_flag,str(edits),supplement_flag,str(supplement)])
        with patch.object(wf,'drive',return_value=0):
            wf.continue_workflow(args)
        state=wf.load_state(job)
        self.assertEqual(state['status'],'running_'+kind+'_blueprint')
        self.assertEqual(state['decisions']['blueprint_edits'],'NEW_EXPLICIT_BLUEPRINT_COMMISSION')
        entries=wf.read_json(job/'inputs/user_materials/index.json')['items']
        self.assertEqual(len(entries),2)
        self.assertEqual((job/next(x['path'] for x in entries if x['path'].endswith('writing_materials.json'))).read_text(),
                         (supplement/'writing_materials.json').read_text())
        rows=json.loads(wf.user_material_index(job,'p0' if p0 else 'question'))
        readable=next(x for x in rows if x['name'].endswith('.readable.md'))
        self.assertIn('NEW_SPREADSHEET_DETAIL',(job/readable['path']).read_text())
        prompt=wf.prompt_blueprint(job,p0=p0)
        self.assertIn('NEW_EXPLICIT_BLUEPRINT_COMMISSION',prompt)
        self.assertIn(readable['path'],prompt)
        self.assertNotIn('NEW_SPREADSHEET_DETAIL',prompt)
        self.assertNotIn('NEW_FACT_BODY',prompt)
        if completed:
            snapshot=Path(state['metadata']['writing_reruns'][-1]['archive_path'])
            self.assertEqual((snapshot/'job_state.json').read_bytes(),before)
            self.assertFalse((snapshot/'inputs/user_materials/index.json').exists())

    def test_article_pause_registers_supplement_before_building_index(self):
        self.commission(p0=False,completed=False)

    def test_p0_pause_registers_supplement_before_building_index(self):
        self.commission(p0=True,completed=False)

    def test_completed_article_snapshots_then_loads_new_supplement(self):
        self.commission(p0=False,completed=True)

    def test_completed_p0_snapshots_then_loads_new_supplement(self):
        self.commission(p0=True,completed=True)


if __name__ == '__main__':
    unittest.main()
