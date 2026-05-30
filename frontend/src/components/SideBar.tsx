/**
 * SideBar：VSCode 左侧栏（Explorer 视图）。
 * 顶部 32px header：标题 "资源管理器" + 4 个图标按钮
 * 内容区：文件树 / empty state（B1 阶段是 placeholder，T4 接 Python 文件树）
 */
import { AppLogo } from './AppLogo';
import { cn } from '../lib/cn';
import { FileTree } from './FileTree';

interface Props {
  workspacePath: string | null;
  /** 由父组件递增；变化时 FileTree 静默 refetch 所有当前展开的目录（保留展开状态） */
  refreshNonce: number;
  /** 由父组件递增；变化时 FileTree 折叠除根目录外所有节点（保留 entries 缓存） */
  collapseNonce: number;
  onOpenFolder: () => void;
  onNewWorkspace: () => void;
  onRefresh: () => void;
  onCollapseAll: () => void;
  /** 双击 .xlsx/.docx/.pdf 时上抛，App 转发给当前活跃工具的 controller */
  onFileActivate?: (path: string) => void;
}

export function SideBar({
  workspacePath,
  refreshNonce,
  collapseNonce,
  onOpenFolder,
  onNewWorkspace,
  onRefresh,
  onCollapseAll,
  onFileActivate,
}: Props) {
  return (
    <div className="bg-vscode-bg border-vscode-border flex h-full flex-col border-r">
      {/* Header（VSCode Explorer header 风） */}
      <div className="border-vscode-border flex h-8 shrink-0 items-center border-b px-3">
        <span className="text-vscode-text text-[11px] font-semibold tracking-wider uppercase">
          资源管理器
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <HeaderBtn
            icon="folder-opened"
            title="打开文件夹"
            onClick={onOpenFolder}
          />
          <HeaderBtn
            icon="new-folder"
            title="新建标准结构"
            onClick={onNewWorkspace}
          />
          <HeaderBtn icon="refresh" title="刷新" onClick={onRefresh} />
          <HeaderBtn
            icon="collapse-all"
            title="全部折叠"
            onClick={onCollapseAll}
          />
        </div>
      </div>

      {/* 内容 */}
      <div className="flex-1 overflow-auto">
        {workspacePath ? (
          // workspacePath 变化时 key 触发 FileTree 重挂（清空 nodes Map）；
          // refreshNonce/collapseNonce 由 FileTree 内部 effect 处理，不丢展开状态
          <FileTree
            key={workspacePath}
            rootPath={workspacePath}
            refreshNonce={refreshNonce}
            collapseNonce={collapseNonce}
            onFileActivate={onFileActivate}
          />
        ) : (
          <EmptyState
            onOpenFolder={onOpenFolder}
            onNewWorkspace={onNewWorkspace}
          />
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
        'flex h-[22px] w-[22px] items-center justify-center rounded-[3px]',
        'text-vscode-text-dim hover:bg-vscode-hover hover:text-white',
      )}
    >
      <i className={cn('codicon', `codicon-${icon}`, '!text-[14px]')} />
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
      <AppLogo size={44} className="mb-1" />
      <div className="flex items-baseline gap-1.5 leading-none">
        <span className="text-vscode-text text-base font-semibold tracking-wide">
          筑核
        </span>
        <span className="text-vscode-text-faint text-[11px] tracking-wider">
          civ-core
        </span>
      </div>
      <p className="text-vscode-text-dim mt-1 mb-1 text-xs">尚未打开工作区。</p>
      <button
        type="button"
        onClick={onOpenFolder}
        className={cn(
          'bg-vscode-button w-full rounded-[2px] px-3 py-1.5 text-xs text-white',
          'hover:bg-vscode-button-hover transition-colors',
        )}
      >
        打开文件夹
      </button>
      <button
        type="button"
        onClick={onNewWorkspace}
        className={cn(
          'border-vscode-border w-full rounded-[2px] border bg-[#2d2d2d] px-3 py-1.5 text-xs',
          'transition-colors hover:bg-[#3a3a3a]',
        )}
      >
        新建标准结构
      </button>
    </div>
  );
}
