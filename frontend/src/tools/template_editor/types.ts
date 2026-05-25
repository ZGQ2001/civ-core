/**
 * template_editor wire 类型 —— 跟 C# `Template/` + Handlers/TemplateHandlers.cs 的 RPC 投影对齐。
 * 全部走 snake_case，跟后端 JSON 一致。纯类型文件，无 runtime 逻辑。
 */

// ── 字段元数据（来自 template.fields RPC）─────────────────

export type FieldSource =
  | 'parameter'
  | 'calculated'
  | 'raw_input'
  | 'user_input';

export interface FieldDef {
  key: string;
  name: string;
  source: FieldSource;
  value_type: 'string' | 'double' | 'int' | 'bool';
  default_format: string | null;
}

// ── 解析后的 Word 表（来自 template.parse RPC）───────────

export interface ParsedCell {
  row: number;
  col: number;
  text: string;
  row_span: number;
  col_span: number;
  bold: boolean;
  font_size: number | null;
}

export interface ParsedTable {
  row_count: number;
  col_count: number;
  table_signature: string;
  cells: ParsedCell[];
}

// ── 模板配置（C# TemplateConfig 投影）────────────────────

export type RepeatStrategy = 'per_row' | 'per_batch';

export interface CellBinding {
  row: number;
  col: number;
  field_key: string;
  format: string | null;
}

export interface TemplateConfig {
  version: number;
  project_type: string;
  display_name: string;
  table_signature: string;
  repeat: RepeatStrategy;
  bindings: CellBinding[];
}

// ── 列表项（template.list RPC）──────────────────────────

export interface TemplateMeta {
  name: string;
  project_type?: string;
  display_name?: string;
  broken?: boolean;
}

// ── 加载结果（template.load RPC）────────────────────────

export interface TemplateLoadRes {
  config: TemplateConfig;
  source_docx_path: string;
  parsed: ParsedTable;
}
