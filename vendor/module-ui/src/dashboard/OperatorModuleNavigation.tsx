import { useState, type CSSProperties } from "react";
import { ChartNoAxesCombined, ChevronDown, Database, PanelLeftClose, PanelLeftOpen, PenLine, Send, Sparkles, Target, Wrench } from "lucide-react";

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
export function OperatorSidebarFooter({ collapsed, onCollapse }: { collapsed: boolean; onCollapse: () => void }) {
  return <div className="operator-sidebar-footer"><button type="button" onClick={onCollapse} aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}>{collapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}<span>收起侧边栏</span></button></div>;
}
