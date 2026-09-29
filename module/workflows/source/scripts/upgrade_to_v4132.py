#!/usr/bin/env python3
"""Apply the selected 4.13.0/4.13.1 -> 4.13.2 delta; preserve configs and jobs.

Default is a dry-run. Exact-context hunks may merge unrelated local changes;
ambiguous/conflicting files stop the entire plan before writes. No API calls.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = {'config', 'jobs', '.venv', 'workspace', 'workspace_data'}
PROTECTED_FILES = {'shared/managed_runtime.py', 'shared/responses_runtime.py', 'requirements.txt'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merge_hunks(current: bytes, hunks: list[dict]) -> bytes:
    for hunk in hunks:
        before=base64.b64decode(hunk['before'], validate=True)
        after=base64.b64decode(hunk['after'], validate=True)
        if before and current.count(before)==1:
            current=current.replace(before,after,1)
        elif after and current.count(after)==1 and (not before or before not in current):
            continue  # hunk already applied, including a resumed dry-run plan
        else:
            raise ValueError('补丁上下文冲突或不唯一，未覆盖本地文件')
    return current


def safe_file(root: Path, relative: str) -> Path:
    path=PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative or not path.parts:
        raise ValueError('升级清单包含不安全路径')
    if path.parts[0] in PROTECTED or relative in PROTECTED_FILES:
        raise ValueError('升级清单试图修改受保护配置、任务或未变更的供应商依赖文件')
    result=root.joinpath(*path.parts)
    for item in [result,*result.parents]:
        if item==root:break
        if item.is_symlink():raise ValueError('升级路径含符号链接，未写入：'+relative)
    return result


def prepare(target: Path, manifest: dict, release: Path=ROOT) -> list[dict]:
    plans=[]
    for item in manifest['files']:
        relative=item['path'];dest=safe_file(target,relative);source=safe_file(release,relative)
        content=source.read_bytes()
        if sha(content)!=item['new_sha256']:raise ValueError('发行文件指纹不匹配：'+relative)
        old=dest.read_bytes() if dest.is_file() else None
        if old is not None and sha(old)==item['new_sha256']:continue
        if item['base_sha256'] is None:
            if dest.exists():raise ValueError('新增文件与本地已有文件冲突：'+relative)
            merged=content;kind='新增'
        elif old is None:
            raise ValueError('基线文件缺失：'+relative)
        elif sha(old)==item['base_sha256']:
            merged=content;kind='更新'
        else:
            if not item.get('hunks'):raise ValueError('本地二进制或删除文件冲突：'+relative)
            merged=merge_hunks(old,item['hunks']);kind='保留本地差异并合并'
            if merged==old:continue
        if relative.endswith('.py'):compile(merged,relative,'exec')
        if relative.endswith('.json'):json.loads(merged)
        plans.append({'path':relative,'dest':dest,'before':old,'content':merged,'kind':kind,'mode':item.get('mode',0o644)})
    return plans


def apply(plans: list[dict],target:Path) -> Path | None:
    if not plans:return None
    backup=target/'.frontmind-upgrade-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True,exist_ok=False)
    saved=[]
    try:
        # Re-check every file before touching any, catching edits after planning.
        for plan in plans:
            actual=plan['dest'].read_bytes() if plan['dest'].is_file() else None
            if actual!=plan['before']:raise ValueError('计划后文件又被修改：'+plan['path'])
            if actual is not None:
                copy=backup/plan['path'];copy.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(plan['dest'],copy)
        for plan in plans:
            dest=plan['dest'];dest.parent.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(prefix='.fm-upgrade-',dir=dest.parent)
            try:
                with os.fdopen(fd,'wb') as f:f.write(plan['content']);f.flush();os.fsync(f.fileno())
                os.chmod(tmp,plan['mode']);os.replace(tmp,dest);saved.append(plan)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
    except BaseException:
        for plan in reversed(saved):
            if plan['before'] is None:plan['dest'].unlink(missing_ok=True)
            else:shutil.copy2(backup/plan['path'],plan['dest'])
        raise
    (backup/'upgrade_receipt.json').write_text(json.dumps({'version':'4.13.2','files':[{'path':p['path'],'sha256':sha(p['content']),'mode':p['kind']} for p in plans]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return backup


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',help='执行已检查的差异计划；默认仅显示')
    args=parser.parse_args();target=args.target.expanduser().resolve()
    if target==ROOT:raise ValueError('目标应为原工作目录；全新目录不必对自身升级')
    if not (target/'shared/workflow_versions.py').is_file():raise ValueError('不是FrontMind程序目录')
    version_source=(target/'shared/workflow_versions.py').read_text(encoding='utf-8')
    match=re.search(r'^RELEASE_VERSION\s*=\s*["\'](4\.13\.[012])["\']',version_source,re.MULTILINE)
    if not match:
        raise ValueError('只支持4.13.0或4.13.1到4.13.2的差异升级')
    source_version=match.group(1)
    manifest=json.loads((ROOT/'UPGRADE_v4.13.2.json').read_text(encoding='utf-8'))
    baseline=source_version if source_version!='4.13.2' else '4.13.1'
    plans=prepare(target,manifest['baselines'][baseline])
    # The manifest cannot hash itself. Copy its already-read exact bytes as a
    # separate planned member so the upgraded directory remains self-contained.
    manifest_name="UPGRADE_v4.13.2.json"
    manifest_bytes=(ROOT/manifest_name).read_bytes()
    manifest_target=safe_file(target,manifest_name)
    manifest_before=manifest_target.read_bytes() if manifest_target.is_file() else None
    if manifest_before not in (None,manifest_bytes):
        raise ValueError("目标中已有不同的4.13.2升级清单，未覆盖")
    if manifest_before is None:
        plans.append({"path":manifest_name,"dest":manifest_target,"before":None,"content":manifest_bytes,"kind":"新增清单","mode":0o644})
    result={'status':'dry_run','planned_files':len(plans),'files':[{'path':p['path'],'action':p['kind']} for p in plans],
            'source_version':source_version, 'target_version':'4.13.2',
            'preserved':'config、jobs、failed_attempts及可精确合并的本地改动；本版更新agents_runtime/host_tools，冲突先停，绝不猜测覆盖。先暂停目标目录活动任务。'}
    if args.apply:
        backup=apply(plans,target);result.update(status='applied' if plans else 'already_current',backup=str(backup) if backup else None)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as error:
        print(json.dumps({'status':'blocked','error':str(error)},ensure_ascii=False),file=sys.stderr);sys.exit(2)
