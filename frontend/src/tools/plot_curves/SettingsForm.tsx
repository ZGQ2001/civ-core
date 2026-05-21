/**
 * plot_curves 调参表单（在底部 Panel 显示）。
 *
 * 4 个 tab：
 *   基础      —— 标题模板 / 标识列 / 网格 / 图例
 *   X 轴      —— 标签 / 范围 / 对数刻度
 *   Y 轴      —— 标签 / 范围 / 对数刻度
 *   曲线样式  —— 第 1 条曲线的名称 / 颜色 / 线宽 / 点大小 / 点样式
 *
 * 所有控件都是给非程序员用的 input / select / slider / color picker，
 * 没有 JSON 编辑。改动即时回写 Context，预览 300ms debounce 重渲染。
 *
 * 未暴露字段：filename_template / points / curves[1..]（多曲线只能继承）
 */
import { useState } from "react";

import { cn } from "../../lib/cn";
import { usePlotCurves } from "./controller";
import type { AxisSpec } from "./types";

type TabId = "basic" | "xaxis" | "yaxis" | "curve";

const MARKERS = [
  { v: "o", label: "圆形 ●" },
  { v: "s", label: "方形 ■" },
  { v: "^", label: "三角形 ▲" },
  { v: "v", label: "倒三角 ▼" },
  { v: "D", label: "菱形 ◆" },
  { v: "x", label: "叉 ✕" },
  { v: "+", label: "加号 +" },
  { v: ".", label: "小点 ·" },
  { v: "None", label: "无（仅线）" },
];

export function PlotCurvesSettingsForm() {
  const c = usePlotCurves();
  const [tab, setTab] = useState<TabId>("basic");
  const preset = c.effectivePreset;

  if (!preset) {
    return (
      <div className="p-6 text-xs text-vscode-text-faint italic">
        （未加载预设；请确认后端预设库可用。）
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full text-xs">
      {/* tab 切换条 */}
      <div className="flex items-center border-b border-vscode-border px-2 shrink-0 gap-1">
        <TabBtn label="基础" icon="symbol-misc" active={tab === "basic"} onClick={() => setTab("basic")} />
        <TabBtn label="X 轴" icon="arrow-right" active={tab === "xaxis"} onClick={() => setTab("xaxis")} />
        <TabBtn label="Y 轴" icon="arrow-up" active={tab === "yaxis"} onClick={() => setTab("yaxis")} />
        <TabBtn label="曲线样式" icon="symbol-color" active={tab === "curve"} onClick={() => setTab("curve")} />
        {c.edited && (
          <button
            type="button"
            onClick={c.resetPreset}
            title="撤销所有改动，回到预设原版"
            className="ml-auto px-2 h-7 text-xs text-vscode-focus hover:underline flex items-center gap-1"
          >
            <i className="codicon codicon-discard !text-[12px]" />
            还原
          </button>
        )}
      </div>

      {/* 单 tab 内容 */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {tab === "basic" && <BasicTab />}
        {tab === "xaxis" && (
          <AxisTab
            axisName="X 轴"
            spec={preset.x_axis}
            onChange={(spec) => c.patchPreset((p) => ({ ...p, x_axis: spec }))}
          />
        )}
        {tab === "yaxis" && (
          <AxisTab
            axisName="Y 轴"
            spec={preset.y_axis}
            onChange={(spec) => c.patchPreset((p) => ({ ...p, y_axis: spec }))}
          />
        )}
        {tab === "curve" && <CurveTab />}
      </div>
    </div>
  );
}

// ── tab 1：基础 ──────────────────────────────────────
function BasicTab() {
  const c = usePlotCurves();
  const preset = c.effectivePreset!;
  return (
    <>
      <Row label="图标题模板" hint="{id} 会被替换为标识列的值">
        <input
          type="text"
          value={preset.title_template}
          onChange={(e) => c.patchPreset((p) => ({ ...p, title_template: e.target.value }))}
          className={inputClass}
        />
      </Row>
      <Row label="标识列名" hint="决定一张图对应哪一行 + 用什么名">
        <input
          type="text"
          value={preset.id_column}
          onChange={(e) => c.patchPreset((p) => ({ ...p, id_column: e.target.value }))}
          className={inputClass}
        />
      </Row>
      <Row label="网格线">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={preset.style?.grid ?? true}
            onChange={(e) =>
              c.patchPreset((p) => ({
                ...p,
                style: { ...(p.style ?? {}), grid: e.target.checked },
              }))
            }
          />
          <span>显示网格线</span>
        </label>
      </Row>
      <Row label="图例位置" hint="留空 = 不显示图例">
        <select
          value={preset.style?.legend ?? ""}
          onChange={(e) =>
            c.patchPreset((p) => ({
              ...p,
              style: {
                ...(p.style ?? {}),
                legend: e.target.value === "" ? null : e.target.value,
              },
            }))
          }
          className={inputClass}
        >
          <option value="">（不显示）</option>
          <option value="best">自动</option>
          <option value="upper left">左上</option>
          <option value="upper right">右上</option>
          <option value="lower left">左下</option>
          <option value="lower right">右下</option>
        </select>
      </Row>
    </>
  );
}

// ── tab 2/3：X 轴 / Y 轴 ─────────────────────────────
function AxisTab({
  axisName,
  spec,
  onChange,
}: {
  axisName: string;
  spec: AxisSpec;
  onChange: (spec: AxisSpec) => void;
}) {
  const range = spec.range;
  const autoRange = range === null;

  return (
    <>
      <Row label={`${axisName}标签`} hint="坐标轴下方/旁边的文字">
        <input
          type="text"
          value={spec.label}
          onChange={(e) => onChange({ ...spec, label: e.target.value })}
          className={inputClass}
        />
      </Row>
      <Row label="范围">
        <div className="space-y-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRange}
              onChange={(e) =>
                onChange({
                  ...spec,
                  range: e.target.checked ? null : [0, 100, 10],
                })
              }
            />
            <span>自动（让 matplotlib 根据数据决定）</span>
          </label>
          {!autoRange && range && (
            <div className="grid grid-cols-3 gap-2">
              <NumberCell label="最小" value={range[0]} onChange={(v) => onChange({ ...spec, range: [v, range[1], range[2]] })} />
              <NumberCell label="最大" value={range[1]} onChange={(v) => onChange({ ...spec, range: [range[0], v, range[2]] })} />
              <NumberCell label="刻度间隔" value={range[2]} onChange={(v) => onChange({ ...spec, range: [range[0], range[1], v] })} />
            </div>
          )}
        </div>
      </Row>
      <Row label="对数刻度" hint="数据跨度大时勾选；适合幂律 / 振幅类">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={spec.log ?? false}
            onChange={(e) => onChange({ ...spec, log: e.target.checked })}
          />
          <span>使用对数轴</span>
        </label>
      </Row>
    </>
  );
}

// ── tab 4：曲线样式 ──────────────────────────────────
function CurveTab() {
  const c = usePlotCurves();
  const preset = c.effectivePreset!;
  const curve = preset.curves[0];
  const hasMoreCurves = preset.curves.length > 1;

  if (!curve) {
    return <div className="text-vscode-text-faint italic">（该预设没有定义曲线）</div>;
  }

  return (
    <>
      {hasMoreCurves && (
        <div className="mb-2 p-2 bg-[#252525] border border-vscode-border rounded-[2px] text-vscode-text-dim text-[11px]">
          <i className="codicon codicon-info !text-[12px] mr-1" />
          该预设有 {preset.curves.length} 条曲线，此处只调整第 1 条样式。其他曲线沿用预设原版。
        </div>
      )}
      <Row label="颜色">
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={normalizeColor(curve.color)}
            onChange={(e) =>
              c.patchPreset((p) => {
                p.curves[0] = { ...p.curves[0], color: e.target.value };
                return p;
              })
            }
            className="h-7 w-12 bg-vscode-input border border-vscode-border rounded-[2px] cursor-pointer"
          />
          <input
            type="text"
            value={curve.color}
            onChange={(e) =>
              c.patchPreset((p) => {
                p.curves[0] = { ...p.curves[0], color: e.target.value };
                return p;
              })
            }
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
          onChange={(v) =>
            c.patchPreset((p) => {
              p.curves[0] = { ...p.curves[0], linewidth: v };
              return p;
            })
          }
        />
      </Row>
      <Row label="点大小">
        <SliderInput
          min={0}
          max={20}
          step={1}
          value={curve.markersize ?? 6}
          onChange={(v) =>
            c.patchPreset((p) => {
              p.curves[0] = { ...p.curves[0], markersize: v };
              return p;
            })
          }
        />
      </Row>
      <Row label="点样式">
        <select
          value={curve.marker ?? "o"}
          onChange={(e) =>
            c.patchPreset((p) => {
              p.curves[0] = { ...p.curves[0], marker: e.target.value };
              return p;
            })
          }
          className={inputClass}
        >
          {MARKERS.map((m) => (
            <option key={m.v} value={m.v}>{m.label}</option>
          ))}
        </select>
      </Row>
    </>
  );
}

// ── 内部小组件 ────────────────────────────────────────
function TabBtn({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-7 px-3 text-xs flex items-center gap-1.5 border-b-2 transition-colors -mb-px",
        active
          ? "text-white border-vscode-focus"
          : "text-vscode-text-dim border-transparent hover:text-white",
      )}
    >
      <i className={cn("codicon", `codicon-${icon}`, "!text-[12px]")} />
      {label}
    </button>
  );
}

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 items-start">
      <div className="text-vscode-text-dim pt-1">
        {label}
        {hint && <div className="text-[10px] text-vscode-text-faint mt-0.5">{hint}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function SliderInput({
  min,
  max,
  step,
  value,
  onChange,
}: {
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="flex-1 accent-vscode-focus"
      />
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value || "0"))}
        className={cn(inputClass, "w-20")}
      />
    </div>
  );
}

function NumberCell({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] text-vscode-text-faint">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value || "0"))}
        className={inputClass}
      />
    </label>
  );
}

const inputClass =
  "bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px] w-full";

function normalizeColor(c: string): string {
  if (c.startsWith("#") && (c.length === 7 || c.length === 9)) return c.slice(0, 7);
  return "#888888";
}
