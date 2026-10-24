import type {KeyboardEvent} from "react";
import {CONTENT_PRODUCTION_RUNNER_STATUSES,contentProductionStagePosition,type ContentProductionDto,type ContentProductionJobKind} from "../contracts/content-production";
import {contentProductionPauseTitle} from "../contracts/content-production-public";
import type {ContentMessage} from "./host";
import {contentWorkflowTranscriptAnchors} from "./content-workflow-transcript";
import "./content-creation-lane.css";

/** 这六个阶段只负责展示和回看；原生工作流的独立确认节点保持不变。 */
export const CONTENT_CREATION_STAGES = [
  {title:"企业资料与范围",description:"主体资料与比较范围"},
  {title:"确认定位与资料包",description:"确认定位，形成可用资料包"},
  {title:"P0 品牌长文",description:"蓝图确认与品牌长文"},
  {title:"问题与监控数据",description:"推荐问题、问答与引用数据"},
  {title:"选题、类型与参考",description:"本题要求、文章类型与参考"},
  {title:"蓝图、写作与交付",description:"定位、蓝图、写作与导出"},
] as const;

export type ContentCreationNavigation={messageId?:string;latest?:boolean;stageIndex:number};
export type ContentCreationLaneProps={
  progress:ContentProductionDto|null;
  messages:readonly ContentMessage[];
  conversationId:string;
  kind:"pack"|"article";
  /** false 表示当前文章尚未绑定已确认的资料包。 */
  boundPack?:boolean;
  /** 已确认资料包包含 P0，可证明品牌长文已交付；不会据此伪造聊天锚点。 */
  packIncludesP0?:boolean;
  onNavigate(request:ContentCreationNavigation):void;
  inspectedStage?:number|null;
  onOpenPack?(stageIndex:number):void;
};
type MarkedMessage=ContentMessage&{contentWorkflowStatus?:string;contentWorkflowKind?:ContentProductionJobKind};
type StepState="pending"|"current"|"done";
type LaneTarget=ContentCreationNavigation|"pack"|null;

/** 位置 13 同时容纳数据导入和问题选择，必须结合原生状态才能区分。 */
export function contentCreationStageIndex(position:number,status?:string|null,kind?:ContentProductionJobKind|null):number|null {
  if(kind==="article"&&status==="awaiting_competitor_selection")return 4;
  if(status==="awaiting_question_selection"||status==="question_selection")return 4;
  if(status==="awaiting_question_research_inputs"||status==="question_research")return 3;
  if(!Number.isInteger(position)||position<1||position>20)return null;
  if(position<=4)return 0;
  if(position<=7)return 1;
  if(position<=12)return 2;
  if(position===13)return null;
  if(position<=16)return 4;
  return 5;
}

function reviewStatus(message:MarkedMessage):string|null {
  if(message.contentWorkflowStatus&&CONTENT_PRODUCTION_RUNNER_STATUSES.includes(message.contentWorkflowStatus))return message.contentWorkflowStatus;
  for(const file of message.outputFiles??[]){
    const name=file.fileName.replace(/\\/gu,"/").split("/").at(-1)??file.fileName;
    for(const status of CONTENT_PRODUCTION_RUNNER_STATUSES){
      if(new RegExp(`(?:^|[_-])${status}(?:[._-]r\\d+)\\.(?:md|html?)$`,"iu").test(name))return status;
    }
  }
  return null;
}

/** 使用工作流标记及原生确认稿文件名，绝不把正文关键词当成历史阶段。 */
export function contentCreationTranscriptAnchors(messages:readonly MarkedMessage[]):Map<number,string>{
  const anchors=new Map<number,string>();
  messages.forEach((message,index)=>{
    const status=reviewStatus(message);
    const position=status?contentProductionStagePosition(null,status):[...contentWorkflowTranscriptAnchors([message]).keys()][0];
    let stage=position===undefined?null:contentCreationStageIndex(position,status,message.contentWorkflowKind);
    // 旧版明确记录的第 4 阶段属于“问题与监控数据”，可安全兼容。
    if(stage===null&&message.contentPhase===3&&message.contentWorkflowPosition===undefined)stage=3;
    if(stage===null||anchors.has(stage))return;
    const preceding=messages[index-1];
    anchors.set(stage,message.role==="assistant"&&preceding?.role==="user"?preceding.id:message.id);
  });
  return anchors;
}

export function contentCreationLaneModel(input:Pick<ContentCreationLaneProps,"progress"|"messages"|"kind"|"boundPack"|"packIncludesP0">&{hasPackSource?:boolean}){
  const {progress,messages,kind,boundPack,packIncludesP0,hasPackSource=false}=input;
  const status=progress?.workflowStatus??progress?.confirmation??progress?.currentStage??null;
  const position=progress?contentProductionStagePosition(progress.currentStage,status):0;
  const missingPack=kind==="article"&&boundPack===false;
  const current=missingPack?0:contentCreationStageIndex(position,status,progress?.jobKind)??contentCreationStageIndex(position,progress?.currentStage,progress?.jobKind)??(kind==="pack"?0:boundPack?2:0);
  const anchors=contentCreationTranscriptAnchors(messages);
  const observed=new Set(anchors.keys());
  for(const confirmation of progress?.completedConfirmations??[]){
    const stage=contentCreationStageIndex(contentProductionStagePosition(null,confirmation),confirmation,progress?.jobKind);
    if(stage!==null)observed.add(stage);
  }
  const ownPackReady=status==="positioning_ready";
  const ownP0Ready=status==="p0_ready";
  const ownArticleReady=status==="completed"&&progress?.jobKind!=="reference_pack"&&progress?.jobKind!=="p0";
  const done=new Set<number>();
  // 资料包绑定证明前两阶段已经确认；不会由文章交付推断未执行的 P0 或监控数据完成。
  if(boundPack){done.add(0);done.add(1);}
  if(boundPack&&packIncludesP0)done.add(2);
  if(!missingPack){
    if(kind==="pack"&&current===1)done.add(0);
    for(const stage of observed)if(stage<current)done.add(stage);
    if(ownPackReady){done.add(0);done.add(1);}
    if(ownP0Ready)done.add(2);
    if(ownArticleReady){done.add(4);done.add(5);}
    if(current===5)done.add(4);
  }
  const steps=CONTENT_CREATION_STAGES.map((step,index)=>{
    const state:StepState=index===current?(done.has(index)?"done":"current"):done.has(index)?"done":"pending";
    const messageId=anchors.get(index);
    // 优先回看本聊天的真实消息；独立文章的资料阶段回到已有资料包源聊天。
    const target:LaneTarget=index<2&&hasPackSource&&!messageId&&(boundPack||missingPack)?"pack"
      :index===current?{stageIndex:index,latest:true}
      :messageId?{stageIndex:index,messageId}:null;
    const detail=index===current&&missingPack?"等待本文件夹的资料包"
      :index===current?contentProductionPauseTitle(status,progress?.pauseTitle??null)??step.description:step.description;
    return {...step,state,detail,target};
  });
  return {current,steps,missingPack};
}

export function ContentCreationLane(props:ContentCreationLaneProps){
  const {current,steps}=contentCreationLaneModel({...props,hasPackSource:!!props.onOpenPack});
  const activate=(target:LaneTarget,stageIndex:number)=>{if(target==="pack")props.onOpenPack?.(stageIndex);else if(target)props.onNavigate(target);};
  const keyboard=(event:KeyboardEvent<HTMLLIElement>,target:LaneTarget,stageIndex:number)=>{
    if(!target||!["Enter"," "].includes(event.key))return;
    event.preventDefault();activate(target,stageIndex);
  };
  return <aside className="cp-creation-lane" aria-label="当前聊天的六步流程" data-conversation-id={props.conversationId}>
    <div className="cp-creation-lane-head"><h2>创作流程</h2><span className="cp-creation-stage-count">{String(current+1).padStart(2,"0")} / 06</span></div>
    <p className="cp-creation-lane-sub">{props.kind==="pack"?"资料包创建与修改":"文章书写"}</p>
    <ol className="cp-creation-steps" aria-label="六步制作流程">{steps.map((step,index)=><li
      key={step.title} data-stage-index={index} data-state={step.state} data-inspected={props.inspectedStage===index||undefined}
      aria-current={index===current?"step":undefined} aria-disabled={!step.target}
      aria-label={`第 ${index+1} 步，${step.title}，${step.state==="done"?"已完成":step.state==="current"?"当前阶段":"待进行"}${step.target?"，点击回看":"，暂无对应历史"}`}
      tabIndex={step.target?0:undefined} onClick={()=>activate(step.target,index)} onKeyDown={event=>keyboard(event,step.target,index)}>
      <span className="cp-creation-step-dot" aria-hidden="true">{step.state==="done"?"✓":index+1}</span>
      <div><span className="cp-creation-step-label">{step.title}</span><span className="cp-creation-step-detail">{step.detail}</span></div>
    </li>)}</ol>
    <p className="cp-creation-route-note">{props.kind==="pack"?"此聊天负责资料与定位。确认资料包后，在文章书写聊天中继续后续阶段。":"企业资料与定位从当前文件夹的资料包带入；文章在本聊天继续推进。"}</p>
  </aside>;
}
export default ContentCreationLane;
