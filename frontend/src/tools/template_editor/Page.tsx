/**
 * 模板编辑器主区 —— 字段对照表 + 使用说明。
 *
 * 用户在 Word 模板里手写 {key} 或 {中文名}；本页只是"作弊条"——
 * 点字段把 {key} 复制到剪贴板。
 */
import { useState } from 'react';

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

export function TemplateEditorPage() {
  const c = useTemplateEditor();

  return (
    <div className="flex h-full flex-col overflow-auto">
      <Header />
      <UsageBlock />
      {c.loading ? (
        <Spinner text="加载字段清单…" />
      ) : c.error ? (
        <ErrorBlock msg={c.error} />
      ) : (
        <FieldTable fields={c.fields} />
      )}
    </div>
  );
}

// ── 顶部 ────────────────────────────────────────────────

function Header() {
  const c = useTemplateEditor();
  return (
    <div className="border-vscode-border space-y-1 border-b px-6 pt-4 pb-3">
      <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
        <i className="codicon codicon-table !text-[16px]" />
        模板字段对照表
        <span className="text-vscode-text-faint ml-2 text-xs font-normal">
          （{c.projectType}）
        </span>
      </h1>
      <div className="text-vscode-text-dim text-xs">
        在 Word 模板里写{' '}
        <code className="bg-vscode-input rounded px-1">{'{key}'}</code> 或{' '}
        <code className="bg-vscode-input rounded px-1">{'{中文名}'}</code>{' '}
        占位符；锚杆数据样表上方插一段{' '}
        <code className="bg-vscode-input rounded px-1">[[每根锚杆]]</code>{' '}
        标记。点字段名复制 key 到剪贴板。
      </div>
    </div>
  );
}

// ── 用法说明 ────────────────────────────────────────────

function UsageBlock() {
  return (
    <details className="border-vscode-border mx-6 my-3 rounded border bg-[#252525] text-xs">
      <summary className="text-vscode-text-dim cursor-pointer px-3 py-2 hover:text-white">
        <i className="codicon codicon-book !text-[12px]" /> 完整用法 / 跨 Run
        注意事项 / 锚点说明
      </summary>
      <div className="text-vscode-text-dim space-y-1.5 px-3 pb-3">
        <p>
          <span className="text-vscode-text">1. 项目级字段</span>（如{' '}
          {'{client_name}'} {'{project_name}'}）写在 Word
          任何位置，引擎按批次填一次。
        </p>
        <p>
          <span className="text-vscode-text">2. 单根锚杆字段</span>（如{' '}
          {'{anchor_id}'} {'{弹性位移量 M (mm)}'}）写在样表内；样表前段落含{' '}
          <code className="bg-vscode-input rounded px-1">[[每根锚杆]]</code>{' '}
          标记，引擎按锚杆数克隆样表。
        </p>
        <p>
          <span className="text-vscode-text">3. 跨 Run 注意</span>：Word
          输入法可能把 {'{anchor_id}'} 拆成多 Run。引擎段落级合并 Run
          文本再替换，所以肉眼看到完整占位符就
          OK；同段落多字体样式会丢，只保留首 Run。
        </p>
        <p>
          <span className="text-vscode-text">4. 拼错的字段</span>
          会留原文不替换，生成完会列出 unknown_keys 提示。
        </p>
      </div>
    </details>
  );
}

// ── 字段表 ────────────────────────────────────────────

function FieldTable({ fields }: { fields: FieldDef[] }) {
  const grouped = SOURCE_ORDER.map((s) => ({
    source: s,
    items: fields.filter((f) => f.source === s),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="space-y-4 px-6 pb-6">
      {grouped.map((g) => (
        <FieldGroup key={g.source} source={g.source} items={g.items} />
      ))}
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
      <div className="text-vscode-text-dim mb-2 text-[11px] tracking-wider uppercase">
        {SOURCE_LABEL[source]}（{items.length}）
      </div>
      <div className="grid grid-cols-1 gap-1 md:grid-cols-2">
        {items.map((f) => (
          <FieldRow key={f.key} field={f} />
        ))}
      </div>
    </div>
  );
}

function FieldRow({ field }: { field: FieldDef }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const text = `{${field.key}}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      // 剪贴板权限失败时静默 —— 用户可手抄
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      title={`点击复制 {${field.key}}`}
      className={cn(
        'border-vscode-border group hover:bg-vscode-hover flex w-full items-baseline gap-2 rounded border px-3 py-1.5 text-left text-xs transition-colors',
      )}
    >
      <span className="text-vscode-text">{field.name}</span>
      <code
        className={cn(
          'text-vscode-text-dim ml-auto font-mono text-[11px]',
          copied && 'text-green-400',
        )}
      >
        {copied ? '已复制' : `{${field.key}}`}
      </code>
      <span className="text-vscode-text-faint font-mono text-[10px]">
        {field.value_type}
        {field.default_format && ` · ${field.default_format}`}
      </span>
    </button>
  );
}

// ── 状态块 ────────────────────────────────────────────

function Spinner({ text }: { text: string }) {
  return (
    <div className="text-vscode-text-dim flex items-center gap-2 px-6 py-3 text-xs">
      <i className="codicon codicon-loading codicon-modifier-spin !text-[14px]" />
      {text}
    </div>
  );
}

function ErrorBlock({ msg }: { msg: string }) {
  return (
    <div className="m-6 rounded border border-l-2 border-l-red-400 bg-[#2d2d2d] p-3 text-xs whitespace-pre-wrap text-red-400">
      <i className="codicon codicon-error mr-1 !text-[14px]" />
      读字段失败：{msg}
    </div>
  );
}
