// 使用真实内容后端的会话/附件存储；本地桥只接收提交，禁止调用执行器。
import {liveContentClient,type ContentBusinessClient} from '../module/client/runtime';
import type {ContentSubjectWorkspace} from '../module/contracts/content-subject-workspace';

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
 const response=await fetch(path,{credentials:'same-origin',...init});
 const value=await response.json();
 if(!response.ok)throw new Error(value.error?.message??value.message??value.error??`HTTP ${response.status}`);
 return value;
}
export const realIntakeClient:ContentBusinessClient={
 ...liveContentClient,
 save:value=>request(`/api/content/drafts/${encodeURIComponent(value.id)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}),
 readSubjectWorkspace:()=>request<ContentSubjectWorkspace>('/api/content/subject-workspace'),
 saveSubjectWorkspace:value=>request<ContentSubjectWorkspace>('/api/content/subject-workspace',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}),
 submitIntake:value=>request('/api/content/intake',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}),
 dispatch:async()=>{throw new Error('当前仅验证真实收件，生成入口已禁用。');},
 stop:async()=>{throw new Error('本轮没有启动执行任务。');},
};
