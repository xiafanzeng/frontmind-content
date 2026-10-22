import {createHash,randomUUID} from "node:crypto";
import {execFile,spawn,type ChildProcess} from "node:child_process";
import {promisify} from "node:util";
import {existsSync,mkdirSync,readFileSync,writeFileSync,renameSync,realpathSync,createReadStream,openSync,closeSync} from "node:fs";
import {basename,dirname,extname,isAbsolute,join,relative,resolve,sep} from "node:path";
import type {IncomingMessage,ServerResponse} from "node:http";
import type {Plugin} from "vite";
import {contentProductionActionSchema,contentProductionInputSchema,type ContentProductionAction,type ContentProductionInput} from "../module/contracts/content-production";
import {parseContentRunnerState,reduceContentProductionProgress,contentProductionPublicDto} from "../module/server/state";
import {projectContentProductionMarkdown,contentProductionArtifactName} from "../module/contracts/content-production-public";
import type {ContentConversation,TaskResponse} from "../module/client/host";
import {readConversationProcesses,type ConversationProcess,type ProcessStatus} from "../module/contracts/conversation-process";
import {publicContentConversation} from "../module/server/conversations";
import {bindConversationProcesses,type LocalProcessTurn} from "../module/server/conversation-process";

const runFile=promisify(execFile);
type Snapshot={directory:string;brand:string;busy:boolean;state:Record<string,any>;reviews:{path:string;text:string;links?:Record<string,string>;time:number}[];files:string[];processes?:ConversationProcess[];factGate?:{issueCount:number;categories:string[];publishReady:boolean}|null};
type StoredTask={id:string;directory:string;conversationId:string;input:ContentProductionInput;error?:boolean;cancelled?:boolean;turns?:LocalProcessTurn[];archivedProcesses?:ConversationProcess[]};
type Store={conversations:Record<string,ContentConversation>;tasks:Record<string,StoredTask>;assets:Record<string,{path:string;filename:string}>;requests:Record<string,{taskId:string;fingerprint:string}>;hidden:string[]};
export type LocalWorkflowOptions={root:string;configDir:string;python:string};
const mime:Record<string,string>={".md":"text/markdown; charset=utf-8",".html":"text/html; charset=utf-8",".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",".zip":"application/zip"};
function reject(message:string,status=400):never{throw Object.assign(new Error(message),{status});}
function safeId(value:unknown):string{if(typeof value!=="string"||!/^[-a-zA-Z0-9_]{1,100}$/.test(value))reject("无效任务标识。");return value;}
function contained(root:string,file:string){const p=relative(realpathSync(root),realpathSync(file));return p!==".."&&!p.startsWith(`..${sep}`)&&!isAbsolute(p);}

/** Exact native actions: never treat arbitrary text as a confirmed choice. */
export function localActionArgs(action:ContentProductionAction,status:string):string[]{
 const args=["--revision",String(action.revision)];
 switch(action.kind){
  case "repair_article_facts":return [...args,"--repair-facts",...action.rejectedClaimIds.flatMap(id=>["--reject-fact-claim",id])];
  case "confirm_competitors":return [...args,"--confirm-competitors"];
  case "confirm_core_positioning":return [...args,"--confirm-core-positioning"];
  case "choose_reference_pack_route":return [...args,"--reference-pack-route",action.route];
  case "choose_question":return [...args,"--question-id",action.selection];
  case "choose_core_positioning_direction":{
   const direction=action.direction.match(/^(?:(?:采用)?方向\s*|direction_)?([1-3])$/)?.[1];
   if(!direction)reject("请输入当前定位方向的编号（1、2 或 3）。");
   return [...args,"--core-positioning-primary",direction];
  }
  case "choose_p0_route":return [...args,"--p0-route",action.route];
  case "choose_p0_examples":return [...args,"--accept-p0-example-route",action.route];
  case "confirm_p0_blueprint":return [...args,...(action.blueprintEdits?["--p0-blueprint-edits",action.blueprintEdits]:["--accept-p0-blueprint"])];
  case "submit_response_brief":return [...args,...(action.noExtraRequirements?["--no-extra-response-requirements"]:["--response-brief",action.requirements!]),"--ai-brand-recognition",action.aiBrandRecognition];
  case "confirm_pattern":return [...args,...(action.selectedPattern?["--pattern",action.selectedPattern]:["--accept-pattern"])];
  case "choose_examples":return [...args,"--example-route",action.route];
  case "confirm_question_positioning":return [...args,"--confirm-question-positioning"];
  case "confirm_blueprint":return [...args,...(action.blueprintEdits?["--blueprint-edits",action.blueprintEdits]:["--accept-blueprint"])];
  case "provide_reference_pack_inputs":case "provide_question_research_inputs":return args;
  case "update_competitor_selection": {
   try{JSON.parse(action.selection);}catch{reject("本地执行器要求结构化比较范围 JSON；请先保留当前范围，或通过原生 CLI 指定候选角色。");}
   return [...args,"--competitor-selection",action.selection];
  }
  case "revise_current_step":{
   const flags:Record<string,string>={awaiting_core_positioning_confirmation:"--core-positioning-edits",awaiting_core_positioning_direction:"--positioning-supplement",awaiting_competitor_selection:"--positioning-supplement",awaiting_p0_blueprint_confirmation:"--p0-blueprint-edits",awaiting_question_positioning_confirmation:"--question-positioning-edits",awaiting_blueprint_confirmation:"--blueprint-edits"};
   if(!flags[status])reject("当前阶段请使用上方明确选项或补充文件；本地执行器不自动解释自然语言操作。");
   return [...args,flags[status],action.instructions];
  }
 }
}

function localAttachmentArgs(action:ContentProductionAction,status:string,jobKind:string|null,files:string[]):string[]{
 if(!files.length)return [];
 const single=(flag:string)=>{if(files.length!==1)reject("当前阶段只接受一个附件，请保留一个文件后重新提交。");return [flag,files[0]];};
 switch(action.kind){
  case "provide_reference_pack_inputs":
   return ["reference_pack","reference_pack_refresh"].includes(jobKind??"")?files.flatMap(file=>["--input",file]):single("--input");
  case "choose_reference_pack_route":
   return action.route==="create"?files.flatMap(file=>["--input",file]):single("--input");
  case "provide_question_research_inputs":
   if(files.some(file=>extname(file).toLowerCase()===".xlsx")){
    if(files.length!==1)reject("监控问答表须单独上传，每次仅接受一张表，不能与其他附件一起提交。");
    return ["--monitoring-answers",files[0]];
   }
   return files.flatMap(file=>["--answer",file]);
  case "choose_p0_route":
   if(action.route==="import")return single("--p0-input");
   break;
  case "revise_current_step":
   if(status==="awaiting_p0_blueprint_confirmation")return single("--p0-blueprint-supplement");
   if(status==="awaiting_blueprint_confirmation")return single("--blueprint-supplement");
   reject("当前阶段的原生执行器不能同时处理调整说明和补充附件；请移除附件后提交调整，附件补充请使用原生 CLI 单独操作。");
 }
 reject("当前操作不接收附件，请移除附件后重新提交。");
}

export function localWorkflowPlugin(options?:LocalWorkflowOptions):Plugin{
 return {name:"frontmind-local-workflow",apply:"serve",configureServer(server){
  if(!options)return;
  const root=resolve(options.root),privateDir=join(root,".local-ui"),storePath=join(privateDir,"store.json");
  mkdirSync(privateDir,{recursive:true,mode:0o700});
  let store:Store=existsSync(storePath)?JSON.parse(readFileSync(storePath,"utf8")):{conversations:{},tasks:{},assets:{},requests:{},hidden:[]};
  const persist=()=>{const temp=storePath+".tmp";writeFileSync(temp,JSON.stringify(store),{mode:0o600});renameSync(temp,storePath);};
  const processes=new Map<string,ChildProcess>();
  const artifacts=new Map<string,{path:string;filename:string}>();
  let cache:Promise<Snapshot[]>|undefined,cacheUntil=0;
  async function snapshots(){
   if(!cache||Date.now()>cacheUntil){cacheUntil=Date.now()+1000;cache=runFile(options!.python,["-B",resolve("standalone/workflow_snapshot.py"),root],{maxBuffer:24*1024*1024,env:{...process.env,FRONTMIND_PROCESS_SUMMARY_CACHE:join(privateDir,"process-summaries")}}).then(r=>JSON.parse(r.stdout) as Snapshot[]).catch(()=>{cache=undefined;reject("无法读取本地工作流状态，请检查服务端运行记录。",503);});}
   return cache;
  }
  const fileOutput=(job:string,path:string)=>{
   const file=resolve(job,path);if(!existsSync(file)||!contained(job,file))reject("文件不在任务目录内。",403);
   const id=createHash("sha256").update(file).digest("hex").slice(0,32),filename=contentProductionArtifactName(basename(file));artifacts.set(id,{path:file,filename});
   return {fileUrl:`/api/frontmind/v2/artifacts/${id}/content`,fileName:filename,mimeType:mime[extname(file)]??"application/octet-stream"};
  };
  async function current(){
   const source=await snapshots();const results=new Map<string,{task:TaskResponse;conversation:ContentConversation;snapshot?:Snapshot;record:StoredTask}>();
   for(const snap of source){
    if(!Object.values(store.tasks).some(t=>t.directory===snap.directory)){
     const mode=snap.state.job_kind==="p0"?"p0":snap.state.job_kind==="article"?"single_article":"new_reference_pack";
     store.tasks[snap.state.job_id]={id:snap.state.job_id,directory:snap.directory,conversationId:snap.state.job_id,input:contentProductionInputSchema.parse({mode,enterpriseName:snap.brand,knowledgeSource:"files"})};persist();
    }
   }
   for(const record of Object.values(store.tasks)){
    if(store.hidden.includes(record.id))continue;
    const snap=source.find(s=>s.directory===record.directory),state=snap?parseContentRunnerState(Buffer.from(JSON.stringify(snap.state))):null;
    if(snap&&!state)reject("原生工作流状态不符合当前模块约定。",503);
    if(record.input.enterpriseName==="内容任务"&&snap?.brand&&snap.brand!=="内容任务"){
     record.input={...record.input,enterpriseName:snap.brand};persist();
    }
    const progress=state?reduceContentProductionProgress(null,{state,providerRank:state.revision,eventId:`r${state.revision}`,artifactId:"local-state",sha256:"local"},record.input.mode):null;
    let dto=contentProductionPublicDto({revision:1,accountUserId:0,purpose:"content_production",knowledgeBase:null,knowledgeText:null,contentProduction:record.input,contentWorkflow:{version:"4.13.2-v16.3",filename:"local-source",sha256:"local-development",rootDirectory:"source"}},progress?{contentProductionProgress:progress}:null);
    if(dto&&snap?.factGate&&!snap.factGate.publishReady&&state?.pending_action?.action==="article_fact_repair")dto={...dto,factGate:snap.factGate,availableActions:["repair_article_facts"]};
    const busy=processes.has(record.id)||Boolean(snap?.busy);
    const done=Boolean(state&&["completed","p0_ready","positioning_ready"].includes(state.status));
    const cancelled=!busy&&Boolean(record.cancelled);
    const failed=!cancelled&&!busy&&(record.error||Boolean(snap?.state.pending_action?.error)||Boolean(state&&!done&&!dto?.confirmation));
    const status=busy?"running":cancelled?"cancelled":done?"completed":failed?"error":dto?.confirmation?"awaiting_input":"pending";
    if(busy&&dto?.confirmation)dto={...dto,confirmation:null,availableActions:[],pauseTitle:"已提交，正在执行下一步。"};
    const stored=store.conversations[record.conversationId];
    const start=Date.parse(String(snap?.state.created_at??""))||stored?.createdAt||Date.now();
    const messages=[...(stored?.messages??[])];
    for(const review of snap?.reviews??[]){
     const id=`review-${createHash("sha256").update(review.path).digest("hex").slice(0,20)}`;
     let text=review.text;const outputs=[fileOutput(join(root,record.directory),review.path)];
     for(const [token,path] of Object.entries(review.links??{})){const output=fileOutput(join(root,record.directory),path);text=text.replaceAll(`](${token})`,`](${output.fileUrl})`);outputs.push(output);}
     if(!messages.some(m=>m.id===id)){
      messages.push({id,role:"assistant",timestamp:review.time,content:projectContentProductionMarkdown(text),outputFiles:outputs});
     }
    }
    const outputs=(snap?.files??[]).map(p=>fileOutput(join(root,record.directory),p));
    if(done&&!cancelled&&outputs.length)messages.push({id:`delivery-${state?.revision}`,role:"assistant",timestamp:Date.parse(String(state?.updated_at))||Date.now(),content:"本阶段已完成，交付文件如下。请审阅内容及其事实依据。",outputFiles:outputs});
    if(failed)messages.push({id:`failure-${state?.revision}`,role:"assistant",timestamp:Date.parse(String(state?.updated_at))||start,content:snap?.factGate&&!snap.factGate.publishReady?`事实校验发现 ${snap.factGate.issueCount} 项问题。原稿已保留；请在制作档案中检查分类并启动事实返工。`:"本轮执行已停止。原任务与已有产出已保留；查看运行记录后，可发送“重试当前执行”继续同一任务。"});
    if(!messages.length&&!(snap?.processes?.length))messages.push({id:"local-start",role:"assistant",timestamp:start,content:"已从本机企业资料启动真实工作流。执行记录会随工具调用更新，研究结束后展示待确认内容。"});
    const label=record.input.mode==="single_article"?"问题文章":record.input.mode==="p0"?"品牌深度文章":"品牌资料包";
    const processStatus:ProcessStatus=status==="error"?"failed":status==="pending"?"unknown":status as ProcessStatus;
    const conversationProcesses=bindConversationProcesses(snap?.processes,messages,record.turns??[],processStatus,record.archivedProcesses??[]);
    const latestTurn=record.turns?.at(-1);
    if(latestTurn&&!busy&&latestTurn.status!==processStatus){latestTurn.status=processStatus;persist();}
    const conversation:ContentConversation={id:record.conversationId,title:stored?.title??`${record.input.enterpriseName} · ${label}`,purpose:"content_production",taskId:record.id,status,createdAt:start,updatedAt:Date.parse(String(state?.updated_at))||start,messages:[...new Map(messages.map(m=>[m.id,m])).values()].sort((a,b)=>a.timestamp-b.timestamp),processes:conversationProcesses};
    results.set(record.id,{record,snapshot:snap,conversation,task:{id:record.id,purpose:"content_production",status,contentProduction:dto}});
   }
   return results;
  }
  function launch(record:StoredTask,args:string[]){
   record.error=false;record.cancelled=false;persist();
   const log=openSync(join(privateDir,`command-${randomUUID()}.log`),"wx",0o600);
   const child=spawn(options!.python,["-B",resolve("module/workflows/scripts/run_managed.py"),"--config-dir",resolve(options!.configDir),"--",...args],{stdio:["ignore",log,log],env:{...process.env,PYTHONDONTWRITEBYTECODE:"1",FRONTMIND_PROCESS_SUMMARY_CACHE:join(privateDir,"process-summaries")}});
   closeSync(log);processes.set(record.id,child);cache=undefined;
   let finished=false;const finish=(code:number|null)=>{if(finished)return;finished=true;if(processes.get(record.id)===child)processes.delete(record.id);record.error=code!==0&&!record.cancelled;const turn=record.turns?.at(-1);if(turn){turn.finishedAt=Date.now();turn.status=record.cancelled?"cancelled":code!==0?"failed":"unknown";}persist();cache=undefined;};
   child.on("error",()=>finish(1));child.on("close",finish);
  }
  async function body(req:IncomingMessage,limit=2*1024*1024){const chunks:Buffer[]=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>limit)reject("文件或请求超过允许大小。",413);chunks.push(Buffer.from(chunk));}return Buffer.concat(chunks);}
  const send=(res:ServerResponse,value:unknown,status=200)=>{res.writeHead(status,{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"});res.end(JSON.stringify(value));};
  server.middlewares.use(async(req,res,next)=>{
   const url=new URL(req.url??"/","http://localhost"),path=url.pathname;
   if(!path.startsWith("/api/"))return next();
   try{
    if(!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(req.headers.host??""))reject("仅允许本机访问。",403);
    if(!["GET","HEAD"].includes(req.method??"GET")&&req.headers.origin!==`http://${req.headers.host}`)reject("请从本机工作台提交。",403);
    if(path==="/api/module/context")return send(res,{module:"content",workspace:{id:"local-managed-workflow",ownerUserId:0},marketEdition:"cn",capabilities:["content"]});
    const all=await current();
    if(path==="/api/content/conversations"&&req.method==="GET")return send(res,[...all.values()].map(x=>x.conversation).concat(Object.values(store.conversations).filter(c=>!Object.values(store.tasks).some(t=>t.conversationId===c.id)).map(c=>publicContentConversation(c) as ContentConversation)));
    const conversationMatch=path.match(/^\/api\/content\/conversations\/([-\w]+)$/);
    if(conversationMatch){
     const id=safeId(conversationMatch[1]);
     if(req.method==="DELETE"){const task=[...all.values()].find(x=>x.record.conversationId===id);if(task?.task.status==="running")reject("请先停止任务再移出列表。",409);store.hidden.push(task?.record.id??id);persist();return send(res,{ok:true});}
     if(req.method==="PUT"){
      const value=JSON.parse((await body(req)).toString()) as ContentConversation;if(value.id!==id||!Array.isArray(value.messages))reject("会话格式不正确。");
      const {execution:_,processes:__,...storedValue}=value;
      store.conversations[id]=storedValue;persist();const match=[...(await current()).values()].find(x=>x.record.conversationId===id);return send(res,match?.conversation??storedValue);
     }
    }
    if(path==="/api/frontmind/v2/assets"&&req.method==="POST"){
     const filename=basename(decodeURIComponent(String(req.headers["x-frontmind-filename"]??"material")));if(!filename||filename==="."||filename==="..")reject("文件名无效。");
     const data=await body(req,512*1024*1024),id="asset_"+randomUUID().replaceAll("-","").slice(0,30),folder=join(privateDir,"uploads",id);mkdirSync(folder,{recursive:true,mode:0o700});
     const file=join(folder,filename);writeFileSync(file,data,{mode:0o600});store.assets[id]={path:file,filename};persist();return send(res,{localAssetId:id,filename});
    }
    const artifactMatch=path.match(/^\/api\/frontmind\/v2\/artifacts\/([a-f0-9]+)\/content$/);
    if(artifactMatch&&req.method==="GET"){
     const file=artifacts.get(artifactMatch[1]);if(!file||!contained(root,file.path))reject("交付文件不存在。",404);
     res.writeHead(200,{"Content-Type":mime[extname(file.path)]??"application/octet-stream","Content-Disposition":`inline; filename*=UTF-8''${encodeURIComponent(file.filename)}`,"Content-Security-Policy":"sandbox","X-Content-Type-Options":"nosniff","Cache-Control":"no-store"});createReadStream(file.path).pipe(res);return;
    }
    const taskMatch=path.match(/^\/api\/frontmind\/v2\/tasks(?:\/([-\w]+)(?:\/(messages|stop))?)?$/);
    if(taskMatch){
     const taskId=taskMatch[1],existing=taskId?all.get(taskId):undefined;
     if(taskId&&!existing)reject("任务不存在。",404);
     if(req.method==="GET")return send(res,existing!.task);
     if(req.method==="POST"&&taskMatch[2]==="stop"){
      const child=processes.get(taskId!);if(!child)reject("此任务由命令行运行，请在原执行入口停止。",409);existing!.record.cancelled=true;persist();child.kill("SIGINT");return send(res,{ok:true});
     }
     if(req.method==="POST"){
      const input=JSON.parse((await body(req)).toString()),requestId=safeId(input.clientRequestId),conversationId=safeId(input.conversationId);
      const fingerprint=createHash("sha256").update(JSON.stringify({input,taskId})).digest("hex"),previous=store.requests[requestId];
      if(previous){if(previous.fingerprint!==fingerprint)reject("同一次提交的内容不能变更。",409);const row=(await current()).get(previous.taskId);if(!row)reject("提交已登记，请重新加载任务。",409);return send(res,row.task);}
      const assetIds=input.localAssetIds??[];if(!Array.isArray(assetIds)||assetIds.length>32)reject("附件列表无效。");
      const files=assetIds.map((id:unknown)=>{const file=store.assets[safeId(id)];if(!file)reject("附件不存在。",404);return file.path;});
      let record:StoredTask,args:string[];
      if(existing){
       record=existing.record;if(record.conversationId!==conversationId)reject("任务与会话不匹配。",409);
       if(processes.has(record.id)||existing.task.status==="running")reject("任务正在执行，请等待本轮结果。",409);
       args=["continue","--job-dir",join(root,record.directory)];
       if(input.contentProductionAction){
        const action=contentProductionActionSchema.parse(input.contentProductionAction),dto=existing.task.contentProduction;
        if(action.revision!==dto?.runnerRevision||!dto.availableActions.includes(action.kind))reject("确认已过期，请刷新当前阶段。",409);
        args.push(...localActionArgs(action,dto.workflowStatus??""));
        args.push(...localAttachmentArgs(action,dto.workflowStatus??"",dto.jobKind,files));
       }else if(["error","cancelled"].includes(existing.task.status)&&String(input.prompt).trim()==="重试当前执行")args.push("--retry-current-action");
       else reject("请使用当前阶段的确认或修改控件继续工作流。");
      }else{
       if(Object.values(store.tasks).some(t=>t.conversationId===conversationId))reject("此会话已有任务，请重新加载后继续。",409);
       const config=contentProductionInputSchema.parse(input.contentProduction);if(!files.length)reject("真实任务需要上传企业材料或已确认资料包。");
       const id="task_"+randomUUID().replaceAll("-","");record={id,directory:id,conversationId,input:config};
       const command=config.mode==="new_reference_pack"?["reference-pack","create"]:config.mode==="single_article"?["article"]:config.mode==="p0"?["p0"]:null;
       if(!command)reject("本地真实入口支持新资料包、品牌深度文章和问题文章。");
        args=[...command,"--job-dir",join(root,id),"--brand",config.enterpriseName];for(const file of files)args.push("--input",file);if(config.question)args.push("--question",config.question);if(config.questionId)args.push("--question-id",config.questionId);
        if(config.mode==="single_article"){
         if(config.articleFocus)args.push("--focus",config.articleFocus);
         for(const value of config.readerQuestions??[])args.push("--reader-question",value);
         for(const value of config.excludedTopics??[])args.push("--exclude-topic",value);
         if(config.genre==="industry_roundup")args.push("--genre",config.genre,
          ...(config.subjectScope??[]).flatMap(name=>["--subject",name]),
          ...(config.comparisonDimensions??[]).flatMap(name=>["--dimension",name]));
        }
       store.tasks[id]=record;
      }
      record.archivedProcesses=existing?.conversation.processes?.map(p=>p.status==="awaiting_input"?{...p,status:"completed" as const}:p);
      record.turns?.forEach(turn=>{if(turn.status==="awaiting_input")turn.status="completed";});
      record.turns??=[];record.turns.push({id:"turn-"+requestId,userMessageId:requestId,startedAt:Date.now(),baseline:readConversationProcesses(existing?.snapshot?.processes).map(p=>p.id),summaryBaseline:readConversationProcesses(existing?.snapshot?.processes).flatMap(p=>[...p.thinking,...p.tools].map(r=>r.id)),...(args.includes("--retry-current-action")?{recoverAttemptId:existing?.snapshot?.processes?.findLast(p=>["failed","unknown"].includes(p.status))?.id}:{}),status:"running"});
      store.requests[requestId]={taskId:record.id,fingerprint};persist();launch(record,args);
      return send(res,{id:record.id,purpose:"content_production",status:"running",contentProduction:null},202);
     }
    }
    reject("本地工作流没有此接口。",404);
   }catch(error){const e=error as Error&{status?:number};send(res,{error:{message:e.status?e.message:"本地请求未完成，请检查输入或服务端运行记录。"}},e.status??400);}
  });
 }};
}
