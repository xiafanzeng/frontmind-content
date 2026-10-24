import { Router, type Request } from "express";
import type { MySql2Database } from "drizzle-orm/mysql2";
import { createContentConversationRouter, type ContentConversationStore } from "./conversations";
import {
 createContentSubjectWorkspaceRouter, ContentSubjectWorkspaceHttpError,
 type ContentSubjectWorkspaceStore,
} from "./subject-workspace";

export interface ContentIntakeStore {
 /** 必须严格校验、幂等持久化并返回真实收件回执，不能在此接口调度生成。 */
 accept(request:Request,input:unknown):Promise<unknown>;
}
export interface ContentHttpBusinessPorts {
 subjectWorkspace:ContentSubjectWorkspaceStore;
 conversations:ContentConversationStore;
 intake:ContentIntakeStore;
 /** 本机验收由宿主显式开启；前端据此关闭所有生成入口。 */
 intakeOnly:boolean;
}

/** Supplied by the host after authentication; never derive ownership from request data. */
export interface ModuleHttpCore {
 context(request:Request):{accountUserId:number;actorUserId:number;enterpriseProjectId:string|null;businessOwnerId:string;businessActorId:string};
 database():Promise<MySql2Database<any>>;
 /** Server-only runtime settings. Never return this object or secret values to the browser. */
 environment:Readonly<Record<string,string|undefined>>;
 /** 由真实 Core 装配，不提供内存、文件或浏览器缓存回退。 */
 content?:ContentHttpBusinessPorts;
}

/** Add new module-owned APIs here. Mounted in both Dashboard and the development subdomain. */
export function createModuleHttpApi(core:ModuleHttpCore):Router {
 const router=Router();
 router.get("/capabilities",(req,res)=>{
  const context=core.context(req);
  res.setHeader("Cache-Control","no-store");
  res.json({module:"content",apiVersion:1,workspaceId:context.enterpriseProjectId,
   intakeOnly:core.content?.intakeOnly??false,
   features:["tasks", "confirmation", "recovery", "artifacts",...(core.content?["subject_workspace","conversations","intake"]:[])]});
 });
 if(core.content){
  const ports=core.content;
  // 先验证宿主已绑定的请求身份，再进入模块端口；浏览器字段不建立身份。
  router.use((request,response,next)=>{
   try{core.context(request);next();}
   catch{response.status(401).json({error:{code:"CONTENT_AUTH_REQUIRED",message:"请先登录内容制作工作台。"}});}
  });
  router.use(createContentSubjectWorkspaceRouter(ports.subjectWorkspace));
  router.use(createContentConversationRouter(ports.conversations));
  router.post("/intake",async(request,response)=>{
   response.setHeader("Cache-Control","no-store");
   try{response.json(await ports.intake.accept(request,request.body));}
   catch(error){
    if(error instanceof ContentSubjectWorkspaceHttpError){
     response.status(error.status).json({error:{code:error.code,message:error.message}});
    }else{
     // 不暴露底层数据库错误；提交结果未知时不能诱导客户再次提交。
     response.status(503).json({error:{code:"CONTENT_INTAKE_UNCONFIRMED",message:"收件状态暂未确认，请刷新查看记录，勿重复提交。"}});
    }
   }
  });
 }
 return router;
}
