"""Readable source reports from the current question's actual citation detail rows."""
from __future__ import annotations
import csv
import io
from pathlib import Path


def cell(value):
    return str(value if value is not None else '未提供').replace('|', '／').replace('\n', '；')


def article_link(item):
    title = cell(item.get('content_title') or item.get('title') or '未提供标题').replace('[', '［').replace(']', '］')
    url = item.get('canonical_url') or item.get('url')
    return '[' + title + '](' + str(url).replace('(', '%28').replace(')', '%29') + ')' if url else title


def paths(w, p, a):
    directory = w.scope(p, a) / 'source_reports'
    return {'report_txt': str((directory / '本题信源列表.txt').resolve()),
            'all_articles_csv': str((directory / '全部引用文章.csv').resolve())}


def source_view(w, p, a):
    directory = w.scope(p, a)
    rows = w.read(directory / 'source_details.json')
    pool = w.sourcepool(p, a)
    actual = w.build_pool(rows)
    w.require(len(rows) == pool['citation_count'] == actual['citation_count'], '本题信源条数与逐条明细不一致')
    w.require(pool['articles'] == actual['articles'], '本题文章池与逐条信源不一致，不能展示旧表')
    selected_file = w.stepdir(p, 4, a) / 'result.json'
    selected = w.read(selected_file) if selected_file.exists() else {}
    dates = sorted({str(x['observed_date']) for x in rows if x.get('observed_date')})
    platforms = sorted({str(x.get('model') or x.get('platform')) for x in rows if x.get('model') or x.get('platform')})
    return {'question_text': selected.get('question_text', ''), 'answer_status': selected.get('answer_status', ''),
            'answer_count': selected.get('answer_count', 0), 'answer_from': selected.get('observed_from'),
            'answer_to': selected.get('observed_to'), 'source_dates': dates,
            'source_from': dates[0] if dates else selected.get('source_observed_from'),
            'source_to': dates[-1] if dates else selected.get('source_observed_to'),
            'citation_count': len(rows), 'article_count': actual['article_count'], 'media_count': len(actual['media']),
            'platforms': platforms, 'media': sorted(actual['media'], key=lambda x: -x['citation_count']),
            'top20': actual['top20'], 'articles': actual['articles'], 'method': actual['method'], 'files': paths(w, p, a)}


def _period(start, end):
    return str(start or '未提供') if not end or start == end else f'{start or "未提供"} 至 {end}'


def render_sources(view):
    answer = '明确本次暂无回答' if view.get('answer_status') == 'not_provided' else '已提供完整回答'
    lines = ['## 本题信源列表', '', '| 项目 | 本题实际数据 |', '|---|---|',
             '| 问题 | ' + cell(view['question_text']) + ' |',
             '| 回答日期 | ' + cell(_period(view['answer_from'], view['answer_to'])) + ' |',
             '| 回答状态／份数 | ' + answer + '／' + str(view['answer_count']) + ' |',
             '| 信源逐条记录日期 | ' + cell(_period(view['source_from'], view['source_to'])) + ' |',
             f'| 引用记录／去重文章／媒体 | {view["citation_count"]}条／{view["article_count"]}篇／{view["media_count"]}家 |',
             '', view['method'],
             '统计仅取本题关联的逐条引用明细；汇总页的日期标签不代替记录日期。某平台没有明细不表示该平台没有引用。',
             '', '### 本题媒体统计', '', '| 媒体 | 去重文章数 | 引用次数 |', '|---|---:|---:|']
    lines += ['| ' + ' | '.join(cell(row[k]) for k in ['media', 'article_count', 'citation_count']) + ' |' for row in view['media']]
    lines += ['', f'### 本题引用文章 Top{len(view["top20"])}', '',
              '| 引用排名 | 文章标题及原文链接 | 媒体 | 引用次数 |', '|---:|---|---|---:|']
    for row in view['top20']:
        lines.append(f'| {row["raw_rank"]} | {article_link(row)} | {cell(row["media"])} | {row["citation_count"]} |')
    lines += ['', '引用排名决定候选池，不代表内容质量或推荐顺序。']
    for label, key in [('完整信源报告 TXT', 'report_txt'), ('全部引用文章 CSV', 'all_articles_csv')]:
        path = view.get('files', {}).get(key)
        if path and Path(path).is_file():
            lines.append(f'[{label}](<{path}>)')
    return '\n'.join(lines) + '\n'


def write_sources(w, p, a):
    view, files = source_view(w, p, a), paths(w, p, a)
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(['引用排名', '文章ID', '文章标题', '原文链接', '媒体', '引用次数'])
    for item in view['articles']:
        writer.writerow([item['raw_rank'], item['article_id'], item['content_title'], item['canonical_url'], item['media'], item['citation_count']])
    w.write(Path(files['all_articles_csv']), '\ufeff' + buffer.getvalue())
    w.write(Path(files['report_txt']), render_sources(view))
    return files
