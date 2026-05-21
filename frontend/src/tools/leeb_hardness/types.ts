/**
 * leeb_hardness 工具的前端类型契约。后端真源在 api/handlers/leeb.py。
 */
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
