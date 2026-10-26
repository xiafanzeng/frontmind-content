import {Brain,LoaderCircle,Wrench} from "lucide-react";
import MarkdownRenderer from "@frontmind/module-ui/components/MarkdownRenderer";
import {compareProcessSummaries,processStatusText,type ConversationProcess} from "../contracts/conversation-process";
import "./conversation-process.css";

/** A chronological stream of public summaries. Icons identify the two kinds;
 * headings and tool counters would obscure what actually happened. */
export default function ConversationExecutionProcess({process,onRecover}:{process:ConversationProcess;onRecover?:()=>void}){
 const callingTool=process.tools.some(item=>item.status==="running");
 const rows=[...process.thinking.map(item=>({...item,kind:"thinking" as const})),...process.tools.map(item=>({...item,kind:"tool" as const}))].sort((a,b)=>compareProcessSummaries(a,b,process.startedAt));
 const status=<div className={process.status==="running"?"cp-process-status cp-process-activity":"cp-process-status"} role="status">{process.status==="running"&&(callingTool?<Wrench size={15} aria-label="工具"/>:<Brain size={15} aria-label="思考"/>)}<span>{process.status==="running"?(callingTool?"正在调用工具":"正在思考"):processStatusText[process.status]}</span>{process.status==="running"&&<LoaderCircle className="cp-process-spinner" size={13}/>}</div>;
 return <section className={`cp-process is-${process.status}`} data-process-id={process.id} aria-label="本次执行过程">
  {process.status!=="running"&&status}

  <ol className="cp-process-stream" id={`process-${process.id}`}>{rows.map(item=><li key={item.id} hidden={item.status==="running"} data-summary-id={item.id} data-summary-kind={item.kind} data-summary-origin={item.summaryOrigin??"record"} data-summary-status={item.status} className={item.status==="failed"?"is-failed":item.kind==="thinking"?"is-thinking":""}>
   {item.kind==="thinking"?<Brain size={15} aria-label="思考"/>:<Wrench size={15} aria-label="工具"/>}<div><MarkdownRenderer content={item.text} allowCopy={false} className="cp-process-summary"/>{item.kind==="tool"&&<small className="cp-process-row-state">{({running:"进行中",completed:"已返回",failed:"失败",unknown:"结果未确认",cancelled:"已取消",recorded:"已记录",awaiting_input:"等待确认"})[item.status]}</small>}{item.pendingImageText&&<p>本次提取尚未识别图片文字。</p>}{item.reason&&<p>{item.reason} {item.nextStep}</p>}</div>
  </li>)}</ol>
  {process.status==="running"&&status}
  {process.status!=="running"&&!rows.length&&<p className="cp-process-empty">执行记录尚未返回。</p>}
  {process.reason&&!rows.some(item=>item.reason===process.reason)&&<p className="cp-process-reason">{process.reason} {process.nextStep}</p>}
  {process.recovery&&<p className="cp-process-recovery">{process.recovery}</p>}
  {onRecover&&<button className="cp-live-retry" type="button" onClick={onRecover}>恢复当前执行</button>}
 </section>;
}
