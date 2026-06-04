/**
 * EditorArea：按 activeToolId 从工具注册表路由到对应工具页。
 * appendOutput 透传给工具页，工具页跑完往底部 Panel 输出 Tab 写日志摘要。
 */
import { Placeholder } from '../tools/Placeholder';
import { TOOLS } from '../tools/registry';
import { ErrorBoundary } from './ErrorBoundary';

interface Props {
  activeToolId: string | null;
  toolLabel: string | null;
  appendOutput: (text: string) => void;
}

export function EditorArea({ activeToolId, toolLabel, appendOutput }: Props) {
  const tool = TOOLS.find((t) => t.id === activeToolId);

  return (
    <div className="bg-vscode-bg flex h-full min-w-0 flex-col">
      {tool ? (
        // 工具级边界：单个工具页渲染崩溃只炸自己、不波及整壳；key=toolId 切走再回即重挂恢复
        <ErrorBoundary
          key={activeToolId ?? 'tool'}
          label={toolLabel ?? undefined}
        >
          <tool.Page appendOutput={appendOutput} />
        </ErrorBoundary>
      ) : activeToolId === 'settings' ? (
        <Placeholder
          icon="settings-gear"
          label={toolLabel ?? '设置'}
          detail="后续接入"
        />
      ) : (
        <Placeholder
          icon="tools"
          label={toolLabel ?? '请选择工具'}
          detail="从左侧 Activity Bar 选一个工具"
        />
      )}
    </div>
  );
}
