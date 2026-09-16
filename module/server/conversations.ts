import {Router,type Request} from "express";
export interface ContentConversationSnapshot {id:string;purpose?:string;taskId?:string;messages:unknown[];[key:string]:unknown}
export interface ContentConversationStore {
 list(request:Request):Promise<ContentConversationSnapshot[]>;
 save(request:Request,snapshot:ContentConversationSnapshot):Promise<ContentConversationSnapshot>;
 delete(request:Request,id:string):Promise<unknown>;
}
export class ContentConversationAccessError extends Error {status=403;}
/** Scope/owner are fixed by the host; the saved business purpose is authoritative. */
export function assertContentSnapshot(input:ContentConversationSnapshot,existing:ContentConversationSnapshot|undefined) {
 if(input.purpose!=="content_production" || (existing && existing.purpose!=="content_production"))
  throw new ContentConversationAccessError("CONTENT_CONVERSATION_PURPOSE_MISMATCH");
 if(existing?.taskId && input.taskId && existing.taskId!==input.taskId)
  throw new ContentConversationAccessError("CONTENT_CONVERSATION_TASK_MISMATCH");
}
export function createContentConversationRouter(store:ContentConversationStore):Router {
 const router=Router();
 router.get("/conversations",async(req,res)=>{try{res.json((await store.list(req)).filter(item=>item.purpose==="content_production"));}catch(error){res.status(500).json({error:error instanceof Error?error.message:"CONTENT_LIST_FAILED"});}});
 router.put("/conversations/:id",async(req,res)=>{try{
  const snapshot=req.body as ContentConversationSnapshot;
  if(!snapshot||snapshot.id!==req.params.id||!Array.isArray(snapshot.messages))return void res.status(400).json({error:"CONTENT_CONVERSATION_INVALID"});
  const existing=(await store.list(req)).find(item=>item.id===snapshot.id);
  assertContentSnapshot(snapshot,existing);
  res.json(await store.save(req,snapshot));
 }catch(error){res.status(error instanceof ContentConversationAccessError?403:400).json({error:error instanceof Error?error.message:"CONTENT_SAVE_FAILED"});}});
 router.delete("/conversations/:id",async(req,res)=>{try{
  const existing=(await store.list(req)).find(item=>item.id===req.params.id);
  if(!existing)return void res.status(404).json({error:"CONTENT_CONVERSATION_NOT_FOUND"});
  assertContentSnapshot(existing,existing);
  res.json(await store.delete(req,existing.id));
 }catch(error){res.status(error instanceof ContentConversationAccessError?403:400).json({error:error instanceof Error?error.message:"CONTENT_DELETE_FAILED"});}});
 return router;
}
