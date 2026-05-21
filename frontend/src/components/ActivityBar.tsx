/**
 * ActivityBar：VSCode 左侧 48px 工具切换栏。
 *
 * 布局（自上而下）：
 *   1. Explorer 按钮（独立）—— 点击 toggle SideBar 显隐，不切换 EditorArea
 *   2. 工具组（topItems）—— 点击切换 EditorArea 工具页
 *   3. flex-1 撑开
 *   4. 底部组（bottomItems）—— settings 等
 *
 * 选中态：左侧 2px 蓝条 indicator + 图标变白。
 */
import { cn } from "../lib/cn";

export interface ActivityItem {
  id: string;
  icon: string;
  tooltip: string;
}

interface Props {
  topItems: ActivityItem[];
  bottomItems: ActivityItem[];
  activeId: string;
  onChange: (id: string) => void;
  /** Explorer 按钮当前是否点亮（= SideBar 是否展开） */
  explorerActive: boolean;
  onExplorerToggle: () => void;
}

export function ActivityBar({
  topItems,
  bottomItems,
  activeId,
  onChange,
  explorerActive,
  onExplorerToggle,
}: Props) {
  return (
    <div className="flex h-full w-12 flex-col bg-vscode-activity border-r border-vscode-border">
      <div className="flex flex-col">
        <Btn
          icon="files"
          tooltip={explorerActive ? "隐藏资源管理器 (Ctrl+B)" : "显示资源管理器 (Ctrl+B)"}
          active={explorerActive}
          onClick={onExplorerToggle}
        />
        {topItems.map((it) => (
          <Btn
            key={it.id}
            icon={it.icon}
            tooltip={it.tooltip}
            active={it.id === activeId}
            onClick={() => onChange(it.id)}
          />
        ))}
      </div>
      <div className="flex-1" />
      <div className="flex flex-col">
        {bottomItems.map((it) => (
          <Btn
            key={it.id}
            icon={it.icon}
            tooltip={it.tooltip}
            active={it.id === activeId}
            onClick={() => onChange(it.id)}
          />
        ))}
      </div>
    </div>
  );
}

function Btn({
  icon,
  tooltip,
  active,
  onClick,
}: {
  icon: string;
  tooltip: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={tooltip}
      aria-label={tooltip}
      onClick={onClick}
      className={cn(
        "relative flex h-12 w-12 items-center justify-center transition-colors",
        active ? "text-white" : "text-vscode-text-dim hover:text-white",
      )}
    >
      <span
        className={cn(
          "absolute left-0 top-0 h-full w-[2px]",
          active ? "bg-vscode-focus" : "bg-transparent",
        )}
      />
      <i className={cn("codicon", `codicon-${icon}`, "!text-[22px]")} />
    </button>
  );
}
