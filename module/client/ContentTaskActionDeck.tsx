import {useRef,useState} from "react";
import type {TaskOperationCard} from "./content-task-operations";
import "./content-task-action-deck.css";

export default function ContentTaskActionDeck({cards,onSelect,busy}:{cards:TaskOperationCard[];onSelect(card:TaskOperationCard,files?:File[],instructions?:string):void;busy:boolean}) {
 const input=useRef<HTMLInputElement>(null),selected=useRef<TaskOperationCard|null>(null);
 const [expandedInput,setExpandedInput]=useState<string|null>(null),[instructions,setInstructions]=useState("");
 if(!cards.length)return <section className="cp-task-deck" aria-label="当前任务操作"><p className="cp-task-deck-empty">当前没有待处理操作，系统将根据任务状态更新下一步。</p></section>;
 return <section className="cp-task-deck" aria-label="当前任务操作">
  <header><strong>当前任务 · 下一步操作</strong><span>根据当前任务状态更新</span></header>
  <div className="cp-task-deck-grid">{cards.map(card=><div key={card.id} className={`cp-task-card cp-task-card-${card.status}`}>
   <button type="button" className="cp-task-card-trigger" disabled={busy||card.disabled||(!card.prompt&&card.kind!=="upload"&&card.kind!=="input")} onClick={()=>{if(card.kind==="upload"){selected.current=card;input.current?.click();}else if(card.kind==="input"){setExpandedInput(expandedInput===card.id?null:card.id);setInstructions("");}else onSelect(card);}}>
    <strong>{card.title}</strong><span>{card.description}</span>{card.status==="awaiting-confirm"&&<small>待确认</small>}
   </button>
   {card.kind==="input"&&expandedInput===card.id&&<div className="cp-task-card-input"><textarea rows={2} value={instructions} placeholder={card.params?.inputPlaceholder??"请输入修改要求"} onChange={event=>setInstructions(event.target.value)}/><button type="button" disabled={!instructions.trim()||busy} onClick={()=>{onSelect(card,[],instructions);setExpandedInput(null);}}>提交修改</button></div>}
  </div>)}</div>
  <input ref={input} type="file" multiple hidden onChange={event=>{const files=Array.from(event.currentTarget.files??[]);if(selected.current&&files.length)onSelect(selected.current,files);event.currentTarget.value="";}}/>
 </section>;
}
