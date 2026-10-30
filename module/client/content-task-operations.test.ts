import {describe,it,expect} from "vitest";
import {mapContentTaskOperations} from "./content-task-operations";
import type {ContentProductionDto} from "../contracts/content-production";

const progress=(patch:Partial<ContentProductionDto>={}):ContentProductionDto=>({
 mode:"production",workflowStatus:"positioning_ready",executionStatus:"awaiting_input",failureCode:null,currentStage:null,jobKind:"reference_pack",runnerRevision:3,pauseTitle:null,choices:[],productionStep:null,factGate:null,confirmation:null,progressPosition:null,completedConfirmations:[],availableActions:["confirm_core_positioning"],knowledgeBase:null,source:"runner_job_state",...patch
} as ContentProductionDto);

describe("mapContentTaskOperations",()=>{
 it("maps available actions to revision-bound cards",()=>{const cards=mapContentTaskOperations(progress());expect(cards[0].action).toEqual({kind:"confirm_core_positioning",revision:3});});
 it("prioritizes running state over selectable actions",()=>{const cards=mapContentTaskOperations(progress({executionStatus:"running",workflowStatus:"running_core_positioning_synthesis"}));expect(cards[0].status).toBe("running");});
 it("builds a parameter card for revise_current_step",()=>{const cards=mapContentTaskOperations(progress({confirmation:"awaiting_blueprint_confirmation",availableActions:["revise_current_step"]}));expect(cards[0]).toMatchObject({id:"revise-current-step",kind:"input",params:{inputPlaceholder:"请描述希望修改的内容"}});});
 it("offers both existing and new reference pack routes",()=>{const cards=mapContentTaskOperations(progress({confirmation:"awaiting_reference_pack_route",availableActions:["choose_reference_pack_route"]}));expect(cards.map(card=>card.action)).toEqual([{kind:"choose_reference_pack_route",revision:3,route:"use"},{kind:"choose_reference_pack_route",revision:3,route:"create"}]);});
 it("keeps stageIndex and kind on retry and running cards",()=>{const retry=mapContentTaskOperations(progress(),{failed:true})[0];const running=mapContentTaskOperations(progress({executionStatus:"running"}))[0];expect(retry).toMatchObject({stageIndex:0,kind:"action"});expect(running).toMatchObject({stageIndex:0,kind:"view"});});
 it("maps server-provided question choices without inventing options",()=>{const cards=mapContentTaskOperations(progress({availableActions:["choose_question"],choices:["1. 问题甲","2. 问题乙"]}));expect(cards.map(card=>card.prompt)).toEqual(["选择问题：问题甲","选择问题：问题乙"]);});
});
