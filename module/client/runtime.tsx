import {useChatReadingPosition} from "@frontmind/module-ui/hooks/useChatReadingPosition";
import {generalExecutionSlots} from "@frontmind/module-ui/lib/general-execution-display";
import {GeneralExecutionActivity} from "@frontmind/module-ui/components/GeneralExecutionActivity";
import BusinessChatInput from "@frontmind/module-ui/components/BusinessChatInput";
import type { BusinessComposerRuntime } from "@frontmind/module-ui/components/business-composer-runtime";
import type { ContentProductionInput } from "../contracts/content-production";
import BusinessMessage from "@frontmind/module-ui/components/BusinessMessage";
import FilePreview from "@frontmind/module-ui/components/FilePreview";
import {AgentWorkbenchShell} from "@frontmind/module-ui/components/AgentWorkbenchShell";
import {WorkbenchTaskToolbar as SharedWorkbenchTaskToolbar} from "@frontmind/module-ui/dashboard/WorkbenchTaskToolbar";
import {BusinessWorkspaceInspector} from "@frontmind/module-ui/dashboard/BusinessWorkspaceInspector";
import {createContext,useCallback,useContext,useEffect,useRef,useState,type ReactNode} from "react";
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
async function json<T>(url:string,init:RequestInit={}):Promise<T>{const response=await fetch(url,{credentials:"same-origin",...init});const value=await response.json();if(!response.ok)throw new Error(value.error?.message??value.error??value.message??`HTTP ${response.status}`);return value;}
export const liveContentClient:ContentBusinessClient={
 list:()=>json("/api/content/conversations"),
 save:value=>json(`/api/content/conversations/${encodeURIComponent(value.id)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)}),
 remove:async id=>{await json(`/api/content/conversations/${encodeURIComponent(id)}`,{method:"DELETE"});},
 upload:async file=>{const value=await json<{localAssetId:string;filename:string}>("/api/frontmind/v2/assets",{method:"POST",headers:{"Content-Type":"application/octet-stream","X-FrontMind-Mime":file.type||"application/octet-stream","X-FrontMind-Filename":encodeURIComponent(file.name),"X-FrontMind-Size":String(file.size)},body:file});return {fileId:value.localAssetId,filename:value.filename};},
 dispatch:(value,taskId)=>json(`/api/frontmind/v2/tasks${taskId?`/${encodeURIComponent(taskId)}/messages`:""}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)}),
 task:(id,signal)=>json(`/api/frontmind/v2/tasks/${encodeURIComponent(id)}`,{signal}),
 stop:async id=>{await json(`/api/frontmind/v2/tasks/${encodeURIComponent(id)}/stop`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});},
};
type Runtime=ContentConversationApi&{workspaceId:string;sendMessage(prompt:string,files?:File[],options?:ContentSendOptions):Promise<boolean>;stop():Promise<void>;notice:string;refresh():Promise<void>};
const RuntimeContext=createContext<Runtime|null>(null);
function useRuntime(){const value=useContext(RuntimeContext);if(!value)throw new Error("Content runtime missing");return value;}
function RuntimeProvider({client,children,workspaceId}:{client:ContentBusinessClient;children:ReactNode;workspaceId:string}) {
 const [conversations,setConversations]=useState<ContentConversation[]>([]),[activeId,setActiveId]=useState<string|null>(null),[hydrated,setHydrated]=useState(false),[notice,setNotice]=useState("");
 const items=useRef(conversations);items.current=conversations;const current=useRef(activeId);current.current=activeId;const locks=useRef(new Set<string>());
 const storageKey=`frontmind-content-active:${workspaceId}`;
 const update=useCallback((item:ContentConversation)=>{setConversations(previous=>{const next=[item,...previous.filter(entry=>entry.id!==item.id)];items.current=next;return next;});},[]);
 const refresh=useCallback(async()=>{const rows=await client.list();setConversations(previous=>{const remoteIds=new Set(rows.map(row=>row.id));const next=[...rows,...previous.filter(row=>!remoteIds.has(row.id)&&row.messages.length===0)];items.current=next;return next;});},[client]);
 useEffect(()=>{let disposed=false;void client.list().then(rows=>{if(disposed)return;setConversations(rows);items.current=rows;const saved=localStorage.getItem(storageKey);setActiveId(rows.some(row=>row.id===saved)?saved:null);setHydrated(true);}).catch(error=>{if(!disposed)setNotice(error.message);});return()=>{disposed=true};},[client,storageKey]);
 const activeConversation=conversations.find(row=>row.id===activeId)??null;
 useEffect(()=>{if(!hydrated)return;if(activeId)localStorage.setItem(storageKey,activeId);else localStorage.removeItem(storageKey);},[activeId,storageKey,hydrated]);
 useEffect(()=>{if(!activeConversation?.taskId)return;let cancelled=false;let timer:ReturnType<typeof setTimeout>;const id=activeConversation.taskId;async function poll(){try{await client.task(id!);if(!cancelled)await refresh();}catch(error){if(!cancelled)setNotice(error instanceof Error?error.message:String(error));}finally{if(!cancelled)timer=setTimeout(poll,3000);}}void poll();return()=>{cancelled=true;clearTimeout(timer);};},[activeConversation?.taskId,client,refresh]);
 const sendMessage=useCallback(async(prompt:string,files:File[]=[],options:ContentSendOptions={})=>{
  const id=current.current;const conversation=items.current.find(row=>row.id===id);if(!conversation)throw new Error("请先选择内容任务");if(locks.current.has(conversation.id))return false;
  locks.current.add(conversation.id);setNotice("");
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
   const accepted={...latest,taskId:result.id,previousResponseId:result.id,executionKind:"general_chat_v2" as const,status:result.status==="cancelled"?"completed":result.status,updatedAt:Date.now(),messages:latest.messages.map(item=>item.id===message!.id?(({generalChatDispatch:_,...rest})=>rest)(item):item)};
   update(await client.save(accepted));return true;
  }catch(error){setNotice(error instanceof Error?error.message:String(error));throw error;}finally{locks.current.delete(conversation.id);}
 },[client,update]);
 const value:Runtime={workspaceId,state:{conversations},activeConversation,hydrated,notice,refresh,sendMessage,createConversation({title}){const id=crypto.randomUUID();update({id,title,purpose:"content_production",status:"idle",messages:[],createdAt:Date.now(),updatedAt:Date.now()});setActiveId(id);return id;},setActive:setActiveId,deleteConversation(id){void client.remove(id).then(()=>{setConversations(previous=>previous.filter(row=>row.id!==id));if(current.current===id)setActiveId(null);}).catch(error=>setNotice(error.message));},async stop(){const id=items.current.find(row=>row.id===current.current)?.taskId;if(id){await client.stop(id);await refresh();}}};
 return <RuntimeContext.Provider value={value}>{notice&&<p className="cp-notice" role="alert">{notice}</p>}{children}</RuntimeContext.Provider>;
}
function ContentDialogue({knowledgeEditingBlocked,conversationFooter}:ContentHomeProps) {
 const runtime=useRuntime();
 const busy=Boolean(knowledgeEditingBlocked)||["running","pending"].includes(runtime.activeConversation?.status??"");
 const viewport=useRef<HTMLDivElement>(null);
 const {showLatest,returnToLatest}=useChatReadingPosition(viewport,`${runtime.workspaceId}:${runtime.activeConversation?.id??"new"}`,`${runtime.activeConversation?.messages.map(m=>`${m.id}:${m.content.length}`).join("|")}:${runtime.activeConversation?.status}`);
 const slots=generalExecutionSlots(runtime.activeConversation?.messages??[],runtime.activeConversation?.execution,busy);
 return <div className="cp-live-dialogue"><div ref={viewport} className="cp-live-messages custom-scrollbar" data-testid="chat-messages-viewport"><div className="workbench-reading-column space-y-7">{runtime.activeConversation?.messages.map(message=><article key={message.id} data-role={message.role} data-reading-anchor={message.id}>
   <GeneralExecutionActivity items={slots.before.get(message.id)} />
   <BusinessMessage message={message} isRunning={busy} isFinalReply={!busy} />
   <GeneralExecutionActivity items={slots.after.get(message.id)} placement="after" />
   {message.generalChatDispatch&&<button className="cp-live-retry" onClick={()=>void runtime.sendMessage(message.content).catch(()=>{})}>重试本次提交</button>}
  </article>)}</div></div>{showLatest&&<button className="workbench-return-latest" onClick={returnToLatest}>回到最新</button>}{conversationFooter}
  <BusinessChatInput runtime={contentComposerRuntime} purpose="content_production" operatorWorkspace knowledgeEditingBlocked={Boolean(knowledgeEditingBlocked)} />
  {["running","pending"].includes(runtime.activeConversation?.status??"")&&<button className="cp-live-stop" type="button" onClick={()=>void runtime.stop().catch(()=>{})}>停止当前执行</button>}
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
function InstalledWorkspace({client}:{client:ContentBusinessClient}){const host:ContentWorkspaceHost={connections:{publishedKnowledge:false},ConversationPurposeProvider:({children})=><>{children}</>,useConversation:useRuntime,useSendMessage:()=>({sendMessage:useRuntime().sendMessage}),retrieveTask:(id,options)=>client.task(id,options?.signal),captureWorkspaceRestOperation:(signal=new AbortController().signal)=>({signal,assertActive(){signal.throwIfAborted();},fetch:(url,init)=>fetch(url,{...init,signal})}),useWorkspaceDraftGuard:useDraftGuard,requestWorkspaceNavigation:requestDraftNavigation,Home:ContentDialogue,FilePreview,WorkbenchTaskToolbar,AgentWorkbenchShell,BusinessWorkspaceInspector};return <ContentWorkspaceHostProvider value={host}><ContentProductionWorkspace workbench/></ContentWorkspaceHostProvider>}
export function ModuleWorkspace({context,client=liveContentClient}:{context:ModuleContext;client?:ContentBusinessClient}) {return <RuntimeProvider client={client} workspaceId={context.workspace.id}><InstalledWorkspace client={client}/></RuntimeProvider>}
