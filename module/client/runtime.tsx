import ExecutionFeedback, {type FeedbackObservation} from "./ExecutionFeedback";
import {generalExecutionSlots} from "@frontmind/module-ui/lib/general-execution-display";
import {GeneralExecutionActivity} from "@frontmind/module-ui/components/GeneralExecutionActivity";
import {useChatReadingPosition} from "@frontmind/module-ui/hooks/useChatReadingPosition";
import {mergeConversationProcesses} from "../contracts/conversation-process";
import ConversationExecutionProcess from "./ConversationExecutionProcess";
import BusinessChatInput from "@frontmind/module-ui/components/BusinessChatInput";
import type { BusinessComposerRuntime } from "@frontmind/module-ui/components/business-composer-runtime";
import type { ContentProductionInput } from "../contracts/content-production";
import BusinessMessage, {type BusinessMessageRuntime} from "@frontmind/module-ui/components/BusinessMessage";
import FilePreview from "@frontmind/module-ui/components/FilePreview";
import {AgentWorkbenchShell} from "@frontmind/module-ui/components/AgentWorkbenchShell";
import {WorkbenchTaskToolbar as SharedWorkbenchTaskToolbar} from "@frontmind/module-ui/dashboard/WorkbenchTaskToolbar";
import {BusinessWorkspaceInspector} from "@frontmind/module-ui/dashboard/BusinessWorkspaceInspector";
import {createContext,useCallback,useContext,useEffect,useMemo,useRef,useState,type ReactNode} from "react";
import {ContentWorkspaceHostProvider,type ContentConversation,type ContentConversationApi,type ContentHomeProps,type ContentSendOptions,type ContentWorkspaceHost,type TaskResponse} from "./host";
import ContentProductionWorkspace from "./ContentProductionWorkspace";
export type ModuleContext={module:string;workspace:{id:string;ownerUserId:number};marketEdition:string;capabilities:string[]};
import "./runtime.css";
export interface ContentBusinessClient {
 list():Promise<ContentConversation[]>;save(value:ContentConversation):Promise<ContentConversation>;remove(id:string):Promise<void>;
 upload(file:File):Promise<{fileId:string;filename:string}>;
 dispatch(input:Record<string,unknown>,taskId?:string):Promise<TaskResponse>;
 task(id:string,signal?:AbortSignal):Promise<TaskResponse>;stop(id:string):Promise<void>;
}
async function json<T>(url:string,init:RequestInit={}):Promise<T>{
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),20000);
 const abort=()=>controller.abort();init.signal?.addEventListener("abort",abort,{once:true});if(init.signal?.aborted)controller.abort();
 try{const response=await fetch(url,{credentials:"same-origin",...init,signal:controller.signal});const value=await response.json();if(!response.ok)throw new Error(value.error?.message??value.error??value.message??`HTTP ${response.status}`);return value;}
 catch(error){if(controller.signal.aborted)throw new Error("请求超时或已取消，请检查连接后重试；提交结果可能已被服务器接收。");throw error;}
 finally{clearTimeout(timer);init.signal?.removeEventListener("abort",abort);}
}
export const liveContentClient:ContentBusinessClient={
 list:()=>json("/api/content/conversations"),
 save:value=>json(`/api/content/conversations/${encodeURIComponent(value.id)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)}),
 remove:async id=>{await json(`/api/content/conversations/${encodeURIComponent(id)}`,{method:"DELETE"});},
 upload:async file=>{const value=await json<{localAssetId:string;filename:string}>("/api/frontmind/v2/assets",{method:"POST",headers:{"Content-Type":"application/octet-stream","X-FrontMind-Mime":file.type||"application/octet-stream","X-FrontMind-Filename":encodeURIComponent(file.name),"X-FrontMind-Size":String(file.size)},body:file});return {fileId:value.localAssetId,filename:value.filename};},
 dispatch:(value,taskId)=>json(`/api/frontmind/v2/tasks${taskId?`/${encodeURIComponent(taskId)}/messages`:""}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)}),
 task:(id,signal)=>json(`/api/frontmind/v2/tasks/${encodeURIComponent(id)}`,{signal}),
 stop:async id=>{await json(`/api/frontmind/v2/tasks/${encodeURIComponent(id)}/stop`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});},
};
type Runtime=ContentConversationApi&{workspaceId:string;sendMessage(prompt:string,files?:File[],options?:ContentSendOptions):Promise<boolean>;stop():Promise<void>;notice:string;submittingIds:ReadonlySet<string>;stoppingId:string|null;observation?:FeedbackObservation;refresh():Promise<void>};
const RuntimeContext=createContext<Runtime|null>(null);
function useRuntime(){const value=useContext(RuntimeContext);if(!value)throw new Error("Content runtime missing");return value;}
function RuntimeProvider({client,children,workspaceId}:{client:ContentBusinessClient;children:ReactNode;workspaceId:string}) {
 const [conversations,setConversations]=useState<ContentConversation[]>([]),[activeId,setActiveId]=useState<string|null>(null),[hydrated,setHydrated]=useState(false),[notice,setNotice]=useState("");
 const [submittingIds,setSubmittingIds]=useState<Set<string>>(new Set()),[stoppingId,setStoppingId]=useState<string|null>(null),[observation,setObservation]=useState<FeedbackObservation>();
 const [initialLoadAttempt,setInitialLoadAttempt]=useState(0),[initialLoadPending,setInitialLoadPending]=useState(true),[initialLoadError,setInitialLoadError]=useState("");
 const initialLoadPendingRef=useRef(true);
 const items=useRef(conversations);items.current=conversations;const current=useRef(activeId);current.current=activeId;const locks=useRef(new Set<string>());const listVersion=useRef(0);
 const storageKey=`frontmind-content-active:${workspaceId}`;
 // A list read cannot supersede a newer read or a local write. Do not compare
 // updatedAt: tool events can change while the business-stage timestamp stays equal.
 const update=useCallback((item:ContentConversation)=>{listVersion.current++;setConversations(previous=>{const next=[item,...previous.filter(entry=>entry.id!==item.id)];items.current=next;return next;});},[]);
 const refresh=useCallback(async()=>{const version=++listVersion.current;const rows=await client.list();if(version!==listVersion.current||locks.current.size>0)return;setConversations(previous=>{const remoteIds=new Set(rows.map(row=>row.id));const next=[...rows.map(row=>({...row,processes:mergeConversationProcesses(previous.find(p=>p.id===row.id)?.processes,row.processes)})),...previous.filter(row=>!remoteIds.has(row.id)&&row.messages.length===0)];items.current=next;return next;});},[client]);
 useEffect(()=>{
  let disposed=false;
  const version=++listVersion.current;
  initialLoadPendingRef.current=true;
  setInitialLoadPending(true);
  // 初始化和重试都只读取任务列表；失败期间保留上次选择的任务编号。
  void (async()=>{
   try{
    const rows=await client.list();
    if(disposed)return;
    // 重试沿用新版本的读取序号保护，避免覆盖较新的读取或本地操作。
    if(version===listVersion.current&&locks.current.size===0){
     setConversations(rows);items.current=rows;
     const saved=localStorage.getItem(storageKey);
     setActiveId(rows.some(row=>row.id===saved)?saved:null);
    }
    setInitialLoadError("");setHydrated(true);
   }catch(error){
    if(!disposed)setInitialLoadError(error instanceof Error&&error.message?error.message:"读取任务失败，请重试。");
   }finally{
    if(!disposed){initialLoadPendingRef.current=false;setInitialLoadPending(false);}
   }
  })();
  return()=>{disposed=true;listVersion.current++;};
 },[client,storageKey,initialLoadAttempt]);
 function retryInitialLoad(){
  if(initialLoadPendingRef.current)return;
  initialLoadPendingRef.current=true;
  setInitialLoadPending(true);
  setInitialLoadAttempt(attempt=>attempt+1);
 }
 const activeConversation=conversations.find(row=>row.id===activeId)??null;
 useEffect(()=>{if(!hydrated)return;if(activeId)localStorage.setItem(storageKey,activeId);else localStorage.removeItem(storageKey);},[activeId,storageKey,hydrated]);
 useEffect(()=>{if(!activeConversation?.taskId)return;let cancelled=false;let timer:ReturnType<typeof setTimeout>;const controller=new AbortController();const id=activeConversation.taskId;
 async function poll(){try{await client.task(id!,controller.signal);if(!cancelled){await refresh();if(!cancelled)setObservation({taskId:id!,checkedAt:Date.now()});}}catch{if(!cancelled)setObservation({taskId:id!,checkedAt:Date.now(),error:true});}finally{if(!cancelled)timer=setTimeout(poll,3000);}}
 void poll();return()=>{cancelled=true;controller.abort();clearTimeout(timer);};},[activeConversation?.taskId,client,refresh]);
 const sendMessage=useCallback(async(prompt:string,files:File[]=[],options:ContentSendOptions={})=>{
  const id=current.current;const conversation=items.current.find(row=>row.id===id);if(!conversation)throw new Error("请先选择内容任务");if(locks.current.has(conversation.id))return false;
  locks.current.add(conversation.id);listVersion.current++;setNotice("");setSubmittingIds(previous=>new Set([...previous,conversation.id]));
  try{
   // Keep the exact persisted envelope for an unacknowledged request. Uploads and
   // task creation are never repeated with a new identity after a lost response.
   let message=conversation.messages.findLast(item=>item.role==="user"&&item.generalChatDispatch);
   if(message && message.content!==prompt)throw new Error("上一条提交尚未确认，请先重试该消息。");
   if(!message){
    const uploaded=[];for(const file of files)uploaded.push(await client.upload(file));
    const clientRequestId=crypto.randomUUID();const localAssetIds=[...new Set(uploaded.map(item=>item.fileId))].sort();
    const dispatch={schemaVersion:1,kind:"pending_user",clientRequestId,providerPrompt:prompt,localAssetIds,localTaskId:conversation.taskId??null,modelProfile:conversation.taskId?null:"frontmind-base",...(conversation.taskId?options.contentProductionAction?{contentProductionAction:options.contentProductionAction}:{}:{purpose:"content_production",contentProduction:options.contentProduction})};
    message={id:clientRequestId,role:"user",content:prompt,timestamp:Date.now(),attachments:uploaded.map(item=>({id:item.fileId,type:"file",name:item.filename,fileId:item.fileId})),generalChatDispatch:dispatch};
    const pending={...conversation,messages:[...conversation.messages,message],updatedAt:Date.now()};update(pending);await client.save(pending);
   }
   const dispatch=message.generalChatDispatch!;const existingTask=typeof dispatch.localTaskId==="string"?dispatch.localTaskId:undefined;
   const result=await client.dispatch({conversationId:conversation.id,clientRequestId:dispatch.clientRequestId,prompt:dispatch.providerPrompt,localAssetIds:dispatch.localAssetIds,...(!existingTask?{modelProfile:dispatch.modelProfile,purpose:"content_production",contentProduction:dispatch.contentProduction}:dispatch.contentProductionAction?{contentProductionAction:dispatch.contentProductionAction}:{})},existingTask);
   if(result.purpose&&result.purpose!=="content_production")throw new Error("返回的任务不属于内容制作");
   const latest=items.current.find(row=>row.id===conversation.id)??conversation;
   const accepted={...latest,taskId:result.id,previousResponseId:result.id,executionKind:"general_chat_v2" as const,status:result.status,updatedAt:Date.now(),messages:latest.messages.map(item=>item.id===message!.id?(({generalChatDispatch:_,...rest})=>rest)(item):item)};
   update(await client.save(accepted));return true;
  }catch(error){setNotice(error instanceof Error?error.message:String(error));throw error;}finally{listVersion.current++;locks.current.delete(conversation.id);setSubmittingIds(previous=>{const next=new Set(previous);next.delete(conversation.id);return next;});}
 },[client,update]);
 const value:Runtime={workspaceId,submittingIds,stoppingId,observation,state:{conversations},activeConversation,hydrated,notice,refresh,sendMessage,createConversation({title}){const id=crypto.randomUUID();update({id,title,purpose:"content_production",status:"idle",messages:[],createdAt:Date.now(),updatedAt:Date.now()});setActiveId(id);return id;},setActive:setActiveId,deleteConversation(id){void client.remove(id).then(()=>{listVersion.current++;setConversations(previous=>previous.filter(row=>row.id!==id));if(current.current===id)setActiveId(null);}).catch(error=>setNotice(error.message));},async stop(){const id=items.current.find(row=>row.id===current.current)?.taskId;if(!id||stoppingId)return;setStoppingId(id);setNotice("");try{await client.stop(id);const result=await client.task(id);if(!["cancelled","completed","error","failed"].includes(result.status))throw new Error("STOP_NOT_CONFIRMED");await refresh();}catch{setNotice("停止请求未确认，请重试停止；当前不能确认执行已停止。");throw new Error("STOP_NOT_CONFIRMED");}finally{setStoppingId(null);}}};
 return <RuntimeContext.Provider value={value}>{!hydrated&&initialLoadError&&<div className="cp-notice" role="alert"><p>任务列表加载失败：{initialLoadError}</p><button type="button" className="cp-live-retry" disabled={initialLoadPending} onClick={retryInitialLoad}>{initialLoadPending?"正在重试…":"重试加载任务"}</button></div>}{notice&&<p className="cp-notice" role="alert">{notice}</p>}{children}</RuntimeContext.Provider>;
}
// Keep the message wrapper's component identity stable across polling updates.
// A fresh wrapper remounts the shared message and replays its entrance animation.
const ContentMessageActions = ({children}:{children:ReactNode}) => <>{children}</>;
const contentMessageRuntime: BusinessMessageRuntime = {MessageActions:ContentMessageActions};
function ContentDialogue({knowledgeEditingBlocked,conversationFooter}:ContentHomeProps) {
 const runtime=useRuntime();
 const busy=Boolean(knowledgeEditingBlocked)||["running","pending"].includes(runtime.activeConversation?.status??"");
 const viewport=useRef<HTMLDivElement>(null);
 const {showLatest,returnToLatest}=useChatReadingPosition(viewport,`${runtime.workspaceId}:${runtime.activeConversation?.id??"new"}`,`${runtime.activeConversation?.messages.map(m=>`${m.id}:${m.content.length}`).join("|")}:${runtime.activeConversation?.status}:${runtime.activeConversation?.processes?.map(p=>`${p.id}:${p.status}:${[...p.thinking,...p.tools].map(r=>`${r.id}:${r.status}:${r.summaryRevision??0}:${r.text.length}`).join(",")}`).join("|")}`);
 const processes=runtime.activeConversation?.processes??[];
 const slots=generalExecutionSlots(runtime.activeConversation?.messages??[],processes.length?undefined:runtime.activeConversation?.execution,busy);
 return <div className="cp-live-dialogue"><div ref={viewport} className="cp-live-messages custom-scrollbar" data-testid="chat-messages-viewport"><div className="workbench-reading-column space-y-7">{runtime.activeConversation?.messages.map(message=><article key={message.id} data-role={message.role} data-reading-anchor={message.id}>
   <GeneralExecutionActivity items={slots.before.get(message.id)} />
   <BusinessMessage runtime={contentMessageRuntime} message={message} isRunning={busy} isFinalReply={!busy} />
   <GeneralExecutionActivity items={slots.after.get(message.id)} placement="after" />
   {processes.filter(p=>p.userMessageId===message.id).map(process=><ConversationExecutionProcess key={process.id} process={process} onRecover={process.id===processes.at(-1)?.id&&["error","cancelled"].includes(runtime.activeConversation?.status??"")?()=>void runtime.sendMessage("重试当前执行").catch(()=>{}):undefined}/>)}
   {message.generalChatDispatch&&<button className="cp-live-retry" onClick={()=>void runtime.sendMessage(message.content).catch(()=>{})}>重试本次提交</button>}
  </article>)}</div></div>{showLatest&&<button className="workbench-return-latest" onClick={returnToLatest}>回到最新</button>}{conversationFooter}
  <ExecutionFeedback conversation={runtime.activeConversation??undefined} submitting={runtime.submittingIds.has(runtime.activeConversation?.id??"")} stopping={runtime.stoppingId===runtime.activeConversation?.taskId} observation={runtime.observation}/>
  <BusinessChatInput runtime={contentComposerRuntime} purpose="content_production" operatorWorkspace knowledgeEditingBlocked={Boolean(knowledgeEditingBlocked)} />
  {["running","pending"].includes(runtime.activeConversation?.status??"")&&<button className="cp-live-stop" type="button" disabled={runtime.stoppingId===runtime.activeConversation?.taskId} onClick={()=>void runtime.stop().catch(()=>{})}>{runtime.stoppingId===runtime.activeConversation?.taskId?"正在请求停止…":"停止当前执行"}</button>}
 </div>;
}
const pendingDrafts = new Set<() => boolean>();
const useDraftGuard: ContentWorkspaceHost["useWorkspaceDraftGuard"] = (input) => {
 const current = useRef(input); current.current = input;
 useEffect(() => {
  const dirty = () => current.current.dirty;
  pendingDrafts.add(dirty);
  const handler = (event: BeforeUnloadEvent) => { if (dirty()) { event.preventDefault(); event.returnValue = ""; } };
  window.addEventListener("beforeunload", handler);
  return () => { pendingDrafts.delete(dirty); window.removeEventListener("beforeunload", handler); };
 }, []);
};
function requestDraftNavigation(operation: () => void) {
 if (![...pendingDrafts].some(dirty => dirty()) || window.confirm("当前修改尚未保存，确定离开吗？")) operation();
}
const WorkbenchTaskToolbar: ContentWorkspaceHost["WorkbenchTaskToolbar"] = props => <SharedWorkbenchTaskToolbar {...props} requestNavigation={requestDraftNavigation} />;
// The same Dashboard composer owns draft, IME, attachment and drag/drop UI.
// The content adapter supplies only this module's persisted dispatch behavior.
const contentComposerRuntime: BusinessComposerRuntime<ContentProductionInput, never, ContentConversation, never> = {
 useConversation() {
  const state=useRuntime();
  return {activeConversation:state.activeConversation,workbenchScopeKey:`content:${state.workspaceId}`,
   commitKnowledgeBaseObservation(){throw new Error("内容任务不能写入知识库状态");},
   wakeKnowledgeBaseConversation(){throw new Error("内容任务不能调度知识库");},
   rollbackPendingKnowledgeBaseTurn(){throw new Error("内容任务不能修改知识库提交");}};
 },
 currentKnowledgeBaseReplySnapshot:()=>null,
 useSendMessage() {
  const runtime=useRuntime();
  return {sendMessage:(text,files,options)=>runtime.sendMessage(text,files,{purpose:"content_production",contentProduction:options?.contentProduction}),
   uploadProgress:null,knowledgeBaseAttachmentAttempt:null,
   stopKnowledgeBaseAttachmentAttempt(){},continueKnowledgeBaseAttachmentAttempt(){},discardKnowledgeBaseAttachmentAttempt(){}};
 },
 useChatSubmission:()=>null,
 useWorkspaceDraftGuard:useDraftGuard,
 captureWorkspaceRestOperation:()=>({assertActive(){},fetch:(input,init)=>fetch(input,{...init,credentials:"same-origin"})}),
 consumePendingFrontMindBuildDraft:()=>"",
 GeneralAgentRuntimeBadge:()=>null,
 KnowledgeBaseManagedUploadRecovery:()=>null,
 generalSuggestions:[],
 formatKnowledgeBaseUploadBytes:bytes=>`${(bytes/1024/1024).toFixed(1)} MB`,
 chatAttachmentSizeError:file=>file.size>100*1024*1024?`文件“${file.name||"未命名文件"}”不能超过 100 MB`:null,
 knowledgeLogoNoticeCode:"unused-content-knowledge-logo",
};
function InstalledWorkspace({client}:{client:ContentBusinessClient}){const host=useMemo<ContentWorkspaceHost>(()=>({connections:{publishedKnowledge:false},ConversationPurposeProvider:ContentMessageActions,useConversation:useRuntime,useSendMessage:()=>({sendMessage:useRuntime().sendMessage}),retrieveTask:(id,options)=>client.task(id,options?.signal),captureWorkspaceRestOperation:(signal=new AbortController().signal)=>({signal,assertActive(){signal.throwIfAborted();},fetch:(url,init)=>fetch(url,{...init,signal})}),useWorkspaceDraftGuard:useDraftGuard,requestWorkspaceNavigation:requestDraftNavigation,Home:ContentDialogue,FilePreview,WorkbenchTaskToolbar,AgentWorkbenchShell,BusinessWorkspaceInspector}),[client]);return <ContentWorkspaceHostProvider value={host}><ContentProductionWorkspace workbench/></ContentWorkspaceHostProvider>}
export function ModuleWorkspace({context,client=liveContentClient}:{context:ModuleContext;client?:ContentBusinessClient}) {return <RuntimeProvider client={client} workspaceId={context.workspace.id}><InstalledWorkspace client={client}/></RuntimeProvider>}
