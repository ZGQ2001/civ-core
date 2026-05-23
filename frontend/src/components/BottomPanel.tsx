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
    <div className="bg-vscode-bg border-vscode-border flex h-full min-h-0 flex-col border-t">
      <div className="border-vscode-border flex h-9 shrink-0 items-center border-b px-2">
        <div className="border-vscode-focus flex h-9 items-center gap-1.5 border-b-2 px-3 text-[11px] tracking-wider text-white uppercase">
          <i className="codicon codicon-output !text-[12px]" />
          输出
        </div>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            title="收起面板 (Ctrl+J)"
            onClick={onClose}
            className="text-vscode-text-dim hover:bg-vscode-hover flex h-6 w-6 items-center justify-center rounded-[3px] hover:text-white"
          >
            <i className="codicon codicon-chevron-down !text-[14px]" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        <pre className="text-vscode-text min-h-full p-3 font-mono text-[12px] break-words whitespace-pre-wrap">
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
