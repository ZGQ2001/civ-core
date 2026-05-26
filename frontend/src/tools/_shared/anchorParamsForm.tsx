/**
 * 锚杆按批次工程参数 UI ——「数据处理」「报告填充」两个工具页共用。
 *
 * 不依赖任何 controller，纯 props-based：
 *   - 上层负责提供 batchIds / paramsByBatch / loading / error / setter
 *   - 本组件负责渲染：批次清单、按批次折叠卡片、5 个参数 input、全部填默认按钮
 *
 * 公共 types（AnchorParams / DEFAULT_ANCHOR_PARAMS）依然放在 data_processing/types.ts，
 * 因为 data_processing 是产生这些 state 的真正主人；report_generator 仅消费。
 */
import { useState } from 'react';

import {
  DEFAULT_ANCHOR_PARAMS,
  type AnchorParams,
} from '../data_processing/types';
import { Field } from './forms';

interface ParamFieldDef {
  key: keyof AnchorParams;
  symbol: string;
  name: string;
  unit: string;
  hint: string;
}

/** 锚杆 5 个工程参数的字段定义 —— 中文名 + 变量符号 + 单位 + 解释。 */
const ANCHOR_PARAM_FIELDS: ParamFieldDef[] = [
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

export interface AnchorParamsSectionProps {
  /** 是否已经具备读批次的前置条件（一般 = 已选输入 Excel）。 */
  excelReady: boolean;
  /** 当前批次清单（来自 anchor.list_batches）。 */
  batchIds: string[];
  /** 各批次参数 map；缺失批次回退默认值。 */
  paramsByBatch: Record<string, AnchorParams>;
  loading: boolean;
  error: string | null;
  /** 单批次 set。 */
  onSetBatch: (batchId: string, params: AnchorParams) => void;
  /** 一键全部填默认。 */
  onSetAll: (params: AnchorParams) => void;
  /** 自定义文案：未选 Excel 时的提示。默认"先选输入 Excel"。 */
  emptyHint?: string;
}

/**
 * 锚杆按批次工程参数 UI —— 把 batch 清单展开成 N 张折叠卡片，每张卡 5 个参数 input。
 *
 * 状态机：
 *   未选 Excel → emptyHint
 *   loading → spinner
 *   error → 红字
 *   空批次 → "没读到批次"
 *   有批次 → 渲染卡片列表
 */
export function AnchorParamsSection({
  excelReady,
  batchIds,
  paramsByBatch,
  loading,
  error,
  onSetBatch,
  onSetAll,
  emptyHint,
}: AnchorParamsSectionProps) {
  if (!excelReady) {
    return (
      <div className="text-vscode-text-faint text-[11px] italic">
        {emptyHint ?? '先选输入 Excel，这里会按批次展开参数表'}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="text-vscode-text-dim flex items-center gap-1 text-[11px]">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
        加载批次清单…
      </div>
    );
  }
  if (error) {
    return (
      <div className="text-[11px] whitespace-pre-wrap text-red-400">
        读批次失败：{error}
      </div>
    );
  }
  if (batchIds.length === 0) {
    return (
      <div className="text-vscode-text-faint text-[11px] italic">
        Excel 里没读到任何批次（检查批次列名是否对得上）
      </div>
    );
  }

  return (
    <Field
      label={`锚杆工程参数（共 ${batchIds.length} 批）`}
      hint="同批次所有锚杆共用一组参数；点卡片标题展开/收起"
    >
      <div className="space-y-2">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => onSetAll(DEFAULT_ANCHOR_PARAMS)}
            className="text-vscode-focus text-[11px] hover:underline"
            title={ANCHOR_PARAM_FIELDS.map(
              (f) => `${f.symbol}=${DEFAULT_ANCHOR_PARAMS[f.key]}${f.unit}`,
            ).join(' / ')}
          >
            全部批次填默认值
          </button>
        </div>

        <div className="space-y-2">
          {batchIds.map((batchId, idx) => (
            <BatchParamsCard
              key={batchId}
              batchId={batchId}
              params={paramsByBatch[batchId] ?? DEFAULT_ANCHOR_PARAMS}
              defaultExpanded={batchIds.length <= 3 || idx === 0}
              onChange={(p) => onSetBatch(batchId, p)}
              onFillDefault={() =>
                onSetBatch(batchId, { ...DEFAULT_ANCHOR_PARAMS })
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
