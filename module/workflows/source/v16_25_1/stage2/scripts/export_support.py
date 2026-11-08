"""Small shared Markdown block reader for equivalent Word/HTML delivery."""
from __future__ import annotations
import html
import os
from pathlib import Path
import re
import sys

def blocks(md):
    lines=md.splitlines();i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if i+1<len(lines) and '|' in line and re.fullmatch(r'[| :\-]+',lines[i+1].strip()) and '-' in lines[i+1]:
            rows=[]
            while i<len(lines) and '|' in lines[i]:
                if not re.fullmatch(r'[| :\-]+',lines[i].strip()):rows.append([x.strip() for x in lines[i].strip().strip('|').split('|')])
                i+=1
            yield 'table',rows;continue
        match=re.match(r'^(#{1,6})\s+(.+)$',line)
        if match:yield 'h'+str(len(match[1])),match[2];i+=1;continue
        match=re.match(r'^(?:[-*]\s+|\d+[.)]\s+)(.+)',line)
        if match:yield ('p',line) if re.match(r'^\d+[.)]',line) else ('li',match[1]);i+=1;continue
        para=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(?:#{1,6}\s|[-*]\s|\d+[.)]\s)',lines[i].strip()):
            if i+1<len(lines) and re.fullmatch(r'[| :\-]+',lines[i+1].strip()) and '|' in lines[i]:break
            para.append(lines[i].strip());i+=1
        yield 'p',' '.join(para)

def inline(text):
    text=html.escape(text)
    text=re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)',lambda m:f'<a href="{m[2]}">{m[1]}</a>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
    return text

def render_html(md,title):
    out=[]
    for kind,value in blocks(md):
        if kind=='table':
            out.append('<div class="table-wrap"><table>')
            for i,row in enumerate(value):
                tag='th' if i==0 else 'td';out.append('<tr>'+''.join(f'<{tag}>{inline(c)}</{tag}>' for c in row)+'</tr>')
            out.append('</table></div>')
        elif kind=='li':out.append('<ul><li>'+inline(value)+'</li></ul>')
        else:out.append(f'<{kind}>'+inline(value)+f'</{kind}>')
    css="body{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;max-width:960px;margin:44px auto;padding:0 24px;color:#222;line-height:1.8}h1{font-size:30px;line-height:1.4}h2{font-size:23px;margin-top:32px}h1,h2,h3{color:#000}p{margin:0 0 15px}a{color:#145fa0}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.65}th,td{border:1px solid #d9d9d9;padding:10px;vertical-align:middle;text-align:left}th{background:#e8eef3;color:#000}tr:nth-child(even){background:#fafbfc}.table-wrap{overflow:auto}li{margin:5px 0}ul{margin:4px 0;padding-left:24px}"
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+css+'</style></head><body>'+''.join(out)+'</body></html>\n'

def write_docx(md,destination,title,wide_tables=False):
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_ORIENT
    from docx.opc.constants import RELATIONSHIP_TYPE
    doc=Document();sec=doc.sections[0];sec.page_width=Inches(11.7 if wide_tables else 8.5);sec.page_height=Inches(8.3 if wide_tables else 11)
    if wide_tables:sec.orientation=WD_ORIENT.LANDSCAPE
    sec.top_margin=sec.bottom_margin=sec.left_margin=sec.right_margin=Inches(0.9)
    font=os.environ.get('FRONTMIND_DOCX_FONT','Songti SC' if sys.platform=='darwin' else 'Noto Sans CJK SC')
    for border in list(doc.styles.element.xpath('.//w:pBdr')):border.getparent().remove(border)
    for name,size,leading in [('Normal',11,18),('List Bullet',11,18),('Title',22,30),('Heading 1',17,24),('Heading 2',13,20),('Heading 3',12,18)]:
        st=doc.styles[name];st.font.name=font;st.font.size=Pt(size);st.font.color.rgb=RGBColor(0,0,0)
        rf=st._element.get_or_add_rPr().get_or_add_rFonts()
        for key in list(rf.attrib):
            if key.endswith('Theme'):del rf.attrib[key]
        for key in ['ascii','hAnsi','eastAsia','cs']:rf.set(qn('w:'+key),font)
        st.paragraph_format.line_spacing=Pt(leading);st.paragraph_format.space_after=Pt(7)
        st.paragraph_format.widow_control=True
        snap=OxmlElement('w:snapToGrid');snap.set(qn('w:val'),'0');st._element.get_or_add_pPr().append(snap)
        if name.startswith('Heading') or name=='Title':
            st.font.bold=True;st.paragraph_format.keep_with_next=True
            st.paragraph_format.space_before=Pt(12 if name.startswith('Heading') else 0)
            st.paragraph_format.space_after=Pt(8 if name.startswith('Heading') else 16)
    def runs(p,text):
        tokens=re.split(r'(\*\*[^*]+\*\*|\[[^\]]+\]\(https?://[^\s)]+\))',text)
        for token in tokens:
            link=re.fullmatch(r'\[([^\]]+)\]\((https?://[^\s)]+)\)',token)
            if link:
                h=OxmlElement('w:hyperlink');h.set(qn('r:id'),p.part.relate_to(link[2],RELATIONSHIP_TYPE.HYPERLINK,is_external=True))
                r=OxmlElement('w:r');prop=OxmlElement('w:rPr');c=OxmlElement('w:color');c.set(qn('w:val'),'145FA0');prop.append(c);r.append(prop);t=OxmlElement('w:t');t.text=link[1];r.append(t);h.append(r);p._p.append(h)
            else:
                bold=token.startswith('**') and token.endswith('**');run=p.add_run(token[2:-2] if bold else token.replace('`',''))
                if bold:run.bold=True
    first=True
    for kind,value in blocks(md):
        if kind=='table':
            cols=max(len(x) for x in value);table=doc.add_table(rows=0,cols=cols);table.autofit=False
            widths=([1.6,1.1,1.1,6.1] if wide_tables and cols==4 else [.85,1.1,.85,3.9] if cols==4 else [(9.9 if wide_tables else 6.7)/cols]*cols)
            for col,width in zip(table.columns,widths):col.width=Inches(width)
            pr=table._tbl.tblPr;borders=OxmlElement('w:tblBorders')
            for edge in ['top','left','bottom','right','insideH','insideV']:
                e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
            pr.append(borders)
            for idx,row in enumerate(value):
                cells=table.add_row().cells
                if wide_tables:
                    no_split=OxmlElement('w:cantSplit');table.rows[-1]._tr.get_or_add_trPr().append(no_split)
                for ci,cell in enumerate(cells):
                    cell.width=Inches(widths[ci]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    cp=cell._tc.get_or_add_tcPr();margins=OxmlElement('w:tcMar')
                    for edge in ['top','left','bottom','right']:
                        el=OxmlElement('w:'+edge);el.set(qn('w:w'),'100');el.set(qn('w:type'),'dxa');margins.append(el)
                    cp.append(margins)
                    if idx==0 or idx%2==0:
                        fill=OxmlElement('w:shd');fill.set(qn('w:fill'),'E8EEF3' if idx==0 else 'FAFBFC');cp.append(fill)
                    p=cell.paragraphs[0];p.paragraph_format.space_after=Pt(2);p.paragraph_format.line_spacing=1.15
                    runs(p,row[ci] if ci<len(row) else '')
                    for r in p.runs:r.font.size=Pt(10);r.bold=True if idx==0 else r.bold
                    if ci in [1,2]:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                if idx==0:
                    repeat=OxmlElement('w:tblHeader');table.rows[-1]._tr.get_or_add_trPr().append(repeat)
            doc.add_paragraph();continue
        if kind.startswith('h'):
            style='Title' if first and kind=='h1' else 'Heading '+str(max(1,min(int(kind[1:])-1,3)));p=doc.add_paragraph(style=style)
        else:p=doc.add_paragraph(style='List Bullet' if kind=='li' else 'Normal')
        runs(p,value);first=False
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True);doc.save(destination)
