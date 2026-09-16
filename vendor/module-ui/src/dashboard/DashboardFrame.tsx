import type { ReactNode } from "react";
import { BarChart3, X } from "lucide-react";
import "./dashboard-styles.css";
import "./operator-workspace.css";
import "./operator-navigation.css";

/** Layout DOM and CSS are shared by the production Dashboard and each module. */
export function DashboardFrame({ children, operatorMode = true, collapsed = false, mobileOpen = false, onMobileOpenChange, immersive = false, afterShell }: { children: ReactNode; operatorMode?: boolean; collapsed?: boolean; mobileOpen?: boolean; onMobileOpenChange: (open: boolean) => void; immersive?: boolean; afterShell?: ReactNode }) {
  return <div className={`user-brand-dashboard ${operatorMode ? `operator-mode ${collapsed ? "operator-collapsed" : ""}` : ""} ${immersive ? "knowledge-build-workspace" : ""}`}>
    <div className={`app-shell ${mobileOpen ? "nav-open" : ""} ${immersive ? "knowledge-build-app-shell" : ""}`}>
      <button className="mobile-menu-btn" onClick={() => onMobileOpenChange(!mobileOpen)} aria-label="切换菜单" aria-expanded={mobileOpen} aria-controls="operator-project-navigation">{mobileOpen ? <X size={22} /> : <BarChart3 size={22} />}</button>
      {mobileOpen && <div className="mobile-nav-overlay" onClick={() => onMobileOpenChange(false)} />}
      {children}
    </div>
    {afterShell}
  </div>;
}
