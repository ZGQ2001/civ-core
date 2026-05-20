/**
 * ActivityBar：VSCode 左侧 48px 工具切换栏。
 * 上方组：业务工具；底部组：settings（gear icon），中间 flex-1 撑开。
 * 选中态：左侧 2px 蓝条 indicator + 图标变白（VSCode 招牌细节）。
 */
import { cn } from "../lib/cn";

export interface ActivityItem {
  id: string;
  icon: string; // codicon class name without "codicon-" prefix
  tooltip: string;
}

interface Props {
  topItems: ActivityItem[];
  bottomItems: ActivityItem[];
  activeId: string;
  onChange: (id: string) => void;
}

export function ActivityBar({ topItems, bottomItems, activeId, onChange }: Props) {
  return (
    <div className="flex h-full w-12 flex-col bg-vscode-activity border-r border-vscode-border">
      <div className="flex flex-col">
        {topItems.map((it) => (
          <Btn key={it.id} item={it} active={it.id === activeId} onClick={() => onChange(it.id)} />
        ))}
      </div>
      <div className="flex-1" />
      <div className="flex flex-col">
        {bottomItems.map((it) => (
          <Btn key={it.id} item={it} active={it.id === activeId} onClick={() => onChange(it.id)} />
        ))}
      </div>
    </div>
  );
}

function Btn({
  item,
  active,
  onClick,
}: {
  item: ActivityItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={item.tooltip}
      aria-label={item.tooltip}
      onClick={onClick}
      className={cn(
        "relative flex h-12 w-12 items-center justify-center transition-colors",
        active ? "text-white" : "text-vscode-text-dim hover:text-white",
      )}
    >
      {/* 左侧 2px 激活指示条（VSCode 风） */}
      <span
        className={cn(
          "absolute left-0 top-0 h-full w-[2px]",
          active ? "bg-vscode-focus" : "bg-transparent",
        )}
      />
      <i className={cn("codicon", `codicon-${item.icon}`, "!text-[22px]")} />
    </button>
  );
}
