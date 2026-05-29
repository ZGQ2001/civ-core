import { useCallback, useMemo, useState } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { useDialogs } from '../../components/Dialogs';
import { cn } from '../../lib/cn';
import { useShell } from '../../lib/shell';
import { RunBtn, Select, ToolHeader } from '../_shared/forms';
import { useTemplateHelper } from './controller';
import { FieldEditor } from './FieldEditor';
import type { CatalogField, FieldLevel, ValidateHint } from './types';
import { LEVEL_LABEL, LEVEL_ORDER } from './types';

interface TemplateHelperPageProps {
  appendOutput?: (line: string) => void;
}

export function TemplateHelperPage(
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- prop 由 EditorArea 统一传，模板助手当前不消费但保留接口对齐
  _props: TemplateHelperPageProps = {},
) {
  const c = useTemplateHelper();
  const shell = useShell();
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set<string>(),
  );
  const [groupBy, setGroupBy] = useState<'group' | 'level'>('level');
  const [editMode, setEditMode] = useState(false);
  const [addingField, setAddingField] = useState(false);
  const [showCatalogMenu, setShowCatalogMenu] = useState(false);

  const existingGroups = useMemo(() => {
    if (!c.activeCatalog) return [];
    return [
      ...new Set(c.activeCatalog.fields.map((f) => f.group).filter(Boolean)),
    ];
  }, [c.activeCatalog]);

  // 分组结果 = [分组名, 字段[]] 的有序数组。
  // 按层级：固定 报告级→检测项目级→批次级→构件级（LEVEL_ORDER），不再按字段插入顺序乱排。
  // 按用途：保持字段插入顺序。
  const groupedEntries = useMemo<[string, CatalogField[]][]>(() => {
    if (!c.activeCatalog) return [];
    if (groupBy === 'level') {
      const byLevel = new Map<FieldLevel, CatalogField[]>();
      for (const f of c.activeCatalog.fields) {
        const lvl = f.level as FieldLevel;
        const arr = byLevel.get(lvl);
        if (arr) arr.push(f);
        else byLevel.set(lvl, [f]);
      }
      return LEVEL_ORDER.filter((lvl) => byLevel.has(lvl)).map((lvl) => [
        LEVEL_LABEL[lvl] || lvl,
        byLevel.get(lvl)!,
      ]);
    }
    const map = new Map<string, CatalogField[]>();
    for (const f of c.activeCatalog.fields) {
      const key = f.group || '其他';
      const arr = map.get(key);
      if (arr) arr.push(f);
      else map.set(key, [f]);
    }
    return Array.from(map.entries());
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
    setExpandedGroups(new Set(groupedEntries.map(([name]) => name)));
  }, [groupedEntries]);

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

  const handlePickCurveDir = useCallback(async () => {
    const selected = await openDialog({
      directory: true,
      multiple: false,
      title: '选择曲线图目录（plot_curves 出图的文件夹）',
    });
    if (typeof selected === 'string') {
      shell.setCurveImageDir(selected);
    }
  }, [shell]);

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
      <ToolHeader icon="list-tree" title="模板助手">
        {/* Catalog selector + group toggle */}
        <div className="flex items-center gap-2">
          <span className="text-vscode-text-dim shrink-0 text-[11px]">
            字段目录
          </span>
          <Select
            value={c.activeCatalogId ?? ''}
            onChange={(e) => {
              if (e.target.value) c.selectCatalog(e.target.value);
            }}
            className="min-w-0 flex-1"
          >
            {c.catalogs.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.label} ({cat.field_count} 字段)
              </option>
            ))}
          </Select>
          <button
            type="button"
            onClick={() => c.refreshCatalogs()}
            className="border-vscode-border rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
            title="刷新"
          >
            <i className="codicon codicon-refresh !text-[12px]" />
          </button>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowCatalogMenu((v) => !v)}
              className="border-vscode-border rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
              title="目录管理"
            >
              <i className="codicon codicon-kebab-vertical !text-[12px]" />
            </button>
            {showCatalogMenu && (
              <CatalogMenu onClose={() => setShowCatalogMenu(false)} />
            )}
          </div>
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
            onClick={() => c.validate()}
          >
            验证
          </RunBtn>
        </div>
        {/* 曲线图目录 —— 跟「报告填充」共用同一份 ShellContext.curveImageDir，两端同步 */}
        <div className="flex items-center gap-2">
          <span
            className="text-vscode-text-dim shrink-0 text-[11px]"
            title="plot_curves 出图文件夹，跟「报告填充」共用此路径"
          >
            曲线图目录
          </span>
          <input
            type="text"
            value={shell.curveImageDir}
            readOnly
            placeholder="（可选 — 跟报告填充共用）"
            className={cn(
              'bg-vscode-input border-vscode-border min-w-0 flex-1 truncate rounded-[2px] border px-2 py-1 text-xs',
              shell.curveImageDir
                ? 'text-vscode-text'
                : 'text-vscode-text-dim italic',
            )}
          />
          <button
            type="button"
            onClick={handlePickCurveDir}
            className="border-vscode-border flex shrink-0 items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
          >
            <i className="codicon codicon-folder-opened !text-[12px]" />
            选择
          </button>
          {shell.curveImageDir && (
            <button
              type="button"
              onClick={() => shell.setCurveImageDir('')}
              className="text-vscode-text-dim hover:text-vscode-text shrink-0 px-1 text-[11px]"
              title="清除"
            >
              <i className="codicon codicon-close !text-[11px]" />
            </button>
          )}
        </div>
        <div className="text-vscode-text-faint text-[10px]">
          验证结果会输出到底部「输出」面板（Ctrl+J）；曲线图目录用于
          {' {{img:xxx}} '}
          占位符嵌图
        </div>
      </ToolHeader>

      {/* 体检结果 —— 验证后结构化展示，错误/未识别一眼可见（不再只埋在底部输出面板） */}
      <ValidateResults />

      {/* 层级图例 —— 让用户一眼看懂 4 个层级是什么 + 怎么在模板里写 */}
      <LevelLegend />

      {/* Toolbar: group toggle + edit mode + expand/collapse */}
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
        {c.dirty && (
          <button
            type="button"
            onClick={() => c.saveCatalog()}
            disabled={c.saving}
            className="flex items-center gap-1 rounded bg-green-700 px-2 py-0.5 text-[11px] text-white hover:bg-green-600"
          >
            {c.saving ? (
              <i className="codicon codicon-loading codicon-modifier-spin !text-[10px]" />
            ) : (
              <i className="codicon codicon-check !text-[10px]" />
            )}
            保存
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setEditMode((v) => !v);
            setAddingField(false);
            c.setEditingFieldKey(null);
          }}
          className={cn(
            'flex items-center gap-1 rounded px-2 py-0.5 text-[11px]',
            editMode
              ? 'bg-vscode-focus text-white'
              : 'text-vscode-text-dim hover:text-vscode-text',
          )}
          title={editMode ? '退出编辑' : '编辑字段'}
        >
          <i className="codicon codicon-edit !text-[11px]" />
          {editMode ? '退出编辑' : '编辑'}
        </button>
        {editMode && (
          <button
            type="button"
            onClick={() => {
              setAddingField(true);
              c.setEditingFieldKey(null);
            }}
            className="flex items-center gap-1 rounded bg-[#2d2d2d] px-2 py-0.5 text-[11px] hover:bg-[#3a3a3a]"
            title="添加字段"
          >
            <i className="codicon codicon-add !text-[11px]" />
            添加
          </button>
        )}
        {!editMode && (
          <span className="text-vscode-text-faint text-[10px]">
            点击字段复制占位符
          </span>
        )}
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
        {addingField && (
          <div className="mb-2">
            <FieldEditor
              isNew
              existingGroups={existingGroups}
              onSave={(f) => {
                c.addField(f);
                setAddingField(false);
              }}
              onCancel={() => setAddingField(false)}
            />
          </div>
        )}
        {groupedEntries.map(([group, fields]) => (
          <FieldGroup
            key={group}
            group={group}
            fields={fields}
            expanded={expandedGroups.has(group)}
            onToggle={() => toggleGroup(group)}
            copiedKey={c.copiedKey}
            onCopy={c.copyPlaceholder}
            editMode={editMode}
            editingFieldKey={c.editingFieldKey}
            existingGroups={existingGroups}
            onEdit={(key) => c.setEditingFieldKey(key)}
            onUpdate={(oldKey, field) => {
              c.updateField(oldKey, field);
              c.setEditingFieldKey(null);
            }}
            onDelete={(key) => c.removeField(key)}
            onCancelEdit={() => c.setEditingFieldKey(null)}
          />
        ))}
      </div>
    </div>
  );
}

// ── Sub-components ──

/**
 * 模板体检结果面板 —— 验证后把 template.validate 的结构化结果摆在页面顶部，
 * 错误 / 未识别占位符一眼可见（取代「只往底部输出面板灌文本」）。
 *
 * 排版优先级（从上到下，越靠上越要命）：
 *   1. 需修正（hints）：层级错配等，红=error / 黄=warning
 *   2. 未识别占位符：模板里写了但 catalog 不认识的 {{xxx}}
 *   3. 检测到的锚点（markers）：给用户「marker 被认出来了」的确认
 *   4. 未使用字段 / 已匹配字段：折叠，次要
 */
function ValidateResults() {
  const c = useTemplateHelper();
  const [showUnused, setShowUnused] = useState(false);
  const [showMatched, setShowMatched] = useState(false);

  const v = c.lastValidation;
  if (!v) return null;

  const s = v.summary;
  const allClear = v.hints.length === 0 && v.unrecognized.length === 0;

  return (
    <div className="border-vscode-border border-b bg-[#1d1d1d] px-5 py-2.5">
      {/* 标题行 + 计数 chips + 收起 */}
      <div className="flex items-center gap-2">
        <i
          className={cn(
            'codicon !text-[14px]',
            allClear
              ? 'codicon-pass text-green-400'
              : 'codicon-warning text-yellow-400',
          )}
        />
        <span className="text-vscode-text text-xs font-medium">
          {allClear ? '模板体检通过' : '模板体检结果'}
        </span>
        <div className="ml-1 flex flex-wrap items-center gap-1.5 text-[10px]">
          <Chip tone="ok" label={`匹配 ${s.matched_count}`} />
          {v.hints.length > 0 && (
            <Chip tone="error" label={`需修正 ${v.hints.length}`} />
          )}
          {s.unrecognized_count > 0 && (
            <Chip tone="warn" label={`未识别 ${s.unrecognized_count}`} />
          )}
          {s.unused_count > 0 && (
            <Chip tone="muted" label={`未使用 ${s.unused_count}`} />
          )}
        </div>
        <button
          type="button"
          onClick={c.dismissValidation}
          className="text-vscode-text-dim hover:text-vscode-text ml-auto shrink-0 p-0.5"
          title="收起体检结果"
        >
          <i className="codicon codicon-close !text-[12px]" />
        </button>
      </div>

      {/* 1. 需修正 —— 层级错配等，最要命，永远展开 */}
      {v.hints.length > 0 && (
        <div className="mt-2 space-y-1">
          {v.hints.map((h, i) => (
            <HintRow key={`${h.field_name}-${i}`} hint={h} />
          ))}
        </div>
      )}

      {/* 2. 未识别占位符 —— 模板里写了但 catalog 不认识 */}
      {v.unrecognized.length > 0 && (
        <div className="mt-2 space-y-1">
          {v.unrecognized.map((u, i) => (
            <div
              key={`${u.placeholder}-${i}`}
              className="flex items-start gap-2 rounded-[2px] border border-l-2 border-yellow-600/40 border-l-yellow-500 bg-[#2a2620] px-2 py-1 text-[11px]"
            >
              <i className="codicon codicon-question mt-0.5 shrink-0 !text-[12px] text-yellow-400" />
              <div className="min-w-0">
                <code className="text-yellow-200">{u.placeholder}</code>
                <span className="text-vscode-text-dim ml-2">
                  未识别 —— catalog
                  里没有这个字段（检查拼写，或去下方字段表加/改）
                </span>
                <div className="text-vscode-text-faint mt-0.5">
                  {u.location}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 3. 检测到的锚点 marker —— 给「认出来了」的确认 */}
      <div className="text-vscode-text-faint mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
        <span>检测到锚点：</span>
        {v.markers.length === 0 ? (
          <span className="italic">无（模板未用 [[…]] 重复区域）</span>
        ) : (
          v.markers.map((m, i) => (
            <code
              key={`${m.text}-${i}`}
              className="border-vscode-border text-vscode-text-dim rounded border bg-[#252525] px-1"
            >
              {m.text}
            </code>
          ))
        )}
      </div>

      {allClear && v.markers.length === 0 && (
        <div className="text-vscode-text-faint mt-1 text-[10px]">
          所有占位符都识别且层级正确。
        </div>
      )}

      {/* 4. 折叠：未使用字段 / 已匹配字段 */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
        {v.unused.length > 0 && (
          <button
            type="button"
            onClick={() => setShowUnused((x) => !x)}
            className="text-vscode-text-dim hover:text-vscode-text flex items-center gap-1"
          >
            <i
              className={cn(
                'codicon !text-[10px]',
                showUnused ? 'codicon-chevron-down' : 'codicon-chevron-right',
              )}
            />
            未使用字段 {v.unused.length}
          </button>
        )}
        {v.matched.length > 0 && (
          <button
            type="button"
            onClick={() => setShowMatched((x) => !x)}
            className="text-vscode-text-dim hover:text-vscode-text flex items-center gap-1"
          >
            <i
              className={cn(
                'codicon !text-[10px]',
                showMatched ? 'codicon-chevron-down' : 'codicon-chevron-right',
              )}
            />
            已匹配字段 {v.matched.length}
          </button>
        )}
      </div>
      {showUnused && v.unused.length > 0 && (
        <div className="mt-1 max-h-32 overflow-y-auto rounded-[2px] bg-[#161616] px-2 py-1.5 text-[10px]">
          <div className="flex flex-wrap gap-1.5">
            {v.unused.map((u) => (
              <span
                key={u.key}
                className="text-vscode-text-dim border-vscode-border inline-flex items-center gap-1 rounded border bg-[#252525] px-1.5 py-0.5"
                title={`${u.key}（${LEVEL_LABEL[u.level] ?? u.level}）`}
              >
                {u.name}
                <span className="text-vscode-text-faint">
                  {LEVEL_LABEL[u.level] ?? u.level}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
      {showMatched && v.matched.length > 0 && (
        <div className="mt-1 max-h-32 overflow-y-auto rounded-[2px] bg-[#161616] px-2 py-1.5 text-[10px]">
          <div className="flex flex-wrap gap-1.5">
            {v.matched.map((m, i) => (
              <span
                key={`${m.key}-${i}`}
                className="text-vscode-text-dim border-vscode-border inline-flex items-center gap-1 rounded border bg-[#252525] px-1.5 py-0.5"
                title={`${m.placeholder} → ${m.key} @ ${m.location}`}
              >
                {m.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 体检计数小 chip —— ok/error/warn/muted 四色。 */
function Chip({
  tone,
  label,
}: {
  tone: 'ok' | 'error' | 'warn' | 'muted';
  label: string;
}) {
  const cls = {
    ok: 'bg-green-500/15 text-green-300 border-green-500/40',
    error: 'bg-red-500/15 text-red-300 border-red-500/40',
    warn: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/40',
    muted: 'bg-gray-500/15 text-gray-300 border-gray-500/40',
  }[tone];
  return (
    <span className={cn('rounded-full border px-1.5 py-px', cls)}>{label}</span>
  );
}

/** 单条「需修正」提示 —— error 红 / warning 黄，带位置。 */
function HintRow({ hint }: { hint: ValidateHint }) {
  const isError = hint.severity === 'error';
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-[2px] border border-l-2 px-2 py-1 text-[11px]',
        isError
          ? 'border-red-600/40 border-l-red-500 bg-[#2a1d1d]'
          : 'border-yellow-600/40 border-l-yellow-500 bg-[#2a2620]',
      )}
    >
      <i
        className={cn(
          'codicon mt-0.5 shrink-0 !text-[12px]',
          isError
            ? 'codicon-error text-red-400'
            : 'codicon-warning text-yellow-400',
        )}
      />
      <div className="min-w-0">
        <span className={isError ? 'text-red-200' : 'text-yellow-200'}>
          {hint.message}
        </span>
        <div className="text-vscode-text-faint mt-0.5">{hint.location}</div>
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
  editMode,
  editingFieldKey,
  existingGroups,
  onEdit,
  onUpdate,
  onDelete,
  onCancelEdit,
}: {
  group: string;
  fields: CatalogField[];
  expanded: boolean;
  onToggle: () => void;
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
  editMode?: boolean;
  editingFieldKey?: string | null;
  existingGroups?: string[];
  onEdit?: (key: string) => void;
  onUpdate?: (oldKey: string, field: CatalogField) => void;
  onDelete?: (key: string) => void;
  onCancelEdit?: () => void;
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
        <div className="mt-0.5 ml-3 space-y-0.5">
          {fields.map((f) => (
            <div key={f.key}>
              {editingFieldKey === f.key ? (
                <FieldEditor
                  initial={f}
                  isNew={false}
                  existingGroups={existingGroups ?? []}
                  onSave={(updated) => onUpdate?.(f.key, updated)}
                  onCancel={() => onCancelEdit?.()}
                />
              ) : (
                <FieldItem
                  field={f}
                  copied={copiedKey === f.key}
                  onCopy={onCopy}
                  editMode={editMode}
                  onEdit={() => onEdit?.(f.key)}
                  onDelete={() => onDelete?.(f.key)}
                />
              )}
            </div>
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
  editMode,
  onEdit,
  onDelete,
}: {
  field: CatalogField;
  copied: boolean;
  onCopy: (text: string, key: string) => void;
  editMode?: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const isImage = field.key === 'curve_image' || field.group === '图片';
  const placeholder = isImage ? `{{img:${field.name}}}` : `{{${field.name}}}`;

  return (
    <div
      className={cn(
        'hover:bg-vscode-list-hover group flex w-full items-center gap-2 rounded px-2 py-1',
        copied && 'bg-green-900/20',
      )}
    >
      {editMode ? (
        <>
          <LevelDot level={field.level} withLabel />
          <span className="text-vscode-text min-w-0 flex-1 truncate text-xs">
            {field.name}
          </span>
          <code className="text-vscode-text-faint text-[10px]">
            {field.key}
          </code>
          <button
            type="button"
            onClick={onEdit}
            className="text-vscode-text-dim hover:text-vscode-text shrink-0 p-0.5 opacity-0 group-hover:opacity-100"
            title="编辑"
          >
            <i className="codicon codicon-edit !text-[11px]" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="shrink-0 p-0.5 text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-300"
            title="删除"
          >
            <i className="codicon codicon-trash !text-[11px]" />
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={() => onCopy(placeholder, field.key)}
          className="flex w-full items-center gap-2 text-left"
          title={`点击复制: ${placeholder}\nKey: ${field.key}\n层级: ${LEVEL_LABEL[field.level] ?? field.level}${field.aliases.length > 0 ? `\n别名: ${field.aliases.join(', ')}` : ''}`}
        >
          <LevelDot level={field.level} withLabel />
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
      )}
    </div>
  );
}

/** 4 层级的颜色/文字配置（chip 图例和 LevelDot 共用）。 */
const LEVEL_META: Record<
  FieldLevel,
  { dot: string; chip: string; desc: string; markerHint: string }
> = {
  report: {
    dot: 'bg-blue-400',
    chip: 'bg-blue-500/15 text-blue-300 border-blue-500/40',
    desc: '整份报告共享一份取值（委托方、项目名、报告编号等）',
    markerHint: '不需要 marker，直接写 {{字段名}}',
  },
  detection_item: {
    dot: 'bg-cyan-400',
    chip: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40',
    desc: '同一类检测共享（锚杆抗拔 / 钻芯 各占一段）',
    markerHint: '[[检测项目]]...[[/检测项目]] 包住该段',
  },
  batch: {
    dot: 'bg-yellow-400',
    chip: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/40',
    desc: '一批构件共享一份取值（同批次灌浆日期等）',
    markerHint: '[[批次]]...[[/批次]] 包住该段',
  },
  component: {
    dot: 'bg-green-400',
    chip: 'bg-green-500/15 text-green-300 border-green-500/40',
    desc: '每个构件一行（锚杆编号、弹性位移量等）',
    markerHint: '[[每根锚杆]]...[[/每根锚杆]] 包住该段',
  },
};

function LevelLegend() {
  return (
    <div className="border-vscode-border border-b bg-[#1f1f1f] px-5 py-2">
      <div className="text-vscode-text-faint mb-1.5 text-[10px]">
        字段层级 — 颜色越深越偏「重复区域」（按宏观→微观排列）
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {(Object.keys(LEVEL_META) as FieldLevel[]).map((lvl) => {
          const meta = LEVEL_META[lvl];
          return (
            <span
              key={lvl}
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px]',
                meta.chip,
              )}
              title={`${LEVEL_LABEL[lvl]}：${meta.desc}\n模板写法：${meta.markerHint}`}
            >
              <span className={cn('h-1.5 w-1.5 rounded-full', meta.dot)} />
              {LEVEL_LABEL[lvl]}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function LevelDot({
  level,
  withLabel = false,
}: {
  level: string;
  withLabel?: boolean;
}) {
  const meta = LEVEL_META[level as FieldLevel];
  const dot = meta?.dot ?? 'bg-gray-400';
  const chip = meta?.chip ?? 'bg-gray-500/15 text-gray-300 border-gray-500/40';
  const label = LEVEL_LABEL[level as FieldLevel] ?? level;

  if (withLabel) {
    return (
      <span
        className={cn(
          'inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-px text-[9px]',
          chip,
        )}
        title={`${label}：${meta?.desc ?? ''}`}
      >
        <span className={cn('h-1.5 w-1.5 rounded-full', dot)} />
        {label}
      </span>
    );
  }
  return (
    <span
      className={cn('inline-block h-2 w-2 shrink-0 rounded-full', dot)}
      title={label}
    />
  );
}

function CatalogMenu({ onClose }: { onClose: () => void }) {
  const c = useTemplateHelper();
  const dlg = useDialogs();
  const [action, setAction] = useState<'none' | 'new' | 'copy' | 'rename'>(
    'none',
  );
  const [inputId, setInputId] = useState('');
  const [inputLabel, setInputLabel] = useState('');

  const handleCreate = useCallback(async () => {
    if (!inputId.trim() || !inputLabel.trim()) return;
    await c.createCatalog(inputId.trim(), inputLabel.trim());
    onClose();
  }, [inputId, inputLabel, c, onClose]);

  const handleCopy = useCallback(async () => {
    if (!inputId.trim() || !inputLabel.trim()) return;
    await c.copyCatalog(inputId.trim(), inputLabel.trim());
    onClose();
  }, [inputId, inputLabel, c, onClose]);

  const handleRename = useCallback(() => {
    if (!inputLabel.trim()) return;
    c.renameCatalog(inputLabel.trim());
    onClose();
  }, [inputLabel, c, onClose]);

  const handleDelete = useCallback(async () => {
    const ok = await dlg.confirm({
      title: '删除字段目录',
      message: `确定删除字段目录「${c.activeCatalog?.label}」？此操作不可撤销。`,
      danger: true,
      confirmLabel: '删除',
    });
    if (!ok) return;
    await c.deleteCatalog();
    onClose();
  }, [dlg, c, onClose]);

  if (action === 'new' || action === 'copy') {
    return (
      <div className="border-vscode-border absolute top-full right-0 z-50 mt-1 w-64 rounded border bg-[#252526] p-3 shadow-lg">
        <div className="text-vscode-text mb-2 text-xs font-medium">
          {action === 'new' ? '新建字段目录' : '复制当前目录'}
        </div>
        <div className="space-y-2">
          <input
            type="text"
            value={inputId}
            onChange={(e) => setInputId(e.target.value)}
            placeholder="目录 ID（英文，如 core_drill）"
            className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
            autoFocus
          />
          <input
            type="text"
            value={inputLabel}
            onChange={(e) => setInputLabel(e.target.value)}
            placeholder="显示名称（如 钻芯取样）"
            className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={action === 'new' ? handleCreate : handleCopy}
              disabled={!inputId.trim() || !inputLabel.trim()}
              className="bg-vscode-button hover:bg-vscode-button-hover rounded-[2px] px-3 py-1 text-xs text-white disabled:opacity-50"
            >
              确定
            </button>
            <button
              type="button"
              onClick={onClose}
              className="text-vscode-text-dim text-xs hover:underline"
            >
              取消
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (action === 'rename') {
    return (
      <div className="border-vscode-border absolute top-full right-0 z-50 mt-1 w-56 rounded border bg-[#252526] p-3 shadow-lg">
        <div className="text-vscode-text mb-2 text-xs font-medium">
          重命名目录
        </div>
        <input
          type="text"
          value={inputLabel}
          onChange={(e) => setInputLabel(e.target.value)}
          placeholder="新名称"
          className="bg-vscode-input border-vscode-border text-vscode-text mb-2 w-full rounded-[2px] border px-2 py-1 text-xs"
          autoFocus
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleRename}
            disabled={!inputLabel.trim()}
            className="bg-vscode-button hover:bg-vscode-button-hover rounded-[2px] px-3 py-1 text-xs text-white disabled:opacity-50"
          >
            确定
          </button>
          <button
            type="button"
            onClick={onClose}
            className="text-vscode-text-dim text-xs hover:underline"
          >
            取消
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="border-vscode-border absolute top-full right-0 z-50 mt-1 w-44 rounded border bg-[#252526] py-1 shadow-lg">
      <MenuBtn
        icon="codicon-new-file"
        label="新建目录"
        onClick={() => setAction('new')}
      />
      <MenuBtn
        icon="codicon-copy"
        label="复制当前目录"
        onClick={() => {
          setInputLabel(
            c.activeCatalog ? `${c.activeCatalog.label}（副本）` : '',
          );
          setAction('copy');
        }}
        disabled={!c.activeCatalog}
      />
      <MenuBtn
        icon="codicon-edit"
        label="重命名"
        onClick={() => {
          setInputLabel(c.activeCatalog?.label ?? '');
          setAction('rename');
        }}
        disabled={!c.activeCatalog}
      />
      <div className="bg-vscode-border my-1 h-px" />
      <MenuBtn
        icon="codicon-trash"
        label="删除目录"
        onClick={handleDelete}
        disabled={!c.activeCatalog}
        danger
      />
    </div>
  );
}

function MenuBtn({
  icon,
  label,
  onClick,
  disabled,
  danger,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs',
        disabled
          ? 'text-vscode-text-faint cursor-not-allowed'
          : danger
            ? 'text-red-400 hover:bg-red-900/20'
            : 'text-vscode-text hover:bg-vscode-list-hover',
      )}
    >
      <i className={cn('codicon', icon, '!text-[12px]')} />
      {label}
    </button>
  );
}
