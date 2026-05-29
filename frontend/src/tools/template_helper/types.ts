export type FieldLevel = 'report' | 'detection_item' | 'batch' | 'component';

export interface CatalogField {
  key: string;
  name: string;
  group: string;
  level: FieldLevel;
  source: string;
  value_type: string;
  default_format: string | null;
  aliases: string[];
}

export interface FieldCatalog {
  id: string;
  label: string;
  fields: CatalogField[];
}

export interface CatalogSummary {
  id: string;
  label: string;
  field_count: number;
}

export interface MatchedField {
  placeholder: string;
  key: string;
  name: string;
  level: FieldLevel;
  location: string;
  scope: string;
  is_image: boolean;
}

export interface UnrecognizedField {
  placeholder: string;
  location: string;
  scope: string;
}

export interface UnusedField {
  key: string;
  name: string;
  group: string;
  level: FieldLevel;
}

export interface ValidateHint {
  severity: 'warning' | 'error';
  field_name: string;
  expected_level: string;
  actual_scope: string;
  location: string;
  message: string;
}

export interface MarkerInfo {
  text: string;
  type: 'open' | 'close';
  level: string;
  location: string;
}

export interface ValidateSummary {
  matched_count: number;
  unrecognized_count: number;
  unused_count: number;
  hint_count: number;
  total_catalog_fields: number;
}

export interface ValidateResult {
  matched: MatchedField[];
  unrecognized: UnrecognizedField[];
  unused: UnusedField[];
  markers: MarkerInfo[];
  hints: ValidateHint[];
  summary: ValidateSummary;
}

export const LEVEL_LABEL: Record<FieldLevel, string> = {
  report: '报告级',
  detection_item: '检测项目级',
  batch: '批次级',
  component: '构件级',
};

/**
 * 层级的宏观→微观规范顺序 —— 报告级 > 检测项目级 > 批次级 > 构件级。
 * 用于「按层级」分组时固定分组排列（否则按字段插入顺序，看着乱）。
 * 与 C# TemplateHandlers.LevelOrder 对齐。
 */
export const LEVEL_ORDER: FieldLevel[] = [
  'report',
  'detection_item',
  'batch',
  'component',
];

export const LEVEL_COLOR: Record<FieldLevel, string> = {
  report: 'text-blue-400',
  detection_item: 'text-cyan-400',
  batch: 'text-yellow-400',
  component: 'text-green-400',
};
