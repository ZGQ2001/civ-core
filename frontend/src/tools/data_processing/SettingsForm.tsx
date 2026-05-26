/**
 * data_processing 右侧 RightPanel「调参」tab：按 calcType 切对应算法的参数面板。
 *   - leeb: 输出路径 + 默认测量角度
 *   - anchor: 规范下拉 + 生成模板按钮 + batch_id 列名 + 按批次参数卡片
 */
import { useCallback, useState } from 'react';
import { save as saveDialog } from '@tauri-apps/plugin-dialog';
import { openPath } from '@tauri-apps/plugin-opener';

import { logLine, useShell } from '../../lib/shell';
import { Field, Picker, ResetBtn } from '../_shared/forms';
import { useDataProcessing } from './controller';
import {
  ANCHOR_STANDARDS,
  DEFAULT_ANCHOR_PARAMS,
  type AnchorParams,
  type AnchorStandard,
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
            className="bg-vscode-input border-vscode-border text-vscode-text w-32 rounded-[2px] border px-2 py-1 text-xs"
          />
        </Field>
      )}

      {c.calcType === 'anchor' && <AnchorSubForm />}

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
        <select
          value={c.anchorStandard}
          onChange={(e) =>
            c.setAnchorStandard(e.target.value as AnchorStandard)
          }
          className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
        >
          {ANCHOR_STANDARDS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
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

      <AnchorParamsSection />

      <div className="border-vscode-border bg-vscode-input/30 rounded-[3px] border px-3 py-2 text-[11px] leading-relaxed">
        <i className="codicon codicon-info text-vscode-focus mr-1 !text-[12px]" />
        Word 报告生成已迁到独立的「报告填充」工具（左侧 Activity Bar）。
        数据处理只算 + 出 Excel；算完后切到「报告填充」选 Word 模板 + 填项目信息出 docx。
      </div>
    </>
  );
}

function BatchIdColumnSelect() {
  const c = useDataProcessing();
  const headers = c.previewHeaders;
  const valueInHeaders = !c.anchorBatchIdColumn || headers.includes(c.anchorBatchIdColumn);
  const title = c.previewError
    ? `读表头失败: ${c.previewError}`
    : c.previewLoading
      ? '正在读表头…'
      : !c.excelPath
        ? '先选 Excel 才能列出表头'
        : '从当前 Excel 的表头里选';
  return (
    <select
      value={c.anchorBatchIdColumn}
      onChange={(e) => c.setAnchorBatchIdColumn(e.target.value)}
      title={title}
      className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
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
    </select>
  );
}

/** 锚杆 5 个工程参数的字段定义 —— 中文名 + 变量符号 + 单位 + 解释。 */
const ANCHOR_PARAM_FIELDS: Array<{
  key: keyof AnchorParams;
  symbol: string;
  name: string;
  unit: string;
  hint: string;
}> = [
  {
    key: 'P',
    symbol: 'P',
    name: '轴向拉力设计值',
    unit: 'N',
    hint: '锚杆设计承受的最大轴向拉力（即 Nt）；用于算各级荷载 0.1Nt/0.4Nt/.../1.2Nt',
  },
  {
    key: 'Lf',
    symbol: 'Lf',
    name: '自由段长度',
    unit: 'mm',
    hint: '锚杆从锚头到锚固段起点的长度；与 La 共同决定位移上下限',
  },
  {
    key: 'La',
    symbol: 'La',
    name: '锚固段长度',
    unit: 'mm',
    hint: '锚杆嵌入岩土的有效锚固长度（与水泥浆体接触段）',
  },
  {
    key: 'A',
    symbol: 'A',
    name: '钢筋截面面积',
    unit: 'mm²',
    hint: '锚杆杆体钢筋截面积；E·A 决定弹性变形量',
  },
  {
    key: 'E',
    symbol: 'E',
    name: '弹性模量',
    unit: 'N/mm²',
    hint: '锚杆杆体材料弹性模量（钢筋取 2.0×10⁵）',
  },
];

function AnchorParamsSection() {
  const c = useDataProcessing();

  if (!c.excelPath) {
    return (
      <div className="text-vscode-text-faint text-[11px] italic">
        先在主界面选输入 Excel，这里会按批次展开参数表
      </div>
    );
  }
  if (c.anchorBatchesLoading) {
    return (
      <div className="text-vscode-text-dim flex items-center gap-1 text-[11px]">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
        加载批次清单…
      </div>
    );
  }
  if (c.anchorBatchesError) {
    return (
      <div className="text-[11px] whitespace-pre-wrap text-red-400">
        读批次失败：{c.anchorBatchesError}
      </div>
    );
  }
  if (c.anchorBatchIds.length === 0) {
    return (
      <div className="text-vscode-text-faint text-[11px] italic">
        Excel 里没读到任何批次（检查批次列名是否对得上）
      </div>
    );
  }

  return (
    <Field
      label={`锚杆工程参数（共 ${c.anchorBatchIds.length} 批）`}
      hint="同批次所有锚杆共用一组参数；点卡片标题展开/收起"
    >
      <div className="space-y-2">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() =>
              c.setAnchorParamsForAllBatches(DEFAULT_ANCHOR_PARAMS)
            }
            className="text-vscode-focus text-[11px] hover:underline"
            title={ANCHOR_PARAM_FIELDS.map(
              (f) => `${f.symbol}=${DEFAULT_ANCHOR_PARAMS[f.key]}${f.unit}`,
            ).join(' / ')}
          >
            全部批次填默认值
          </button>
        </div>

        <div className="space-y-2">
          {c.anchorBatchIds.map((batchId, idx) => (
            <BatchParamsCard
              key={batchId}
              batchId={batchId}
              params={c.anchorParamsByBatch[batchId] ?? DEFAULT_ANCHOR_PARAMS}
              defaultExpanded={c.anchorBatchIds.length <= 3 || idx === 0}
              onChange={(p) => c.setAnchorParamsForBatch(batchId, p)}
              onFillDefault={() =>
                c.setAnchorParamsForBatch(batchId, { ...DEFAULT_ANCHOR_PARAMS })
              }
            />
          ))}
        </div>
      </div>
    </Field>
  );
}

function BatchParamsCard({
  batchId,
  params,
  defaultExpanded,
  onChange,
  onFillDefault,
}: {
  batchId: string;
  params: AnchorParams;
  defaultExpanded: boolean;
  onChange: (p: AnchorParams) => void;
  onFillDefault: () => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="border-vscode-border rounded-[3px] border bg-[#252525]">
      <div
        className="hover:bg-vscode-hover flex cursor-pointer items-center px-2 py-1.5 select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <i
          className={`codicon codicon-chevron-${expanded ? 'down' : 'right'} text-vscode-text-dim mr-1 !text-[12px]`}
        />
        <i className="codicon codicon-symbol-misc text-vscode-text-dim mr-1.5 !text-[12px]" />
        <span
          className="text-vscode-text truncate text-[12px] font-medium"
          title={batchId}
        >
          {batchId}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onFillDefault();
          }}
          className="text-vscode-focus ml-auto text-[10px] hover:underline"
          title="给本批次填默认值"
        >
          填默认
        </button>
      </div>

      {expanded && (
        <div className="border-vscode-border space-y-2.5 border-t px-3 py-2">
          {ANCHOR_PARAM_FIELDS.map((f) => (
            <div key={f.key}>
              <div className="mb-0.5 flex items-baseline gap-1.5">
                <span className="text-vscode-text text-[11px] font-medium">
                  {f.name}
                </span>
                <span className="text-vscode-text-dim font-mono text-[11px]">
                  {f.symbol}
                </span>
              </div>
              <div className="flex">
                <input
                  type="number"
                  value={params[f.key]}
                  step="any"
                  onChange={(e) =>
                    onChange({
                      ...params,
                      [f.key]: parseFloat(e.target.value || '0'),
                    })
                  }
                  className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus min-w-0 flex-1 rounded-l-[2px] border px-2 py-1 text-[11px] focus:outline-none"
                />
                <span className="border-vscode-border text-vscode-text-dim inline-flex min-w-[40px] items-center justify-center rounded-r-[2px] border border-l-0 bg-[#1f1f1f] px-2 text-[11px]">
                  {f.unit}
                </span>
              </div>
              <div className="text-vscode-text-faint mt-0.5 text-[10px] leading-tight">
                {f.hint}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
