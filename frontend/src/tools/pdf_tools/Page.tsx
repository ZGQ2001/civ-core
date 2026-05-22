/**
 * pdf_tools 工具页主区：顶部 mode 切换 + 文件操作 + 跑；中间 PDF 信息列表；底部结果。
 * 右侧参数（输出路径 / 模板 / 表达式）在 SettingsForm。
 */
import { useCallback } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../../lib/cn";
import { usePdfTools } from "./controller";
import { MODE_LABELS, type Mode, type PdfFileInfo } from "./types";

interface Props {
  appendOutput?: (text: string) => void;
}

export function PdfToolsPage({ appendOutput }: Props = {}) {
  const c = usePdfTools();

  const pickMergeInputs = useCallback(async () => {
    const sel = await openDialog({
      title: "选择要合并的 PDF（可多选）",
      multiple: true,
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (Array.isArray(sel)) c.addMergeInputs(sel);
    else if (typeof sel === "string") c.addMergeInputs([sel]);
  }, [c]);

  const pickSplitInput = useCallback(async () => {
    const sel = await openDialog({
      title: "选择要拆分的 PDF",
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (typeof sel === "string") c.setSplitInput(sel);
  }, [c]);

  const handleRun = useCallback(async () => {
    const r = await c.run();
    if (!r) return;
    const ts = new Date().toLocaleTimeString();
    if (r.kind === "merge") {
      appendOutput?.(`[${ts}] pdf merge: ${r.res.count} 个 → ${r.res.output}`);
    } else if (r.kind === "split") {
      appendOutput?.(`[${ts}] pdf ${c.mode}: 拆出 ${r.res.count} 个文件`);
    } else if (r.kind === "error") {
      appendOutput?.(`[${ts}] pdf ${c.mode} 失败: ${r.message}`);
    }
  }, [c, appendOutput]);

  // canRun 按 mode 算
  const canRun = !c.running && (
    c.mode === "merge"
      ? c.mergeInputs.length >= 1 && !!c.mergeOutput
      : (!!c.splitInput && !!c.splitOutDir &&
          (c.mode !== "split_by_ranges" || !!c.splitExpr.trim()))
  );

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：mode 切换 + 操作 + 跑 */}
      <div className="px-6 pt-4 pb-3 border-b border-vscode-border space-y-2">
        <h1 className="text-base font-medium text-vscode-text flex items-center gap-2">
          <i className="codicon codicon-file-pdf !text-[16px]" />
          PDF 工具
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          {(Object.entries(MODE_LABELS) as Array<[Mode, string]>).map(([id, label]) => (
            <ModeTab
              key={id}
              label={label}
              active={c.mode === id}
              onClick={() => c.setMode(id)}
            />
          ))}
          <span className="text-vscode-text-faint mx-1">·</span>
          {c.mode === "merge" ? (
            <button
              type="button"
              onClick={pickMergeInputs}
              className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1"
            >
              <i className="codicon codicon-add !text-[12px]" />
              添加 PDF…
            </button>
          ) : (
            <button
              type="button"
              onClick={pickSplitInput}
              className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1"
            >
              <i className="codicon codicon-folder-opened !text-[12px]" />
              选 PDF…
            </button>
          )}
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
              {c.running
                ? c.mode === "merge" ? "合并中…" : "拆分中…"
                : c.mode === "merge" ? "开始合并" : "开始拆分"}
            </button>
          </div>
        </div>
      </div>

      {/* 中间：PDF 列表 */}
      <div className="flex-1 min-h-0 overflow-hidden bg-[#252525]">
        <PreviewPane />
      </div>

      {/* 结果 / 错误 */}
      {(c.mergeResult || c.splitResult || c.runError) && (
        <div className="px-6 py-3 border-t border-vscode-border text-xs max-h-[200px] overflow-auto">
          {c.runError && (
            <div className="text-red-400 whitespace-pre-wrap">
              <i className="codicon codicon-error !text-[14px] mr-1" />
              {c.runError}
            </div>
          )}
          {c.mergeResult && (
            <div className="flex items-center gap-2">
              <i className="codicon codicon-pass !text-[14px] text-green-400" />
              <span className="text-vscode-text">
                合并完成 · {c.mergeResult.count} 个文件
              </span>
              <button
                type="button"
                onClick={() => openPath(c.mergeResult!.output).catch(console.error)}
                className="ml-auto text-vscode-focus hover:underline truncate"
                title={c.mergeResult.output}
              >
                打开输出
              </button>
            </div>
          )}
          {c.splitResult && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <i className="codicon codicon-pass !text-[14px] text-green-400" />
                <span className="text-vscode-text">
                  拆出 {c.splitResult.count} 个文件 · 输出目录 {c.splitOutDir}
                </span>
              </div>
              <details className="text-vscode-text-dim">
                <summary className="cursor-pointer hover:text-white">查看清单</summary>
                <ul className="mt-1 ml-4 space-y-0.5">
                  {c.splitResult.written.map((p) => (
                    <li key={p}>
                      <button
                        type="button"
                        onClick={() => openPath(p).catch(console.error)}
                        className="text-vscode-focus hover:underline truncate text-left"
                      >
                        {p.split(/[\\/]/).pop()}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ModeTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-3 py-1 text-xs rounded-[2px] border",
        active
          ? "bg-vscode-selected border-vscode-focus text-white"
          : "bg-transparent border-vscode-border text-vscode-text-dim hover:text-white hover:bg-vscode-hover",
      )}
    >
      {label}
    </button>
  );
}

function PreviewPane() {
  const c = usePdfTools();

  // 空状态：按 mode 给不同提示
  if (c.previewInfos.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-center px-8">
        <div>
          <i className="codicon codicon-file-pdf !text-[48px] text-vscode-text-faint" />
          <div className="mt-3 text-sm text-vscode-text-dim">
            {c.mode === "merge"
              ? "请添加要合并的 PDF（按顺序）"
              : "请选要拆分的 PDF"}
          </div>
          <div className="mt-1 text-xs text-vscode-text-faint">
            选好后会显示每个文件的页数和大小
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
      <div className="flex items-center px-4 py-2 border-b border-vscode-border text-xs shrink-0 text-vscode-text-dim">
        <span>
          {c.previewInfos.length} 个文件 · 合计 {c.previewTotalPages} 页
        </span>
        {c.previewLoading && (
          <span className="ml-3 flex items-center gap-1">
            <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
            更新中…
          </span>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto px-4 py-2 space-y-1">
        {c.previewInfos.map((info, i) => (
          <PdfInfoRow key={`${info.path}_${i}`} info={info} index={i} />
        ))}
      </div>
    </div>
  );
}

function PdfInfoRow({ info, index }: { info: PdfFileInfo; index: number }) {
  const c = usePdfTools();
  const isMerge = c.mode === "merge";
  const filename = info.path.split(/[\\/]/).pop() ?? info.path;

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-2 py-1.5 rounded-[2px] border text-xs",
        info.error
          ? "bg-[#3a1f1f] border-red-900"
          : "bg-[#2a2a2a] border-[#3a3a3a] hover:border-vscode-border",
      )}
    >
      <span className="w-6 text-right text-vscode-text-faint">{index + 1}.</span>
      <div className="flex-1 min-w-0">
        <div className="text-vscode-text truncate" title={info.path}>
          {filename}
        </div>
        {info.error ? (
          <div className="text-[11px] text-red-400 truncate" title={info.error}>
            {info.error}
          </div>
        ) : (
          <div className="text-[11px] text-vscode-text-faint">
            {info.pages !== undefined && `${info.pages} 页`}
            {info.size_kb !== undefined && ` · ${info.size_kb.toFixed(1)} KB`}
          </div>
        )}
      </div>
      {isMerge && (
        <div className="flex items-center gap-0.5 shrink-0">
          <IconBtn
            icon="chevron-up"
            title="上移"
            onClick={() => c.moveMergeUp(index)}
            disabled={index === 0}
          />
          <IconBtn
            icon="chevron-down"
            title="下移"
            onClick={() => c.moveMergeDown(index)}
            disabled={index === c.mergeInputs.length - 1}
          />
          <IconBtn
            icon="close"
            title="移除"
            onClick={() => c.removeMergeAt(index)}
            danger
          />
        </div>
      )}
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
        "h-6 w-6 flex items-center justify-center rounded text-vscode-text-dim",
        disabled
          ? "opacity-30 cursor-not-allowed"
          : danger
            ? "hover:bg-vscode-hover hover:text-red-400"
            : "hover:bg-vscode-hover hover:text-white",
      )}
    >
      <i className={`codicon codicon-${icon} !text-[12px]`} />
    </button>
  );
}
