#!/usr/bin/env python3
"""Run an already commissioned sample from a new Job, starting at selection.

Only original inputs and previously confirmed business choices are imported.
No manuscript, old blueprint, revision request, or model result is reused.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import frontmind_workflow as wf
from shared import writing_requirements, recommendation_references, language_editor_v15
from shared.example_acquisition import ExampleStore


def prepare(pattern: str, job: Path):
    case = ROOT/'customer_inputs/taixin/v16'
    config = wf.read_json(case/pattern/'case.json')
    character_range = language_editor_v15.validate_body_character_range(config['body_character_range'])
    job = wf.ensure_new_job(job, 'article', job_id=job.name)
    state = wf.load_state(job)
    if state['metadata'].get('natural_prose_contract') != 'frontmind-natural-prose/16':
        raise RuntimeError('This sample must use the new default mission, without an upgrade or manuscript edit.')
    wf.bind_reference_pack(job, case/config['reference_pack'])
    state = wf.load_state(job)
    question = wf.select_question(Path(state['reference_pack']['path']), config['question_id'],
                                  period_id=config['question_period'])
    state['question'] = wf.freeze_question_inputs(job, question)
    state['selected_pattern_id'] = pattern
    state['selected_example_route'] = config['example_route']
    state['metadata']['startup_target'] = 'article'
    state['metadata']['startup_entrypoint'] = 'confirmed_case'
    state['metadata']['confirmed_case_input'] = {'pattern':pattern, 'note':config['confirmed_input_note']}
    state['metadata']['body_character_range'] = character_range
    state['metadata']['blueprint_material_roots'] = ['inputs/user_materials/question']
    if config.get('editorial_research_hints'):
        state['metadata']['editorial_research_hints'] = config['editorial_research_hints']
    state['decisions'] = {
        'reference_pack_route': {'choice':'use','confirmed_at':wf.now()},
        'response_brief': config['requirements']['article_brief'],
        'ai_brand_recognition': 'insufficient',
        'response_brief_confirmation': {'confirmed':True,'confirmed_at':wf.now()},
        'pattern': {'pattern_id':pattern,'confirmed_at':wf.now()},
        'example_route': {'route':config['example_route'],'confirmed_at':wf.now()},
        'question_positioning_confirmation': {'pattern_id':pattern,'confirmed':True,'confirmed_at':wf.now()},
    }
    writing_requirements.merge_changes(state, config['requirements'])
    wf.save_state(job, state)
    positioning = wf.read_json(case/pattern/'confirmed_positioning.json')
    wf.validate_question_positioning(positioning, state)
    wf.atomic_json(job/'question_positioning/question_positioning.json', positioning)
    material_paths = config.get('material_paths')
    if material_paths is None:
        material_paths = ['materials/common']
        if pattern == 'P02':
            material_paths.append('materials/P02')
    elif not isinstance(material_paths, list) or not material_paths or any(
        not isinstance(path, str) or not path.strip() for path in material_paths
    ):
        raise ValueError('material_paths must be a non-empty list of paths relative to the case directory.')
    for material_path in material_paths:
        wf.save_user_material(job, str(case/material_path), 'question')
    if pattern == 'P01':
        recommendation_references.register(wf, ROOT, job)
    else:
        store = ExampleStore(job)
        rows=[]
        for example in config['examples']:
            record=store.import_user_file(case/example['path'], title=example['title'])
            rows.append({'artifact_id':record['artifact_id'],'reference_role':example['role'],
                         'style_analysis':example.get('style_analysis','')})
        wf.save_examples(job, rows, 'question')
    state=wf.load_state(job)
    wf.prepare_blueprint_material_index(job, state, p0=False)
    wf.save_state(job, state)
    wf.set_status(job, 'running_article_blueprint', 'article_blueprint')
    wf.atomic_json(job/'inputs/current_commission.json', config['requirements'])
    print(json.dumps({'prepared':str(job),'pattern':pattern,'mission':state['metadata']['natural_prose_contract'],
                      'previous_manuscript':False,'previous_blueprint':False,'manuscript_edits':False},ensure_ascii=False),flush=True)
    return job


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pattern',choices=['P01','P02'],required=True)
    ap.add_argument('--job-dir',type=Path,required=True)
    ap.add_argument('--stage',choices=['prepare','blueprint','write','all','resume'],default='prepare')
    args=ap.parse_args()
    job=args.job_dir.expanduser().resolve()
    if args.stage in {'prepare','blueprint','all'}:
        prepare(args.pattern,job)
    if args.stage in {'blueprint','all','resume'}:
        wf.drive(job)
    if args.stage in {'write','all'}:
        state=wf.load_state(job)
        if state['status']!='awaiting_blueprint_confirmation':
            raise RuntimeError('Expected the newly generated blueprint; found '+state['status'])
        opts=wf.parser().parse_args(['continue','--job-dir',str(job),'--revision',str(state['revision']),'--accept-blueprint'])
        wf.continue_workflow(opts)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
