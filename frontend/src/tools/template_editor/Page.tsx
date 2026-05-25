/**
 * 模板编辑器主区 —— 组合：ToolBar + TableView + 已保存模板侧栏。
 *
 * 解耦：本文件只做布局；所有状态/交互都在 components/*。
 */
import { useMemo } from 'react';

import { cn } from '../../lib/cn';
import { cellKey, useTemplateEditor } from './controller';
import { TableView } from './components/TableView';
import { ToolBar } from './components/ToolBar';
import type { FieldDef, ParsedTable } from './types';

export function TemplateEditorPage() {
  return (
    <div className="flex h-full flex-col">
      <ToolBar />
      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col overflow-auto bg-[#252525]">
          <ParseBody />
        </main>
        <aside className="border-vscode-border w-60 shrink-0 overflow-auto border-l">
          <SavedTemplatesList />
        </aside>
      </div>
    </div>
  );
}

// ── 中间内容区 ──────────────────────────────────────────

function ParseBody() {
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
    return <Spinner text="正在解析模板…" />;
  }
  if (c.parseError) {
    return (
      <div className="m-6 rounded border border-l-2 border-l-red-400 bg-[#2d2d2d] p-3 text-xs whitespace-pre-wrap text-red-400">
        <i className="codicon codicon-error mr-1 !text-[14px]" />
        解析失败：{c.parseError}
      </div>
    );
  }
  if (!c.parsed) return null;

  return (
    <div className="flex flex-col gap-3 p-4">
      <ParsedSummary
        parsed={c.parsed}
        bindingCount={Object.keys(c.bindings).length}
      />
      <TableViewBridge />
    </div>
  );
}

/** 让 TableView 不直接耦合 hook：在这里把 controller state 拼成 props。 */
function TableViewBridge() {
  const c = useTemplateEditor();
  const boundLabels = useBoundLabels(c.fields);
  if (!c.parsed) return null;
  return (
    <TableView
      table={c.parsed}
      boundLabels={boundLabels}
      selected={c.selectedCell}
      onCellClick={c.selectCell}
    />
  );
}

/** bindings + fields → { "r-c": "字段中文名" } 给 TableView 用。 */
function useBoundLabels(fields: FieldDef[]): Record<string, string> {
  const c = useTemplateEditor();
  return useMemo(() => {
    const out: Record<string, string> = {};
    const nameByKey = new Map(fields.map((f) => [f.key, f.name]));
    for (const b of Object.values(c.bindings))
      out[cellKey(b.row, b.col)] = nameByKey.get(b.field_key) ?? b.field_key;
    return out;
  }, [c.bindings, fields]);
}

// ── 解析摘要小条 ────────────────────────────────────────

function ParsedSummary({
  parsed,
  bindingCount,
}: {
  parsed: ParsedTable;
  bindingCount: number;
}) {
  return (
    <div className="border-vscode-border bg-vscode-bg flex flex-wrap items-baseline gap-x-6 gap-y-1 rounded border px-3 py-2 text-xs">
      <Stat label="行" value={parsed.row_count} />
      <Stat label="列" value={parsed.col_count} />
      <Stat label="主格" value={parsed.cells.length} />
      <Stat label="已绑" value={bindingCount} />
      <Stat label="签名" value={parsed.table_signature} mono />
    </div>
  );
}

function Stat({
  label,
  value,
  mono,
}: {
  label: string;
  value: number | string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-1.5">
      <span className="text-vscode-text-faint">{label}:</span>
      <span className={cn('text-vscode-text', mono && 'font-mono')}>
        {value}
      </span>
    </div>
  );
}

// ── 已保存模板侧栏 ─────────────────────────────────────

function SavedTemplatesList() {
  const c = useTemplateEditor();
  return (
    <div className="space-y-2 p-3 text-xs">
      <div className="text-vscode-text-dim flex items-center gap-2 text-[10px] tracking-wider uppercase">
        <i className="codicon codicon-library !text-[12px]" />
        已保存
        {c.templatesLoading && (
          <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
        )}
      </div>
      {c.templatesError ? (
        <div className="text-red-400">{c.templatesError}</div>
      ) : c.templates.length === 0 && !c.templatesLoading ? (
        <div className="text-vscode-text-faint italic">（暂无）</div>
      ) : (
        <ul className="space-y-1">
          {c.templates.map((t) => (
            <li
              key={t.name}
              className={cn(
                'border-vscode-border group flex items-center gap-1 rounded border px-2 py-1.5',
                c.currentName === t.name && 'border-vscode-focus bg-[#1e3a5f]',
              )}
            >
              <button
                type="button"
                onClick={() => c.loadTemplate(t.name)}
                className="text-vscode-text truncate text-left hover:text-white"
                title={t.display_name || t.name}
              >
                <i
                  className={cn(
                    'codicon mr-1 !text-[12px]',
                    t.broken
                      ? 'codicon-warning text-yellow-400'
                      : 'codicon-table',
                  )}
                />
                {t.name}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm(`删除模板「${t.name}」？此操作不可撤销。`))
                    c.deleteTemplate(t.name);
                }}
                title="删除"
                className="text-vscode-text-dim ml-auto opacity-0 transition-opacity group-hover:opacity-100 hover:text-red-400"
              >
                <i className="codicon codicon-trash !text-[12px]" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── 占位 ────────────────────────────────────────────────

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

function Spinner({ text }: { text: string }) {
  return (
    <div className="text-vscode-text-dim flex items-center gap-2 p-6 text-xs">
      <i className="codicon codicon-loading codicon-modifier-spin !text-[14px]" />
      {text}
    </div>
  );
}
