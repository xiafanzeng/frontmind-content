import {expect,it} from "vitest";
import {contentProductionInputSchema,contentProductionActionSchema} from "../contracts/content-production";
import {publicContentConversation} from "../server/conversations";

const base={mode:"single_article",enterpriseName:"合成企业",knowledgeSource:"files"};
const roundup={...base,genre:"industry_roundup",subjectScope:["合成企业","合成同行甲","合成同行乙"],comparisonDimensions:["温控","噪音"]};
it("保留原有四类任务输入，新增字段按文体严格校验",()=>{
 for(const mode of ["new_reference_pack","refresh_reference_pack","p0","single_article"])
  expect(contentProductionInputSchema.safeParse({...base,mode}).success).toBe(true);
 expect(contentProductionInputSchema.safeParse(roundup).success).toBe(true);
 for(const input of [{...roundup,subjectScope:["合成同行甲","合成企业","合成同行乙"]},{...roundup,comparisonDimensions:["温控","温控"]},{...roundup,mode:"p0"},{...base,subjectScope:roundup.subjectScope},{...base,mode:"p0",articleFocus:"不可丢弃的聚焦"}])
  expect(contentProductionInputSchema.safeParse(input).success).toBe(false);
});
it("事实修复必须携带原修订号与有效事实编号",()=>{
 expect(contentProductionActionSchema.safeParse({kind:"repair_article_facts",revision:0,rejectedClaimIds:["F01"]}).success).toBe(true);
 for(const action of [{kind:"repair_article_facts",revision:0,rejectedClaimIds:["F0"]},{kind:"repair_article_facts",rejectedClaimIds:[]}])
  expect(contentProductionActionSchema.safeParse(action).success).toBe(false);
});
it("保留正式宿主已投影的通用执行记录作为兼容回退",()=>{
 const execution={schemaVersion:1,taskId:"task",coverage:"partial",timeline:[{id:"public-event",turnId:"turn",userSequence:1,timestamp:100,rank:1,kind:"status",status:"running",publicSummary:"正在处理内容任务"}]};
 const snapshot=publicContentConversation({id:"conversation",purpose:"content_production",messages:[],execution});
 expect(snapshot.execution).toEqual(execution);expect(snapshot.processes).toEqual([]);
});
