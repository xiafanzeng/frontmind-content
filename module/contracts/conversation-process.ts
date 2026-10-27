import {contentExecutionActionLabels} from "./content-execution";

export const processStatusText = {running:"执行中",awaiting_input:"等待确认",completed:"已完成",failed:"执行失败",cancelled:"已取消",unknown:"结果未确认"} as const;
export type ProcessStatus = keyof typeof processStatusText;
export type ProcessSummary = {id:string;timestamp?:number;attemptStartedAt?:number;sequence?:number;finishedAt?:number;text:string;summaryOrigin?:"model";summaryRevision?:number;pendingImageText?:boolean;status:ProcessStatus|"recorded";reason?:string;nextStep?:string};
export type ConversationProcess = {id:string;userMessageId?:string;startedAt:number;finishedAt?:number;status:ProcessStatus;thinking:ProcessSummary[];tools:ProcessSummary[];retractedSummaryIds?:string[];reason?:string;nextStep?:string;recovery?:string};

const reasons = new Set(["来源地址未通过公网校验。","材料标识未登记。","材料引用不唯一。","材料超出允许范围或内容已变更。","读取要求不符合约定。","相同读取错误重复出现，已停止本次尝试。","读取请求被拒绝，历史记录未保存具体原因。","连接中断。","服务请求失败。","阶段结果未通过校验。","来源读取失败。","服务重试已耗尽。","执行结果尚未确认。","本轮执行失败。","本次执行已取消。"]);
const nextSteps = new Set(["检查网络解析或补充可核验材料；保留地址安全校验。","从材料目录复制准确标识后再读取。","从材料目录选择准确标识后再读取。","重新登记并确认材料后继续。","修正读取要求后再继续。","修正来源或材料标识后显式恢复。","核对来源和登记材料；修正后显式恢复。","检查连接后显式恢复。","检查服务与账户配置后显式恢复。","检查来源引用与结果格式后显式恢复。","检查来源或补充可核验材料。","检查服务状态后显式恢复。","检查后台诊断后显式恢复。","已有产出已保留，可显式恢复当前执行。"]);
const texts = new Set(["正在调用工具。","已接受本轮任务，等待执行记录。","已取得登记材料，供当前阶段核对。","已取得网页内容，供当前阶段核对。","已提交阶段结果；交付状态另行核验。",...Object.values(contentExecutionActionLabels).flatMap(x=>["正在处理：","正在结合登记材料处理：","正在结合网页内容核对：","正在核对已提交的阶段结果："].map(prefix=>`${prefix}${x}。`)),"正在处理：工作流阶段。"]);
for(const verb of ["正在","已完成","未能完成","结果未确认："]) for(const task of ["查看材料目录","读取登记材料","检索登记材料","提取文档内容","检索公开来源","核对网页来源","识别图片文字","提交阶段结果","检查文章字数","处理工具结果"]) texts.add(`${verb}${task}。`);

/** The backend applies this before API responses; frontend imports repeat the
 * check. Model output is one bounded public sentence, never an arbitrary trace. */
export const safeModelSummary=(value:unknown):value is string=>typeof value==="string"&&value.trim()===value&&value.length>=5&&value.length<=160&&/[\u4e00-\u9fff]/.test(value)&&!/(?:[\n\r{}\[\]`<>]|https?:\/\/|(?:\/|[A-Z]:\\)(?:Users|private|tmp|home|var|etc|[^\s/]+\/)|\\[^\s]+\\|\b(?:sk-[\w-]+|bearer\s+\S+|api[_ -]?key|authorization|password|token|secret)\b|\b\w+_\w+\b|\b\w+\s*\(|[\w.+-]+@[\w.-]+\.[a-z]+|(?<!\d)1[3-9]\d{9}(?!\d)|\b(?:\d{1,3}\.){3}\d{1,3}\b)/i.test(value);

const identity=(x:unknown):x is string=>typeof x==="string"&&/^[-\w]{1,120}$/.test(x);
const time=(x:unknown):x is number=>typeof x==="number"&&Number.isFinite(x)&&x>=0&&x<=8.64e15;
const object=(x:unknown):Record<string,unknown>=>x&&typeof x==="object"?x as Record<string,unknown>:{};
const retractions=(x:unknown):string[]=>Array.isArray(x)?[...new Set(x.slice(0,10000).filter(identity))]:[];
const state=(x:unknown):x is ProcessStatus=>typeof x==="string"&&Object.hasOwn(processStatusText,x);
/** Untimed writer rows use the recorded attempt boundary, never a fabricated event time. */
export const compareProcessSummaries=(a:ProcessSummary,b:ProcessSummary,fallback=0)=>(a.timestamp??a.attemptStartedAt??fallback)-(b.timestamp??b.attemptStartedAt??fallback)||(a.sequence??0)-(b.sequence??0)||a.id.localeCompare(b.id);
const optional=(r:Record<string,unknown>)=>({...(reasons.has(String(r.reason))?{reason:String(r.reason)}:{}),...(nextSteps.has(String(r.nextStep))?{nextStep:String(r.nextStep)}:{})});

/** Revision 6 uses returned content and tool receipts only. Earlier summaries
 * can derive from private reasoning, including copies persisted before upgrade.
 * Apply the source boundary again on every server response and offline import. */
export function readConversationProcesses(input:unknown):ConversationProcess[]{
 if(!Array.isArray(input))return [];
 const summaries=(input:unknown):ProcessSummary[]=>!Array.isArray(input)?[]:[...new Map(input.slice(0,10000).flatMap(raw=>{const r=object(raw);const model=r.summaryOrigin==="model"&&Number.isSafeInteger(r.summaryRevision)&&Number(r.summaryRevision)>=6&&safeModelSummary(r.text);if(!identity(r.id)||!(r.timestamp===undefined||time(r.timestamp))||!(r.status==="recorded"||state(r.status))||!(texts.has(String(r.text))||model))return [];return [[r.id,{id:r.id,...(time(r.timestamp)?{timestamp:r.timestamp}:{}),...(time(r.attemptStartedAt)?{attemptStartedAt:r.attemptStartedAt}:{}),...(typeof r.sequence==="number"&&Number.isSafeInteger(r.sequence)&&r.sequence>=0?{sequence:r.sequence}:{}),text:String(r.text),...(r.pendingImageText===true?{pendingImageText:true}:{}),...(model?{summaryOrigin:"model" as const,summaryRevision:Number(r.summaryRevision)}:{}),status:r.status,...(time(r.finishedAt)&&(r.timestamp===undefined||r.finishedAt>=r.timestamp)?{finishedAt:r.finishedAt}:{}),...optional(r)} as ProcessSummary] as const];})).values()].sort(compareProcessSummaries);
 return [...new Map(input.slice(0,1000).flatMap(raw=>{const r=object(raw);if(!identity(r.id)||!time(r.startedAt)||!state(r.status))return [];return [[r.id,{id:r.id,startedAt:r.startedAt,status:r.status,thinking:summaries(r.thinking),tools:summaries(r.tools),...(retractions(r.retractedSummaryIds).length?{retractedSummaryIds:retractions(r.retractedSummaryIds)}:{}),...(identity(r.userMessageId)?{userMessageId:r.userMessageId}:{}),...(time(r.finishedAt)&&r.finishedAt>=r.startedAt?{finishedAt:r.finishedAt}:{}),...optional(r),...(["已沿用原会话恢复。","已创建新尝试；历史失败保留。"].includes(String(r.recovery))?{recovery:String(r.recovery)}:{})} as ConversationProcess] as const];})).values()].map(p=>({...p,thinking:p.thinking.filter(r=>!p.retractedSummaryIds?.includes(r.id)),tools:p.tools.filter(r=>!p.retractedSummaryIds?.includes(r.id))})).sort((a,b)=>a.startedAt-b.startedAt||a.id.localeCompare(b.id));
}

/** Polling may repeat or omit already persisted summaries. Terminal states do
 * not regress; a recovery belongs to a distinct turn identity. */
export function mergeConversationProcesses(previous:ConversationProcess[]=[],incoming:ConversationProcess[]=[]):ConversationProcess[]{
 const merged=new Map(previous.map(p=>[p.id,p]));
 const terminal=(status:string)=>["completed","failed","cancelled"].includes(status);
 for(const next of incoming){
  const prior=merged.get(next.id);
  if(!prior){merged.set(next.id,next);continue;}
  const retractedSummaryIds=[...new Set([...(prior.retractedSummaryIds??[]),...(next.retractedSummaryIds??[])])];
  const summaries=(old:ProcessSummary[],fresh:ProcessSummary[])=>{
   const rows=new Map(old.map(r=>[r.id,r]));
   for(const r of fresh){
    const p=rows.get(r.id);
    const result=p&&terminal(p.status)?{...p}: {...r};
    const caption=p&&((p.summaryRevision??0)>(r.summaryRevision??0)||(terminal(p.status)&&(p.summaryRevision??0)>=(r.summaryRevision??0)))?p:r;
    result.attemptStartedAt=r.attemptStartedAt??p?.attemptStartedAt;
    result.text=caption.text;
    result.pendingImageText=r.pendingImageText??p?.pendingImageText;
    result.summaryOrigin=caption.summaryOrigin;
    result.summaryRevision=caption.summaryRevision;
    rows.set(r.id,result);
   }
   return [...rows.values()].filter(r=>!retractedSummaryIds.includes(r.id)).sort(compareProcessSummaries);
  };
  merged.set(next.id,{...prior,...next,...(retractedSummaryIds.length?{retractedSummaryIds}:{}),status:terminal(prior.status)?prior.status:next.status,thinking:summaries(prior.thinking,next.thinking),tools:summaries(prior.tools,next.tools)});
 }
 return [...merged.values()].sort((a,b)=>a.startedAt-b.startedAt||a.id.localeCompare(b.id));
}
