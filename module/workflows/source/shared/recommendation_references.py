"""Replaceable user-selected style examples, separate from factual sources."""
import hashlib
import json
import re
from pathlib import Path
from .example_acquisition import ExampleStore, AcquisitionError

STYLE_PROFILE = 'frontmind-selected-pattern-examples/20261011'


def profile_enabled(state):
    return (state.get('job_kind') == 'article'
            and state.get('metadata', {}).get('pattern_example_profile') == STYLE_PROFILE)


def profile_items(root, pattern):
    folder = Path(root) / 'resources/selected_pattern_examples_20261011'
    profile = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    return folder, profile['patterns'][pattern]


def register_selected(wf, root, job):
    """Freeze the user's chosen text references through the existing example node."""
    state = wf.load_state(job)
    _, entry = profile_items(root, state['selected_pattern_id'])
    store, rows = ExampleStore(job), []
    for item in entry['examples']:
        local = Path(root) / item['body'] if item.get('body') else None
        if local and local.is_file():
            body = local.read_bytes()
            if item.get('sha256') and hashlib.sha256(body).hexdigest() != item['sha256']:
                raise ValueError('随包例文与登记内容不一致')
            obtained = 'bundled_user_selected_text'
        else:
            from .host_tools import HostTools
            try:
                acquired = store.acquire_http(item['url'], encoding=item.get('encoding'),
                                              article_tokens=item.get('article_tokens', []))
            except AcquisitionError:
                acquired = None
            if acquired is None or acquired.get('completeness') != 'complete':
                returned = HostTools(root, job, 'answer_analysis').execute(
                    'web_read', {'url': item['url'], 'method': 'reader'})
                acquired = store.resolve(returned['artifact_id'], require_complete=True)
            text = (Path(job) / acquired['text_path']).read_text(encoding='utf-8')
            text = text_only_reference(text, item)
            body = text.encode('utf-8')
            obtained = 'user_selected_article_text'
        record = store._save(body, body.decode('utf-8'), {
            'title': item['title'], 'obtained_via': obtained,
            'original_url': item['url'], 'final_url': item['url'],
            'content_type': 'text/markdown', 'completeness': 'complete',
            'acquisition_status': 'complete', 'source_observed_at': item['fetched_at'],
            'integrity_note': 'User-selected article text; images and page furniture omitted. Style reference only.'})
        rows.append({'artifact_id': record['artifact_id'], 'reference_role': item['role'],
                     'style_analysis': item['style_analysis']})
        if state.get('flags', {}).get('offline_fixture'):
            rows[-1].update(markdown=body.decode('utf-8'), title=item['title'], url=item['url'],
                            source='offline_selected_reference')
    registered = wf.save_examples(job, rows, 'question')
    apply_selected_defaults(wf, root, job)
    return registered


def apply_selected_defaults(wf, root, job):
    """Apply type-specific suggestions without overwriting explicit requirements."""
    state = wf.load_state(job)
    _, entry = profile_items(root, state['selected_pattern_id'])
    meta = state.setdefault('metadata', {})
    current = meta.setdefault('effective_writing_requirements', {})
    for field, previous in meta.get('pattern_example_defaults', {}).items():
        if current.get(field) == previous:
            current.pop(field)
    defaults = {'estimated_length': entry['estimated_length'],
                'formatting': '纯文字正文，保留自然段和小标题，不插入图片、图注或配图占位。'}
    owned = {}
    for field, default in defaults.items():
        if field not in current:
            current[field] = owned[field] = default
    meta['pattern_example_defaults'] = owned
    state['metadata']['pattern_example_note'] = entry.get('genre_note', '')
    state['metadata']['pattern_example_selection'] = {
        'profile': STYLE_PROFILE, 'pattern_id': state['selected_pattern_id'],
        'titles': [item['title'] for item in entry['examples']],
        'urls': [item['url'] for item in entry['examples']], 'text_only': True}
    wf.save_state(job, state)


def text_only_reference(text, item):
    """Keep the article text while omitting visual and webpage-only material."""
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'<img\b[^>]*>', '', text, flags=re.I)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'(?m)^\s*#{1,6}\s+', '', text)
    text = text.replace('**', '').replace('__', '')
    start, end = item.get('body_start'), item.get('body_end')
    if start and start in text:
        text = text[text.index(start):]
    if end and end in text:
        text = text[:text.rindex(end) + len(end)]
    text = re.sub(r'(?m)^.*(?:打开网易新闻 查看精彩图片|返回搜狐，查看更多|展开全文).*$','',text)
    omitted = set(item.get('omit_lines', []))
    prefixes = tuple(item.get('omit_line_prefixes', []))
    text = '\n'.join(line for line in text.splitlines()
                     if line.strip() not in omitted
                     and not (prefixes and line.strip().startswith(prefixes)))
    text = re.sub(r'(?m)>>\s*$', '', text)
    return re.sub(r'\n\s*\n(?:\s*\n)+', '\n\n', text).strip() + '\n'


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
