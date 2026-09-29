"""Package the actual program, original case inputs and completed model outputs."""
from pathlib import Path
import json
import argparse
import os
import sys
import shutil
import hashlib
import html
import re

BASE=Path(__file__).resolve().parents[1]
SOURCE=BASE
sys.path.insert(0,str(SOURCE))
from scripts import build_release as release
from scripts import frontmind_workflow as wf
from shared import manuscript_revision, natural_editor

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

# These strings are model prose, including copies embedded in later requests.
# Path portability is a metadata transformation, never another editing pass.
BODY_KEYS=frozenset({'article_markdown','base_markdown','candidate_markdown',
                    'final_markdown','draft_markdown','edit_base_markdown'})


def manuscript_strings(value):
    rows=[]
    if isinstance(value,dict):
        for key,item in value.items():
            if key in BODY_KEYS and isinstance(item,str):
                rows.append(item)
            else:
                rows.extend(manuscript_strings(item))
    elif isinstance(value,list):
        for item in value:
            rows.extend(manuscript_strings(item))
    return rows


class PortableRecords:
    def __init__(self,job,workflow=SOURCE,prose=(),relative_files=None):
        aliases={}
        for path,label in ((Path(job),'CASE_JOB'),(Path(workflow),'WORKFLOW_ROOT')):
            for value in {str(path),str(path.resolve())}:
                aliases[value]=label
                # Some tool inputs serialize slash-escaped JSON inside Markdown.
                aliases[value.replace('/',r'\/')]=label
        self.aliases=sorted(aliases.items(),key=lambda row:len(row[0]),reverse=True)
        self.relative_files=relative_files or {}
        variants=set()
        for body in prose:
            stripped=re.sub(r'\A\s*# [^\n]*(?:\n|$)','',body,count=1)
            for text in (body,stripped):
                if text:
                    variants.update((text,json.dumps(text,ensure_ascii=False)[1:-1],html.escape(text)))
        self.prose=sorted(variants,key=len,reverse=True)

    def metadata(self,text):
        for original,label in self.aliases:
            text=text.replace(original,label)
        return text

    def prompt(self,text):
        protected={}
        for index,body in enumerate(self.prose):
            if body not in text:
                continue
            token='\x00PRESERVED_MANUSCRIPT_'+str(index)+'\x00'
            protected[token]=body
            text=text.replace(body,token)
        text=self.metadata(text)
        for token,body in protected.items():
            text=text.replace(token,body)
        return text

    def json(self,value):
        if isinstance(value,dict):
            return {key:(item if key in BODY_KEYS and isinstance(item,str)
                         else self.relative_files.get(item,item) if key=='result_file' and isinstance(item,str)
                         else self.json(item))
                    for key,item in value.items()}
        if isinstance(value,list):
            return [self.json(item) for item in value]
        if isinstance(value,str):
            return self.prompt(value)
        return value

    def copy(self,source,destination,*,prompt=False):
        suffix=source.suffix.casefold()
        if suffix=='.json':
            value=json.loads(source.read_text(encoding='utf-8'))
            portable=self.json(value)
            if manuscript_strings(value)!=manuscript_strings(portable):
                raise RuntimeError('Manuscript changed while copying '+source.name)
            destination.write_text(json.dumps(portable,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        elif source.name in {'article.md','article.html'} and not prompt:
            # These files are the rendered manuscript, not path metadata.
            shutil.copy2(source,destination)
        elif suffix in {'.md','.html'}:
            text=source.read_text(encoding='utf-8')
            if prompt:
                portable=self.prompt(text)
            elif suffix=='.html':
                # Only markup attributes/comments may contain local metadata.
                # Visible article text and paragraph structure stay byte-identical.
                portable=re.sub(r'<[^>]*>',lambda match:self.metadata(match.group()),text)
            else:
                # Reader-facing Markdown may contain path metadata in link
                # destinations; plain prose, headings and emphasis are unchanged.
                portable=re.sub(r'(?<=\]\()[^\n)]*(?=\))',lambda match:self.metadata(match.group()),text)
                portable=re.sub(r'<!--.*?-->',lambda match:self.metadata(match.group()),portable,flags=re.S)
            destination.write_text(portable,encoding='utf-8')
        else:
            shutil.copy2(source,destination)


def prompt_source_attempts(attempt,seen=None):
    """Follow only recorded recovery links, including zero-call recovery."""
    seen=set() if seen is None else set(seen)
    if attempt.name in seen:
        raise RuntimeError('Cyclic prompt recovery reference: '+attempt.name)
    seen.add(attempt.name)
    record=json.loads((attempt/'execution.json').read_text(encoding='utf-8'))
    sources=[]
    for key,hash_key in (('recovered_from_attempt','source_execution_sha256'),
                         ('resumed_tools_from_attempt','resumed_execution_sha256')):
        source_id=record.get(key)
        if not source_id:
            continue
        if not isinstance(source_id,str) or not re.fullmatch(r'[A-Za-z0-9_]+',source_id):
            raise RuntimeError('Invalid prompt recovery reference')
        source=attempt.parent/source_id
        execution=source/'execution.json'
        if not execution.is_file() or digest(execution)!=record.get(hash_key):
            raise RuntimeError('Original prompt recovery source changed: '+source_id)
        for path in prompt_source_attempts(source,seen):
            if path not in sources:
                sources.append(path)
    return sources+[attempt]


def request_instruction_texts(request):
    """Extract prompt fields only; never export request/profile/tool metadata."""
    rows=[]
    for field in ('system_instructions','instructions'):
        value=request.get(field)
        if value is not None:
            if not isinstance(value,str):
                raise RuntimeError('Unsupported instruction text in '+field)
            if value:
                rows.append((field,value))
    for index,message in enumerate(request.get('messages',[])):
        if not isinstance(message,dict) or message.get('role') not in {'system','developer'}:
            continue
        field=f'messages[{index}].content'
        content=message.get('content')
        if isinstance(content,str):
            if content:
                rows.append((field,content))
        elif isinstance(content,list):
            for part_index,part in enumerate(content):
                if not isinstance(part,dict) or part.get('type') not in {'text','input_text'} or not isinstance(part.get('text'),str):
                    raise RuntimeError('Unsupported instruction content in '+field)
                if part['text']:
                    rows.append((f'{field}[{part_index}].text',part['text']))
        else:
            raise RuntimeError('Unsupported instruction content in '+field)
    return rows


def collect_system_prompts(action,attempt,dest,portable):
    """Save the actual call's instructions, deduplicated across model rounds."""
    prompts={}
    for source in prompt_source_attempts(attempt):
        paths=sorted(path for path in source.glob('*_request.json')
                     if re.fullmatch(r'(?:round|model)_\d+_request\.json',path.name))
        for path in paths:
            request=json.loads(path.read_text(encoding='utf-8'))
            for field,text in request_instruction_texts(request):
                prompts.setdefault(text,[]).append({'attempt_id':source.name,
                    'request_file':path.name,'field':field,'request_sha256':digest(path)})
    if not prompts:
        raise RuntimeError('Actual model system prompt is missing: '+action)
    records=[]
    for index,(original,sources) in enumerate(prompts.items(),1):
        suffix='' if index==1 else f'_{index:02d}'
        target=dest/(action+'_system_prompt'+suffix+'.md')
        target.write_text(portable.prompt(original),encoding='utf-8')
        records.append({'file':target.name,'original_text_sha256':hashlib.sha256(original.encode('utf-8')).hexdigest(),
                        'packaged_text_sha256':digest(target),'sources':sources})
    return records


def collect_completed_case(pattern,entry,case):
    if entry['status']!='accepted':
        raise RuntimeError('Read the actual article and finish Word inspection before packaging: '+pattern)
    job=Path(entry['job'])
    js=json.loads((job/'job_state.json').read_text())
    if js['status']!='completed':
        raise RuntimeError('The complete model chain has not finished')
    metadata=js.get('metadata',{})
    if metadata.get('natural_prose_contract')!='frontmind-natural-prose/15' or metadata.get('article_manuscript_revision'):
        raise RuntimeError('Package this case from its new default writing run: '+pattern)
    verified=manuscript_revision.validate_completed_manuscript(wf,job,p0=False)
    if any(row.get('execution_mode')!='production' for row in verified['source']['actions']):
        raise RuntimeError('Only actual model outputs can be packaged as the accepted sample: '+pattern)
    production=list((job/'production').glob('article_*.json'))
    prose=[]
    for path in production:
        prose.extend(manuscript_strings(json.loads(path.read_text(encoding='utf-8'))))
    relative_files={path.relative_to(job).as_posix():path.name for path in production}
    portable=PortableRecords(job,prose=prose,relative_files=relative_files)
    dest=case/'generated'/pattern
    dest.mkdir(parents=True,exist_ok=True)
    for path in production:
        portable.copy(path,dest/path.name)
    portable.copy(job/'blueprints/article_blueprint.json',dest/'article_blueprint.json')
    delivery=metadata.get('delivery') or {}
    delivery_paths=[Path(value) for value in delivery.values() if isinstance(value,str)]
    if not delivery_paths:
        delivery_paths=list((job/'deliverables').glob('*'))
    for path in delivery_paths:
        if not path.resolve().is_relative_to(job.resolve()):
            raise RuntimeError('Delivery must belong to its recorded Job: '+str(path))
        if path.is_file() and path.suffix in {'.md','.html','.docx','.json'}:
            portable.copy(path,dest/path.name)
    actions=[]
    for action in ('article_blueprint','article_draft','article_edit','article_finalize','article_repair','article_polish','article_titles','article_title_review'):
        runtime=job/'provider'/action/'runtime'
        if not (runtime/'latest.json').is_file():
            continue
        latest=json.loads((runtime/'latest.json').read_text())
        attempt=runtime/'attempts'/latest['attempt_id']
        execution=json.loads((attempt/'execution.json').read_text())
        cfg=execution.get('requested_configuration') or {}
        record={'action':action,'attempt_id':latest['attempt_id'],'status':execution.get('status'),
                'mode':execution.get('execution_mode'),'model':cfg.get('model'),
                'tool_calls':execution.get('tool_calls',0)}
        # A zero-call recovery has no new prompt.md; use its original call.
        prompt_attempt=next((path for path in reversed(prompt_source_attempts(attempt))
                             if (path/'prompt.md').is_file()),None)
        if prompt_attempt is not None:
            target=dest/(action+'_prompt.md')
            portable.copy(prompt_attempt/'prompt.md',target,prompt=True)
            record.update(original_prompt_sha256=digest(prompt_attempt/'prompt.md'),
                          prompt_source_attempt_id=prompt_attempt.name,
                          packaged_prompt_sha256=digest(target))
        record['system_prompts']=collect_system_prompts(action,attempt,dest,portable)
        actions.append(record)
    final_source=json.loads((job/'production/article_final_source.json').read_text())
    final_review=json.loads((job/final_source['result_file']).read_text())
    packaged_source=json.loads((dest/'article_final_source.json').read_text())
    if not (dest/packaged_source['result_file']).is_file():
        raise RuntimeError('The packaged final source must resolve to its editorial result')
    (dest/'run.json').write_text(json.dumps({'pattern':pattern,'mission':'frontmind-natural-prose/15',
        'fresh_job':True,'previous_manuscript_imported':False,'external_assistant_rewrite':False,
        'final_review_action':final_source['review_action'],
        'xty_local_edit_count':len(final_review['local_edits']),
        'development_prompt_revalidation':[
            {'stage':row['stage'],'reason':row['reason']}
            for row in metadata.get('v15_development_revalidation',[])],
        'writer_count_contract':metadata.get('writer_count_contract'),
        'natural_prose_contract':metadata.get('natural_prose_contract'),
        'path_normalization':{'CASE_JOB':'the fresh sample Job root','WORKFLOW_ROOT':'the extracted workflow root',
                              'scope':'Local path metadata only; manuscript strings are unchanged.',
                              'result_file':'Relative to this packaged sample directory.'},
        'system_prompt_extraction':'Only instruction text from actual model request records; repeated text is saved once with all call sources. Complete requests, credentials and runtime logs are not copied.',
        'body_characters':natural_editor.character_count(verified['base_markdown']),'actions':actions},ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--stage-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    state=json.loads(args.state.read_text())
    case=SOURCE/'customer_inputs/taixin/v15'
    stage=args.stage_dir.resolve()
    if stage.exists():
        raise RuntimeError('Use a new staging directory; do not overwrite an earlier package')
    for pattern in ('P01','P02'):
        collect_completed_case(pattern,state[pattern],case)
    projection=stage/release.RELEASE_ROOT_NAME
    files=release.copy_projection(SOURCE,projection)
    required={'shared/writing_context_v15.py','shared/language_editor_v15.py','scripts/package_v15.py','scripts/run_taixin_v15_case.py','shared/p01_writing_v2.py','shared/writing_context_v14.py','shared/writing_context.py','shared/writing_requirements.py','shared/writer_measure.py',
              'shared/natural_editor.py','shared/model_runtime.py','shared/host_tools.py',
              'shared/agents_runtime.py','shared/managed_runtime.py','scripts/frontmind_workflow.py',
              *release.CREDENTIAL_FILES}
    if not required<=set(files):
        raise RuntimeError('The release projection omitted live program/configuration files: '+', '.join(sorted(required-set(files))))
    report={'projection':release.audit_projection(projection,files)}
    report['source_hashes']=release.verify_file_hashes(SOURCE,projection,files)
    report['validation']=release.run_json([sys.executable,'-B','scripts/validate_workflow.py','--release-projection'],projection,'release layout')
    archive=stage/release.FINAL_ZIP_NAME
    release.write_zip(projection,archive)
    report['zip']=release.inspect_release_zip(archive)
    clean=release.extract_zip(archive,stage/'clean-extraction')
    report['extraction_hashes']=release.verify_file_hashes(SOURCE,clean,files)
    os.environ['FRONTMIND_PYTHON']=sys.executable
    report['preflight']=release.run_json([str(clean/'scripts/frontmind'),'preflight'],clean,'clean preflight')
    report['runtime']=release.validate_model_runtime(clean,sys.executable)
    report['files']=len(files)
    report['sha256']=digest(archive)
    report['zip_path']=str(archive)
    (stage/'package-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    out=args.output_dir/archive.name
    shutil.copy2(archive,out)
    state['package']={'path':str(out),'files':len(files),'sha256':report['sha256'],'preflight':report['preflight']['status'],'runtime':report['runtime']['status']}
    state['status']='completed'
    args.state.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'zip':str(out),'files':len(files),'preflight':report['preflight']['status'],'runtime':report['runtime']['status']},ensure_ascii=False))


if __name__=='__main__':
    main()
