/**
 * data_processing 右侧 RightPanel「调参」tab：按 calcType 切对应算法的参数面板。
 *   - leeb: 输出路径 + 默认测量角度
 *   - anchor: 规范下拉 + 生成模板按钮 + batch_id 列名 + 按批次参数表
 */
import { useCallback } from "react";
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
      <Field label="输出 Excel 路径" hint="留空 = <输入同级>/<stem>_<类型>_结果.xlsx">
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
      try { await openPath(written); } catch { /* 忽略：用户可能没装关联 */ }
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
          <div className="mt-1 text-[11px] text-green-400 flex items-center gap-1">
            <i className="codicon codicon-pass !text-[12px]" />
            已生成：{c.anchorTemplateStatus.path}
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

      <AnchorParamsTable />
    </>
  );
}

function AnchorParamsTable() {
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

  const cols: Array<{ key: keyof AnchorParams; label: string; hint: string }> = [
    { key: "P", label: "P", hint: "轴向拉力设计值（N）" },
    { key: "Lf", label: "Lf", hint: "自由段长度（mm）" },
    { key: "La", label: "La", hint: "锚固段长度（mm）" },
    { key: "A", label: "A", hint: "钢筋面积（mm²）" },
    { key: "E", label: "E", hint: "弹性模量（N/mm²）" },
  ];

  return (
    <Field
      label={`锚杆参数（按批次，共 ${c.anchorBatchIds.length} 批）`}
      hint="单位：P=N, Lf/La=mm, A=mm², E=N/mm²"
    >
      <div className="space-y-2">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => c.setAnchorParamsForAllBatches(DEFAULT_ANCHOR_PARAMS)}
            className="text-[11px] text-vscode-focus hover:underline"
            title={`P=${DEFAULT_ANCHOR_PARAMS.P}, Lf=${DEFAULT_ANCHOR_PARAMS.Lf}, La=${DEFAULT_ANCHOR_PARAMS.La}, A=${DEFAULT_ANCHOR_PARAMS.A}, E=${DEFAULT_ANCHOR_PARAMS.E}`}
          >
            全部填默认值
          </button>
        </div>

        <div className="overflow-x-auto border border-vscode-border rounded-[2px]">
          <table className="w-full text-[11px]">
            <thead className="bg-[#1f1f1f]">
              <tr>
                <th className="text-left px-2 py-1 text-vscode-text-dim font-medium border-b border-vscode-border">
                  批次
                </th>
                {cols.map((col) => (
                  <th
                    key={col.key}
                    title={col.hint}
                    className="text-left px-2 py-1 text-vscode-text-dim font-medium border-b border-vscode-border"
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {c.anchorBatchIds.map((batchId, i) => {
                const params = c.anchorParamsByBatch[batchId] ?? DEFAULT_ANCHOR_PARAMS;
                return (
                  <tr key={batchId} className={i % 2 === 0 ? "bg-[#252525]" : "bg-[#2a2a2a]"}>
                    <td
                      className="px-2 py-1 text-vscode-text border-b border-[#333] truncate max-w-[80px]"
                      title={batchId}
                    >
                      {batchId}
                    </td>
                    {cols.map((col) => (
                      <td key={col.key} className="px-1 py-0.5 border-b border-[#333]">
                        <input
                          type="number"
                          value={params[col.key]}
                          onChange={(e) =>
                            c.setAnchorParamsForBatch(batchId, {
                              ...params,
                              [col.key]: parseFloat(e.target.value || "0"),
                            })
                          }
                          className="w-full bg-vscode-input border border-vscode-border px-1 py-0.5 text-[11px] text-vscode-text rounded-[2px]"
                        />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </Field>
  );
}
