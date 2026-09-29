import { Router, type Request } from "express";
import type { MySql2Database } from "drizzle-orm/mysql2";

/** Supplied by the host after authentication; never derive ownership from request data. */
export interface ModuleHttpCore {
 context(request:Request):{accountUserId:number;actorUserId:number;enterpriseProjectId:string|null;businessOwnerId:string;businessActorId:string};
 database():Promise<MySql2Database<any>>;
 /** Server-only runtime settings. Never return this object or secret values to the browser. */
 environment:Readonly<Record<string,string|undefined>>;
}

/** Add new module-owned APIs here. Mounted in both Dashboard and the development subdomain. */
export function createModuleHttpApi(core:ModuleHttpCore):Router {
 const router=Router();
 router.get("/capabilities",(req,res)=>{
  const context=core.context(req);
  res.setHeader("Cache-Control","no-store");
  res.json({module:"content",apiVersion:1,workspaceId:context.enterpriseProjectId,
   features:["tasks", "confirmation", "recovery", "artifacts"]});
 });
 return router;
}
