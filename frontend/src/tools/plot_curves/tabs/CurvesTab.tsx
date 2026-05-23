/**
 * 曲线 tab：当前预设（一个预设 = 一条曲线）的样式 + 数据点编辑。
 *
 * 产品语义：「一预设一曲线」。想换曲线 → 新建预设，不在这里增删曲线。
 * 后端 schema curves 是数组（兼容性），UI 上只暴露 curves[0]；
 * 旧预设 curves 为空时自动初始化一条默认曲线（兜底，正常路径下不会触发）。
 */
import { useEffect } from 'react';

import { cn } from '../../../lib/cn';
import { usePlotCurves } from '../controller';
import type { CurveDef, PointDef } from '../types';
import { Row, SliderInput, inputClass, normalizeColor } from './_shared';

const MARKERS = [
  { v: 'o', label: '圆形' },
  { v: 's', label: '方形' },
  { v: '^', label: '三角形' },
  { v: 'v', label: '倒三角' },
  { v: 'D', label: '菱形' },
  { v: 'x', label: '叉' },
  { v: '+', label: '加号' },
  { v: '.', label: '小点' },
  { v: 'None', label: '无（仅线）' },
];

const DEFAULT_CURVE: CurveDef = {
  name: '曲线',
  color: '#1F4FE0',
  marker: 'o',
  linewidth: 2,
  markersize: 6,
  points: [],
};

const DEFAULT_POINT: PointDef = {
  fixed_axis: 'x',
  fixed_value: 0,
  var_column: '',
};

export function CurvesTab() {
  const c = usePlotCurves();
  const preset = c.effectivePreset!;
  const curve = preset.curves[0];

  // 兜底：空 curves 自动初始化一条默认（避免 UI 崩；正常新建流程已经带 curves[0]）
  useEffect(() => {
    if (preset.curves.length === 0) {
      c.patchPreset((p) => {
        p.curves = [{ ...DEFAULT_CURVE }];
        return p;
      });
    }
  }, [preset.curves.length, c]);

  if (!curve) return null; // useEffect 下一帧会补上

  const patchCurve = (updater: (cv: CurveDef) => CurveDef) => {
    c.patchPreset((p) => {
      p.curves[0] = updater({ ...p.curves[0] });
      return p;
    });
  };

  return (
    <div className="space-y-3">
      <Row label="颜色">
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={normalizeColor(curve.color)}
            onChange={(e) =>
              patchCurve((cv) => ({ ...cv, color: e.target.value }))
            }
            className="bg-vscode-input border-vscode-border h-7 w-12 cursor-pointer rounded-[2px] border"
          />
          <input
            type="text"
            value={curve.color}
            onChange={(e) =>
              patchCurve((cv) => ({ ...cv, color: e.target.value }))
            }
            className={cn(inputClass, 'w-28 font-mono')}
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
          value={curve.marker ?? 'o'}
          onChange={(e) =>
            patchCurve((cv) => ({ ...cv, marker: e.target.value }))
          }
          className={inputClass}
        >
          {MARKERS.map((m) => (
            <option key={m.v} value={m.v}>
              {m.label}（{m.v}）
            </option>
          ))}
        </select>
      </Row>

      <PointsEditor
        points={curve.points}
        onChange={(pts) => patchCurve((cv) => ({ ...cv, points: pts }))}
      />
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
  const columnSuggestions = Object.keys(c.previewRowData);

  const updatePoint = (i: number, patch: Partial<PointDef>) => {
    onChange(points.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  };
  const addPoint = () => onChange([...points, { ...DEFAULT_POINT }]);
  const removePoint = (i: number) => onChange(points.filter((_, j) => j !== i));

  return (
    <div className="border-vscode-border rounded-[2px] border">
      <div className="border-vscode-border text-vscode-text-dim border-b bg-[#252525] px-2 py-1.5 text-[11px] tracking-wider uppercase">
        数据点（{points.length}）
        <span className="text-vscode-text-faint ml-2 text-[10px] tracking-normal normal-case">
          固定一个轴的值，另一个轴的值从 Excel 某列读
        </span>
      </div>

      {points.length === 0 ? (
        <div className="text-vscode-text-faint p-2 text-[11px] italic">
          （还没有数据点。点下方按钮添加。）
        </div>
      ) : (
        <table className="w-full text-[11px]">
          <thead className="text-vscode-text-faint bg-[#1d1d1d]">
            <tr>
              <th className="w-12 px-2 py-1 text-left font-normal">#</th>
              <th className="w-24 px-2 py-1 text-left font-normal">固定轴</th>
              <th className="w-24 px-2 py-1 text-left font-normal">固定值</th>
              <th className="px-2 py-1 text-left font-normal">
                变化列（Excel 表头）
              </th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {points.map((pt, i) => (
              <tr key={i} className="border-vscode-border border-t">
                <td className="text-vscode-text-dim px-2 py-1">{i + 1}</td>
                <td className="px-2 py-1">
                  <select
                    value={pt.fixed_axis}
                    onChange={(e) =>
                      updatePoint(i, {
                        fixed_axis: e.target.value as 'x' | 'y',
                      })
                    }
                    className={cn(inputClass, 'py-0.5')}
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
                      updatePoint(i, {
                        fixed_value: parseFloat(e.target.value || '0'),
                      })
                    }
                    className={cn(inputClass, 'py-0.5')}
                  />
                </td>
                <td className="px-2 py-1">
                  <select
                    value={pt.var_column}
                    onChange={(e) =>
                      updatePoint(i, { var_column: e.target.value })
                    }
                    className={cn(inputClass, 'py-0.5')}
                  >
                    <option value="">（选择 Excel 表头）</option>
                    {columnSuggestions.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                    {pt.var_column &&
                      !columnSuggestions.includes(pt.var_column) && (
                        <option value={pt.var_column}>{pt.var_column}</option>
                      )}
                  </select>
                </td>
                <td className="px-1 py-1">
                  <button
                    type="button"
                    onClick={() => removePoint(i)}
                    title="删除该点"
                    className="text-vscode-text-dim hover:bg-vscode-hover flex h-5 w-5 items-center justify-center rounded hover:text-red-400"
                  >
                    <i className="codicon codicon-close !text-[12px]" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <button
        type="button"
        onClick={addPoint}
        className="border-vscode-border text-vscode-text-dim hover:bg-vscode-hover flex w-full items-center justify-center gap-1 border-t px-2 py-1.5 text-[11px] hover:text-white"
      >
        <i className="codicon codicon-add !text-[12px]" />
        新增数据点
      </button>
    </div>
  );
}
