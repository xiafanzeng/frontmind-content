"""DOCX family declarations without distributing or embedding font binaries.

Legacy embedded-font audits remain in docx_font_embedding. New documents have
an explicit system-font dependency; validation of OOXML is not visual QA.
"""
from __future__ import annotations
import os,tempfile,zipfile
from pathlib import Path
from lxml import etree
from .docx_font_embedding import FONT_FAMILY as DEFAULT_FONT_FAMILY, W_NS, _patch_word_xml
FONT_FAMILY = os.environ.get("FRONTMIND_DOCX_FONT", DEFAULT_FONT_FAMILY).strip() or DEFAULT_FONT_FAMILY

FONT_EXTENSIONS={'.otf','.ttf','.ttc','.woff','.woff2','.odttf','.eot'}

def _without_embeddings(parts):
    out={}
    for name,data in parts.items():
        if name.startswith('word/fonts/') or Path(name).suffix.lower() in FONT_EXTENSIONS:
            continue
        if name.endswith('.xml') or name.endswith('.rels'):
            root=etree.fromstring(data)
            for el in list(root.iter()):
                local=etree.QName(el).localname
                is_embed=local in {'embedRegular','embedBold','embedItalic','embedBoldItalic','embedTrueTypeFonts','saveSubsetFonts'}
                is_font_rel=local=='Relationship' and el.get('Type','').endswith('/font')
                is_font_type=local in {'Default','Override'} and ('font' in el.get('ContentType','').lower() and local=='Default' or el.get('PartName','').startswith('/word/fonts/'))
                if (is_embed or is_font_rel or is_font_type) and el.getparent() is not None:el.getparent().remove(el)
            data=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
        out[name]=data
    return out

def enforce_docx_font_contract(path: Path|str, **_):
    p=Path(path)
    if p.is_symlink() or not p.is_file():raise ValueError('unsafe or missing document')
    with zipfile.ZipFile(p) as z:
        parts={n:z.read(n) for n in z.namelist()}
    for n in parts:
        if n.startswith('word/') and n.endswith('.xml'):parts[n]=_patch_word_xml(n,parts[n], family=FONT_FAMILY)
    parts=_without_embeddings(parts)
    fd,tmp=tempfile.mkstemp(prefix='.'+p.name,suffix='.docx',dir=p.parent);os.close(fd)
    try:
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
            for n,v in parts.items():z.writestr(n,v)
        report=audit_docx_font_contract(tmp)
        if not report['passed']:raise ValueError('; '.join(report['issues']))
        os.replace(tmp,p)
        return report
    finally:Path(tmp).unlink(missing_ok=True)

def audit_docx_font_contract(path: Path|str):
    issues=[]
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if any(n.startswith('word/fonts/') or Path(n).suffix.lower() in FONT_EXTENSIONS for n in names):issues.append('font binaries present')
        for n in ('word/document.xml','word/styles.xml','word/settings.xml'):
            if n not in names:issues.append('missing '+n);continue
            root=etree.fromstring(z.read(n))
            if root.xpath('//*[local-name()="embedRegular" or local-name()="embedBold" or local-name()="embedTrueTypeFonts"]'):issues.append('embedding instructions remain')
        styles=etree.fromstring(z.read('word/styles.xml'))
        fonts=styles.findall('.//{%s}rFonts'%W_NS)
        if not fonts or any(el.get('{%s}eastAsia'%W_NS)!=FONT_FAMILY for el in fonts):issues.append('inconsistent CJK family declaration')
    return {'passed':not issues,'issues':issues,'mode':'system_fonts','font_family':FONT_FAMILY,
            'embedded_fonts':False,'external_font_dependency':True,'visual_quality_verified':False}
