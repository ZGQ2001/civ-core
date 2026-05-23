/**
 * 工具页公共 form 控件：Field 容器、Picker（带"选择…"按钮的只读路径输入）、
 * ResetBtn（回默认值）、RunBtn（loading 状态的主按钮）。
 *
 * 历史：原本耦合在 LeebHardnessTool.tsx 末尾，被 PdfTools / Word2Pdf 跨文件 import；
 * 随 leeb 拆 controller/Page/SettingsForm 范式，搬到这里作为三个工具共用底座。
 */
import { cn } from '../../lib/cn';

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
