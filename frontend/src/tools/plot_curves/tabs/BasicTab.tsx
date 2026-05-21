/**
 * 基础 tab：图标题模板 + 标识列 + 网格 + 图例位置。
 * 不暴露 filename_template（一般跟 title_template 形态固定）。
 */
import { usePlotCurves } from "../controller";
import { Row, inputClass } from "./_shared";

export function BasicTab() {
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
