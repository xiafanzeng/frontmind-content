// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {afterEach,expect,it} from "vitest";
import ContentDeliverables from "../client/ContentDeliverables";
import {ContentWorkspaceHostProvider,type ContentWorkspaceHost,type ContentMessage,type ContentOutputFile} from "../client/host";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
const roots:Array<ReturnType<typeof createRoot>>=[];
async function mount(messages:ContentMessage[]){
 const container=document.createElement('div');document.body.appendChild(container);
 const root=createRoot(container);roots.push(root);
 const host={FilePreview:({file}:any)=><a href={file.blobUrl}>{file.name}</a>} as unknown as ContentWorkspaceHost;
 await act(async()=>root.render(<ContentWorkspaceHostProvider value={host}><ContentDeliverables messages={messages}/></ContentWorkspaceHostProvider>));
 return container;
}
afterEach(async()=>{for(const root of roots.splice(0))await act(async()=>root.unmount());document.body.replaceChildren();});

it("keeps the delivery panel visible before the first file exists",async()=>{
 const view=await mount([]);
 expect(view.querySelector('section[aria-label="交付文件"]')).not.toBeNull();
 expect(view.textContent).toContain('0 份');expect(view.textContent).toContain('暂无交付文件');
 expect(view.querySelector('details')).toBeNull();
});

function file(fileName:string,id=fileName):ContentOutputFile {
 return {fileName,fileUrl:`/artifacts/${id}`,mimeType:"application/octet-stream"};
}

function reply(id:string,outputFiles:ContentOutputFile[],turnId=id):ContentMessage {
 return {id,role:"assistant",content:"",timestamp:0,generalChat:{turnId,providerEventId:id},outputFiles};
}

function links(view:HTMLElement){
 return [...view.querySelectorAll("a")].map(link=>link.getAttribute("href"));
}

it("shows only the latest reference pack and one final article among 27 files",async()=>{
 const oldPack=file("Reference_Pack.zip");
 const pack=file("Reference_Pack_v2.zip");
 const word=file("p0.docx");
 const intermediates=Array.from({length:22},(_,index)=>file(`review-${index}.md`));
 const view=await mount([
  reply("first",[oldPack,...intermediates]),
  reply("second",[pack,file("p0_brand_article.md"),word,file("p0.html")]),
  reply("repeated",[{...oldPack},{...word}]),
 ]);
 expect(view.textContent).toContain("2 份");
 expect(links(view)).toEqual([pack.fileUrl,word.fileUrl]);
});

it("prefers Word within a turn and picks a newer article even without a Word file",async()=>{
 const word=file("p0.docx");
 const sameTurnHtml=file("p0.html");
 const newer=file("问题文章.md");
 const first=reply("word",[word],"p0-turn");
 const second=reply("html",[sameTurnHtml],"p0-turn");
 expect(links(await mount([first,second]))).toEqual([word.fileUrl]);
 expect(links(await mount([first,second,reply("article",[newer,{...word}])]))).toEqual([newer.fileUrl]);
});

it("uses the highest numbered reference pack even when an older revision appears later",async()=>{
 const latest=file("品牌资料包_10.zip");
 const earlier=file("品牌资料包_2.zip");
 expect(links(await mount([reply("latest",[latest]),reply("earlier",[earlier])]))).toEqual([latest.fileUrl]);
});

it("recognizes final files with legacy brand prefixes",async()=>{
 const older=file("示例品牌_Reference_Pack.zip");
 const pack=file("示例品牌_Reference_Pack_P0_v10.zip");
 const article=file("示例品牌_P0正文.docx");
 const review=file("示例品牌_定位确认稿.md");
 const view=await mount([reply("first",[older]),reply("final",[pack,article,review])]);
 expect(links(view)).toEqual([pack.fileUrl,article.fileUrl]);
 const question=file("示例品牌_问题1正文.md");
 expect(links(await mount([reply("p0",[pack,article]),reply("question",[question])]))).toEqual([pack.fileUrl,question.fileUrl]);
});
