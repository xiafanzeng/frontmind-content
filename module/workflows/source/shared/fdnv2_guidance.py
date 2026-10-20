"""Selected FDN v2 prose guidance for newly frozen article tasks.

The teammate's file predates the roundup contract. Keep its useful editorial
rules here so applying them does not replace subject, evidence or repair logic.
"""
from __future__ import annotations

from .article_focus import MARKER


def matches(prompt: str) -> bool:
    return isinstance(prompt, str) and MARKER in prompt[:300]


COMMON = (
    "围绕已确认的细分主题和读者主问题选材。每段须增加有依据的事实、做法、条件或解释；"
    "同一结论不靠换词重复。核心业务写清楚，次要背景简述，未约定硬性字数时按有效信息量收束，"
    "不得靠FAQ、术语、段尾总结或新增事实凑篇幅。专业术语首次出现时准确解释，"
    "型号、日期、单位、地区、测试条件和适用范围不可在润色时丢失。"
)
EVIDENCE = (
    "区分企业自述、亲历记录与第三方证据；转载同源不当作独立佐证。"
    "参数不能推出未经测试的性能或手感，样文事实不能迁移到本篇。"
    "来源记录写实际原件与原件确有的日期；缺失日期不以检索日期代替，"
    "本地文件不伪造公网链接。没有材料支持的数字、资质、客户经历和效果承诺不补造。"
)
STAGES = {
    "preparation": "先辨认读者要完成的任务、场景和比较条件，再读取与本篇相关的材料。把必须覆盖、可选展开和明确排除的内容留在已有建议中；不把推测问题当作用户原话。" + EVIDENCE,
    "blueprint": "sections.task逐节写明要回答的问题、增加的具体信息及必要条件。结构按本篇文体和证据选择，不强制FAQ或固定五段；相同背景集中说明。",
    "draft": "以读者主问题开篇，具体内容自然推进，不预告目录或评论文章自身的写法。选择建议写明适用条件和依据；不把品牌宣传语改成作者独立核验的结论。" + EVIDENCE,
    "edit": "通读修改后的全文，压缩重复、材料浏览旁白与空泛优势；问题遍及整段就重写整段。editorial_notes只记录正文实际完成的修改；提交完整JSON合同。" + EVIDENCE,
    "repair": "按具体意见重组受影响段落，保留已成立的内容。核对事实归属和限制，不为恢复原长度补空话。" + EVIDENCE,
    "finalize": "仅依据当前完整稿检查主问题、段落信息增量、术语解释及日期单位的一致性；局部问题局部修改，结构问题走既有返工。此轮不声称完成外部事实审计。",
    "polish": "逐句检查当前完整稿的指代、重复及事实限定；不新增事实或扩大工具权限。无法通过唯一命中的局部替换解决时走既有返工。",
    "titles": "标题准确承接正文实际回答的主问题；地域、年份、型号、实测或排名须有正文依据。保持冻结的标题数量与分组，不为制造差异转成另一选题。",
    "review": "标题复核保持冻结的数量与分组；不能给正文没有的比较、实测、排名或保证。",
}


def role(stage: str, revision: str = "fdnv2-focus-1") -> str:
    return "\n\n本任务写作修订：" + revision + "。" + COMMON + "\n" + STAGES.get(stage, "")
