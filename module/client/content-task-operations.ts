import { CONTENT_PRODUCTION_CONFIRMATION_ACTIONS, type ContentProductionDto } from "../contracts/content-production";
import type { ContentProductionAction } from "../contracts/content-production";

export type TaskOperationCard = {
 id: string;
 stageIndex: number;
 kind: "action"|"upload"|"choice"|"view"|"danger"|"input";
 title: string;
 description: string;
 status: "pending-choice"|"awaiting-confirm"|"running"|"done"|"failed"|"waiting-external";
 action?: ContentProductionAction;
 params?: { choices?: string[]; inputPlaceholder?: string };
 prompt: string;
 disabled?: boolean;
};

const labels: Partial<Record<ContentProductionAction["kind"], {title:string;description:string;prompt:string}>> = {
 choose_reference_pack_route:{title:"选择资料包方式",description:"新建资料包或采用已有资料包",prompt:"新建资料包"},
 provide_reference_pack_inputs:{title:"补充企业资料",description:"上传本轮企业与品牌材料",prompt:"上传本轮资料"},
 provide_question_research_inputs:{title:"补充问答资料",description:"上传本轮监控问答与引用资料",prompt:"上传本轮资料"},
 choose_question:{title:"选择问题",description:"从当前推荐问题中选择",prompt:""},
 confirm_competitors:{title:"确认比较对象",description:"确认当前比较范围",prompt:"确认比较对象"},
 confirm_core_positioning:{title:"确认核心定位",description:"确认当前定位结果",prompt:"确认核心定位"},
 choose_p0_route:{title:"选择品牌长文方式",description:"创建或导入品牌长文",prompt:"新建 P0"},
 choose_p0_examples:{title:"选择写作规范",description:"选择工作流规范或参考例文",prompt:"P0 文风：工作流写作规范"},
 confirm_p0_blueprint:{title:"确认品牌长文方案",description:"确认后进入正文制作",prompt:"确认写作方案"},
 submit_response_brief:{title:"确认应答要求",description:"确认企业应答要求与品牌认知",prompt:"无额外要求"},
 confirm_pattern:{title:"选择文章类型",description:"采用当前推荐文章类型",prompt:"文章类型：P01"},
 choose_examples:{title:"选择写作风格",description:"选择 A 或 B 方案",prompt:"文风：A"},
 confirm_question_positioning:{title:"确认问题定位",description:"确认本题差异化定位",prompt:"确认问题定位"},
 confirm_blueprint:{title:"确认文章方案",description:"确认后进入正文写作",prompt:"确认写作方案"},
 revise_current_step:{title:"修改当前步骤",description:"按当前阶段要求调整",prompt:"修改："},
 resume_current_execution:{title:"恢复当前执行",description:"继续未完成的任务",prompt:"恢复当前执行"},
};

export function mapContentTaskOperations(progress: ContentProductionDto|null|undefined, ctx:{busy?:boolean;failed?:boolean;pendingConfirmation?:boolean;taskId?:string|null;startupConfig?:boolean;retryStartup?:string|null;resumableAssembly?:boolean;handoff?:boolean}={}):TaskOperationCard[] {
 if(!progress)return ctx.startupConfig?[{id:"start-production",stageIndex:0,kind:"upload",title:"上传资料并开始处理",description:"核对当前主体与资料范围后启动任务",status:"pending-choice",prompt:"新建资料包",disabled:ctx.busy}]:[];
 const revision=progress.runnerRevision;
 if(ctx.failed||progress.executionFailure)return [{id:"retry",stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"action",title:"重试当前步骤",description:"保留当前任务与确认信息后重新尝试",status:"failed",action:revision==null?undefined:{kind:"resume_current_execution",revision},prompt:"恢复当前执行",disabled:ctx.busy||revision==null}];
 const running=ctx.busy||progress.executionStatus==="running"||progress.executionStatus==="pending"||String(progress.workflowStatus??"").startsWith("running_");
 if(running)return [{id:"running",stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"view",title:"正在处理",description:progress.pauseTitle??"等待真实任务状态更新",status:"running",prompt:"",disabled:true}];
 if(!revision&&progress.availableActions.length===0)return [];
 const confirmationKinds=progress.confirmation
  ? CONTENT_PRODUCTION_CONFIRMATION_ACTIONS[progress.confirmation as keyof typeof CONTENT_PRODUCTION_CONFIRMATION_ACTIONS] ?? []
  : null;
 const allowed=confirmationKinds
  ? progress.availableActions.filter(kind=>confirmationKinds.includes(kind))
  : progress.availableActions;
 const cards:TaskOperationCard[]=[];
 for(const kind of allowed){
  const meta=labels[kind]; if(!meta)continue;
  let action:ContentProductionAction|undefined;
  if(revision!=null){
   if(["choose_question","choose_core_positioning_direction","revise_current_step","choose_reference_pack_route","choose_p0_route","choose_p0_examples","choose_examples","confirm_pattern","submit_response_brief"].includes(kind))continue;
   if(kind==="choose_reference_pack_route"||kind==="revise_current_step")continue;
   else action={kind,revision} as ContentProductionAction;
  }
  cards.push({id:kind,stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:["provide_reference_pack_inputs","provide_question_research_inputs"].includes(kind)?"upload":"action",title:meta.title,description:meta.description,status:progress.confirmation?"awaiting-confirm":"pending-choice",action,prompt:meta.prompt,disabled:ctx.busy||ctx.pendingConfirmation||(!action&&kind!=="choose_question"&&kind!=="choose_core_positioning_direction"&&kind!=="revise_current_step")});
 }
 if(revision!=null&&allowed.includes("revise_current_step"))cards.push({id:"revise-current-step",stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"input",title:"返回修改方案",description:"补充本阶段需要调整的内容",status:"awaiting-confirm",prompt:"修改当前步骤",params:{inputPlaceholder:"请描述希望修改的内容"},disabled:ctx.busy||ctx.pendingConfirmation});
 if(revision!=null&&allowed.includes("choose_reference_pack_route"))for(const route of ["use","create"] as const)cards.push({id:`reference-pack-route-${route}`,stageIndex:0,kind:"choice",title:route==="use"?"采用已有资料包":"创建新资料包",description:route==="use"?"选择已有主体资料包继续":"根据本轮材料创建资料包",status:"awaiting-confirm",action:{kind:"choose_reference_pack_route",revision,route},prompt:route==="use"?"采用已有资料包":"新建资料包"});
 if(revision!=null&&allowed.includes("choose_reference_pack_route"))for(const route of ["use","create"] as const)cards.push({id:`reference-pack-route-${route}`,stageIndex:0,kind:"choice",title:route==="use"?"采用已有资料包":"创建新资料包",description:route==="use"?"选择已有主体资料包继续":"根据本轮材料创建资料包",status:"awaiting-confirm",action:{kind:"choose_reference_pack_route",revision,route},prompt:route==="use"?"采用已有资料包":"新建资料包"});\n if(revision!=null&&allowed.includes("choose_p0_route"))for(const route of ["create","import"] as const)cards.push({id:`p0-route-${route}`,stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"choice",title:route==="create"?"新建品牌长文":"导入已有品牌长文",description:"选择本轮品牌长文来源",status:"awaiting-confirm",action:{kind:"choose_p0_route",revision,route},prompt:route==="create"?"新建 P0":"导入 P0"});
 if(revision!=null&&allowed.includes("choose_p0_examples"))for(const route of ["workflow","top20"] as const)cards.push({id:`p0-examples-${route}`,stageIndex:2,kind:"choice",title:route==="workflow"?"采用工作流写作规范":"采用前二十篇参考例文",description:"选择品牌长文写作参考",status:"awaiting-confirm",action:{kind:"choose_p0_examples",revision,route},prompt:route==="workflow"?"P0 文风：工作流写作规范":"P0 文风：Top20"});
 if(revision!=null&&allowed.includes("choose_examples"))for(const route of ["A","B"] as const)cards.push({id:`examples-${route}`,stageIndex:4,kind:"choice",title:`方案 ${route}`,description:"选择本轮文章表达风格",status:"awaiting-confirm",action:{kind:"choose_examples",revision,route},prompt:`文风：${route}`});
 if(revision!=null&&allowed.includes("confirm_pattern"))for(const pattern of progress.choices.map(value=>/P0[1-6]/u.exec(value)?.[0]).filter((value):value is string=>Boolean(value)))cards.push({id:`pattern-${pattern}`,stageIndex:4,kind:"choice",title:pattern,description:"选择文章类型",status:"awaiting-confirm",action:{kind:"confirm_pattern",revision,selectedPattern:pattern as `P0${1|2|3|4|5|6}`},prompt:`文章类型：${pattern}`});
 if(revision!=null&&allowed.includes("submit_response_brief"))for(const recognition of ["sufficient","insufficient","uncertain"] as const)cards.push({id:`recognition-${recognition}`,stageIndex:4,kind:"choice",title:({sufficient:"品牌认知充分",insufficient:"品牌认知不充分",uncertain:"品牌认知不确定"} as const)[recognition],description:"确认企业当前品牌认知程度",status:"awaiting-confirm",action:{kind:"submit_response_brief",revision,noExtraRequirements:true,aiBrandRecognition:recognition},prompt:`无额外要求；品牌认知：${({sufficient:"充分",insufficient:"不充分",uncertain:"不确定"} as const)[recognition]}`});
 if(allowed.includes("choose_question"))progress.choices.forEach((choice,index)=>cards.push({id:`question-${index}`,stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"choice",title:choice,description:"选择此问题作为当前研究对象",status:"pending-choice",prompt:`选择问题：${choice.replace(/^选择\s*/u,"").replace(/^\d+[.．、]\s*/u,"")}`,disabled:ctx.busy||ctx.pendingConfirmation}));
 if(allowed.includes("choose_core_positioning_direction"))progress.choices.forEach((choice,index)=>cards.push({id:`direction-${index}`,stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"choice",title:choice,description:"选择当前定位方向",status:"pending-choice",prompt:choice.startsWith("方向")?choice:`方向：${choice}`,disabled:ctx.busy||ctx.pendingConfirmation}));
 if(ctx.startupConfig)cards.push({id:"start-production",stageIndex:0,kind:"upload",title:"上传资料并开始处理",description:"核对当前主体与资料范围后启动任务",status:"pending-choice",prompt:"新建资料包",disabled:ctx.busy});
 if(ctx.retryStartup)cards.push({id:"retry-startup",stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"action",title:"重试启动原任务",description:"使用原始任务输入重新提交",status:"failed",prompt:ctx.retryStartup,disabled:ctx.busy});
 if(ctx.resumableAssembly)cards.push({id:"resume-assembly",stageIndex:1,kind:"action",title:"继续未完成步骤",description:"继续资料包装配，不重新生成研究或定位",status:"pending-choice",prompt:"继续未完成步骤",disabled:ctx.busy});
 if(ctx.handoff)cards.push({id:"handoff",stageIndex:Math.max(0,Math.min(5,(progress.progressPosition??1)-1)),kind:"action",title:progress.workflowStatus==="positioning_ready"?"继续制作品牌长文":"继续问题与监控数据",description:"按现有会话阶段继续后续流程",status:"pending-choice",prompt:progress.workflowStatus==="positioning_ready"?"继续 P0":"继续问题文章",disabled:ctx.busy});
 return cards;
}
