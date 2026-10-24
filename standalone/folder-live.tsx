import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ModuleShell} from '@frontmind/module-ui/dashboard/ModuleShell';
import {ModuleWorkspace,type ModuleContext} from '../module/client/runtime';
import {realIntakeClient} from './real-intake-client';
import './base.css';

function App(){
 const [context,setContext]=useState<ModuleContext|null>(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();void fetch('/api/module/context',{signal:controller.signal}).then(async response=>{if(!response.ok)throw new Error('真实后端连接失败');const value=await response.json();if(value.module!=='content'||!value.workspace?.id)throw new Error('内容后端工作区不匹配');const selected=new URLSearchParams(location.search).get('conversation');if(selected&&/^[a-zA-Z0-9_-]{1,128}$/.test(selected))localStorage.setItem('frontmind-content-active:'+value.workspace.id,selected);setContext(value);}).catch(error=>{if(!controller.signal.aborted)setError(error.message);});return()=>controller.abort();},[]);
 return <ModuleShell module={{id:'content',label:'内容制作',color:'#8a6100'}} views={[{id:'content',label:'内容工作台'}]} activeView="content" onSelectView={()=>{}} showViewTabs={false}>
  <div className="cp-live-notice" role="status">真实内容后端 · 仅收件，生成入口已关闭</div>
  {error?<p role="alert">{error}</p>:context?<div className="cp-local-workspace"><ModuleWorkspace context={context} client={realIntakeClient}/></div>:<p role="status">正在连接真实内容后端…</p>}
 </ModuleShell>;
}
createRoot(document.getElementById('root')!).render(<App/>);
