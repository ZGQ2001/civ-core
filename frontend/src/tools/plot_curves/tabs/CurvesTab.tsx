/**
 * 曲线样式 tab：accordion 式管理多条曲线 + 每条曲线的数据点。
 *
 * 操作：
 *  - 顶部「新增曲线」按钮：追加一条默认曲线
 *  - 每条曲线卡可展开 / 折叠；卡头部带删除按钮
 *  - 卡内：color / linewidth / markersize / marker + 数据点子表
 *  - 数据点子表：每行 fixed_axis(x/y) + fixed_value + var_column；
 *    var_column 用 datalist 从 Excel 当前行 keys 给建议（既能选也能输）
 */
import { useState } from "react";

import { cn } from "../../../lib/cn";
import { usePlotCurves } from "../controller";
import type { CurveDef, PointDef } from "../types";
import { Row, SliderInput, inputClass, normalizeColor } from "./_shared";

const MARKERS = [
  { v: "o", label: "圆形" },
  { v: "s", label: "方形" },
  { v: "^", label: "三角形" },
  { v: "v", label: "倒三角" },
  { v: "D", label: "菱形" },
  { v: "x", label: "叉" },
  { v: "+", label: "加号" },
  { v: ".", label: "小点" },
  { v: "None", label: "无（仅线）" },
];

const DEFAULT_CURVE = (idx: number): CurveDef => ({
  name: `曲线 ${idx + 1}`,
  color: "#1F4FE0",
  marker: "o",
  linewidth: 2,
  markersize: 6,
  points: [],
});

const DEFAULT_POINT: PointDef = {
  fixed_axis: "x",
  fixed_value: 0,
  var_column: "",
};

export function CurvesTab() {
  const c = usePlotCurves();
  const preset = c.effectivePreset!;
  const curves = preset.curves;

  const addCurve = () => {
    c.patchPreset((p) => {
      p.curves = [...p.curves, DEFAULT_CURVE(p.curves.length)];
      return p;
    });
  };

  return (
    <div className="space-y-2">
      {curves.length === 0 && (
        <div className="p-3 bg-[#252525] border border-vscode-border rounded-[2px] text-vscode-text-dim text-[11px]">
          <i className="codicon codicon-info !text-[12px] mr-1" />
          该预设还没定义曲线。点下方按钮添加第一条曲线。
        </div>
      )}

      {curves.map((curve, i) => (
        <CurveCard key={i} index={i} curve={curve} />
      ))}

      <button
        type="button"
        onClick={addCurve}
        className="w-full px-3 py-2 text-xs border border-dashed border-vscode-border rounded-[2px] text-vscode-text-dim hover:text-white hover:bg-vscode-hover flex items-center justify-center gap-1"
      >
        <i className="codicon codicon-add !text-[12px]" />
        新增曲线
      </button>
    </div>
  );
}

function CurveCard({ index, curve }: { index: number; curve: CurveDef }) {
  const c = usePlotCurves();
  const [expanded, setExpanded] = useState(index === 0);

  const patchCurve = (updater: (cv: CurveDef) => CurveDef) => {
    c.patchPreset((p) => {
      p.curves[index] = updater({ ...p.curves[index] });
      return p;
    });
  };

  const removeCurve = () => {
    if (!window.confirm(`删除曲线「${curve.name || `曲线 ${index + 1}`}」？`)) return;
    c.patchPreset((p) => {
      p.curves = p.curves.filter((_, i) => i !== index);
      return p;
    });
  };

  return (
    <div className="border border-vscode-border rounded-[2px] bg-[#1d1d1d]">
      {/* 卡头：序号 + 名称 + 展开/收起 + 删除 */}
      <div className="flex items-center px-2 py-1.5 bg-[#252525] border-b border-vscode-border">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1.5 flex-1 text-left text-xs text-vscode-text hover:text-white"
        >
          <i
            className={`codicon !text-[12px] ${
              expanded ? "codicon-chevron-down" : "codicon-chevron-right"
            }`}
          />
          <span
            className="inline-block w-3 h-3 rounded-sm border border-vscode-border shrink-0"
            style={{ backgroundColor: curve.color }}
          />
          <span className="font-medium">曲线 {index + 1}</span>
          <span className="text-vscode-text-dim">
            ・{curve.points.length} 个数据点
          </span>
        </button>
        <button
          type="button"
          onClick={removeCurve}
          title="删除该曲线"
          className="h-6 w-6 flex items-center justify-center rounded text-vscode-text-dim hover:text-red-400 hover:bg-vscode-hover"
        >
          <i className="codicon codicon-trash !text-[12px]" />
        </button>
      </div>

      {/* 卡内：样式 + 数据点 */}
      {expanded && (
        <div className="p-3 space-y-3">
          <Row label="颜色">
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={normalizeColor(curve.color)}
                onChange={(e) => patchCurve((cv) => ({ ...cv, color: e.target.value }))}
                className="h-7 w-12 bg-vscode-input border border-vscode-border rounded-[2px] cursor-pointer"
              />
              <input
                type="text"
                value={curve.color}
                onChange={(e) => patchCurve((cv) => ({ ...cv, color: e.target.value }))}
                className={cn(inputClass, "w-28 font-mono")}
              />
            </div>
          </Row>
          <Row label="线宽">
            <SliderInput
              min={0}
              max={6}
              step={0.5}
              value={curve.linewidth ?? 2}
              onChange={(v) => patchCurve((cv) => ({ ...cv, linewidth: v }))}
            />
          </Row>
          <Row label="点大小">
            <SliderInput
              min={0}
              max={20}
              step={1}
              value={curve.markersize ?? 6}
              onChange={(v) => patchCurve((cv) => ({ ...cv, markersize: v }))}
            />
          </Row>
          <Row label="点样式">
            <select
              value={curve.marker ?? "o"}
              onChange={(e) => patchCurve((cv) => ({ ...cv, marker: e.target.value }))}
              className={inputClass}
            >
              {MARKERS.map((m) => (
                <option key={m.v} value={m.v}>
                  {m.label}（{m.v}）
                </option>
              ))}
            </select>
          </Row>

          {/* 数据点子表 */}
          <PointsEditor
            points={curve.points}
            onChange={(pts) => patchCurve((cv) => ({ ...cv, points: pts }))}
          />
        </div>
      )}
    </div>
  );
}

function PointsEditor({
  points,
  onChange,
}: {
  points: PointDef[];
  onChange: (pts: PointDef[]) => void;
}) {
  const c = usePlotCurves();
  // 当前行所有列名 — 给 var_column 做 datalist 建议
  const columnSuggestions = Object.keys(c.previewRowData);
  const datalistId = `pcol-${Math.random().toString(36).slice(2, 8)}`;

  const updatePoint = (i: number, patch: Partial<PointDef>) => {
    const next = points.map((p, j) => (j === i ? { ...p, ...patch } : p));
    onChange(next);
  };

  const addPoint = () => onChange([...points, { ...DEFAULT_POINT }]);

  const removePoint = (i: number) => onChange(points.filter((_, j) => j !== i));

  return (
    <div className="border border-vscode-border rounded-[2px]">
      <div className="px-2 py-1.5 bg-[#252525] border-b border-vscode-border text-[11px] uppercase tracking-wider text-vscode-text-dim flex items-center justify-between">
        <span>
          数据点（{points.length}）
          <span className="ml-2 normal-case text-[10px] text-vscode-text-faint tracking-normal">
            固定一个轴的值，另一个轴的值从 Excel 某列读
          </span>
        </span>
      </div>

      {points.length === 0 ? (
        <div className="p-2 text-[11px] text-vscode-text-faint italic">
          （还没有数据点。点下方按钮添加。）
        </div>
      ) : (
        <table className="w-full text-[11px]">
          <thead className="bg-[#1d1d1d] text-vscode-text-faint">
            <tr>
              <th className="text-left px-2 py-1 font-normal w-12">#</th>
              <th className="text-left px-2 py-1 font-normal w-20">固定轴</th>
              <th className="text-left px-2 py-1 font-normal w-24">固定值</th>
              <th className="text-left px-2 py-1 font-normal">变化列（Excel 表头）</th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {points.map((pt, i) => (
              <tr key={i} className="border-t border-vscode-border">
                <td className="px-2 py-1 text-vscode-text-dim">{i + 1}</td>
                <td className="px-2 py-1">
                  <select
                    value={pt.fixed_axis}
                    onChange={(e) =>
                      updatePoint(i, { fixed_axis: e.target.value as "x" | "y" })
                    }
                    className={cn(inputClass, "py-0.5")}
                  >
                    <option value="x">X 固定</option>
                    <option value="y">Y 固定</option>
                  </select>
                </td>
                <td className="px-2 py-1">
                  <input
                    type="number"
                    value={pt.fixed_value}
                    onChange={(e) =>
                      updatePoint(i, { fixed_value: parseFloat(e.target.value || "0") })
                    }
                    className={cn(inputClass, "py-0.5")}
                  />
                </td>
                <td className="px-2 py-1">
                  <input
                    type="text"
                    value={pt.var_column}
                    onChange={(e) => updatePoint(i, { var_column: e.target.value })}
                    placeholder="例：60kN 位移读数"
                    list={columnSuggestions.length > 0 ? datalistId : undefined}
                    className={cn(inputClass, "py-0.5")}
                  />
                </td>
                <td className="px-1 py-1">
                  <button
                    type="button"
                    onClick={() => removePoint(i)}
                    title="删除该点"
                    className="h-5 w-5 flex items-center justify-center rounded text-vscode-text-dim hover:text-red-400 hover:bg-vscode-hover"
                  >
                    <i className="codicon codicon-close !text-[12px]" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Excel 表头建议（来自当前预览行） */}
      {columnSuggestions.length > 0 && (
        <datalist id={datalistId}>
          {columnSuggestions.map((k) => (
            <option key={k} value={k} />
          ))}
        </datalist>
      )}

      <button
        type="button"
        onClick={addPoint}
        className="w-full px-2 py-1.5 text-[11px] border-t border-vscode-border text-vscode-text-dim hover:text-white hover:bg-vscode-hover flex items-center justify-center gap-1"
      >
        <i className="codicon codicon-add !text-[12px]" />
        新增数据点
      </button>
    </div>
  );
}
