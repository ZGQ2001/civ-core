/**
 * 报告填充顶部「预设管理」条 —— 整份 user_inputs 的另存为 / 载入 / 删除。
 *
 * 设计：
 *   - 一份预设 = 一整套 user_inputs（用户拍板「整份报告一套预设」，2026-05-28）。
 *   - 跟 catalog_id 绑定，避免给锚杆报告拉出钻芯的预设。
 *   - 不存 excel_path / word_template_path 等会话级 state；只存能跨报告复用的。
 */
import { useCallback, useEffect, useState } from 'react';

import { rpc } from '../../lib/rpc';
import { logLine, useShell } from '../../lib/shell';
import type { ReportUserInputs } from './types';

interface PresetSummary {
  id: string;
  label: string;
  catalog_id: string;
  updated_at: string;
  field_count: number;
}

interface PresetDto {
  id: string;
  label: string;
  catalog_id: string;
  user_inputs: Record<string, string>;
  updated_at: string;
}

interface Props {
  catalogId: string;
  values: ReportUserInputs;
  /** 载入预设后调用 —— 覆盖当前 user_inputs。 */
  onLoad: (values: ReportUserInputs) => void;
}

export function PresetBar({ catalogId, values, onLoad }: Props) {
  const shell = useShell();
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [showLoadMenu, setShowLoadMenu] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await rpc<{ presets: PresetSummary[] }>(
        'report_preset.list',
        {
          catalog_id: catalogId,
        },
      );
      setPresets(res.presets);
    } catch (e) {
      shell.appendOutput(logLine(`[报告] 加载预设列表失败: ${String(e)}`));
    } finally {
      setLoading(false);
    }
  }, [catalogId, shell]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  const handleLoad = useCallback(
    async (id: string) => {
      try {
        const res = await rpc<{ preset: PresetDto }>('report_preset.get', {
          id,
        });
        onLoad(res.preset.user_inputs);
        shell.appendOutput(
          logLine(
            `[报告] 已载入预设「${res.preset.label}」（${Object.keys(res.preset.user_inputs).length} 字段）`,
          ),
        );
        setShowLoadMenu(false);
      } catch (e) {
        shell.appendOutput(logLine(`[报告] 载入预设失败: ${String(e)}`));
      }
    },
    [onLoad, shell],
  );

  const handleDelete = useCallback(
    async (id: string, label: string) => {
      if (!window.confirm(`确定删除预设「${label}」？此操作不可撤销。`)) return;
      try {
        await rpc('report_preset.delete', { id });
        shell.appendOutput(logLine(`[报告] 已删除预设「${label}」`));
        refresh();
      } catch (e) {
        shell.appendOutput(logLine(`[报告] 删除预设失败: ${String(e)}`));
      }
    },
    [refresh, shell],
  );

  return (
    <div className="border-vscode-border rounded-[3px] border bg-[#252525] p-2">
      <div className="flex items-center gap-2">
        <span
          className="text-vscode-text-dim shrink-0 text-[11px]"
          title="一份预设 = 一整套项目元信息（跨报告复用）"
        >
          报告预设
        </span>
        <div className="text-vscode-text-faint flex-1 text-[10px]">
          {loading
            ? '加载中…'
            : presets.length > 0
              ? `已有 ${presets.length} 套预设可用`
              : '尚无预设 —— 填好元信息后点「另存为」'}
        </div>
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setShowLoadMenu((v) => !v);
              setShowSaveDialog(false);
            }}
            disabled={presets.length === 0}
            className="border-vscode-border rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-[11px] hover:bg-[#3a3a3a] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i className="codicon codicon-list-tree mr-1 !text-[11px]" />
            载入…
          </button>
          {showLoadMenu && presets.length > 0 && (
            <LoadMenu
              presets={presets}
              onPick={handleLoad}
              onDelete={handleDelete}
              onClose={() => setShowLoadMenu(false)}
            />
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            setShowSaveDialog((v) => !v);
            setShowLoadMenu(false);
          }}
          className="border-vscode-border rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-[11px] hover:bg-[#3a3a3a]"
        >
          <i className="codicon codicon-save mr-1 !text-[11px]" />
          另存为…
        </button>
      </div>
      {showSaveDialog && (
        <SaveDialog
          catalogId={catalogId}
          values={values}
          existingIds={new Set(presets.map((p) => p.id))}
          onClose={() => setShowSaveDialog(false)}
          onSaved={() => {
            setShowSaveDialog(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function LoadMenu({
  presets,
  onPick,
  onDelete,
  onClose,
}: {
  presets: PresetSummary[];
  onPick: (id: string) => void;
  onDelete: (id: string, label: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="border-vscode-border absolute top-full right-0 z-50 mt-1 max-h-72 w-72 overflow-y-auto rounded border bg-[#252526] shadow-lg">
      <div className="border-vscode-border flex items-center justify-between border-b px-2 py-1">
        <span className="text-vscode-text-dim text-[10px]">
          点击载入；× 删除
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-vscode-text-dim hover:text-vscode-text"
          title="关闭"
        >
          <i className="codicon codicon-close !text-[11px]" />
        </button>
      </div>
      {presets.map((p) => (
        <div
          key={p.id}
          className="hover:bg-vscode-list-hover group flex items-center gap-2 px-2 py-1.5"
        >
          <button
            type="button"
            onClick={() => onPick(p.id)}
            className="min-w-0 flex-1 text-left"
          >
            <div className="text-vscode-text truncate text-xs">{p.label}</div>
            <div className="text-vscode-text-faint text-[10px]">
              {p.field_count} 字段 · {formatStamp(p.updated_at)}
            </div>
          </button>
          <button
            type="button"
            onClick={() => onDelete(p.id, p.label)}
            className="shrink-0 p-0.5 text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-300"
            title="删除"
          >
            <i className="codicon codicon-trash !text-[11px]" />
          </button>
        </div>
      ))}
    </div>
  );
}

function SaveDialog({
  catalogId,
  values,
  existingIds,
  onClose,
  onSaved,
}: {
  catalogId: string;
  values: ReportUserInputs;
  existingIds: Set<string>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const shell = useShell();
  const [label, setLabel] = useState('');
  const [id, setId] = useState('');
  const [saving, setSaving] = useState(false);

  const filledCount = Object.values(values).filter((v) => v?.trim()).length;
  const overwrite = id && existingIds.has(id);

  const handleSave = useCallback(async () => {
    if (!label.trim() || !id.trim()) return;
    setSaving(true);
    try {
      // 只存非空字段，节省存储 + 避免覆盖空字段
      const compact: Record<string, string> = {};
      for (const [k, v] of Object.entries(values)) {
        if (v?.trim()) compact[k] = v;
      }
      await rpc('report_preset.save', {
        preset: {
          id: id.trim(),
          label: label.trim(),
          catalog_id: catalogId,
          user_inputs: compact,
        },
      });
      shell.appendOutput(
        logLine(
          `[报告] 已保存预设「${label}」（${Object.keys(compact).length} 字段）`,
        ),
      );
      onSaved();
    } catch (e) {
      shell.appendOutput(logLine(`[报告] 保存预设失败: ${String(e)}`));
    } finally {
      setSaving(false);
    }
  }, [label, id, catalogId, values, shell, onSaved]);

  return (
    <div className="border-vscode-border mt-2 space-y-2 rounded border bg-[#1f1f1f] p-2">
      <div className="text-vscode-text-dim text-[10px]">
        把当前已填的 {filledCount} 项 user_inputs 保存为「{catalogId}
        」目录下的预设
      </div>
      <input
        type="text"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="预设名称（中文，例：XX环境整治-标准模板）"
        className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
        autoFocus
      />
      <input
        type="text"
        value={id}
        onChange={(e) => setId(e.target.value)}
        placeholder="预设 ID（英文小写下划线，例：xx_env_standard）"
        className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
      />
      {overwrite && (
        <div className="text-[10px] text-yellow-400">
          <i className="codicon codicon-warning mr-1 !text-[11px]" />
          ID 已存在：保存将覆盖同 ID 旧预设
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={!label.trim() || !id.trim() || saving}
          className="bg-vscode-button hover:bg-vscode-button-hover rounded-[2px] px-3 py-1 text-[11px] text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? '保存中…' : '保存'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="text-vscode-text-dim text-[11px] hover:underline"
        >
          取消
        </button>
      </div>
    </div>
  );
}

function formatStamp(iso: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch {
    return iso;
  }
}
