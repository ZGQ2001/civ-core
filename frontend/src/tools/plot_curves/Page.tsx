/**
 * plot_curves 工具页主区：顶部操作行 + 实时预览图 + 行号切换 + 结果区。
 * 所有 state 走 usePlotCurves Context；调参表单在底部 Panel（SettingsForm.tsx）。
 */
import { useCallback, useEffect, useState } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../../lib/cn";
import { usePlotCurves } from "./controller";

interface Props {
  appendOutput?: (text: string) => void;
}

export function PlotCurvesPage({ appendOutput }: Props = {}) {
  const c = usePlotCurves();
  // 对照视图：true=图+表左右并排，false=图全宽 + 数据表折叠在下方
  const [compareView, setCompareView] = useState(false);

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
    const r = await c.run();
    if (r) {
      const ts = new Date().toLocaleTimeString();
      appendOutput?.(
        [
          `[${ts}] plot_curves: 曲线=${c.preset}  输入=${c.excelPath}`,
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
              曲线已被调参（运行 / 预览均用编辑版）
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
          <select
            value={c.sheet}
            onChange={(e) => c.setSheet(e.target.value)}
            disabled={!c.excelPath || c.sheetsLoading || c.sheets.length === 0}
            title={
              c.sheetsError
                ? `读 sheet 失败: ${c.sheetsError}`
                : c.sheetsLoading
                  ? "正在读 sheet 列表…"
                  : "下拉选择要绘图的 sheet"
            }
            className="bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px] min-w-[8rem] max-w-[16rem]"
          >
            {!c.excelPath && <option value="">（先选 Excel）</option>}
            {c.excelPath && c.sheetsLoading && <option value="">（加载中…）</option>}
            {c.excelPath && !c.sheetsLoading && c.sheets.length === 0 && (
              <option value="">{c.sheetsError ? "（读取失败）" : "（无 sheet）"}</option>
            )}
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
          <span className="text-vscode-text-faint">·</span>
          <label className="text-xs text-vscode-text-dim">曲线:</label>
          <select
            value={c.preset}
            onChange={(e) => c.setPreset(e.target.value)}
            disabled={c.presets.length === 0}
            title={
              c.currentSource === "system"
                ? '内置曲线（只读，可"另存为"再改）'
                : "我的曲线（可改可删）"
            }
            className="bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
          >
            {c.presets.length === 0 && <option value="">（无可用）</option>}
            {c.presets.map((p) => (
              <option key={p} value={p}>
                {c.presetSources[p] === "system" ? "[内置] " : "[我的] "}
                {p}
              </option>
            ))}
          </select>
          <PresetCrudButtons />
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
          <div className="text-xs text-red-400">曲线加载失败：{c.presetLoadError}</div>
        )}
      </div>

      {/* 中间：预览图（可切换对照视图） */}
      <div className="flex-1 min-h-0 overflow-hidden bg-[#252525]">
        <PreviewPane compareView={compareView} onToggleCompareView={() => setCompareView(v => !v)} />
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

function PreviewPane({
  compareView,
  onToggleCompareView,
}: {
  compareView: boolean;
  onToggleCompareView: () => void;
}) {
  const c = usePlotCurves();

  if (!c.excelPath) {
    return (
      <div className="flex h-full items-center justify-center text-center px-8">
        <div>
          <i className="codicon codicon-graph !text-[48px] text-vscode-text-faint" />
          <div className="mt-3 text-sm text-vscode-text-dim">请先选 Excel 数据文件</div>
          <div className="mt-1 text-xs text-vscode-text-faint">
            选好后会实时预览第 1 行数据的图
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

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 顶部工具条：行翻页 + 跳转 + 对照开关 */}
      <RowNavBar compareView={compareView} onToggleCompareView={onToggleCompareView} />

      {/* 图区域：始终在上面，占满剩余高度 */}
      <div className="flex-1 min-h-0 flex flex-col items-center overflow-auto py-3">
        <PreviewImage />
      </div>

      {/* 对照视图开启时：底部紧凑数据条带（只露一行高，pill 风横向滚动） */}
      {compareView && <RowDataStrip />}
    </div>
  );
}

/** 顶部行翻页工具条：上一行 / 下一行 / 跳转到第 N 行 / 数据对照开关。 */
function RowNavBar({
  compareView,
  onToggleCompareView,
}: {
  compareView: boolean;
  onToggleCompareView: () => void;
}) {
  const c = usePlotCurves();
  // 跳转用本地 draft，让用户能边输边改；blur / Enter 时提交
  const [jumpDraft, setJumpDraft] = useState("");
  useEffect(() => {
    setJumpDraft(String(c.rowIndex + 1));
  }, [c.rowIndex]);

  const commitJump = () => {
    const n = parseInt(jumpDraft || "0", 10);
    if (Number.isFinite(n) && n >= 1 && n <= c.previewTotal) {
      c.setRowIndex(n - 1);
    } else {
      setJumpDraft(String(c.rowIndex + 1));
    }
  };

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-vscode-border text-xs shrink-0">
      {c.previewTotal > 1 && (
        <>
          <button
            type="button"
            disabled={c.rowIndex === 0}
            onClick={() => c.setRowIndex(c.rowIndex - 1)}
            title="上一行"
            className="px-2 h-6 bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
          >
            <i className="codicon codicon-chevron-left !text-[12px]" />
            上一行
          </button>
          <button
            type="button"
            disabled={c.rowIndex >= c.previewTotal - 1}
            onClick={() => c.setRowIndex(c.rowIndex + 1)}
            title="下一行"
            className="px-2 h-6 bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
          >
            下一行
            <i className="codicon codicon-chevron-right !text-[12px]" />
          </button>
          <span className="text-vscode-text-dim">第</span>
          <input
            type="number"
            min={1}
            max={c.previewTotal}
            value={jumpDraft}
            onChange={(e) => setJumpDraft(e.target.value)}
            onBlur={commitJump}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            }}
            title="输入行号回车跳转"
            className="bg-vscode-input border border-vscode-border px-1.5 h-6 text-xs text-vscode-text rounded-[2px] w-14 text-center"
          />
          <span className="text-vscode-text-dim">/ {c.previewTotal} 行</span>
          {c.previewRowId && (
            <span className="text-vscode-text-dim">
              ・<span className="text-vscode-text">{c.previewRowId}</span>
            </span>
          )}
        </>
      )}
      <button
        type="button"
        onClick={onToggleCompareView}
        title="在图下方显示当前行的所有列值"
        className={cn(
          "ml-auto px-2 h-6 border border-vscode-border rounded-[2px] flex items-center gap-1",
          compareView
            ? "bg-vscode-selected text-white border-vscode-focus"
            : "bg-[#2d2d2d] hover:bg-[#3a3a3a] text-vscode-text-dim hover:text-white",
        )}
      >
        <i className={`codicon !text-[12px] ${compareView ? "codicon-eye" : "codicon-eye-closed"}`} />
        {compareView ? "关闭对照" : "数据对照"}
      </button>
    </div>
  );
}

/** 当前行被图引用的列：pill 风条带、横向滚动、只占一行高。
 *  引用列 = id_column + curves[].points[].var_column；其他列不显示（噪音）。 */
function RowDataStrip() {
  const c = usePlotCurves();
  const rowData = c.previewRowData;

  const referenced = new Set<string>();
  if (c.effectivePreset) {
    if (c.effectivePreset.id_column) referenced.add(c.effectivePreset.id_column);
    for (const curve of c.effectivePreset.curves) {
      for (const pt of curve.points as Array<{ var_column?: string }>) {
        if (pt?.var_column) referenced.add(pt.var_column);
      }
    }
  }

  const visibleKeys = Object.keys(rowData).filter((k) => referenced.has(k));

  return (
    <div className="shrink-0 border-t border-vscode-border bg-[#1a1a1a]">
      <div className="px-3 py-2 overflow-x-auto whitespace-nowrap text-[11px]">
        {Object.keys(rowData).length === 0 ? (
          <span className="text-vscode-text-faint italic">
            （预览渲染好后这里显示图里用到的列）
          </span>
        ) : visibleKeys.length === 0 ? (
          <span className="text-vscode-text-faint italic">
            （这条曲线还没引用任何列；去右侧「曲线」tab 添加数据点）
          </span>
        ) : (
          visibleKeys.map((k) => {
            const v = rowData[k];
            return (
              <span
                key={k}
                title={`${k}: ${v ?? "(空)"}`}
                className="inline-flex items-baseline mr-2 px-2 py-0.5 rounded border bg-vscode-selected/40 border-vscode-focus align-middle"
              >
                <span className="mr-1.5 text-white">{k}</span>
                <span className="text-vscode-text font-mono">
                  {v === null || v === undefined ? (
                    <span className="text-vscode-text-faint italic">—</span>
                  ) : (
                    String(v)
                  )}
                </span>
              </span>
            );
          })
        )}
      </div>
    </div>
  );
}

function PreviewImage() {
  const c = usePlotCurves();
  return (
    <div className="relative">
      {c.previewPng ? (
        <img
          src={`data:image/png;base64,${c.previewPng}`}
          alt={c.previewTitle}
          className={cn(
            "max-w-full bg-white rounded-[2px] shadow-lg transition-opacity",
            c.previewLoading ? "opacity-50" : "opacity-100",
          )}
          style={{ maxHeight: "75vh" }}
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
  );
}

/** 曲线（预设）增删改按钮组。一预设 = 一曲线，所有 UI 文案统一叫"曲线"。 */
function PresetCrudButtons() {
  const c = usePlotCurves();
  const isUser = c.currentSource === "user";

  const handleNewBlank = async () => {
    const name = window.prompt("新建曲线；输入名字：", "新曲线");
    if (!name?.trim()) return;
    // 默认模板：必填字段 + 一条默认曲线（避免用户进 form 看到"还没定义曲线"困惑）
    const blank = {
      id_column: "",
      filename_template: "{id}.png",
      title_template: "{id}",
      x_axis: { label: "X", range: null },
      y_axis: { label: "Y", range: null },
      curves: [
        {
          name: "曲线",
          color: "#1F4FE0",
          marker: "o",
          linewidth: 2,
          markersize: 6,
          points: [],
        },
      ],
    };
    try {
      await c.savePreset(name.trim(), blank as never);
    } catch (e) {
      alert(`新建失败：${String(e)}`);
    }
  };

  const handleSave = async () => {
    if (!c.effectivePreset || !c.preset) return;
    // 内置曲线 + 已编辑 → 强制弹"另存为"；自己的曲线直接覆盖
    if (c.currentSource === "system") {
      const name = window.prompt(
        `当前曲线「${c.preset}」是内置曲线（只读）。\n输入新名字另存为我的曲线：`,
        `${c.preset}（我的）`,
      );
      if (!name?.trim()) return;
      try {
        await c.savePreset(name.trim(), c.effectivePreset);
        alert(`已另存为：${name.trim()}`);
      } catch (e) {
        alert(`保存失败：${String(e)}`);
      }
    } else {
      try {
        await c.savePreset(c.preset, c.effectivePreset);
        alert(`已保存：${c.preset}`);
      } catch (e) {
        alert(`保存失败：${String(e)}`);
      }
    }
  };

  const handleCopy = async () => {
    if (!c.preset) return;
    const name = window.prompt("复制为新曲线；输入新名字：", `${c.preset}（副本）`);
    if (!name?.trim()) return;
    try {
      await c.copyPreset(c.preset, name.trim());
    } catch (e) {
      alert(`复制失败：${String(e)}`);
    }
  };

  const handleRename = async () => {
    if (!c.preset || !isUser) return;
    const name = window.prompt(`重命名「${c.preset}」为：`, c.preset);
    if (!name?.trim() || name.trim() === c.preset) return;
    try {
      await c.renamePreset(c.preset, name.trim());
    } catch (e) {
      alert(`重命名失败：${String(e)}`);
    }
  };

  const handleDelete = async () => {
    if (!c.preset || !isUser) return;
    if (!window.confirm(`确定删除曲线「${c.preset}」？此操作不可撤销。`)) return;
    try {
      await c.deletePreset(c.preset);
    } catch (e) {
      alert(`删除失败：${String(e)}`);
    }
  };

  return (
    <div className="flex items-center gap-1">
      {c.edited && (
        <button
          type="button"
          onClick={handleSave}
          title={
            c.currentSource === "system"
              ? '内置曲线只读 — 将弹出"另存为"'
              : "保存修改到这条曲线"
          }
          className="px-2 py-1 text-xs bg-vscode-button hover:bg-vscode-button-hover text-white rounded-[2px] flex items-center gap-1"
        >
          <i className="codicon codicon-save !text-[12px]" />
          {c.currentSource === "system" ? "另存为…" : "保存"}
        </button>
      )}
      <IconBtn icon="new-file" title="新建曲线（从零开始）" onClick={handleNewBlank} />
      <IconBtn icon="copy" title="复制当前曲线为新曲线" onClick={handleCopy} />
      <IconBtn icon="edit" title={isUser ? "重命名" : "内置曲线不可改名"} onClick={handleRename} disabled={!isUser} />
      <IconBtn icon="trash" title={isUser ? "删除" : "内置曲线不可删"} onClick={handleDelete} disabled={!isUser} danger />
    </div>
  );
}

function IconBtn({
  icon,
  title,
  onClick,
  disabled,
  danger,
}: {
  icon: string;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "h-7 w-7 flex items-center justify-center rounded-[2px] border border-vscode-border transition-colors",
        disabled
          ? "text-vscode-text-faint cursor-not-allowed opacity-50"
          : danger
            ? "text-vscode-text-dim hover:text-red-400 hover:bg-vscode-hover"
            : "text-vscode-text-dim hover:text-white hover:bg-vscode-hover",
      )}
    >
      <i className={`codicon codicon-${icon} !text-[14px]`} />
    </button>
  );
}

