/**
 * RightPanel：VSCode 风右侧辅助栏（AuxiliaryBar）。
 *
 * 支持多 tab：当前工具调参 + 未来的 AI 助手等常驻面板。
 * 当 tabs 为空时显示占位（说明该工具没设置 + 没启用 agent）。
 *
 * 显隐由外部（App）控制 panelRef.collapse/expand；这里只负责内容。
 */
import { useEffect, useState } from "react";

import { cn } from "../lib/cn";

export interface RightTab {
  id: string;
  label: string;
  /** codicon 名（不带 codicon- 前缀） */
  icon: string;
  node: React.ReactNode;
}

interface Props {
  tabs: RightTab[];
  /** 默认激活的 tab id；若不在 tabs 里则用第一个 */
  defaultActiveId?: string;
  onClose: () => void;
}

export function RightPanel({ tabs, defaultActiveId, onClose }: Props) {
  const [activeId, setActiveId] = useState<string>(
    defaultActiveId && tabs.some((t) => t.id === defaultActiveId)
      ? defaultActiveId
      : tabs[0]?.id ?? "",
  );

  // tabs 变了（切工具）→ 若当前 active 不在新 tabs 里，退回第一个
  useEffect(() => {
    if (!tabs.some((t) => t.id === activeId)) {
      // tabs 改变是外部 prop 变动（切工具）→ 需要在 effect 里修正 activeId
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveId(tabs[0]?.id ?? "");
    }
  }, [tabs, activeId]);

  const active = tabs.find((t) => t.id === activeId);

  return (
    <div className="flex h-full flex-col bg-vscode-bg border-l border-vscode-border min-w-0">
      <div className="flex h-8 items-center border-b border-vscode-border shrink-0 pr-1">
        <div className="flex items-center flex-1 min-w-0 overflow-x-auto">
          {tabs.map((t) => (
            <TabBtn
              key={t.id}
              tab={t}
              active={t.id === activeId}
              onClick={() => setActiveId(t.id)}
            />
          ))}
        </div>
        <button
          type="button"
          title="收起右侧面板 (Ctrl+Alt+B)"
          onClick={onClose}
          className="h-6 w-6 flex items-center justify-center rounded-[3px] text-vscode-text-dim hover:bg-vscode-hover hover:text-white shrink-0"
        >
          <i className="codicon codicon-chevron-right !text-[12px]" />
        </button>
      </div>
      <div className="flex-1 overflow-auto min-h-0">
        {active ? (
          active.node
        ) : (
          <div className="p-6 text-xs text-vscode-text-faint italic">
            （当前工具没有可调参数。未来 AI 助手会常驻这里。）
          </div>
        )}
      </div>
    </div>
  );
}

function TabBtn({
  tab,
  active,
  onClick,
}: {
  tab: RightTab;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={tab.label}
      className={cn(
        "h-8 px-3 text-[11px] uppercase tracking-wider flex items-center gap-1.5 border-b-2 transition-colors shrink-0",
        active
          ? "text-white border-vscode-focus"
          : "text-vscode-text-dim border-transparent hover:text-white",
      )}
    >
      <i className={cn("codicon", `codicon-${tab.icon}`, "!text-[12px]")} />
      {tab.label}
    </button>
  );
}
