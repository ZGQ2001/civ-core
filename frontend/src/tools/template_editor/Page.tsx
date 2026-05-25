/**
 * 模板编辑器主区 —— Phase 2 骨架。
 *
 * 当前 UI：
 *  - 顶部：选 docx 按钮 + 解析状态摘要
 *  - 中间：已保存模板列表（待编辑入口；按钮交互留给下一轮）
 *
 * TableView 渲染 + 字段绑定交互 → 留给 Phase 2 后续 commit。
 */
import { useCallback } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { cn } from '../../lib/cn';
import { useTemplateEditor } from './controller';

export function TemplateEditorPage() {
  const c = useTemplateEditor();

  const pickDocx = useCallback(async () => {
    const sel = await openDialog({
      title: '选择 Word 模板（含 [[数据绑定区]] 锚点 + 目标表格）',
      multiple: false,
      filters: [{ name: 'Word', extensions: ['docx'] }],
    });
    if (typeof sel === 'string') c.setSourceDocxPath(sel);
  }, [c]);

  return (
    <div className="flex h-full flex-col">
      <Header onPickDocx={pickDocx} />
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-6">
        <ParsedSummary />
        <SavedTemplatesList />
      </div>
    </div>
  );
}

// ── 顶部条 ──────────────────────────────────────────────

function Header({ onPickDocx }: { onPickDocx: () => void }) {
  const c = useTemplateEditor();
  return (
    <div className="border-vscode-border space-y-2 border-b px-6 pt-4 pb-3">
      <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
        <i className="codicon codicon-table !text-[16px]" />
        模板编辑
        <span className="text-vscode-text-faint ml-2 text-xs font-normal">
          （Phase 2 骨架；表格渲染 + 绑定交互建设中）
        </span>
      </h1>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onPickDocx}
          className="border-vscode-border flex shrink-0 items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
        >
          <i className="codicon codicon-folder-opened !text-[12px]" />选 Word
          模板…
        </button>
        {c.sourceDocxPath && (
          <span
            className="text-vscode-text-dim max-w-[400px] truncate text-xs"
            title={c.sourceDocxPath}
          >
            {c.sourceDocxPath.split(/[\\/]/).pop()}
          </span>
        )}
      </div>
    </div>
  );
}

// ── 解析摘要 ────────────────────────────────────────────

function ParsedSummary() {
  const c = useTemplateEditor();

  if (!c.sourceDocxPath) {
    return (
      <EmptyHint
        icon="folder-opened"
        title="先选一份 Word 模板"
        detail="模板要求：在目标表格前插入一段，内容含 [[数据绑定区]]"
      />
    );
  }

  if (c.parseLoading) {
    return (
      <div className="text-vscode-text-dim flex items-center gap-2 text-xs">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[14px]" />
        正在解析模板…
      </div>
    );
  }

  if (c.parseError) {
    return (
      <div className="border-vscode-border rounded border-l-2 border-l-red-400 bg-[#2d2d2d] p-3 text-xs whitespace-pre-wrap text-red-400">
        <i className="codicon codicon-error mr-1 !text-[14px]" />
        解析失败：{c.parseError}
      </div>
    );
  }

  if (!c.parsed) return null;

  return (
    <div className="border-vscode-border space-y-2 rounded border bg-[#252525] p-3 text-xs">
      <div className="text-vscode-text flex items-center gap-2">
        <i className="codicon codicon-pass !text-[14px] text-green-400" />
        解析成功
      </div>
      <div className="text-vscode-text-dim grid grid-cols-3 gap-x-6 gap-y-1">
        <Stat label="行数" value={c.parsed.row_count} />
        <Stat label="列数" value={c.parsed.col_count} />
        <Stat label="主格数" value={c.parsed.cells.length} />
        <Stat
          label="签名"
          value={c.parsed.table_signature}
          className="col-span-3 font-mono"
        />
      </div>
      <div className="text-vscode-text-faint pt-1 text-[11px]">
        下一步：在右侧 RightPanel 查看可用字段；表格渲染 + 点击绑定建设中。
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  className,
}: {
  label: string;
  value: number | string;
  className?: string;
}) {
  return (
    <div className={cn('flex gap-2', className)}>
      <span className="text-vscode-text-faint">{label}:</span>
      <span className="text-vscode-text">{value}</span>
    </div>
  );
}

// ── 已保存模板列表 ─────────────────────────────────────

function SavedTemplatesList() {
  const c = useTemplateEditor();
  return (
    <div className="border-vscode-border space-y-2 rounded border bg-[#252525] p-3 text-xs">
      <div className="text-vscode-text-dim flex items-center gap-2 text-[11px] tracking-wider uppercase">
        <i className="codicon codicon-library !text-[12px]" />
        已保存模板
        {c.templatesLoading && (
          <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
        )}
      </div>
      {c.templatesError ? (
        <div className="text-red-400">读列表失败：{c.templatesError}</div>
      ) : c.templates.length === 0 && !c.templatesLoading ? (
        <div className="text-vscode-text-faint italic">
          （还没有保存过模板）
        </div>
      ) : (
        <ul className="space-y-1">
          {c.templates.map((t) => (
            <li
              key={t.name}
              className="border-vscode-border flex items-center gap-2 rounded border px-2 py-1"
            >
              <i
                className={cn(
                  'codicon !text-[12px]',
                  t.broken
                    ? 'codicon-warning text-yellow-400'
                    : 'codicon-table',
                )}
              />
              <span className="text-vscode-text">{t.name}</span>
              {t.display_name && (
                <span className="text-vscode-text-dim">— {t.display_name}</span>
              )}
              {t.project_type && (
                <span className="text-vscode-text-faint ml-auto text-[10px]">
                  {t.project_type}
                </span>
              )}
              {t.broken && (
                <span className="ml-auto text-yellow-400">配置损坏</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EmptyHint({
  icon,
  title,
  detail,
}: {
  icon: string;
  title: string;
  detail: string;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <i
        className={`codicon codicon-${icon} text-vscode-text-faint !text-[48px]`}
      />
      <div className="text-vscode-text-dim mt-3 text-sm">{title}</div>
      <div className="text-vscode-text-faint mt-1 max-w-md text-xs">
        {detail}
      </div>
    </div>
  );
}
