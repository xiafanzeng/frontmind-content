"""Offline behavior checks for full media coverage and honest evidence."""
from pathlib import Path
import copy
import csv
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import media_advice as ma
import interaction as ui


class OfflineWorkflow:
    def __init__(self, pool):self.pool=pool
    def sourcepool(self, p, article):return self.pool
    def require(self, condition, message):
        if not condition:raise ValueError(message)
    def nonempty(self, value):return isinstance(value,str) and bool(value.strip())
    def fullbody(self, p, article, rank):
        if rank != 1:raise ValueError('该条没有实际全文')
        return '离线全文fixture'
    def finalbody(self, p, step, article):return '离线当前完整终稿'
    def digest(self, text):return hashlib.sha256(text.encode()).hexdigest()
    def selected(self, p, article):return {'question_text':'离线健康设备选型问题','observed_from':'2026-11-06'}


class MediaAdvice(unittest.TestCase):
    def setUp(self):
        articles=[]
        for i,(name,cites) in enumerate([('博客园',8),('博客园',4),('爱采购',11),('上海道生医疗科技有限公司',23)],1):
            articles.append({'article_id':f'a{i:06d}','raw_rank':i,'media':name,
                             'content_title':f'离线证据标题{i}','canonical_url':f'https://example.org/{i}',
                             'citation_count':cites})
        self.pool={'articles':articles,'media':[
            {'media':'博客园','article_count':2,'citation_count':12},
            {'media':'爱采购','article_count':1,'citation_count':11},
            {'media':'上海道生医疗科技有限公司','article_count':1,'citation_count':23}],
            'article_count':4,'citation_count':46}
        self.workflow=OfflineWorkflow(self.pool)
        self.value={'rows':[
            self.row('博客园','a000001','内容平台'),self.row('爱采购','a000003','商业发布平台')],
            'excluded_sources':[{'media':'上海道生医疗科技有限公司','source_kind':'企业官网',
                'reason':'离线来源身份fixture：厂商自有产品官网。','article_ids':['a000004']}],
            'selection':{'selected_media':['博客园','爱采购'],'reason':'离线仅两家独立合格载体，如实推荐两家，不用官网凑数。'},
            'availability_note':'离线测试，账号和资源可购性未核实。'}

    def row(self, media, article_id, kind):
        return {'media':media,'source_kind':kind,'priority':'可选推荐','outlet_key':media,
            'topic_fit':'related','form_fit':'adaptable','audience_fit':'direct',
            'fit_basis':'离线题名涉及机构设备选择，需将医疗用途限定为当前非临床康养评估。',
            'selection_reason':'离线测试中具备机构选型题材和可改写的图文载体，先核对具体栏目。',
            'use_route':'将本稿内容调整为健康设备选型说明或产品信息。',
            'next_action':'核实该平台具体账号、内容形式及发布要求。',
            'reason':'有实际被引内容作为载体依据，需按本稿用途调整。',
            'evidence':[{'article_id':article_id,'read_level':'title_only','scope_fit':'cross',
                'basis':'仅标题显示设备选型主题，不推断全文结论。',
                'scope_basis':'证据题名涉及医疗用途，本稿限定非临床康养评估。'}]}

    def validate(self, value=None):return ma.validate(self.workflow,None,'fixture',self.value if value is None else value)

    def test_complete_partition_retains_cross_scope_title_only_platforms(self):
        result=self.validate()
        self.assertEqual(result['coverage']['source_count'],3)
        self.assertEqual(result['coverage']['recommended_source_count'],2)
        self.assertEqual(result['coverage']['excluded_source_count'],1)
        self.assertEqual(result['rows'][0]['article_count'],2)
        self.assertEqual(result['rows'][0]['citation_count'],12)
        self.assertEqual(result['rows'][0]['evidence_article_count'],1)
        self.assertEqual(result['rows'][0]['evidence_citation_count'],8)
        self.assertEqual(result['article_sha256'],self.workflow.digest('离线当前完整终稿'))

    def test_missing_media_rejected(self):
        self.value['rows'].pop()
        with self.assertRaisesRegex(ValueError,'缺少爱采购'):self.validate()

    def test_duplicate_media_rejected(self):
        self.value['rows'].append(copy.deepcopy(self.value['rows'][0]))
        with self.assertRaisesRegex(ValueError,'重复'):self.validate()

    def test_recommend_and_exclude_overlap_rejected(self):
        self.value['excluded_sources'].append({'media':'博客园'})
        with self.assertRaisesRegex(ValueError,'既推荐又剔除'):self.validate()

    def test_unknown_source_rejected(self):
        self.value['rows'][0]['media']='本题没有的平台'
        with self.assertRaisesRegex(ValueError,'未知来源'):self.validate()

    def test_non_identity_exclusion_reasons_cannot_replace_media(self):
        for category in ['医疗题材','缺全文','低引用','账号未知']:
            value=copy.deepcopy(self.value)
            value['rows'].pop()
            value['excluded_sources'].append({'media':'爱采购','source_kind':category,
                'reason':category,'article_ids':['a000003']})
            with self.subTest(category=category),self.assertRaisesRegex(ValueError,'来源|剔除'):self.validate(value)

    def test_official_site_type_rejected_in_recommendations(self):
        self.value['rows'][0]['source_kind']='企业官网'
        with self.assertRaisesRegex(ValueError,'企业官网'):self.validate()

    def test_wrong_media_evidence_rejected(self):
        self.value['rows'][0]['evidence'][0]['article_id']='a000003'
        with self.assertRaisesRegex(ValueError,'属于该媒体'):self.validate()

    def test_duplicate_evidence_rejected(self):
        self.value['rows'][0]['evidence']*=2
        with self.assertRaisesRegex(ValueError,'重复'):self.validate()

    def test_unavailable_fulltext_cannot_be_claimed(self):
        self.value['rows'][1]['evidence'][0]['read_level']='fulltext'
        with self.assertRaisesRegex(ValueError,'实际全文'):self.validate()

    def test_actual_fulltext_and_mixed_scope_can_be_recommended(self):
        evidence=self.value['rows'][0]['evidence'][0]
        evidence['read_level']='fulltext';evidence['scope_fit']='mixed'
        self.validate()

    def test_unknown_scope_and_account_still_receive_explicit_advice(self):
        row=self.value['rows'][1];row['priority']='待核实后考虑';row['source_kind']='待核实平台'
        row['evidence'][0]['scope_fit']='undetermined'
        self.value['selection']['selected_media']=['博客园']
        result=self.validate()
        self.assertEqual(result['coverage']['candidate_source_group_count'],2)
        self.assertEqual(result['coverage']['recommended_source_count'],1)

    def test_missing_use_route_or_next_action_rejected(self):
        for field in ['use_route','next_action','reason']:
            value=copy.deepcopy(self.value);value['rows'][0].pop(field)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'使用方式'):self.validate(value)

    def test_excluded_evidence_must_belong_to_actual_source(self):
        self.value['excluded_sources'][0]['article_ids']=['a000001']
        with self.assertRaisesRegex(ValueError,'实际条目'):self.validate()

    def test_ui_text_csv_keep_every_media_and_separate_official_site(self):
        value=self.validate();text='\n'.join(ui._media_table(value))
        for name in ['博客园','爱采购']:self.assertIn(name,text)
        self.assertNotIn('上海道生医疗科技有限公司',text)
        self.assertIn('上海道生医疗科技有限公司',ma.exclusion_report(value,self.pool))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'media.csv';ma.write_csv(value,path)
            with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        self.assertEqual([x['媒体名字'] for x in rows],['博客园','爱采购'])
        self.assertEqual(list(rows[0]),['媒体名字','类型','比例','具体文章依据'])
        self.assertEqual(rows[0]['类型'],'内容平台')
        self.assertEqual(rows[0]['比例'],'2篇／12次')
        self.assertIn('8次',rows[0]['具体文章依据'])
        for row in rows:
            self.assertEqual(len(row),4)
            self.assertNotIn('（'+row['类型']+'）',row['媒体名字'])
        for row in text.splitlines():
            if row.startswith('| '):self.assertEqual(len(row.split('|')[1:-1]),4)
        for internal_key in ['priority','use_route','next_action','reason']:
            self.assertNotIn(value['rows'][0][internal_key],text)
        self.assertEqual(value['rows'][0]['citation_count'],12)
        self.assertEqual(value['rows'][0]['evidence_citation_count'],8)

    def test_no_media_case_can_exclude_all_actual_official_sources(self):
        pool=copy.deepcopy(self.pool);pool['media']=pool['media'][-1:];pool['articles']=pool['articles'][-1:]
        pool['article_count']=1;pool['citation_count']=23
        self.workflow.pool=pool;self.value['rows']=[];self.value['selection']['selected_media']=[]
        result=self.validate()
        self.assertEqual(result['coverage']['recommended_source_count'],0)
        self.assertTrue(result['coverage']['complete'])

    def test_platform_label_keeps_original_group_for_coverage(self):
        self.value['rows'][1]['platform_name']='百度爱采购商家发布载体'
        value=self.validate();text='\n'.join(ma.render_lines(value))
        self.assertEqual(ma.table_values(value['rows'][1])[0],'百度爱采购商家发布载体')
        self.assertIn('原来源标签：爱采购',ma.table_values(value['rows'][1])[3])
        self.assertEqual(value['rows'][1]['media'],'爱采购')
        self.assertTrue(value['coverage']['complete'])

    def many_sources(self,number=24):
        articles=[];rows=[];groups=[]
        for index in range(1,number+1):
            name=f'离线平台{index:02d}';aid=f'a{index:06d}'
            articles.append({'article_id':aid,'raw_rank':index,'media':name,
                             'content_title':f'离线机构选型文章{index}',
                             'canonical_url':f'https://example.org/offline/{index}','citation_count':index})
            groups.append({'media':name,'article_count':1,'citation_count':index})
            rows.append(self.row(name,aid,'内容平台'))
        self.pool={'media':groups,'articles':articles,'article_count':number,'citation_count':sum(range(1,number+1))}
        self.workflow.pool=self.pool
        self.value={'rows':rows,'excluded_sources':[],
                    'selection':{'selected_media':[r['media'] for r in rows[:20]],
                                 'reason':'离线测试的选定顺序基于文章适配判断，不代表任何真实媒体建议。'},
                    'availability_note':'离线合成数据，验证20个名额与完整候选保留，无网络或提供商调用。'}

    def test_twenty_selected_and_remaining_candidates_stay_in_full_pool(self):
        self.many_sources();result=self.validate()
        self.assertEqual(result['coverage']['recommended_source_count'],20)
        self.assertEqual(result['coverage']['candidate_source_group_count'],24)
        self.assertEqual(result['coverage']['reserve_source_group_count'],4)
        self.assertEqual(len(ma.visible_rows(result)),20)
        self.assertEqual(len(ma.visible_rows(result,selected_only=False)),24)
        main='\n'.join(ma.render_lines(result));all_rows='\n'.join(ma.render_lines(result,selected_only=False))
        self.assertNotIn('离线平台24',main);self.assertIn('离线平台24',all_rows)
        with tempfile.TemporaryDirectory() as directory:
            for only_selected,expected in [(True,20),(False,24)]:
                path=Path(directory)/f'{only_selected}.csv';ma.write_csv(result,path,selected_only=only_selected)
                with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
                self.assertEqual(len(rows),expected+1)
                self.assertTrue(all(len(row)==4 for row in rows))

    def test_twenty_required_when_enough_eligible_outlets(self):
        for number in [19,21]:
            self.many_sources();self.value['selection']['selected_media']=[r['media'] for r in self.value['rows'][:number]]
            with self.subTest(number=number),self.assertRaisesRegex(ValueError,'应推荐20'):self.validate()

    def test_same_platform_alias_cannot_take_two_recommendation_slots(self):
        self.many_sources();self.value['rows'][1]['outlet_key']=self.value['rows'][0]['outlet_key']
        with self.assertRaisesRegex(ValueError,'别名不能重复'):self.validate()

    def test_aliases_leave_real_shortfall_instead_of_padding(self):
        self.value['rows'][1]['outlet_key']=self.value['rows'][0]['outlet_key']
        self.value['selection']['selected_media']=['博客园']
        result=self.validate()
        self.assertEqual(result['coverage']['recommended_source_count'],1)
        self.assertEqual(result['coverage']['candidate_source_group_count'],2)

    def test_weak_topic_cannot_fill_recommendation_quota(self):
        self.many_sources();self.value['rows'][0]['topic_fit']='weak'
        with self.assertRaisesRegex(ValueError,'弱相关'):self.validate()
        self.value['selection']['selected_media']=[r['media'] for r in self.value['rows'][1:21]]
        self.assertEqual(self.validate()['coverage']['recommended_source_count'],20)

    def test_selection_order_is_preserved_without_resorting_by_citation_count(self):
        self.many_sources();self.value['selection']['selected_media'].reverse()
        result=self.validate()
        self.assertEqual(ma.visible_rows(result)[0]['media'],'离线平台20')
        self.assertEqual(ma.visible_rows(result)[-1]['media'],'离线平台01')
        self.assertNotIn('离线平台24',[r['media'] for r in ma.visible_rows(result)])

    def test_old_full_table_cannot_be_silently_truncated(self):
        self.many_sources();self.value.pop('selection')
        with self.assertRaisesRegex(ValueError,'20信源'):self.validate()
        with self.assertRaisesRegex(ValueError,'尚未完成'):ma.render_lines(self.value)

    def test_selected_source_requires_concrete_selection_reason(self):
        self.value['rows'][0].pop('selection_reason')
        with self.assertRaisesRegex(ValueError,'择优理由'):self.validate()

    def test_source_fit_assessment_is_required_for_all_candidates(self):
        self.value['rows'][0]['form_fit']='没有阅读却声称高度匹配'
        with self.assertRaisesRegex(ValueError,'写法及读者适配'):self.validate()

    def test_user_required_video_is_selected_without_adding_a_twenty_first_slot(self):
        self.many_sources();video=self.value['rows'][-1]
        video['source_kind']='视频平台';video['topic_fit']='direct';video['form_fit']='rebuild'
        self.value['selection'].update(required_media=[video['media']],required_media_note='离线模拟用户：这个视频平台也要纳入。')
        with self.assertRaisesRegex(ValueError,'必须纳入20'):self.validate()
        self.value['selection']['selected_media'][-1]=video['media']
        result=self.validate()
        self.assertEqual(len(ma.visible_rows(result)),20)
        self.assertEqual(ma.visible_rows(result)[-1]['media'],video['media'])

    def test_user_required_source_still_needs_real_source_pool_identity(self):
        self.value['selection'].update(required_media=['本题没有的媒体'],required_media_note='离线模拟指定。')
        with self.assertRaisesRegex(ValueError,'本题有真实依据'):self.validate()

    def test_required_source_records_actual_user_direction(self):
        self.value['selection']['required_media']=['博客园']
        with self.assertRaisesRegex(ValueError,'记录用户原话'):self.validate()


if __name__=='__main__':unittest.main()
