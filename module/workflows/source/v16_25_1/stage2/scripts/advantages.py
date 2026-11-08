"""Read-only confirmed advantages imported from the three-item Pack."""
from pathlib import Path
import re
CONTRACT = 'frontmind-brand-advantages/16.19'

def folder(p):
    return Path(p) / 'reference_pack' / 'differentiation'


def snapshot(w, p, snapshot_id=None):
    if snapshot_id is None:
        f = folder(p) / 'confirmed.json'
        w.require(f.is_file(), '先在C确认本次写作优势；旧文章继续使用其已绑定版本')
        snapshot_id = w.read(f).get('snapshot_id')
    w.require(isinstance(snapshot_id, str) and re.fullmatch(r'[a-f0-9]{64}', snapshot_id), '优势版本ID格式不正确')
    f = folder(p) / 'snapshots' / (snapshot_id + '.json')
    w.require(f.is_file(), '指定优势版本不存在；保留旧版本文件，不改写原文章')
    value = w.read(f); payload = {k: v for k, v in value.items() if k != 'snapshot_id'}
    w.require(value.get('contract') == CONTRACT and value.get('snapshot_id') == snapshot_id and w.digest(w.dump(payload)) == snapshot_id,
              '已保存优势版本内容发生变化，不覆盖原文章依赖')
    return value


def dependencies(w, p, snapshot_id=None):
    value = snapshot(w, p, snapshot_id)
    f = folder(p) / 'snapshots' / (value['snapshot_id'] + '.json')
    return {f.relative_to(p).as_posix(): w.hashfile(f)}
