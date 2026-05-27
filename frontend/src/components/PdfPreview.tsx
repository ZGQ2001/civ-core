/**
 * PDF 预览器：react-pdf + pdf.js。本地路径走 Tauri asset 协议（见 tauri.conf.json）。
 *
 * 设计：
 *  - 只渲染当前页，翻页按钮在底部
 *  - 自适应容器宽度（ResizeObserver 监容器）
 *  - 不渲染 text / annotation layer：纯预览，省 CPU
 *
 * worker 通过 Vite ?url 拿到 hashed 资源 URL，运行时设到 pdfjs.GlobalWorkerOptions。
 */
import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { convertFileSrc } from '@tauri-apps/api/core';
import { Document, Page, pdfjs } from 'react-pdf';
import pdfWorkerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

import { cn } from '../lib/cn';

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerSrc;

interface Props {
  /** 本地文件绝对路径；空串/undefined → 显示空状态 */
  path: string | undefined;
  /** 空状态文案 */
  emptyHint?: string;
}

/**
 * Document 的 file prop 我们传字符串 URL，避免每次渲染 new 对象触发 react-pdf 重新加载。
 * memo + 同 path 引用稳定 → 不重复拉 PDF。
 */
function PdfPreviewInner({ path, emptyHint }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [pageNum, setPageNum] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 监容器宽度
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      // 减去左右内边距，给 Page 一个安全宽度
      setContainerWidth(Math.max(200, w - 24));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 切换文件 → 重置页号 / 错误
  useEffect(() => {
    // 切换 path 必然要把页号回归首页、清掉旧错误。这是与 path 派生的状态重置
    /* eslint-disable react-hooks/set-state-in-effect */
    setPageNum(1);
    setNumPages(0);
    setLoadError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [path]);

  const fileUrl = useMemo(
    () => (path ? convertFileSrc(path) : null),
    [path],
  );

  if (!fileUrl) {
    return (
      <div className="flex h-full items-center justify-center px-8 text-center">
        <div className="text-vscode-text-dim text-sm">
          {emptyHint ?? '选好 PDF 后这里会显示预览'}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex h-full flex-col overflow-hidden bg-[#1e1e1e]"
    >
      <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
        <div className="flex justify-center">
          <Document
            file={fileUrl}
            onLoadSuccess={({ numPages: n }) => {
              setNumPages(n);
              setLoadError(null);
            }}
            onLoadError={(err) => {
              setLoadError(err.message || '加载失败');
              setNumPages(0);
            }}
            loading={
              <div className="text-vscode-text-dim py-8 text-xs">
                <i className="codicon codicon-loading codicon-modifier-spin mr-1 !text-[12px]" />
                加载中…
              </div>
            }
            error={
              <div className="max-w-2xl px-4 py-8 text-xs text-red-400">
                <i className="codicon codicon-error mr-1 !text-[14px]" />
                无法打开 PDF
                {loadError && <div className="mt-1">{loadError}</div>}
              </div>
            }
          >
            {numPages > 0 && containerWidth > 0 && (
              <Page
                pageNumber={pageNum}
                width={containerWidth}
                renderTextLayer={false}
                renderAnnotationLayer={false}
                loading={
                  <div className="text-vscode-text-dim py-4 text-xs">
                    渲染第 {pageNum} 页…
                  </div>
                }
              />
            )}
          </Document>
        </div>
      </div>
      {numPages > 0 && (
        <div className="border-vscode-border text-vscode-text-dim flex shrink-0 items-center justify-center gap-2 border-t px-3 py-2 text-xs">
          <PageNavBtn
            icon="chevron-left"
            title="上一页"
            disabled={pageNum <= 1}
            onClick={() => setPageNum((n) => Math.max(1, n - 1))}
          />
          <span className="min-w-[70px] text-center">
            第 {pageNum} / {numPages} 页
          </span>
          <PageNavBtn
            icon="chevron-right"
            title="下一页"
            disabled={pageNum >= numPages}
            onClick={() => setPageNum((n) => Math.min(numPages, n + 1))}
          />
        </div>
      )}
    </div>
  );
}

function PageNavBtn({
  icon,
  title,
  disabled,
  onClick,
}: {
  icon: string;
  title: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex h-6 w-6 items-center justify-center rounded',
        disabled
          ? 'cursor-not-allowed opacity-30'
          : 'hover:bg-vscode-hover hover:text-white',
      )}
    >
      <i className={`codicon codicon-${icon} !text-[14px]`} />
    </button>
  );
}

export const PdfPreview = memo(PdfPreviewInner);
