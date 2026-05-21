/**
 * BottomPanel：VSCode 风底部面板（当前只放"输出"Tab）。
 *
 * 设计变更（2026-05-21）：工具调参面板从这里挪到了右侧 RightPanel。
 * 底部 Panel 现在专用于"输出/日志"，后续可加"问题/终端"等运行时信息。
 *
 * 显隐由外部（App）控制 panelRef.collapse/expand；这里只渲染内容。
 */
interface Props {
  output: string;
  /** 折叠按钮：collapse 自身 */
  onClose: () => void;
}

export function BottomPanel({ output, onClose }: Props) {
  return (
    <div className="flex h-full flex-col bg-vscode-bg border-t border-vscode-border min-h-0">
      <div className="flex h-9 items-center border-b border-vscode-border px-2 shrink-0">
        <div className="h-9 px-3 text-[11px] uppercase tracking-wider flex items-center gap-1.5 border-b-2 border-vscode-focus text-white">
          <i className="codicon codicon-output !text-[12px]" />
          输出
        </div>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            title="收起面板 (Ctrl+J)"
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center text-vscode-text-dim hover:bg-vscode-hover hover:text-white rounded-[3px]"
          >
            <i className="codicon codicon-chevron-down !text-[14px]" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        <pre className="p-3 font-mono text-[12px] text-vscode-text whitespace-pre-wrap break-words min-h-full">
          {output || (
            <span className="text-vscode-text-faint italic">
              （暂无输出。运行工具后这里会显示日志摘要。）
            </span>
          )}
        </pre>
      </div>
    </div>
  );
}
