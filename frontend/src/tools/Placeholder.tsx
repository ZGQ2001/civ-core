/**
 * Placeholder：还没接通的工具页统一占位。
 * T5.2 / T5.3 / settings 复用；plot_curves 已替换为真组件。
 */
interface Props {
  icon: string;
  label: string;
  detail?: string;
}

export function Placeholder({ icon, label, detail }: Props) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <i className={`codicon codicon-${icon} !text-[48px] text-vscode-text-faint`} />
        <div className="mt-3 text-2xl font-light text-vscode-text-dim">{label}</div>
        <div className="mt-1 text-xs text-vscode-text-faint">
          {detail ?? "T5 后续轮次接入"}
        </div>
      </div>
    </div>
  );
}
