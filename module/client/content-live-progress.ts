import type {ContentProductionDto} from "../contracts/content-production";

/** 只翻译服务端原生状态，不按等待时间猜进度或生成百分比。 */
export function contentLiveProgressLabel(progress:ContentProductionDto|null|undefined):string|null {
 if(!progress)return null;
 const kind=progress.jobKind==="p0"?"品牌长文":"问题文章";
 if(["running_p0_production","running_article_production"].includes(progress.workflowStatus??"")){
  const steps:Record<string,string>={draft:`正在生成${kind}初稿`,edit:`正在编辑${kind}`,style:`正在处理${kind}文风`,polish:`正在润色${kind}`,finalize:`正在整理${kind}终稿`,repair:`正在修订${kind}`,titles:"正在生成候选标题",title_review:"正在核对候选标题",deliver:"正在导出交付文件"};
  return steps[progress.productionStep??""]??`正在制作${kind}`;
 }
 const states:Record<string,string>={
  running_reference_material_intake:"正在读取和整理企业资料",
  running_positioning_market_research:"正在研究市场与比较对象",
  running_positioning_value_synthesis:"正在综合定位方向",
  running_positioning_competitive_tiering:"正在梳理比较对象",
  running_positioning_brand_placement:"正在分析品牌定位",
  running_positioning_positioning_polish:"正在完善定位表述",
  running_positioning_choice_map:"正在整理比较范围",
  running_positioning_direction_generation:"正在生成定位方向",
  running_positioning_direction_critique:"正在核对定位方向",
  running_core_positioning_synthesis:"正在生成核心定位",
  running_core_positioning_critique:"正在核对核心定位",
  running_reference_pack_assembly:"正在装配品牌资料包",
  running_p0_example_discovery:"正在整理品牌长文参考",
  running_p0_blueprint:"正在生成品牌长文写作方案",
  running_reference_pack_p0_commit:"正在将品牌长文写入资料包",
  running_answer_analysis:"正在分析本题问答资料",
  running_question_positioning:"正在生成本题差异化定位",
  running_article_blueprint:"正在生成问题文章写作方案",
 };
 return states[progress.workflowStatus??""]??null;
}
