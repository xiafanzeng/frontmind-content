"""New editorial inputs/exports and byte-identical v3 requests; no model calls."""
import copy
import hashlib
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from shared import title_strategy as ts, title_publication as pub, title_editorial_v168 as editor
from shared import writing_context_v14 as ctx, model_runtime as rt
from scripts import frontmind_workflow as wf


def candidates():
    return {'candidates':[{'title':f'合成品牌入口{i}', 'angle':f'内容入口{i}',
            'style':'formal' if i<=5 else 'scenario','usage_hint':['公众号B端','新闻稿']}
            for i in range(1,11)],'canonical_title_id':'title_07','title_notes':['补充素材正文尚未展开。']}


class DiverseTitlesTests(TestCase):
    def test_usage_and_notes_survive_normalization_and_exports(self):
        raw=candidates()
        normalized=pub.validate_title_map(raw,p0=True,expected_policy=ts.DEFAULT)
        self.assertEqual(normalized['title_contract_version'],ts.TITLE_HOOKS_CONTRACT_VERSION)
        self.assertEqual(pub.validate_title_map(normalized,p0=True),normalized)
        self.assertEqual(pub.title_review_input(normalized,p0=True),raw)
        for rendered in (wf.title_options_markdown(normalized,p0=True),wf.title_options_html(normalized,p0=True)):
            self.assertIn('公众号B端',rendered);self.assertIn('编辑备注',rendered)
            self.assertIn(raw['title_notes'][0],rendered)

    def test_invalid_usage_is_format_error_but_length_and_numbers_are_not_gates(self):
        raw=candidates()
        pub.validate_title_map(raw,p0=True,expected_policy=ts.DEFAULT)
        for value in (None,[],['未知'],['新闻稿']*2,['新闻稿','文档标题','方案页']):
            bad=copy.deepcopy(raw);bad['candidates'][0]['usage_hint']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                pub.validate_title_map(bad,p0=True,expected_policy=ts.DEFAULT)

    def test_accepted_keeps_notes_and_revision_changes_titles_not_notes_only(self):
        raw=candidates();accepted={'outcome':'accepted',**copy.deepcopy(raw),'reason':''}
        pub.validate_title_review_result(accepted,raw,p0=True,expected_policy=ts.DEFAULT)
        bad=copy.deepcopy(accepted);bad['title_notes']=[]
        with self.assertRaises(ValueError):pub.validate_title_review_result(bad,raw,p0=True,expected_policy=ts.DEFAULT)
        bad.update(outcome='revised',title_notes=['只改备注。'])
        with self.assertRaises(ValueError):pub.validate_title_review_result(bad,raw,p0=True,expected_policy=ts.DEFAULT)
        bad['canonical_title_id']='title_03'
        pub.validate_title_review_result(bad,raw,p0=True,expected_policy=ts.DEFAULT)

    def test_title_only_publication_preserves_exact_body_bytes(self):
        raw=candidates();review={'outcome':'accepted',**copy.deepcopy(raw),'reason':''}
        body='# 内部标题\r\n\r\n甲段。\r\n\r\n乙段。\r\n'
        result,map_,binding=pub.publication(body,raw,p0=True,title_review=review,expected_policy=ts.DEFAULT)
        self.assertEqual(result,pub.body_only(body))
        self.assertEqual(pub.verify_publication(body,raw,result,binding,p0=True,title_review=review,expected_policy=ts.DEFAULT),map_)

    def test_v3_prompt_system_schema_and_request_fingerprint_are_frozen(self):
        expected={'p0_titles':'933557f4881f54792aa42e7db164342b4b52d976e154b0805bd9e86bffd35d81',
                  # 原生宿主沿用已上线配置，区别于附件离线分发的默认宿主配置。
                  'p0_title_review':'d0bb1b4e243c1bd404a9735c694b2faf3985dc0e028da9f7170d64a685fad1b6'}
        state={'job_kind':'p0','selected_pattern_id':'P00','metadata':{'title_strategy':dict(ts.V3_POLICY)}}
        fake=SimpleNamespace(load_state=lambda _:state)
        raw={'candidates':[{'title':f'合成品牌标题{i}','angle':'同题','style':'formal' if i<=5 else 'scenario'} for i in range(1,11)],'canonical_title_id':'title_07'}
        with patch.object(ctx,'grouped_title_context',return_value='固定委托与完整正文'):
            prompts={'p0_titles':ctx.prompt_titles(fake,'unused',p0=True),'p0_title_review':ctx.prompt_title_review(fake,'unused',p0=True,title_result=raw)}
        for action,prompt in prompts.items():
            data={'prompt':prompt,'system':ctx.system(action,prompt),'fingerprint':rt.request_fingerprint(action,prompt)}
            if action.endswith('review'):data['schema']=rt.submit_tool_for(action,prompt=prompt)
            self.assertEqual(hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),expected[action])
        self.assertEqual(pub.validate_title_map(raw,p0=True)['title_strategy'],ts.V3_POLICY)

    def test_explicit_ammo_only_no_body_length_as_product_number(self):
        state={'job_kind':'p0','metadata':{'p0_title_revision':{'effective_writing_requirements':{'estimated_length':'3600字','title_ammo_extra':[{'text':'设备使用12通道。','source':'产品页'}]},'edits_markdown':'```json\n{"title_ammo_extra":["2分钟可检测完成，生成检测报告。"]}\n```'}}}
        self.assertEqual(len(editor._extra_inputs(state)),2)
        self.assertNotIn('3600',str(editor._extra_inputs(state)))

    def test_v4_review_schema_requires_placement_and_recognizes_only_owned_marker(self):
        prompt=ctx.MARKER+'\n'+ts.MARKER+'\n标题委托'
        schema=rt.submit_tool_for('p0_title_review',prompt=prompt)['function']['parameters']['properties']['result']
        row=schema['properties']['candidates']['items']
        self.assertIn('usage_hint',row['required'])
        self.assertEqual(row['properties']['usage_hint']['maxItems'],2)
        self.assertIsNone(ts.request_policy('原件引用\n'+prompt))
