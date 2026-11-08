"""New question/answer uploads reuse positioning and preserve older articles."""
from pathlib import Path
import json
import shutil
import uuid

CONTRACT='frontmind-question-updates/16.19'

def folder(p,batch):return Path(p)/'question_updates'/batch
def batch_dirs(p):return sorted(x for x in (Path(p)/'question_updates').glob('*') if x.is_dir() and (x/'manifest.json').is_file())
def key(text):
    from shared.question_semantics import normalize_question_key
    return normalize_question_key(text)

def import_batch(w,p,batch,files,sources=()):
    w.ident(batch);w.require(len(batch)<=30,'上传批次ID请不超过30字符')
    target=folder(p,batch);w.require(not target.exists(),'上传批次已存在，使用新ID保留原期次')
    w.state(p);w.require(files,'请提供含题目及完整回答的问答表；只更新信源可直接为已有题关联新信源')
    from shared.question_bank_import import read_export
    baseline_hashes={x['file_sha256'] for x in w.read(Path(p)/'inputs/answer_imports.json')} if (Path(p)/'inputs/answer_imports.json').exists() else set()
    old_hashes={x['sha256'] for d in batch_dirs(p) for x in w.read(d/'manifest.json')['answer_files']}
    seen=set();imports=[]
    for file in files:
        f=Path(file).expanduser().resolve();h=w.hashfile(f)
        w.require(h not in seen|old_hashes|baseline_hashes,'该完整问答文件已导入，请选择已有期次；修正版用新文件，不重复累计样本')
        seen.add(h);data=read_export(f,brand=w.state(p)['brand'],aliases=w.state(p)['aliases']);imports.append((f,h,data))
    known={key(x['question_text']):x['id'] for x in w.catalog(p)}
    for d in batch_dirs(p):
        for x in w.read(d/'question_catalog.json'):known.setdefault(key(x['question_text']),x['id'])
    qs={};groups=[]
    for file,h,imp in imports:
        for date,questions in imp['dates'].items():
            for k,item in questions.items():
                qid=known.setdefault(k,'uq'+w.digest(k)[:12])
                q=qs.setdefault(qid,{'id':qid,'question_text':item['text'],'periods':[]})
                per=next((x for x in q['periods'] if x['date']==date),None)
                if per is None:
                    per={'id':'up_'+batch+'_'+str(len(groups)+1).zfill(4),'date':date,'answer_count':0,'batch_id':batch};q['periods'].append(per)
                    groups.append({'question_id':qid,'period_id':per['id'],'question_text':q['question_text'],'date':date,'answers':[]})
                g=next(x for x in groups if x['question_id']==qid and x['period_id']==per['id'])
                g['answers']+=item['answers'];per['answer_count']+=len(item['answers'])
    w.require(groups and all(g['answers'] for g in groups),'新题必须有完整答案，不以问题清单或摘要代替')
    staging=target.with_name('.'+batch+'-'+uuid.uuid4().hex[:8]);staging.mkdir(parents=True)
    try:
        manifest={'contract':CONTRACT,'batch_id':batch,'created_at':w.now(),'answer_files':[],'source_files':[],
                  'positioning_policy':'reuse_confirmed_positioning_without_reassessment'}
        for f,h,imp in imports:
            rel='inputs/answers/'+h[:16]+f.suffix.lower();dest=staging/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
            manifest['answer_files'].append({'path':rel,'sha256':h,'original_name':f.name,'warnings':imp.get('warnings',[])})
        sh=set()
        for file in sources:
            f=Path(file).expanduser().resolve();h=w.hashfile(f);w.require(h not in sh,'同批信源文件重复');sh.add(h)
            rel='inputs/sources/'+h[:16]+f.suffix.lower();dest=staging/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
            manifest['source_files'].append({'path':rel,'sha256':h,'original_name':f.name})
        w.write(staging/'all_answers.json',groups);w.write(staging/'question_catalog.json',list(qs.values()));w.write(staging/'manifest.json',manifest)
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging);raise
    return {'batch_id':batch,'questions':len(qs),'question_periods':len(groups),'answers':sum(len(x['answers']) for x in groups),
            'sources':len(sources),'status':'ready','positioning':'已确认定位沿用；新数据仅作为本轮问题优化输入'}

def load(w,p,batch):
    w.ident(batch);d=folder(p,batch);manifest=w.read(d/'manifest.json')
    w.require(manifest['batch_id']==batch and manifest['contract']==CONTRACT,'上传批次合同不匹配')
    for f in manifest['answer_files']+manifest['source_files']:
        w.require((d/f['path']).is_file() and w.hashfile(d/f['path'])==f['sha256'],'上传原文件已变，请以新批次导入修正版')
    return manifest

def dependencies(w,p,batch):
    d=folder(p,batch);m=load(w,p,batch)
    fs=[d/'manifest.json',d/'all_answers.json',d/'question_catalog.json']+[d/x['path'] for x in m['answer_files']+m['source_files']]
    return {f.relative_to(p).as_posix():w.hashfile(f) for f in fs}

def available(w,p):
    out=json.loads(w.dump(w.catalog(p)));byid={q['id']:q for q in out}
    mapping={x['question_id']:x for x in w.result(p,2)['question_map']} if w.done(p,2) else {}
    for q in out:
        for per in q['periods']:
            m=mapping.get(q['id'],{});per.update(batch_id=None,category=m.get('category'),available=bool(m and m.get('fit')!='out_of_scope'))
    for d in batch_dirs(p):
        load(w,p,d.name)
        for q in w.read(d/'question_catalog.json'):
            dest=byid.get(q['id'])
            if dest is None:dest={'id':q['id'],'question_text':q['question_text'],'periods':[]};out.append(dest);byid[q['id']]=dest
            for per in q['periods']:dest['periods'].append({**per,'batch_id':d.name,'available':True,'category':mapping.get(q['id'],{}).get('category')})
    return out

def resolve(w,p,qid,pid):
    q=next((x for x in available(w,p) if x['id']==qid),None);w.require(q,'请从已有或新上传的问题目录选择')
    per=next((x for x in q['periods'] if x['id']==pid),None);w.require(per and per['available'],'期次不存在或原目录已排除该题')
    return q,per

def answers(w,p,qid,pid):
    q,per=resolve(w,p,qid,pid);f=folder(p,per['batch_id'])/'all_answers.json' if per['batch_id'] else Path(p)/'inputs/all_answers.json'
    return next(g for g in w.read(f) if g['question_id']==qid and g['period_id']==pid)

def mapping(w,p,a):
    s=w.selected(p,a);pos=w.result(p,2)
    old=next((x for x in pos['question_map'] if x['question_id']==s['question_id']),None)
    if old:return old
    return {'question_id':s['question_id'],'category':None,'branch_ids':[pos['taxonomy'][0]['id']]}

def source_files(w,p,q,per):
    if not per.get('batch_id'):return []
    d=folder(p,per['batch_id']);m=load(w,p,per['batch_id']);result=[]
    from shared.article_pool import read_details
    date=None if per['date']=='undated' else per['date']
    context={'question_text':q['question_text'],'period_id':per['id'],'observed_from':date,'observed_to':date}
    for item in m['source_files']:
        f=d/item['path']
        try:read_details(f,context,explicit_period=per['id'])
        except ValueError:continue
        result.append(str(f))
    return result

def article_dependencies(w,p,a):
    out={};meta=w.scope(p,a)/'question_input_context.json'
    for f in [w.scope(p,a)/'question_answers.json',meta]:
        if f.exists():out[f.relative_to(p).as_posix()]=w.hashfile(f)
    batch=w.read(meta).get('batch_id') if meta.exists() else w.result(p,4,a).get('batch_id') if w.done(p,4,a) else None
    if batch:out.update(dependencies(w,p,batch))
    return out
