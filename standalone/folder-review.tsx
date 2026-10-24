// 与真实内容工作区共用业务组件；本入口仅注入浏览器持久离线客户端。
import {useMemo} from "react";
import {createRoot} from "react-dom/client";
import {ModuleShell} from "@frontmind/module-ui/dashboard/ModuleShell";
import {ModuleWorkspace} from "../module/client/runtime";
import {folderDemoClient} from "./folder-demo-client";
import "./base.css";

function App() {
  const {client, context} = useMemo(() => folderDemoClient(), []);
  return <ModuleShell module={{id: "content", label: "内容制作", color: "#8a6100"}} views={[{id: "content", label: "内容工作台"}]} activeView="content" onSelectView={() => {}} preview showViewTabs={false}>
    <div className="cp-local-workspace"><ModuleWorkspace context={context} client={client}/></div>
  </ModuleShell>;
}
createRoot(document.getElementById("root")!).render(<App/>);
