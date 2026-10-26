import {
  contentProductionActionSchema,
  type ContentProductionAction,
  type ContentProductionDto,
} from "../contracts/content-production";

type ConfirmationInputProgress = Pick<ContentProductionDto, "availableActions" | "runnerRevision" | "choices">;
export type ContentConfirmationInputResult = { action: ContentProductionAction | null; hint: string };

/** 只解释当前阶段的明确输入；用户原文和附件仍由调用方原样保留。 */
export function contentConfirmationInputHint(progress: ConfirmationInputProgress): string {
  const has = (kind: ContentProductionAction["kind"]) => progress.availableActions.includes(kind);
  const examples: string[] = [];
  if (has("choose_question")) examples.push("直接输入问题序号或完整问题，也可写“选择问题：具体问题”");
  if (has("update_competitor_selection")) examples.push("竞品：A 作为比较对象，B 只作举例");
  if (has("confirm_competitors")) examples.push("确认比较对象");
  if (has("choose_core_positioning_direction")) examples.push("方向：所选定位方向");
  if (has("confirm_core_positioning")) examples.push("确认核心定位");
  if (has("choose_reference_pack_route")) examples.push("新建资料包", "使用已有资料包");
  if (has("choose_p0_route")) examples.push("新建 P0", "导入 P0（同时附上文件）");
  if (has("choose_p0_examples")) examples.push("P0 文风：工作流写作规范", "P0 文风：Top20");
  if (has("confirm_pattern")) examples.push("文章类型：P01（可选 P01—P06）");
  if (has("choose_examples")) examples.push(progress.choices.some(choice => choice.includes("文章池"))
    ? "文风：A；文章池：1、5（或不采用）" : "文风：A（或 B）");
  if (has("submit_response_brief")) examples.push("额外要求：无；品牌认知：充分（或不充分、不确定）");
  if (has("confirm_question_positioning")) examples.push("确认问题定位");
  if (has("confirm_blueprint") || has("confirm_p0_blueprint")) examples.push("确认写作方案");
  if (has("provide_reference_pack_inputs") || has("provide_question_research_inputs")) examples.push("上传本轮资料、粘贴企业或产品介绍，或输入“资料：具体内容”");
  if (has("revise_current_step")) examples.push("修改：具体调整要求");
  return examples.length ? `请明确输入，例如：${examples.join("；")}。` : "当前没有可由聊天输入确认的操作，请等待本轮处理或刷新阶段。";
}

/** 本地确定性提取，不读取外部服务，不将“继续”“同意”等模糊表述当成确认。 */
export function parseContentConfirmationInput(
  progress: ConfirmationInputProgress,
  text: string,
  filesCount = 0,
): ContentConfirmationInputResult {
  const original = text.trim();
  const command = original.replace(/[。！!]+$/u, "").trim();
  const hint = contentConfirmationInputHint(progress);
  const fail = (reason = "未识别为当前阶段的明确选择。"): ContentConfirmationInputResult => ({ action: null, hint: `${reason}${hint}` });
  const revision = progress.runnerRevision;
  if (revision === null || !Number.isInteger(revision) || revision < 0) return fail("当前确认版本尚未就绪，请刷新后再提交。");
  if (!Number.isInteger(filesCount) || filesCount < 0) return fail("附件数量无效，请重新选择附件。");
  const has = (kind: ContentProductionAction["kind"]) => progress.availableActions.includes(kind);
  const accept = (value: unknown): ContentConfirmationInputResult => {
    const parsed = contentProductionActionSchema.safeParse(value);
    if (!parsed.success) return fail("输入尚不符合本轮确认要求。");
    if (!has(parsed.data.kind)) return fail("当前阶段不支持这项操作。");
    return { action: parsed.data, hint: "已从本次输入提取选择，请核对卡片后确认。" };
  };
  const simple = (kind: ContentProductionAction["kind"]) => accept({ kind, revision });

  // 显式修改优先，避免将“不要确认，请修改”等任意句子误识别为确认。
  const revisionInput = /^修改(?:表述)?\s*[:：]\s*([\s\S]+)$/u.exec(original);
  if (revisionInput) return accept({ kind: "revise_current_step", revision, instructions: revisionInput[1].trim() });
  const selections: Array<[RegExp, ContentProductionAction["kind"], "selection" | "direction"]> = [
    [/^选择问题\s*[:：]\s*([\s\S]+)$/u, "choose_question", "selection"],
    [/^(?:竞品|比较对象)\s*[:：]\s*([\s\S]+)$/u, "update_competitor_selection", "selection"],
    [/^(?:方向|核心定位方向)\s*[:：]\s*([\s\S]+)$/u, "choose_core_positioning_direction", "direction"],
  ];
  for (const [pattern, kind, field] of selections) {
    const match = pattern.exec(original);
    if (match) return accept({ kind, revision, [field]: match[1].trim() });
  }
  if (/^(?:我)?确认(?:当前)?(?:比较对象|竞品)$/u.test(command)) return simple("confirm_competitors");
  if (/^(?:我)?确认(?:当前)?核心定位$/u.test(command)) return simple("confirm_core_positioning");
  if (/^确认并导出(?:\s*(?:品牌资料包|Reference Pack))?$/iu.test(command)) return simple("confirm_core_positioning");
  if (/^(?:我)?确认(?:当前)?(?:问题定位|本题差异化定位)$/u.test(command)) return simple("confirm_question_positioning");
  if (/^(?:我)?确认\s*(?:当前)?(?:(?:P0|品牌文章)\s*)?(?:写作方案|蓝图)(?:[，,]\s*开始正文)?$/iu.test(command)) {
    const blueprints = (["confirm_blueprint", "confirm_p0_blueprint"] as const).filter(has);
    return blueprints.length === 1 ? simple(blueprints[0]) : fail("当前写作方案尚不能唯一确认。");
  }

  if (/^(?:(?:新建|创建|制作)\s*(?:P0|品牌文章|品牌长文|品牌深度文章)|P0\s*[:：]?\s*(?:新建|创建))$/iu.test(command)) return accept({ kind: "choose_p0_route", revision, route: "create" });
  if (/^(?:导入\s*(?:P0|品牌文章|品牌长文|品牌深度文章)|P0\s*[:：]?\s*导入)$/iu.test(command)) {
    return filesCount > 0 ? accept({ kind: "choose_p0_route", revision, route: "import" }) : fail("导入 P0 需要同时附上原文文件。");
  }
  if (/^(?:新建|创建)(?:品牌)?资料包$/u.test(command)) return accept({ kind: "choose_reference_pack_route", revision, route: "create" });
  if (/^使用已有(?:品牌)?资料包$/u.test(command)) return accept({ kind: "choose_reference_pack_route", revision, route: "use" });

  const patternChoice = /^(?:(?:选择)?文章类型\s*[:：]?\s*)?(P0[1-6])$/iu.exec(command);
  if (patternChoice) return accept({ kind: "confirm_pattern", revision, selectedPattern: patternChoice[1].toUpperCase() });
  if (/^采用(?:本轮)?推荐(?:的)?文章类型$/u.test(command)) return simple("confirm_pattern");
  if (/^(?:P0\s*文风\s*[:：]\s*)?(?:使用|采用)?(?:工作流写作规范|默认写作规范)$/iu.test(command)) {
    if (has("choose_p0_examples")) return accept({ kind: "choose_p0_examples", revision, route: "workflow" });
    if (has("choose_examples") && !progress.choices.some(choice => choice.includes("文章池"))) return accept({ kind: "choose_examples", revision, route: "B" });
    return fail("请分别明确文风与文章池构思参考。");
  }
  if (/^(?:P0\s*文风\s*[:：]\s*)?(?:采用|使用)?Top\s*20(?:例文)?$/iu.test(command)) return accept({ kind: "choose_p0_examples", revision, route: "top20" });

  // 复合表述要求字段明确；语句中的其他要求不会被截掉后悄悄确认。
  const parts = command.split(/[;；\n]+/u).map(part => part.trim()).filter(Boolean);
  if (has("submit_response_brief") && /(?:额外要求|企业应答要求|应答要求|品牌认知)/u.test(command)) {
    let requirements: string | undefined;
    let recognition: "sufficient" | "insufficient" | "uncertain" | undefined;
    for (const part of parts) {
      const requirement = /^(?:额外要求|企业应答要求|应答要求)\s*[:：]\s*(.+)$/u.exec(part);
      const brand = /^品牌认知(?:判断)?\s*[:：]\s*(充分|不充分|不确定)$/u.exec(part);
      if (requirement && requirements === undefined) requirements = requirement[1].trim();
      else if (/^(?:本题)?无额外(?:企业应答)?要求$/u.test(part) && requirements === undefined) requirements = "无";
      else if (brand && recognition === undefined) recognition = ({ 充分: "sufficient", 不充分: "insufficient", 不确定: "uncertain" } as const)[brand[1] as "充分" | "不充分" | "不确定"];
      else return fail("应答要求与品牌认知需要各填写一次，品牌认知只能选充分、不充分或不确定。");
    }
    if (!requirements || !recognition) return fail("请同时填写额外要求或明确无额外要求，以及品牌认知判断。");
    const noExtra = /^(?:无|无额外要求|无额外企业应答要求|本题无额外要求)$/u.test(requirements);
    if (!noExtra && /无额外(?:企业应答)?要求/u.test(requirements)) return fail("无额外要求与补充要求同时出现，请明确其中一种。");
    return accept({ kind: "submit_response_brief", revision, ...(noExtra ? { noExtraRequirements: true } : { requirements }), aiBrandRecognition: recognition });
  }
  if (has("choose_examples") && /(?:文风|方案\s*[AB])/iu.test(command)) {
    let route: "A" | "B" | undefined;
    let pool: string | undefined;
    for (const part of parts) {
      const style = /^(?:(?:选择)?文风\s*[:：]?\s*|(?:我选择)?方案\s*)([AB])$/iu.exec(part);
      const reference = /^文章池(?:构思参考)?(?:选择)?\s*[:：]\s*(.+)$/u.exec(part);
      if (style && route === undefined) route = style[1].toUpperCase() as "A" | "B";
      else if (reference && pool === undefined) pool = reference[1].trim();
      else return fail("请明确文风 A 或 B，并单独填写文章池选择。");
    }
    if (!route) return fail("请明确选择文风 A 或 B。");
    const poolRequired = progress.choices.some(choice => choice.includes("文章池"));
    if (poolRequired && !pool) return fail("当前需要同时选择文章池构思参考：填写 1—2 个编号，或明确不采用。");
    if (pool && pool !== "不采用") {
      const ids = pool.split(/[、,，\s]+/u).filter(Boolean);
      if (!ids.length || ids.length > 2 || ids.some(id => !/^[1-9]\d{0,3}$/u.test(id)) || new Set(ids).size !== ids.length) return fail("文章池请填写 1—2 个不同的正整数编号，或明确不采用。");
    }
    return accept({ kind: "choose_examples", revision, route });
  }

  const inputKinds = (["provide_reference_pack_inputs", "provide_question_research_inputs"] as const).filter(has);
  const note = /^(?:资料|材料|资料说明|文件说明)\s*[:：]\s*([\s\S]+)$/u.exec(command);
  // 资料说明中的“采用某技术”“创建服务能力”“修改后的产品资料”是材料正文，
  // 不能按任意动作词子串拦截。前面的明确动作仍优先；这里只排除整句控制指令。
  const controlClause = "(?:(?:请|我|先|暂时|现在|直接|再|不要|别|不应|不能|不|暂不)\\s*)*(?:确认|同意|继续|下一步|开始|提交|取消|撤销|暂停|停止|返回|拒绝|上传|发送|导入|修改|更改|新建|创建|选择|选用|采用)(?:一下|吧|即可|就好|当前内容|本轮内容|当前阶段|本轮选择)?";
  const controlOnly = new RegExp(`^${controlClause}(?:[，,；;、\\s]*(?:并|然后)?\\s*${controlClause})*[，,；;、\\s？?]*$`, "u").test(command)
    || /^(?:好的?|是的?|可以|没问题|收到|行|嗯|不要|不用|不必|暂不|不了|ok|okay|yes|no)[，,；;、\s？?]*$/iu.test(command);
  const negatedControl = /^(?:(?:请|我|先|暂时|现在)\s*)*(?:不要|别|不应|不能|不|暂不)\s*(?:确认|同意|继续|下一步|开始|提交|取消|撤销|暂停|停止|返回|上传|发送|导入|修改|更改|新建|创建|选择|选用|采用)/u.test(command);
  // 选题停点的底部提示允许直接填写题目或序号，不能再要求用户记住字段前缀。
  // 明确材料说明仍属于材料动作；带文件时保留原资料导入路径。
  if (has("choose_question") && (filesCount === 0 || inputKinds.length === 0) && command && !note) {
    const otherField = /^(?:文风|方案|P0\s*文风|文章类型|类型|方向|核心定位方向|竞品|比较对象|额外要求|企业应答要求|应答要求|品牌认知(?:判断)?|文章池(?:构思参考)?(?:选择)?|构思参考|修改)\s*[:：]/iu.test(command)
      || /^(?:文风|方案)\s*[:：]?\s*[AB]$/iu.test(command);
    const businessControl = /^(?:请)?(?:继续|开始|确认|取消|暂停|停止)(?:制作|生成|进行)?(?:P0|品牌长文|问题文章|正文写作|写作流程|下一步)[。！!？?]*$/iu.test(command);
    if (controlOnly || negatedControl || otherField || businessControl || /^[AB]$/iu.test(command)) return fail("请填写问题序号或完整问题，当前输入不是明确题目。");
    if (/^[1-9]\d*$/u.test(command) || command.length >= 2 && /\p{L}/u.test(command)) {
      return accept({ kind: "choose_question", revision, selection: original });
    }
    return fail("问题序号须为正整数，或请填写完整问题。");
  }
  if (inputKinds.length === 1 && (note || (filesCount > 0 || Boolean(command)) && !controlOnly && !negatedControl)) return simple(inputKinds[0]);
  return fail();
}
