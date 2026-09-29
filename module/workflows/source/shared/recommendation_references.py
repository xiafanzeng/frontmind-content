"""A replaceable P01 example pair, kept separate from length and fact sources."""
import hashlib
import json
from pathlib import Path
from .example_acquisition import ExampleStore


def register(wf, root, job):
    folder = Path(root) / 'resources/p01_recommendation'
    manifest = json.loads((folder / 'manifest.json').read_text())
    store = ExampleStore(job)
    rows = []
    for item in manifest['examples']:
        body_path = folder / item['body']
        if body_path.is_file():
            body = body_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != item['sha256']:
                raise ValueError('P01 完整例文与登记内容不一致')
            record = store._save((folder / item['raw']).read_bytes(), body.decode(), {
                'title': item['title'], 'obtained_via': 'bundled_http_snapshot',
                'original_url': item['url'], 'final_url': item['url'],
                'http_status': 200, 'content_type': 'text/html', 'completeness': 'complete',
                'acquisition_status': 'complete', 'source_fetched_at': item['fetched_at'],
                'integrity_note': 'Original HTTP response and full article text captured and read together; a writing reference, not a factual source.'})
        else:
            # Distributable program retains the chosen source configuration;
            # fetch the full original into the task's immutable source store.
            record = store.acquire_http(item['url'], encoding=item.get('encoding'),
                                        article_tokens=item.get('article_tokens', []))
            store.resolve(record['artifact_id'], require_complete=True)
        rows.append({'artifact_id': record['artifact_id'], 'reference_role': item['role'],
                     'style_analysis': item['style_analysis']})
    return wf.save_examples(job, rows, 'question')
