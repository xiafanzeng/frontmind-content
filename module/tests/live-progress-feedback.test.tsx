// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {expect,it} from "vitest";
import ExecutionFeedback from "../client/ExecutionFeedback";
import type {ContentConversation} from "../client/host";
import type {ContentProductionDto} from "../contracts/content-production";

it("反馈随服务端真实步骤变化，保留同一个任务且不按计时猜百分比",async()=>{
 (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
 const container=document.createElement("div"),root=createRoot(container);
 const conversation:ContentConversation={id:"chat",taskId:"original-task",title:"原任务",status:"running",messages:[],createdAt:Date.now(),updatedAt:Date.now()};
 const progress={jobKind:"p0",workflowStatus:"running_p0_production",productionStep:"edit"} as ContentProductionDto;
 try{
  const render=async(value:ContentProductionDto,error=false)=>{await act(async()=>root.render(<ExecutionFeedback conversation={conversation} observation={{taskId:"original-task",checkedAt:Date.now(),contentProduction:value,error}}/>));};
  await render(progress);expect(container.textContent).toContain("正在编辑品牌长文");expect(container.textContent).toContain("状态已同步于");
  await render({...progress,productionStep:"titles"});expect(container.textContent).toContain("正在生成候选标题");expect(container.textContent).not.toContain("正在编辑品牌长文");expect(container.textContent).not.toContain("%");
  await render(progress,true);expect(container.textContent).toContain("当前无法确认服务器进度");expect(container.textContent).not.toContain("正在编辑品牌长文");
 }finally{await act(async()=>root.unmount());}
});
