/**
 * SideBar：VSCode 左侧栏（Explorer 视图）。
 * 顶部 32px header：标题 "资源管理器" + 4 个图标按钮
 * 内容区：文件树 / empty state（B1 阶段是 placeholder，T4 接 Python 文件树）
 */
import { cn } from "../lib/cn";
import { FileTree } from "./FileTree";

interface Props {
  workspacePath: string | null;
  /** 由父组件递增；变化时 FileTree 整树重挂（实现刷新/全部折叠） */
  refreshKey: number;
  onOpenFolder: () => void;
  onNewWorkspace: () => void;
  onRefresh: () => void;
  onCollapseAll: () => void;
  /** 双击 .xlsx/.docx/.pdf 时上抛，App 转发给当前活跃工具的 controller */
  onFileActivate?: (path: string) => void;
}

export function SideBar({
  workspacePath,
  refreshKey,
  onOpenFolder,
  onNewWorkspace,
  onRefresh,
  onCollapseAll,
  onFileActivate,
}: Props) {
  return (
    <div className="flex h-full flex-col bg-vscode-bg border-r border-vscode-border">
      {/* Header（VSCode Explorer header 风） */}
      <div className="flex h-8 items-center px-3 border-b border-vscode-border shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-vscode-text">
          资源管理器
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <HeaderBtn icon="folder-opened" title="打开文件夹" onClick={onOpenFolder} />
          <HeaderBtn icon="new-folder" title="新建标准结构" onClick={onNewWorkspace} />
          <HeaderBtn icon="refresh" title="刷新" onClick={onRefresh} />
          <HeaderBtn icon="collapse-all" title="全部折叠" onClick={onCollapseAll} />
        </div>
      </div>

      {/* 内容 */}
      <div className="flex-1 overflow-auto">
        {workspacePath ? (
          // key 让 refreshKey/路径变化时整棵树重挂
          <FileTree
            key={`${workspacePath}::${refreshKey}`}
            rootPath={workspacePath}
            onFileActivate={onFileActivate}
          />
        ) : (
          <EmptyState onOpenFolder={onOpenFolder} onNewWorkspace={onNewWorkspace} />
        )}
      </div>
    </div>
  );
}

function HeaderBtn({
  icon,
  title,
  onClick,
}: {
  icon: string;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className={cn(
        "flex h-[22px] w-[22px] items-center justify-center rounded-[3px]",
        "text-vscode-text-dim hover:bg-vscode-hover hover:text-white",
      )}
    >
      <i className={cn("codicon", `codicon-${icon}`, "!text-[14px]")} />
    </button>
  );
}

function EmptyState({
  onOpenFolder,
  onNewWorkspace,
}: {
  onOpenFolder: () => void;
  onNewWorkspace: () => void;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
      <p className="text-xs text-vscode-text-dim">尚未打开工作区。</p>
      <button
        type="button"
        onClick={onOpenFolder}
        className={cn(
          "w-full bg-vscode-button px-3 py-1.5 text-xs text-white rounded-[2px]",
          "hover:bg-vscode-button-hover transition-colors",
        )}
      >
        打开文件夹
      </button>
      <button
        type="button"
        onClick={onNewWorkspace}
        className={cn(
          "w-full bg-[#2d2d2d] border border-vscode-border px-3 py-1.5 text-xs rounded-[2px]",
          "hover:bg-[#3a3a3a] transition-colors",
        )}
      >
        新建标准结构
      </button>
    </div>
  );
}

