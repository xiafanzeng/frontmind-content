"""Readable, resumable business choices and the complete question-writing route."""
from pathlib import Path
import reporting

CATEGORY_HELP = {'行业排名': '推荐、选型及有哪些选择等问题', '美誉舆情': '怎么样、口碑、资质、可信度或争议', '产品场景': '具体需求、使用场景、方法与服务流程'}
STATUS = {'awaiting_reference_pack':'等待三项Reference Pack','awaiting_question_selection':'等待选择问题或输入新题','awaiting_answers':'等待回答或明确暂无回答','awaiting_source_table':'等待本题信源表','ready_to_select':'题目与信源已就绪','awaiting_writing_selection':'等待选择问题类型与文章模式','legacy_article_requires_new_branch':'旧版文章缺少类型选择记录，需另建文章','awaiting_task_confirmation':'等待确认本篇任务','awaiting_brief_confirmation':'等待确认简要约稿','awaiting_fulltexts':'等待缺失全文','generation_pending':'写作请求进行中','awaiting_failure_resolution':'等待处理失败请求','awaiting_visual_qa':'Word排版检查待完成','delivery_complete':'本篇交付完成','ready':'可继续执行'}
LABELS = {'question_text':'问题','question':'问题','date':'回答日期','source_date':'信源日期','answer_status':'回答状态','answer_count':'回答数','category':'问题类型','form':'文章写法','pattern_id':'文章模式','reader':'目标读者','focus':'本篇重点','requirements':'本篇要求','brief':'约稿','length_suggestion':'建议篇幅','writing_material_markdown':'本篇自然事实素材','example_use':'构思参考用法','pass':'是否通过','issues':'具体问题','prose_review':'文风检查','notes':'说明','total':'候选全文数','attempted':'已尝试','complete':'完整正文排名','status':'状态','model':'模型','error_type':'失败类型','advantage_ids':'本篇选用优势','candidate_order':'文章主体','reason':'理由','note':'选择原话／说明'}
ANSWER = {'pending':'待补回答或明确暂无','provided':'已提供完整回答','not_provided':'明确本次暂无回答'}

def current(w,p):
    f=Path(p)/'current_task.json'
    return w.read(f) if f.exists() else {}

def choose_question(w,p,qid,pid=None,article=None):
    import question_updates as qu
    q=next((q for q in qu.available(w,p) if q['id']==qid),None);w.require(q,'从目录选题或先登记新问题')
    if pid is None:
        w.require(len(q['periods'])==1,'本题多期，请指定period-id');pid=q['periods'][0]['id']
    qu.resolve(w,p,qid,pid)
    if article:w.ident(article);w.require(article not in w.state(p)['articles'],'文章ID已存在')
    w.write(Path(p)/'current_task.json',{'question_id':qid,'period_id':pid,'article':article})
    return screen(w,p)

def at(v,n,instruction,pause=False,status='ready'):
    v.update(step=n,status=status,requires_user_input=pause,must_stop=pause,instruction=instruction)
    return v

def _context(w,p,a,v,n):
    v['inputs']=[]
    for name in ['定位.md','核心差异化优势.md','知识库.zip']:
        f=Path(p)/'imported_pack'/name
        if f.is_file():v['inputs'].append({'label':name,'path':str(f.resolve())})
    if a:
        q=w.selected(p,a)
        v['inputs'].append({'label':'本题数据','value':q['question_text']+'；'+str(q.get('answer_count',0))+'份完整回答'})
        for entry in q.get('inputs',[]):
            f=Path(p)/entry['path']
            if f.is_file():v['inputs'].append({'label':'已关联逐条信源原件','path':str(f.resolve())})
        for key,label in [('report_txt','本题信源报告'),('all_articles_csv','全部引用文章')]:
            f=reporting.paths(w,p,a)[key]
            if Path(f).is_file():v['inputs'].append({'label':label,'path':f})
    v['models']=['XTY gemini-4-argon／high（写作、必要编辑、拟题）；Kimi Hosted high一次文风检查'] if n in (8,9) else ['Kimi Hosted kimi-k3.1-pro/high；本地程序统计和导出']
    outputs=[]
    if a:
        stage=w.stepdir(p,n,a);runs=sorted((stage/'writer_runs').glob('*/execution.json'))
        if runs:
            for index,ex in enumerate(runs,1):
                record=w.read(ex)
                for name,label in [('system.md','System Prompt原文'),('user.md','User Prompt原文'),('response_content.txt','返回内容原文')]:
                    f=ex.parent/name
                    if f.is_file():outputs.append({'label':f'第{index}次调用 {label}（{record.get("status","未知")}）','path':str(f.resolve())})
        else:
            for f in sorted((stage/'prompts').glob('*/system.md')):
                outputs.append({'label':'本步准备的System Prompt（准备不代表调用）','path':str(f.resolve())})
                if (f.parent/'user.md').is_file():outputs.append({'label':'本步准备的User Prompt','path':str((f.parent/'user.md').resolve())})
        if (stage/'final.md').is_file():outputs.append({'label':'本步成稿','path':str((stage/'final.md').resolve())})
        if (stage/'candidate.json').is_file():
            f=stage/w.read(stage/'candidate.json')['path']
            if f.is_file():outputs.append({'label':'当前完整候选稿','path':str(f.resolve())})
        if n==11:
            for f in sorted((Path(p)/'deliveries'/a).glob('*')):
                if f.is_file() and f.suffix.lower() in ['.txt','.docx','.html','.md'] and f.name!='VISUAL_QA_PENDING.md':
                    outputs.append({'label':f.name,'path':str(f.resolve())})
    v['outputs']=outputs
    return v

def _references(w,p,a):
    result=w.result(p,6,a);lookup={x['raw_rank']:x for x in w.sourcepool(p,a)['articles']}
    ac=w.read(w.scope(p,a)/'acquisition.json');entries={x['rank']:x for x in ac['entries']};rows=[]
    for i,rank in enumerate(result['selected_ranks']):
        entry=entries.get(rank,{});row=dict(lookup[rank],reason=result['reasons'][i])
        row['availability']='完整正文' if entry.get('completeness')=='complete' else '完整性记录待核对'
        if entry.get('text_path'):row['path']=str((w.scope(p,a)/entry['text_path']).resolve())
        rows.append(row)
    return rows

def _failure(w,p,a,n,v,show):
    runs=sorted((w.stepdir(p,n,a)/'writer_runs').glob('*/execution.json'),reverse=True)
    if not runs or w.read(runs[0]).get('status')=='succeeded':return None
    record=w.read(runs[0]);running=record.get('status')=='running'
    v['details'].append({'label':'真实请求状态','value':{'status':record.get('status'),'model':record.get('requested_model','gemini-4-argon')+'／high','error_type':record.get('error_type')}})
    return show(n,'先检查真实进程与日志，不启动并行重复请求。' if running else '请求未成功，先检查保存记录；重试须显式执行同模型请求，不自动换模型。',not running,'generation_pending' if running else 'awaiting_failure_resolution')

def screen(w,p=None,article=None):
    if not p or not (Path(p)/'state.json').exists():
        return {'schema':'frontmind-question-writing/16.25.1','title':'问题优化','status':'awaiting_reference_pack','requires_user_input':True,'must_stop':True,'step':None,'instruction':'提供第一流程导出的三项Reference Pack：定位.md、核心差异化优势.md、知识库.zip。无需品牌介绍稿。','options':[{'command':'import-pack','label':'导入三项Reference Pack'}],'details':[]}
    import question_updates as qu
    import writing_choices as choices
    p=Path(p);w.confirmed(p,2);w.advantage_snapshot(p);state=w.state(p);pending=current(w,p)
    v={'schema':'frontmind-question-writing/16.25.1','title':'问题优化','brand':state['brand'],'project':str(p.resolve()),'requires_user_input':False,'must_stop':False,'status':'ready','step':None,'instruction':'','options':[],'details':[]}
    a=article or pending.get('article')
    if a and a not in state['articles']:a=None
    def show(n,text,pause=False,status='ready'):
        return _context(w,p,a,at(v,n,text,pause,status),n)
    if not a:
        if not pending.get('question_id'):
            v['details']=[{'label':'已有问题目录','value':qu.available(w,p)},{'label':'可继续的文章','value':state['articles']}]
            v['options']=[{'command':'choose-question','label':'选择已有问题'},{'command':'add-question','label':'只输入新问题'},{'command':'screen --article ID','label':'继续已有文章'}]
            return show(4,'从已有目录选题，或直接输入新问题。选择问题不等于选择文章类型。',True,'awaiting_question_selection')
        q,period=qu.resolve(w,p,pending['question_id'],pending['period_id']);v['details']=[{'label':'本题及期次','value':{'question':q['question_text'],**period}}]
        if period['answer_status']=='pending':
            v['options']=[{'command':'attach-answers','label':'补交本题完整回答'},{'command':'skip-answers','label':'明确本次暂无回答'},{'command':'new-article','label':'重新选题'}]
            return show(4,'题目已登记。补交完整回答；没有回答可明确记录，仍可继续。',True,'awaiting_answers')
        if not period.get('source_files'):
            v['options']=[{'command':'attach-sources','label':'提供本题信源表'},{'command':'new-article','label':'重新选题'}]
            return show(4,'必须关联本题逐条信源，答案与信源日期分别保留。',True,'awaiting_source_table')
        v['options']=[{'command':'select','label':'冻结本题数据，展示信源表并选择文章模式'}]
        return show(4,'本题、回答状态及信源已关联；继续后先展示实际信源列表，再选择写法。',False,'ready_to_select')
    v['article']=a;choice=choices.load(w,p,a,required=False)
    if not choice:
        if w.done(p,5,a):
            v['details']=[{'label':'本题信源列表','value':reporting.source_view(w,p,a)},
                          {'label':'旧版文章记录','value':'这篇文章已冻结本篇任务，但没有新版要求的明确问题类型及文章模式选择记录。旧稿和实际调用记录原样保留；不能在旧文补选类型冒充当时已选择。'}]
            v['options']=[{'command':'new-article','label':'保留旧文，另建文章并重新选择类型'},
                          {'command':'show-sources','label':'查看旧文关联的本题信源表'}]
            return show(5,'旧版记录缺少类型选择。请另建文章分支后选择问题类型与文章模式；不在已冻结旧文执行choose-writing。',True,'legacy_article_requires_new_branch')
        v['details']=[{'label':'本题信源列表','value':reporting.source_view(w,p,a)},{'label':'问题类型与文章模式','value':{'categories':CATEGORY_HELP,'patterns':choices.PATTERNS,'catalog_category':w.selected(p,a).get('category'),'candidate_pool':choices.candidates(w,p)}}]
        v['options']=[{'command':'choose-writing','label':'明确选择问题类型和文章模式（P01／P02／P03／P04／P06）'},{'command':'show-sources','label':'查看本题完整信源表'},{'command':'new-article','label':'另选问题'}]
        return show(5,'问题类型与文章模式是两个维度。请显式选择；系统建议和确认写作任务均不能代替类型选择。',True,'awaiting_writing_selection')
    v['details'].append({'label':'已选类型与模式','value':choice})
    if not w.done(p,5,a):return show(5,'按已选类型和文章模式形成本篇读者、主体及重点，沿用定位和相关优势。')
    if not (w.stepdir(p,5,a)/'confirmation.json').exists():
        v['details'].append({'label':'本篇写作任务','value':w.task(p,a)})
        v['options']=[{'command':'confirm --step 5','label':'确认本篇任务'},{'command':'new-article','label':'另建文章调整任务'}]
        return show(5,'请核对本篇读者、用途、主体顺序和重点；同范围明确授权可沿用。',True,'awaiting_task_confirmation')
    if not w.done(p,6,a):
        f=w.scope(p,a)/'acquisition.json';entries=w.read(f)['entries'] if f.exists() else [];complete=[]
        for entry in entries:
            try:w.fullbody(p,a,entry['rank']);complete.append(entry['rank'])
            except (ValueError,KeyError,FileNotFoundError):pass
        total=len(w.body_pool(p,a));v['details'].append({'label':'全文取得进度','value':{'total':total,'attempted':len(entries),'complete':complete}})
        missing=len(entries)==total and len(complete)<2
        return show(6,'尝试取得实际全文，按本篇类型、模式和定位自动选两篇。'+('当前不足两篇，继续补取缺失原文。' if missing else '选文自动完成，结果仍会展示。'),missing,'awaiting_fulltexts' if missing else 'ready')
    if not w.done(p,7,a):
        v['details'].append({'label':'自动选中的两篇构思参考','value':_references(w,p,a)})
        return show(7,'展示自动选文结果及理由，继续形成简要约稿与本篇自然选材，无需用户代选例文。')
    if not (w.stepdir(p,7,a)/'confirmation.json').exists():
        v['details'] += [{'label':'自动选中的两篇构思参考','value':_references(w,p,a)},{'label':'本篇简要约稿','value':w.result(p,7,a)}]
        v['options']=[{'command':'confirm --step 7','label':'确认约稿并写作'}]
        return show(7,'确认简要约稿和本篇自然选材；保留作者组织段落的空间。',True,'awaiting_brief_confirmation')
    if not w.done(p,8,a):
        failed=_failure(w,p,a,8,v,show)
        if failed:return failed
        f=w.stepdir(p,8,a)/'latest_review.json'
        if f.exists():v['details'].append({'label':'当前稿文风检查','value':w.read(f)})
        return show(8,'有具体问题才定向编辑一次，再核对改动；不固定全文多轮。' if f.exists() else '按已选文章模式用Gemini high写正文，保留真实Prompt与返回全文，检查反防御性表达和文字是否顺畅。')
    if not w.done(p,9,a):
        failed=_failure(w,p,a,9,v,show)
        if failed:return failed
        stage=w.stepdir(p,9,a)
        if (stage/'title_references.json').exists():
            refs=w.read(stage/'title_references.json');lookup={x['raw_rank']:x for x in w.sourcepool(p,a)['top20']}
            v['details'].append({'label':'全部Top20标题及独立两条核心参考','value':{'ordered_titles':[lookup[r] for r in refs['ordered_ranks']],'core_title_ranks':refs['core_title_ranks'],'core_reasons':refs['core_reasons']}})
        if (stage/'writer_result.json').exists():v['details'].append({'label':'Gemini初拟10个标题','value':w.read(stage/'writer_result.json')})
        return show(9,'读取全部Top20标题，独立选两条核心题式，拟定并编辑同一篇完整文章的10个替代主标题。正文两篇参考不自动等于标题核心参考。')
    if not w.done(p,10,a):
        v['details'].append({'label':'最终10个标题','value':w.result(p,9,a)})
        return show(10,'完整评估本题候选，按本篇用途/写法、具体证据和改编成本优选20个独立信源。官网等剔除，未入选媒体保留候选；主表只显示入选20个的四列。')
    v['details'].append({'label':'本篇媒体信源建议','value':w.result(p,10,a)})
    if not w.done(p,11,a):return show(11,'正文、10个标题和媒体建议均已完成。导出同一终稿与支持产物，再逐页检查Word。')
    qa=w.result(p,11,a).get('visual_qa')=='passed'
    return show(11,'本篇正文、10个标题、媒体表与排版检查完成，可另选问题。' if qa else '文件已导出，继续Word渲染逐页检查，不能把导出当排版验收。',False,'delivery_complete' if qa else 'awaiting_visual_qa')

def cell(value):return reporting.cell(value)

def readable(value):
    if isinstance(value,bool):return ['通过' if value else '未通过']
    if value is None:return ['未提供']
    if isinstance(value,(str,int,float)):return [str(value)]
    if isinstance(value,list):
        out=[]
        for i,item in enumerate(value,1):
            out += [f'{i}. '+('' if isinstance(item,(dict,list)) else cell(item))]
            if isinstance(item,(dict,list)):out += readable(item)
        return out or ['无']
    out=[]
    for key,item in value.items():
        if key.endswith(('_sha256','_snapshot_id')) or key in ['snapshot_id','dependencies','candidate_ids','branch_id','facts','subject_evidence','by']:continue
        out += [LABELS.get(key,key)+'：']+readable(item)
    return out

def _key_table(value,keys):
    return ['| 项目 | 当前内容 |','|---|---|']+['| '+LABELS.get(k,k)+' | '+cell('、'.join(map(str,value[k])) if isinstance(value[k],list) else value[k])+' |' for k in keys if k in value]

def _media_table(value):
    from media_advice import render_lines
    return render_lines(value)

def render(value):
    lines=['# '+value['title'],'','状态：'+STATUS.get(value['status'],value['status']),'',value['instruction']]
    if value.get('brand'):lines += ['', '企业：'+value['brand']]
    if value.get('step') is not None:lines += ['当前步骤：'+str(value['step'])]
    for detail in value.get('details',[]):
        label,data=detail['label'],detail['value']
        if label=='本题信源列表':
            lines += ['',reporting.render_sources(data)];continue
        lines += ['', '## '+label,'']
        if label=='已有问题目录':
            lines += ['| 编号 | 问题 | 日期 | 回答 | 信源 |','|---|---|---|---|---|'];number=0
            for q in data:
                for per in q['periods']:
                    if not per.get('available'):continue
                    number+=1;lines.append('| '+' | '.join(cell(x) for x in [number,q['question_text'],per['date'],ANSWER.get(per['answer_status'],per['answer_status'])+f"（{per['answer_count']}份）",'已关联' if per.get('source_files') else '待提供'])+' |')
            if not number:lines += ['', '暂无已有题目，可直接输入新问题。']
        elif label=='可继续的文章':
            lines += ['| 文章 | 对应问题 |','|---|---|']+[f"| {cell(a)} | {cell(x.get('question_text','已有问题'))} |" for a,x in data.items()]
            if not data:lines += ['', '暂无已创建文章。']
        elif label=='本题及期次':
            item=dict(data);item['answer_status']=ANSWER.get(item.get('answer_status'),item.get('answer_status'))
            lines += _key_table(item,['question','date','answer_status','answer_count','source_date'])
        elif label=='问题类型与文章模式':
            lines += ['问题类型描述问题意图；文章模式决定怎样组织回答。二者分别保存。','','| 问题类型 | 用途 |','|---|---|']
            lines += ['| '+cell(k)+' | '+cell(v)+' |' for k,v in data['categories'].items()]
            if data.get('catalog_category'):lines += ['', '目录记录的类型：'+cell(data['catalog_category'])+'（供参考，仍需明确本篇选择）。']
            lines += ['', '| 模式 | 文章写法 | 回答任务 | 常见适配问题类型 |','|---|---|---|---|']
            for key,item in data['patterns'].items():
                if key not in ['P01','P02','P03','P04','P06']:continue
                lines.append('| '+' | '.join(cell(x) for x in [key,item['form'],item.get('label',item['form']),'、'.join(item.get('categories',[]))])+' |')
            lines += ['', '请指定“问题类型＋文章模式”；例如“行业排名＋P01”。系统建议不代替用户选择。']
            if data.get('candidate_pool'):
                lines += ['', '选择P02时，再从以下已确认同类对象中选本篇子集，数量不固定；可用对象ID或完整名称提交。', '', '| 对象ID | 已确认对象 | 对应产品／方案 |', '|---|---|---|']
                for candidate in data['candidate_pool']:
                    lines.append('| '+cell(candidate.get('candidate_id',''))+' | '+cell(candidate.get('display_name',candidate.get('name','')))+' | '+cell(candidate.get('product_name') or candidate.get('offer_name') or '按确认定位记录')+' |')
        elif label in ['已选类型与模式','本篇写作任务']:
            lines += _key_table(data,['category','pattern_id','form','reader','focus','candidate_order','requirements','note'])
        elif label=='本篇简要约稿':
            for key in ['brief','length_suggestion','writing_material_markdown','example_use']:
                if data.get(key):lines += [LABELS[key]+'：','',str(data[key]),'']
        elif label=='自动选中的两篇构思参考':
            lines += ['| 排名 | 文章及原文链接 | 引用次数 | 取得状态 | 采用理由 |','|---|---|---:|---|---|']
            for x in data:
                text=reporting.article_link(x)
                if x.get('path'):text+=f'（[已取得正文](<{x["path"]}>)）'
                lines.append(f'| {x["raw_rank"]} | {text} | {x["citation_count"]} | {cell(x["availability"])} | {cell(x["reason"])} |')
        elif label=='全部Top20标题及独立两条核心参考':
            lines += ['| 引用排名 | 标题与链接 | 核心题式参考 |','|---|---|---|']
            for x in data['ordered_titles']:
                core='是' if x['raw_rank'] in data['core_title_ranks'] else ''
                lines.append(f'| {x["raw_rank"]} | {reporting.article_link(x)} | {core} |')
            lines += ['',*[f'{i}. {reason}' for i,reason in enumerate(data['core_reasons'],1)]]
        elif label=='本篇媒体信源建议':lines += _media_table(data)
        elif isinstance(data,dict) and 'titles' in data:
            lines += [f'{i}. {x["title"]}'+('（建议优先）' if i-1==data.get('recommended_index') else '') for i,x in enumerate(data['titles'],1)]
        else:lines += readable(data)
    for key,title in [('inputs','本步输入'),('models','执行模型与方式'),('outputs','Prompt与产物')]:
        items=value.get(key,[]);lines += ['', '## '+title,'']
        if not items:lines.append('等待本步执行后生成。' if key=='outputs' else '按当前任务补齐。')
        for item in items:
            if isinstance(item,str):lines.append('- '+item)
            elif item.get('path'):lines.append(f'- [{item["label"]}](<{item["path"]}>)')
            else:lines.append('- '+item['label']+'：'+str(item.get('value','')))
    if value.get('options'):lines += ['', '可选操作：','']+[f'{i}. {x["label"]}' for i,x in enumerate(value['options'],1)]
    return '\n'.join(lines)+'\n'
