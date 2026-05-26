import { useCallback } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { Field, Picker, RunBtn } from '../_shared/forms';
import { useTemplateHelper } from './controller';

export function TemplateHelperSettingsForm() {
  const c = useTemplateHelper();

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
    await c.validate();
  }, [c]);

  return (
    <div className="space-y-4 p-3">
      {/* Catalog selector */}
      <Field label="字段目录" hint="选择当前检测类型的字段定义">
        <div className="flex gap-2">
          <select
            value={c.activeCatalogId ?? ''}
            onChange={(e) => {
              if (e.target.value) c.selectCatalog(e.target.value);
            }}
            className="bg-vscode-input border-vscode-border text-vscode-text flex-1 rounded-[2px] border px-2 py-1 text-xs"
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
            className="border-vscode-border flex shrink-0 items-center rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-xs hover:bg-[#3a3a3a]"
            title="刷新目录列表"
          >
            <i className="codicon codicon-refresh !text-[12px]" />
          </button>
        </div>
      </Field>

      {/* Template file picker */}
      <Field label="模板文件" hint="选择要验证的 Word 模板 (.docx)">
        <Picker
          value={c.docxPath}
          onPick={handlePickDocx}
          placeholder="选择 .docx 模板文件"
          muted={!c.docxPath}
        />
      </Field>

      {/* Validate button */}
      <RunBtn
        running={c.validating}
        disabled={!c.docxPath || !c.activeCatalogId || c.validating}
        onClick={handleValidate}
      >
        验证模板
      </RunBtn>

      {/* Validation summary */}
      {c.validateResult && (
        <div className="border-vscode-border space-y-1 rounded border p-2">
          <div className="text-vscode-text-dim text-[11px] font-medium">
            验证摘要
          </div>
          <SummaryRow
            icon="codicon-check"
            color="text-green-400"
            label="已匹配"
            count={c.validateResult.summary.matched_count}
          />
          <SummaryRow
            icon="codicon-warning"
            color="text-yellow-400"
            label="未识别"
            count={c.validateResult.summary.unrecognized_count}
          />
          <SummaryRow
            icon="codicon-circle-outline"
            color="text-vscode-text-faint"
            label="未使用"
            count={c.validateResult.summary.unused_count}
          />
        </div>
      )}

      {/* Help */}
      <div className="border-vscode-border space-y-1.5 rounded border p-2">
        <div className="text-vscode-text-dim text-[11px] font-medium">
          使用说明
        </div>
        <div className="text-vscode-text-faint space-y-1 text-[11px] leading-relaxed">
          <p>1. 在左侧字段面板中点击字段，占位符自动复制到剪贴板</p>
          <p>2. 打开 Word 模板，在需要填充的位置粘贴</p>
          <p>3. 选择模板文件后点击「验证模板」检查占位符正确性</p>
        </div>
        <div className="border-vscode-border mt-2 space-y-1 border-t pt-2">
          <div className="text-vscode-text-dim text-[11px]">占位符格式</div>
          <div className="text-vscode-text-faint text-[11px]">
            <code className="text-[#ce9178]">{'{{字段名}}'}</code> — 文本/数值
          </div>
          <div className="text-vscode-text-faint text-[11px]">
            <code className="text-[#ce9178]">{'{{img:字段名}}'}</code> — 图片
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryRow({
  icon,
  color,
  label,
  count,
}: {
  icon: string;
  color: string;
  label: string;
  count: number;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <i className={`codicon ${icon} ${color} !text-[12px]`} />
      <span className="text-vscode-text-dim">{label}</span>
      <span className="text-vscode-text ml-auto">{count}</span>
    </div>
  );
}
