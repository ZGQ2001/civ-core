/**
 * data_processing 工具页主区：顶部操作行（含「计算类型」下拉）+ 中间 Excel 前 N 行预览 + 底部结果。
 * 所有状态走 useDataProcessing；右侧参数（输出路径 / 默认角度 / 其他算法特定参数）在 SettingsForm。
 */
import { useCallback } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../../lib/cn";
import { useDataProcessing } from "./controller";
import { CALC_TYPE_LABELS, type CalcType, type CellValue } from "./types";

interface Props {
  appendOutput?: (text: string) => void;
}

export function DataProcessingPage({ appendOutput }: Props = {}) {
  const c = useDataProcessing();

  const pickExcel = useCallback(async () => {
    const sel = await openDialog({
      title: "选择检测数据 Excel",
      multiple: false,
      filters: [{ name: "Excel", extensions: ["xlsx", "xls"] }],
    });
    if (typeof sel === "string") c.setExcelPath(sel);
  }, [c]);

  const handleRun = useCallback(async () => {
    const res = await c.run();
    const calcLabel = CALC_TYPE_LABELS[c.calcType];
    if (res) {
      appendOutput?.(
        `[${new Date().toLocaleTimeString()}] ${calcLabel}: ${res.summary} → ${res.output}`,
      );
    } else if (c.runError) {
      appendOutput?.(
        `[${new Date().toLocaleTimeString()}] ${calcLabel} 失败: ${c.runError}`,
      );
    }
  }, [c, appendOutput]);

  const canRun = !!c.excelPath && !c.running;
  const calcOptions = Object.entries(CALC_TYPE_LABELS) as Array<[CalcType, string]>;

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：计算类型 + 选 Excel + Sheet + 表头行 + 跑 */}
      <div className="px-6 pt-4 pb-3 border-b border-vscode-border space-y-2">
        <h1 className="text-base font-medium text-vscode-text flex items-center gap-2">
          <i className="codicon codicon-symbol-method !text-[16px]" />
          数据处理
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs text-vscode-text-dim">计算:</label>
          <select
            value={c.calcType}
            onChange={(e) => {
              // 守 select 的 value：理论上 options 只来自 CALC_TYPE_LABELS 的 key，
              // 防御性兜底以防将来 options 改动遗漏 / DevTools 篡改
              const v = e.target.value;
              if (v in CALC_TYPE_LABELS) c.setCalcType(v as CalcType);
            }}
            title="未来会有更多计算类型（钻芯法 / 回弹法 等）"
            className="bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
          >
            {calcOptions.map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
          <span className="text-vscode-text-faint">·</span>
          <button
            type="button"
            onClick={pickExcel}
            className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1 shrink-0"
          >
            <i className="codicon codicon-folder-opened !text-[12px]" />
            选 Excel…
          </button>
          {c.excelPath && (
            <span
              className="text-xs text-vscode-text-dim truncate max-w-[400px]"
              title={c.excelPath}
            >
              {c.excelPath.split(/[\\/]/).pop()}
            </span>
          )}
          <span className="text-vscode-text-faint">·</span>
          <label className="text-xs text-vscode-text-dim">Sheet:</label>
          <select
            value={c.sheet}
            onChange={(e) => c.setSheet(e.target.value)}
            disabled={!c.excelPath || c.sheets.length === 0}
            className="bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px] min-w-[8rem] max-w-[16rem]"
          >
            {!c.excelPath && <option value="">（先选 Excel）</option>}
            {c.excelPath && c.sheets.length === 0 && <option value="">（加载中…）</option>}
            {c.sheets.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
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
          <div className="ml-auto flex items-center gap-2">
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
              {c.running ? "计算中…" : "开始计算"}
            </button>
          </div>
        </div>
      </div>

      {/* 中间：表格预览 */}
      <div className="flex-1 min-h-0 overflow-hidden bg-[#252525]">
        <PreviewPane />
      </div>

      {/* 结果 / 错误（跑完才显示）*/}
      {(c.result || c.runError) && (
        <div className="px-6 py-3 border-t border-vscode-border text-xs max-h-[200px] overflow-auto">
          {c.runError && (
            <div className="text-red-400 whitespace-pre-wrap">
              <i className="codicon codicon-error !text-[14px] mr-1" />
              {c.runError}
            </div>
          )}
          {c.result && (
            <div className="flex items-center gap-2">
              <i className="codicon codicon-pass !text-[14px] text-green-400" />
              <span className="text-vscode-text">
                计算完成 · {c.result.summary}
              </span>
              <button
                type="button"
                onClick={() => openPath(c.result!.output).catch(console.error)}
                className="ml-auto text-vscode-focus hover:underline truncate"
                title={c.result.output}
              >
                打开输出 Excel
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PreviewPane() {
  const c = useDataProcessing();

  if (!c.excelPath) {
    return (
      <div className="flex h-full items-center justify-center text-center px-8">
        <div>
          <i className="codicon codicon-table !text-[48px] text-vscode-text-faint" />
          <div className="mt-3 text-sm text-vscode-text-dim">请先选 Excel 数据文件</div>
          <div className="mt-1 text-xs text-vscode-text-faint">
            选好后会显示前 50 行供检查
          </div>
        </div>
      </div>
    );
  }

  if (c.previewError) {
    return (
      <div className="flex h-full items-center justify-center text-center px-8">
        <div className="max-w-2xl text-xs text-red-400 whitespace-pre-wrap">
          <i className="codicon codicon-error !text-[20px] block mb-2" />
          预览失败：{c.previewError}
        </div>
      </div>
    );
  }

  if (c.previewLoading && c.previewHeaders.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-vscode-text-dim text-xs">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[16px] mr-2" />
        正在读取…
      </div>
    );
  }

  if (c.previewHeaders.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-center px-8">
        <div className="text-xs text-vscode-text-dim">
          <i className="codicon codicon-warning !text-[16px] mr-1" />
          没有读到表头；检查 Sheet / 表头行号是否正确
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center px-4 py-2 border-b border-vscode-border text-xs shrink-0 text-vscode-text-dim">
        <span>
          预览 {c.previewShownRows} / 共 {c.previewTotalRows} 行 · {c.previewHeaders.length} 列
        </span>
        {c.previewLoading && (
          <span className="ml-3 flex items-center gap-1">
            <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
            更新中…
          </span>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        <table className="w-full text-[11px] border-collapse">
          <thead className="bg-[#1f1f1f] sticky top-0">
            <tr>
              <th className="text-right px-2 py-1 text-vscode-text-faint font-normal border-b border-vscode-border w-12">
                #
              </th>
              {c.previewHeaders.map((h) => (
                <th
                  key={h}
                  className="text-left px-2 py-1 text-vscode-text font-medium border-b border-vscode-border whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {c.previewRows.map((row, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-[#252525]" : "bg-[#2a2a2a]"}>
                <td className="text-right px-2 py-1 text-vscode-text-faint border-b border-[#333]">
                  {i + 1}
                </td>
                {c.previewHeaders.map((h) => (
                  <td
                    key={h}
                    className="px-2 py-1 text-vscode-text border-b border-[#333] whitespace-nowrap"
                  >
                    {formatCell(row[h])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatCell(v: CellValue | undefined): React.ReactNode {
  if (v === null || v === undefined || v === "") {
    return <span className="text-vscode-text-faint italic">—</span>;
  }
  return String(v);
}
