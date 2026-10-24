import {useEffect,useState} from "react";
import type {ContentConversation} from "./host";
import type {ContentProductionExecutionFailure} from "../contracts/content-production";
import {receivedContentIntake} from "../contracts/content-intake-receipt";

type Notice={id:string;code:"model_fallback"|"model_failure";reason:string};
const reasons:Record<string,string>={timeout:"模型服务响应超时",connection:"无法连接模型服务",rate_limit:"模型服务限流",upstream:"模型上游服务返回错误",access:"模型服务认证或权限异常",quota:"模型服务额度异常",request:"模型请求被服务拒绝",unknown:"具体原因未提供"};
// 仅显示明确的服务枚举，绝不把原始错误、工具参数或内部推理显示给用户。
export function executionNotices(conversation:ContentConversation):Notice[]{
 const entries=conversation.execution?.timeline??[];
 const turn=entries.at(-1)?.turnId;
 return entries.flatMap(entry=>{
  if(entry.turnId!==turn||entry.kind!=="status")return [];
  const value=(entry as unknown as {serviceNotice?:unknown}).serviceNotice;
  if(!value||typeof value!=="object")return [];
  const notice=value as {code?:unknown;reason?:unknown};
  if(notice.code!=="model_fallback"&&notice.code!=="model_failure")return [];
  return [{id:entry.id,code:notice.code,reason:typeof notice.reason==="string"&&Object.hasOwn(reasons,notice.reason)?notice.reason:"unknown"}];
 });
}
export type FeedbackObservation={taskId:string;checkedAt:number;error?:boolean;executionFailure?:ContentProductionExecutionFailure|null};
export default function ExecutionFeedback({conversation,submitting,stopping,observation}:{conversation?:ContentConversation;submitting?:boolean;stopping?:boolean;observation?:FeedbackObservation}){
 const [now,setNow]=useState(Date.now);
 const intakeReceipt=receivedContentIntake(conversation);
 const failure=observation?.taskId===conversation?.taskId?observation?.executionFailure:null;
 const active=!intakeReceipt&&!failure&&(!!submitting||!!stopping||["running","pending"].includes(conversation?.status??""));
 useEffect(()=>{if(!active)return;setNow(Date.now());const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[active,conversation?.id]);
 if(!conversation||intakeReceipt)return null;
 // 旧对话的列表状态可能已回到 idle；执行时间线仍保留已确认的终态。
 const terminal=conversation.execution?.timeline.findLast(e=>e.kind==="status");
 const status=failure?"error":conversation.status==="idle"&&terminal?.kind==="status"&&["cancelled","error","ended"].includes(terminal.status)?terminal.status:conversation.status;
 const notices=executionNotices(conversation);
 const entries=conversation.execution?.timeline??[];
 const latest=entries.at(-1),turn=latest?.turnId;
 const start=entries.find(e=>e.turnId===turn)?.timestamp??conversation.messages.findLast(m=>m.role==="user")?.timestamp??conversation.updatedAt;
 const elapsed=Math.max(0,Math.floor((now-start)/1000));
 const pollFailed=observation?.error&&observation.taskId===conversation.taskId;
 const unacknowledged=conversation.messages.some(m=>m.generalChatDispatch);
 let text="";
 if(failure)text=`${failure.action==="positioning_market_research"?"市场研究执行失败":"本轮执行失败"}，已提交资料和执行记录已保留。`;
 else if(stopping)text="正在请求停止，等待服务器确认。";
 else if(submitting)text="正在上传资料并提交任务，请稍候。";
 else if(pollFailed)text="状态更新暂时失败，正在重试；当前无法确认服务器进度。";
 else if(conversation.status==="pending")text="任务已接收，正在等待执行。";
 else if(conversation.status==="running")text="任务正在执行，等待下一条服务端记录。";
 else if(status==="error")text="本轮执行失败，已提交资料和执行记录已保留。";
 else if(status==="cancelled")text="本轮已停止，已提交资料和执行记录保留。";
 else if(unacknowledged)text="本次提交尚未确认，请使用“重试本次提交”核对提交结果。";
 else if(status==="awaiting_input")text="等待你确认或补充材料。";
 else if(status==="completed"||status==="ended")text="本轮已结束，请查看回复、交付文件或下一步确认。";
 if(!text&&!notices.length)return null;
 const lastRecord=latest?.timestamp??start;
 return <section className="cp-execution-feedback" aria-label="执行状态反馈">
  {text&&<p role={status==="error"||pollFailed?"alert":"status"}>{text}</p>}
  {active&&<p className="cp-feedback-time" role="timer" aria-label="本轮等待时长">本轮已等待 {elapsed} 秒{!submitting&&now-lastRecord>=30000?" · 暂未收到新记录，可停止当前执行。":""}</p>}
  {notices.map(notice=><p className="cp-feedback-service" key={notice.id} role={notice.code==="model_failure"?"alert":"status"}>{notice.code==="model_fallback"?"主模型不可用，已切换备用模型（GLM-5.3）。":"模型调用失败。"}{notice.reason!=="unknown"?`原因：${reasons[notice.reason]}。`:notice.code==="model_failure"?"具体原因未提供。":""}</p>)}
 </section>;
}
