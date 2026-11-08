"""Question-first intake. Answers are optional; scoped citations are required."""
from pathlib import Path
from datetime import datetime
import json
import shutil
import uuid

CONTRACT = 'frontmind-question-inputs/16.21'

def key(text):
    from shared.question_semantics import normalize_question_key
    return normalize_question_key(text)

def directory(w,p,qid,pid):
    return Path(p)/'question_inputs'/w.ident(qid)/w.ident(pid)

def valid_date(w,value):
    w.require(value=='undated' or datetime.strptime(value,'%Y-%m-%d').strftime('%Y-%m-%d')==value,'日期用YYYY-MM-DD；未知用undated')
    return value

def available(w,p):
    out=json.loads(w.dump(w.catalog(p)));lookup={q['id']:q for q in out}
    mapping={x['question_id']:x for x in w.accepted(p,2).get('question_map',[])}
    baseline=w.read(Path(p)/'inputs/all_answers.json')
    for q in out:
        for per in q['periods']:
            g=next((g for g in baseline if g['question_id']==q['id'] and g['period_id']==per['id']),{})
            count=len(g.get('answers',[]))
            per.update(answer_count=count,answer_status='provided' if count else 'pending',available=mapping.get(q['id'],{}).get('fit')!='out_of_scope',category=mapping.get(q['id'],{}).get('category') or q.get('category'))
    for f in sorted((Path(p)/'question_inputs').glob('*/*/meta.json')):
        meta=w.read(f);q=lookup.get(meta['question_id'])
        if q is None:
            q={'id':meta['question_id'],'question_text':meta['question_text'],'periods':[],'origin':'new_question'}
            lookup[q['id']]=q;out.append(q)
        per={**meta,'id':meta['period_id'],'available':True}
        q['periods']=[x for x in q['periods'] if x['id']!=per['id']]+[per]
    return out

def resolve(w,p,qid,pid):
    q=next((q for q in available(w,p) if q['id']==qid),None);w.require(q,'问题不在目录，请先登记题目')
    per=next((x for x in q['periods'] if x['id']==pid),None);w.require(per and per['available'],'期次不存在或已排除')
    return q,per

def register_question(w,p,text,date='undated',category=None):
    w.confirmed(p,2);w.require(w.nonempty(text),'请提供问题原文，不要求先有回答');valid_date(w,date)
    w.require(category is None or category in w.CATEGORIES,'问题类型只用当前三类')
    old=next((q for q in available(w,p) if key(q['question_text'])==key(text)),None)
    qid=old['id'] if old else 'q_'+w.digest(key(text))[:12];pid='p_'+uuid.uuid4().hex[:12]
    meta={'contract':CONTRACT,'question_id':qid,'period_id':pid,'question_text':text.strip(),'date':date,'category':category,'answer_count':0,'answer_status':'pending','answer_files':[],'source_files':[],'created_at':w.now()}
    w.write(directory(w,p,qid,pid)/'meta.json',meta);return meta

def editable(w,p,qid,pid):
    q,per=resolve(w,p,qid,pid)
    w.require(not any(a['question_id']==qid and a['period_id']==pid for a in w.state(p)['articles'].values()),'该期次已绑定文章，不能覆盖；同题登记新期次保留历史')
    d=directory(w,p,qid,pid)
    meta=w.read(d/'meta.json') if (d/'meta.json').exists() else {'contract':CONTRACT,'question_id':qid,'period_id':pid,'question_text':q['question_text'],'date':per['date'],'category':per.get('category'),'answer_count':per['answer_count'],'answer_status':per['answer_status'],'answer_files':[],'source_files':[],'created_at':w.now()}
    return q,meta,d

def attach_answers(w,p,qid,pid,files,answer_date=None):
    q,meta,d=editable(w,p,qid,pid);w.require(files,'提供完整回答文件，或skip-answers明确暂无回答')
    from shared.question_bank_import import read_export
    chosen=valid_date(w,answer_date or meta['date']);parsed=[];dates=set()
    for file in files:
        f=Path(file).expanduser().resolve();data=read_export(f,brand=w.state(p)['brand'],aliases=w.state(p)['aliases'])
        matches={date:row for date,questions in data['dates'].items() for k,row in questions.items() if k==key(q['question_text'])}
        w.require(matches,'回答文件没有当前问题的完整回答');dates.update(matches);parsed.append((f,matches))
    if chosen=='undated':
        w.require(len(dates)==1,'回答含多期，请用--answer-date指定本次日期');chosen=next(iter(dates))
    responses=[];originals=[];seen=set()
    for f,matches in parsed:
        w.require(chosen in matches,'回答日期与本期不匹配');h=w.hashfile(f);w.require(h not in seen,'回答文件重复');seen.add(h)
        responses+=matches[chosen]['answers'];dest=d/'answers'/(h[:20]+f.suffix.lower());dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
        originals.append({'path':dest.relative_to(p).as_posix(),'sha256':h})
    w.require(responses,'不能以摘要代替完整回答')
    w.write(d/'answers.json',{'question_id':qid,'period_id':pid,'question_text':q['question_text'],'date':chosen,'answers':responses})
    meta.update(date=chosen,answer_count=len(responses),answer_status='provided',answer_files=originals);w.write(d/'meta.json',meta);return meta

def skip_answers(w,p,qid,pid,note):
    _,meta,d=editable(w,p,qid,pid);w.require(w.nonempty(note),'记录用户明确暂无回答或本次不提供的原话')
    w.require(meta['answer_count']==0,'已有回答不能改成暂无，请登记新期次')
    meta.update(answer_status='not_provided',answer_note=note);w.write(d/'meta.json',meta);return meta

def attach_sources(w,p,qid,pid,files,source_date=None):
    q,meta,d=editable(w,p,qid,pid);w.require(files,'必须提供本题信源表');date=valid_date(w,source_date or meta['date'])
    from shared.article_pool import read_details
    ctx={'question_text':q['question_text'],'period_id':pid,'observed_from':None if date=='undated' else date,'observed_to':None if date=='undated' else date}
    originals=[];seen=set();count=0;observed_dates=set()
    for file in files:
        f=Path(file).expanduser().resolve();h=w.hashfile(f);w.require(h not in seen,'信源文件重复');seen.add(h)
        rows=read_details(f,ctx,explicit_period=pid);count+=len(rows);observed_dates.update(x['observed_date'] for x in rows if x.get('observed_date'))
        dest=d/'sources'/(h[:20]+f.suffix.lower());dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
        originals.append({'path':dest.relative_to(p).as_posix(),'sha256':h})
    if date=='undated' and observed_dates:
        w.require(len(observed_dates)==1,'信源含多个日期，请用--source-date明确本期，不混合多期')
        date=next(iter(observed_dates))
    meta.update(source_files=originals,source_date=date,citation_records=count);w.write(d/'meta.json',meta);return meta

def answers(w,p,qid,pid):
    q,per=resolve(w,p,qid,pid);f=directory(w,p,qid,pid)/'answers.json'
    if f.exists():return w.read(f)
    return next((g for g in w.read(Path(p)/'inputs/all_answers.json') if g['question_id']==qid and g['period_id']==pid),{'question_id':qid,'period_id':pid,'question_text':q['question_text'],'date':per['date'],'answers':[]})

def source_files(w,p,q,per):
    for f in per.get('source_files',[]):w.require(w.hashfile(Path(p)/f['path'])==f['sha256'],'关联信源发生变化，请用新期次')
    return [str(Path(p)/x['path']) for x in per.get('source_files',[])]

def mapping(w,p,a):
    s=w.selected(p,a);pos=w.accepted(p,2)
    return next((x for x in pos.get('question_map',[]) if x['question_id']==s['question_id']),None) or {'question_id':s['question_id'],'category':s.get('category'),'branch_ids':[pos['taxonomy'][0]['id']]}

def article_dependencies(w,p,a):
    out={}
    for name in ['question_answers.json','question_input_context.json']:
        f=w.scope(p,a)/name
        if f.exists():out[f.relative_to(p).as_posix()]=w.hashfile(f)
    f=w.scope(p,a)/'question_input_context.json'
    if f.exists():
        x=w.read(f);d=directory(w,p,x['question_id'],x['period_id'])
        for f in d.rglob('*') if d.exists() else []:
            if f.is_file():out[f.relative_to(p).as_posix()]=w.hashfile(f)
    return out
