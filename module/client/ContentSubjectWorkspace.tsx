import {useCallback,useEffect,useRef,useState,type ReactNode} from "react";
import {ChevronDown,Folder,FolderOpen,Pin,Plus,Search,X,Trash2} from "lucide-react";
import {Dialog,DialogContent,DialogDescription,DialogTitle} from "@frontmind/module-ui/components/ui/dialog";
import {contentOutputIdentity,useContentWorkspaceHost,type ContentConversation,type ContentTranscriptNavigation,type TaskResponse} from "./host";
import type {ContentBusinessClient} from "./runtime";
import {contentProductionStagePosition,type ContentProductionDto,type ContentProductionInput} from "../contracts/content-production";
import {receivedContentIntake} from "../contracts/content-intake-receipt";
import {emptySubjectWorkspace,createSubjectFolder,bindSubjectChat,boundSubjectPack,latestSubjectPack,switchSubjectPack,updateSubjectChatMetadata,deleteSubjectFolder,type ContentSubjectWorkspace as SubjectState} from "../contracts/content-subject-workspace";
import {ContentCreationLane,contentCreationTranscriptAnchors} from "./ContentCreationLane";
import {useComposerConfirmation,contentConfirmationActionLabel} from "./useComposerConfirmation";
import ContentTaskActionDeck from "./ContentTaskActionDeck";
import {mapContentTaskOperations} from "./content-task-operations";
import ContentProductionFailureNotice from "./ContentProductionFailureNotice";
import "./content-subject-workspace.css";

/** 主体、版本与聊天属于业务层；预览和正式宿主共用本组件。 */
export default function ContentSubjectWorkspace({client}:{client:ContentBusinessClient}) {
 const host=useContentWorkspaceHost();
 const api=host.useConversation();
 const {sendMessage}=host.useSendMessage();
 const {Home,FilePreview}=host;
 const [subjects,setSubjects]=useState<SubjectState>(emptySubjectWorkspace());
 const stateRef=useRef(subjects);stateRef.current=subjects;
 const [loaded,setLoaded]=useState(false),[saving,setSaving]=useState(false),[notice,setNotice]=useState("");
 const writing=useRef(false),readSequence=useRef(0);
 const [folderId,setFolderId]=useState("");
 const [task,setTask]=useState<TaskResponse|null>(null),[taskError,setTaskError]=useState("");
 const [navigation,setNavigation]=useState<ContentTranscriptNavigation>();
 const [inspected,setInspected]=useState<number|null>(null);
 const [modal,setModal]=useState<"folder"|"chat"|null>(null),[pendingDelete,setPendingDelete]=useState<{kind:"conversation"|"folder";id:string;name:string}|null>(null),[name,setName]=useState(""),[chatTitle,setChatTitle]=useState(""),[chatKind,setChatKind]=useState<"pack"|"article"|"">("");
 const [assignConversation,setAssignConversation]=useState<string|null>(null);
 const pendingCreate=useRef<{id:string;title:string;folderId:string;kind:"pack"|"article"}|null>(null);
 const sourceNavigation=useRef<{conversationId:string;stageIndex:number}|null>(null);
 const navigationRef=useRef<HTMLElement|null>(null);
 const [formFolder,setFormFolder]=useState(""),[preview,setPreview]=useState<string|null>(null);
 const [showAll,setShowAll]=useState<Record<string,boolean>>({}),[folderSearch,setFolderSearch]=useState("");
 const [localChoices,setLocalChoices]=useState<Record<string,{style?:"A"|"B";requirements?:string}>>({});
 const current=api.activeConversation;
 const liveConversationIds=new Set(api.state.conversations.map(conversation=>conversation.id));
 const currentRef=useRef(current?.id);currentRef.current=current?.id;
 useEffect(()=>{
  // 创建或切换后让已选聊天出现在目录可视范围内，避免新记录落在屏幕之外。
  const selected=navigationRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
  selected?.scrollIntoView?.({block:"nearest"});
 },[current?.id,loaded]);
 const binding=current?subjects.bindings[current.id]:undefined;
 const historical=Boolean(current&&(!binding||(binding.kind==="article"&&!binding.packVersionId&&!current.taskId&&current.messages.length>0)));
 const generation=binding?.generation??current?.messages.findLast(message=>message.contentWorkflowGeneration!==undefined)?.contentWorkflowGeneration??0;
 const folder=subjects.folders.find(item=>item.id===(binding?.folderId||folderId))??subjects.folders[0];
 const pack=current&&binding?boundSubjectPack(subjects,current.id):null;
 const latest=folder?latestSubjectPack(subjects,folder.id):null;
 const observedTask=api.activeTask===undefined?task:api.activeTask;
 const progress=observedTask?.id===current?.taskId?observedTask?.contentProduction??null:null;
 const chatKindForDisplay=progress?.jobKind==="p0"||progress?.jobKind==="article"?"article":binding?.kind??"pack";
 // 正常入口沿用服务端回执；显式验收客户端保留旧版本回填的兼容显示。
 const intakeReceived=Boolean(receivedContentIntake(current))||Boolean(client.submitIntake&&current&&!current.taskId&&current.messages.some(message=>message.role==="user"));
 const turnFailed=Boolean(progress?.executionFailure)||Boolean(observedTask&&observedTask.id===current?.taskId&&["error","failed","cancelled"].includes(observedTask.status));
 const busy=saving||Boolean(api.submittingIds?.has(current?.id??""))||["running","pending"].includes(current?.status??"")||["running","pending"].includes(observedTask?.status??"");
 const stopLock=useRef(false);const [stopping,setStopping]=useState(false);
 async function stopExecution(){
  const id=current?.taskId;if(!id||stopLock.current)return;
  stopLock.current=true;setStopping(true);setNotice("");
  try{await client.stop(id);let value=await client.task(id);for(let check=0;check<40&&["running","pending"].includes(value.status);check++){await new Promise(resolve=>setTimeout(resolve,250));value=await client.task(id);}if(["running","pending"].includes(value.status))throw new Error("停止请求未确认，请重试停止。");if(currentRef.current===current?.id)setTask(value);await api.refreshConversations?.();}
  catch(error){setNotice(error instanceof Error?error.message:"停止请求未确认，请重试停止。");}
  finally{stopLock.current=false;setStopping(false);}
 }
 const recoveryLock=useRef(false);const [recovering,setRecovering]=useState(false);
 const retryStartup=progress?.source==="awaiting_runner"&&["error","stopped","cancelled"].includes(observedTask?.status??"")?current?.messages.find(message=>message.role==="user"&&!message.generalChatDispatch):null;
 const resumeExecution=progress?.availableActions.includes("resume_current_execution")===true;
 async function recoverExecution(){
  if(busy||recoveryLock.current||(!retryStartup&&!resumeExecution))return;
  recoveryLock.current=true;setRecovering(true);setNotice("");
  try{const accepted=await sendMessage(resumeExecution?"恢复当前执行":retryStartup!.content,[],resumeExecution?{contentProductionAction:{kind:"resume_current_execution",revision:progress!.runnerRevision!}}:{});if(accepted!==false)await refreshAfterSend();}
  catch(error){setNotice(error instanceof Error?error.message:"恢复失败，请重试。");}
  finally{recoveryLock.current=false;setRecovering(false);}
 }
 const resumableAssembly=!busy&&!turnFailed&&["completed","idle"].includes(current?.status??"")&&progress?.workflowStatus==="running_reference_pack_assembly"&&!progress.confirmation;
 // 已有任务保留原冻结上下文，不因新版尚未登记资料包而挡住历史或重建任务。
 const missing=Boolean(binding?.kind==="article"&&!pack&&!current?.taskId&&!current?.messages.length);
 const choiceKey=`${current?.id}:${progress?.runnerRevision??"idle"}`;
 const choices=localChoices[choiceKey]??{};
 // 尚无任务时只核对本次输入，不把本地修订号 0 投影成原生 Runner 停点。
 const startupConfig:ContentProductionInput|null=loaded&&current&&!current.taskId&&!intakeReceived&&binding?{mode:binding.kind==="pack"?(latest?"refresh_reference_pack":"new_reference_pack"):pack?.includesP0?"single_article":"p0",enterpriseName:folder?.name??current.title,knowledgeSource:"files",monitoringAnswerAssetIds:[],subjectContext:{folderId:binding.folderId,generation:binding.generation??0,packVersionId:binding.kind==="pack"?(latest?.id??null):binding.packVersionId}}:null;
 const startupReview:ContentProductionDto|null=startupConfig?{
  mode:startupConfig.mode,enterpriseName:startupConfig.enterpriseName,workflowVersion:"input-review-only",
  workflowStatus:null,currentStage:null,jobKind:null,runnerRevision:0,pauseTitle:null,choices:[],productionStep:null,
  confirmation:null,progressPosition:0,completedConfirmations:[],
  availableActions:binding?.kind==="pack"?["provide_reference_pack_inputs"]:["choose_question","provide_question_research_inputs"],
  knowledgeBase:null,source:"awaiting_runner",
 }:null;

 const readSubjects=useCallback(async()=>{
  if(!client.readSubjectWorkspace)throw new Error("当前宿主尚未接入主体资料库。");
  const sequence=++readSequence.current;
  const value=await client.readSubjectWorkspace();
  if(sequence===readSequence.current&&!writing.current){stateRef.current=value;setSubjects(value);setLoaded(true);}
 },[client]);
 useEffect(()=>{let cancelled=false;void readSubjects().catch(error=>{if(!cancelled)setNotice(error.message);});return()=>{cancelled=true;readSequence.current++;};},[readSubjects]);
 async function changeSubjects(operation:(value:SubjectState)=>SubjectState){
  if(writing.current){setNotice("正在保存，请稍候。");throw new Error("正在保存，请稍候。");}
  if(!client.saveSubjectWorkspace)throw new Error("当前宿主不能保存主体资料库。");
  writing.current=true;setSaving(true);readSequence.current++;
  try{
   let saved:SubjectState;
   try{saved=await client.saveSubjectWorkspace(operation(stateRef.current));}
   catch(error){
    // 轮询、另一窗口或服务器登记资料包可能推进修订号；重新读取后只重放本次元数据操作。
    if(!(error instanceof Error)||!error.message.includes("主体资料库已在其他窗口更新")||!client.readSubjectWorkspace)throw error;
    const latest=await client.readSubjectWorkspace();stateRef.current=latest;setSubjects(latest);
    saved=await client.saveSubjectWorkspace(operation(latest));
   }
   stateRef.current=saved;setSubjects(saved);setNotice("");return saved;
  }
  catch(error){setNotice(error instanceof Error?error.message:"保存失败，修改尚未提交。");throw error;}
  finally{writing.current=false;setSaving(false);}
 }
 const report=(operation:()=>Promise<unknown>)=>{void operation().catch(()=>{});};
 useEffect(()=>{setInspected(null);setNavigation(undefined);setTask(null);setTaskError("");setPreview(null);},[current?.id,current?.taskId]);
 useEffect(()=>{const target=sourceNavigation.current;if(!target||current?.id!==target.conversationId)return;const anchor=contentCreationTranscriptAnchors(current.messages).get(target.stageIndex);if(!anchor)return;sourceNavigation.current=null;setInspected(target.stageIndex);setNavigation(previous=>({conversationId:current.id,messageId:anchor,sequence:(previous?.sequence??0)+1}));},[current?.id,current?.messages]);
 useEffect(()=>{
  const id=current?.taskId,conversationId=current?.id;if(!id||api.activeTask!==undefined)return;
  let disposed=false,timer:ReturnType<typeof setTimeout>;const controller=new AbortController();
  async function read(){try{const value=await client.task(id!,controller.signal);if(disposed||currentRef.current!==conversationId)return;if(value.id!==id)throw new Error("任务与当前聊天不匹配。");setTask(value);setTaskError("");await api.refreshConversations?.();}catch(error){if(!disposed)setTaskError(error instanceof Error?error.message:"阶段读取失败。");}finally{if(!disposed)timer=setTimeout(read,2500);}}
  void read();return()=>{disposed=true;controller.abort();clearTimeout(timer);};
 },[current?.taskId,current?.id,client,api.activeTask===undefined]);
 useEffect(()=>{if(["positioning_ready","p0_ready","completed"].includes(progress?.workflowStatus??""))void readSubjects().catch(error=>setNotice(error.message));},[progress?.workflowStatus,progress?.runnerRevision,readSubjects]);
 const refreshAfterSend=async()=>{await api.refreshConversations?.();if(current?.taskId){const next=await client.task(current.taskId);if(currentRef.current===current.id)setTask(next);}await readSubjects();};
 const confirmationKey=turnFailed||intakeReceived?null:startupReview&&current&&binding?`${current.id}:input-review:${binding.folderId}:${binding.kind}:${binding.packVersionId??"none"}:${binding.generation}:${latest?.id??"none"}`:progress?.confirmation&&current?`${current.id}:${current.taskId}:${binding?.generation}:${binding?.packVersionId}:${progress.runnerRevision}:${progress.confirmation}`:null;
 const confirmation=useComposerConfirmation(confirmationKey,startupReview??progress,async(prompt,files,action)=>{
  if(turnFailed||binding?.restartRequired||currentRef.current!==current?.id)return false;
  const accepted=await sendMessage(prompt,files,!current?.taskId&&startupConfig
   ?{contentProduction:startupConfig,contentWorkflowGeneration:binding?.generation??0}
   :{contentProductionAction:action,contentWorkflowPosition:contentProductionStagePosition(progress?.currentStage??null,progress?.workflowStatus??null),contentWorkflowStatus:progress?.workflowStatus??undefined,contentWorkflowGeneration:generation,contentWorkflowKind:progress?.jobKind??undefined});
  if(accepted===false)return false;
  setNotice("");
  // 已被服务器接受的提交不可因随后读取失败而再次发送。
  void refreshAfterSend().catch(()=>{if(currentRef.current===current?.id)setNotice("已提交，状态读取失败，请刷新查看记录，勿重复提交。");});
  return true;
 },setNotice);
 host.useWorkspaceDraftGuard({dirty:modal!==null&&Boolean(name.trim()||chatTitle.trim()||chatKind),label:"新建主体或聊天"});
 const navigate=(id:string)=>host.requestWorkspaceNavigation(()=>{api.setActive(id);setNotice("");});
 const openPack=(stageIndex?:number)=>{if(pack){if(stageIndex!==undefined)sourceNavigation.current={conversationId:pack.sourceConversationId,stageIndex};navigate(pack.sourceConversationId);}else if(folder){const source=Object.entries(subjects.bindings).find(([id,item])=>item.folderId===folder.id&&item.kind==="pack"&&!item.archived&&api.state.conversations.some(row=>row.id===id));if(source)navigate(source[0]);else openChat(folder.id,"pack");}};
 function openChat(id=folder?.id??"",kind:"pack"|"article"|""=""){setAssignConversation(null);setFormFolder(id);setChatKind(kind);setChatTitle(kind==="pack"?"资料包创建与修改":kind==="article"?"新文章书写":"");setName("");setModal("chat");setNotice("");}
 function openFolder(){setName("");setChatTitle("");setChatKind("");setModal("folder");setNotice("");}
 async function create(){
  try{
   if(modal==="folder"){
    const id=crypto.randomUUID();await changeSubjects(value=>createSubjectFolder(value,name,id));setFolderId(id);setFormFolder(id);api.setActive("");setName("");setChatKind("pack");setChatTitle("资料包创建与修改");setModal("chat");return;
   }
   if(!chatKind||!chatTitle.trim()||!formFolder)return;
   if(!api.saveConversation)throw new Error("当前宿主不能保存聊天。");
   const previous=pendingCreate.current;
   const id=assignConversation??(previous?.folderId===formFolder&&previous.kind===chatKind&&previous.title===chatTitle.trim()?previous.id:crypto.randomUUID()),now=Date.now();
   pendingCreate.current={id,title:chatTitle.trim(),folderId:formFolder,kind:chatKind};
   const row:ContentConversation={id,title:chatTitle.trim(),purpose:"content_production",status:"idle",messages:[],createdAt:now,updatedAt:now};
   if(!assignConversation&&!api.state.conversations.some(item=>item.id===id))await api.saveConversation(row);
   await changeSubjects(value=>bindSubjectChat(value,{conversationId:id,folderId:formFolder,kind:chatKind}));
   pendingCreate.current=null;setAssignConversation(null);setModal(null);setChatTitle("");setChatKind("");setFolderId(formFolder);api.setActive(id);
  }catch(error){setNotice(error instanceof Error?error.message:"创建失败，请重试。");}
 }
 async function switchPack(versionId:string){
  if(!current||!versionId||versionId===pack?.id||busy||confirmation.pending)return;
  try{await changeSubjects(value=>switchSubjectPack(value,{conversationId:current.id,versionId,hasTask:Boolean(current.taskId)}));await api.refreshConversations?.();setTask(null);setTaskError("");await readSubjects();setInspected(null);setNotice("已切换资料包。后续写作须按新资料重新确认；此前交付保留为历史。");}catch{}
 }
 function setMetadata(id:string,patch:{pinned?:boolean;archived?:boolean}){report(async()=>{
  const folderId=stateRef.current.bindings[id]?.folderId;
  await changeSubjects(value=>updateSubjectChatMetadata(value,id,patch));
  if(patch.archived&&currentRef.current===id){
   const next=api.state.conversations.find(row=>row.id!==id&&stateRef.current.bindings[row.id]?.folderId===folderId&&!stateRef.current.bindings[row.id]?.archived);
   navigate(next?.id??"");
  }
  if(patch.archived!==undefined)setNotice(patch.archived?"聊天已归档，可在当前主体的已归档列表中恢复。":"聊天已恢复。");
 });}
 async function deleteConversation(conversation:ContentConversation){
  setPendingDelete({kind:"conversation",id:conversation.id,name:conversation.title});
 }
 async function confirmDeleteConversation(){
  if(!pendingDelete||pendingDelete.kind!=="conversation")return;
  const target=pendingDelete;setPendingDelete(null);
  const binding=stateRef.current.bindings[target.id];
  const folderIdToUse=binding?.folderId??folder?.id;
  const wasSelected=currentRef.current===target.id;
  try{
   if(!api.deleteConversation)throw new Error("当前宿主不支持删除聊天。");
   await (api.deleteConversation as unknown as (id:string)=>Promise<void>)(target.id);
   await api.refreshConversations?.();
   if(binding)await readSubjects();
   if(wasSelected){
    const next=api.state.conversations.find(row=>row.id!==target.id&&stateRef.current.bindings[row.id]?.folderId===folderIdToUse&&!stateRef.current.bindings[row.id]?.archived);
    api.setActive(next?.id??"");
   }
   setNotice("聊天已删除。");
  }catch(error){setNotice(error instanceof Error?error.message:"删除聊天失败。");}
 }
 async function deleteFolder(folderIdToDelete:string,nameToDelete:string){
  const target=subjects.folders.find(item=>item.id===folderIdToDelete);
  const hasBindings=Object.entries(subjects.bindings).some(([conversationId,binding])=>binding.folderId===folderIdToDelete&&liveConversationIds.has(conversationId));
  if(!target||target.versions.length||hasBindings){setNotice(target?.versions.length?"含已确认资料包版本，不能删除。":"仍有绑定聊天，不能删除。");return;}
  setPendingDelete({kind:"folder",id:folderIdToDelete,name:nameToDelete});
 }
 async function confirmDeleteFolder(){
  if(!pendingDelete||pendingDelete.kind!=="folder")return;
  const target=pendingDelete;setPendingDelete(null);
  try{
   await changeSubjects(value=>deleteSubjectFolder(value,target.id,liveConversationIds));
   if(folderId===target.id){const next=stateRef.current.folders.find(item=>item.id!==target.id);setFolderId(next?.id??"");api.setActive("");}
   setNotice("文件夹已删除。");
  }catch(error){setNotice(error instanceof Error?error.message:"删除文件夹失败。");}
 }
 const setChoice=(patch:{style?:"A"|"B";requirements?:string})=>setLocalChoices(previous=>({...previous,[choiceKey]:{...previous[choiceKey],...patch}}));
 async function stage(prompt:string,files:File[]){
  if(intakeReceived){setNotice("服务器已收件，生成尚未启动，请勿重复提交当前聊天。");return false;}
  if(turnFailed){setNotice("本轮执行已停止，请先处理失败原因，再明确发起下一轮。");return false;}
  if(!loaded){setNotice("正在读取项目信息，请稍候。");return false;}
  if(!binding&&!current?.taskId){setNotice("历史聊天和附件已保留；开始新的制作流程时再选择主体文件夹。");return false;}
  if(!current||missing||busy||binding?.restartRequired){setNotice(binding?.restartRequired?"资料包已变更，当前宿主尚未完成重新绑定，请先刷新。":"请先完成当前文件夹的资料包。");return false;}
  const attachmentError=files.map(file=>client.validateAttachment?.(file)).find(Boolean);
  if(attachmentError){setNotice(attachmentError);return false;}
  setInspected(null);setNavigation(previous=>({conversationId:current.id,latest:true,sequence:(previous?.sequence??0)+1}));
  if(!current.taskId)return confirmation.stage(prompt,files);
  if(!progress?.confirmation){
   const deliveredManuscript=progress?.jobKind==="p0"&&progress.workflowStatus==="p0_ready"||progress?.jobKind==="article"&&progress.workflowStatus==="completed";
   if(deliveredManuscript||resumableAssembly&&/^继续/u.test(prompt.trim()))return sendMessage(prompt,files,{contentWorkflowStatus:progress!.workflowStatus??undefined,contentWorkflowGeneration:generation,contentWorkflowKind:progress!.jobKind??undefined});
   setNotice("当前没有待确认的写作步骤，请先读取阶段。");return false;
  }
  let text=prompt;
  if(progress.availableActions.includes("choose_examples")&&progress.choices.some(item=>item.includes("文章池"))){
   const style=/^(?:文风\s*[:：]?\s*|方案\s*)?([AB])$/iu.exec(prompt.trim());
   if(style&&files.length===0){setChoice({style:style[1].toUpperCase() as "A"|"B"});setNotice("文风已记录。请在底部继续填写 1—2 个构思参考编号，或“不采用”；核对卡片后再提交。");return true;}
   if(choices.style&&/^(?:文章池\s*[:：]\s*)?(?:不采用|\d+(?:[、,，\s]+\d+)?)$/u.test(prompt.trim()))text=`文风：${choices.style}；文章池：${prompt.replace(/^文章池\s*[:：]\s*/u,"").trim()}`;
  }
  if(progress.availableActions.includes("submit_response_brief")){
   if(files.length===0&&/^(?:无额外要求|额外要求\s*[:：]\s*[^；;\n]+)$/u.test(prompt.trim())){setChoice({requirements:prompt.trim()});setNotice("已记录企业应答要求。请继续判断品牌认知：充分、不充分或不确定。");return true;}
   if(choices.requirements&&/^(?:品牌认知\s*[:：]\s*)?(?:充分|不充分|不确定)$/u.test(prompt.trim()))text=`${choices.requirements.startsWith("额外要求")?choices.requirements:`额外要求：${choices.requirements}`}；品牌认知：${prompt.replace(/^品牌认知\s*[:：]\s*/u,"").trim()}`;
  }
  return confirmation.stage(text,files);
 }
 async function stageAction(action:import("../contracts/content-production").ContentProductionAction,prompt:string,files:File[]=[]){
  if(!current||busy||turnFailed||intakeReceived){setNotice("当前任务暂不可操作，请刷新状态后重试。");return false;}
  const attachmentError=files.map(file=>client.validateAttachment?.(file)).find(Boolean);if(attachmentError){setNotice(attachmentError);return false;}
  if(!current.taskId){return stage(prompt,files);}
  setInspected(null);setNavigation(previous=>({conversationId:current.id,latest:true,sequence:(previous?.sequence??0)+1}));
  return confirmation.stageAction(action,prompt,files);
 }
 function action(label:string,prompt:string){return <button key={label} type="button" className="cp-subject-action" disabled={busy||Boolean(confirmation.pending)} onClick={()=>report(()=>stage(prompt,[]))}>{label}</button>;}
 function actions():ReactNode {
  if(turnFailed||intakeReceived||busy)return null;
  const has=(kind:string)=>progress?.availableActions.some(item=>item===kind);
  if(has("choose_question"))return progress?.choices.filter(item=>/^(?:选择\s*)?\d+(?:[.．、]\s*|$)/u.test(item)).map(item=>action(item,`选择问题：${item.replace(/^选择\s*/u,"").replace(/^\d+[.．、]\s*/u,"")}`));
  if(has("choose_core_positioning_direction"))return progress?.choices.flatMap(item=>{const match=/方向\s*([A-C1-3])/iu.exec(item);return match?[action(item,`方向：${match[1]}`)]:[];});
  if(has("choose_p0_route"))return action("先制作品牌长文","新建 P0");
  if(has("choose_p0_examples"))return <>{action("采用工作流写作规范","P0 文风：工作流写作规范")}{action("查看匹配例文","P0 文风：Top20")}</>;
  if(has("confirm_competitors"))return action(progress?.jobKind==="article"?"确认本题两家比较对象":"确认比较范围","确认比较对象");
  if(has("confirm_core_positioning"))return action("确认核心定位","确认核心定位");
  if(has("confirm_pattern"))return <>{action("P01 · 集中介绍本主体","文章类型：P01")}{action("P02 · 本主体＋两家比较对象","文章类型：P02")}</>;
  if(has("choose_examples"))return <>{action("方案 A · 参考匹配例文写法","文风：A")}{action("方案 B · 工作流写作规范","文风：B")}{choices.style&&<span>已选文风 {choices.style}；请从底部填写构思参考，或“不采用”。</span>}</>;
  if(has("submit_response_brief"))return choices.requirements?<>{["充分","不充分","不确定"].map(item=>action(item,item))}</>:action("无额外要求","无额外要求");
  if(has("confirm_question_positioning"))return action("确认本题定位，生成蓝图","确认问题定位");
  if(has("confirm_blueprint")||has("confirm_p0_blueprint"))return action("确认蓝图，开始写作","确认写作方案");
  return null;
 }
 const handoff=!turnFailed&&progress?.sessionPhases===true&&["positioning_ready","p0_ready"].includes(progress?.workflowStatus??"");
 async function continueWriting(){if(!handoff)return;try{await sendMessage(progress?.workflowStatus==="positioning_ready"?"继续 P0":"继续问题文章");await refreshAfterSend();}catch(error){setNotice(error instanceof Error?error.message:"接续失败。");}}
 const footer=<div className="cp-subject-turn" hidden={inspected!==null}>
  {historical&&<p className="cp-subject-question">原聊天、附件与任务已保留。{current?.taskId?"后续操作继续使用原任务。":"历史记录可直接查看。"}</p>}
  {!historical&&!intakeReceived&&current&&(!current.taskId||!current.messages.length)&&<p className="cp-subject-question">{binding?.kind==="pack"?"请从下方操作卡片选择资料处理方式。":"已自动引用同主体资料包，请从下方操作卡片选择当前步骤。"}</p>}
  {intakeReceived&&<p className="cp-subject-question">服务器已收件，生成尚未启动。</p>}
  {!intakeReceived&&client.attachmentHint&&(startupReview??progress)?.availableActions.some(kind=>kind==="provide_reference_pack_inputs"||kind==="provide_question_research_inputs")&&<p className="cp-subject-question">{client.attachmentHint}</p>}
  {!busy&&!confirmation.pending&&progress?.pauseTitle&&<div className="cp-subject-question"><span>当前需要确认</span><strong>{progress.pauseTitle}</strong></div>}
  <ContentTaskActionDeck cards={mapContentTaskOperations(progress,{busy,failed:turnFailed,pendingConfirmation:Boolean(confirmation.pending),taskId:current?.taskId,startupConfig:Boolean(!current?.taskId&&startupConfig&&!intakeReceived),retryStartup:!progress?.confirmation?retryStartup?.content:undefined,resumeExecution,resumableAssembly:!progress?.confirmation&&resumableAssembly,handoff:!progress?.confirmation&&handoff})} busy={busy||Boolean(confirmation.pending)} onSelect={(card,files=[],instructions)=>{if(card.id==="retry-startup"||card.id==="resume-execution"){void recoverExecution();return;}if(card.id==="handoff"){void continueWriting();return;}if(card.action)void stageAction(card.action,card.prompt,files);else if(card.id==="revise-current-step"&&progress?.runnerRevision!=null&&instructions?.trim())void stageAction({kind:"revise_current_step",revision:progress.runnerRevision,instructions:instructions.trim()},`修改：${instructions.trim()}`);else void stage(card.prompt,files);}} />
  {api.activeTask===undefined&&current?.taskId&&["running","pending"].includes(observedTask?.status??current.status)&&<button className="cp-live-stop" type="button" disabled={stopping} onClick={()=>void stopExecution()}>{stopping?"正在请求停止…":"停止当前执行"}</button>}
  {confirmation.pending&&<section className="cp-subject-confirmation" aria-label="输入确认卡片"><strong>{startupReview?"核对本次输入":contentConfirmationActionLabel(confirmation.pending.action)}</strong>{startupReview&&<span>仅核对输入，生成尚未启动。</span>}<p>{confirmation.pending.prompt}</p>{confirmation.pending.files.map((file,i)=><span key={i}>{file.name}</span>)}<div className="cp-subject-actions"><button type="button" className="cp-subject-primary" disabled={confirmation.submitting} onClick={()=>report(confirmation.confirm)}>{confirmation.submitting?"正在提交…":"确认提交"}</button><button type="button" className="cp-subject-action" disabled={confirmation.submitting} onClick={confirmation.cancel}>返回修改</button></div></section>}
 </div>;
 const row=(conversation:ContentConversation)=>{const metadata=subjects.bindings[conversation.id];return <div key={conversation.id} className="cp-subject-chat" data-current={current?.id===conversation.id}><button type="button" className="cp-subject-chat-name" aria-current={current?.id===conversation.id?"page":undefined} title={conversation.title} onClick={()=>navigate(conversation.id)}>{conversation.title}</button><div className="cp-subject-tools">{metadata&&<button type="button" disabled={saving} aria-label={`${metadata.pinned?"取消置顶":"置顶聊天"}：${conversation.title}`} aria-pressed={Boolean(metadata.pinned)} onClick={()=>setMetadata(conversation.id,{pinned:!metadata.pinned})}><Pin size={14}/></button>}<button type="button" disabled={saving} title={metadata?"删除该聊天；已确认资料包来源或执行中的聊天会被服务端拒绝":"删除历史聊天"} aria-label={`删除聊天：${conversation.title}`} onClick={()=>void deleteConversation(conversation)}><Trash2 size={14}/></button></div></div>;};
 const updateAvailable=pack&&latest&&pack.id!==latest.id;
 const outputs=current?.messages.filter(item=>item.role==="assistant").flatMap(item=>item.outputFiles??[])??[];
 const previewPack=subjects.folders.flatMap(item=>item.versions).find(item=>item.id===preview);
 const normalizedFolderSearch=folderSearch.trim().toLocaleLowerCase();
 const filteredFolders=subjects.folders.map(item=>{
  const all=api.state.conversations.filter(value=>subjects.bindings[value.id]?.folderId===item.id);
  const live=all.sort((a,b)=>Number(Boolean(subjects.bindings[b.id].pinned))-Number(Boolean(subjects.bindings[a.id].pinned)));
  const archived:ContentConversation[]=[];
  const folderMatches=!normalizedFolderSearch||item.name.toLocaleLowerCase().includes(normalizedFolderSearch);
  const matchingLive=folderMatches?live:live.filter(value=>value.title.toLocaleLowerCase().includes(normalizedFolderSearch));
  const matchingArchived=folderMatches?archived:archived.filter(value=>value.title.toLocaleLowerCase().includes(normalizedFolderSearch));
  return {item,live,archived,matchingLive,matchingArchived,folderMatches,expanded:item.expanded!==false};
 }).filter(entry=>!normalizedFolderSearch||entry.folderMatches||entry.matchingLive.length>0||entry.matchingArchived.length>0);
 const historicalConversations=api.state.conversations.filter(value=>!subjects.bindings[value.id]&&(!normalizedFolderSearch||value.title.toLocaleLowerCase().includes(normalizedFolderSearch)));
 const subjectNavigation=(
  <nav ref={navigationRef} className="cp-subject-nav" aria-label="主体文件夹与聊天">
   <header><h2>主体文件夹</h2><button type="button" aria-label="新建主体文件夹" title="新建主体文件夹" onClick={openFolder} disabled={!loaded||busy}><Plus size={18}/></button></header>
   <label className="cp-subject-search"><Search size={16} aria-hidden="true"/><input aria-label="搜索主体与聊天" type="search" value={folderSearch} onChange={event=>setFolderSearch(event.target.value)} placeholder="搜索主体与聊天"/></label>
   <button type="button" className="cp-subject-new-chat" onClick={()=>openChat()} disabled={!folder||busy}>＋ 新建聊天</button>
   {filteredFolders.map(({item,live,archived,matchingLive,matchingArchived,folderMatches,expanded})=>{
    const visible=normalizedFolderSearch?matchingLive:showAll[item.id]?live:live.slice(0,5);
    if(!normalizedFolderSearch&&current&&live.includes(current)&&!visible.includes(current))visible.splice(4,1,current);
    const showChildren=expanded||Boolean(normalizedFolderSearch);
    return <section className="cp-subject-group" key={item.id}>
     <div className="cp-subject-folder-row">
      <button type="button" className="cp-subject-folder-name" aria-expanded={expanded} onClick={()=>{const different=folder?.id!==item.id;const operation=()=>{setFolderId(item.id);if(different)api.setActive(live[0]?.id??"");report(()=>changeSubjects(value=>({...value,revision:value.revision+1,folders:value.folders.map(f=>f.id===item.id?{...f,expanded:different?true:!expanded}:f)})));};if(different)host.requestWorkspaceNavigation(operation);else operation();}}>
       {showChildren?<FolderOpen size={16}/>:<Folder size={16}/>}<span>{item.name}</span>
      </button>
      <button type="button" aria-label={`在${item.name}中新建聊天`} title="在当前主体中新建聊天" onClick={()=>openChat(item.id)} disabled={busy}><Plus size={15}/></button><button type="button" aria-label={`删除文件夹：${item.name}`} title={item.versions.length?"含资料包版本，不能删除":Object.entries(subjects.bindings).some(([conversationId,binding])=>binding.folderId===item.id&&liveConversationIds.has(conversationId))?"仍有绑定聊天，不能删除":"删除空文件夹"} disabled={saving||item.versions.length>0||Object.entries(subjects.bindings).some(([conversationId,binding])=>binding.folderId===item.id&&liveConversationIds.has(conversationId))} onClick={()=>void deleteFolder(item.id,item.name)}><Trash2 size={14}/></button>
     </div>
     {showChildren&&<>
      {visible.map(row)}
      {!normalizedFolderSearch&&!live.length&&<p className="cp-subject-nav-empty">暂无聊天</p>}
      {normalizedFolderSearch&&folderMatches&&!matchingLive.length&&<p className="cp-subject-nav-empty">暂无匹配聊天</p>}
      {!normalizedFolderSearch&&live.length>5&&<button type="button" className="cp-subject-more" onClick={()=>setShowAll(value=>({...value,[item.id]:!value[item.id]}))}>{showAll[item.id]?"收起显示":"展开显示"}</button>}
      
     </>}
    </section>;
   })}
   {historicalConversations.length>0&&<section className="cp-subject-group"><h3>历史项目</h3>{historicalConversations.map(row)}</section>}
   {normalizedFolderSearch&&!filteredFolders.length&&!historicalConversations.length&&<p className="cp-subject-nav-empty cp-subject-search-empty">没有匹配的主体或聊天</p>}
  </nav>
 );
 return <section className="cp-subject-workspace" aria-label="主体文件夹与内容创作">
  {subjectNavigation}
  <main className="cp-subject-main"><header className="cp-subject-heading"><div className="cp-subject-crumb">{historical?"历史项目":folder?.name??"主体文件夹"} / {historical?"原有聊天":binding?.kind==="pack"?"资料包创建与修改":"文章书写"}</div><div className="cp-subject-title"><h1>{current?.title??folder?.name??"内容创作"}</h1>{binding&&<span>{binding.kind==="pack"?"资料包创建与修改":"文章书写"}</span>}</div><div className="cp-subject-reference"><span>{historical?"保留原记录":binding?.kind==="article"?pack?"自动引用":"等待资料包":"归档至"}</span><strong>{historical?current?.taskId?"原任务与附件":"原聊天与附件":binding?.kind==="article"?pack?`${folder?.name}资料包 · v${pack.version}`:"当前文件夹尚无已确认资料包":`${folder?.name??"请选择主体"} / 主体资料包`}</strong>{binding&&(pack||latest)&&<button type="button" onClick={()=>setPreview((pack||latest)!.id)}>查看</button>}</div>{binding?.kind==="article"&&pack&&folder&&<div className="cp-subject-version"><label>引用版本<select aria-label="资料包引用版本" value={pack.id} disabled={busy||Boolean(confirmation.pending)} onChange={event=>report(()=>switchPack(event.target.value))}>{folder.versions.map(item=><option key={item.id} value={item.id}>v{item.version}{item.id===latest?.id?"（最新）":""}{item.includesP0?" · 含P0":""}</option>)}</select><ChevronDown size={12}/></label>{updateAvailable&&<><span>资料包已更新至 v{latest.version}，本篇仍引用 v{pack.version}</span><button type="button" onClick={()=>report(()=>switchPack(latest.id))} disabled={busy||Boolean(confirmation.pending)}>应用新版本</button></>}</div>}</header>
   {(notice||taskError)&&<p className="cp-subject-notice" role="status">{notice||taskError}</p>}
   <ContentProductionFailureNotice failure={progress?.executionFailure}/>
   {current?(missing?<div className="cp-subject-empty"><p>{latest?`本主体已有已确认资料包 v${latest.version}，请引用后继续。`:"当前主体还没有已确认的资料包。请先完成资料包，再继续这篇文章。"}</p>{latest?<button type="button" className="cp-subject-primary" onClick={()=>report(()=>switchPack(latest.id))}>引用资料包 v{latest.version} 继续</button>:<button type="button" className="cp-subject-primary" onClick={()=>openPack()}>前往资料包聊天</button>}</div>:<div className="cp-subject-dialogue"><Home embedded operatorWorkspace hideComposer hideSidebar hidePortalNavigation showKnowledgeBaseStarter={false} showAccountMenu={false} showSettings={false} purpose="content_production" knowledgeEditingBlocked={Boolean(binding?.restartRequired)||Boolean(historical&&!current?.taskId)} transcriptNavigation={navigation} onReturnToLatest={()=>setInspected(null)} onComposerSubmit={stage} conversationFooter={footer}/></div>):<div className="cp-subject-empty"><p>{loaded?"请选择聊天，或在主体文件夹中新建聊天。":"正在读取主体与聊天…"}</p><button type="button" className="cp-subject-primary" onClick={()=>folder?openChat(folder.id):openFolder()} disabled={!loaded}>{folder?"新建聊天":"新建主体文件夹"}</button></div>}
  </main>
  <aside className="cp-subject-right"><ContentCreationLane progress={progress} executing={Boolean(api.submittingIds?.has(current?.id??""))||["running","pending"].includes(current?.status??"")||["running","pending"].includes(observedTask?.status??"")} messages={(current?.messages??[]).filter(message=>!binding||(message.contentWorkflowGeneration??0)===binding.generation)} packIncludesP0={Boolean(pack?.includesP0)} conversationId={current?.id??""} kind={chatKindForDisplay} boundPack={historical||Boolean(current?.taskId&&!pack)?undefined:Boolean(pack)} inspectedStage={inspected} onOpenPack={pack?openPack:undefined} onNavigate={target=>{if(!current)return;setInspected(target.latest?null:target.stageIndex);setNavigation(previous=>({conversationId:current.id,messageId:target.messageId,latest:target.latest,sequence:(previous?.sequence??0)+1}));}}/>{outputs.length>0&&<details className="cp-subject-files"><summary>交付文件（{new Set(outputs.map(contentOutputIdentity)).size}）</summary>{[...new Map(outputs.map(file=>[contentOutputIdentity(file),file])).values()].map(file=><FilePreview key={file.fileUrl} file={{id:file.fileUrl,type:"file",name:file.fileName,blobUrl:file.fileUrl}}/>)}</details>}</aside>
  <Dialog open={pendingDelete!==null} onOpenChange={value=>{if(!value)setPendingDelete(null);}}><DialogContent className="cp-subject-modal"><DialogTitle>{pendingDelete?.kind==="folder"?"确认删除文件夹":"确认删除聊天"}</DialogTitle><DialogDescription>{pendingDelete?.kind==="folder"?`确定删除空文件夹「${pendingDelete.name}」？`:`确定删除聊天「${pendingDelete?.name??""}」？此操作不可撤销。`}</DialogDescription><div className="cp-subject-modal-actions"><button type="button" className="cp-subject-action" onClick={()=>setPendingDelete(null)}>取消</button><button type="button" className="cp-subject-primary" disabled={saving} onClick={()=>void (pendingDelete?.kind==="folder"?confirmDeleteFolder():confirmDeleteConversation())}>确认删除</button></div></DialogContent></Dialog>
  <Dialog open={modal!==null} onOpenChange={value=>{if(!value)setModal(null);}}><DialogContent className="cp-subject-modal"><DialogTitle>{modal==="folder"?"新建主体文件夹":"新建聊天"}</DialogTitle><DialogDescription>{modal==="folder"?"输入企业、品牌或产品名称。":"选择所属主体和聊天类型，资料包将按主体自动引用。"}</DialogDescription>{modal==="folder"?<label>主体名称<input autoFocus value={name} onChange={event=>setName(event.target.value)} maxLength={40} placeholder="例如：示例品牌"/></label>:<><label>所属文件夹<select value={formFolder} onChange={event=>setFormFolder(event.target.value)}>{subjects.folders.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><fieldset><legend>聊天类型 · 必选</legend>{(["pack","article"] as const).map(kind=><label className="cp-subject-radio" key={kind}><input type="radio" name="subject-chat-kind" checked={chatKind===kind} onChange={()=>{setChatKind(kind);setChatTitle(kind==="pack"?"资料包创建与修改":"新文章书写");}}/><span>{kind==="pack"?"资料包创建与修改":"文章书写"}<small>{kind==="pack"?"整理资料、确认定位，创建或更新本主体资料包。":"自动引用同一主体的已确认资料包，在对话中完成写作。"}</small></span></label>)}</fieldset><label>聊天名称<input value={chatTitle} onChange={event=>setChatTitle(event.target.value)} maxLength={50}/></label>{chatKind==="article"&&<p>{(()=>{const item=subjects.folders.find(value=>value.id===formFolder),version=item?latestSubjectPack(subjects,item.id):null;return version?`将自动引用 ${item?.name}资料包 · v${version.version}`:"本主体尚无资料包。创建文章后，需先完成同主体的资料包。";})()}</p>}</>}{notice&&<p role="alert">{notice}</p>}<div className="cp-subject-modal-actions"><button type="button" className="cp-subject-action" onClick={()=>setModal(null)}>取消</button><button type="button" className="cp-subject-primary" disabled={saving||(modal==="folder"?!name.trim():!formFolder||!chatKind||!chatTitle.trim())} onClick={()=>report(create)}>{saving?"正在保存…":modal==="folder"?"创建文件夹":"创建聊天"}</button></div></DialogContent></Dialog>
  <Dialog open={Boolean(previewPack)} onOpenChange={value=>{if(!value)setPreview(null);}}><DialogContent className="cp-subject-modal"><DialogTitle>{folder?.name}资料包 · v{previewPack?.version}</DialogTitle><DialogDescription>已确认的资料包版本与原始交付。</DialogDescription>{previewPack&&<><p>来源聊天：{api.state.conversations.find(item=>item.id===previewPack.sourceConversationId)?.title??previewPack.sourceConversationId}</p><p>{previewPack.includesP0?"含品牌长文 P0":"主体资料与已确认定位"}</p><FilePreview file={{id:previewPack.file.fileUrl,type:"file",name:previewPack.file.fileName,blobUrl:previewPack.file.fileUrl}}/><button type="button" className="cp-subject-action" disabled={!api.state.conversations.some(item=>item.id===previewPack.sourceConversationId)} onClick={()=>{setPreview(null);navigate(previewPack.sourceConversationId);}}>查看来源聊天</button></>}</DialogContent></Dialog>
 </section>;
}
