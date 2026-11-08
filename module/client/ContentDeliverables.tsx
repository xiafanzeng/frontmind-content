import {contentOutputIdentity,useContentWorkspaceHost,type ContentMessage,type ContentOutputFile} from "./host";
import "./content-deliverables.css";

const packName = /(?:^|[_. -])(?:reference[_ -]pack|品牌资料包)(?:[_ -]p0)?(?:[_ -](?:v|r)?(\d+))?\.zip$/iu;
const articleName = /(?:^|[_. -])(?:(p0(?:[_ -]brand[_ -]article|[_ -]?正文)?|品牌深度文章|品牌长文)|article|^正文|问题文章|问题\d+[_ -]?正文)(?:[_ -](?:v|r)?(\d+))?\.(docx|md|html|txt)$/iu;
const articleFormats = ["txt","html","md","docx"];

function selectDeliverables(messages:readonly ContentMessage[]){
  let pack:{file:ContentOutputFile;version:number}|undefined;
  const articles=new Map<string,{file:ContentOutputFile;rank:number}>();
  const seen=new Set<string>();

  for(const message of messages){
    if(message.role!=="assistant")continue;
    for(const file of message.outputFiles??[]){
      const identity=contentOutputIdentity(file);
      if(seen.has(identity))continue;
      seen.add(identity);

      const name=file.fileName.split(/[\\/]/u).at(-1)??file.fileName;
      const packMatch=packName.exec(name);
      if(packMatch){
        const version=Number(packMatch[1]??1);
        if(!pack||version>=pack.version)pack={file,version};
        continue;
      }

      const articleMatch=articleName.exec(name);
      if(!articleMatch)continue;
      const [,p0,revision,extension]=articleMatch;
      const key=JSON.stringify([message.generalChat?.turnId??message.id,p0?"p0":"article",Number(revision??1)]);
      const rank=articleFormats.indexOf(extension.toLowerCase());
      const previous=articles.get(key);
      if(!previous||rank>=previous.rank)articles.set(key,{file,rank});
    }
  }

  const article=[...articles.values()].at(-1);
  const selected:ContentOutputFile[]=[];
  if(pack)selected.push(pack.file);
  if(article)selected.push(article.file);
  return selected;
}

export default function ContentDeliverables({messages}:{messages:readonly ContentMessage[]}){
  const {FilePreview}=useContentWorkspaceHost();
  const selected=selectDeliverables(messages);
  return <section className="cp-subject-deliverables" aria-label="交付文件">
    <header><h2>交付文件</h2><span>{selected.length} 份</span></header>
    {selected.length?<div className="cp-subject-deliverable-list">{selected.map(file=><FilePreview key={contentOutputIdentity(file)} file={{id:file.fileUrl,type:"file",name:file.fileName,blobUrl:file.fileUrl}}/>)}</div>
      :<div className="cp-subject-deliverable-empty"><p>暂无交付文件</p><small>资料包或文章生成后会显示在这里。</small></div>}
  </section>;
}
