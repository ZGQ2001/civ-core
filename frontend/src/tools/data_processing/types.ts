/**
 * data_processing 工具的前端类型契约。
 *
 * 当前只接「里氏硬度」一种计算，未来用 calcType 下拉切换：
 *   - leeb: 里氏硬度（→ 后端 leeb.run）
 *   - 未来: rebound（回弹）/ core_drilling（钻芯）/ ...
 *
 * 后端真源：api/handlers/leeb.py。preview_excel 是通用读 Excel 表格（与 calcType 无关）。
 */
export type CalcType = "leeb";

export const CALC_TYPE_LABELS: Record<CalcType, string> = {
  leeb: "里氏硬度",
};

export type CellValue = string | number | boolean | null;

export interface PreviewRes {
  sheets: string[];
  sheet: string;
  headers: string[];
  rows: Record<string, CellValue>[];
  total_rows: number;
  shown_rows: number;
}

export interface RunRes {
  batches: number;
  components: number;
  output: string;
}
