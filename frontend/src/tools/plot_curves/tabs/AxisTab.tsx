/**
 * X 轴 / Y 轴 tab：标签 + 范围 + 对数刻度。
 * 通用组件，X 和 Y tab 都用它，只是传入不同的 spec/onChange。
 */
import type { AxisSpec } from "../types";
import { NumberCell, Row, inputClass } from "./_shared";

export function AxisTab({
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
                label="刻度间隔"
                value={range[2]}
                onChange={(v) => onChange({ ...spec, range: [range[0], range[1], v] })}
              />
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
