import { useCallback, useMemo, useState } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { cn } from '../../lib/cn';
import { RunBtn } from '../_shared/forms';
import { useTemplateHelper } from './controller';
import type { CatalogField, FieldLevel } from './types';
import { LEVEL_COLOR, LEVEL_LABEL } from './types';

export function TemplateHelperPage({
  appendOutput,
}: {
  appendOutput?: (line: string) => void;
}) {
  const c = useTemplateHelper();
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set<string>(),
  );
  const [validateTab, setValidateTab] = useState<
    'matched' | 'unrecognized' | 'unused' | 'hints'
  >('hints');
  const [groupBy, setGroupBy] = useState<'group' | 'level'>('level');

  const grouped = useMemo(() => {
    if (!c.activeCatalog) return new Map<string, CatalogField[]>();
    const map = new Map<string, CatalogField[]>();
    for (const f of c.activeCatalog.fields) {
      const key =
        groupBy === 'level'
          ? (LEVEL_LABEL[f.level as FieldLevel] || f.level)
          : (f.group || '其他');
      const arr = map.get(key);
      if (arr) arr.push(f);
      else map.set(key, [f]);
    }
    return map;
  }, [c.activeCatalog, groupBy]);

  const toggleGroup = useCallback((group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    setExpandedGroups(new Set(grouped.keys()));
  }, [grouped]);

  const collapseAll = useCallback(() => {
    setExpandedGroups(new Set());
  }, []);

  const handlePickDocx = useCallback(async () => {
    const selected = await openDialog({
      filters: [{ name: 'Word 模板', extensions: ['docx'] }],
      multiple: false,
      title: '选择 Word 模板文件',
    });
    if (typeof selected === 'string') {
      c.setDocxPath(selected);
    }
  }, [c]);

  const handleValidate = useCallback(async () => {
    const res = await c.validate();
    if (res) {
      appendOutput?.(
        `验证完成: ${res.summary.matched_count} 匹配 / ${res.summary.unrecognized_count} 未识别 / ${res.summary.hint_count} 条提示`,
      );
      if (res.hints.length > 0) setValidateTab('hints');
      else setValidateTab('matched');
    } else if (c.validateError) {
      appendOutput?.(`验证失败: ${c.validateError}`);
    }
  }, [c, appendOutput]);

  if (c.catalogLoading) {
    return (
      <div className="text-vscode-text-dim flex h-full items-center justify-center text-sm">
        <i className="codicon codicon-loading codicon-modifier-spin mr-2" />
        加载字段目录...
      </div>
    );
  }

  if (!c.activeCatalog) {
    return (
      <div className="text-vscode-text-dim flex h-full flex-col items-center justify-center gap-2 text-sm">
        <i className="codicon codicon-list-tree text-[32px] opacity-40" />
        <span>暂无字段目录</span>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-auto bg-[#1e1e1e]">
      {/* Top bar: catalog + template + validate */}
      <div className="border-vscode-border space-y-3 border-b bg-[#252526] px-5 py-3">
        <div className="flex items-center gap-2">
          <i className="codicon codicon-list-tree text-vscode-focus !text-[16px]" />
          <h1 className="text-vscode-text text-base font-medium">模板助手</h1>
        </div>

        {/* Catalog selector + group toggle */}
        <div className="flex items-center gap-2">
          <span className="text-vscode-text-dim shrink-0 text-[11px]">
            字段目录
          </span>
          <select
            value={c.activeCatalogId ?? ''}
            onChange={(e) => {
              if (e.target.value) c.selectCatalog(e.target.value);
            }}
            className="bg-vscode-input border-vscode-border text-vscode-text min-w-0 flex-1 rounded-[2px] border px-2 py-1 text-xs"
          >
            {c.catalogs.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.label} ({cat.field_count} 字段)
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => c.refreshCatalogs()}
            className="border-vscode-border rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
            title="刷新"
          >
            <i className="codicon codicon-refresh !text-[12px]" />
          </button>
        </div>

        {/* Template picker + validate */}
        <div className="flex items-center gap-2">
          <span className="text-vscode-text-dim shrink-0 text-[11px]">
            验证模板
          </span>
          <input
            type="text"
            value={c.docxPath}
            readOnly
            placeholder="选择 .docx 模板文件"
            className={cn(
              'bg-vscode-input border-vscode-border min-w-0 flex-1 truncate rounded-[2px] border px-2 py-1 text-xs',
              c.docxPath ? 'text-vscode-text' : 'text-vscode-text-dim italic',
            )}
          />
          <button
            type="button"
            onClick={handlePickDocx}
            className="border-vscode-border flex shrink-0 items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
          >
            <i className="codicon codicon-folder-opened !text-[12px]" />
            选择
          </button>
          <RunBtn
            running={c.validating}
            disabled={!c.docxPath || !c.activeCatalogId || c.validating}
            onClick={handleValidate}
          >
            验证
          </RunBtn>
        </div>
      </div>

      {/* Hints bar (if validation has hints) */}
      {c.validateResult && c.validateResult.hints.length > 0 && (
        <div className="border-vscode-border border-b bg-yellow-900/10 px-5 py-2">
          <div className="flex items-start gap-2 text-xs text-yellow-300">
            <i className="codicon codicon-warning mt-0.5 shrink-0 !text-[14px]" />
            <div className="space-y-1">
              {c.validateResult.hints.map((h, i) => (
                <div key={i} className={h.severity === 'error' ? 'text-red-400' : ''}>
                  {h.message}
                  <span className="text-vscode-text-faint ml-2 text-[10px]">
                    {h.location}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Toolbar: group toggle + expand/collapse */}
      <div className="border-vscode-border flex items-center gap-2 border-b px-5 py-1.5">
        <span className="text-vscode-text-dim text-[11px]">分组</span>
        <button
          type="button"
          onClick={() => setGroupBy('level')}
          className={cn(
            'rounded px-2 py-0.5 text-[11px]',
            groupBy === 'level'
              ? 'bg-vscode-list-hover text-vscode-text'
              : 'text-vscode-text-dim',
          )}
        >
          按层级
        </button>
        <button
          type="button"
          onClick={() => setGroupBy('group')}
          className={cn(
            'rounded px-2 py-0.5 text-[11px]',
            groupBy === 'group'
              ? 'bg-vscode-list-hover text-vscode-text'
              : 'text-vscode-text-dim',
          )}
        >
          按用途
        </button>
        <div className="flex-1" />
        <span className="text-vscode-text-faint text-[10px]">
          点击字段复制占位符
        </span>
        <button
          type="button"
          onClick={expandAll}
          className="text-vscode-text-dim hover:text-vscode-text p-0.5"
          title="全部展开"
        >
          <i className="codicon codicon-expand-all !text-[14px]" />
        </button>
        <button
          type="button"
          onClick={collapseAll}
          className="text-vscode-text-dim hover:text-vscode-text p-0.5"
          title="全部折叠"
        >
          <i className="codicon codicon-collapse-all !text-[14px]" />
        </button>
      </div>

      {/* Field palette */}
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-2">
        {Array.from(grouped.entries()).map(([group, fields]) => (
          <FieldGroup
            key={group}
            group={group}
            fields={fields}
            expanded={expandedGroups.has(group)}
            onToggle={() => toggleGroup(group)}
            copiedKey={c.copiedKey}
            onCopy={c.copyPlaceholder}
          />
        ))}
      </div>

      {/* Validation Results */}
      {c.validateResult && (
        <>
          <div className="bg-vscode-border h-px shrink-0" />
          <div className="flex max-h-[280px] min-h-0 flex-col">
            <div className="border-vscode-border flex items-center gap-1 border-b bg-[#252526] px-4 py-1">
              <i className="codicon codicon-checklist text-vscode-text-dim !text-[14px]" />
              <span className="text-vscode-text-dim text-[11px]">验证结果</span>
              <div className="flex-1" />
              <TabBtn
                active={validateTab === 'hints'}
                count={c.validateResult.summary.hint_count}
                label="提示"
                variant="warn"
                onClick={() => setValidateTab('hints')}
              />
              <TabBtn
                active={validateTab === 'matched'}
                count={c.validateResult.summary.matched_count}
                label="已匹配"
                variant="success"
                onClick={() => setValidateTab('matched')}
              />
              <TabBtn
                active={validateTab === 'unrecognized'}
                count={c.validateResult.summary.unrecognized_count}
                label="未识别"
                variant="error"
                onClick={() => setValidateTab('unrecognized')}
              />
              <TabBtn
                active={validateTab === 'unused'}
                count={c.validateResult.summary.unused_count}
                label="未使用"
                variant="neutral"
                onClick={() => setValidateTab('unused')}
              />
            </div>
            <div className="overflow-y-auto px-4 py-2 text-xs">
              {validateTab === 'hints' &&
                (c.validateResult.hints.length > 0 ? (
                  c.validateResult.hints.map((h, i) => (
                    <div
                      key={i}
                      className="border-vscode-border flex items-start gap-2 border-b py-1.5 last:border-0"
                    >
                      <i
                        className={cn(
                          'codicon mt-0.5 !text-[12px]',
                          h.severity === 'error'
                            ? 'codicon-error text-red-400'
                            : 'codicon-warning text-yellow-400',
                        )}
                      />
                      <div>
                        <div className={h.severity === 'error' ? 'text-red-400' : 'text-yellow-300'}>
                          {h.message}
                        </div>
                        <div className="text-vscode-text-faint text-[10px]">
                          {h.location}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-vscode-text-dim py-2 text-center">
                    <i className="codicon codicon-pass mr-1 text-green-400 !text-[12px]" />
                    所有字段层级匹配正确
                  </div>
                ))}
              {validateTab === 'matched' &&
                c.validateResult.matched.map((m, i) => (
                  <div
                    key={i}
                    className="border-vscode-border flex items-center gap-2 border-b py-1 last:border-0"
                  >
                    <i className="codicon codicon-check text-green-400 !text-[12px]" />
                    <code className="text-[#ce9178]">{m.placeholder}</code>
                    <LevelBadge level={m.level} />
                    <span className="text-vscode-text-dim">{m.name}</span>
                    <span className="text-vscode-text-faint ml-auto text-[10px]">
                      {m.location}
                    </span>
                  </div>
                ))}
              {validateTab === 'unrecognized' &&
                (c.validateResult.unrecognized.length > 0 ? (
                  c.validateResult.unrecognized.map((u, i) => (
                    <div
                      key={i}
                      className="border-vscode-border flex items-center gap-2 border-b py-1 last:border-0"
                    >
                      <i className="codicon codicon-warning text-yellow-400 !text-[12px]" />
                      <code className="text-[#ce9178]">{u.placeholder}</code>
                      <span className="text-vscode-text-faint ml-auto text-[10px]">
                        {u.location}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="text-vscode-text-dim py-2 text-center">
                    所有占位符均已识别
                  </div>
                ))}
              {validateTab === 'unused' &&
                (c.validateResult.unused.length > 0 ? (
                  c.validateResult.unused.map((u, i) => (
                    <div
                      key={i}
                      className="border-vscode-border flex items-center gap-2 border-b py-1 last:border-0"
                    >
                      <i className="codicon codicon-circle-outline text-vscode-text-faint !text-[12px]" />
                      <span className="text-vscode-text">{u.name}</span>
                      <LevelBadge level={u.level} />
                      <span className="text-vscode-text-faint ml-auto text-[10px]">
                        {u.group}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="text-vscode-text-dim py-2 text-center">
                    所有字段均已使用
                  </div>
                ))}
            </div>
          </div>
        </>
      )}

      {c.validateError && !c.validateResult && (
        <div className="border-vscode-border border-t p-4 text-xs text-red-400">
          <i className="codicon codicon-error mr-1 !text-[12px]" />
          {c.validateError}
        </div>
      )}
    </div>
  );
}

// ── Sub-components ──

function LevelBadge({ level }: { level: string }) {
  const label = LEVEL_LABEL[level as FieldLevel] ?? level;
  const color = LEVEL_COLOR[level as FieldLevel] ?? 'text-vscode-text-dim';
  return (
    <span className={cn('rounded bg-[#2d2d2d] px-1.5 py-0.5 text-[9px]', color)}>
      {label}
    </span>
  );
}

function FieldGroup({
  group,
  fields,
  expanded,
  onToggle,
  copiedKey,
  onCopy,
}: {
  group: string;
  fields: CatalogField[];
  expanded: boolean;
  onToggle: () => void;
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
}) {
  return (
    <div className="mb-1">
      <button
        type="button"
        onClick={onToggle}
        className="text-vscode-text hover:bg-vscode-list-hover flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-xs font-medium"
      >
        <i
          className={cn(
            'codicon !text-[12px]',
            expanded ? 'codicon-chevron-down' : 'codicon-chevron-right',
          )}
        />
        {group}
        <span className="text-vscode-text-faint ml-1 text-[10px] font-normal">
          ({fields.length})
        </span>
      </button>
      {expanded && (
        <div className="ml-3 mt-0.5 space-y-0.5">
          {fields.map((f) => (
            <FieldItem
              key={f.key}
              field={f}
              copied={copiedKey === f.key}
              onCopy={onCopy}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FieldItem({
  field,
  copied,
  onCopy,
}: {
  field: CatalogField;
  copied: boolean;
  onCopy: (text: string, key: string) => void;
}) {
  const isImage = field.key === 'curve_image' || field.group === '图片';
  const placeholder = isImage ? `{{img:${field.name}}}` : `{{${field.name}}}`;

  return (
    <button
      type="button"
      onClick={() => onCopy(placeholder, field.key)}
      className={cn(
        'hover:bg-vscode-list-hover group flex w-full items-center gap-2 rounded px-2 py-1 text-left',
        copied && 'bg-green-900/20',
      )}
      title={`点击复制: ${placeholder}\nKey: ${field.key}\n层级: ${LEVEL_LABEL[field.level] ?? field.level}${field.aliases.length > 0 ? `\n别名: ${field.aliases.join(', ')}` : ''}`}
    >
      <LevelDot level={field.level} />
      <span className="text-vscode-text min-w-0 flex-1 truncate text-xs">
        {field.name}
      </span>
      {copied ? (
        <span className="shrink-0 text-[10px] text-green-400">
          <i className="codicon codicon-check !text-[10px]" /> 已复制
        </span>
      ) : (
        <code className="text-vscode-text-faint shrink-0 text-[10px] opacity-0 group-hover:opacity-100">
          {placeholder}
        </code>
      )}
    </button>
  );
}

function LevelDot({ level }: { level: string }) {
  const color = {
    report: 'bg-blue-400',
    detection_item: 'bg-cyan-400',
    batch: 'bg-yellow-400',
    component: 'bg-green-400',
  }[level] ?? 'bg-gray-400';

  return (
    <span
      className={cn('inline-block h-2 w-2 shrink-0 rounded-full', color)}
      title={LEVEL_LABEL[level as FieldLevel] ?? level}
    />
  );
}

function TabBtn({
  active,
  count,
  label,
  variant,
  onClick,
}: {
  active: boolean;
  count: number;
  label: string;
  variant: 'success' | 'error' | 'warn' | 'neutral';
  onClick: () => void;
}) {
  const color = {
    success: 'text-green-400',
    error: 'text-red-400',
    warn: 'text-yellow-400',
    neutral: 'text-vscode-text-faint',
  }[variant];

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]',
        active
          ? 'bg-vscode-list-hover text-vscode-text'
          : 'text-vscode-text-dim hover:text-vscode-text',
      )}
    >
      <span className={cn(count > 0 && color)}>{count}</span>
      {label}
    </button>
  );
}
