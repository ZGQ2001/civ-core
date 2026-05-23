/**
 * pdf_tools 工具页主区：顶部 mode 切换 + 文件操作 + 跑；中间 PDF 信息列表；底部结果。
 * 右侧参数（输出路径 / 模板 / 表达式）在 SettingsForm。
 */
import { useCallback } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { openPath } from '@tauri-apps/plugin-opener';

import { cn } from '../../lib/cn';
import { usePdfTools } from './controller';
import { MODE_LABELS, type Mode, type PdfFileInfo } from './types';

interface Props {
  appendOutput?: (text: string) => void;
}

export function PdfToolsPage({ appendOutput }: Props = {}) {
  const c = usePdfTools();

  const pickMergeInputs = useCallback(async () => {
    const sel = await openDialog({
      title: '选择要合并的 PDF（可多选）',
      multiple: true,
      filters: [{ name: 'PDF', extensions: ['pdf'] }],
    });
    if (Array.isArray(sel)) c.addMergeInputs(sel);
    else if (typeof sel === 'string') c.addMergeInputs([sel]);
  }, [c]);

  const pickSplitInput = useCallback(async () => {
    const sel = await openDialog({
      title: '选择要拆分的 PDF',
      filters: [{ name: 'PDF', extensions: ['pdf'] }],
    });
    if (typeof sel === 'string') c.setSplitInput(sel);
  }, [c]);

  const handleRun = useCallback(async () => {
    const r = await c.run();
    if (!r) return;
    const ts = new Date().toLocaleTimeString();
    if (r.kind === 'merge') {
      appendOutput?.(`[${ts}] pdf merge: ${r.res.count} 个 → ${r.res.output}`);
    } else if (r.kind === 'split') {
      appendOutput?.(`[${ts}] pdf ${c.mode}: 拆出 ${r.res.count} 个文件`);
    } else if (r.kind === 'error') {
      appendOutput?.(`[${ts}] pdf ${c.mode} 失败: ${r.message}`);
    }
  }, [c, appendOutput]);

  // canRun 按 mode 算
  const canRun =
    !c.running &&
    (c.mode === 'merge'
      ? c.mergeInputs.length >= 1 && !!c.mergeOutput
      : !!c.splitInput &&
        !!c.splitOutDir &&
        (c.mode !== 'split_by_ranges' || !!c.splitExpr.trim()));

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：mode 切换 + 操作 + 跑 */}
      <div className="border-vscode-border space-y-2 border-b px-6 pt-4 pb-3">
        <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
          <i className="codicon codicon-file-pdf !text-[16px]" />
          PDF 工具
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          {(Object.entries(MODE_LABELS) as Array<[Mode, string]>).map(
            ([id, label]) => (
              <ModeTab
                key={id}
                label={label}
                active={c.mode === id}
                onClick={() => c.setMode(id)}
              />
            ),
          )}
          <span className="text-vscode-text-faint mx-1">·</span>
          {c.mode === 'merge' ? (
            <button
              type="button"
              onClick={pickMergeInputs}
              className="border-vscode-border flex items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
            >
              <i className="codicon codicon-add !text-[12px]" />
              添加 PDF…
            </button>
          ) : (
            <button
              type="button"
              onClick={pickSplitInput}
              className="border-vscode-border flex items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
            >
              <i className="codicon codicon-folder-opened !text-[12px]" />选
              PDF…
            </button>
          )}
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
              {c.running
                ? c.mode === 'merge'
                  ? '合并中…'
                  : '拆分中…'
                : c.mode === 'merge'
                  ? '开始合并'
                  : '开始拆分'}
            </button>
          </div>
        </div>
      </div>

      {/* 中间：PDF 列表 */}
      <div className="min-h-0 flex-1 overflow-hidden bg-[#252525]">
        <PreviewPane />
      </div>

      {/* 结果 / 错误 */}
      {(c.mergeResult || c.splitResult || c.runError) && (
        <div className="border-vscode-border max-h-[200px] overflow-auto border-t px-6 py-3 text-xs">
          {c.runError && (
            <div className="whitespace-pre-wrap text-red-400">
              <i className="codicon codicon-error mr-1 !text-[14px]" />
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
                onClick={() =>
                  openPath(c.mergeResult!.output).catch(console.error)
                }
                className="text-vscode-focus ml-auto truncate hover:underline"
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
                <summary className="cursor-pointer hover:text-white">
                  查看清单
                </summary>
                <ul className="mt-1 ml-4 space-y-0.5">
                  {c.splitResult.written.map((p) => (
                    <li key={p}>
                      <button
                        type="button"
                        onClick={() => openPath(p).catch(console.error)}
                        className="text-vscode-focus truncate text-left hover:underline"
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
        'rounded-[2px] border px-3 py-1 text-xs',
        active
          ? 'bg-vscode-selected border-vscode-focus text-white'
          : 'border-vscode-border text-vscode-text-dim hover:bg-vscode-hover bg-transparent hover:text-white',
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
      <div className="flex h-full items-center justify-center px-8 text-center">
        <div>
          <i className="codicon codicon-file-pdf text-vscode-text-faint !text-[48px]" />
          <div className="text-vscode-text-dim mt-3 text-sm">
            {c.mode === 'merge'
              ? '请添加要合并的 PDF（按顺序）'
              : '请选要拆分的 PDF'}
          </div>
          <div className="text-vscode-text-faint mt-1 text-xs">
            选好后会显示每个文件的页数和大小
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

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-vscode-border text-vscode-text-dim flex shrink-0 items-center border-b px-4 py-2 text-xs">
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
      <div className="min-h-0 flex-1 space-y-1 overflow-auto px-4 py-2">
        {c.previewInfos.map((info, i) => (
          <PdfInfoRow key={`${info.path}_${i}`} info={info} index={i} />
        ))}
      </div>
    </div>
  );
}

function PdfInfoRow({ info, index }: { info: PdfFileInfo; index: number }) {
  const c = usePdfTools();
  const isMerge = c.mode === 'merge';
  const filename = info.path.split(/[\\/]/).pop() ?? info.path;

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-[2px] border px-2 py-1.5 text-xs',
        info.error
          ? 'border-red-900 bg-[#3a1f1f]'
          : 'hover:border-vscode-border border-[#3a3a3a] bg-[#2a2a2a]',
      )}
    >
      <span className="text-vscode-text-faint w-6 text-right">
        {index + 1}.
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-vscode-text truncate" title={info.path}>
          {filename}
        </div>
        {info.error ? (
          <div className="truncate text-[11px] text-red-400" title={info.error}>
            {info.error}
          </div>
        ) : (
          <div className="text-vscode-text-faint text-[11px]">
            {info.pages !== undefined && `${info.pages} 页`}
            {info.size_kb !== undefined && ` · ${info.size_kb.toFixed(1)} KB`}
          </div>
        )}
      </div>
      {isMerge && (
        <div className="flex shrink-0 items-center gap-0.5">
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
        'text-vscode-text-dim flex h-6 w-6 items-center justify-center rounded',
        disabled
          ? 'cursor-not-allowed opacity-30'
          : danger
            ? 'hover:bg-vscode-hover hover:text-red-400'
            : 'hover:bg-vscode-hover hover:text-white',
      )}
    >
      <i className={`codicon codicon-${icon} !text-[12px]`} />
    </button>
  );
}
