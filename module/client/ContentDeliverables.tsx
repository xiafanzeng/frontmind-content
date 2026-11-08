import {contentOutputIdentity,useContentWorkspaceHost,type ContentOutputFile} from "./host";
import "./content-deliverables.css";

export default function ContentDeliverables({files}:{files:readonly ContentOutputFile[]}){
  const {FilePreview}=useContentWorkspaceHost();
  const unique=[...new Map(files.map(file=>[contentOutputIdentity(file),file])).values()];
  return <section className="cp-subject-deliverables" aria-label="交付文件">
    <header><h2>交付文件</h2><span>{unique.length} 份</span></header>
    {unique.length?<div className="cp-subject-deliverable-list">{unique.map(file=><FilePreview key={contentOutputIdentity(file)} file={{id:file.fileUrl,type:"file",name:file.fileName,blobUrl:file.fileUrl}}/>)}</div>
      :<div className="cp-subject-deliverable-empty"><p>暂无交付文件</p><small>资料包或文章生成后会显示在这里。</small></div>}
  </section>;
}
