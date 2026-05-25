/**
 * ToolBar —— 顶部操作条：选 docx / 模板名 / 重复策略 / 保存 / 新建 / 当前编辑状态。
 *
 * 解耦：只调 controller actions，不直接 rpc。
 */
import { useCallback } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { cn } from '../../../lib/cn';
import { useTemplateEditor } from '../controller';
import type { RepeatStrategy } from '../types';

export function ToolBar() {
  const c = useTemplateEditor();

  const pickDocx = useCallback(async () => {
    const sel = await openDialog({
      title: '选择 Word 模板（含 [[数据绑定区]] 锚点 + 目标表格）',
      multiple: false,
      filters: [{ name: 'Word', extensions: ['docx'] }],
    });
    if (typeof sel === 'string') c.setSourceDocxPath(sel);
  }, [c]);

  const handleSave = useCallback(async () => {
    const defaultName = c.currentName ?? c.displayName.trim() ?? '新模板';
    const name =
      c.currentName ?? window.prompt('模板名（目录名）:', defaultName);
    if (!name || !name.trim()) return;
    const ok = await c.saveTemplate(name.trim());
    if (ok) alert(`已保存：${name.trim()}`);
  }, [c]);

  return (
    <div className="border-vscode-border space-y-2 border-b px-6 pt-4 pb-3">
      <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
        <i className="codicon codicon-table !text-[16px]" />
        模板编辑
        {c.currentName && (
          <span className="text-vscode-focus ml-2 text-xs font-normal">
            （编辑：{c.currentName}）
          </span>
        )}
        {!c.currentName && c.parsed && (
          <span className="text-vscode-text-faint ml-2 text-xs font-normal">
            （新模板未保存）
          </span>
        )}
      </h1>
      <div className="flex flex-wrap items-center gap-2">
        <Btn icon="folder-opened" onClick={pickDocx} label="选 Word 模板…" />
        {c.sourceDocxPath && (
          <span
            className="text-vscode-text-dim max-w-[280px] truncate text-xs"
            title={c.sourceDocxPath}
          >
            {c.sourceDocxPath.split(/[\\/]/).pop()}
          </span>
        )}

        <span className="text-vscode-text-faint">·</span>
        <label className="text-vscode-text-dim text-xs">标题:</label>
        <input
          type="text"
          value={c.displayName}
          onChange={(e) => c.setDisplayName(e.target.value)}
          placeholder="如：锚杆抗拔试验报告"
          className="bg-vscode-input border-vscode-border text-vscode-text w-44 rounded-[2px] border px-2 py-1 text-xs"
        />

        <span className="text-vscode-text-faint">·</span>
        <label className="text-vscode-text-dim text-xs">重复:</label>
        <select
          value={c.repeat}
          onChange={(e) => c.setRepeat(e.target.value as RepeatStrategy)}
          className="bg-vscode-input border-vscode-border text-vscode-text rounded-[2px] border px-2 py-1 text-xs"
        >
          <option value="per_row">一行一张表</option>
          <option value="per_batch" disabled>
            一批一张表（Phase 3）
          </option>
        </select>

        <div className="ml-auto flex items-center gap-2">
          <Btn icon="new-file" onClick={c.startNewTemplate} label="新建" />
          <Btn
            icon="save"
            onClick={handleSave}
            label={c.saving ? '保存中…' : '保存'}
            disabled={!c.parsed || c.saving}
            primary
          />
        </div>
      </div>
      {c.saveError && (
        <div className="text-xs text-red-400">
          <i className="codicon codicon-error mr-1 !text-[12px]" />
          {c.saveError}
        </div>
      )}
    </div>
  );
}

function Btn({
  icon,
  label,
  onClick,
  disabled,
  primary,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex shrink-0 items-center gap-1 rounded-[2px] border px-2 py-1 text-xs transition-colors',
        primary
          ? 'border-vscode-focus bg-vscode-button hover:bg-vscode-button-hover text-white'
          : 'border-vscode-border bg-[#2d2d2d] hover:bg-[#3a3a3a]',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <i className={`codicon codicon-${icon} !text-[12px]`} />
      {label}
    </button>
  );
}
