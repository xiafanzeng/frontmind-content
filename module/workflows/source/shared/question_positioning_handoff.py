"""Pass confirmed question positioning to new editorial requests only.

The positioning is background for selection and planning, not a replacement for
the current commission. A separate opt-in preserves historical frozen prompts.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import p02_selection, writing_requirements

CONTRACT = 'frontmind-confirmed-question-positioning/1'
METADATA_KEY = 'question_positioning_handoff'
PATH = 'question_positioning/question_positioning.json'
GUIDANCE = (
    '以下是本题已确认的定位，用于理解对象关系、介绍重点和差异化角度，并据此选材与构思。'
    '它是当前委托的补充，不是企业事实来源，也不要求照搬其措辞、章节或选择指南写法。'
    '当前明确写作要求、本轮构思修改及已确认的P02三家名单与顺序优先；'
    '定位中与这些要求冲突的旧范围、排序或表达安排不再采用。'
    '保留仍适用的重点，将其落实到自然事实材料的取舍和正式蓝图的主次中。'
)


def enabled(state):
    return (
        state.get('job_kind') == 'article'
        and state.get('selected_pattern_id') in {'P01', 'P02'}
        and state.get('metadata', {}).get('natural_prose_contract') in {'frontmind-natural-prose/16', 'frontmind-natural-prose/16.5'}
        and state.get('metadata', {}).get(METADATA_KEY) == CONTRACT
    )


def context(wf, job):
    state = wf.load_state(job)
    if not enabled(state):
        return ''
    decision = state.get('decisions', {}).get('question_positioning_confirmation')
    if not isinstance(decision, dict) or decision.get('confirmed') is not True:
        return ''
    if decision.get('pattern_id', state['selected_pattern_id']) != state['selected_pattern_id']:
        return ''
    if not writing_requirements.positioning_still_valid(state, job):
        return ''
    value = wf.read_json(Path(job) / PATH)
    if not isinstance(value.get('natural_analysis'), str) or not value['natural_analysis'].strip():
        return ''
    if p02_selection.enabled(state):
        # The v16.3 selection owns membership and order. A mismatching saved
        # positioning is stale even when someone retained its confirmation.
        record = p02_selection.current(state)
        names = [entity['name'] for entity in record['entities']]
        if value.get('candidate_scope') != names:
            return ''
    selected = {key: value[key] for key in (
        'question', 'pattern_id', 'brand', 'natural_analysis',
        'candidate_scope', 'material_adjustments',
    ) if key in value}
    guidance = GUIDANCE
    if state.get('metadata', {}).get('natural_prose_contract') == 'frontmind-natural-prose/16.5':
        selected.pop('material_adjustments', None)
        guidance += (' 本轮只从定位提取介绍对象、读者需求、业务重点与差异化方向。定位中的核对、证据缺口、'
                     '宣传边界或免责声明是历史工作备注，不进入可写材料和蓝图任务；不要通过改写这些备注来完成正文。')
    return '\n'.join((
        '<confirmed_question_positioning>', guidance,
        json.dumps(selected, ensure_ascii=False, indent=2),
        '</confirmed_question_positioning>',
    ))
