/**
 * EditorArea：中间工具区占位。
 * B2 阶段会做成 Tab 编辑器（多文件 / 多工具 Tab）；T1 阶段先放占位欢迎页。
 */
interface Props {
  activeToolId: string | null;
  toolLabel: string | null;
}

export function EditorArea({ activeToolId, toolLabel }: Props) {
  return (
    <div className="flex h-full flex-col bg-vscode-bg">
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="text-2xl font-light text-vscode-text-dim">
            {toolLabel ?? "请选择工具"}
          </div>
          {activeToolId && (
            <div className="mt-2 text-xs text-vscode-text-faint">
              工具 ID：<code>{activeToolId}</code>
              <br />
              （T5 阶段会接入实际工具页面）
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
