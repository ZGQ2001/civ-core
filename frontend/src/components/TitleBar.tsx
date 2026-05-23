/**
 * TitleBar：自画窗口顶栏（VSCode Win 风，无系统装饰条）。
 *
 * 布局：[图标位/菜单空]  ──  居中标题   ──  [最小化 ▢ 关闭]
 * 整条 div 设 data-tauri-drag-region：用户在空白处可拖动窗口（Tauri 2 自动处理）。
 * 系统按钮区（最小化/最大化/关闭）不能进 drag region，否则点不到。
 */
import { useEffect, useState } from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';

import { cn } from '../lib/cn';

interface Props {
  workspaceName: string | null;
  toolLabel: string | null;
}

export function TitleBar({ workspaceName, toolLabel }: Props) {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    const win = getCurrentWindow();
    win.isMaximized().then(setMaximized);
    const unlistenP = win.onResized(() => {
      win.isMaximized().then(setMaximized);
    });
    return () => {
      unlistenP.then((fn) => fn());
    };
  }, []);

  const titleParts = [workspaceName ?? '未打开工作区', toolLabel].filter(
    Boolean,
  );

  return (
    <div
      data-tauri-drag-region
      className="bg-vscode-activity border-vscode-border flex h-[30px] shrink-0 items-center border-b select-none"
    >
      {/* 左侧 logo 占位（48px 对齐下面的 Activity Bar） */}
      <div
        data-tauri-drag-region
        className="flex w-12 items-center justify-center"
      >
        <i className="codicon codicon-symbol-misc text-vscode-text-dim !text-[14px]" />
      </div>

      {/* 居中标题 —— 也是 drag region */}
      <div
        data-tauri-drag-region
        className="text-vscode-text-dim flex flex-1 items-center justify-center text-[12px]"
      >
        <span data-tauri-drag-region className="truncate px-2">
          {titleParts.join('  —  ')}
        </span>
      </div>

      {/* 右侧窗口按钮组（不能进 drag region） */}
      <div className="flex h-full">
        <CtlBtn
          icon="chrome-minimize"
          aria="最小化"
          onClick={() => getCurrentWindow().minimize()}
        />
        <CtlBtn
          icon={maximized ? 'chrome-restore' : 'chrome-maximize'}
          aria={maximized ? '还原' : '最大化'}
          onClick={() => getCurrentWindow().toggleMaximize()}
        />
        <CtlBtn
          icon="chrome-close"
          aria="关闭"
          variant="close"
          onClick={() => getCurrentWindow().close()}
        />
      </div>
    </div>
  );
}

function CtlBtn({
  icon,
  aria,
  variant,
  onClick,
}: {
  icon: string;
  aria: string;
  variant?: 'close';
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={aria}
      title={aria}
      onClick={onClick}
      className={cn(
        'flex h-full w-[46px] items-center justify-center transition-colors',
        'text-vscode-text',
        variant === 'close'
          ? 'hover:bg-[#e81123] hover:text-white'
          : 'hover:bg-vscode-hover',
      )}
    >
      <i className={cn('codicon', `codicon-${icon}`, '!text-[12px]')} />
    </button>
  );
}
