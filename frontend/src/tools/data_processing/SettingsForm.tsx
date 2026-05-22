/**
 * data_processing 右侧 RightPanel「调参」tab：按 calcType 切对应算法的参数面板。
 *   - leeb: 输出路径 + 默认测量角度
 *   - anchor: 规范下拉 + 生成模板按钮 + batch_id 列名 + 按批次参数卡片
 */
import { useCallback, useState } from "react";
import { save as saveDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { Field, Picker, ResetBtn } from "../_shared/forms";
import { useDataProcessing } from "./controller";
import {
  ANCHOR_STANDARDS,
  DEFAULT_ANCHOR_PARAMS,
  type AnchorParams,
  type AnchorStandard,
} from "./types";

export function DataProcessingSettingsForm() {
  const c = useDataProcessing();

  const pickOutput = useCallback(async () => {
    const sel = await saveDialog({
      title: "保存结果 Excel 为",
      defaultPath: c.defaultOutput || undefined,
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
    });
    if (typeof sel === "string") c.setOutputPath(sel);
  }, [c]);

  return (
    <div className="flex flex-col h-full text-xs overflow-auto p-4 space-y-4">
      <Field label="输出 Excel 路径" hint="留空 = 与输入同级 / 同名加后缀">
        <Picker
          value={c.outputPath || c.defaultOutput}
          onPick={pickOutput}
          placeholder="（选 Excel 后自动）"
          muted={!c.outputPath}
          extra={
            c.outputPath ? <ResetBtn onClick={() => c.setOutputPath("")} /> : undefined
          }
        />
      </Field>

      {c.calcType === "leeb" && (
        <Field label="默认测量角度（度）" hint="构件未指定角度时用此值；常用 0 / 90 / 180">
          <input
            type="number"
            value={c.angle}
            onChange={(e) => c.setAngle(parseFloat(e.target.value || "0"))}
            className="w-32 bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
          />
        </Field>
      )}

      {c.calcType === "anchor" && <AnchorSubForm />}

      <div className="pt-2 text-[11px] text-vscode-text-faint">
        选好 Excel 后点工具页顶部「开始计算」即可；结果会显示在工具页底部。
      </div>
    </div>
  );
}

// ── anchor 子 form ────────────────────────────────────────

function AnchorSubForm() {
  const c = useDataProcessing();

  const genTemplate = useCallback(async () => {
    const savePath = await saveDialog({
      title: "保存锚杆抗拔输入模板为",
      defaultPath: "锚杆抗拔输入模板.xlsx",
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
    });
    if (typeof savePath !== "string") return;
    const written = await c.generateAnchorTemplate(savePath);
    if (written) {
      try { await openPath(written); } catch { /* 没装关联程序就忽略 */ }
    }
  }, [c]);

  return (
    <>
      <Field label="规范" hint="未来可扩展其他规范；当前仅支持 GB 50086-2015">
        <select
          value={c.anchorStandard}
          onChange={(e) => c.setAnchorStandard(e.target.value as AnchorStandard)}
          className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
        >
          {ANCHOR_STANDARDS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </Field>

      <Field label="输入数据模板" hint="生成空白模板让用户照样例填写">
        <button
          type="button"
          onClick={genTemplate}
          disabled={c.anchorTemplateStatus.kind === "running"}
          className="w-full px-3 py-1.5 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center justify-center gap-2 disabled:opacity-60"
        >
          {c.anchorTemplateStatus.kind === "running" ? (
            <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
          ) : (
            <i className="codicon codicon-new-file !text-[12px]" />
          )}
          {c.anchorTemplateStatus.kind === "running" ? "生成中…" : "生成模板…"}
        </button>
        {c.anchorTemplateStatus.kind === "ok" && (
          <div className="mt-1 text-[11px] text-green-400 flex items-start gap-1">
            <i className="codicon codicon-pass !text-[12px] mt-0.5 shrink-0" />
            <span className="break-all">已生成：{c.anchorTemplateStatus.path}</span>
          </div>
        )}
        {c.anchorTemplateStatus.kind === "error" && (
          <div className="mt-1 text-[11px] text-red-400 whitespace-pre-wrap">
            <i className="codicon codicon-error !text-[12px] mr-1" />
            生成失败：{c.anchorTemplateStatus.message}
          </div>
        )}
      </Field>

      <Field label="批次列名" hint="输入 Excel 里用于区分批次的列名">
        <input
          type="text"
          value={c.anchorBatchIdColumn}
          onChange={(e) => c.setAnchorBatchIdColumn(e.target.value)}
          className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
        />
      </Field>

      <AnchorParamsSection />
    </>
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
    key: "P", symbol: "P", name: "轴向拉力设计值", unit: "N",
    hint: "锚杆设计承受的最大轴向拉力（即 Nt）；用于算各级荷载 0.1Nt/0.4Nt/.../1.2Nt",
  },
  {
    key: "Lf", symbol: "Lf", name: "自由段长度", unit: "mm",
    hint: "锚杆从锚头到锚固段起点的长度；与 La 共同决定位移上下限",
  },
  {
    key: "La", symbol: "La", name: "锚固段长度", unit: "mm",
    hint: "锚杆嵌入岩土的有效锚固长度（与水泥浆体接触段）",
  },
  {
    key: "A", symbol: "A", name: "钢筋截面面积", unit: "mm²",
    hint: "锚杆杆体钢筋截面积；E·A 决定弹性变形量",
  },
  {
    key: "E", symbol: "E", name: "弹性模量", unit: "N/mm²",
    hint: "锚杆杆体材料弹性模量（钢筋取 2.0×10⁵）",
  },
];

function AnchorParamsSection() {
  const c = useDataProcessing();

  if (!c.excelPath) {
    return (
      <div className="text-[11px] text-vscode-text-faint italic">
        先在主界面选输入 Excel，这里会按批次展开参数表
      </div>
    );
  }
  if (c.anchorBatchesLoading) {
    return (
      <div className="text-[11px] text-vscode-text-dim flex items-center gap-1">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
        加载批次清单…
      </div>
    );
  }
  if (c.anchorBatchesError) {
    return (
      <div className="text-[11px] text-red-400 whitespace-pre-wrap">
        读批次失败：{c.anchorBatchesError}
      </div>
    );
  }
  if (c.anchorBatchIds.length === 0) {
    return (
      <div className="text-[11px] text-vscode-text-faint italic">
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
            onClick={() => c.setAnchorParamsForAllBatches(DEFAULT_ANCHOR_PARAMS)}
            className="text-[11px] text-vscode-focus hover:underline"
            title={ANCHOR_PARAM_FIELDS
              .map((f) => `${f.symbol}=${DEFAULT_ANCHOR_PARAMS[f.key]}${f.unit}`)
              .join(" / ")}
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
    <div className="border border-vscode-border rounded-[3px] bg-[#252525]">
      <div
        className="flex items-center px-2 py-1.5 cursor-pointer hover:bg-vscode-hover select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <i
          className={`codicon codicon-chevron-${expanded ? "down" : "right"} !text-[12px] text-vscode-text-dim mr-1`}
        />
        <i className="codicon codicon-symbol-misc !text-[12px] text-vscode-text-dim mr-1.5" />
        <span className="text-[12px] text-vscode-text font-medium truncate" title={batchId}>
          {batchId}
        </span>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onFillDefault(); }}
          className="ml-auto text-[10px] text-vscode-focus hover:underline"
          title="给本批次填默认值"
        >
          填默认
        </button>
      </div>

      {expanded && (
        <div className="px-3 py-2 space-y-2.5 border-t border-vscode-border">
          {ANCHOR_PARAM_FIELDS.map((f) => (
            <div key={f.key}>
              <div className="flex items-baseline gap-1.5 mb-0.5">
                <span className="text-[11px] text-vscode-text font-medium">{f.name}</span>
                <span className="text-[11px] text-vscode-text-dim font-mono">{f.symbol}</span>
              </div>
              <div className="flex">
                <input
                  type="number"
                  value={params[f.key]}
                  step="any"
                  onChange={(e) =>
                    onChange({ ...params, [f.key]: parseFloat(e.target.value || "0") })
                  }
                  className="flex-1 min-w-0 bg-vscode-input border border-vscode-border px-2 py-1 text-[11px] text-vscode-text rounded-l-[2px] focus:outline-none focus:border-vscode-focus"
                />
                <span className="inline-flex items-center px-2 bg-[#1f1f1f] border border-l-0 border-vscode-border text-[11px] text-vscode-text-dim rounded-r-[2px] min-w-[40px] justify-center">
                  {f.unit}
                </span>
              </div>
              <div className="text-[10px] text-vscode-text-faint mt-0.5 leading-tight">
                {f.hint}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
