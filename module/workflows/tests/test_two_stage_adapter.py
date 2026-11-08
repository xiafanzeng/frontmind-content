"""Real local adapter/engine commands; no provider calls or fake success records."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ENTRY=Path(__file__).resolve().parents[1]/'source/scripts/frontmind_v16251.py'


class TwoStageAdapter(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        knowledge=self.base/'knowledge.zip'
        with zipfile.ZipFile(knowledge,'w') as archive:
            archive.writestr('知识/品牌.md','# 合成品牌\n\n提供机构信息记录服务。')
        self.knowledge=knowledge.read_bytes()
        self.pack=self.base/'three_item.zip'
        with zipfile.ZipFile(self.pack,'w') as archive:
            # Windows-origin Markdown is a supported input, including CRLF.
            archive.writestr('Reference_Pack/定位.md','# 合成品牌 定位\r\n\r\n品牌：合成品牌\r\n别名：\r\n产品定位：机构信息记录服务\r\n\r\n## 本轮定位\r\n\r\n提供机构信息记录。\r\n\r\n## 优化问题目录\r\n\r\n### q000001\r\n\r\n问题：机构怎样保存记录？\r\n类型：产品场景\r\n')
            archive.writestr('Reference_Pack/核心差异化优势.md','# 核心差异化优势\n\n## 历史记录\n\n可查看历次记录。\n')
            archive.writestr('Reference_Pack/知识库.zip',self.knowledge)

    def command(self,*args,ok=True):
        environment={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'}
        environment.pop('FRONTMIND_CONTENT_PROVIDER_PROXY',None)
        result=subprocess.run([sys.executable,'-X','utf8',str(ENTRY),*map(str,args)],capture_output=True,text=True,encoding='utf-8',env=environment,timeout=30)
        if ok:self.assertEqual(result.returncode,0,result.stderr)
        return result

    def action(self,job,value,*files,ok=True):
        file=self.base/'action.json';file.write_text(json.dumps(value),encoding='utf-8')
        args=['continue','--job-dir',job,'--action-file',file]
        for item in files:args+=['--input',item]
        return self.command(*args,ok=ok)

    def test_import_pack_is_real_three_item_delivery_and_keeps_original_knowledge(self):
        job=self.base/'pack-job'
        result=self.command('start','--job-dir',job,'--task','import-reference-pack','--brand','合成品牌','--reference-pack',self.pack)
        state=json.loads(result.stdout)
        self.assertEqual(state['status'],'positioning_ready')
        self.assertEqual(state['schema_version'],'16.25.1')
        delivery=state['metadata']['reference_pack_delivery']
        self.assertTrue(delivery['positioning_confirmed'])
        self.assertTrue(delivery['advantages_confirmed'])
        self.assertFalse(delivery['readiness']['p0_ready'])
        output=Path(delivery['portable_zip_path'])
        self.assertEqual(delivery['portable_zip_sha256'],'sha256:'+hashlib.sha256(output.read_bytes()).hexdigest())
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()),{'Reference_Pack/定位.md','Reference_Pack/核心差异化优势.md','Reference_Pack/知识库.zip'})
            self.assertEqual(archive.read('Reference_Pack/知识库.zip'),self.knowledge)
        self.assertFalse(list(job.rglob('hosted_runs')))
        self.assertFalse(list(job.rglob('writer_runs')))

    def test_article_has_explicit_question_answer_source_and_mode_pauses_without_p0(self):
        job=self.base/'article-job'
        initial=json.loads(self.command('start','--job-dir',job,'--task','article','--brand','合成品牌','--reference-pack',self.pack).stdout)
        self.assertEqual(initial['status'],'awaiting_question_selection')
        self.assertIsNone(initial['p0_route'])
        before=(job/'job_state.json').read_bytes()
        rejected=self.action(job,{'kind':'choose_question','revision':0,'selection':'q000001'},ok=False)
        self.assertNotEqual(rejected.returncode,0)
        self.assertEqual(before,(job/'job_state.json').read_bytes())
        selected=json.loads(self.action(job,{'kind':'choose_question','revision':1,'selection':'q000001'}).stdout)
        self.assertEqual(selected['status'],'awaiting_question_answers')
        sources=json.loads(self.action(job,{'kind':'set_question_answers','revision':2,'noAnswers':True}).stdout)
        self.assertEqual(sources['status'],'awaiting_question_sources')
        source=self.base/'sources.json'
        source.write_text(json.dumps([
            {'问题':'机构怎样保存记录？','文章链接':'https://example.org/a','文章标题':'机构记录服务','媒体名称':'媒体甲','日期':'2026-11-08'},
            {'问题':'机构怎样保存记录？','文章链接':'https://example.net/b','文章标题':'历次记录的用途','媒体名称':'媒体乙','日期':'2026-11-08'},
        ],ensure_ascii=False),encoding='utf-8')
        mode=json.loads(self.action(job,{'kind':'provide_question_sources','revision':3},source).stdout)
        self.assertEqual(mode['status'],'awaiting_writing_selection')
        self.assertEqual(mode['revision'],4)
        self.assertTrue(any('P06' in value for value in mode['current_pause']['available_choices']))
        self.assertFalse(any('P05' in value for value in mode['current_pause']['available_choices']))
        review=Path(mode['current_pause']['review_markdown_path']).read_text(encoding='utf-8')
        self.assertIn('媒体甲',review);self.assertIn('Top2',review)
        self.assertFalse(list(job.rglob('hosted_runs')))
        self.assertFalse(list(job.rglob('writer_runs')))

    def test_wrong_brand_or_legacy_pack_cannot_be_relabelled(self):
        result=self.command('start','--job-dir',self.base/'wrong','--task','article','--brand','其他品牌','--reference-pack',self.pack,ok=False)
        self.assertNotEqual(result.returncode,0)
        legacy=self.base/'legacy.zip'
        with zipfile.ZipFile(legacy,'w') as archive:archive.writestr('reference_pack.json','{"schema_version":"4.1"}')
        result=self.command('start','--job-dir',self.base/'legacy-job','--task','article','--brand','合成品牌','--reference-pack',legacy,ok=False)
        self.assertNotEqual(result.returncode,0)

    def test_paused_and_delivered_resume_preserves_original_job_bytes(self):
        for task in ('article','import-reference-pack'):
            with self.subTest(task=task):
                job=self.base/task
                self.command('start','--job-dir',job,'--task',task,'--brand','合成品牌','--reference-pack',self.pack)
                before={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()}
                current=json.loads(before['job_state.json'])
                self.command('continue','--job-dir',job)
                self.action(job,{'kind':'resume_current_execution','revision':current['revision']})
                after={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*') if p.is_file()}
                self.assertEqual(before,after)

    def test_explicit_initial_question_and_answer_roles_are_reused(self):
        job=self.base/'explicit-question'
        answer=self.base/'complete-answer.json'
        answer.write_text(json.dumps([{'question':'机构怎样保存记录？','brand':'合成品牌','platform':'ChatGPT',
            'date':'2026-11-08','answer':'机构可以保存完整记录，按日期查询历次记录。'}],ensure_ascii=False),encoding='utf-8')
        request=self.base/'request.txt'
        request.write_text('请保留原始完整要求：面向机构管理人员。',encoding='utf-8')
        state=json.loads(self.command('start','--job-dir',job,'--task','article','--brand','合成品牌',
            '--reference-pack',self.pack,'--question-id','q000001','--answer',answer,'--request-file',request).stdout)
        self.assertEqual(state['status'],'awaiting_question_sources')
        self.assertEqual((job/'inputs/request.txt').read_text(encoding='utf-8'),request.read_text(encoding='utf-8'))
        self.assertFalse(list(job.rglob('hosted_runs')))


if __name__=='__main__':unittest.main()
