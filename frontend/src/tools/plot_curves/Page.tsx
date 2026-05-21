/**
 * plot_curves 工具页主区：顶部操作行 + 实时预览图 + 行号切换 + 结果区。
 * 所有 state 走 usePlotCurves Context；调参表单在底部 Panel（SettingsForm.tsx）。
 */
import { useCallback } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../../lib/cn";
import { usePlotCurves } from "./controller";

interface Props {
  appendOutput?: (text: string) => void;
}

export function PlotCurvesPage({ appendOutput }: Props = {}) {
  const c = usePlotCurves();

  const pickExcel = useCallback(async () => {
    const sel = await openDialog({
      title: "选择 Excel 数据文件",
      multiple: false,
      filters: [{ name: "Excel", extensions: ["xlsx", "xls"] }],
    });
    if (typeof sel === "string") c.setExcelPath(sel);
  }, [c]);

  const pickOutputDir = useCallback(async () => {
    const sel = await openDialog({
      title: "选择输出目录",
      directory: true,
      multiple: false,
    });
    if (typeof sel === "string") c.setOutputDir(sel);
  }, [c]);

  const handleRun = useCallback(async () => {
    await c.run();
    if (c.result) {
      const ts = new Date().toLocaleTimeString();
      const r = c.result;
      appendOutput?.(
        [
          `[${ts}] plot_curves: 预设=${c.preset}  输入=${c.excelPath}`,
          `  → 已写 ${r.summary.written_count} / 失败 ${r.summary.failed_count} / 跳过空ID ${r.summary.skipped_empty_id} / 跳过缺数据 ${r.summary.skipped_bad_data}`,
          `  → 输出目录: ${r.output_dir}`,
        ].join("\n"),
      );
    }
  }, [c, appendOutput]);

  const canRun = !!c.excelPath && !!c.preset && !c.running;

  return (
    <div className="flex h-full flex-col">
      {/* 顶部一行：Excel + Sheet + 预设 + 跑 */}
      <div className="px-6 pt-4 pb-3 border-b border-vscode-border space-y-2">
        <h1 className="text-base font-medium text-vscode-text flex items-center gap-2">
          <i className="codicon codicon-graph-line !text-[16px]" />
          绘曲线图
          {c.edited && (
            <span className="text-xs text-yellow-400 flex items-center gap-1 ml-2">
              <i className="codicon codicon-edit !text-[12px]" />
              预设已被调参（运行 / 预览均用编辑版）
              <button
                type="button"
                onClick={c.resetPreset}
                className="text-vscode-focus hover:underline ml-1"
              >
                还原
              </button>
            </span>
          )}
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={pickExcel}
            className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1 shrink-0"
          >
            <i className="codicon codicon-folder-opened !text-[12px]" />
            选 Excel…
          </button>
          {c.excelPath && (
            <span className="text-xs text-vscode-text-dim truncate max-w-[400px]" title={c.excelPath}>
              {c.excelPath.split(/[\\/]/).pop()}
            </span>
          )}
          <span className="text-vscode-text-faint">·</span>
          <label className="text-xs text-vscode-text-dim">Sheet:</label>
          <input
            type="text"
            value={c.sheet}
            onChange={(e) => c.setSheet(e.target.value)}
            placeholder="（默认第一个）"
            title="留空 = 用 Excel 的第一个 sheet"
            className="bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px] w-32"
          />
          <span className="text-vscode-text-faint">·</span>
          <label className="text-xs text-vscode-text-dim">表头行:</label>
          <input
            type="number"
            min={1}
            value={c.headerRow}
            onChange={(e) => c.setHeaderRow(Math.max(1, parseInt(e.target.value || "1", 10)))}
            title="表头所在的 1-based 行号；数据从下一行开始读"
            className="bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px] w-14"
          />
          <span className="text-vscode-text-faint">·</span>
          <label className="text-xs text-vscode-text-dim">预设:</label>
          <select
            value={c.preset}
            onChange={(e) => c.setPreset(e.target.value)}
            disabled={c.presets.length === 0}
            className="bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
          >
            {c.presets.length === 0 && <option value="">（无可用）</option>}
            {c.presets.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={pickOutputDir}
              title={c.outputDir || "默认: <Excel 同级>/曲线图/"}
              className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1 shrink-0"
            >
              <i className="codicon codicon-folder !text-[12px]" />
              输出
            </button>
            <button
              type="button"
              disabled={!canRun}
              onClick={handleRun}
              className={cn(
                "px-3 py-1 text-xs rounded-[2px] flex items-center gap-1.5",
                canRun
                  ? "bg-vscode-button hover:bg-vscode-button-hover text-white"
                  : "bg-[#3a3a3a] text-vscode-text-dim cursor-not-allowed",
              )}
            >
              {c.running && (
                <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
              )}
              {c.running ? "出图中…" : "开始批量出图"}
            </button>
          </div>
        </div>
        {c.presetLoadError && (
          <div className="text-xs text-red-400">预设加载失败：{c.presetLoadError}</div>
        )}
      </div>

      {/* 中间：预览图 */}
      <div className="flex-1 min-h-0 overflow-auto bg-[#252525] flex flex-col items-center">
        <PreviewPane />
      </div>

      {/* 结果区（跑完才显示） */}
      {(c.result || c.runError) && (
        <div className="px-6 py-3 border-t border-vscode-border text-xs max-h-[200px] overflow-auto">
          {c.runError && (
            <div className="text-red-400 whitespace-pre-wrap">
              <i className="codicon codicon-error !text-[14px] mr-1" />
              {c.runError}
            </div>
          )}
          {c.result && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <i
                  className={cn(
                    "codicon !text-[14px]",
                    c.result.summary.failed_count === 0
                      ? "codicon-pass text-green-400"
                      : "codicon-warning text-yellow-400",
                  )}
                />
                <span className="text-vscode-text">
                  已写 {c.result.summary.written_count} / 失败 {c.result.summary.failed_count}
                  {(c.result.summary.skipped_empty_id > 0 ||
                    c.result.summary.skipped_bad_data > 0) &&
                    ` · 跳过空ID ${c.result.summary.skipped_empty_id} / 跳过缺数据 ${c.result.summary.skipped_bad_data}`}
                </span>
                <button
                  type="button"
                  onClick={() => openPath(c.result!.output_dir).catch(console.error)}
                  className="ml-auto text-vscode-focus hover:underline"
                >
                  打开输出目录
                </button>
              </div>
              {c.result.failed.length > 0 && (
                <details open>
                  <summary className="cursor-pointer text-red-400">
                    失败 {c.result.failed.length} 项
                  </summary>
                  <ul className="mt-1 ml-4 space-y-0.5 text-vscode-text-dim">
                    {c.result.failed.map((f) => (
                      <li key={f.path}>
                        {f.path.split(/[\\/]/).pop()}：
                        <span className="text-red-400 ml-1">{f.error}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PreviewPane() {
  const c = usePlotCurves();

  if (!c.excelPath) {
    return (
      <div className="flex flex-1 items-center justify-center text-center px-8">
        <div>
          <i className="codicon codicon-graph !text-[48px] text-vscode-text-faint" />
          <div className="mt-3 text-sm text-vscode-text-dim">
            请先选 Excel 数据文件
          </div>
          <div className="mt-1 text-xs text-vscode-text-faint">
            选好后会实时预览第 1 行数据的图
          </div>
        </div>
      </div>
    );
  }

  if (c.previewError) {
    return (
      <div className="flex flex-1 items-center justify-center text-center px-8">
        <div className="max-w-2xl text-xs text-red-400 whitespace-pre-wrap">
          <i className="codicon codicon-error !text-[20px] block mb-2" />
          预览失败：{c.previewError}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center w-full py-4 gap-3">
      {/* 行号切换条 */}
      {c.previewTotal > 1 && (
        <div className="flex items-center gap-2 text-xs text-vscode-text">
          <button
            type="button"
            disabled={c.rowIndex === 0}
            onClick={() => c.setRowIndex(c.rowIndex - 1)}
            className="px-2 h-6 bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
          >
            <i className="codicon codicon-chevron-left !text-[12px]" />
            上一张
          </button>
          <span className="text-vscode-text-dim">
            第 {c.rowIndex + 1} / {c.previewTotal} 张
            {c.previewRowId && <span className="ml-2 text-vscode-text">（{c.previewRowId}）</span>}
          </span>
          <button
            type="button"
            disabled={c.rowIndex >= c.previewTotal - 1}
            onClick={() => c.setRowIndex(c.rowIndex + 1)}
            className="px-2 h-6 bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
          >
            下一张
            <i className="codicon codicon-chevron-right !text-[12px]" />
          </button>
        </div>
      )}

      {/* 图片本体（loading 时半透明） */}
      <div className="relative">
        {c.previewPng ? (
          <img
            src={`data:image/png;base64,${c.previewPng}`}
            alt={c.previewTitle}
            className={cn(
              "max-w-full bg-white rounded-[2px] shadow-lg transition-opacity",
              c.previewLoading ? "opacity-50" : "opacity-100",
            )}
            style={{ maxHeight: "70vh" }}
          />
        ) : (
          <div className="flex h-[300px] w-[500px] items-center justify-center text-vscode-text-dim">
            {c.previewLoading ? (
              <span className="flex items-center gap-2">
                <i className="codicon codicon-loading codicon-modifier-spin !text-[16px]" />
                正在渲染预览…
              </span>
            ) : (
              "等待预览"
            )}
          </div>
        )}
        {c.previewLoading && c.previewPng && (
          <div className="absolute top-2 right-2 px-2 py-0.5 bg-black/60 text-white text-xs rounded">
            <i className="codicon codicon-loading codicon-modifier-spin !text-[10px] mr-1" />
            更新中…
          </div>
        )}
      </div>

      {/* 数据对照：当前 row 的所有列值，预设用到的列高亮 */}
      <RowDataDetails />

      <div className="text-xs text-vscode-text-faint">
        提示：在「底部 Panel · 工具设置」里调参，会实时反映到这张预览。
      </div>
    </div>
  );
}

function RowDataDetails() {
  const c = usePlotCurves();
  const rowData = c.previewRowData;
  const keys = Object.keys(rowData);
  if (keys.length === 0) return null;

  // 算预设引用的列名集合（id_column + curves[].points[].var_column）
  const referenced = new Set<string>();
  if (c.effectivePreset) {
    if (c.effectivePreset.id_column) referenced.add(c.effectivePreset.id_column);
    for (const curve of c.effectivePreset.curves) {
      for (const pt of curve.points as Array<{ var_column?: string }>) {
        if (pt?.var_column) referenced.add(pt.var_column);
      }
    }
  }

  return (
    <details className="w-full max-w-4xl mx-auto px-4">
      <summary className="cursor-pointer text-xs text-vscode-text-dim hover:text-white py-2 flex items-center gap-2">
        <i className="codicon codicon-table !text-[12px]" />
        <span>查看本行原始数据（{keys.length} 列）</span>
        <span className="text-[10px] text-vscode-text-faint">— 高亮列被预设引用</span>
      </summary>
      <div className="mt-2 border border-vscode-border rounded-[2px] overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-[#252525] text-vscode-text-dim">
            <tr>
              <th className="text-left px-3 py-1.5 w-2/5 font-normal">列名</th>
              <th className="text-left px-3 py-1.5 font-normal">值</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k, i) => {
              const v = rowData[k];
              const used = referenced.has(k);
              return (
                <tr
                  key={k}
                  className={cn(
                    i % 2 === 0 ? "bg-vscode-bg" : "bg-[#222]",
                    used && "bg-vscode-selected/30",
                  )}
                >
                  <td className={cn("px-3 py-1 align-top", used ? "text-white font-medium" : "text-vscode-text-dim")}>
                    {used && <i className="codicon codicon-link !text-[10px] mr-1 text-vscode-focus" />}
                    {k}
                  </td>
                  <td className="px-3 py-1 text-vscode-text font-mono align-top break-all">
                    {v === null || v === undefined ? (
                      <span className="text-vscode-text-faint italic">（空）</span>
                    ) : (
                      String(v)
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}
