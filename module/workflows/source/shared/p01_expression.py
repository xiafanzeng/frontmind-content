"""Opt-in expression policy. Historical prompts remain frozen."""
CONTRACT = 'frontmind-p01-expression/1'
MARKER = '<frontmind_p01_expression version="1" />'
GUIDANCE = '''可以将具体业务、产品特点和服务安排放进合理的使用情境，写出其直接带来的便利、体验或选择价值，并用自然、有感染力的语言表达。不要求原始材料逐字提供同一句价值说明；实际能力、服务安排和效果判断仍须有依据。
保留具体内容及其成立的吸引力。删去空泛、重复或脱离事实的优势总结；不要把自然的场景、用途和价值表达一并削掉，也不要将每段统一改成“特点＋好处”的固定句式。推荐意味可以鲜明，不为显得客观将成稿压成资料摘要。不固定场景、章节、推荐理由数量，不编造体验者、采访或客户故事。'''
def enabled(state):
    return (state.get('job_kind') == 'article' and state.get('selected_pattern_id') == 'P01'
            and state.get('metadata', {}).get('p01_expression_policy') == CONTRACT)
def matches(prompt):
    return isinstance(prompt, str) and prompt.startswith('<frontmind_natural_prose version="16">\n' + MARKER + '\n')
def role(stage, original):
    if stage == 'edit':
        original = original.replace('让段落在最后一项具体内容处收住。无需再解释前面这些业务如何共同构成体系、延伸服务或方便选择。', '让项目、用途和特点融入连贯介绍，可以写出与这些事实直接相关的价值和吸引力；已经表达清楚的意思不再追加同义总结。')
    if stage == 'preparation':
        original += '\n案例insight具体说明借鉴的选材、场景衔接和展开方式，同时辨别不适用的体验身份、重复口号或无据判断。案例不能改变当前委托的正文范围，不照搬行业事实和章节模板。'
    return original + '\n' + GUIDANCE
