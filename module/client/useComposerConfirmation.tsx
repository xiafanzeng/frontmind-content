import {useEffect,useRef,useState} from "react";
import type {ContentProductionAction,ContentProductionDto} from "../contracts/content-production";
import {parseContentConfirmationInput,contentConfirmationInputHint} from "./content-confirmation-input";

type Pending={key:string;prompt:string;files:File[];action:ContentProductionAction;resolve:(accepted:boolean)=>void;submitting:boolean};
export function contentConfirmationActionLabel(action:ContentProductionAction):string{
  switch(action.kind){
    case "choose_p0_route":return action.route==="create"?"新建品牌长文":"导入已有品牌长文";
    case "choose_reference_pack_route":return action.route==="create"?"创建品牌资料包":"采用已有品牌资料包";
    case "choose_question":return `选择问题：${action.selection}`;
    case "update_competitor_selection":return "更新比较对象与范围";
    case "choose_core_positioning_direction":return `定位方向：${action.direction}`;
    case "choose_p0_examples":return action.route==="workflow"?"采用工作流写作规范":"采用前二十篇参考例文";
    case "choose_examples":return `文风方案 ${action.route}；保留原输入中的文章池选择`;
    case "confirm_pattern":return action.selectedPattern?`文章类型：${action.selectedPattern}`:"采用本轮推荐的文章类型";
    case "submit_response_brief":return `应答要求：${action.noExtraRequirements?"无额外要求":action.requirements}；品牌认知：${{sufficient:"充分",insufficient:"不充分",uncertain:"不确定"}[action.aiBrandRecognition]}`;
    case "provide_reference_pack_inputs":return "提交企业材料或品牌资料包";
    case "provide_question_research_inputs":return "提交本轮监控问答与引用资料";
    case "confirm_competitors":return "确认当前比较对象";
    case "confirm_core_positioning":return "确认核心定位";
    case "confirm_question_positioning":return "确认本题差异化定位";
    case "confirm_p0_blueprint":return "确认品牌长文写作方案";
    case "confirm_blueprint":return "确认文章写作方案";
    case "revise_current_step":return "按原输入修改当前阶段";
    case "repair_article_facts":return "按事实校验结果返工";
    case "resume_current_execution":return "恢复当前执行";
  }
}
/** 复用聊天输入的发送承诺：确认成功才清草稿，返回修改则保留原文字与附件。 */
export function useComposerConfirmation(key:string|null,progress:ContentProductionDto|null|undefined,onCommit:(prompt:string,files:File[],action:ContentProductionAction)=>Promise<unknown>,onNotice:(text:string)=>void){
  const current=useRef(key);current.current=key;
  const request=useRef<Pending|null>(null);
  const [pending,setPending]=useState<Pending|null>(null);
  const [submitting,setSubmitting]=useState(false);
  function cancel(){const item=request.current;if(!item||item.submitting)return;request.current=null;setPending(null);item.resolve(false);}
  useEffect(()=>{const item=request.current;if(item&&item.key!==key&&!item.submitting){request.current=null;setPending(null);item.resolve(false);}},[key]);
  useEffect(()=>()=>{request.current?.resolve(false);request.current=null;},[]);
  function stage(prompt:string,files:File[]){
    if(!key||!progress||request.current)return Promise.resolve(false);
    const parsed=parseContentConfirmationInput(progress,prompt,files.length);
    if(!parsed.action){onNotice(parsed.hint);return Promise.resolve(false);}
    onNotice("");
    return new Promise<boolean>(resolve=>{const item={key,prompt,files:[...files],action:parsed.action!,resolve,submitting:false};request.current=item;setPending(item);});
  }
  async function confirm(){
    const item=request.current;if(!item||item.submitting)return;
    if(item.key!==current.current){cancel();onNotice("阶段已更新，请重新核对当前问题。");return;}
    item.submitting=true;setSubmitting(true);
    try{
      const accepted=await onCommit(item.prompt,item.files,item.action);
      if(accepted===false)throw new Error("提交未确认成功，请重试。");
      if(request.current===item){request.current=null;setPending(null);item.resolve(true);}
    }catch(error){onNotice(error instanceof Error?error.message:"提交失败，原输入与附件已保留，请重试。");}
    finally{item.submitting=false;setSubmitting(false);if(request.current===item&&item.key!==current.current){request.current=null;setPending(null);item.resolve(false);}}
  }
  return {pending,submitting,stage,confirm,cancel,hint:progress?contentConfirmationInputHint(progress):""};
}
