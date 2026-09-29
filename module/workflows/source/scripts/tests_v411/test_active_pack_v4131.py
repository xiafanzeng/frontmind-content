import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from shared.host_tools import HostTools
from shared.question_bank_import import monitoring_exclusions, business_registry_view

class ActivePackTests(unittest.TestCase):
    def test_host_reads_current_binding_not_stale_conventional_input(self):
        with tempfile.TemporaryDirectory() as t:
            # Resolve the macOS /var -> /private/var symlink: HostTools resolves
            # job_root, and the recorded binding must stay in the same form.
            root=Path(t).resolve(); job=root/'job'; job.mkdir()
            old=job/'00_input/reference_pack'; new=job/'00_input/reference_pack_r2_changed'
            for p,text in ((old,'STALE_TEXT'),(new,'CURRENT_TEXT')):
                (p/'materials').mkdir(parents=True);(p/'materials/facts.md').write_text(text)
            (job/'job_state.json').write_text(json.dumps({'reference_pack':{'path':str(new)}}))
            tools=HostTools(root,job,'p0_blueprint')
            self.assertEqual(1,tools.execute('search_materials',{'query':'CURRENT_TEXT'})['total_matches'])
            self.assertEqual(0,tools.execute('search_materials',{'query':'STALE_TEXT'})['total_matches'])

    def test_legacy_export_materials_projected_out_without_deleting_archive(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve(); job=root/'job'; job.mkdir();pack=job/'00_input/reference_pack'
            for folder in ('materials','registries','research/question_research'):(pack/folder).mkdir(parents=True,exist_ok=True)
            digest='sha256:'+'a'*64;sid='src_'+'a'*16
            index={'monitoring_imports':[{'source_sha256':digest}]}
            material={'items':[{'path':'materials/old_export.json','source_sha256':digest}]}
            claims={'claims':[{'claim_id':'c1','source_ids':[sid],'claim_text':'AI_NOT_A_BUSINESS_FACT'},
                              {'claim_id':'c2','source_ids':['own'],'claim_text':'ACTUAL_SOURCE_FACT'}]}
            for name,obj in [('research/question_research/index.json',index),('materials/index.json',material),('registries/claim_registry.json',claims)]:
                (pack/name).write_text(json.dumps(obj))
            (pack/'materials/old_export.json').write_text(json.dumps({'answer':'AI_NOT_A_BUSINESS_FACT'}))
            (job/'job_state.json').write_text(json.dumps({'reference_pack':{'path':str(pack)}}))
            before=(pack/'registries/claim_registry.json').read_bytes()
            tools=HostTools(root,job,'p0_blueprint')
            self.assertEqual(0,tools.execute('search_materials',{'query':'AI_NOT_A_BUSINESS_FACT'})['total_matches'])
            self.assertEqual(1,tools.execute('search_materials',{'query':'ACTUAL_SOURCE_FACT'})['total_matches'])
            self.assertEqual(before,(pack/'registries/claim_registry.json').read_bytes())

if __name__=='__main__':unittest.main()
