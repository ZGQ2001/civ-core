/**
 * word2pdf 工具页主区：顶部添加 docx + 跑；中间 Word 文件信息列表；底部结果。
 * 右侧参数（输出目录）在 SettingsForm。
 */
import { useCallback } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { openPath } from '@tauri-apps/plugin-opener';

import { cn } from '../../lib/cn';
import { useWord2Pdf } from './controller';
import type { DocxFileInfo } from './types';

interface Props {
  appendOutput?: (text: string) => void;
}

export function Word2PdfPage({ appendOutput }: Props = {}) {
  const c = useWord2Pdf();

  const addDocs = useCallback(async () => {
    const sel = await openDialog({
      title: '选择 Word 文件（可多选）',
      multiple: true,
      filters: [{ name: 'Word', extensions: ['docx', 'doc'] }],
    });
    if (Array.isArray(sel)) c.addInputs(sel);
    else if (typeof sel === 'string') c.addInputs([sel]);
  }, [c]);

  const handleRun = useCallback(async () => {
    const r = await c.run();
    if (!r) return;
    const ts = new Date().toLocaleTimeString();
    if (r.kind === 'ok') {
      appendOutput?.(
        `[${ts}] word2pdf: 成功 ${r.res.written.length} / 失败 ${r.res.failed.length} (共 ${r.res.total})`,
      );
    } else {
      appendOutput?.(`[${ts}] word2pdf 失败: ${r.message}`);
    }
  }, [c, appendOutput]);

  const canRun = !c.running && c.inputs.length >= 1 && !!c.outDir;

  return (
    <div className="flex h-full flex-col">
      <div className="border-vscode-border space-y-2 border-b px-6 pt-4 pb-3">
        <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
          <i className="codicon codicon-file-binary !text-[16px]" />
          Word → PDF 批量转换
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={addDocs}
            className="border-vscode-border flex items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
          >
            <i className="codicon codicon-add !text-[12px]" />
            添加 Word…
          </button>
          {c.inputs.length > 0 && (
            <button
              type="button"
              onClick={c.clearInputs}
              className="border-vscode-border flex items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
            >
              <i className="codicon codicon-clear-all !text-[12px]" />
              清空
            </button>
          )}
          <span className="text-vscode-text-faint text-xs">
            （走 COM 单进程：需装 Microsoft Word 或 WPS）
          </span>
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
              {c.running ? '转换中…' : '开始转换'}
            </button>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden bg-[#252525]">
        <PreviewPane />
      </div>

      {(c.result || c.runError) && (
        <div className="border-vscode-border max-h-[200px] space-y-2 overflow-auto border-t px-6 py-3 text-xs">
          {c.runError && (
            <div className="whitespace-pre-wrap text-red-400">
              <i className="codicon codicon-error mr-1 !text-[14px]" />
              {c.runError}
            </div>
          )}
          {c.result && (
            <>
              <div className="flex items-center gap-2">
                <i
                  className={cn(
                    'codicon !text-[14px]',
                    c.result.failed.length === 0
                      ? 'codicon-pass text-green-400'
                      : 'codicon-warning text-yellow-400',
                  )}
                />
                <span
                  className={
                    c.result.failed.length === 0
                      ? 'text-green-400'
                      : 'text-yellow-400'
                  }
                >
                  {c.result.failed.length === 0 ? '全部成功' : '部分失败'}
                </span>
                <span className="text-vscode-text-dim">
                  成功 {c.result.written.length} / 失败 {c.result.failed.length}{' '}
                  / 共 {c.result.total}
                </span>
              </div>
              {c.result.written.length > 0 && (
                <details className="text-vscode-text-dim">
                  <summary className="cursor-pointer hover:text-white">
                    成功 {c.result.written.length} 个
                  </summary>
                  <ul className="mt-1 ml-4 space-y-0.5">
                    {c.result.written.map((p) => (
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
              )}
              {c.result.failed.length > 0 && (
                <details className="text-vscode-text-dim" open>
                  <summary className="cursor-pointer text-red-400">
                    失败 {c.result.failed.length} 个
                  </summary>
                  <ul className="mt-1 ml-4 space-y-1">
                    {c.result.failed.map((f) => (
                      <li key={f.path}>
                        <div className="truncate" title={f.path}>
                          {f.path.split(/[\\/]/).pop()}
                        </div>
                        <div className="ml-2 text-red-400">{f.error}</div>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function PreviewPane() {
  const c = useWord2Pdf();

  if (c.previewInfos.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-8 text-center">
        <div>
          <i className="codicon codicon-file-binary text-vscode-text-faint !text-[48px]" />
          <div className="text-vscode-text-dim mt-3 text-sm">
            请添加要转换的 Word 文件
          </div>
          <div className="text-vscode-text-faint mt-1 text-xs">
            选好后会显示每个文件的段落数 / 大小（若有页数缓存也会显示）
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
        <span>{c.previewInfos.length} 个 Word 文件</span>
        {c.previewLoading && (
          <span className="ml-3 flex items-center gap-1">
            <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
            更新中…
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1 space-y-1 overflow-auto px-4 py-2">
        {c.previewInfos.map((info, i) => (
          <DocInfoRow key={`${info.path}_${i}`} info={info} index={i} />
        ))}
      </div>
    </div>
  );
}

function DocInfoRow({ info, index }: { info: DocxFileInfo; index: number }) {
  const c = useWord2Pdf();
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
            {info.paragraphs !== undefined && `${info.paragraphs} 段`}
            {info.pages !== undefined && ` · ${info.pages} 页`}
            {info.size_kb !== undefined && ` · ${info.size_kb.toFixed(1)} KB`}
          </div>
        )}
      </div>
      <button
        type="button"
        title="移除"
        onClick={() => c.removeAt(index)}
        className="text-vscode-text-dim hover:bg-vscode-hover flex h-6 w-6 items-center justify-center rounded hover:text-red-400"
      >
        <i className="codicon codicon-close !text-[12px]" />
      </button>
    </div>
  );
}
