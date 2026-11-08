// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {afterEach,expect,it} from "vitest";
import ContentDeliverables from "../client/ContentDeliverables";
import {ContentWorkspaceHostProvider,type ContentWorkspaceHost,type ContentOutputFile} from "../client/host";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
const roots:Array<ReturnType<typeof createRoot>>=[];
async function mount(files:ContentOutputFile[]){
 const container=document.createElement('div');document.body.appendChild(container);
 const root=createRoot(container);roots.push(root);
 const host={FilePreview:({file}:any)=><a href={file.blobUrl}>{file.name}</a>} as unknown as ContentWorkspaceHost;
 await act(async()=>root.render(<ContentWorkspaceHostProvider value={host}><ContentDeliverables files={files}/></ContentWorkspaceHostProvider>));
 return container;
}
afterEach(async()=>{for(const root of roots.splice(0))await act(async()=>root.unmount());document.body.replaceChildren();});

it("keeps the delivery panel visible before the first file exists",async()=>{
 const view=await mount([]);
 expect(view.querySelector('section[aria-label="交付文件"]')).not.toBeNull();
 expect(view.textContent).toContain('0 份');expect(view.textContent).toContain('暂无交付文件');
 expect(view.querySelector('details')).toBeNull();
});

it("shows files immediately, deduplicates repeated messages and retains different versions",async()=>{
 const first={fileUrl:'/api/frontmind/v2/artifacts/first/content',fileName:'品牌长文.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',sha256:'a'.repeat(64)};
 const second={...first,fileUrl:'/api/frontmind/v2/artifacts/second/content',sha256:'b'.repeat(64)};
 const view=await mount([first,{...first},second]);
 expect(view.textContent).toContain('2 份');
 expect([...view.querySelectorAll('a')].map(link=>link.getAttribute('href'))).toEqual([first.fileUrl,second.fileUrl]);
 expect(view.textContent).not.toContain('暂无交付文件');
});
