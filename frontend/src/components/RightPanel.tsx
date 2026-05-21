/**
 * RightPanel：VSCode 风右侧辅助栏（AuxiliaryBar）。
 *
 * 用途：承载"当前工具的参数面板"。从底部 Panel 挪过来以后，
 * SideBar 可以全高、底部 Panel 留给"输出"专用，调参在右侧，互不挤占。
 *
 * 当前工具没有参数面板时（leeb/pdf/word2pdf），整个 RightPanel 默认折叠。
 */
interface Props {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}

export function RightPanel({ title, children, onClose }: Props) {
  return (
    <div className="flex h-full flex-col bg-vscode-bg border-l border-vscode-border min-w-0">
      <div className="flex h-8 items-center px-3 border-b border-vscode-border shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-vscode-text truncate">
          {title}
        </span>
        <button
          type="button"
          title="收起右侧面板"
          onClick={onClose}
          className="ml-auto h-6 w-6 flex items-center justify-center rounded-[3px] text-vscode-text-dim hover:bg-vscode-hover hover:text-white"
        >
          <i className="codicon codicon-chevron-right !text-[12px]" />
        </button>
      </div>
      <div className="flex-1 overflow-auto min-h-0">{children}</div>
    </div>
  );
}
