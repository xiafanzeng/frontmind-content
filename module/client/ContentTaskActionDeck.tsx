import {useEffect,useRef,useState,type ReactNode} from "react";
import {Paperclip,X} from "lucide-react";
import type {ContentProductionAction} from "../contracts/content-production";
import {buildTaskOperationSubmission,type TaskOperationCard,type TaskOperationInput} from "./content-task-operations";
import "./content-task-action-deck.css";

export type PausePanelState="awaiting"|"running"|"stopped"|"failed"|"startup"|"delivered"|"idle";
export type PausePanelHeader={state:PausePanelState;stage:string;title:string;revision?:number|null;pending?:string;next?:string};
export type PauseSubmission={action?:ContentProductionAction;prompt:string};
const stateLabels:Record<PausePanelState,string>={awaiting:"等待你确认",running:"正在执行",stopped:"已停止",failed:"执行失败",startup:"准备开始",delivered:"已交付",idle:"暂无待办"};
const draftPrefix="frontmind-content-pause-draft:";
type Draft={key:string|null;open:string|null;values:Record<string,TaskOperationInput>;restored?:boolean};

function readDraft(key:string|null):Draft{
 if(!key)return {key,open:null,values:{}};
 try{const value=JSON.parse(localStorage.getItem(draftPrefix+key)??"null");if(value&&typeof value==="object"&&value.values&&typeof value.values==="object")return {key,open:typeof value.open==="string"?value.open:null,values:value.values,restored:Object.keys(value.values).length>0};}catch{}
 return {key,open:null,values:{}};
}
/** 提交成功时页面可能已切到别的聊天，只清理提交时所属草稿中的这张卡片。 */
function clearStoredCard(key:string,cardId:string){
 const stored=readDraft(key);delete stored.values[cardId];
 try{if(Object.keys(stored.values).length)localStorage.setItem(draftPrefix+key,JSON.stringify({open:stored.open===cardId?null:stored.open,values:stored.values}));else localStorage.removeItem(draftPrefix+key);}catch{}
}

export default function ContentTaskActionDeck({cards,onSelect,busy,header,results,revision=null,draftScope,draftKey=null,onStop,stopping=false,saving=false}:{cards:TaskOperationCard[];onSelect(card:TaskOperationCard,submission:PauseSubmission,files:File[]):Promise<boolean>|void;busy:boolean;header?:PausePanelHeader;results?:ReactNode;revision?:number|null;draftScope?:string;draftKey?:string|null;onStop?():void;stopping?:boolean;saving?:boolean}) {
 const [draft,setDraft]=useState<Draft>(()=>readDraft(draftKey));
 const [files,setFiles]=useState<Record<string,File[]>>({});
 const [errors,setErrors]=useState<Record<string,string>>({});
 const [collapsed,setCollapsed]=useState(false);
 const picker=useRef<HTMLInputElement>(null),pickerCard=useRef<{id:string;key:string|null}|null>(null);
 const activeKey=useRef(draftKey);activeKey.current=draftKey;
 const previousDraft=useRef<{key:string;scope?:string}|null>(null);
 useEffect(()=>{
  setDraft(previous=>previous.key===draftKey?previous:readDraft(draftKey));setFiles({});setErrors({});
  if(!draftKey)return;
  // 同一聊天推进到新确认版本时清理本页离开的旧草稿；其他窗口的草稿不动。
  const left=previousDraft.current;
  if(left&&left.key!==draftKey&&left.scope===draftScope)try{localStorage.removeItem(draftPrefix+left.key);}catch{}
  previousDraft.current={key:draftKey,scope:draftScope};
 },[draftKey,draftScope]);
 // 草稿只写回它读取时所属的确认版本，切换阶段的同一轮不会串写。
 useEffect(()=>{if(!draft.key||draft.key!==draftKey)return;try{if(draft.open||Object.keys(draft.values).length)localStorage.setItem(draftPrefix+draft.key,JSON.stringify({open:draft.open,values:draft.values}));else localStorage.removeItem(draftPrefix+draft.key);}catch{}},[draft,draftKey]);
 const values=(id:string)=>draft.values[id]??{};
 const update=(id:string,patch:TaskOperationInput)=>{setDraft(previous=>({...previous,values:{...previous.values,[id]:{...previous.values[id],...patch}}}));setErrors(previous=>({...previous,[id]:""}));};
 const toggle=(id:string)=>setDraft(previous=>({...previous,open:previous.open===id?null:id}));
 async function submit(card:TaskOperationCard){
  const chosen=files[card.id]??[],key=draftKey;
  const built=buildTaskOperationSubmission(card,{...values(card.id),fileCount:chosen.length},revision);
  if(built.error){setErrors(previous=>({...previous,[card.id]:built.error!}));return;}
  const accepted=await onSelect(card,{action:built.action,prompt:built.prompt},chosen);
  if(accepted!==true)return;
  if(activeKey.current!==key){if(key)clearStoredCard(key,card.id);return;}
  setDraft(previous=>{const next={...previous.values};delete next[card.id];return {...previous,open:previous.open===card.id?null:previous.open,values:next};});setFiles(previous=>({...previous,[card.id]:[]}));
 }
 const fileList=(card:TaskOperationCard)=>{const chosen=files[card.id]??[];return <div className="cp-pause-files">
  <button type="button" className="cp-pause-attach" disabled={busy} onClick={()=>{pickerCard.current={id:card.id,key:draftKey};picker.current?.click();}}><Paperclip size={13} aria-hidden="true"/>{chosen.length?"继续添加文件":"选择文件"}</button>
  {chosen.map((file,index)=><span key={`${file.name}:${index}`} className="cp-pause-file">{file.name}<button type="button" aria-label={`移除文件：${file.name}`} disabled={busy} onClick={()=>setFiles(previous=>({...previous,[card.id]:chosen.filter((_,i)=>i!==index)}))}><X size={12}/></button></span>)}
  {draft.restored&&!chosen.length&&Object.keys(values(card.id)).length>0&&<small>已恢复上次填写的文字；附件需重新选择。</small>}
 </div>;};
 const form=(card:TaskOperationCard)=>{
  const value=values(card.id),f=card.form!;
  const fields=f.type==="text"?<>
   <label className="cp-pause-field"><span>{f.label}</span><textarea rows={3} value={value.text??""} placeholder={f.placeholder} disabled={busy} onChange={event=>update(card.id,{text:event.target.value})}/></label>
   {f.suggestions&&f.suggestions.length>0&&<div className="cp-pause-chips" aria-label="常用修改">{f.suggestions.map(item=><button type="button" key={item} disabled={busy} onClick={()=>update(card.id,{text:(value.text?.trim()?`${value.text.trim()}\n`:"")+`${item}：`})}>{item}</button>)}</div>}
   {f.attach&&fileList(card)}
  </>:f.type==="upload"?<>
   {fileList(card)}
   {f.note&&<label className="cp-pause-field"><span>资料说明（可选）</span><textarea rows={2} value={value.text??""} placeholder="例如：官网地址、产品重点或需要排除的内容" disabled={busy} onChange={event=>update(card.id,{text:event.target.value})}/></label>}
   {f.hint&&<small className="cp-pause-hint">{f.hint}</small>}
  </>:f.type==="response-brief"?<>
   <fieldset className="cp-pause-fieldset"><legend>企业应答要求</legend>
    <label className="cp-pause-option"><input type="radio" name={`${card.id}-requirements`} checked={value.requirementsMode==="none"} disabled={busy} onChange={()=>update(card.id,{requirementsMode:"none"})}/>无额外要求</label>
    <label className="cp-pause-option"><input type="radio" name={`${card.id}-requirements`} checked={value.requirementsMode==="custom"} disabled={busy} onChange={()=>update(card.id,{requirementsMode:"custom"})}/>有额外要求</label>
    {value.requirementsMode==="custom"&&<textarea rows={3} aria-label="额外应答要求" value={value.requirements??""} placeholder="例如：突出门店服务流程，不提及价格" disabled={busy} onChange={event=>update(card.id,{requirements:event.target.value})}/>}
   </fieldset>
   <fieldset className="cp-pause-fieldset"><legend>回答中的品牌认知</legend>
    {(["sufficient","insufficient","uncertain"] as const).map(item=><label className="cp-pause-option" key={item}><input type="radio" name={`${card.id}-recognition`} checked={value.recognition===item} disabled={busy} onChange={()=>update(card.id,{recognition:item})}/>{{sufficient:"充分",insufficient:"不充分",uncertain:"不确定"}[item]}</label>)}
   </fieldset>
  </>:<>
   <fieldset className="cp-pause-fieldset"><legend>文风方案</legend>
    <label className="cp-pause-option"><input type="radio" name={`${card.id}-route`} checked={value.route==="A"} disabled={busy} onChange={()=>update(card.id,{route:"A"})}/>方案 A · 参考例文的文风</label>
    <label className="cp-pause-option"><input type="radio" name={`${card.id}-route`} checked={value.route==="B"} disabled={busy} onChange={()=>update(card.id,{route:"B"})}/>方案 B · 工作流写作规范</label>
   </fieldset>
   {f.pool&&<fieldset className="cp-pause-fieldset"><legend>文章池构思参考</legend>
    <input type="text" aria-label="文章池编号" value={value.pool??""} placeholder="填写 1—2 个编号，例如：1、5" disabled={busy||value.noPool} onChange={event=>update(card.id,{pool:event.target.value})}/>
    <label className="cp-pause-option"><input type="checkbox" checked={Boolean(value.noPool)} disabled={busy} onChange={event=>update(card.id,{noPool:event.target.checked})}/>不采用文章池参考</label>
   </fieldset>}
  </>;
  return <div className="cp-task-card-input">{fields}{errors[card.id]&&<p className="cp-pause-error" role="alert">{errors[card.id]}</p>}
   <div className="cp-pause-form-actions"><button type="button" className="cp-pause-submit" disabled={busy} onClick={()=>void submit(card)}>{f.type==="text"&&f.submitLabel?f.submitLabel:"核对并提交"}</button><button type="button" className="cp-pause-cancel" disabled={busy} onClick={()=>toggle(card.id)}>收起</button></div>
  </div>;
 };
 const state=header?.state??(cards.length?"awaiting":"idle");
 return <section className="cp-task-deck" data-state={state} aria-label="当前暂停点">
  <header className="cp-pause-head">
   <span className="cp-pause-state">{stateLabels[state]}</span>
   <div className="cp-pause-title">{header?.stage&&<span>{header.stage}</span>}<strong>{header?.title??"当前任务 · 下一步操作"}</strong></div>
   {header?.revision!=null&&<span className="cp-pause-revision" title="提交时会核对这一确认版本">确认版本 {header.revision}</span>}
   {saving&&<span className="cp-pause-saving" role="status">正在保存…</span>}
   {onStop&&state==="running"&&<button type="button" className="cp-pause-stop" disabled={stopping} onClick={onStop}>{stopping?"正在请求停止…":"停止当前执行"}</button>}
   <button type="button" className="cp-pause-collapse" aria-expanded={!collapsed} onClick={()=>setCollapsed(value=>!value)}>{collapsed?"展开":"收起"}</button>
  </header>
  <div className="cp-pause-body" hidden={collapsed}>
   {results&&<div className="cp-pause-results"><span className="cp-pause-label">已有结果</span>{results}</div>}
   {(header?.pending||header?.next)&&<dl className="cp-pause-guide">{header.pending&&<div><dt>{state==="awaiting"?"待确认":"当前情况"}</dt><dd>{header.pending}</dd></div>}{header.next&&<div><dt>{state==="awaiting"?"确认后":"下一步"}</dt><dd>{header.next}</dd></div>}</dl>}
   {cards.length?<div className="cp-task-deck-grid" role="group" aria-label="可选操作">{cards.map(card=>{const open=draft.open===card.id&&Boolean(card.form);return <div key={card.id} className={`cp-task-card cp-task-card-${card.status}`} data-open={open||undefined} data-primary={card.primary||undefined}>
    <button type="button" className="cp-task-card-trigger" aria-expanded={card.form?open:undefined} disabled={busy||card.disabled||card.kind==="view"} onClick={()=>{if(card.form)toggle(card.id);else void onSelect(card,{action:card.action,prompt:card.prompt},[]);}}>
     <strong>{card.title}</strong><span>{card.description}</span>{card.form&&!open&&<small>{card.kind==="upload"?"选择文件":"填写"}</small>}
    </button>
    {open&&form(card)}
   </div>;})}</div>:<p className="cp-task-deck-empty">当前没有待处理操作，系统将根据任务状态更新下一步。</p>}
  </div>
  <input ref={picker} type="file" multiple hidden onChange={event=>{const chosen=Array.from(event.currentTarget.files??[]);const target=pickerCard.current;if(target&&target.key===activeKey.current&&chosen.length)setFiles(previous=>({...previous,[target.id]:[...(previous[target.id]??[]),...chosen]}));event.currentTarget.value="";}}/>
 </section>;
}
