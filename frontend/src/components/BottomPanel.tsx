/**
 * BottomPanel：VSCode 风底部面板（Output / Tool Settings / Problems 等 Tab）。
 *
 * 第一版只放 2 个 Tab：
 *   - 输出：全局 logs（plot_curves 跑完写一段摘要进来；后续工具也走这里）
 *   - 工具设置：当前 activeToolId 对应的可调参数面板（plot_curves 第二刀会填）
 *
 * 显隐由外部（App）控制 panelRef.collapse/expand；这里只渲染内容。
 */
import { useState } from "react";

import { cn } from "../lib/cn";

interface Props {
  output: string;
  /** 当前 activeToolId 对应的 settings 面板（PlotCurvesTool 等填进来） */
  settingsSlot?: React.ReactNode;
  /** 折叠按钮：collapse 自身 */
  onClose: () => void;
}

type TabId = "output" | "settings";

export function BottomPanel({ output, settingsSlot, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("output");

  return (
    <div className="flex h-full flex-col bg-vscode-bg border-t border-vscode-border min-h-0">
      <div className="flex h-9 items-center border-b border-vscode-border px-2 shrink-0">
        <Tab
          label="输出"
          icon="output"
          active={activeTab === "output"}
          onClick={() => setActiveTab("output")}
        />
        <Tab
          label="工具设置"
          icon="settings"
          active={activeTab === "settings"}
          onClick={() => setActiveTab("settings")}
        />
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            title="关闭面板"
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center text-vscode-text-dim hover:bg-vscode-hover hover:text-white rounded-[3px]"
          >
            <i className="codicon codicon-chevron-down !text-[14px]" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {activeTab === "output" && <OutputPane text={output} />}
        {activeTab === "settings" && <SettingsPane slot={settingsSlot} />}
      </div>
    </div>
  );
}

function Tab({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-9 px-3 text-[11px] uppercase tracking-wider flex items-center gap-1.5 border-b-2 transition-colors",
        active
          ? "text-white border-vscode-focus"
          : "text-vscode-text-dim border-transparent hover:text-white",
      )}
    >
      <i className={cn("codicon", `codicon-${icon}`, "!text-[12px]")} />
      {label}
    </button>
  );
}

function OutputPane({ text }: { text: string }) {
  return (
    <pre className="p-3 font-mono text-[12px] text-vscode-text whitespace-pre-wrap break-words min-h-full">
      {text || <span className="text-vscode-text-faint italic">（暂无输出。运行工具后这里会显示日志摘要。）</span>}
    </pre>
  );
}

function SettingsPane({ slot }: { slot?: React.ReactNode }) {
  if (!slot) {
    return (
      <div className="p-6 text-xs text-vscode-text-faint italic">
        （当前工具没有可调参数。）
      </div>
    );
  }
  return <div className="p-3">{slot}</div>;
}
