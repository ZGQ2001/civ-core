/**
 * StatusBar：VSCode 底部 22px 状态栏。
 *
 * 招牌双色：
 *   无工作区 → 紫色 #68217a（"危险/未就绪"提示）
 *   有工作区 → 蓝色 #007acc（常态）
 * 用 inline style 兜底，避免 Tailwind v4 utility 万一未生成。
 */
interface Props {
  workspacePath: string | null;
  toolLabel: string | null;
  sidecarStatus?: string;
  /** 底部 Panel 当前是否展开（决定按钮高亮 + 图标方向） */
  bottomPanelOpen: boolean;
  onToggleBottomPanel: () => void;
  rightPanelOpen: boolean;
  onToggleRightPanel: () => void;
  /** 当前工具有没有右侧调参面板（无的话隐藏按钮，避免误导） */
  rightPanelAvailable: boolean;
}

export function StatusBar({
  workspacePath,
  toolLabel,
  sidecarStatus,
  bottomPanelOpen,
  onToggleBottomPanel,
  rightPanelOpen,
  onToggleRightPanel,
  rightPanelAvailable,
}: Props) {
  const bg = workspacePath ? "#007acc" : "#68217a";
  return (
    <div
      style={{ backgroundColor: bg }}
      className="flex h-[22px] items-center text-white text-[11px] px-3 shrink-0 select-none"
    >
      <span className="truncate flex items-center gap-1">
        <i
          className={`codicon !text-[12px] ${
            workspacePath ? "codicon-folder-active" : "codicon-warning"
          }`}
        />
        {workspacePath ?? "尚未打开工作区"}
      </span>
      <div className="ml-auto flex items-center gap-3">
        {sidecarStatus && <span className="opacity-80">{sidecarStatus}</span>}
        {toolLabel && <span>{toolLabel}</span>}
        <button
          type="button"
          onClick={onToggleBottomPanel}
          title={`${bottomPanelOpen ? "隐藏" : "显示"}底部面板 (Ctrl+J)`}
          className="flex items-center gap-1 px-1.5 h-[18px] rounded hover:bg-white/15 transition-colors"
        >
          <i
            className={`codicon !text-[12px] ${
              bottomPanelOpen ? "codicon-chevron-down" : "codicon-chevron-up"
            }`}
          />
          <span>面板</span>
        </button>
        {rightPanelAvailable && (
          <button
            type="button"
            onClick={onToggleRightPanel}
            title={`${rightPanelOpen ? "隐藏" : "显示"}右侧调参 (Ctrl+Alt+B)`}
            className="flex items-center gap-1 px-1.5 h-[18px] rounded hover:bg-white/15 transition-colors"
          >
            <i
              className={`codicon !text-[12px] ${
                rightPanelOpen ? "codicon-layout-sidebar-right" : "codicon-layout-sidebar-right-off"
              }`}
            />
            <span>调参</span>
          </button>
        )}
      </div>
    </div>
  );
}
