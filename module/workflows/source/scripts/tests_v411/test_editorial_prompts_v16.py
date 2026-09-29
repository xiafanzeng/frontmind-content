"""Validate v16 input boundaries and complete prose-stage routing."""
from unittest.mock import patch
from scripts.tests_v411.test_natural_prose_prompts_v15 import ProsePromptTests
from scripts import frontmind_workflow as wf
from shared import editorial_preparation as prep, writing_context, writing_context_v16 as prose, model_runtime


class EditorialPromptTests(ProsePromptTests):
    # Build the legacy fixture, explicitly attach the new preparation contract.
    def job(self, pattern='P02'):
        job = super().job(pattern)
        state = wf.load_state(job)
        state['metadata']['natural_prose_contract'] = prose.CONTRACT
        wf.save_state(job,state)
        prepared = prep.fixture()
        prepared.update(writing_material_markdown='CLEAN_MATERIAL 机构开展具体业务。',
                        blueprint_suggestions='EDITORIAL_SUGGESTION 从相关需求进入，再介绍代表业务。')
        prep.freeze(wf,job,prepared)
        bp = wf.read_json(job/'blueprints/article_blueprint.json')
        wf.atomic_json(job/'blueprints/article_blueprint.json',prep.bind_blueprint(job,bp))
        return job

    def test_both_patterns_use_the_new_writer_and_counter(self):
        job = self.job('P01')
        for pattern in ('P01','P02'):
            state=wf.load_state(job)
            state['selected_pattern_id']=pattern
            wf.save_state(job,state)
            with patch('shared.writing_context_v14.examples',return_value='STYLE_REFERENCE'):
                for action,builder in [('article_draft',writing_context.prompt_article),('article_edit',writing_context.prompt_edit)]:
                    prompt=builder(wf,job,p0=False)
                    self.assertTrue(prose.matches(prompt))
                    self.assertIn('CLEAN_MATERIAL',prompt)
                    self.assertIn('STYLE_REFERENCE',prompt)
                    self.assertNotIn('EDITORIAL_SUGGESTION',prompt)
                    self.assertNotIn('reference_cases',prompt)
                    self.assertNotIn('source_ref',prompt)
                    self.assertEqual(model_runtime._initial_messages(action,prompt)[0]['content'],prose.system(action,prompt))

    def test_copy_editor_reads_only_current_body_and_commission(self):
        job=self.job()
        prompt=writing_context.prompt_finalize(wf,job,p0=False)
        self.assertTrue(prose.matches(prompt))
        self.assertIn(self.body,prompt)
        for excluded in ('CLEAN_MATERIAL','EDITORIAL_SUGGESTION','BLUEPRINT_ONLY','reference_cases'):
            self.assertNotIn(excluded,prompt)

    def test_final_polish_reads_the_repaired_manuscript(self):
        job=self.job()
        wf.atomic_json(job/'production/article_repaired.json',{'article_markdown':'# 正文\n\nAFTER_REPAIR 新基稿。'})
        prompt=prose.prompt_finish(wf,job,after_repair=True)
        self.assertIn('AFTER_REPAIR',prompt)
        self.assertNotIn(self.body,prompt)

    def test_polish_focus_is_optional_bound_and_polish_only(self):
        from shared.natural_editor import digest
        job=self.job()
        repaired='# 正文\n\nAFTER_REPAIR 新基稿。'
        wf.atomic_json(job/'production/article_repaired.json',{'article_markdown':repaired})
        wf.atomic_json(job/'production/article_editorial_review.json',{'needs_revision':True,'comments':['REPAIR_COMMENT']})
        with patch('shared.writing_context_v14.examples',return_value='STYLE_REFERENCE'):
            builders=(prose.prompt_preparation,prose.prompt_blueprint,prose.prompt_article,
                      prose.prompt_edit,prose.prompt_finalize,prose.prompt_repair)
            originals=[builder(wf,job) for builder in builders]
            original_polish=prose.prompt_finish(wf,job,after_repair=True)
            focus={'base_sha256':digest(repaired),'issues':['FOCUS_ONLY 核对词语搭配。']}
            state=wf.load_state(job)
            state['metadata']['article_polish_focus']=focus
            wf.save_state(job,state)
            with self.subTest('matching focus reaches polish only'):
                prompt=prose.prompt_finish(wf,job,after_repair=True)
                self.assertIn('FOCUS_ONLY',prompt)
                self.assertIn(repaired,prompt)
                self.assertIn(focus['base_sha256'],prompt)
                self.assertEqual([builder(wf,job) for builder in builders],originals)
            with self.subTest('stale focus fails explicitly'):
                wf.atomic_json(job/'production/article_repaired.json',{'article_markdown':repaired+' changed'})
                with self.assertRaisesRegex(ValueError,'基稿摘要'):
                    prose.prompt_finish(wf,job,after_repair=True)
                self.assertEqual(prose.prompt_finalize(wf,job),originals[4])
                wf.atomic_json(job/'production/article_repaired.json',{'article_markdown':repaired})
            with self.subTest('invalid focus fails explicitly'):
                state['metadata']['article_polish_focus']={'base_sha256':digest(repaired),'issues':[]}
                wf.save_state(job,state)
                with self.assertRaisesRegex(ValueError,'issues'):
                    prose.prompt_finish(wf,job,after_repair=True)
            with self.subTest('no focus leaves prompt unchanged'):
                state['metadata'].pop('article_polish_focus')
                wf.save_state(job,state)
                self.assertEqual(prose.prompt_finish(wf,job,after_repair=True),original_polish)

    def test_final_editors_distinguish_distributed_sentence_edits_without_widening_permissions(self):
        import copy
        from shared import language_editor_v15, writing_context_v15
        job=self.job()
        body='# 介绍\n\n## 第一节\n\n**甲机构**开展项目甲。重复尾句甲。\n\n## 第二节\n\n**乙机构**开展项目乙。重复尾句乙。'
        wf.atomic_json(job/'production/article_repaired.json',{'article_markdown':body})
        polish=prose.prompt_finish(wf,job,after_repair=True)
        schema=model_runtime.submit_tool_for('article_polish',prompt=polish)['function']['parameters']['properties']['result']
        baseline=language_editor_v15.review_schema()
        description=schema['properties']['needs_revision']['description']
        self.assertEqual(description,prose.POLISH_REVISION_SCOPE)
        self.assertIn(description,prose.system('article_polish',polish))
        unchanged=copy.deepcopy(schema)
        unchanged['properties']['needs_revision']['description']=baseline['properties']['needs_revision']['description']
        self.assertEqual(unchanged,baseline)
        final_prompt=prose.prompt_finalize(wf,job)
        final_schema=model_runtime.submit_tool_for('article_finalize',prompt=final_prompt)['function']['parameters']['properties']['result']
        self.assertEqual(final_schema,schema)
        for action,prompt in (
                ('article_polish',writing_context_v15.MARKER+'\nlegacy'),
                ('article_finalize',writing_context_v15.MARKER+'\nlegacy')):
            with self.subTest('other stages keep their schema',action=action,prompt=prompt[:45]):
                current=model_runtime.submit_tool_for(action,prompt=prompt)['function']['parameters']['properties']['result']
                self.assertEqual(current,baseline)
        self.assertIn(prose.POLISH_REVISION_SCOPE,prose.system('article_finalize'))
        local={'needs_revision':False,'comments':[], 'local_edits':[
            {'original':'重复尾句甲。','replacement':''},
            {'original':'重复尾句乙。','replacement':''}]}
        with self.subTest('distributed local edits preserve structure'):
            language_editor_v15.validate_review(local,body)
            after=language_editor_v15.apply_local_edits(body,local['local_edits'])
            self.assertIn('**甲机构**开展项目甲。',after)
            self.assertIn('**乙机构**开展项目乙。',after)
        with self.subTest('structural rejection remains available'):
            review={'needs_revision':True,'comments':['重点需重新分配并重组两个段落。'],'local_edits':[]}
            self.assertEqual(language_editor_v15.validate_review(review,body),review)
        for edit in (
                {'original':'## 第一节','replacement':'## 新标题'},
                {'original':'**甲机构**','replacement':'**其他主体**'},
                {'original':'重复尾句甲。','replacement':'新段。\n\n另起一段。'}):
            with self.subTest('structural edits remain prohibited',edit=edit):
                with self.assertRaises(ValueError):
                    language_editor_v15.validate_review({'needs_revision':False,'comments':[],'local_edits':[edit]},body)

    def test_frozen_jobs_and_other_patterns_do_not_opt_in(self):
        job=self.job();state=wf.load_state(job)
        for version in ('frontmind-natural-prose/15','frontmind-natural-prose/14'):
            state['metadata']['natural_prose_contract']=version
            wf.save_state(job,state)
            self.assertFalse(prose.matches(writing_context.prompt_article(wf,job,p0=False)))
        state['metadata']['natural_prose_contract']=prose.CONTRACT
        for pattern in ('P03','P04','P05','P06'):
            state['selected_pattern_id']=pattern
            self.assertFalse(prose.enabled(state))

    def test_preparation_suggestions_reach_blueprint_only(self):
        job=self.job()
        with patch('shared.writing_context_v14.examples',return_value='STYLE_REFERENCE'):
            prompt=writing_context.prompt_blueprint(wf,job,p0=False)
        self.assertTrue(prose.matches(prompt))
        self.assertIn('EDITORIAL_SUGGESTION',prompt)
        self.assertIn('CLEAN_MATERIAL',prompt)
        self.assertNotIn('offline_case_',prompt)
        self.assertNotIn('http',prompt)

    def test_downstream_outline_cannot_change_preparation_request(self):
        job=self.job()
        original=prose.prompt_preparation(wf,job)
        bp=wf.read_json(job/'blueprints/article_blueprint.json')
        bp.update(article_brief='DOWNSTREAM_ONLY',recommendation_relationships=[{'label':'new','subjects':['example']}])
        wf.atomic_json(job/'blueprints/article_blueprint.json',bp)
        self.assertEqual(prose.prompt_preparation(wf,job),original)

    def test_reference_commentary_cannot_rewrite_the_commission(self):
        job=self.job('P01')
        bp=wf.read_json(job/'blueprints/article_blueprint.json')
        bp['example_use']='HIDDEN_CONTENT_DIRECTION 以评估逻辑作为全文主线。'
        wf.atomic_json(job/'blueprints/article_blueprint.json',bp)
        with patch('shared.writing_context_v14._natural_examples',return_value='AGREED_REFERENCE_PROSE'):
            for builder in (prose.prompt_article,prose.prompt_edit):
                prompt=builder(wf,job)
                self.assertIn('AGREED_REFERENCE_PROSE',prompt)
                self.assertNotIn('HIDDEN_CONTENT_DIRECTION',prompt)
