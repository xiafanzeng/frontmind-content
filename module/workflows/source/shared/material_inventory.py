"""Version the controller's appendable catalog without weakening source checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

INDEX_PATH = 'inputs/user_materials/index.json'
SNAPSHOT_DIR = 'artifacts/material_inventory'


def _safe_path(job: Path, relative: str) -> Path:
    job = Path(job).resolve()
    path = job / relative
    cursor = job
    for part in path.relative_to(job).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError('material inventory path contains a symlink')
    if not path.resolve().is_relative_to(job):
        raise ValueError('material inventory path escapes the Job')
    return path


def _store(job: Path, raw: bytes, expected: str) -> Path:
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('historical material inventory bytes do not match')
    path = _safe_path(job, f'{SNAPSHOT_DIR}/{expected}.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(raw)
        path.chmod(0o444)
    except FileExistsError:
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('historical material inventory snapshot changed')
    return path


def preserve_current(job: Path) -> Path | None:
    """Called before the controller appends new supplemental material."""
    path = _safe_path(job, INDEX_PATH)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    return _store(job, raw, hashlib.sha256(raw).hexdigest())


def historical_path(job: Path, expected: str) -> Path:
    """Return only bytes proven identical to the catalog a saved action saw.

    Earlier releases overwrote the catalog without a snapshot. Their catalog
    was serialized by atomic_json after appending items, so an exact prefix can
    recover the original bytes. A digest mismatch never becomes a semantic
    comparison or permission to ignore a changed source.
    """
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('invalid material inventory digest')
    snapshot = _safe_path(job, f'{SNAPSHOT_DIR}/{expected}.json')
    if snapshot.exists():
        if not snapshot.is_file() or hashlib.sha256(snapshot.read_bytes()).hexdigest() != expected:
            raise ValueError('historical material inventory snapshot changed')
        return snapshot
    current = _safe_path(job, INDEX_PATH)
    raw = current.read_bytes()
    if hashlib.sha256(raw).hexdigest() == expected:
        return current
    value = json.loads(raw)
    if (not isinstance(value, dict)
            or value.get('artifact_type') != 'frontmind_positioning_user_materials'
            or not isinstance(value.get('schema_version'), str)
            or not isinstance(value.get('items'), list)
            or any(not isinstance(item, dict) for item in value['items'])):
        raise ValueError('historical material inventory is unavailable')
    items = value['items']
    for length in range(len(items) - 1, -1, -1):
        candidate = {**value, 'items': items[:length]}
        previous = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        if hashlib.sha256(previous).hexdigest() == expected:
            return _store(job, previous, expected)
    raise ValueError('historical material inventory is unavailable')
