/**
 * PDF 预览器：react-pdf + pdf.js。本地路径走 Tauri asset 协议（见 tauri.conf.json）。
 *
 * 设计：
 *  - 只渲染当前页，翻页按钮在底部
 *  - 自适应容器宽度（ResizeObserver 监容器）+ 用户缩放（按钮 / Ctrl+滚轮）
 *  - 不渲染 text / annotation layer：纯预览，省 CPU
 *
 * worker 通过 Vite ?url 拿到 hashed 资源 URL，运行时设到 pdfjs.GlobalWorkerOptions。
 */
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.2;

function clampZoom(z: number): number {
  return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
}

function PdfPreviewInner({ path, emptyHint }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [pageNum, setPageNum] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  /** 1 = 适配容器宽度；>1 放大；<1 缩小 */
  const [zoom, setZoom] = useState(1);

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

  // 切换文件 → 重置页号 / 缩放 / 错误
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setPageNum(1);
    setNumPages(0);
    setLoadError(null);
    setZoom(1);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [path]);

  const zoomIn = useCallback(
    () => setZoom((z) => clampZoom(Math.round((z + ZOOM_STEP) * 100) / 100)),
    [],
  );
  const zoomOut = useCallback(
    () => setZoom((z) => clampZoom(Math.round((z - ZOOM_STEP) * 100) / 100)),
    [],
  );
  const zoomReset = useCallback(() => setZoom(1), []);

  // Ctrl + 滚轮缩放（在滚动容器上）
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const dir = e.deltaY > 0 ? -1 : 1;
      setZoom((z) => clampZoom(Math.round((z + dir * ZOOM_STEP) * 100) / 100));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const fileUrl = useMemo(() => (path ? convertFileSrc(path) : null), [path]);

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
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto px-3 py-3">
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
                width={containerWidth * zoom}
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
          <span className="text-vscode-text-faint mx-2">·</span>
          <PageNavBtn
            icon="zoom-out"
            title="缩小"
            disabled={zoom <= ZOOM_MIN + 1e-6}
            onClick={zoomOut}
          />
          <button
            type="button"
            onClick={zoomReset}
            title="恢复 100%（适配宽度）"
            className="hover:bg-vscode-hover min-w-[48px] rounded px-1 text-center hover:text-white"
          >
            {Math.round(zoom * 100)}%
          </button>
          <PageNavBtn
            icon="zoom-in"
            title="放大"
            disabled={zoom >= ZOOM_MAX - 1e-6}
            onClick={zoomIn}
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
