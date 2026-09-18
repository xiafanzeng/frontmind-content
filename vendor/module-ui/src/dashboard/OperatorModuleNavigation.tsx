import { useState, type CSSProperties } from "react";
import { ChartNoAxesCombined, ChevronDown, Database, FolderOpen, PanelLeftClose, PanelLeftOpen, PenLine, Plus, Send, Settings, Sparkles, Target, Wrench } from "lucide-react";

export type OperatorModuleNavigationItem = { id: string; label: string; color: string; active?: boolean };
const moduleIcons = { brand: Database, intent: Target, progress: ChartNoAxesCombined, content: PenLine, publish: Send, publishing: Send, extensions: Wrench };

/** The Dashboard's original visual navigation, shared without account/project behavior. */
export function OperatorModuleNavigation({ modules, onSelect, logoSrc = new URL("../assets/frontmind-wordmark.svg", import.meta.url).href }: { logoSrc?: string; modules: readonly OperatorModuleNavigationItem[]; onSelect: (id: string) => void }) {
  const [modulesExpanded, setModulesExpanded] = useState(true);
  return <>
    <div className="operator-brand"><div className="operator-brand-logo"><img src={logoSrc} alt="FrontMind" /></div></div>
    <nav className="operator-module-nav" aria-label="项目模块">
      <h2 className="operator-module-group-label">
        <button type="button" className="operator-module-group-toggle" aria-label="AI 智能品牌优化" aria-expanded={modulesExpanded} aria-controls="operator-brand-modules" onClick={() => setModulesExpanded(value => !value)}>
          <span className="operator-brand-symbol" aria-hidden="true"><Sparkles size={20} /></span><span>AI 智能品牌优化</span>
          <ChevronDown size={14} aria-hidden="true" className={modulesExpanded ? "is-open" : ""} />
        </button>
      </h2>
      <div id="operator-brand-modules" className="operator-brand-modules" hidden={!modulesExpanded}>
        {modules.map(module => { const Icon = moduleIcons[module.id as keyof typeof moduleIcons] ?? Database; return <button key={module.id} type="button" className={`operator-nav-entry operator-module-entry ${module.active ? "active" : ""}`} style={{ "--module-accent": module.color } as CSSProperties} title={module.label} aria-label={module.label} aria-current={module.active ? "page" : undefined} onClick={() => onSelect(module.id)}><Icon size={20} /><span>{module.label}</span></button>; })}
      </div>
    </nav>
  </>;
}
export function OperatorSidebarFooter({ collapsed, onCollapse, workspaceLabel = "FrontMind 开发工作区", accountLabel = "FrontMind" }: { collapsed: boolean; onCollapse: () => void; workspaceLabel?: string; accountLabel?: string }) {
  return <>
    <div className="operator-project-group operator-project-capsule is-active">
      <div className="operator-project-heading">
        <button type="button" className="operator-nav-entry operator-project-entry active" aria-label="项目总览" title={`项目总览 · ${workspaceLabel}`} onClick={() => { if (collapsed) onCollapse(); }}>
          <FolderOpen size={20} />
          <span className="operator-project-capsule-label"><strong>项目总览</strong><small>{workspaceLabel}</small></span>
          <ChevronDown size={16} aria-hidden="true" />
        </button>
        <button type="button" className="operator-project-menu-trigger" aria-label="新建企业项目" title="新建企业项目" disabled><Plus size={18} /></button>
      </div>
    </div>
    <div className="operator-account-row">
      <button type="button" className="operator-account-identity" aria-label={accountLabel} title={accountLabel} disabled>
        <span aria-hidden="true">{accountLabel.slice(0, 1) || "F"}</span><strong>{accountLabel}</strong>
      </button>
      <button type="button" className="operator-account-settings" aria-label="账号设置" title="账号设置" disabled><Settings size={18} /></button>
    </div>
    <div className="operator-sidebar-footer"><button type="button" onClick={onCollapse} aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}>{collapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}<span>收起侧边栏</span></button></div>
  </>;
}
