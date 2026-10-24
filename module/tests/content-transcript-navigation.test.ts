// @vitest-environment jsdom
import {expect,it,vi} from "vitest";
import {contentTranscriptAnchors,navigateContentTranscript} from "../client/content-transcript-navigation";

it("只识别明确阶段，并将回复前的用户消息作为阶段起点",()=>{
  const anchors=contentTranscriptAnchors([
    {id:"u",role:"user",content:"材料",timestamp:1},
    {id:"a",role:"assistant",content:"回复",contentPhase:2,timestamp:2},
    {id:"unknown",role:"assistant",content:"问题文章与资料包",timestamp:3},
  ]);
  expect([...anchors]).toEqual([[2,"u"]]);
});

it("定位当前会话消息；拒绝跨会话，支持返回最新",()=>{
  const viewport=document.createElement("div"),target=document.createElement("article");
  target.dataset.readingAnchor="history";viewport.append(target);
  viewport.getBoundingClientRect=()=>({top:100}) as DOMRect;
  target.getBoundingClientRect=()=>({top:400}) as DOMRect;
  const latest=vi.fn(),scroll=vi.fn();viewport.addEventListener("scroll",scroll);
  expect(navigateContentTranscript(viewport,{conversationId:"other",messageId:"history",sequence:1},"same",latest)).toBe(false);
  expect(viewport.scrollTop).toBe(0);
  expect(navigateContentTranscript(viewport,{conversationId:"same",messageId:"history",sequence:2},"same",latest)).toBe(true);
  expect(viewport.scrollTop).toBe(300);expect(scroll).toHaveBeenCalledTimes(1);
  expect(navigateContentTranscript(viewport,{conversationId:"same",latest:true,sequence:3},"same",latest)).toBe(true);
  expect(latest).toHaveBeenCalledTimes(1);
});
