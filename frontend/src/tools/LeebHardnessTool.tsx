/**
 * 里氏硬度 INSP-001 工具页。
 * 流程：选 Excel → （可选）改输出路径 + 默认角度 → 跑 → 显示批/构件统计。
 */
import { useCallback, useMemo, useState } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../lib/cn";
import { rpc } from "../lib/rpc";

interface RunRes {
  batches: number;
  components: number;
  output: string;
}

interface Props {
  appendOutput?: (text: string) => void;
}

export function LeebHardnessTool({ appendOutput }: Props = {}) {
  const [excelPath, setExcelPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [angle, setAngle] = useState(0);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunRes | null>(null);
  const [error, setError] = useState<string | null>(null);

  const defaultOutput = useMemo(() => {
    if (!excelPath) return "";
    const sep = excelPath.includes("\\") ? "\\" : "/";
    const idx = excelPath.lastIndexOf(sep);
    const dir = idx > 0 ? excelPath.slice(0, idx) : "";
    const file = idx > 0 ? excelPath.slice(idx + 1) : excelPath;
    const stem = file.replace(/\.[^.]+$/, "");
    return `${dir}${sep}${stem}_结果.xlsx`;
  }, [excelPath]);

  const pickExcel = useCallback(async () => {
    const sel = await openDialog({
      title: "选择里氏硬度 Excel",
      multiple: false,
      filters: [{ name: "Excel", extensions: ["xlsx", "xls"] }],
    });
    if (typeof sel === "string") setExcelPath(sel);
  }, []);

  const pickOutput = useCallback(async () => {
    const sel = await openDialog({
      title: "选择输出 Excel 文件",
      multiple: false,
      defaultPath: defaultOutput || undefined,
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
    });
    if (typeof sel === "string") setOutputPath(sel);
  }, [defaultOutput]);

  const canRun = !!excelPath && !running;

  const handleRun = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const params: Record<string, unknown> = {
        input_xlsx: excelPath,
        angle_degrees: angle,
      };
      if (outputPath.trim()) params.output_xlsx = outputPath.trim();
      const res = await rpc<RunRes>("leeb.run", params);
      setResult(res);
      appendOutput?.(
        `[${new Date().toLocaleTimeString()}] leeb: ${res.batches} 批 / ${res.components} 构件 → ${res.output}`,
      );
    } catch (e) {
      setError(String(e));
      appendOutput?.(`[${new Date().toLocaleTimeString()}] leeb 失败: ${String(e)}`);
    } finally {
      setRunning(false);
    }
  }, [canRun, excelPath, outputPath, angle, appendOutput]);

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="px-6 pt-5 pb-3 border-b border-vscode-border">
        <h1 className="text-lg font-medium text-vscode-text flex items-center gap-2">
          <i className="codicon codicon-symbol-numeric !text-[18px]" />
          里氏硬度 INSP-001
        </h1>
        <p className="mt-1 text-xs text-vscode-text-dim">
          读检测数据 Excel → 套规范库（GB/T 17394 等）→ 算硬度 → 写结果 Excel（每批 2 sheet）。
        </p>
      </div>

      <div className="px-6 py-4 space-y-4 max-w-3xl">
        <Field label="输入 Excel">
          <Picker value={excelPath} onPick={pickExcel} placeholder="尚未选择" />
        </Field>

        <Field label="输出 Excel 路径" hint="留空 = <输入同级>/<stem>_结果.xlsx">
          <Picker
            value={outputPath || defaultOutput}
            onPick={pickOutput}
            placeholder="（选 Excel 后自动）"
            muted={!outputPath}
            extra={outputPath ? <ResetBtn onClick={() => setOutputPath("")} /> : undefined}
          />
        </Field>

        <Field label="默认测量角度（度）" hint="构件未指定角度时用此值；常用 0 / 90 / 180">
          <input
            type="number"
            value={angle}
            onChange={(e) => setAngle(parseFloat(e.target.value || "0"))}
            className="w-32 bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
          />
        </Field>

        <div className="pt-2 flex items-center gap-3">
          <RunBtn running={running} disabled={!canRun} onClick={handleRun}>
            {running ? "正在计算…" : "开始计算"}
          </RunBtn>
          {!excelPath && <span className="text-xs text-vscode-text-dim">请先选 Excel</span>}
        </div>
      </div>

      {(result || error) && (
        <div className="px-6 py-4 border-t border-vscode-border max-w-3xl">
          {error && (
            <div className="text-xs text-red-400 whitespace-pre-wrap">
              <i className="codicon codicon-error !text-[14px] mr-1" />
              {error}
            </div>
          )}
          {result && (
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2 text-sm text-green-400">
                <i className="codicon codicon-pass !text-[16px]" />
                <span>计算完成</span>
                <span className="text-vscode-text-dim">
                  {result.batches} 批 / {result.components} 构件
                </span>
              </div>
              <div className="text-vscode-text-dim">
                输出：
                <button
                  type="button"
                  onClick={() => openPath(result.output).catch(console.error)}
                  className="ml-1 text-vscode-focus hover:underline"
                >
                  {result.output}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 共享小组件（也被 PdfToolsTool / Word2PdfTool 用） ──
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
      <div className="text-[11px] uppercase tracking-wider text-vscode-text-dim mb-1">
        {label}
      </div>
      {children}
      {hint && <div className="mt-1 text-[11px] text-vscode-text-faint">{hint}</div>}
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
          "flex-1 bg-vscode-input border border-vscode-border px-2 py-1 text-xs rounded-[2px] truncate",
          muted ? "text-vscode-text-dim italic" : "text-vscode-text",
        )}
      />
      <button
        type="button"
        onClick={onPick}
        className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1 shrink-0"
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
      className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1 shrink-0"
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
        "px-4 py-1.5 text-xs rounded-[2px] flex items-center gap-2",
        !disabled
          ? "bg-vscode-button hover:bg-vscode-button-hover text-white"
          : "bg-[#3a3a3a] text-vscode-text-dim cursor-not-allowed",
      )}
    >
      {running && <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />}
      {children}
    </button>
  );
}
