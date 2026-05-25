/**
 * data_processing 工具的前端类型契约。
 *
 * 当前支持的 calcType：
 *   - leeb: 里氏硬度（→ 后端 leeb.run）
 *   - anchor: 锚杆抗拔试验 GB 50086-2015（→ 后端 anchor.run）
 *
 * preview_excel 是通用读 Excel（与 calcType 无关），沿用 leeb.preview_excel；
 * 列表加批次清单（anchor 独有）走 anchor.list_batches。
 */
export type CalcType = 'leeb' | 'anchor';

export const CALC_TYPE_LABELS: Record<CalcType, string> = {
  leeb: '里氏硬度',
  anchor: '锚杆抗拔试验',
};

export type CellValue = string | number | boolean | null;

export interface MergeRange {
  sr: number;
  sc: number;
  er: number;
  ec: number;
}

export interface PreviewRes {
  sheets: string[];
  sheet: string;
  headers: string[];
  rows: Record<string, CellValue>[];
  total_rows: number;
  shown_rows: number;
  merges?: MergeRange[];
}

/**
 * 统一运行结果：summary 文本由 controller 按 calcType 组装，
 * Page/输出面板直接展示，不感知具体 calcType 的字段差异。
 */
export interface RunRes {
  calcType: CalcType;
  output: string;
  summary: string;
}

// ── 锚杆专属 ────────────────────────────────────────────────

/** 锚杆工程参数（同一批次所有锚杆共享）。单位与后端一致：N / mm / mm² / N/mm²。 */
export interface AnchorParams {
  P: number;
  Lf: number;
  La: number;
  A: number;
  E: number;
}

export const DEFAULT_ANCHOR_PARAMS: AnchorParams = {
  P: 180000,
  Lf: 500,
  La: 7500,
  A: 804.25,
  E: 200000,
};

export const ANCHOR_STANDARDS = ['GB 50086-2015'] as const;
export type AnchorStandard = (typeof ANCHOR_STANDARDS)[number];

export const ANCHOR_DEFAULT_BATCH_COL = '批次';
