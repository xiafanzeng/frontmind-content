"""All seven genres, title-only continuation and frozen v2 payloads; offline."""
import copy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_title_input_scope_final13 as scope
from scripts.tests_v411.test_grouped_titles_v163 import titles, review
from shared import title_strategy as strategy, title_publication as publication
from shared import writing_context, writing_context_v14 as context, model_runtime, title_editorial_v168


class SevenGenreTitleTests(unittest.TestCase):
    setUp = scope.TitleInputScopeTests.setUp
    job = scope.TitleInputScopeTests.job
    step = scope.TitleInputScopeTests.step
    until = scope.TitleInputScopeTests.until
    finish = scope.TitleInputScopeTests.finish
    request_titles = scope.TitleInputScopeTests.request_titles
    retry = scope.TitleInputScopeTests.retry

    def test_new_jobs_and_seven_actual_title_routes_have_five_plus_five(self):
        base = self.root
        for pattern in ('P0', 'P01', 'P02', 'P03', 'P04', 'P05', 'P06'):
            with self.subTest(pattern=pattern):
                self.root = base/pattern; self.root.mkdir()
                p0 = pattern == 'P0'
                self.assertEqual(wf.make_state(pattern, 'p0' if p0 else 'article')['metadata']['title_strategy'], strategy.DEFAULT)
                job = self.job('p0' if p0 else 'article')
                state = wf.load_state(job)
                state['selected_pattern_id'] = 'P00' if p0 else pattern
                state['metadata']['title_strategy'] = dict(strategy.DEFAULT)
                wf.save_state(job, state)
                raw = wf.fixture_titles(job, p0=p0)
                for action, prompt in {
                    ('p0' if p0 else 'article')+'_titles': writing_context.prompt_titles(wf, job, p0=p0, final_markdown=self.body),
                    ('p0' if p0 else 'article')+'_title_review': writing_context.prompt_title_review(wf, job, p0=p0, final_markdown=self.body, title_result=raw),
                }.items():
                    self.assertEqual(strategy.request_policy(prompt), strategy.DEFAULT)
                    self.assertIn(publication.body_only(self.body), prompt)
                    self.assertNotIn('# 内部标题', prompt)
                    system = model_runtime._initial_messages(action, prompt)[0]['content']
                    self.assertIn(__import__("shared.title_editorial_v168", fromlist=["RULES"]).RULES, system)
                    self.assertNotIn('20个', system)
                    if action.endswith('_titles'):
                        wf.validate_action_result(job, action, raw)
                schema = model_runtime.submit_tool_for(('p0' if p0 else 'article')+'_title_review', prompt=prompt)['function']['parameters']['properties']['result']
                self.assertIn('style', schema['properties']['candidates']['items']['required'])
                self.assertEqual(tuple(row['style'] for row in raw['candidates']), strategy.STYLE_SEQUENCE)
                self.assertEqual(publication.validate_title_map(raw, p0=p0, expected_policy=strategy.DEFAULT)['total_count'], 10)

    def test_title_only_upgrade_and_retry_keep_every_body_artifact_exact(self):
        base = self.root
        for pattern in ('P0', 'P01', 'P02', 'P03', 'P04', 'P05', 'P06'):
            with self.subTest(pattern=pattern):
                self.root = base/pattern; self.root.mkdir()
                p0 = pattern == 'P0'; prefix = 'p0' if p0 else 'article'
                job = self.job(prefix)
                state = wf.load_state(job); state['selected_pattern_id'] = 'P00' if p0 else pattern
                wf.save_state(job, state); self.finish(job, p0=p0)
                before = {p.name:p.read_bytes() for p in (job/'production').glob('*.json') if 'title' not in p.name}
                old_delivery = Path(wf.load_state(job)['metadata']['delivery']['markdown']).read_bytes()
                prior_calls = len(self.actions)
                with ExitStack() as stack:
                    if p0:
                        # This fixture tests title continuation, not pack serialization.
                        # Real P0 regeneration separately exercises the pack writer.
                        pack = job/'synthetic-pack.zip'; pack.write_bytes(b'explicit offline pack fixture')
                        state = wf.load_state(job)
                        state['metadata']['reference_pack_delivery'] = {'portable_zip_path':str(pack), 'pack_version':1,
                            'portable_zip_sha256':'sha256:'+hashlib.sha256(pack.read_bytes()).hexdigest()}
                        wf.save_state(job,state)
                        stack.enter_context(patch.object(wf,'validate_reference_pack',return_value={'status':'pass','readiness':{'p0_ready':True}}))
                        stack.enter_context(patch.object(wf,'reference_pack_root',return_value={'pack_id':'offline-pack','pack_version':1}))
                        stack.enter_context(patch.object(wf,'read_reference_member',return_value=old_delivery))
                    self.request_titles(job, '改为5个正式标题和5个场景卖点标题，按当前体裁拟定，正文保持不变。')
                state = wf.load_state(job); frozen = copy.deepcopy(state['metadata'][prefix+'_title_revision'])
                self.assertEqual(frozen['title_strategy'], strategy.DEFAULT)
                prompt = writing_context.prompt_titles(wf, job, p0=p0)
                self.retry(job, prefix+'_titles')
                self.assertEqual(writing_context.prompt_titles(wf, job, p0=p0), prompt)
                self.assertEqual(wf.load_state(job)['metadata'][prefix+'_title_revision'], frozen)
                self.finish(job, p0=p0)
                self.assertEqual(self.actions[prior_calls:], [prefix+'_titles', prefix+'_title_review'])
                self.assertEqual(before, {p.name:p.read_bytes() for p in (job/'production').glob('*.json') if 'title' not in p.name})
                delivery = wf.load_state(job)['metadata']['delivery']
                self.assertEqual(Path(delivery['markdown']).read_bytes(), old_delivery)
                title_map = wf.read_json(Path(delivery['title_map']))
                self.assertEqual(title_map['title_strategy'], strategy.DEFAULT)
                self.assertEqual(publication.validate_title_map(title_map, p0=p0), title_map)
                for field in ('title_options', 'title_options_html'):
                    rendered = Path(delivery[field]).read_text()
                    self.assertIn('正式标题', rendered); self.assertIn('场景卖点', rendered)


class FrozenV2Tests(unittest.TestCase):
    def test_v2_actual_prompt_system_and_tool_schema_match_v166_baseline(self):
        # Captured from the complete v16.6 baseline before any v16.7 changes.
        expected = {'article_titles':'6098eb9c2ba5ed705cd703278f8b56be14fd8f9661718dbfa6232c8c5a4f7ccb',
                    'article_title_review':'403503d67e0f934688e66f3ce215e86cb152a84d8167608c91f3f518b5d4e0e1'}
        state = {'job_kind':'article','selected_pattern_id':'P01','metadata':{'title_strategy':dict(strategy.V2_POLICY)}}
        fake = SimpleNamespace(load_state=lambda _:state)
        raw = {'candidates':[{'title':f'推荐标题{i}','angle':'同题','style':'formal' if i<=5 else 'scenario'} for i in range(1,11)], 'canonical_title_id':'title_07'}
        with patch.object(context, 'category_title_context', return_value='固定委托与完整正文'):
            prompts = {'article_titles':context.prompt_titles(fake, 'unused', p0=False),
                       'article_title_review':context.prompt_title_review(fake, 'unused', p0=False, title_result=raw)}
        for action, prompt in prompts.items():
            payload = {'prompt':prompt,'system':context.system(action,prompt)}
            if action.endswith('review'):payload['schema']=model_runtime.submit_tool_for(action,prompt=prompt)
            self.assertEqual(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),expected[action])
            self.assertEqual(strategy.request_policy(prompt), strategy.V2_POLICY)

    def test_normalized_v2_artifacts_and_absent_revision_stay_frozen(self):
        normalized = publication.validate_title_map(titles(), expected_policy=strategy.V2_POLICY)
        self.assertEqual(normalized['title_strategy'], strategy.V2_POLICY)
        self.assertEqual(publication.validate_title_map(normalized), normalized)
        publication.validate_title_review_result(review(titles()), normalized, p0=False)
        with self.assertRaises(ValueError):
            publication.validate_title_map(normalized, expected_policy=strategy.DEFAULT)
        for pattern in ('P01','P02','P03','P04','P05','P06'):
            state = wf.make_state('frozen','article'); state['selected_pattern_id']=pattern
            state['metadata']['article_title_revision']={}
            self.assertEqual(strategy.expected_count(state),20)
        state=wf.make_state('p0','p0'); state['metadata']['p0_title_revision']={}
        self.assertEqual(strategy.expected_count(state),20)


if __name__ == '__main__':
    unittest.main()
