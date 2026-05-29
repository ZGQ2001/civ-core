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
 *
 * 数据处理只算 + 出 Excel；Word 报告已迁出至独立的「报告填充」工具。
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

/**
 * 数据处理 → 报告填充 的「一键导入」快照（装配线显式快照，避免下游直接 useDataProcessing）。
 *
 * data_processing controller 在自身相关 state 变化时把这份快照发布到 ShellContext；
 * report_generator 从 shell 读它来算「上游是否就绪」探针 + 执行一键导入。
 * 这样 report 不再依赖 DataProcessingProvider 的嵌套顺序，可独立挂载/测试。
 * 跨工具共享走 ShellContext（与 curveImageDir 同一先例），不新造管线抽象。
 */
export interface DataProcessingSnapshot {
  calcType: CalcType;
  excelPath: string;
  /** 结果 xlsx 路径（算过才有）；一键导入据此决定走 result 还是 raw。 */
  outputPath: string;
  sheet: string;
  anchorStandard: AnchorStandard;
  anchorBatchIdColumn: string;
  anchorBatchIds: string[];
  anchorParamsByBatch: Record<string, AnchorParams>;
}
