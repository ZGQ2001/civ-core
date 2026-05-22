/**
 * ShellContext：App 提供给所有工具 Provider 的全局壳能力。
 *
 * - appendOutput: 任何地方（包括 RightPanel 里的 SettingsForm）都能往底部「输出」Panel 写日志
 * - activeToolId: 工具 Provider 用它判断「文件激活事件是不是给我的」
 * - activatedFile: 文件树双击 .xlsx/.docx/.pdf 时塞进来；key 用于强制 effect 重跑（同路径再激活也触发）
 *
 * Provider 内通过 useShell() 读，无需 prop drilling。
 */
import { createContext, useContext } from "react";

export interface ActivatedFile {
  path: string;
  /** 单调递增；同一 path 再次激活时变化，确保 useEffect 依赖能再次触发。 */
  key: number;
}

export interface ShellContextValue {
  appendOutput: (text: string) => void;
  activeToolId: string;
  activatedFile: ActivatedFile | null;
}

export const ShellContext = createContext<ShellContextValue | null>(null);

export function useShell(): ShellContextValue {
  const v = useContext(ShellContext);
  if (!v) throw new Error("useShell 必须在 <ShellContext.Provider> 内调用");
  return v;
}

/** 给日志加 [HH:MM:SS] 前缀的小工具，所有工具统一格式。 */
export function logLine(msg: string): string {
  const t = new Date();
  const hh = String(t.getHours()).padStart(2, "0");
  const mm = String(t.getMinutes()).padStart(2, "0");
  const ss = String(t.getSeconds()).padStart(2, "0");
  return `[${hh}:${mm}:${ss}] ${msg}`;
}
