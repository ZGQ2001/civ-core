/**
 * ShellContext：App 提供给所有工具 Provider 的全局壳能力。
 *
 * - appendOutput: 任何地方（包括 RightPanel 里的 SettingsForm）都能往底部「输出」Panel 写日志
 * - activeToolId: 工具 Provider 用它判断「文件激活事件是不是给我的」
 * - activatedFile: 文件树双击 .xlsx/.docx/.pdf 时塞进来；key 用于强制 effect 重跑（同路径再激活也触发）
 *
 * Provider 内通过 useShell() 读，无需 prop drilling。
 */
import { createContext, useContext } from 'react';

import type { DataProcessingSnapshot } from '../tools/data_processing/types';

export interface ActivatedFile {
  path: string;
  /** 单调递增；同一 path 再次激活时变化，确保 useEffect 依赖能再次触发。 */
  key: number;
}

export interface ShellContextValue {
  appendOutput: (text: string) => void;
  activeToolId: string;
  activatedFile: ActivatedFile | null;
  /** 工具生成文件后调用，触发目录树刷新。 */
  notifyFilesChanged: () => void;
  /**
   * 占位图（曲线图）目录 —— 跨工具共享：报告填充用它嵌 {{img:曲线图}}，
   * 模板助手用它跑预校验。两端读写同一份，避免一边改了另一边还停在旧路径。
   * 空字符串 = 未配置。
   */
  curveImageDir: string;
  setCurveImageDir: (dir: string) => void;
  /**
   * 数据处理发布的「一键导入」快照（装配线显式快照）。
   * data_processing 写、report_generator 读——下游不再直接 useDataProcessing，解除 Provider 嵌套依赖。
   * null = 数据处理还没产生任何可导入 state。
   */
  dataProcessingSnapshot: DataProcessingSnapshot | null;
  setDataProcessingSnapshot: (s: DataProcessingSnapshot) => void;
}

export const ShellContext = createContext<ShellContextValue | null>(null);

export function useShell(): ShellContextValue {
  const v = useContext(ShellContext);
  if (!v) throw new Error('useShell 必须在 <ShellContext.Provider> 内调用');
  return v;
}

/** 给日志加 [HH:MM:SS] 前缀的小工具，所有工具统一格式。 */
export function logLine(msg: string): string {
  const t = new Date();
  const hh = String(t.getHours()).padStart(2, '0');
  const mm = String(t.getMinutes()).padStart(2, '0');
  const ss = String(t.getSeconds()).padStart(2, '0');
  return `[${hh}:${mm}:${ss}] ${msg}`;
}
