/**
 * data_processing 工具页主区：顶部操作行（含「计算类型」下拉）+ 中间 Excel 前 N 行预览 + 底部结果。
 * 所有状态走 useDataProcessing；右侧参数（输出路径 / 默认角度 / 其他算法特定参数）在 SettingsForm。
 */
import { useCallback } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { openPath } from '@tauri-apps/plugin-opener';

import { cn } from '../../lib/cn';
import { useDataProcessing } from './controller';
import { CALC_TYPE_LABELS, type CalcType, type CellValue } from './types';

interface Props {
  appendOutput?: (text: string) => void;
}

export function DataProcessingPage({ appendOutput }: Props = {}) {
  const c = useDataProcessing();

  const pickExcel = useCallback(async () => {
    const sel = await openDialog({
      title: '选择检测数据 Excel',
      multiple: false,
      filters: [{ name: 'Excel', extensions: ['xlsx', 'xls'] }],
    });
    if (typeof sel === 'string') c.setExcelPath(sel);
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
  const calcOptions = Object.entries(CALC_TYPE_LABELS) as Array<
    [CalcType, string]
  >;

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：计算类型 + 选 Excel + Sheet + 表头行 + 跑 */}
      <div className="border-vscode-border space-y-2 border-b px-6 pt-4 pb-3">
        <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
          <i className="codicon codicon-symbol-method !text-[16px]" />
          数据处理
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-vscode-text-dim text-xs">计算:</label>
          <select
            value={c.calcType}
            onChange={(e) => {
              // 守 select 的 value：理论上 options 只来自 CALC_TYPE_LABELS 的 key，
              // 防御性兜底以防将来 options 改动遗漏 / DevTools 篡改
              const v = e.target.value;
              if (v in CALC_TYPE_LABELS) c.setCalcType(v as CalcType);
            }}
            title="未来会有更多计算类型（钻芯法 / 回弹法 等）"
            className="bg-vscode-input border-vscode-border text-vscode-text rounded-[2px] border px-2 py-1 text-xs"
          >
            {calcOptions.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
          <span className="text-vscode-text-faint">·</span>
          <button
            type="button"
            onClick={pickExcel}
            className="border-vscode-border flex shrink-0 items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
          >
            <i className="codicon codicon-folder-opened !text-[12px]" />选
            Excel…
          </button>
          {c.excelPath && (
            <span
              className="text-vscode-text-dim max-w-[400px] truncate text-xs"
              title={c.excelPath}
            >
              {c.excelPath.split(/[\\/]/).pop()}
            </span>
          )}
          <span className="text-vscode-text-faint">·</span>
          <label className="text-vscode-text-dim text-xs">Sheet:</label>
          <select
            value={c.sheet}
            onChange={(e) => c.setSheet(e.target.value)}
            disabled={!c.excelPath || c.sheets.length === 0}
            className="bg-vscode-input border-vscode-border text-vscode-text max-w-[16rem] min-w-[8rem] rounded-[2px] border px-2 py-1 text-xs"
          >
            {!c.excelPath && <option value="">（先选 Excel）</option>}
            {c.excelPath && c.sheets.length === 0 && (
              <option value="">（加载中…）</option>
            )}
            {c.sheets.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <span className="text-vscode-text-faint">·</span>
          <label className="text-vscode-text-dim text-xs">表头行:</label>
          <input
            type="number"
            min={1}
            value={c.headerRow}
            onChange={(e) =>
              c.setHeaderRow(Math.max(1, parseInt(e.target.value || '1', 10)))
            }
            title="表头所在的 1-based 行号；数据从下一行开始读"
            className="bg-vscode-input border-vscode-border text-vscode-text w-14 rounded-[2px] border px-2 py-1 text-xs"
          />
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              disabled={!canRun}
              onClick={handleRun}
              className={cn(
                'flex items-center gap-1.5 rounded-[2px] px-3 py-1 text-xs',
                canRun
                  ? 'bg-vscode-button hover:bg-vscode-button-hover text-white'
                  : 'text-vscode-text-dim cursor-not-allowed bg-[#3a3a3a]',
              )}
            >
              {c.running && (
                <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
              )}
              {c.running ? '计算中…' : '开始计算'}
            </button>
          </div>
        </div>
      </div>

      {/* 中间：表格预览 */}
      <div className="min-h-0 flex-1 overflow-hidden bg-[#252525]">
        <PreviewPane />
      </div>

      {/* 结果 / 错误（跑完才显示）*/}
      {(c.result || c.runError) && (
        <div className="border-vscode-border max-h-[200px] overflow-auto border-t px-6 py-3 text-xs">
          {c.runError && (
            <div className="whitespace-pre-wrap text-red-400">
              <i className="codicon codicon-error mr-1 !text-[14px]" />
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
                className="text-vscode-focus ml-auto truncate hover:underline"
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
      <div className="flex h-full items-center justify-center px-8 text-center">
        <div>
          <i className="codicon codicon-table text-vscode-text-faint !text-[48px]" />
          <div className="text-vscode-text-dim mt-3 text-sm">
            请先选 Excel 数据文件
          </div>
          <div className="text-vscode-text-faint mt-1 text-xs">
            选好后会显示前 50 行供检查
          </div>
        </div>
      </div>
    );
  }

  if (c.previewError) {
    return (
      <div className="flex h-full items-center justify-center px-8 text-center">
        <div className="max-w-2xl text-xs whitespace-pre-wrap text-red-400">
          <i className="codicon codicon-error mb-2 block !text-[20px]" />
          预览失败：{c.previewError}
        </div>
      </div>
    );
  }

  if (c.previewLoading && c.previewHeaders.length === 0) {
    return (
      <div className="text-vscode-text-dim flex h-full items-center justify-center text-xs">
        <i className="codicon codicon-loading codicon-modifier-spin mr-2 !text-[16px]" />
        正在读取…
      </div>
    );
  }

  if (c.previewHeaders.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-8 text-center">
        <div className="text-vscode-text-dim text-xs">
          <i className="codicon codicon-warning mr-1 !text-[16px]" />
          没有读到表头；检查 Sheet / 表头行号是否正确
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-vscode-border text-vscode-text-dim flex shrink-0 items-center border-b px-4 py-2 text-xs">
        <span>
          预览 {c.previewShownRows} / 共 {c.previewTotalRows} 行 ·{' '}
          {c.previewHeaders.length} 列
        </span>
        {c.previewLoading && (
          <span className="ml-3 flex items-center gap-1">
            <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
            更新中…
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-[11px]">
          <thead className="sticky top-0 bg-[#1f1f1f]">
            <tr>
              <th className="text-vscode-text-faint border-vscode-border w-12 border-b px-2 py-1 text-right font-normal">
                #
              </th>
              {c.previewHeaders.map((h) => (
                <th
                  key={h}
                  className="text-vscode-text border-vscode-border border-b px-2 py-1 text-left font-medium whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {c.previewRows.map((row, i) => (
              <tr
                key={i}
                className={i % 2 === 0 ? 'bg-[#252525]' : 'bg-[#2a2a2a]'}
              >
                <td className="text-vscode-text-faint border-b border-[#333] px-2 py-1 text-right">
                  {i + 1}
                </td>
                {c.previewHeaders.map((h) => (
                  <td
                    key={h}
                    className="text-vscode-text border-b border-[#333] px-2 py-1 whitespace-nowrap"
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
  if (v === null || v === undefined || v === '') {
    return <span className="text-vscode-text-faint italic">—</span>;
  }
  return String(v);
}
