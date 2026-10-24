import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AgentWorkbenchShell } from "../components/AgentWorkbenchShell";
import { OperatorThemeProvider } from "../components/ui/operator-theme";
import { DashboardFrame } from "./DashboardFrame";
import { OperatorModuleNavigation, StandaloneWorkspaceFooter } from "./OperatorModuleNavigation";
import { ModulePresentationProvider } from "./module-presentation";
import "./module-shell.css";

export type ModuleShellProps = {
  module: { id: string; label: string; color: string };
  views: readonly { id: string; label: string; color?: string }[];
  activeView: string;
  onSelectView: (id: string) => void;
  children: ReactNode;
  /** Business workbenches already render the shared thin top bar. */
  showViewTabs?: boolean;
  preview?: boolean;
  navigationModules?: readonly { id: string; label: string; color: string; href?: string; views: readonly { id: string; label: string }[] }[];
  requestNavigation?: (action: () => void) => void;
};
const SIDEBAR_KEY = "frontmind.operator.sidebarCollapsed";
const ModuleSidebarTarget = createContext<HTMLElement | null>(null);
export const ModuleSidebarTargetProvider = ModuleSidebarTarget.Provider;
/** 同一插槽供独立模块与正式 Dashboard 宿主挂载业务目录。 */
export function useModuleSidebarTarget() { return useContext(ModuleSidebarTarget); }
export function ModuleShell({ module, views, activeView, onSelectView, children, showViewTabs = true, navigationModules, preview = false, requestNavigation = action => action() }: ModuleShellProps) {
  const immersive = ["knowledge", "enterprise-qa", "content"].includes(activeView);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [compact, setCompact] = useState(() => typeof window !== "undefined" && window.matchMedia("(max-width: 1279px)").matches);
  const [phone, setPhone] = useState(() => typeof window !== "undefined" && window.matchMedia("(max-width: 1023px)").matches);
  const [savedCollapsed, setSavedCollapsed] = useState(() => { try { return localStorage.getItem(SIDEBAR_KEY) === "1"; } catch { return false; } });
  const sidebarRef = useRef<HTMLElement>(null);
  const [sidebarTarget, setSidebarTarget] = useState<HTMLDivElement | null>(null);
  const collapsed = compact ? !mobileOpen : mobileOpen ? false : savedCollapsed;
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1279px)"), narrow = window.matchMedia("(max-width: 1023px)");
    const update = () => { setCompact(media.matches); setPhone(narrow.matches); };
    media.addEventListener("change", update); narrow.addEventListener("change", update);
    return () => { media.removeEventListener("change", update); narrow.removeEventListener("change", update); };
  }, []);
  useEffect(() => {
    // 平板/小桌面只是展开导航；只有手机抽屉才锁住正文并圈定焦点。
    if (!mobileOpen || !phone || !sidebarRef.current) return;
    const sidebar = sidebarRef.current;
    const origin = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const main = sidebar.closest(".app-shell")?.querySelector<HTMLElement>("main");
    const originalInert = main?.inert;
    if (main) main.inert = true;
    const controls = () => Array.from(sidebar.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], [tabindex="0"]')).filter(node => !node.closest('[hidden]'));
    controls()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMobileOpen(false); }
      if (event.key !== "Tab") return;
      const items = controls(), first = items[0], last = items.at(-1);
      if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); if (main) main.inert = originalInert ?? false; if (origin?.isConnected) origin.focus(); };
  }, [mobileOpen, phone]);
  const collapse = () => {
    if (compact) setMobileOpen(value => !value);
    else setSavedCollapsed(value => { const next = !value; try { localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0"); } catch {} return next; });
  };
  const select = (id: string) => { onSelectView(id); setMobileOpen(false); };
  const presentation = { ...module, actions: views.map(view => ({ id: view.id, label: view.label, color: view.color ?? module.color, active: view.id === activeView, kind: "open-panel" as const, run: () => select(view.id) })) };
  return <OperatorThemeProvider><ModulePresentationProvider module={presentation} requestNavigation={requestNavigation}>
    <ModuleSidebarTargetProvider value={activeView === "content" ? sidebarTarget : null}><DashboardFrame immersive={immersive} collapsed={(compact && !mobileOpen) || savedCollapsed} mobileOpen={mobileOpen} onMobileOpenChange={setMobileOpen}>
      <aside ref={sidebarRef} role={mobileOpen && phone ? "dialog" : undefined} aria-modal={mobileOpen && phone ? true : undefined} aria-hidden={phone && !mobileOpen ? true : undefined} inert={phone && !mobileOpen ? true : undefined} id="operator-project-navigation" className="global-nav operator-sidebar" aria-label="工作区导航" data-collapsed={collapsed} data-entry="project">
        <OperatorModuleNavigation modules={(navigationModules ?? [{ ...module, views }]).map(item => ({ ...item, active: item.views.some(view => view.id === activeView) }))} onSelect={id => requestNavigation(() => select((navigationModules ?? [{ ...module, views }]).find(item => item.id === id)?.views[0]?.id ?? activeView))} onNavigate={href => requestNavigation(() => window.location.assign(href))} activeModuleChildren={activeView === "content" ? <div ref={setSidebarTarget} className="operator-module-children" /> : undefined} />
        <div className="operator-sidebar-bottom"><StandaloneWorkspaceFooter collapsed={collapsed} onCollapse={collapse} workspaceLabel="FrontMind 开发工作区" accountLabel="FrontMind" /></div>
      </aside>
      <main className={`dashboard-main workbench-main ${immersive ? "knowledge-build-main" : ""}`}>
        {preview && <div className="module-preview-notice" role="status">本地预览 · 合成示例数据，不会执行真实业务</div>}
        {showViewTabs ? <AgentWorkbenchShell projectId="module-workspace" moduleId={activeView} title={views.find(view => view.id === activeView)?.label ?? module.label} layout="workspace" showLatestControl={false} main={children} /> : children}
      </main>
    </DashboardFrame></ModuleSidebarTargetProvider>
  </ModulePresentationProvider></OperatorThemeProvider>;
}
export default ModuleShell;
