import type {ContentBusinessClient} from "../module/client/runtime";
import type {ContentConversation,TaskResponse} from "../module/client/host";
export function previewContentClient():ContentBusinessClient {
 let rows:ContentConversation[]=[];
 const clone=<T,>(value:T):T=>structuredClone(value);
 return {async list(){return clone(rows);},async save(value){rows=[clone(value),...rows.filter(row=>row.id!==value.id)];return clone(value);},async remove(id){rows=rows.filter(row=>row.id!==id);},async upload(file){return {fileId:`asset_${crypto.randomUUID().replaceAll("-","").slice(0,30)}`,filename:file.name};},async dispatch(input,taskId){const id=taskId??crypto.randomUUID();const row=rows.find(row=>row.id===input.conversationId);if(row){row.taskId=id;row.status="awaiting_input";row.messages.push({id:crypto.randomUUID(),role:"assistant",content:"这是本地预览任务。已保留输入与附件名称；真实研究、人工确认与成果生成需要在开发子域名执行。",timestamp:Date.now()});}return {id,purpose:"content_production",status:"completed"};},async task(id){return {id,purpose:"content_production",status:"completed",contentProduction:null} satisfies TaskResponse;},async stop(){}};
}
