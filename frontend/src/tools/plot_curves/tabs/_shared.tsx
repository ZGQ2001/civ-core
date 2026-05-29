/**
 * SettingsForm 各 tab 共用的表单控件。
 * 解耦：避免每个 tab 文件都重复 Row / SliderInput / NumberCell / inputClass。
 */
import { cn } from '../../../lib/cn';

export const inputClass =
  'bg-vscode-input border border-vscode-border focus:border-vscode-focus px-2 py-1 text-xs text-vscode-text rounded-[2px] w-full focus:outline-none';

export function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  // 标签列从 140px 收到 96px：右侧调参面板宽度有限，140 会把内容挤到换行；
  // hint 字号从 10 → 11，与 VSCode dim text 视觉更协调。
  return (
    <div className="grid grid-cols-[96px_1fr] items-start gap-3">
      <div className="text-vscode-text-dim pt-1 leading-tight">
        {label}
        {hint && (
          <div className="text-vscode-text-faint mt-1 text-[11px] leading-snug">
            {hint}
          </div>
        )}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function SliderInput({
  min,
  max,
  step,
  value,
  onChange,
}: {
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="accent-vscode-focus flex-1"
      />
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value || '0'))}
        className={cn(inputClass, 'w-20')}
      />
    </div>
  );
}

export function NumberCell({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-vscode-text-faint text-[10px]">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value || '0'))}
        className={inputClass}
      />
    </label>
  );
}

// matplotlib 接受多种颜色格式；HTML color picker 只认 "#RRGGBB"
// 已是 # 开头取前 7 位（防 "#RRGGBBAA"），否则返灰色兜底
// eslint-disable-next-line react-refresh/only-export-components -- 颜色工具与 form 子组件同文件共存
export function normalizeColor(c: string): string {
  if (c.startsWith('#') && (c.length === 7 || c.length === 9))
    return c.slice(0, 7);
  return '#888888';
}
