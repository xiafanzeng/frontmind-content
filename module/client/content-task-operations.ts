import { CONTENT_PRODUCTION_CONFIRMATION_ACTIONS, contentProductionActionSchema, contentProductionStagePosition, type ContentProductionAction, type ContentProductionConfirmation, type ContentProductionDto } from "../contracts/content-production";
import { CONTENT_PRODUCTION_PATTERNS } from "../contracts/content-production-public";
import { contentCreationStageIndex } from "./ContentCreationLane";

/** 卡片只描述服务端已开放的动作；表单字段在提交时才组装为原有动作结构。 */
export type TaskOperationForm =
 | {type:"text";label:string;placeholder:string;attach?:boolean;suggestions?:string[];submitLabel?:string}
 | {type:"upload";label:string;minFiles:number;note:boolean;hint?:string}
 | {type:"response-brief"}
 | {type:"examples";pool:boolean};

export type TaskOperationCard = {
 id: string;
 stageIndex: number;
 kind: "action"|"choice"|"input"|"upload"|"form"|"view";
 title: string;
 description: string;
 status: "pending-choice"|"awaiting-confirm"|"running"|"done"|"failed"|"waiting-external";
 action?: ContentProductionAction;
 form?: TaskOperationForm;
 prompt: string;
 primary?: boolean;
 disabled?: boolean;
};

export type TaskOperationInput = {
 text?: string;
 fileCount?: number;
 route?: "A"|"B";
 pool?: string;
 noPool?: boolean;
 requirementsMode?: "none"|"custom";
 requirements?: string;
 recognition?: "sufficient"|"insufficient"|"uncertain";
};

/** 每个暂停点的待确认内容与确认后的下一步，只说明原工作流已有的行为。 */
export const CONTENT_PAUSE_GUIDE: Record<ContentProductionConfirmation, {pending:string;next:string}> = {
 awaiting_reference_pack_route:{pending:"选择采用已有品牌资料包，或根据本轮材料新建。",next:"采用已有资料包时登记该资料包；新建时读取材料并开展公开研究。"},
 awaiting_reference_pack_input:{pending:"补充企业、品牌或产品材料，可附文字说明。",next:"读取材料并开展公开研究，生成比较范围预览。"},
 awaiting_competitor_selection:{pending:"核对比较范围预览中的候选对象，可保留、删除或新增名称。",next:"生成定位方向与核心定位确认稿。"},
 awaiting_core_positioning_direction:{pending:"从候选定位方向中选择一项。",next:"按所选方向生成核心定位确认稿。"},
 awaiting_core_positioning_confirmation:{pending:"审阅核心定位确认稿。",next:"定稿并导出品牌资料包。"},
 awaiting_p0_route:{pending:"选择新建品牌长文，或导入已有文章。",next:"新建时匹配参考例文并生成写作方案；导入时登记原文。"},
 awaiting_p0_example_confirmation:{pending:"选择品牌深度文章的写作参考。",next:"生成品牌深度文章写作方案。"},
 awaiting_p0_blueprint_confirmation:{pending:"审阅品牌深度文章写作方案（结构、篇幅与选材）。",next:"开始正文写作、编辑和候选标题，完成后交付。"},
 awaiting_question_research_inputs:{pending:"上传本轮监控问答表、AI 完整回答或信源明细。",next:"导入问答与引用数据，生成可选问题。"},
 awaiting_question_selection:{pending:"选择本次优化的问题，也可填写序号或完整问题。",next:"带入该题的回答与引用，生成应答要求确认稿。"},
 awaiting_response_brief:{pending:"填写本题企业应答要求（或明确无额外要求），并判断回答中的品牌认知。",next:"分析回答要点并推荐文章类型。"},
 awaiting_pattern_confirmation:{pending:"采用推荐的文章类型，或改选其他类型。",next:"准备文风方案与本题参考文章。"},
 awaiting_example_confirmation:{pending:"选择文风方案；需要时选择 1—2 篇文章池构思参考，或明确不采用。",next:"进入本题定位或写作方案步骤。"},
 awaiting_question_positioning_confirmation:{pending:"审阅本题差异化定位确认稿。",next:"生成本题写作方案。"},
 awaiting_blueprint_confirmation:{pending:"审阅本题写作方案（结构、篇幅与参考）。",next:"开始正文写作、编辑、候选标题与导出。"},
};

const direct: Partial<Record<ContentProductionAction["kind"], {title:string;description:string;prompt:string}>> = {
 confirm_competitors:{title:"确认比较对象",description:"按当前比较范围继续",prompt:"确认比较对象"},
 confirm_core_positioning:{title:"确认核心定位",description:"确认后导出品牌资料包",prompt:"确认核心定位"},
 confirm_p0_blueprint:{title:"确认写作方案，开始写作",description:"按当前写作方案写品牌长文",prompt:"确认写作方案"},
 confirm_question_positioning:{title:"确认本题定位",description:"确认后生成本题写作方案",prompt:"确认问题定位"},
 confirm_blueprint:{title:"确认写作方案，开始写作",description:"按当前写作方案写问题文章",prompt:"确认写作方案"},
};
const patternIds = new Map<string,string>(CONTENT_PRODUCTION_PATTERNS.map(([id,label])=>[label,id]));
const recognitionText = {sufficient:"充分",insufficient:"不充分",uncertain:"不确定"} as const;
const numbered = /^(?:选择\s*)?\d+(?:[.．、]\s*|$)/u;

/** 原生停点中的位置与六步流程对应；无法判断时保留在第一步。 */
export function contentOperationStage(progress: ContentProductionDto|null|undefined): number {
 const status=progress?.workflowStatus??progress?.confirmation??null;
 return contentCreationStageIndex(contentProductionStagePosition(progress?.currentStage??null,status),status,progress?.jobKind)??0;
}

/** 选项文字可能是协议编号（P01）或已翻译的中文类型名；两者都映射回原编号。 */
export function contentPatternChoice(choice: string): {selectedPattern?:string;recommended:boolean;label:string;id?:string}|null {
 const value=choice.trim();
 const recommended=/^采用(?:本轮)?推荐/u.test(value);
 const label=value.replace(/^(?:采用(?:本轮)?推荐(?:的)?(?:文章类型)?|选择|改用)\s*[:：]?\s*/u,"").trim();
 const id=/\bP0[1-6]\b/u.exec(value)?.[0]??patternIds.get(label);
 if(recommended)return {recommended:true,label:label||"推荐类型",...(id?{id}:{})};
 return id?{selectedPattern:id,recommended:false,label:patternIds.has(label)?label:(CONTENT_PRODUCTION_PATTERNS.find(([key])=>key===id)?.[1]??id)}:null;
}

export function mapContentTaskOperations(progress: ContentProductionDto|null|undefined, ctx:{busy?:boolean;failed?:boolean;pendingConfirmation?:boolean;taskId?:string|null;startupConfig?:boolean;startupKind?:"pack"|"article";retryStartup?:string|null;resumeExecution?:boolean;resumableAssembly?:boolean;handoff?:boolean;delivered?:boolean;startupStopped?:boolean;packReady?:boolean}={}):TaskOperationCard[] {
 const stageIndex=contentOperationStage(progress);
 const startup=():TaskOperationCard=>({id:"start-production",stageIndex:0,kind:"upload",title:"上传资料并开始处理",description:ctx.startupKind==="article"?"上传监控问答表或本题资料，核对后启动":"上传企业、品牌或产品资料，核对后启动",status:"pending-choice",prompt:"上传本轮资料",form:{type:"upload",label:"本轮资料",minFiles:0,note:true,hint:"上传文件或填写资料说明，二者至少一项；例如官网地址、产品重点或需要排除的内容。"},primary:true,disabled:ctx.busy});
 const retry=(index:number):TaskOperationCard=>({id:"retry-startup",stageIndex:index,kind:"action",title:"重试启动原任务",description:"使用原始任务输入重新提交",status:"failed",prompt:ctx.retryStartup!,primary:true,disabled:ctx.busy});
 const restart:TaskOperationCard={id:"restart-chat",stageIndex:0,kind:"action",title:"新建聊天重新开始",description:"原聊天与附件保留；在同一主体下重新提交资料",status:"failed",prompt:"",primary:true,disabled:ctx.busy};
 if(!progress){const cards:TaskOperationCard[]=[];if(ctx.startupConfig)cards.push(startup());if(ctx.retryStartup)cards.push(retry(0));return cards;}
 const revision=progress.runnerRevision;
 if(ctx.startupStopped&&!ctx.retryStartup)return [restart];
 if(ctx.failed||progress.executionFailure){
  if(ctx.retryStartup)return [retry(stageIndex)];
  if(progress.availableActions.includes("resume_current_execution"))return [{id:"resume-execution",stageIndex,kind:"action",title:"恢复当前执行",description:"保留已完成的结果与确认信息，从中断处继续",status:"failed",action:revision==null?undefined:{kind:"resume_current_execution",revision},prompt:"恢复当前执行",primary:true,disabled:ctx.busy||revision==null}];
  if(!progress.availableActions.includes("repair_article_facts"))return [];
 }
 // running_* 只是原生阶段名；事实返工和中断恢复时它也会保留，执行与否以 executionStatus 为准。
 const running=ctx.busy||(progress.executionStatus?["running","pending"].includes(progress.executionStatus):String(progress.workflowStatus??"").startsWith("running_")&&!progress.availableActions.length);
 if(running){const runningCards:TaskOperationCard[]=[{id:"running",stageIndex,kind:"view",title:"正在处理",description:progress.pauseTitle??"等待真实任务状态更新",status:"running",prompt:"",disabled:true}];if(ctx.resumableAssembly&&!ctx.busy)runningCards.push({id:"resume-assembly",stageIndex:1,kind:"action",title:"继续未完成步骤",description:"继续资料包装配，不重新生成研究或定位",status:"pending-choice",prompt:"继续未完成步骤",primary:true,disabled:ctx.busy});return runningCards;}
 const cards:TaskOperationCard[]=[];
 const locked=ctx.busy||ctx.pendingConfirmation;
 const add=(card:Omit<TaskOperationCard,"stageIndex"|"status"|"disabled">&{disabled?:boolean})=>cards.push({stageIndex,status:progress.confirmation?"awaiting-confirm":"pending-choice",...card,disabled:locked||card.disabled});
 if(revision!=null){
  const confirmationKinds=progress.confirmation?CONTENT_PRODUCTION_CONFIRMATION_ACTIONS[progress.confirmation]??[]:null;
  const allowed=new Set(confirmationKinds?progress.availableActions.filter(kind=>confirmationKinds.includes(kind)):progress.availableActions);
  const choices=progress.choices;
  for(const kind of ["confirm_competitors","confirm_core_positioning","confirm_p0_blueprint","confirm_question_positioning","confirm_blueprint"] as const){
   const meta=direct[kind];if(allowed.has(kind)&&meta)add({id:kind,kind:"action",...meta,action:{kind,revision},primary:true});
  }
  if(allowed.has("choose_reference_pack_route")){
   add({id:"reference-pack-route-use",kind:"upload",title:"采用已有品牌资料包",description:"使用本轮已提供的资料包，或上传要使用的资料包",action:{kind:"choose_reference_pack_route",revision,route:"use"},prompt:"使用已有资料包",form:{type:"upload",label:"品牌资料包（已提供时可不选）",minFiles:0,note:false}});
   add({id:"reference-pack-route-create",kind:"upload",title:"新建品牌资料包",description:"根据本轮材料创建，可补充文件",action:{kind:"choose_reference_pack_route",revision,route:"create"},prompt:"新建资料包",form:{type:"upload",label:"补充材料（可选）",minFiles:0,note:false}});
  }
  for(const kind of ["provide_reference_pack_inputs","provide_question_research_inputs"] as const)if(allowed.has(kind))add({id:kind,kind:"upload",title:kind==="provide_reference_pack_inputs"?"补充企业资料":"导入问答与信源",description:kind==="provide_reference_pack_inputs"?"上传企业、品牌或产品材料":"上传监控问答表、完整回答或信源明细",action:{kind,revision},prompt:"上传本轮资料",primary:!cards.length,form:{type:"upload",label:"本轮资料",minFiles:0,note:true,hint:kind==="provide_question_research_inputs"?"监控问答表（Excel）须单独上传，每次一张。":"也可只填写资料说明，例如官网地址或产品介绍。"}});
  if(allowed.has("choose_question")){
   choices.filter(choice=>numbered.test(choice)).forEach((choice,index)=>{const selection=choice.replace(/^选择\s*/u,"").replace(/^\d+[.．、]\s*/u,"").trim();add({id:`question-${index}`,kind:"choice",title:choice.replace(/^选择\s*/u,""),description:"选择此问题作为本次优化对象",action:{kind:"choose_question",revision,selection},prompt:`选择问题：${selection}`});});
   add({id:"question-custom",kind:"input",title:"填写其他问题",description:"输入问题序号或完整问题",prompt:"选择问题：",form:{type:"text",label:"问题序号或完整问题",placeholder:"例如：3，或“药店中医健康检测设备推荐”"}});
  }
  if(allowed.has("update_competitor_selection"))add({id:"update-competitor-selection",kind:"input",title:"修改比较对象",description:"保留、删除或新增比较对象名称",prompt:"比较对象：",form:{type:"text",label:"比较对象调整",placeholder:"例如：保留甲、乙作为比较对象；删除丙；新增丁"}});
  if(allowed.has("choose_core_positioning_direction")){
   // 原生选项还包含“提交我的方向”“探索其他方向”等控制项，只有编号方向生成直接选择。
   choices.filter(choice=>/^(?:采用)?方向\s*\d+$/u.test(choice.trim())).forEach((choice,index)=>add({id:`direction-${index}`,kind:"choice",title:choice.trim(),description:"以此方向生成核心定位",action:{kind:"choose_core_positioning_direction",revision,direction:choice.trim()},prompt:`方向：${choice.trim()}`}));
   add({id:"direction-custom",kind:"input",title:"填写我的方向",description:"自定义方向，或主方向加一个辅助方向",prompt:"方向：",form:{type:"text",label:"定位方向",placeholder:"例如：采用方向 1 为主方向，方向 2 作为辅助"}});
  }
  if(allowed.has("choose_p0_route")){
   add({id:"p0-route-create",kind:"choice",title:"新建品牌长文",description:"沿用资料包，匹配参考并生成写作方案",action:{kind:"choose_p0_route",revision,route:"create"},prompt:"新建 P0"});
   add({id:"p0-route-import",kind:"upload",title:"导入已有品牌长文",description:"上传已有文章原文",action:{kind:"choose_p0_route",revision,route:"import"},prompt:"导入 P0",form:{type:"upload",label:"已有文章原文",minFiles:1,note:false}});
  }
  if(allowed.has("choose_p0_examples"))for(const route of ["workflow","top20"] as const)add({id:`p0-examples-${route}`,kind:"choice",title:route==="workflow"?"采用工作流写作规范":"采用参考例文",description:route==="workflow"?"按工作流规范写品牌长文":"参考匹配的同类文章写法",action:{kind:"choose_p0_examples",revision,route},prompt:route==="workflow"?"P0 文风：工作流写作规范":"P0 文风：Top20"});
  if(allowed.has("repair_article_facts"))add({id:"repair-article-facts",kind:"action",title:"按事实校验结果返工",description:progress.factGate?.issueCount?`校验发现 ${progress.factGate.issueCount} 处待核对内容，按校验结果修改正文`:"按工作流事实校验结果修改正文",action:{kind:"repair_article_facts",revision,rejectedClaimIds:[]},prompt:"按事实校验结果返工",primary:true});
  if(allowed.has("submit_response_brief"))add({id:"response-brief",kind:"form",title:"填写应答要求与品牌认知",description:"两项都填写后提交",prompt:"",primary:true,form:{type:"response-brief"}});
  if(allowed.has("confirm_pattern")){
   const options=choices.map(contentPatternChoice).filter((value):value is NonNullable<ReturnType<typeof contentPatternChoice>>=>Boolean(value));
   if(!options.some(option=>option.recommended))options.unshift({recommended:true,label:"推荐类型"});
   const seen=new Set<string>();
   for(const option of options){
    // 推荐项已对应某一类型时，不再重复列出同一类型。
    const key=option.recommended?"recommended":option.selectedPattern!;if(seen.has(key))continue;seen.add(key);if(option.recommended&&option.id)seen.add(option.id);
    add({id:`pattern-${key}`,kind:"choice",title:option.recommended?`采用推荐：${option.label}`:option.label,description:option.recommended?"采用本轮分析推荐的文章类型":`改用${option.label}`,action:option.recommended?{kind:"confirm_pattern",revision}:{kind:"confirm_pattern",revision,selectedPattern:option.selectedPattern as `P0${1|2|3|4|5|6}`},prompt:option.recommended?"采用推荐文章类型":`文章类型：${option.selectedPattern}`,primary:option.recommended});
   }
  }
  if(allowed.has("choose_examples"))add({id:"examples",kind:"form",title:"选择文风与构思参考",description:"文风与文章池分别选择",prompt:"",primary:true,form:{type:"examples",pool:choices.some(choice=>choice.includes("文章池"))}});
  if(allowed.has("revise_current_step"))add({id:"revise-current-step",kind:"input",title:"返回修改",description:"补充本阶段需要调整的内容，可附文件",prompt:"修改：",form:{type:"text",label:"修改要求",placeholder:"请描述希望修改的内容",attach:true,suggestions:choices.filter(choice=>/修改|补充|返回|更换|重新|探索|调研/u.test(choice)&&!numbered.test(choice))}});
 }
 if(ctx.startupConfig)cards.push(startup());
 if(ctx.retryStartup)cards.push(retry(stageIndex));
 if(ctx.resumeExecution&&revision!=null&&!cards.some(card=>card.id==="resume-execution"))cards.push({id:"resume-execution",stageIndex,kind:"action",title:"恢复当前执行",description:"保留已完成的结果与确认信息，从中断处继续",status:"pending-choice",action:{kind:"resume_current_execution",revision},prompt:"恢复当前执行",disabled:ctx.busy});
 if(ctx.resumableAssembly)cards.push({id:"resume-assembly",stageIndex:1,kind:"action",title:"继续未完成步骤",description:"继续资料包装配，不重新生成研究或定位",status:"pending-choice",prompt:"继续未完成步骤",primary:true,disabled:ctx.busy});
 if(ctx.handoff)cards.push({id:"handoff",stageIndex,kind:"action",title:progress.workflowStatus==="positioning_ready"?"继续制作品牌长文":"继续问题与监控数据",description:"沿用本任务已确认的资料，进入下一阶段",status:"pending-choice",prompt:progress.workflowStatus==="positioning_ready"?"继续 P0":"继续问题文章",primary:true,disabled:ctx.busy});
 if(ctx.packReady)cards.push({id:"open-article-chat",stageIndex,kind:"action",title:"新建文章书写聊天",description:"自动引用本主体的已确认资料包，继续品牌长文与问题文章",status:"pending-choice",prompt:"",primary:true,disabled:ctx.busy});
 if(ctx.delivered)cards.push({id:"revise-delivery",stageIndex,kind:"input",title:"修改交付稿",description:"按要求修改正文并更新交付文件",status:"pending-choice",prompt:"",form:{type:"text",label:"修改要求",placeholder:"例如：合并重复段落，补充第三部分的服务流程",attach:true,submitLabel:"提交修改"},disabled:ctx.busy});
 return cards;
}

type TaskOperationSubmission={action?:ContentProductionAction;prompt:string;error?:string};

/** 按卡片和表单输入组装原有动作；缺项时返回提示，不猜测用户意图。 */
export function buildTaskOperationSubmission(card:TaskOperationCard, input:TaskOperationInput, revision:number|null):TaskOperationSubmission {
 const result=assembleTaskOperation(card,input,revision);
 // 非法动作不能进入持久化的待发请求，这里与服务端使用同一份校验。
 if(result.action&&!contentProductionActionSchema.safeParse(result.action).success)return {prompt:"",error:"内容不符合提交要求，单项文字不能超过 20000 字。"};
 return result;
}

function assembleTaskOperation(card:TaskOperationCard, input:TaskOperationInput, revision:number|null):TaskOperationSubmission {
 const text=input.text?.trim()??"";
 const files=input.fileCount??0;
 const form=card.form;
 if(form?.type==="upload"){
  if(files<form.minFiles)return {prompt:"",error:form.minFiles===1?"请先选择文件。":`请至少选择 ${form.minFiles} 个文件。`};
  if(card.id==="start-production"||card.action?.kind==="provide_reference_pack_inputs"||card.action?.kind==="provide_question_research_inputs"){
   if(!files&&!text)return {prompt:"",error:"请上传文件或填写资料说明。"};
   return {action:card.action,prompt:text?`资料：${text}`:card.prompt};
  }
  return {action:card.action,prompt:card.prompt};
 }
 if(form?.type==="text"){
  if(!text)return {prompt:"",error:`请填写${form.label}。`};
  if(card.id==="revise-delivery")return {prompt:text};
  if(revision==null)return {prompt:"",error:"当前确认版本尚未就绪，请刷新后再提交。"};
  if(card.id==="revise-current-step")return {action:{kind:"revise_current_step",revision,instructions:text},prompt:`修改：${text}`};
  if(card.id==="update-competitor-selection")return {action:{kind:"update_competitor_selection",revision,selection:text},prompt:`比较对象：${text}`};
  if(card.id==="direction-custom")return {action:{kind:"choose_core_positioning_direction",revision,direction:text},prompt:`方向：${text}`};
  if(card.id==="question-custom")return {action:{kind:"choose_question",revision,selection:text},prompt:`选择问题：${text}`};
  return {prompt:"",error:"当前卡片不接受文字输入。"};
 }
 if(form?.type==="response-brief"){
  if(revision==null)return {prompt:"",error:"当前确认版本尚未就绪，请刷新后再提交。"};
  const requirements=input.requirements?.trim()??"";
  if(!input.requirementsMode)return {prompt:"",error:"请选择是否有额外应答要求。"};
  if(input.requirementsMode==="custom"&&!requirements)return {prompt:"",error:"请填写额外应答要求，或改选“无额外要求”。"};
  if(!input.recognition)return {prompt:"",error:"请判断品牌认知：充分、不充分或不确定。"};
  const brand=`品牌认知：${recognitionText[input.recognition]}`;
  return input.requirementsMode==="none"
   ?{action:{kind:"submit_response_brief",revision,noExtraRequirements:true,aiBrandRecognition:input.recognition},prompt:`无额外要求；${brand}`}
   :{action:{kind:"submit_response_brief",revision,requirements,aiBrandRecognition:input.recognition},prompt:`额外要求：${requirements}；${brand}`};
 }
 if(form?.type==="examples"){
  if(revision==null)return {prompt:"",error:"当前确认版本尚未就绪，请刷新后再提交。"};
  if(!input.route)return {prompt:"",error:"请选择文风方案 A 或 B。"};
  if(!form.pool)return {action:{kind:"choose_examples",revision,route:input.route},prompt:`文风：${input.route}`};
  if(input.noPool)return {action:{kind:"choose_examples",revision,route:input.route},prompt:`文风：${input.route}；文章池：不采用`};
  const ids=(input.pool??"").split(/[、,，\s]+/u).filter(Boolean);
  if(!ids.length)return {prompt:"",error:"请填写 1—2 个文章池编号，或选择“不采用”。"};
  if(ids.length>2||ids.some(id=>!/^[1-9]\d{0,3}$/u.test(id))||new Set(ids).size!==ids.length)return {prompt:"",error:"文章池请填写 1—2 个不同的正整数编号。"};
  return {action:{kind:"choose_examples",revision,route:input.route},prompt:`文风：${input.route}；文章池：${ids.join("、")}`};
 }
 return {action:card.action,prompt:card.prompt};
}
