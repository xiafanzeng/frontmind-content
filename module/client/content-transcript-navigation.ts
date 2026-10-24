import {contentProductionFilePhase} from "../contracts/content-production-public";
import type {ContentMessage,ContentTranscriptNavigation} from "./host";

/** 只使用明确的阶段标记或工作流原生输出文件名；不猜测客户正文属于哪个阶段。 */
export function contentTranscriptAnchors(messages:readonly ContentMessage[]) {
  const anchors=new Map<number,string>();
  for(let index=0;index<messages.length;index++){
    const message=messages[index];
    const explicit=message.contentPhase;
    const fromFiles=(message.outputFiles??[]).map(file=>contentProductionFilePhase(file.fileName)).filter((phase):phase is number=>phase!==null);
    const phase=typeof explicit==="number"&&Number.isInteger(explicit)&&explicit>=0&&explicit<6 ? explicit : fromFiles.length ? Math.max(...fromFiles) : null;
    if(phase===null||anchors.has(phase))continue;
    const preceding=messages[index-1];
    const start=message.role==="assistant"&&preceding?.role==="user" ? preceding.id : message.id;
    anchors.set(phase,start);
  }
  return anchors;
}

/** 定位聊天历史，不隐藏消息、不改任务状态，也不发送任何业务请求。 */
export function navigateContentTranscript(viewport:HTMLElement,request:ContentTranscriptNavigation,conversationId:string,latest:()=>void){
  if(request.conversationId!==conversationId)return false;
  if(request.latest){latest();return true;}
  const target=Array.from(viewport.querySelectorAll<HTMLElement>("[data-reading-anchor]")).find(node=>node.dataset.readingAnchor===request.messageId);
  if(!target)return false;
  // 告知既有阅读位置管理：这是一次主动回看，停止自动跟随最新消息。
  viewport.dispatchEvent(new Event("wheel"));
  viewport.scrollTop+=target.getBoundingClientRect().top-viewport.getBoundingClientRect().top;
  viewport.dispatchEvent(new Event("scroll"));
  return true;
}
