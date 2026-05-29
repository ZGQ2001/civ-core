/**
 * data_processing 右侧 RightPanel「调参」tab：按 calcType 切对应算法的参数面板。
 *   - leeb: 输出路径 + 默认测量角度
 *   - anchor: 规范下拉 + 生成模板按钮 + batch_id 列名 + 按批次参数卡片
 */
import { useCallback } from 'react';
import { save as saveDialog } from '@tauri-apps/plugin-dialog';
import { openPath } from '@tauri-apps/plugin-opener';

import { logLine, useShell } from '../../lib/shell';
import { AnchorParamsSection } from '../_shared/anchorParamsForm';
import { Field, INPUT_CLS, Picker, ResetBtn, Select } from '../_shared/forms';
import { useDataProcessing } from './controller';
import {
  ANCHOR_STANDARDS,
  type AnchorStandard,
  COATING_STANDARDS,
  type CoatingStandard,
} from './types';

export function DataProcessingSettingsForm() {
  const c = useDataProcessing();

  const pickOutput = useCallback(async () => {
    const sel = await saveDialog({
      title: '保存结果 Excel 为',
      defaultPath: c.defaultOutput || undefined,
      filters: [{ name: 'Excel', extensions: ['xlsx'] }],
    });
    if (typeof sel === 'string') c.setOutputPath(sel);
  }, [c]);

  return (
    <div className="flex h-full flex-col space-y-4 overflow-auto p-4 text-xs">
      <Field label="输出 Excel 路径" hint="留空 = 与输入同级 / 同名加后缀">
        <Picker
          value={c.outputPath || c.defaultOutput}
          onPick={pickOutput}
          placeholder="（选 Excel 后自动）"
          muted={!c.outputPath}
          extra={
            c.outputPath ? (
              <ResetBtn onClick={() => c.setOutputPath('')} />
            ) : undefined
          }
        />
      </Field>

      {c.calcType === 'leeb' && (
        <Field
          label="默认测量角度（度）"
          hint="构件未指定角度时用此值；常用 0 / 90 / 180"
        >
          <input
            type="number"
            value={c.angle}
            onChange={(e) => c.setAngle(parseFloat(e.target.value || '0'))}
            className={`${INPUT_CLS} w-32`}
          />
        </Field>
      )}

      {c.calcType === 'anchor' && <AnchorSubForm />}

      {c.calcType === 'coating' && <CoatingSubForm />}

      <div className="text-vscode-text-faint pt-2 text-[11px]">
        选好 Excel 后点工具页顶部「开始计算」即可；结果会显示在工具页底部。
      </div>
    </div>
  );
}

// ── anchor 子 form ────────────────────────────────────────

function AnchorSubForm() {
  const c = useDataProcessing();
  const shell = useShell();

  const genTemplate = useCallback(async () => {
    // saveDialog 自身可能抛 permission/IO 错——必须 catch，否则错误进 unhandledrejection 静默
    shell.appendOutput(logLine('[锚杆] 点击「生成模板」→ 打开保存对话框'));
    let savePath: string;
    try {
      const sel = await saveDialog({
        title: '保存锚杆抗拔输入模板为',
        defaultPath: '锚杆抗拔输入模板.xlsx',
        filters: [{ name: 'Excel', extensions: ['xlsx'] }],
      });
      if (typeof sel !== 'string') {
        shell.appendOutput(logLine('[锚杆] 已取消'));
        return;
      }
      savePath = sel;
    } catch (e) {
      const msg = String(e);
      console.error('saveDialog 失败:', e);
      shell.appendOutput(logLine(`[锚杆] 保存对话框失败: ${msg}`));
      return;
    }
    const written = await c.generateAnchorTemplate(savePath);
    if (written) {
      try {
        await openPath(written);
      } catch (e) {
        // 没装关联程序就忽略，但日志记一笔便于排查
        shell.appendOutput(
          logLine(`[锚杆] 自动打开失败（已生成，请手动打开）: ${String(e)}`),
        );
      }
    }
  }, [c, shell]);

  return (
    <>
      <Field label="规范" hint="未来可扩展其他规范；当前仅支持 GB 50086-2015">
        <Select
          value={c.anchorStandard}
          onChange={(e) =>
            c.setAnchorStandard(e.target.value as AnchorStandard)
          }
          className="w-full"
        >
          {ANCHOR_STANDARDS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="输入数据模板" hint="生成空白模板让用户照样例填写">
        <button
          type="button"
          onClick={genTemplate}
          disabled={c.anchorTemplateStatus.kind === 'running'}
          className="border-vscode-border flex w-full items-center justify-center gap-2 rounded-[2px] border bg-[#2d2d2d] px-3 py-1.5 text-xs hover:bg-[#3a3a3a] disabled:opacity-60"
        >
          {c.anchorTemplateStatus.kind === 'running' ? (
            <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
          ) : (
            <i className="codicon codicon-new-file !text-[12px]" />
          )}
          {c.anchorTemplateStatus.kind === 'running' ? '生成中…' : '生成模板…'}
        </button>
        {c.anchorTemplateStatus.kind === 'ok' && (
          <div className="mt-1 flex items-start gap-1 text-[11px] text-green-400">
            <i className="codicon codicon-pass mt-0.5 shrink-0 !text-[12px]" />
            <span className="break-all">
              已生成：{c.anchorTemplateStatus.path}
            </span>
          </div>
        )}
        {c.anchorTemplateStatus.kind === 'error' && (
          <div className="mt-1 text-[11px] whitespace-pre-wrap text-red-400">
            <i className="codicon codicon-error mr-1 !text-[12px]" />
            生成失败：{c.anchorTemplateStatus.message}
          </div>
        )}
      </Field>

      <Field label="批次列名" hint="从当前 Excel 表头里选用于区分批次的列">
        <BatchIdColumnSelect />
      </Field>

      <DataProcessingAnchorParams />

      <div className="border-vscode-border bg-vscode-input/30 rounded-[3px] border px-3 py-2 text-[11px] leading-relaxed">
        <i className="codicon codicon-info text-vscode-focus mr-1 !text-[12px]" />
        Word 报告生成已迁到独立的「报告填充」工具（左侧 Activity Bar）。
        数据处理只算 + 出 Excel；算完后切到「报告填充」选 Word 模板 +
        填项目信息出 docx。
      </div>
    </>
  );
}

function BatchIdColumnSelect() {
  const c = useDataProcessing();
  const headers = c.previewHeaders;
  const valueInHeaders =
    !c.anchorBatchIdColumn || headers.includes(c.anchorBatchIdColumn);
  const title = c.previewError
    ? `读表头失败: ${c.previewError}`
    : c.previewLoading
      ? '正在读表头…'
      : !c.excelPath
        ? '先选 Excel 才能列出表头'
        : '从当前 Excel 的表头里选';
  return (
    <Select
      value={c.anchorBatchIdColumn}
      onChange={(e) => c.setAnchorBatchIdColumn(e.target.value)}
      title={title}
      className="w-full"
    >
      <option value="">（请选择）</option>
      {headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
      {!valueInHeaders && (
        <option value={c.anchorBatchIdColumn}>
          {c.anchorBatchIdColumn}（不在当前表头）
        </option>
      )}
    </Select>
  );
}

/** AnchorSubForm 里渲染的"按批次工程参数"区——绑定到 controller 的 props 适配。 */
function DataProcessingAnchorParams() {
  const c = useDataProcessing();
  return (
    <AnchorParamsSection
      excelReady={!!c.excelPath}
      batchIds={c.anchorBatchIds}
      paramsByBatch={c.anchorParamsByBatch}
      loading={c.anchorBatchesLoading}
      error={c.anchorBatchesError}
      onSetBatch={c.setAnchorParamsForBatch}
      onSetAll={c.setAnchorParamsForAllBatches}
      emptyHint="先在主界面选输入 Excel，这里会按批次展开参数表"
    />
  );
}

// ── coating 子 form ───────────────────────────────────────
// 比 anchor 简单：设计厚度在 Excel「设计厚度」列里按构件填，无需按批次填工程参数。

function CoatingSubForm() {
  const c = useDataProcessing();
  const shell = useShell();

  const genTemplate = useCallback(async () => {
    shell.appendOutput(logLine('[防火涂层] 点击「生成模板」→ 打开保存对话框'));
    let savePath: string;
    try {
      const sel = await saveDialog({
        title: '保存防火涂层厚度输入模板为',
        defaultPath: '防火涂层厚度输入模板.xlsx',
        filters: [{ name: 'Excel', extensions: ['xlsx'] }],
      });
      if (typeof sel !== 'string') {
        shell.appendOutput(logLine('[防火涂层] 已取消'));
        return;
      }
      savePath = sel;
    } catch (e) {
      const msg = String(e);
      console.error('saveDialog 失败:', e);
      shell.appendOutput(logLine(`[防火涂层] 保存对话框失败: ${msg}`));
      return;
    }
    const written = await c.generateCoatingTemplate(savePath);
    if (written) {
      try {
        await openPath(written);
      } catch (e) {
        shell.appendOutput(
          logLine(
            `[防火涂层] 自动打开失败（已生成，请手动打开）: ${String(e)}`,
          ),
        );
      }
    }
  }, [c, shell]);

  return (
    <>
      <Field
        label="规范"
        hint="GB 50205-2020 §13.4.3 厚涂型防火涂料涂层厚度验收"
      >
        <Select
          value={c.coatingStandard}
          onChange={(e) =>
            c.setCoatingStandard(e.target.value as CoatingStandard)
          }
          className="w-full"
        >
          {COATING_STANDARDS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="输入数据模板" hint="长表（每行一测点）；含梁/柱样例">
        <button
          type="button"
          onClick={genTemplate}
          disabled={c.coatingTemplateStatus.kind === 'running'}
          className="border-vscode-border flex w-full items-center justify-center gap-2 rounded-[2px] border bg-[#2d2d2d] px-3 py-1.5 text-xs hover:bg-[#3a3a3a] disabled:opacity-60"
        >
          {c.coatingTemplateStatus.kind === 'running' ? (
            <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
          ) : (
            <i className="codicon codicon-new-file !text-[12px]" />
          )}
          {c.coatingTemplateStatus.kind === 'running' ? '生成中…' : '生成模板…'}
        </button>
        {c.coatingTemplateStatus.kind === 'ok' && (
          <div className="mt-1 flex items-start gap-1 text-[11px] text-green-400">
            <i className="codicon codicon-pass mt-0.5 shrink-0 !text-[12px]" />
            <span className="break-all">
              已生成：{c.coatingTemplateStatus.path}
            </span>
          </div>
        )}
        {c.coatingTemplateStatus.kind === 'error' && (
          <div className="mt-1 text-[11px] whitespace-pre-wrap text-red-400">
            <i className="codicon codicon-error mr-1 !text-[12px]" />
            生成失败：{c.coatingTemplateStatus.message}
          </div>
        )}
      </Field>

      <Field
        label="批次列名"
        hint="用于区分批次的列；不分批可留默认（无此列则全部归一批）"
      >
        <CoatingBatchIdColumnSelect />
      </Field>

      <div className="border-vscode-border bg-vscode-input/30 rounded-[3px] border px-3 py-2 text-[11px] leading-relaxed">
        <i className="codicon codicon-info text-vscode-focus mr-1 !text-[12px]" />
        判定（按构件）：≥80% 测点 ≥ 设计厚度，且最薄处 ≥ 设计 × 85%。设计厚度在
        Excel「设计厚度」列里按构件填，无需在此填参数。
      </div>
    </>
  );
}

function CoatingBatchIdColumnSelect() {
  const c = useDataProcessing();
  const headers = c.previewHeaders;
  const valueInHeaders =
    !c.coatingBatchIdColumn || headers.includes(c.coatingBatchIdColumn);
  const title = c.previewError
    ? `读表头失败: ${c.previewError}`
    : c.previewLoading
      ? '正在读表头…'
      : !c.excelPath
        ? '先选 Excel 才能列出表头'
        : '从当前 Excel 的表头里选';
  return (
    <Select
      value={c.coatingBatchIdColumn}
      onChange={(e) => c.setCoatingBatchIdColumn(e.target.value)}
      title={title}
      className="w-full"
    >
      <option value="批次">批次（默认）</option>
      {headers
        .filter((h) => h !== '批次')
        .map((h) => (
          <option key={h} value={h}>
            {h}
          </option>
        ))}
      {!valueInHeaders && c.coatingBatchIdColumn !== '批次' && (
        <option value={c.coatingBatchIdColumn}>
          {c.coatingBatchIdColumn}（不在当前表头）
        </option>
      )}
    </Select>
  );
}
