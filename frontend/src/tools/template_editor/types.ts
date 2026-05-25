/**
 * template_editor wire 类型 —— 跟 C# Handlers/TemplateHandlers.cs 对齐。
 *
 * 占位符驱动后只剩字段元数据：用户的 Word 模板就是配置，前端不再有 bindings /
 * ParsedTable / TemplateConfig 等概念。
 */

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
