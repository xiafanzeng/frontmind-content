import { createContext, useContext, type ReactNode } from "react";

export type WorkbenchAction = {
  id: string;
  label: string;
  kind: "open-panel" | "open-editor" | "start-task" | "navigate";
  run: () => void;
  disabled?: boolean;
  active?: boolean;
  color?: string;
  description?: string;
};
export type WorkbenchModulePresentation = {
  id: string;
  label: string;
  color?: string;
  actions: WorkbenchAction[];
};
type ModulePresentation = {
  module: WorkbenchModulePresentation;
  requestNavigation?: (action: () => void) => void;
};
const Context = createContext<ModulePresentation | null>(null);
export function ModulePresentationProvider({ children, ...value }: ModulePresentation & { children: ReactNode }) {
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useModulePresentation = () => useContext(Context);
