import {mergeConversationProcesses,readConversationProcesses,type ConversationProcess,type ProcessStatus} from "../contracts/conversation-process";
import type {ContentMessage} from "../client/host";
export type LocalProcessTurn={id:string;userMessageId:string;startedAt:number;finishedAt?:number;baseline:string[];status?:ProcessStatus;summaryBaseline?:string[];recoverAttemptId?:string};

/** Dispatch boundaries are persisted outside the Job. Historical attempts that
 * predate the UI have their own explicit anchors; never assign them to a new turn. */
export function bindConversationProcesses(input:unknown,messages:ContentMessage[],turns:LocalProcessTurn[],status:ProcessStatus,archived:ConversationProcess[]=[]){
 const attempts=readConversationProcesses(input).map(attempt=>({...attempt,
  thinking:attempt.thinking.map(row=>({...row,attemptStartedAt:attempt.startedAt})),
  tools:attempt.tools.map(row=>({...row,attemptStartedAt:attempt.startedAt})),
 })),used=new Set<string>(),processes:ConversationProcess[]=[];
 // Native evidence can retract one unsupported caption without erasing its turn.
 const retracted=new Set(attempts.flatMap(a=>a.retractedSummaryIds??[]));
 archived=readConversationProcesses(archived.map(p=>({...p,retractedSummaryIds:[...new Set([...(p.retractedSummaryIds??[]),...[...p.thinking,...p.tools].filter(r=>retracted.has(r.id)).map(r=>r.id)])]})));
 // Pre-upgrade UI users have durable IDs/timestamps but no dispatch ledger.
 // Associate only their chronological interval. Earlier native work stays
 // explicitly historical instead of being pulled into the latest UI message.
 const nativeTurns=messages.filter(m=>m.role==="user"&&!m.id.startsWith("history-")&&!turns.some(t=>t.userMessageId===m.id)).map(m=>({id:"turn-"+m.id,userMessageId:m.id,startedAt:m.timestamp,baseline:attempts.filter(a=>a.startedAt<m.timestamp).map(a=>a.id)}));
 turns=[...turns,...nativeTurns].sort((a,b)=>a.startedAt-b.startedAt||a.id.localeCompare(b.id));
 for(let index=turns.length-1;index>=0;index--){
  const turn=turns[index]!,next=turns[index+1];
  const frozen=archived.find(p=>p.id===turn.id);
  const owned=attempts.filter(a=>!used.has(a.id)&&(!turn.baseline.includes(a.id)||a.id===turn.recoverAttemptId)&&(!next||a.startedAt<next.startedAt)).map(a=>turn.baseline.includes(a.id)?{...a,thinking:a.thinking.filter(r=>!turn.summaryBaseline?.includes(r.id)),tools:a.tools.filter(r=>!turn.summaryBaseline?.includes(r.id))}:a);
  owned.forEach(a=>used.add(a.id));
  if(next&&frozen){
   // Late summary results may update the old turn, but never its business state
   // or ownership. The next turn cannot take those rows from its predecessor.
   const fresh={...frozen,thinking:owned.flatMap(a=>a.thinking),tools:owned.flatMap(a=>a.tools),retractedSummaryIds:[...(frozen.retractedSummaryIds??[]),...owned.flatMap(a=>a.retractedSummaryIds??[])]};
   processes.push(mergeConversationProcesses([frozen],[fresh])[0]!);continue;
  }
  const current=index===turns.length-1;
  const state=current?status:turn.status??"unknown";
  const last=owned.findLast(a=>a.reason);
  processes.push({id:turn.id,userMessageId:turn.userMessageId,startedAt:turn.startedAt,status:state,
   ...(turn.finishedAt?{finishedAt:turn.finishedAt}:{}),
   retractedSummaryIds:owned.flatMap(a=>a.retractedSummaryIds??[]),
   thinking:owned.flatMap(a=>a.thinking),
   tools:owned.flatMap(a=>a.tools),...(state==="failed"?{reason:last?.reason??"本轮执行失败。",nextStep:last?.nextStep??"检查后台诊断后显式恢复。"}:{}),
   ...(state==="cancelled"?{reason:"本次执行已取消。",nextStep:"已有产出已保留，可显式恢复当前执行。"}:{}),
   ...(owned.findLast(a=>a.recovery)?.recovery?{recovery:owned.findLast(a=>a.recovery)!.recovery}:{}),
  });
 }
 for(const frozen of archived.filter(p=>!turns.some(t=>t.id===p.id))){
  const anchor=frozen.userMessageId;
  if(anchor&&!messages.some(m=>m.id===anchor))messages.push({id:anchor,role:"user",timestamp:frozen.startedAt,content:"历史执行阶段（从原生记录恢复）"});
  processes.push(frozen);
 }
 for(const attempt of attempts.filter(a=>!used.has(a.id)&&!archived.some(p=>p.id===a.id))){
  const anchor="history-"+attempt.id;
  if(!messages.some(m=>m.id===anchor))messages.push({id:anchor,role:"user",timestamp:attempt.startedAt,content:"历史执行阶段（从原生记录恢复）"});
  processes.push({...attempt,userMessageId:anchor});
 }
 return readConversationProcesses(processes);
}
