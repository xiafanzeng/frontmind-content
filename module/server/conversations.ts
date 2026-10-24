import {Router,type Request,type Response} from "express";
import { ZodError } from "zod";
import { ContentSubjectWorkspaceHttpError } from "./subject-workspace";
import {readConversationProcesses} from "../contracts/conversation-process";
import {projectContentExecutionLanguage} from "../contracts/content-execution-language";
import type {GeneralExecutionDto} from "@frontmind/module-contracts/execution";
export interface ContentConversationSnapshot {id:string;purpose?:string;taskId?:string;messages:unknown[];[key:string]:unknown}
export interface ContentConversationStore {
 list(request:Request):Promise<ContentConversationSnapshot[]>;
 save(request:Request,snapshot:ContentConversationSnapshot):Promise<ContentConversationSnapshot>;
 delete(request:Request,id:string):Promise<unknown>;
}
export class ContentConversationAccessError extends Error {status=403;}
function sendConversationFailure(response:Response,error:unknown) {
 if(error instanceof ContentConversationAccessError){response.status(403).json({error:error.message});return;}
 if(error instanceof ContentSubjectWorkspaceHttpError){response.status(error.status).json({error:{code:error.code,message:error.message}});return;}
 if(error instanceof ZodError){response.status(400).json({error:"聊天数据格式无效，请检查后重试。"});return;}
 // 私有 Core 的已知业务错误保留精确状态；MySQL/网络错误不透传内部信息。
 const businessStatuses:Record<string,number>={BAD_REQUEST:400,UNAUTHORIZED:401,FORBIDDEN:403,NOT_FOUND:404,CONFLICT:409,PAYLOAD_TOO_LARGE:413};
 const code=error instanceof Error&&"code" in error&&typeof error.code==="string"?error.code:"";
 if(Object.hasOwn(businessStatuses,code)){response.status(businessStatuses[code]).json({error:{code,message:error instanceof Error?error.message:"聊天请求未通过校验。"}});return;}
 response.status(503).json({error:{code:"CONTENT_CONVERSATION_UNAVAILABLE",message:"聊天服务暂时不可用，请刷新确认保存状态，勿重复提交。"}});
}
/** Scope/owner are fixed by the host; the saved business purpose is authoritative. */
export function assertContentSnapshot(input:ContentConversationSnapshot,existing:ContentConversationSnapshot|undefined) {
 if(input.purpose!=="content_production" || (existing && existing.purpose!=="content_production"))
  throw new ContentConversationAccessError("CONTENT_CONVERSATION_PURPOSE_MISMATCH");
 if(existing?.taskId && input.taskId && existing.taskId!==input.taskId)
  throw new ContentConversationAccessError("CONTENT_CONVERSATION_TASK_MISMATCH");
}
/** Core adapters must provide the same backend summary projection. Existing general execution data remains available as a compatibility fallback. */
export function publicContentConversation(snapshot:ContentConversationSnapshot):ContentConversationSnapshot {
 const {execution,processes,...business}=snapshot;
 // Core already projects public execution fields. Reject malformed legacy data,
 // while retaining the existing live display when no native summary is present.
 const candidate=execution as {schemaVersion?:number;timeline?:unknown[]}|undefined;
 const fallback=candidate?.schemaVersion===1&&Array.isArray(candidate.timeline)?candidate:undefined;
 return {...business,...(fallback?{execution:projectContentExecutionLanguage(fallback as GeneralExecutionDto)}:{}),processes:readConversationProcesses(processes)};
}

export function createContentConversationRouter(store:ContentConversationStore):Router {
 const router=Router();
 router.get("/conversations",async(req,res)=>{try{res.json((await store.list(req)).filter(item=>item.purpose==="content_production").map(publicContentConversation));}catch(error){sendConversationFailure(res,error);}});
 router.put("/conversations/:id",async(req,res)=>{try{
  const snapshot=req.body as ContentConversationSnapshot;
  if(!snapshot||snapshot.id!==req.params.id||!Array.isArray(snapshot.messages))return void res.status(400).json({error:"CONTENT_CONVERSATION_INVALID"});
  const existing=(await store.list(req)).find(item=>item.id===snapshot.id);
  assertContentSnapshot(snapshot,existing);
  const {processes:__,...business}=snapshot;
  res.json(publicContentConversation(await store.save(req,{...business,processes:existing?.processes??[]})));
 }catch(error){sendConversationFailure(res,error);}});
 router.delete("/conversations/:id",async(req,res)=>{try{
  const existing=(await store.list(req)).find(item=>item.id===req.params.id);
  if(!existing)return void res.status(404).json({error:"CONTENT_CONVERSATION_NOT_FOUND"});
  assertContentSnapshot(existing,existing);
  res.json(await store.delete(req,existing.id));
 }catch(error){sendConversationFailure(res,error);}});
 return router;
}
