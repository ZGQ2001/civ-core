import { useCallback, useMemo, useState } from 'react';

import { cn } from '../../lib/cn';
import { useTemplateHelper } from './controller';
import type { CatalogField } from './types';

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
    'matched' | 'unrecognized' | 'unused'
  >('matched');

  const grouped = useMemo(() => {
    if (!c.activeCatalog) return new Map<string, CatalogField[]>();
    const map = new Map<string, CatalogField[]>();
    for (const f of c.activeCatalog.fields) {
      const g = f.group || '其他';
      const arr = map.get(g);
      if (arr) arr.push(f);
      else map.set(g, [f]);
    }
    return map;
  }, [c.activeCatalog]);

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

  const handleValidate = useCallback(async () => {
    const res = await c.validate();
    if (res) {
      appendOutput?.(
        `验证完成: ${res.summary.matched_count} 匹配 / ${res.summary.unrecognized_count} 未识别 / ${res.summary.unused_count} 未使用`,
      );
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
        <span>请在右侧选择一个字段目录</span>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="bg-vscode-sidebar border-vscode-border flex items-center gap-2 border-b px-3 py-1.5">
        <span className="text-vscode-text-dim text-xs">
          {c.activeCatalog.label}
        </span>
        <span className="text-vscode-text-faint text-[11px]">
          {c.activeCatalog.fields.length} 个字段
        </span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={expandAll}
          className="text-vscode-text-dim hover:text-vscode-text rounded p-0.5 text-[11px]"
          title="全部展开"
        >
          <i className="codicon codicon-expand-all !text-[14px]" />
        </button>
        <button
          type="button"
          onClick={collapseAll}
          className="text-vscode-text-dim hover:text-vscode-text rounded p-0.5 text-[11px]"
          title="全部折叠"
        >
          <i className="codicon codicon-collapse-all !text-[14px]" />
        </button>
      </div>

      {/* Main content: split into palette + validation */}
      <div className="flex min-h-0 flex-1 flex-col">
        {/* Field Palette */}
        <div
          className={cn(
            'overflow-y-auto',
            c.validateResult ? 'flex-1' : 'flex-[2]',
          )}
        >
          <div className="p-2">
            <div className="text-vscode-text-dim mb-2 text-[11px]">
              点击字段复制占位符到剪贴板，粘贴到 Word 模板中
            </div>
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
        </div>

        {/* Validation Results */}
        {c.validateResult && (
          <>
            <div className="bg-vscode-border h-px shrink-0" />
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="bg-vscode-sidebar border-vscode-border flex items-center gap-1 border-b px-2 py-1">
                <i className="codicon codicon-checklist text-vscode-text-dim !text-[14px]" />
                <span className="text-vscode-text-dim text-[11px]">
                  验证结果
                </span>
                <div className="flex-1" />
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
                  variant="warn"
                  onClick={() => setValidateTab('unused')}
                />
              </div>
              <div className="overflow-y-auto p-2 text-xs">
                {validateTab === 'matched' &&
                  c.validateResult.matched.map((m, i) => (
                    <div
                      key={i}
                      className="border-vscode-border flex items-center gap-2 border-b py-1 last:border-0"
                    >
                      <i className="codicon codicon-check text-green-400 !text-[12px]" />
                      <code className="text-[#ce9178]">{m.placeholder}</code>
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
                        <code className="text-vscode-text-faint">
                          {u.key}
                        </code>
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

        {/* Validate error */}
        {c.validateError && !c.validateResult && (
          <>
            <div className="bg-vscode-border h-px shrink-0" />
            <div className="p-3 text-xs text-red-400">
              <i className="codicon codicon-error mr-1 !text-[12px]" />
              {c.validateError}
            </div>
          </>
        )}
      </div>
    </div>
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
      title={`点击复制: ${placeholder}\nKey: ${field.key}${field.aliases.length > 0 ? `\n别名: ${field.aliases.join(', ')}` : ''}`}
    >
      <SourceIcon source={field.source} />
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

function SourceIcon({ source }: { source: string }) {
  switch (source) {
    case 'parameter':
      return (
        <i
          className="codicon codicon-symbol-constant text-blue-400 !text-[12px]"
          title="工程参数"
        />
      );
    case 'rawinput':
      return (
        <i
          className="codicon codicon-table text-green-400 !text-[12px]"
          title="原始数据"
        />
      );
    case 'calculated':
      return (
        <i
          className="codicon codicon-symbol-method text-purple-400 !text-[12px]"
          title="计算结果"
        />
      );
    case 'userinput':
      return (
        <i
          className="codicon codicon-edit text-yellow-400 !text-[12px]"
          title="用户输入"
        />
      );
    default:
      return (
        <i
          className="codicon codicon-symbol-field text-vscode-text-dim !text-[12px]"
          title={source}
        />
      );
  }
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
  variant: 'success' | 'error' | 'warn';
  onClick: () => void;
}) {
  const color = {
    success: 'text-green-400',
    error: 'text-red-400',
    warn: 'text-yellow-400',
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
