"""Private, stage-three-only China.com source acquisition and pinned snapshots.

No synthesized body, search snippet, or cross-domain reprint is accepted as an
original. A first successful capture is pinned by raw/body hashes in this Job;
that is acquisition integrity, NOT a claim of human quality certification.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request
import urllib.parse
from lxml import html as lh
from .editorial_contracts import EditorialContractError
from .brand_stage import CONTRACT, REFERENCE_IDS

SNAPSHOT = 'inputs/brand_references'
LIMIT = 8 * 1024 * 1024


def _sha(data):
    return hashlib.sha256(data.encode('utf-8') if isinstance(data,str) else data).hexdigest()


def _read_json(path):
    try:
        if path.is_symlink(): raise ValueError('symlink')
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict): raise ValueError('object')
        return value
    except (OSError,ValueError) as e:
        raise EditorialContractError('brand_reference_manifest','例文清单缺失或损坏') from e


def _valid_url(url):
    p=urllib.parse.urlsplit(url)
    host=p.hostname or ''
    if p.scheme!='https' or not (host=='china.com' or host.endswith('.china.com')) or p.username or p.password or p.port not in (None,443):
        raise EditorialContractError('brand_reference_origin','固定例文只能从已列明的中华网HTTPS页面取得')
    return url


class _ChinaRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _valid_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def extract(raw, spec):
    """Use actual article containers, not page-wide 404 or advertising text."""
    try:
        tree=lh.fromstring(raw)
        titles=tree.xpath('//title/text() | //h1//text()')
        key=spec['title_key']
        if key not in ''.join(titles) and key not in tree.text_content()[:1800]:
            raise ValueError('title mismatch')
        for bad in tree.xpath('//script|//style|//nav|//footer|//noscript'):
            bad.drop_tree()
        # Smallest ancestor containing the known section/end anchors is robust
        # to desktop/mobile containers, while excluding unrelated page modules.
        anchors=spec['section_keys']+[spec['end_key']]
        nodes=[]
        for node in tree.xpath('//article|//main|//div|//section'):
            text=node.text_content()
            if all(a in text for a in anchors) and len(node.xpath('.//p'))>=5:
                nodes.append((len(text),node))
        if not nodes: raise ValueError('complete article region missing')
        node=min(nodes,key=lambda x:x[0])[1]
        paragraphs=[]
        for p in node.xpath('.//p|.//h2|.//h3'):
            text=re.sub(r'\s+',' ',p.text_content()).strip()
            if text.startswith(('免责声明','责任编辑','文章投诉','本文仅供','本网站上的内容')): break
            if not text or text==spec['title'] or text.startswith('来源：'): continue
            if '\ufffd' in text: raise ValueError('encoding')
            if p.tag in {'h2','h3'}: text='## '+text
            paragraphs.append(text)
        body='\n\n'.join(paragraphs)+'\n'
        if len(body)<800 or not all(a in body for a in anchors):
            raise ValueError('incomplete article')
        # The last anchor is an observed closing phrase, not a made-up checksum.
        end_index=next(i for i,p in reversed(list(enumerate(paragraphs))) if spec['end_key'] in p)
        body='\n\n'.join(paragraphs[:end_index+1])+'\n'
        return body
    except Exception as e:
        raise EditorialContractError('brand_reference_incomplete','例文标题、正文区域或首尾校验未通过；不能使用摘要代替全文') from e


def _fetch(spec):
    if spec.get("fetch_mode") == "pinned_china_article_v1":
        from . import p0_style
        example={"fetch":{"url":spec["source_url"],"content_sha256":spec["content_sha256"]}}
        body=p0_style._fetch(example)
        return body.encode("utf-8"), body, spec["source_url"]
    failures=[]
    for url in dict.fromkeys(u for u in (spec.get('source_url'),spec.get('alternate_source_url')) if u):
        _valid_url(url)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'FrontMind-ReferenceReader/4.12.5','Accept':'text/html'})
            with urllib.request.build_opener(_ChinaRedirect()).open(req,timeout=30) as response:
                final=_valid_url(response.url)
                raw=response.read(LIMIT+1)
            if len(raw)>LIMIT: raise ValueError('oversize')
            return raw,extract(raw,spec),final
        except Exception as e:
            failures.append(getattr(e,'code',type(e).__name__))
    raise EditorialContractError('brand_reference_fetch_failed',f"{spec['id']}完整例文未取得（{','.join(map(str,failures))}）；停在第三遍，保留初稿与E8，不使用摘要或改写稿代替")


def job_examples(package_root,job_root,*,freeze=False):
    package_root,job_root=Path(package_root),Path(job_root)
    source=package_root/'resources/p0_brand_stage/manifest.json'
    specs=_read_json(source)
    if specs.get('contract_version')!=CONTRACT or tuple(x.get('id') for x in specs.get('examples',[]))!=REFERENCE_IDS:
        raise EditorialContractError('brand_reference_manifest','固定两篇例文清单与本版合同不一致')
    state=_read_json(job_root/'job_state.json')
    offline=(state.get('flags') or {}).get('offline_fixture') is True
    target=job_root/SNAPSHOT
    if target.is_symlink():
        raise EditorialContractError('brand_reference_path','例文快照不能是符号链接')
    index=target/'manifest.json'
    if not index.exists():
        if not freeze: raise EditorialContractError('brand_reference_missing','尚未进入第三遍并取得完整例文')
        if target.exists(): raise EditorialContractError('brand_reference_partial','例文快照不完整；不覆盖未知已有内容')
        target.parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='.brand-reference-',dir=target.parent))
        records=[]
        try:
            for spec in specs['examples']:
                guide_path=spec.get('guide_path')
                guide=(source.parent/guide_path).read_text(encoding='utf-8') if guide_path else spec.get('guide','')
                if offline:
                    body=('离线合成例文，仅测试流程，不代表任何真实网页。'+spec['id']+'\n\n')*12
                    raw=body.encode();final='offline://synthetic/'+spec['id'];method='offline_simulated'
                elif spec.get('body_path'):
                    src=source.parent/spec['body_path']
                    body=src.read_text(encoding='utf-8')
                    if _sha(body)!=spec.get('content_sha256'):
                        raise EditorialContractError('brand_reference_changed','港隽用户原始例文与已批准版本不一致')
                    raw=body.encode('utf-8');final='user-provided://gangjun';method='user_original'
                else:
                    raw,body,final=_fetch(spec);method='http_original'
                bp=spec['id']+'.md';hp=spec['id']+'.html'
                (staging/bp).write_text(body,encoding='utf-8');(staging/hp).write_bytes(raw)
                records.append(dict(id=spec['id'],title=spec['title'],publication=spec['publication'],source_url=spec.get('source_url','user-provided://gangjun'),final_url=final,body_path=bp,raw_path=hp,sha256=_sha(body),raw_sha256=_sha(raw),guide=guide,guide_sha256=_sha(guide),method=method))
            manifest=dict(contract_version=CONTRACT,source_manifest_sha256=_sha(source.read_bytes()),execution_mode='offline_simulated' if offline else 'production',capture_integrity='raw_and_extracted_body_hashes',human_source_acceptance=False,examples=records)
            (staging/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            os.replace(staging,target)
        finally:
            if staging.exists():shutil.rmtree(staging)
    saved=_read_json(index)
    if saved.get('source_manifest_sha256')!=_sha(source.read_bytes()) or saved.get('contract_version')!=CONTRACT:
        raise EditorialContractError('brand_reference_changed','例文选择已经改变，需要显式迁移第三遍快照，不能复用旧稿')
    if saved.get('execution_mode')!=('offline_simulated' if offline else 'production'):
        raise EditorialContractError('brand_reference_mode','离线夹具不得进入真实写作')
    records=saved.get('examples',[])
    if tuple(r.get('id') for r in records)!=REFERENCE_IDS:
        raise EditorialContractError('brand_reference_changed','例文数量或身份已改变')
    output=[]
    for spec,r in zip(specs['examples'],records):
        bp=target/(r['id']+'.md');hp=target/(r['id']+'.html')
        if bp.is_symlink() or hp.is_symlink() or not bp.is_file() or not hp.is_file():
            raise EditorialContractError('brand_reference_missing','原始例文与提取正文快照缺失')
        body=bp.read_text(encoding='utf-8')
        guide_path=spec.get('guide_path')
        guide=(source.parent/guide_path).read_text(encoding='utf-8') if guide_path else spec.get('guide','')
        if _sha(body)!=r.get('sha256') or _sha(hp.read_bytes())!=r.get('raw_sha256') or r.get('guide_sha256')!=_sha(guide):
            raise EditorialContractError('brand_reference_changed','例文快照或指南校验失败，不继续写作')
        output.append({**r,'text':body,'path':str(bp),'guide':guide})
    return output


def render(records):
    return '\n\n'.join('## 写法参考 '+r['id']+'：'+r['title']+'\n来源：'+r['source_url']+'\n'+r['publication']+'\n\n<reference_text>\n'+r['text']+'\n</reference_text>\n\n编辑参考：'+r['guide'] for r in records)
