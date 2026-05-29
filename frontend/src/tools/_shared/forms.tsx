/**
 * 工具页公共 form 控件：ToolHeader（统一顶栏）、Field 容器、Picker（带"选择…"按钮的
 * 只读路径输入）、ResetBtn（回默认值）、RunBtn（loading 状态的主按钮）、IconBtn（小图标钮）。
 *
 * 历史：原本耦合在 LeebHardnessTool.tsx 末尾，被 PdfTools / Word2Pdf 跨文件 import；
 * 随 leeb 拆 controller/Page/SettingsForm 范式，搬到这里作为所有工具共用底座。
 *
 * 统一 token（Tier1/2 视觉与交互统一）：
 *   - 顶栏：所有工具页用 ToolHeader（同底色 #252526 / 同 padding / 同标题字号）
 *   - 主按钮：统一 RunBtn；小图标钮：统一 IconBtn（禁用态统一 opacity-50）
 *   - 输入/下拉：统一 INPUT_CLS（带 focus:border-vscode-focus 焦点环）；下拉用 Select
 *   - 报错：统一 ErrorBanner（role="alert" + 可选「重试」恢复动作）
 */
import { cn } from '../../lib/cn';

/**
 * 输入/下拉统一类名 —— 深色底 + 边框 + 统一焦点环（此前大量 select/input 缺焦点态）。
 * <input> 直接套；<select> 用下面的 Select 组件（已内置）。
 */
export const INPUT_CLS =
  'bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus rounded-[2px] border px-2 py-1 text-xs focus:outline-none';

/** 统一下拉控件：套 INPUT_CLS（含焦点环）+ 统一禁用态；extra className 合并（保留各处的宽度等）。 */
export function Select({
  value,
  onChange,
  disabled,
  title,
  className,
  children,
}: {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  disabled?: boolean;
  title?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={onChange}
      disabled={disabled}
      title={title}
      className={cn(INPUT_CLS, 'disabled:cursor-not-allowed', className)}
    >
      {children}
    </select>
  );
}

/**
 * 统一报错条 —— role="alert"（无障碍播报）+ 红色左边框卡片 + 可选「重试」恢复动作。
 * 收敛此前各工具裸红字、无 aria、无恢复路径的写法。
 */
export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="border-vscode-border flex items-start gap-2 rounded border border-l-2 border-l-red-400 bg-[#2d2d2d] p-3 text-xs text-red-400"
    >
      <i className="codicon codicon-error mt-px !text-[14px]" />
      <div className="min-w-0 flex-1 whitespace-pre-wrap">{message}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="border-vscode-border text-vscode-text-dim hover:bg-vscode-hover flex shrink-0 items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-0.5 text-[11px] hover:text-white"
        >
          <i className="codicon codicon-refresh !text-[11px]" />
          重试
        </button>
      )}
    </div>
  );
}

/**
 * 统一工具页顶栏 —— 收敛此前 3 套写法（无底色 / #252526+描述 / #252526+focus 图标）。
 * 标题行固定：codicon(16px) + 标题；可选 subtitle / badge（如就绪态告警）/ actions（右侧主按钮）。
 * children 放工具各自的操作工具条（选文件 / 模式切换 等），跟随标题行下方、同一带状容器内。
 */
export function ToolHeader({
  icon,
  title,
  subtitle,
  badge,
  actions,
  children,
}: {
  icon: string;
  /** 标题。一般是字符串；plot_curves 等需要在标题行内嵌徽章时传 ReactNode。 */
  title: React.ReactNode;
  subtitle?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="border-vscode-border shrink-0 space-y-2 border-b bg-[#252526] px-6 py-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
            <i className={cn('codicon', `codicon-${icon}`, '!text-[16px]')} />
            {title}
          </h1>
          {subtitle && (
            <p className="text-vscode-text-dim mt-1 text-xs">{subtitle}</p>
          )}
          {badge}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-vscode-text-dim mb-1 text-[11px] tracking-wider uppercase">
        {label}
      </div>
      {children}
      {hint && (
        <div className="text-vscode-text-faint mt-1 text-[11px]">{hint}</div>
      )}
    </div>
  );
}

export function Picker({
  value,
  onPick,
  placeholder,
  muted,
  extra,
}: {
  value: string;
  onPick: () => void;
  placeholder?: string;
  muted?: boolean;
  extra?: React.ReactNode;
}) {
  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={value}
        readOnly
        placeholder={placeholder}
        className={cn(
          'bg-vscode-input border-vscode-border flex-1 truncate rounded-[2px] border px-2 py-1 text-xs',
          muted ? 'text-vscode-text-dim italic' : 'text-vscode-text',
        )}
      />
      <button
        type="button"
        onClick={onPick}
        className="border-vscode-border flex shrink-0 items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
      >
        <i className="codicon codicon-folder-opened !text-[12px]" />
        选择…
      </button>
      {extra}
    </div>
  );
}

export function ResetBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="border-vscode-border flex shrink-0 items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
      title="回到默认"
    >
      <i className="codicon codicon-discard !text-[12px]" />
    </button>
  );
}

export function RunBtn({
  running,
  disabled,
  onClick,
  children,
}: {
  running: boolean;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 rounded-[2px] px-4 py-1.5 text-xs',
        !disabled
          ? 'bg-vscode-button hover:bg-vscode-button-hover text-white'
          : 'text-vscode-text-dim cursor-not-allowed bg-[#3a3a3a]',
      )}
    >
      {running && (
        <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
      )}
      {children}
    </button>
  );
}

/**
 * 小图标按钮 —— 收敛此前 plot_curves / pdf_tools 各自重复定义的两份 IconBtn。
 * 默认无边框 h-6 w-6（行内操作）；bordered 时 h-7 w-7 带边框（工具条 CRUD）。
 * 统一禁用态 opacity-50、统一 danger hover 红。
 */
export function IconBtn({
  icon,
  title,
  onClick,
  disabled,
  danger,
  bordered,
}: {
  icon: string;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  bordered?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex shrink-0 items-center justify-center rounded-[2px] transition-colors',
        bordered ? 'border-vscode-border h-7 w-7 border' : 'h-6 w-6',
        disabled
          ? 'text-vscode-text-faint cursor-not-allowed opacity-50'
          : danger
            ? 'text-vscode-text-dim hover:bg-vscode-hover hover:text-red-400'
            : 'text-vscode-text-dim hover:bg-vscode-hover hover:text-white',
      )}
    >
      <i
        className={cn(
          'codicon',
          `codicon-${icon}`,
          bordered ? '!text-[14px]' : '!text-[12px]',
        )}
      />
    </button>
  );
}
