import { describe, expect, it } from "vitest";
import { contentProductionActionSchema, type ContentProductionAction } from "../contracts/content-production";
import { contentConfirmationInputHint, parseContentConfirmationInput } from "../client/content-confirmation-input";

const progress = (availableActions: ContentProductionAction["kind"][], choices: string[] = []) => ({ availableActions, runnerRevision: 17, choices });
const parse = (actions: ContentProductionAction["kind"][], text: string, files = 0, choices: string[] = []) => parseContentConfirmationInput(progress(actions, choices), text, files);

describe("底部统一输入的本地确认提取", () => {
  it.each([
    ["确认比较对象", "confirm_competitors"], ["我确认当前比较对象。", "confirm_competitors"],
    ["确认核心定位", "confirm_core_positioning"], ["确认问题定位", "confirm_question_positioning"],
    ["确认本题差异化定位", "confirm_question_positioning"], ["确认写作方案", "confirm_blueprint"],
    ["确认 P0 写作方案", "confirm_p0_blueprint"],
  ] as const)("提取明确确认：%s", (text, kind) => {
    expect(parse([kind], text).action).toEqual({ kind, revision: 17 });
  });

  it.each(["继续", "同意", "确认", "不要确认比较对象", "先确认核心定位再修改一下", "确认写作方案，但不要开始正文", "确认问题定位？", "我不确认问题定位", "确认比较对象和核心定位"])("模糊、否定和复合命令不推进：%s", text => {
    const result = parse(["confirm_competitors", "confirm_core_positioning", "confirm_question_positioning", "confirm_blueprint"], text);
    expect(result.action).toBeNull();
    expect(result.hint).toContain("请明确输入");
  });

  it("保留选择文本的内部内容，不将其解释为额外确认", () => {
    expect(parse(["choose_question"], "选择问题：为什么 A 不适合此场景？").action).toEqual({ kind: "choose_question", revision: 17, selection: "为什么 A 不适合此场景？" });
    expect(parse(["update_competitor_selection"], "竞品：A 作为比较对象，B 不纳入").action).toEqual({ kind: "update_competitor_selection", revision: 17, selection: "A 作为比较对象，B 不纳入" });
    expect(parse(["choose_core_positioning_direction"], "方向：强调适用边界").action).toEqual({ kind: "choose_core_positioning_direction", revision: 17, direction: "强调适用边界" });
  });

  it("显式修改只生成修改动作，保持原要求", () => {
    expect(parse(["revise_current_step", "confirm_blueprint"], "修改：不要确认，先增加验证材料\n保留原结论").action).toEqual({ kind: "revise_current_step", revision: 17, instructions: "不要确认，先增加验证材料\n保留原结论" });
    expect(parse(["confirm_blueprint"], "修改：增加验证材料").action).toBeNull();
  });

  it("P0 新建与文件导入分别提取", () => {
    expect(parse(["choose_p0_route"], "新建 P0").action).toEqual({ kind: "choose_p0_route", revision: 17, route: "create" });
    expect(parse(["choose_p0_route"], "P0：导入", 1).action).toEqual({ kind: "choose_p0_route", revision: 17, route: "import" });
    expect(parse(["choose_p0_route"], "导入 P0").action).toBeNull();
    expect(parse(["choose_p0_route"], "不要新建 P0").action).toBeNull();
  });

  it("提取 P0 文风规范与 Top20", () => {
    expect(parse(["choose_p0_examples"], "P0 文风：工作流写作规范").action).toEqual({ kind: "choose_p0_examples", revision: 17, route: "workflow" });
    expect(parse(["choose_p0_examples"], "P0 文风：Top20").action).toEqual({ kind: "choose_p0_examples", revision: 17, route: "top20" });
  });

  it.each(["P01", "P02", "P03", "P04", "P05", "P06"])("仅确认明确的文章类型 %s", selectedPattern => {
    expect(parse(["confirm_pattern"], `文章类型：${selectedPattern}`).action).toEqual({ kind: "confirm_pattern", revision: 17, selectedPattern });
  });
  it.each(["P00", "P07", "P01 或 P02", "不要 P01"])("拒绝无效或多义文章类型 %s", text => expect(parse(["confirm_pattern"], text).action).toBeNull());

  it("明确品牌认知三选一并同时明确额外要求", () => {
    expect(parse(["submit_response_brief"], "额外要求：无；品牌认知：不充分").action).toEqual({ kind: "submit_response_brief", revision: 17, noExtraRequirements: true, aiBrandRecognition: "insufficient" });
    expect(parse(["submit_response_brief"], "品牌认知：不确定\n企业应答要求：强调适用边界").action).toEqual({ kind: "submit_response_brief", revision: 17, requirements: "强调适用边界", aiBrandRecognition: "uncertain" });
    expect(parse(["submit_response_brief"], "无额外要求；品牌认知：充分").action).toEqual({ kind: "submit_response_brief", revision: 17, noExtraRequirements: true, aiBrandRecognition: "sufficient" });
  });
  it.each(["额外要求：无", "品牌认知：充分", "额外要求：无；品牌认知：充分或不充分", "额外要求：无；品牌认知：充分；品牌认知：不确定", "额外要求：无额外要求但补充案例；品牌认知：充分"])("应答要求不完整或矛盾不推进：%s", text => expect(parse(["submit_response_brief"], text).action).toBeNull());

  it("文章池构思参考与文风分别明确选择", () => {
    const text = "文风：A；文章池：1、5";
    expect(parse(["choose_examples"], text, 0, ["选择文章池"]).action).toEqual({ kind: "choose_examples", revision: 17, route: "A" });
    expect(parse(["choose_examples"], "文风：B；文章池：不采用", 0, ["文章池"]).action).toEqual({ kind: "choose_examples", revision: 17, route: "B" });
    expect(parse(["choose_examples"], "文风：B").action).toEqual({ kind: "choose_examples", revision: 17, route: "B" });
  });
  it.each(["文风：A", "文风：B；文章池：", "文风：B；文章池：随便", "文风：B；文章池：1、2、3", "文风：B；文章池：1、1", "文风：B；文章池：0", "文风：B；文章池：不采用；顺便开始写", "文风：A；文风：B；文章池：1"])("文章池要求缺失或多义时不推进：%s", text => expect(parse(["choose_examples"], text, 0, ["文章池"]).action).toBeNull());

  it("附件仅在提供资料可用时产生提供资料动作", () => {
    expect(parse(["provide_reference_pack_inputs"], "本期企业材料", 1).action).toEqual({ kind: "provide_reference_pack_inputs", revision: 17 });
    expect(parse(["provide_question_research_inputs"], "", 2).action).toEqual({ kind: "provide_question_research_inputs", revision: 17 });
    expect(parse(["provide_question_research_inputs"], "资料：同一期次的 AI 回答").action).toEqual({ kind: "provide_question_research_inputs", revision: 17 });
    expect(parse(["confirm_blueprint"], "企业材料", 1).action).toBeNull();
  });
  it("附件不吞显式选择或否定命令", () => {
    expect(parse(["choose_question", "provide_question_research_inputs"], "选择问题：3", 1).action).toEqual({ kind: "choose_question", revision: 17, selection: "3" });
    expect(parse(["provide_question_research_inputs"], "确认写作方案", 1).action).toBeNull();
    expect(parse(["provide_question_research_inputs"], "不要上传，先继续", 1).action).toBeNull();
    expect(parse(["provide_question_research_inputs"], "继续", 1).action).toBeNull();
  });
  it.each(["provide_reference_pack_inputs", "provide_question_research_inputs"] as const)("%s 接受没有格式前缀的完整材料正文", kind => {
    const introduction = "本公司成立于2015年，主要面向机构客户提供健康管理设备。\n产品采用多通道传感技术，创建连续服务能力；以下是修改后的产品资料。\n设备支持本地报告和历史记录，适用范围以正式产品说明为准。";
    expect(parse([kind], introduction).action).toEqual({ kind, revision: 17 });
    expect(parse([kind], "公司主营产品为便携式检测终端，服务中医馆和康养机构。").action).toEqual({ kind, revision: 17 });
    expect(parse([kind], "", 1).action).toEqual({ kind, revision: 17 });
    expect(parse([kind], "   ").action).toBeNull();
  });
  it.each([
    "采用多通道传感技术，附件为产品说明书。",
    "创建服务能力和客户档案是产品支持的业务场景。",
    "修改后的产品资料，包括型号、使用场景和售后说明。",
    "企业资料已更新，供本轮选择和核对产品身份。",
  ])("普通附件说明中的动作词不被误挡：%s", text => {
    expect(parse(["provide_reference_pack_inputs"], text, 1).action).toEqual({ kind: "provide_reference_pack_inputs", revision: 17 });
    expect(parse(["provide_question_research_inputs"], text, 1).action).toEqual({ kind: "provide_question_research_inputs", revision: 17 });
  });
  it.each([
    "继续", "同意", "确认", "取消", "暂停", "下一步", "请继续", "先确认", "同意并继续",
    "不要上传，先继续", "不要确认当前写作方案", "我不确认问题定位", "确认？", "取消；暂停",
    "好的", "可以", "没问题", "收到", "不要", "不用", "OK", "继续，",
  ])("纯控制或否定指令不能伪装成材料：%s", text => {
    for (const kind of ["provide_reference_pack_inputs", "provide_question_research_inputs"] as const) {
      expect(parse([kind], text).action).toBeNull();
      expect(parse([kind], text, 1).action).toBeNull();
    }
  });
  it("只在唯一材料输入停点接受普通正文，不吞其他动作或模糊的材料类别", () => {
    const text = "本公司采用便携式终端开展机构健康服务。";
    expect(parse(["confirm_core_positioning"], text, 1).action).toBeNull();
    expect(parse(["choose_p0_route"], text).action).toBeNull();
    expect(parse(["provide_reference_pack_inputs", "provide_question_research_inputs"], text, 1).action).toBeNull();
    expect(parse(["provide_reference_pack_inputs", "revise_current_step"], "修改：请补充产品型号", 1).action).toEqual({ kind: "revise_current_step", revision: 17, instructions: "请补充产品型号" });
    expect(parse(["provide_reference_pack_inputs"], "修改：请补充产品型号", 1).action).toBeNull();
    expect(parseContentConfirmationInput({ ...progress(["provide_reference_pack_inputs"]), runnerRevision: null }, text, 1).action).toBeNull();
  });
  it.each(["1", "25", "便携式AI中医健康检测终端推荐", "如何选择适合中医馆的便携式设备？", "康养机构采用哪种健康检测设备更合适？", "How to choose a portable health terminal?"])("选题停点直接接收普通问题或正整数编号：%s", text => {
    expect(parse(["choose_question"], text).action).toEqual({ kind: "choose_question", revision: 17, selection: text });
    expect(parse(["choose_question"], text, 1).action).toEqual({ kind: "choose_question", revision: 17, selection: text });
    expect(parse(["choose_question", "provide_question_research_inputs"], text).action).toEqual({ kind: "choose_question", revision: 17, selection: text });
  });
  it.each(["继续", "同意", "确认", "取消", "请继续", "好的", "不要确认", "继续制作品牌长文", "文风：A", "文风:A", "文风 A", "方案 A", "方案：B", "文章类型：P01", "方向：服务能力", "额外要求：无", "品牌认知：不充分", "文章池：1、5", "构思参考：1、5", "A", "0", "-1", "1.5"])("选题停点不把控制句、其他字段或无效编号当问题：%s", text => {
    expect(parse(["choose_question"], text).action).toBeNull();
    expect(parse(["choose_question", "provide_question_research_inputs"], text).action).toBeNull();
  });
  it("直接题目只作用于选题阶段，材料说明和修订校验仍保留", () => {
    expect(parse(["confirm_blueprint"], "如何选择便携式设备？").action).toBeNull();
    expect(parse(["choose_question", "provide_question_research_inputs"], "资料：本题同期监控回答").action).toEqual({ kind: "provide_question_research_inputs", revision: 17 });
    expect(parse(["choose_question", "provide_question_research_inputs"], "本期监控回答与信源表", 1).action).toEqual({ kind: "provide_question_research_inputs", revision: 17 });
    expect(parseContentConfirmationInput({ ...progress(["choose_question"]), runnerRevision: null }, "1").action).toBeNull();
    expect(parse(["choose_question"], "字".repeat(20_001)).action).toBeNull();
  });
  it("使用当前修订号和可用动作，并经现有 schema 校验", () => {
    const value = parse(["confirm_competitors"], "确认比较对象").action;
    expect(contentProductionActionSchema.safeParse(value).success).toBe(true);
    expect(parse(["confirm_core_positioning"], "确认比较对象").action).toBeNull();
    expect(parseContentConfirmationInput({ ...progress(["confirm_competitors"]), runnerRevision: null }, "确认比较对象").action).toBeNull();
    expect(parse(["choose_question"], `选择问题：${"字".repeat(20_001)}`).action).toBeNull();
    expect(contentConfirmationInputHint(progress(["confirm_core_positioning"]))).toContain("确认核心定位");
  });
});
