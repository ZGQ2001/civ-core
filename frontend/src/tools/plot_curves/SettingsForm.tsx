/**
 * plot_curves 调参表单（在底部 Panel 显示）。
 *
 * 表单字段（给不懂编程的人用，不暴露 JSON）：
 *  - 图标题：title_template
 *  - X / Y 轴：label + 范围（min/max/step）+ 对数刻度勾选
 *  - 第 1 条曲线：名称 / 颜色 / 线宽 / 点大小 / 点样式
 *  - 网格线开关 / 图例显示
 *
 * 没暴露的字段（points / filename_template / id_column）保留原值；
 * 多条曲线只支持改第 1 条样式（更多曲线属于"高级"，留后续做）。
 *
 * 改动即时回写 Context，Page 组件的预览图 300ms debounce 重新渲染。
 */
import { cn } from "../../lib/cn";
import { usePlotCurves } from "./controller";
import type { AxisSpec } from "./types";

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
  const preset = c.effectivePreset;

  if (!preset) {
    return (
      <div className="p-6 text-xs text-vscode-text-faint italic">
        （未加载预设；请确认后端预设库可用。）
      </div>
    );
  }

  // 第 1 条曲线（form 只暴露这一条）
  const curve = preset.curves[0];
  const hasMoreCurves = preset.curves.length > 1;

  return (
    <div className="p-4 space-y-5 text-xs">
      <Section title="标题与标识">
        <Row label="图标题模板" hint="{id} 会被替换为标识列的值">
          <input
            type="text"
            value={preset.title_template}
            onChange={(e) =>
              c.patchPreset((p) => ({ ...p, title_template: e.target.value }))
            }
            className={inputClass}
          />
        </Row>
        <Row label="标识列名" hint="决定一张图对应哪一行 + 用什么名">
          <input
            type="text"
            value={preset.id_column}
            onChange={(e) =>
              c.patchPreset((p) => ({ ...p, id_column: e.target.value }))
            }
            className={inputClass}
          />
        </Row>
      </Section>

      <Section title="X 轴">
        <AxisFields
          spec={preset.x_axis}
          onChange={(spec) => c.patchPreset((p) => ({ ...p, x_axis: spec }))}
        />
      </Section>

      <Section title="Y 轴">
        <AxisFields
          spec={preset.y_axis}
          onChange={(spec) => c.patchPreset((p) => ({ ...p, y_axis: spec }))}
        />
      </Section>

      {curve && (
        <Section
          title={hasMoreCurves ? `曲线（共 ${preset.curves.length} 条，只显示第 1 条样式）` : "曲线"}
        >
          <Row label="曲线名称">
            <input
              type="text"
              value={curve.name}
              onChange={(e) =>
                c.patchPreset((p) => {
                  p.curves[0] = { ...p.curves[0], name: e.target.value };
                  return p;
                })
              }
              className={inputClass}
            />
          </Row>
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
          <Row label="线宽" hint="毫米单位的视觉粗细">
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
        </Section>
      )}

      <Section title="其他">
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
      </Section>
    </div>
  );
}

// ── 内部小组件 ────────────────────────────────────────
function AxisFields({
  spec,
  onChange,
}: {
  spec: AxisSpec;
  onChange: (spec: AxisSpec) => void;
}) {
  const range = spec.range;
  const autoRange = range === null;

  return (
    <>
      <Row label="标签">
        <input
          type="text"
          value={spec.label}
          onChange={(e) => onChange({ ...spec, label: e.target.value })}
          className={inputClass}
        />
      </Row>
      <Row label="范围">
        <div className="space-y-1">
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
            <span>自动（由数据范围决定）</span>
          </label>
          {!autoRange && range && (
            <div className="grid grid-cols-3 gap-2">
              <NumberCell
                label="最小"
                value={range[0]}
                onChange={(v) => onChange({ ...spec, range: [v, range[1], range[2]] })}
              />
              <NumberCell
                label="最大"
                value={range[1]}
                onChange={(v) => onChange({ ...spec, range: [range[0], v, range[2]] })}
              />
              <NumberCell
                label="步长"
                value={range[2]}
                onChange={(v) => onChange({ ...spec, range: [range[0], range[1], v] })}
              />
            </div>
          )}
        </div>
      </Row>
      <Row label="对数刻度">
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-vscode-border rounded-[2px]">
      <div className="px-3 py-1.5 bg-[#252525] border-b border-vscode-border text-[11px] uppercase tracking-wider text-vscode-text">
        {title}
      </div>
      <div className="p-3 space-y-2">{children}</div>
    </div>
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
        {hint && (
          <div className="text-[10px] text-vscode-text-faint mt-0.5">{hint}</div>
        )}
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

// matplotlib 接受 "#RRGGBB" / "rgb()" / 命名颜色；HTML color picker 只认 "#RRGGBB"
// 已经是 # 开头取前 7 位（防 "#RRGGBBAA"），否则返灰色兜底
function normalizeColor(c: string): string {
  if (c.startsWith("#") && (c.length === 7 || c.length === 9)) return c.slice(0, 7);
  return "#888888";
}
