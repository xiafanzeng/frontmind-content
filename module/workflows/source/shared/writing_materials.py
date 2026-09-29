"""Explicit, persistent factual selection for a newly requested manuscript edit."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

CONTRACT = 'explicit-writing-materials-v1'
FIELDS = {'writing_material_markdown', 'material_adjustments', 'writing_material_sources'}


def _digest(content):
    wire = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(wire.encode('utf-8')).hexdigest()


def _content(value):
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError('事实选材 JSON 仅使用 writing_material_markdown、material_adjustments、writing_material_sources')
    body = value.get('writing_material_markdown')
    if not isinstance(body, str) or not body.strip():
        raise ValueError('事实选材须包含非空 writing_material_markdown')
    notes = value.get('material_adjustments', [])
    sources = value.get('writing_material_sources', [])
    if not isinstance(notes, list) or any(not isinstance(x, str) or not x.strip() for x in notes):
        raise ValueError('material_adjustments 须为文字数组，可为空')
    if not isinstance(sources, list) or any(not isinstance(x, dict) or
            not isinstance(x.get('source_ref'), str) or not x['source_ref'].strip() or
            not isinstance(x.get('use'), str) or not x['use'].strip() for x in sources):
        raise ValueError('writing_material_sources 须为含 source_ref 与 use 的对象数组，可为空')
    return {'writing_material_markdown': body, 'material_adjustments': notes, 'writing_material_sources': sources}


def read_input(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('事实选材入口须为普通文件或目录')
    if path.is_dir():
        choices = [path/name for name in ('writing_materials.json', 'writing_materials.md') if (path/name).exists()]
        if len(choices) != 1:
            raise ValueError('事实选材目录须且只能有 writing_materials.json 或 writing_materials.md 一个入口')
        path = choices[0]
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {'.json', '.md'}:
        raise ValueError('事实选材须为 UTF-8 JSON 或 Markdown 文件')
    text = path.read_text(encoding='utf-8')
    content = _content(json.loads(text) if path.suffix.lower() == '.json' else {'writing_material_markdown': text})
    return {'contract': CONTRACT, 'source_name': path.name, 'content': content, 'sha256': _digest(content)}


def validate(value):
    if not isinstance(value, dict) or value.get('contract') != CONTRACT:
        raise ValueError('冻结事实选材格式无效')
    content = _content(value.get('content'))
    if value.get('sha256') != _digest(content):
        raise ValueError('冻结事实选材与保存内容不一致')
    return value


def from_revision(revision):
    value = (revision or {}).get('writing_materials')
    return validate(value) if value is not None else None


def freeze(previous_revision, replacement=None):
    value = validate(replacement) if replacement is not None else from_revision(previous_revision)
    return copy.deepcopy(value) if value is not None else None


def selected(revision, blueprint):
    value = from_revision(revision)
    return value['content'] if value else blueprint
