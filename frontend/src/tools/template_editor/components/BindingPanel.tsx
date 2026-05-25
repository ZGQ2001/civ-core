/**
 * BindingPanel —— 字段列表 + 交互式绑定，住在右侧 RightPanel。
 *
 * 行为：
 *  - 没选格子 → 字段列表灰色，hint "先点左侧格子"
 *  - 选了格子 → 字段可点；点字段调 bindFieldToSelected
 *  - 已绑定字段尾巴显示 "→ r行c列" + 「解绑」按钮
 *  - 同一字段不能绑两格（controller 内部保证唯一）
 */
import { cn } from '../../../lib/cn';
import { cellKey, useTemplateEditor } from '../controller';
import type { CellBinding, FieldDef, FieldSource } from '../types';

const SOURCE_LABEL: Record<FieldSource, string> = {
  parameter: '工程参数',
  raw_input: '原始数据',
  calculated: '计算结果',
  user_input: '用户填写',
};
const SOURCE_ORDER: FieldSource[] = [
  'parameter',
  'raw_input',
  'calculated',
  'user_input',
];

export function BindingPanel() {
  const c = useTemplateEditor();

  if (c.fieldsLoading) {
    return (
      <PanelShell>
        <Hint icon="loading codicon-modifier-spin" text="加载字段清单…" dim />
      </PanelShell>
    );
  }
  if (c.fieldsError) {
    return (
      <PanelShell>
        <div className="text-xs text-red-400">
          <i className="codicon codicon-error mr-1 !text-[14px]" />
          读字段失败：{c.fieldsError}
        </div>
      </PanelShell>
    );
  }

  // 按 source 分组
  const grouped = SOURCE_ORDER.map((s) => ({
    source: s,
    items: c.fields.filter((f) => f.source === s),
  })).filter((g) => g.items.length > 0);

  // 按 fieldKey → 已绑定的格子
  const boundByKey: Record<string, CellBinding> = {};
  for (const b of Object.values(c.bindings)) boundByKey[b.field_key] = b;

  return (
    <PanelShell>
      <SelectionHint />
      {grouped.map((g) => (
        <FieldGroup
          key={g.source}
          source={g.source}
          items={g.items}
          boundByKey={boundByKey}
          canBind={c.selectedCell !== null}
          onBind={(key) => c.bindFieldToSelected(key)}
          onUnbind={(b) => c.unbindCell(b.row, b.col)}
          selectedKey={
            c.selectedCell
              ? c.bindings[cellKey(c.selectedCell.row, c.selectedCell.col)]
                  ?.field_key
              : undefined
          }
        />
      ))}
    </PanelShell>
  );
}

// ── 内部 ────────────────────────────────────────────────

function PanelShell({ children }: { children: React.ReactNode }) {
  const c = useTemplateEditor();
  return (
    <div className="flex h-full flex-col text-xs">
      <div className="border-vscode-border shrink-0 border-b px-3 py-2">
        <div className="text-vscode-text font-medium">
          可用字段（{c.projectType}）
        </div>
        <div className="text-vscode-text-faint mt-0.5 text-[11px]">
          {c.selectedCell
            ? `已选 ${c.selectedCell.row + 1}行${c.selectedCell.col + 1}列`
            : '点击左侧格子开始绑定'}
        </div>
      </div>
      <div className="flex-1 space-y-3 overflow-auto p-3">{children}</div>
    </div>
  );
}

function SelectionHint() {
  const c = useTemplateEditor();
  if (!c.selectedCell || !c.parsed) return null;
  const k = cellKey(c.selectedCell.row, c.selectedCell.col);
  const bound = c.bindings[k];
  return (
    <div className="border-vscode-border space-y-1 rounded border bg-[#252525] p-2 text-[11px]">
      <div className="flex items-center justify-between">
        <span className="text-vscode-text">
          第 {c.selectedCell.row + 1} 行 / 第 {c.selectedCell.col + 1} 列
        </span>
        <button
          type="button"
          onClick={c.clearSelectedCell}
          title="取消选择"
          className="text-vscode-text-dim hover:text-white"
        >
          <i className="codicon codicon-close !text-[12px]" />
        </button>
      </div>
      {bound ? (
        <div className="flex items-center gap-2">
          <span className="text-blue-300">
            <i className="codicon codicon-symbol-field !text-[11px]" /> 已绑：
            {lookupName(c.fields, bound.field_key)}
          </span>
          <button
            type="button"
            onClick={() =>
              c.unbindCell(c.selectedCell!.row, c.selectedCell!.col)
            }
            className="text-vscode-text-dim ml-auto hover:text-red-400"
          >
            解绑
          </button>
        </div>
      ) : (
        <div className="text-vscode-text-faint italic">未绑定 — 点字段绑上</div>
      )}
    </div>
  );
}

function FieldGroup({
  source,
  items,
  boundByKey,
  canBind,
  onBind,
  onUnbind,
  selectedKey,
}: {
  source: FieldSource;
  items: FieldDef[];
  boundByKey: Record<string, CellBinding>;
  canBind: boolean;
  onBind: (key: string) => void;
  onUnbind: (b: CellBinding) => void;
  selectedKey: string | undefined;
}) {
  return (
    <div>
      <div className="text-vscode-text-dim mb-1.5 text-[10px] tracking-wider uppercase">
        {SOURCE_LABEL[source]}（{items.length}）
      </div>
      <ul className="space-y-1">
        {items.map((f) => (
          <FieldRow
            key={f.key}
            field={f}
            bound={boundByKey[f.key]}
            isSelectedHere={selectedKey === f.key}
            canBind={canBind}
            onClick={() => canBind && onBind(f.key)}
            onUnbind={() => boundByKey[f.key] && onUnbind(boundByKey[f.key])}
          />
        ))}
      </ul>
    </div>
  );
}

function FieldRow({
  field,
  bound,
  isSelectedHere,
  canBind,
  onClick,
  onUnbind,
}: {
  field: FieldDef;
  bound: CellBinding | undefined;
  isSelectedHere: boolean;
  canBind: boolean;
  onClick: () => void;
  onUnbind: () => void;
}) {
  const disabled = !canBind && !bound;
  return (
    <li
      title={field.key}
      onClick={onClick}
      className={cn(
        'border-vscode-border flex items-baseline gap-2 rounded border px-2 py-1 transition-colors',
        disabled
          ? 'text-vscode-text-faint cursor-not-allowed opacity-60'
          : 'cursor-pointer',
        isSelectedHere
          ? 'border-blue-400 bg-[#1e3a5f]'
          : bound
            ? 'bg-[#252525]'
            : 'hover:bg-vscode-hover',
      )}
    >
      <span className={cn(bound ? 'text-blue-300' : 'text-vscode-text')}>
        {field.name}
      </span>
      <span className="text-vscode-text-faint ml-auto font-mono text-[10px]">
        {field.value_type}
        {field.default_format && ` · ${field.default_format}`}
      </span>
      {bound && (
        <>
          <span className="text-vscode-text-dim text-[10px]">
            → {bound.row + 1},{bound.col + 1}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onUnbind();
            }}
            title="解绑"
            className="text-vscode-text-dim hover:text-red-400"
          >
            <i className="codicon codicon-close !text-[12px]" />
          </button>
        </>
      )}
    </li>
  );
}

function Hint({
  icon,
  text,
  dim,
}: {
  icon: string;
  text: string;
  dim?: boolean;
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 text-xs',
        dim ? 'text-vscode-text-dim' : 'text-vscode-text',
      )}
    >
      <i className={`codicon codicon-${icon} !text-[14px]`} />
      {text}
    </div>
  );
}

function lookupName(fields: FieldDef[], key: string): string {
  return fields.find((f) => f.key === key)?.name ?? key;
}
