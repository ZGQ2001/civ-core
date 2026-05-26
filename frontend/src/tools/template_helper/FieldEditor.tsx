import { useCallback, useState } from 'react';

import { cn } from '../../lib/cn';
import type { CatalogField, FieldLevel } from './types';
import { LEVEL_LABEL } from './types';

const EMPTY_FIELD: CatalogField = {
  key: '',
  name: '',
  group: '',
  level: 'report',
  source: 'userinput',
  value_type: 'string',
  default_format: null,
  aliases: [],
};

const SOURCE_OPTIONS = [
  { value: 'userinput', label: '用户输入（手动填写）' },
  { value: 'parameter', label: '工程参数（同批次共享）' },
  { value: 'rawinput', label: '原始数据（来自 Excel 列）' },
  { value: 'calculated', label: '计算结果（程序计算）' },
];

const LEVEL_OPTIONS: { value: FieldLevel; label: string }[] = [
  { value: 'report', label: '报告级（整份报告填一次）' },
  { value: 'detection_item', label: '检测项目级（每个检测项目）' },
  { value: 'batch', label: '检测批级（每个检测批）' },
  { value: 'component', label: '构件级（每个构件/锚杆）' },
];

const TYPE_OPTIONS = [
  { value: 'string', label: '文本' },
  { value: 'double', label: '小数' },
  { value: 'int', label: '整数' },
  { value: 'bool', label: '布尔' },
];

export function FieldEditor({
  initial,
  isNew,
  existingGroups,
  onSave,
  onCancel,
}: {
  initial?: CatalogField;
  isNew: boolean;
  existingGroups: string[];
  onSave: (field: CatalogField) => void;
  onCancel: () => void;
}) {
  const [field, setField] = useState<CatalogField>(
    initial ?? { ...EMPTY_FIELD },
  );
  const [aliasText, setAliasText] = useState(
    (initial?.aliases ?? []).join(', '),
  );

  const set = useCallback(
    <K extends keyof CatalogField>(key: K, value: CatalogField[K]) => {
      setField((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const handleSave = useCallback(() => {
    if (!field.key.trim() || !field.name.trim()) return;
    const aliases = aliasText
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    onSave({
      ...field,
      key: field.key.trim(),
      name: field.name.trim(),
      aliases,
    });
  }, [field, aliasText, onSave]);

  const keyValid = /^[a-z][a-z0-9_]*$/.test(field.key);

  return (
    <div className="border-vscode-focus space-y-2 rounded border bg-[#1e1e1e] p-3">
      <div className="text-vscode-text mb-1 text-xs font-medium">
        {isNew ? '添加字段' : '编辑字段'}
      </div>

      {/* Row 1: key + name */}
      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-vscode-text-dim text-[10px]">
            Key（英文标识）
          </label>
          <input
            type="text"
            value={field.key}
            onChange={(e) => set('key', e.target.value)}
            disabled={!isNew}
            placeholder="例: project_name"
            className={cn(
              'bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs',
              !isNew && 'opacity-60',
              isNew && field.key && !keyValid && 'border-red-500',
            )}
          />
          {isNew && field.key && !keyValid && (
            <div className="mt-0.5 text-[9px] text-red-400">
              小写字母开头，只含小写字母、数字、下划线
            </div>
          )}
        </div>
        <div className="flex-1">
          <label className="text-vscode-text-dim text-[10px]">
            名称（中文）
          </label>
          <input
            type="text"
            value={field.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="例: 工程名称"
            className="bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs"
          />
        </div>
      </div>

      {/* Row 2: level + source */}
      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-vscode-text-dim text-[10px]">层级</label>
          <select
            value={field.level}
            onChange={(e) => set('level', e.target.value as FieldLevel)}
            className="bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs"
          >
            {LEVEL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {LEVEL_LABEL[o.value]} —{' '}
                {o.label.split('（')[1]?.replace('）', '') ?? ''}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-vscode-text-dim text-[10px]">数据来源</label>
          <select
            value={field.source}
            onChange={(e) => set('source', e.target.value)}
            className="bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Row 3: group + type + format */}
      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-vscode-text-dim text-[10px]">分组</label>
          <input
            type="text"
            value={field.group}
            onChange={(e) => set('group', e.target.value)}
            placeholder="例: 项目信息"
            list="field-groups"
            className="bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs"
          />
          <datalist id="field-groups">
            {existingGroups.map((g) => (
              <option key={g} value={g} />
            ))}
          </datalist>
        </div>
        <div className="w-20">
          <label className="text-vscode-text-dim text-[10px]">类型</label>
          <select
            value={field.value_type}
            onChange={(e) => set('value_type', e.target.value)}
            className="bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs"
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="w-20">
          <label className="text-vscode-text-dim text-[10px]">格式</label>
          <input
            type="text"
            value={field.default_format ?? ''}
            onChange={(e) => set('default_format', e.target.value || null)}
            placeholder="0.00"
            className="bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs"
          />
        </div>
      </div>

      {/* Row 4: aliases */}
      <div>
        <label className="text-vscode-text-dim text-[10px]">
          别名（逗号分隔，用户在模板里的其他写法）
        </label>
        <input
          type="text"
          value={aliasText}
          onChange={(e) => setAliasText(e.target.value)}
          placeholder="例: 项目名称, 工程名"
          className="bg-vscode-input border-vscode-border text-vscode-text mt-0.5 w-full rounded-[2px] border px-2 py-1 text-xs"
        />
      </div>

      {/* Buttons */}
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={handleSave}
          disabled={
            !field.key.trim() || !field.name.trim() || (isNew && !keyValid)
          }
          className="bg-vscode-button hover:bg-vscode-button-hover flex items-center gap-1 rounded-[2px] px-3 py-1 text-xs text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <i className="codicon codicon-check !text-[11px]" />
          {isNew ? '添加' : '保存'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="border-vscode-border rounded-[2px] border bg-[#2d2d2d] px-3 py-1 text-xs hover:bg-[#3a3a3a]"
        >
          取消
        </button>
      </div>
    </div>
  );
}
