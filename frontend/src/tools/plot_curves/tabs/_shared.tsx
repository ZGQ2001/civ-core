/**
 * SettingsForm 各 tab 共用的表单控件。
 * 解耦：避免每个 tab 文件都重复 Row / SliderInput / NumberCell / inputClass。
 */
import { cn } from "../../../lib/cn";

export const inputClass =
  "bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px] w-full";

export function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 items-start">
      <div className="text-vscode-text-dim pt-1">
        {label}
        {hint && <div className="text-[10px] text-vscode-text-faint mt-0.5">{hint}</div>}
      </div>
      <div>{children}</div>
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
        className="flex-1 accent-vscode-focus"
      />
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value || "0"))}
        className={cn(inputClass, "w-20")}
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
      <span className="text-[10px] text-vscode-text-faint">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value || "0"))}
        className={inputClass}
      />
    </label>
  );
}

// matplotlib 接受多种颜色格式；HTML color picker 只认 "#RRGGBB"
// 已是 # 开头取前 7 位（防 "#RRGGBBAA"），否则返灰色兜底
export function normalizeColor(c: string): string {
  if (c.startsWith("#") && (c.length === 7 || c.length === 9)) return c.slice(0, 7);
  return "#888888";
}
