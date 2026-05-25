/**
 * 模板编辑器右侧 RightPanel —— Phase 2 骨架：可用字段清单只读展示。
 *
 * 后续：点击格子时该面板变交互（点字段名 → 绑到当前格）。
 */
import { cn } from '../../lib/cn';
import { useTemplateEditor } from './controller';
import type { FieldDef, FieldSource } from './types';

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

export function TemplateEditorSettingsForm() {
  const c = useTemplateEditor();

  if (c.fieldsLoading) {
    return (
      <div className="text-vscode-text-dim flex items-center gap-2 p-3 text-xs">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[14px]" />
        加载字段清单…
      </div>
    );
  }

  if (c.fieldsError) {
    return (
      <div className="p-3 text-xs whitespace-pre-wrap text-red-400">
        <i className="codicon codicon-error mr-1 !text-[14px]" />
        读字段失败：{c.fieldsError}
      </div>
    );
  }

  const grouped = SOURCE_ORDER.map((s) => ({
    source: s,
    items: c.fields.filter((f) => f.source === s),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="flex h-full flex-col text-xs">
      <div className="border-vscode-border shrink-0 border-b px-3 py-2">
        <div className="text-vscode-text font-medium">
          可用字段（{c.projectType}）
        </div>
        <div className="text-vscode-text-faint mt-0.5 text-[11px]">
          点格子绑定 / 拖拽建设中
        </div>
      </div>
      <div className="flex-1 space-y-3 overflow-auto p-3">
        {grouped.map((g) => (
          <FieldGroup key={g.source} source={g.source} items={g.items} />
        ))}
      </div>
    </div>
  );
}

function FieldGroup({
  source,
  items,
}: {
  source: FieldSource;
  items: FieldDef[];
}) {
  return (
    <div>
      <div className="text-vscode-text-dim mb-1.5 text-[10px] tracking-wider uppercase">
        {SOURCE_LABEL[source]}（{items.length}）
      </div>
      <ul className="space-y-1">
        {items.map((f) => (
          <li
            key={f.key}
            className={cn(
              'border-vscode-border flex items-baseline gap-2 rounded border px-2 py-1',
              'text-vscode-text-dim cursor-default',
            )}
            title={f.key}
          >
            <span className="text-vscode-text">{f.name}</span>
            <span className="text-vscode-text-faint ml-auto font-mono text-[10px]">
              {f.value_type}
              {f.default_format && ` · ${f.default_format}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
