import {ModuleShell} from "@frontmind/module-ui/dashboard/ModuleShell";
import {CONTENT_MODULE_LABEL} from "../module/client/module-label";
import {useEffect,useMemo,useState} from "react";
import {ModuleWorkspace,liveContentClient,type ContentBusinessClient,type ModuleContext} from "../module/client/runtime";
import {createIntakeVerificationClient,intakeVerificationRequested} from "../module/client/intake-verification-client";
import {previewContentClient} from "./preview";
export default function App({preview=false,localWorkflow=false}:{preview?:boolean;localWorkflow?:boolean}) {
 const verifyIntake=useMemo(()=>intakeVerificationRequested(location.search),[]);
 const [verificationClient,setVerificationClient]=useState<ContentBusinessClient|null>(null);
 const [context,setContext]=useState<ModuleContext|null>(preview?{module:"content",workspace:{id:"local-preview",ownerUserId:0},marketEdition:"cn",capabilities:["content"]}:null),[error,setError]=useState("");
 const normalClient=useMemo(()=>preview?previewContentClient():liveContentClient,[preview]);
 const client=verifyIntake?verificationClient:normalClient;
 useEffect(()=>{if(!["/","/content","/content-production"].includes(location.pathname))history.replaceState(null,"",verifyIntake?`/${location.search}${location.hash}`:"/");if(preview){if(verifyIntake)setError("演示页不能验证真实收件，请打开正式内容工作区。");return;}const controller=new AbortController();const contextRequest=fetch("/api/module/context",{signal:controller.signal,credentials:"same-origin"}).then(async response=>{if(!response.ok)throw new Error("无法取得内容工作区，请重新验证开发门禁");return response.json();});void Promise.all([contextRequest,verifyIntake?createIntakeVerificationClient(liveContentClient,{signal:controller.signal}):Promise.resolve(null)]).then(([value,verified])=>{if(value.module!=="content"||!value.workspace?.id)throw new Error("内容模块上下文不匹配");if(verifyIntake)setVerificationClient(verified);setContext(value);}).catch(error=>{if(!controller.signal.aborted)setError(error.message);});return()=>controller.abort();},[preview,verifyIntake]);
 return <ModuleShell module={{id:"content",label:CONTENT_MODULE_LABEL,color:"#8a6100"}} views={[{id:"content",label:"内容工作台"}]} activeView="content" onSelectView={()=>{}} preview={preview} showViewTabs={false}>{localWorkflow&&!verifyIntake&&<div className="cp-live-notice" role="status">真实工作流 · 模型调用计费 · 任务与文件保存在本机</div>}{error?<p role="alert">{error}</p>:context&&client?<><div className="cp-local-workspace"><ModuleWorkspace context={context} client={client}/></div></>:<p role="status">正在进入内容工作区…</p>}</ModuleShell>;
}
