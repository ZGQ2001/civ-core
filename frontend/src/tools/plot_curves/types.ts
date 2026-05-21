/**
 * plot_curves preset 类型（与后端 presets/plot_curves/curve_presets.json 对齐）。
 * points 用 unknown[] —— form 不暴露，原样透传。
 */
export interface AxisSpec {
  label: string;
  range: [number, number, number] | null;
  log?: boolean;
}

export interface CurveDef {
  name: string;
  color: string;
  marker?: string;
  linewidth?: number;
  markersize?: number;
  points: unknown[];
}

export interface PlotPreset {
  id_column: string;
  filename_template: string;
  title_template: string;
  x_axis: AxisSpec;
  y_axis: AxisSpec;
  y_axis2?: AxisSpec | null;
  curves: CurveDef[];
  style?: { grid?: boolean; legend?: string | null };
}

export interface PreviewRes {
  png_base64: string;
  mime: string;
  row_id: string;
  title: string;
  total_rows: number;
  /** 当前行的所有列值 — 给前端"数据对照"折叠区显示 */
  row_data: Record<string, string | number | boolean | null>;
}

export interface FailedItem {
  path: string;
  error: string;
}

export interface RunRes {
  written: string[];
  failed: FailedItem[];
  summary: {
    total: number;
    written_count: number;
    failed_count: number;
    skipped_empty_id: number;
    skipped_bad_data: number;
  };
  output_dir: string;
}
