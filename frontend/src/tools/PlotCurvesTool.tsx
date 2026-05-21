/**
 * 绘曲线图工具页（plot_curves）—— T5 第一个端到端工具页。
 *
 * 流程：选 Excel → 选预设 → （可选）改 sheet/表头行/输出目录 → 跑
 * 后端：plot_curves.list_presets / plot_curves.run（同步阻塞）
 * 进度：第一版同步等待 + 最终统计（流式进度的方案见 PROGRESS T5 决策）
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../lib/cn";
import { rpc } from "../lib/rpc";

interface PresetsRes {
  presets: string[];
  default: string | null;
}

interface FailedItem {
  path: string;
  error: string;
}

interface RunRes {
  written: string[];
  failed: FailedItem[];
  summary: {
    total: number;
    written_count: number;
    failed_count: number;
    skipped_empty_id: number;
    skipped_bad_data: number;
  };
  output_dir: string;
}

export function PlotCurvesTool() {
  const [presets, setPresets] = useState<string[]>([]);
  const [presetLoadError, setPresetLoadError] = useState<string | null>(null);
  const [preset, setPreset] = useState<string>("");
  const [excelPath, setExcelPath] = useState<string>("");
  const [sheet, setSheet] = useState<string>("");
  const [headerRow, setHeaderRow] = useState<number>(1);
  const [outputDir, setOutputDir] = useState<string>(""); // 空=用默认
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunRes | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // 启动时拉一次预设列表
  useEffect(() => {
    (async () => {
      try {
        const r = await rpc<PresetsRes>("plot_curves.list_presets");
        setPresets(r.presets);
        if (r.default) setPreset(r.default);
      } catch (e) {
        setPresetLoadError(String(e));
      }
    })();
  }, []);

  const excelDir = useMemo(() => {
    if (!excelPath) return "";
    const idx = Math.max(excelPath.lastIndexOf("\\"), excelPath.lastIndexOf("/"));
    return idx > 0 ? excelPath.slice(0, idx) : "";
  }, [excelPath]);

  // 显示用：输出目录用户没选时显示默认占位（<excel 同级>/曲线图）
  const outputDirDisplay = outputDir || (excelDir ? `${excelDir}\\曲线图` : "（选 Excel 后自动）");

  const pickExcel = useCallback(async () => {
    try {
      const sel = await openDialog({
        title: "选择 Excel 数据文件",
        multiple: false,
        filters: [{ name: "Excel", extensions: ["xlsx", "xls"] }],
      });
      if (typeof sel === "string") setExcelPath(sel);
    } catch (e) {
      console.error("选 Excel 失败:", e);
    }
  }, []);

  const pickOutputDir = useCallback(async () => {
    try {
      const sel = await openDialog({
        title: "选择输出目录",
        directory: true,
        multiple: false,
      });
      if (typeof sel === "string") setOutputDir(sel);
    } catch (e) {
      console.error("选输出目录失败:", e);
    }
  }, []);

  const canRun = !!excelPath && !!preset && !running;

  const handleRun = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      const params: Record<string, unknown> = {
        excel_path: excelPath,
        preset,
        header_row: headerRow,
      };
      if (sheet.trim()) params.sheet = sheet.trim();
      if (outputDir.trim()) params.output_dir = outputDir.trim();
      const res = await rpc<RunRes>("plot_curves.run", params);
      setResult(res);
    } catch (e) {
      setRunError(String(e));
    } finally {
      setRunning(false);
    }
  }, [canRun, excelPath, preset, sheet, headerRow, outputDir]);

  return (
    <div className="flex h-full flex-col overflow-auto">
      {/* 工具页头 */}
      <div className="px-6 pt-5 pb-3 border-b border-vscode-border">
        <h1 className="text-lg font-medium text-vscode-text flex items-center gap-2">
          <i className="codicon codicon-graph-line !text-[18px]" />
          绘曲线图
        </h1>
        <p className="mt-1 text-xs text-vscode-text-dim">
          读 Excel → 套预设 → 批量导出 PNG。
        </p>
      </div>

      {/* 表单 */}
      <div className="px-6 py-4 space-y-4 max-w-3xl">
        <Field label="输入 Excel">
          <div className="flex gap-2">
            <input
              type="text"
              value={excelPath}
              readOnly
              placeholder="尚未选择"
              className="flex-1 bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px] truncate"
            />
            <Btn onClick={pickExcel} icon="folder-opened">选择…</Btn>
          </div>
        </Field>

        <Field label="预设" hint={presetLoadError ? `加载失败：${presetLoadError}` : undefined}>
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value)}
            disabled={presets.length === 0}
            className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
          >
            {presets.length === 0 && <option value="">（无可用预设）</option>}
            {presets.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Sheet 名" hint="留空 = 第一个 sheet">
            <input
              type="text"
              value={sheet}
              onChange={(e) => setSheet(e.target.value)}
              placeholder="（默认第一个）"
              className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
            />
          </Field>
          <Field label="表头行（1-based）">
            <input
              type="number"
              min={1}
              value={headerRow}
              onChange={(e) => setHeaderRow(Math.max(1, parseInt(e.target.value || "1", 10)))}
              className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
            />
          </Field>
        </div>

        <Field label="输出目录">
          <div className="flex gap-2">
            <input
              type="text"
              value={outputDirDisplay}
              readOnly
              className={cn(
                "flex-1 bg-vscode-input border border-vscode-border px-2 py-1 text-xs rounded-[2px] truncate",
                outputDir ? "text-vscode-text" : "text-vscode-text-dim italic",
              )}
            />
            <Btn onClick={pickOutputDir} icon="folder">自定义…</Btn>
            {outputDir && <Btn onClick={() => setOutputDir("")} icon="discard">回到默认</Btn>}
          </div>
        </Field>

        {/* 跑按钮 */}
        <div className="pt-2 flex items-center gap-3">
          <button
            type="button"
            disabled={!canRun}
            onClick={handleRun}
            className={cn(
              "px-4 py-1.5 text-xs rounded-[2px] flex items-center gap-2",
              canRun
                ? "bg-vscode-button hover:bg-vscode-button-hover text-white"
                : "bg-[#3a3a3a] text-vscode-text-dim cursor-not-allowed",
            )}
          >
            {running && <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />}
            {running ? "正在批量出图…" : "开始批量出图"}
          </button>
          {!excelPath && <span className="text-xs text-vscode-text-dim">请先选 Excel</span>}
        </div>
      </div>

      {/* 结果区 */}
      {(result || runError) && (
        <div className="px-6 py-4 border-t border-vscode-border max-w-3xl">
          {runError && (
            <div className="text-xs text-red-400 whitespace-pre-wrap">
              <i className="codicon codicon-error !text-[14px] mr-1" />
              {runError}
            </div>
          )}
          {result && <ResultPanel result={result} />}
        </div>
      )}
    </div>
  );
}

function ResultPanel({ result }: { result: RunRes }) {
  const { summary, written, failed, output_dir } = result;
  const ok = summary.failed_count === 0;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <i
          className={cn(
            "codicon !text-[16px]",
            ok ? "codicon-pass text-green-400" : "codicon-warning text-yellow-400",
          )}
        />
        <span className={ok ? "text-green-400" : "text-yellow-400"}>
          {ok ? "全部成功" : "部分失败"}
        </span>
        <span className="text-vscode-text-dim text-xs">
          已写 {summary.written_count} / 失败 {summary.failed_count}
          {(summary.skipped_empty_id > 0 || summary.skipped_bad_data > 0) && (
            <> · 跳过空ID {summary.skipped_empty_id} / 跳过缺数据 {summary.skipped_bad_data}</>
          )}
        </span>
      </div>

      <div className="text-xs text-vscode-text-dim flex items-center gap-2">
        <span>输出目录：</span>
        <button
          type="button"
          onClick={() => openPath(output_dir).catch(console.error)}
          className="text-vscode-focus hover:underline truncate"
          title={output_dir}
        >
          {output_dir}
        </button>
      </div>

      {written.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-vscode-text-dim hover:text-vscode-text">
            已写出 {written.length} 个文件（点开查看）
          </summary>
          <ul className="mt-2 ml-4 space-y-0.5">
            {written.map((p) => (
              <li key={p}>
                <button
                  type="button"
                  onClick={() => openPath(p).catch(console.error)}
                  className="text-vscode-focus hover:underline truncate text-left"
                  title={p}
                >
                  {p.split(/[\\/]/).pop()}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {failed.length > 0 && (
        <details className="text-xs" open>
          <summary className="cursor-pointer text-red-400">
            失败 {failed.length} 项
          </summary>
          <ul className="mt-2 ml-4 space-y-1">
            {failed.map((f) => (
              <li key={f.path} className="text-vscode-text-dim">
                <div className="truncate" title={f.path}>{f.path.split(/[\\/]/).pop()}</div>
                <div className="text-red-400 ml-2">{f.error}</div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Field({
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

function Btn({
  onClick,
  icon,
  children,
}: {
  onClick: () => void;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1 shrink-0"
    >
      <i className={`codicon codicon-${icon} !text-[12px]`} />
      {children}
    </button>
  );
}
