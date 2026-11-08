import {useContentWorkspaceHost} from "./host";
import { useState } from "react";
import type { ContentProductionAction, ContentProductionDto, ContentProductionMode } from "../contracts/content-production";
import "./two-stage-confirmation.css";

type StartMode = Extract<ContentProductionMode, "new_reference_pack" | "import_reference_pack" | "p0" | "single_article">;
const words = (value: string) => value.split(/[、,，\s]+/u).map(x => x.trim()).filter(Boolean);

export function TwoStageStart({kind,mode,onMode,onStart,busy,onNotice}:{
  kind:"pack"|"article";mode:StartMode;onMode(mode:StartMode):void;
  onStart(prompt:string,files:File[]):Promise<unknown>;busy:boolean;onNotice(text:string):void;
}) {
  const [files,setFiles]=useState<File[]>([]);
  useContentWorkspaceHost().useWorkspaceDraftGuard({dirty:files.length>0,label:"新版工作流输入"});
  async function start() {
    if(kind==="pack"&&(files.length!==1||!files[0].name.toLowerCase().endsWith(".zip")||files[0].size===0||files[0].size>100*1024*1024)){
      onNotice("请选择一个非空 ZIP 文件，大小不超过 100 MiB。");return;
    }
    const prompt=mode==="new_reference_pack"?"按 v16.25.1 整理知识库定位与差异化优势。":mode==="import_reference_pack"?"导入已有三项资料包，沿用已确认定位与优势。":mode==="p0"?"使用当前三项资料包制作 P0 品牌长文。":"使用当前三项资料包进入问题优化写作，P0 不作为前置条件。";
    await onStart(prompt,files);
  }
  return <section className="cp-confirmation cp-two-stage" aria-label="新版工作流入口">
    <strong>v16.25.1 · {kind==="pack"?"定位与差异化优势":"问题优化写作"}</strong>
    <fieldset className="cp-confirmation-fields" disabled={busy}>
      {kind==="pack"?<>
        <label><input type="radio" name="two-stage-start" checked={mode==="new_reference_pack"} onChange={()=>onMode("new_reference_pack")}/> 从 Markdown 知识库整理定位和优势</label>
        <label><input type="radio" name="two-stage-start" checked={mode==="import_reference_pack"} onChange={()=>onMode("import_reference_pack")}/> 导入已有资料包</label>
        <label className="cp-field">{mode==="import_reference_pack"?"三项 Reference Pack ZIP":"完整 Markdown 知识库 ZIP"}
          <input type="file" accept=".zip" aria-label={mode==="import_reference_pack"?"三项资料包 ZIP":"Markdown 知识库 ZIP"} onChange={event=>setFiles(Array.from(event.target.files??[]))}/>
        </label>
        <small>{mode==="import_reference_pack"?"包含定位.md、核心差异化优势.md、知识库.zip；确认后沿用本包内容。":"知识库须包含完整 Markdown 正文；原始 PDF、Word、图片请先整理为知识库。"}</small>
      </>:<>
        <label><input type="radio" name="two-stage-start" checked={mode==="single_article"} onChange={()=>onMode("single_article")}/> 围绕问题写文章</label>
        <label><input type="radio" name="two-stage-start" checked={mode==="p0"} onChange={()=>onMode("p0")}/> 制作 P0 品牌长文</label>
        <small>沿用当前主体已确认的三项资料包。问题文章无需先完成 P0。</small>
      </>}
      <button type="button" className="cp-primary" disabled={busy} onClick={()=>void start().catch(error=>onNotice(error instanceof Error?error.message:"输入提交失败，请重试。"))}>核对本次输入</button>
    </fieldset>
  </section>;
}

export function TwoStageConfirmation({progress,busy,onAction,onNotice}:{
  progress:ContentProductionDto;busy:boolean;
  onAction(action:ContentProductionAction,prompt:string,files?:File[]):Promise<unknown>;
  onNotice(text:string):void;
}) {
  const [selection,setSelection]=useState("");
  const [ordered,setOrdered]=useState(progress.choices.map(x=>x.split("｜")[0]).join("、"));
  const [none,setNone]=useState(false),[instructions,setInstructions]=useState("");
  const [category,setCategory]=useState<""|"行业排名"|"美誉舆情"|"产品场景">("");
  const [pattern,setPattern]=useState<""|"P01"|"P02"|"P03"|"P04"|"P06">("");
  const [subjects,setSubjects]=useState(""),[media,setMedia]=useState("");
  const [files,setFiles]=useState<File[]>([]),[date,setDate]=useState("");
  const [rank,setRank]=useState(""),[pending,setPending]=useState(false);
  useContentWorkspaceHost().useWorkspaceDraftGuard({dirty:Boolean(selection||instructions||files.length||category||pattern||subjects||media||date||rank),label:"新版工作流确认"});
  const revision=progress.runnerRevision??0;
  const disabled=busy||pending||progress.runnerRevision==null;
  const status=progress.confirmation;
  async function send(action:ContentProductionAction,prompt:string,attachments:File[]=[]){
    if(disabled)return;
    setPending(true);onNotice("");
    try{await onAction(action,prompt,attachments);}catch(error){onNotice(error instanceof Error?error.message:"提交失败，请重试。");}
    finally{setPending(false);}
  }
  const upload=<label className="cp-field">本轮文件<input type="file" multiple accept=".xlsx,.csv,.json,.txt,.md" aria-label="本轮文件" onChange={event=>setFiles(Array.from(event.target.files??[]))}/></label>;
  return <section className="cp-confirmation cp-two-stage" aria-label="新版工作流确认">
    <strong>{progress.pauseTitle??"资料包已确认"}</strong>
    <fieldset className="cp-confirmation-fields" disabled={disabled}>
      {!status&&progress.availableActions.includes("revise_advantages")&&<>
        <label className="cp-field">修改或补充已确认优势<textarea aria-label="修改已确认优势" value={instructions} onChange={event=>setInstructions(event.target.value)}/></label>
        <button type="button" className="cp-primary" disabled={disabled||!instructions.trim()} onClick={()=>void send({kind:"revise_advantages",revision,instructions:instructions.trim()},`修改优势并生成新版本：${instructions.trim()}`)}>修改优势并生成新版本</button>
      </>}
      {status==="awaiting_positioning_selection"&&<>
        {progress.choices.map(choice=><label key={choice}><input type="radio" name="positioning" checked={selection===choice.split("｜")[0]} onChange={()=>setSelection(choice.split("｜")[0])}/>{choice}</label>)}
        <button type="button" className="cp-primary" disabled={disabled||!selection} onClick={()=>void send({kind:"choose_positioning",revision,categoryId:selection,note:`用户选择定位：${selection}`},`我选择定位 ${selection}。`)}>确认所选定位</button>
      </>}
      {status==="awaiting_advantages_confirmation"&&<>
        <p>{progress.choices.join("；")}</p>
        <label className="cp-field">保留的优势编号与顺序<input aria-label="优势顺序" value={ordered} onChange={event=>setOrdered(event.target.value)} placeholder="adv2、adv1、adv3"/></label>
        <label><input type="checkbox" checked={none} onChange={event=>setNone(event.target.checked)}/> 本次暂无单独优势</label>
        <button type="button" className="cp-primary" disabled={disabled||(!none&&!words(ordered).length)} onClick={()=>void send({kind:"confirm_advantages",revision,advantageIds:none?[]:words(ordered),none,note:none?"用户明确本次暂无优势":`用户确认优势及顺序：${ordered}`},none?"本次暂无单独优势。":`确认优势及顺序：${ordered}`)}>确认优势与顺序</button>
        <label className="cp-field">修改或补充优势<textarea aria-label="修改或补充优势" value={instructions} onChange={event=>setInstructions(event.target.value)}/></label>
        <button type="button" className="cp-secondary" disabled={disabled||!instructions.trim()} onClick={()=>void send({kind:"revise_advantages",revision,instructions:instructions.trim()},`修改优势：${instructions.trim()}`)}>修改草案后重新查看</button>
      </>}
      {status==="awaiting_question_selection"&&<>
        {progress.choices.length>0&&<p>{progress.choices.join("；")}</p>}
        <label className="cp-field">问题编号或完整新问题<input aria-label="问题编号或完整新问题" value={selection} onChange={event=>setSelection(event.target.value)}/></label>
        <button type="button" className="cp-primary" disabled={disabled||!selection.trim()} onClick={()=>void send({kind:"choose_question",revision,selection:selection.trim()},`选择问题：${selection.trim()}`)}>采用此问题</button>
      </>}
      {status==="awaiting_question_answers"&&<>
        {upload}<label className="cp-field">回答日期（可选）<input type="date" value={date} onChange={event=>setDate(event.target.value)}/></label>
        <button type="button" className="cp-primary" disabled={disabled||!files.length} onClick={()=>void send({kind:"set_question_answers",revision,noAnswers:false,...(date?{answerDate:date}:{})},"关联本题完整回答。",files)}>关联完整回答</button>
        <button type="button" className="cp-secondary" disabled={disabled} onClick={()=>void send({kind:"set_question_answers",revision,noAnswers:true,note:"用户明确本次暂无回答"},"本次暂无回答，继续关联本题信源。")}>本次暂无回答</button>
      </>}
      {status==="awaiting_question_sources"&&<>
        {upload}<label className="cp-field">信源日期（可选）<input type="date" value={date} onChange={event=>setDate(event.target.value)}/></label>
        <button type="button" className="cp-primary" disabled={disabled||!files.length} onClick={()=>void send({kind:"provide_question_sources",revision,...(date?{sourceDate:date}:{})},"关联本题逐条信源，展示媒体统计与 Top20 文章。",files)}>关联本题逐条信源</button>
      </>}
      {status==="awaiting_writing_selection"&&<>
        <label className="cp-field">问题类型<select aria-label="问题类型" value={category} onChange={event=>setCategory(event.target.value as typeof category)}><option value="">请选择</option>{["行业排名","美誉舆情","产品场景"].map(value=><option key={value}>{value}</option>)}</select></label>
        <label className="cp-field">文章模式<select aria-label="文章模式" value={pattern} onChange={event=>setPattern(event.target.value as typeof pattern)}><option value="">请选择</option>{[["P01","单品牌推荐"],["P02","多品牌分别介绍"],["P03","场景说明"],["P04","真实事件新闻"],["P06","评价回应"]].map(([value,label])=><option key={value} value={value}>{value} · {label}</option>)}</select></label>
        {pattern==="P02"&&<label className="cp-field">本篇其他主体编号与顺序<input aria-label="本篇其他主体" value={subjects} onChange={event=>setSubjects(event.target.value)} placeholder="从已展示的确认同类池选择，如 c001、c003"/></label>}
        <label className="cp-field">指定纳入的信源（可选）<input value={media} onChange={event=>setMedia(event.target.value)} placeholder="填写实际指定的渠道，如抖音"/></label>
        <button type="button" className="cp-primary" disabled={disabled||!category||!pattern||(pattern==="P02"&&!words(subjects).length)} onClick={()=>{if(!category||!pattern)return;const note=`用户选择${category}、${pattern}；其他主体：${subjects||"无"}；指定信源：${media||"无"}`;void send({kind:"choose_writing",revision,category,pattern,subjects:pattern==="P02"?words(subjects):[],requiredMedia:words(media),note},note);}}>确认类型、模式与主体</button>
      </>}
      {status==="awaiting_reference_fulltext"&&<>
        <p>{progress.choices.join("；")}</p>{upload}
        <label className="cp-field">对应引用排名<input type="number" min="1" max="500" value={rank} onChange={event=>setRank(event.target.value)}/></label>
        <button type="button" className="cp-primary" disabled={disabled||files.length!==1||!Number.isInteger(Number(rank))||Number(rank)<1} onClick={()=>void send({kind:"provide_reference_fulltext",revision,rank:Number(rank)},`补充第 ${rank} 篇参考文章完整原文。`,files)}>补充完整原文</button>
      </>}
      {(status==="awaiting_article_task_confirmation"||status==="awaiting_writing_brief_confirmation")&&<button type="button" className="cp-primary" disabled={disabled} onClick={()=>void send({kind:status==="awaiting_article_task_confirmation"?"confirm_article_task":"confirm_writing_brief",revision,note:status==="awaiting_article_task_confirmation"?"用户确认本篇任务":"用户确认本篇约稿"},status==="awaiting_article_task_confirmation"?"确认本篇写作任务。":"确认本篇简要约稿并开始写作。")}>确认当前内容</button>}
    </fieldset>
  </section>;
}
