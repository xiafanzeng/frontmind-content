"""测试专用：从公开合成材料建立有效资料包，不读取客户目录。"""
from pathlib import Path
import atexit
import json
import tempfile
import zipfile
_cache = None
def reference_pack():
    global _cache
    if _cache is not None: return _cache
    from scripts.tests_v411 import test_workflow_v411 as legacy
    temp = tempfile.TemporaryDirectory(prefix='frontmind-synthetic-pack-');atexit.register(temp.cleanup)
    job=Path(temp.name)/'positioning'
    manifest=json.loads((legacy.FIXTURE/'manifest.json').read_text(encoding='utf-8'))
    legacy.run_cli('reference-pack','create','--brand',manifest['brand'],'--input',str(legacy.FIXTURE/'brand_material.md'),'--job-dir',str(job),'--offline-fixture')
    legacy.confirm_competitors(job);legacy.resume(job,'--confirm-core-positioning')
    folder=job/'deliverables/Reference_Pack_v1';pack=Path(temp.name)/'synthetic.zip'
    with zipfile.ZipFile(pack,'w',zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(folder).as_posix())
    _cache=pack;return pack
