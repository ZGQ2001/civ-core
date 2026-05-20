/**
 * StatusBar：VSCode 底部 22px #007acc 蓝条。
 * 左：工作区路径 | 右：当前工具
 */
interface Props {
  workspacePath: string | null;
  toolLabel: string | null;
  sidecarStatus?: string;
}

export function StatusBar({ workspacePath, toolLabel, sidecarStatus }: Props) {
  return (
    <div className="flex h-[22px] items-center bg-vscode-status text-white text-[11px] px-3 shrink-0">
      <span className="truncate">{workspacePath ?? "无工作区"}</span>
      <div className="ml-auto flex items-center gap-3">
        {sidecarStatus && <span className="opacity-80">{sidecarStatus}</span>}
        {toolLabel && <span>{toolLabel}</span>}
      </div>
    </div>
  );
}
