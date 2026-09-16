import {ModuleShell} from "@frontmind/module-ui/dashboard/ModuleShell";
import {CONTENT_MODULE_LABEL} from "../module/client/module-label";
import {useEffect,useMemo,useState} from "react";
import {ModuleWorkspace,liveContentClient,type ModuleContext} from "../module/client/runtime";
import {previewContentClient} from "./preview";
export default function App({preview=false}:{preview?:boolean}) {
 const [context,setContext]=useState<ModuleContext|null>(preview?{module:"content",workspace:{id:"local-preview",ownerUserId:0},marketEdition:"cn",capabilities:["content"]}:null),[error,setError]=useState("");
 const client=useMemo(()=>preview?previewContentClient():liveContentClient,[preview]);
 useEffect(()=>{if(!["/","/content","/content-production"].includes(location.pathname))history.replaceState(null,"","/");if(preview)return;const controller=new AbortController();void fetch("/api/module/context",{signal:controller.signal,credentials:"same-origin"}).then(async response=>{if(!response.ok)throw new Error("无法取得内容工作区，请重新验证开发门禁");return response.json();}).then(value=>{if(value.module!=="content"||!value.workspace?.id)throw new Error("内容模块上下文不匹配");setContext(value);}).catch(error=>{if(!controller.signal.aborted)setError(error.message);});return()=>controller.abort();},[preview]);
 return <ModuleShell module={{id:"content",label:CONTENT_MODULE_LABEL,color:"#8a6100"}} views={[{id:"content",label:"内容工作台"}]} activeView="content" onSelectView={()=>{}} preview={preview} showViewTabs={false}>{error?<p role="alert">{error}</p>:context?<ModuleWorkspace context={context} client={client}/>:<p role="status">正在进入内容工作区…</p>}</ModuleShell>;
}
