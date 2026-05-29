/**
 * catalog.* —— 字段目录（report user_inputs 的字段定义）CRUD。
 *
 * 字段目录是「这种检测类型的报告允许填哪些字段」的唯一来源：每个字段有
 * key / 中文名 / 分组 / 层级 / 来源 / 值类型 / 默认格式 / 别名。anchor_run、
 * report_render_placeholder 等需要 user_inputs 的 tool 都按它来对字段。
 *
 * agent 用法：
 *   - 查字段定义优先用 template_fields（只读、更轻）；catalog_get 返回更完整的目录对象。
 *   - catalog_save / catalog_delete 会改全局字段目录（落 ~/.civ-core/），属配置级写操作，
 *     非必要别动——给报告填字段值用 report_preset_*，不要改 catalog。
 *
 * 入参 schema 跟 dotnet/civ-doc/Handlers/CatalogHandlers.cs + Catalog/FieldCatalogDto.cs 对照。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const catalogList: ToolDef = {
  rpcMethod: "catalog.list",
  mcpName: "catalog_list",
  description:
    "列出所有字段目录。返回 {catalogs: [{id, label, field_count}]}。" +
    "agent 用法：先列出有哪些检测类型的目录（如 'anchor' 锚杆抗拔），再用 catalog_get / template_fields 看字段。",
};

export const catalogGet: ToolDef = {
  rpcMethod: "catalog.get",
  mcpName: "catalog_get",
  description:
    "读单个字段目录的完整定义。返回 {catalog: {id, label, fields: [{key, name, group, level, source, value_type, default_format, aliases}]}}。" +
    "\n\n只想拿字段清单（不要目录壳）的话用更轻的 template_fields。",
  inputSchema: {
    id: z.string().describe("字段目录 id（如 'anchor'）"),
  },
};

/** 单个字段定义 schema，对照 Catalog/FieldCatalogDto.cs 的 CatalogFieldDto。 */
const catalogFieldSchema = z.object({
  key: z.string().describe("字段 key（英文小写下划线，模板占位符 {{key}} 用）"),
  name: z.string().describe("显示名（中文）"),
  group: z.string().describe("分组（UI 折叠卡片归类用，如 '委托信息'）"),
  level: z
    .enum(["report", "detection_item", "batch", "component"])
    .describe(
      "字段层级：report 报告级 / detection_item 检测项目级 / batch 检测批级 / component 构件级。" +
        "模板验证器据此检查占位符是否放在正确的重复标记区域内。",
    ),
  source: z
    .string()
    .describe("字段来源，通常 'user_input'（用户填）或 'computed'（计算产出）"),
  value_type: z
    .string()
    .describe("值类型，如 'string' / 'number' / 'date'"),
  default_format: z
    .string()
    .optional()
    .describe("默认数字格式（如 '0.00' 两位小数）；非数字字段留空"),
  aliases: z
    .array(z.string())
    .optional()
    .describe("别名列表——模板里写别名也能命中本字段"),
});

export const catalogSave: ToolDef = {
  rpcMethod: "catalog.save",
  mcpName: "catalog_save",
  description:
    "新建或覆盖字段目录（按 catalog.id 主键）。返回 {ok}。" +
    "\n\n⚠️ 这是配置级写操作，会改全局字段目录（落 ~/.civ-core/），影响该检测类型所有报告的字段对照。" +
    "给单份报告填字段值请用 report_preset_save，不要动 catalog。",
  inputSchema: {
    catalog: z
      .object({
        id: z.string().describe("目录 id（英文小写下划线，如 'anchor'）"),
        label: z.string().describe("显示名（中文）"),
        fields: z
          .array(catalogFieldSchema)
          .describe("字段定义列表"),
      })
      .describe("字段目录完整内容"),
  },
};

export const catalogDelete: ToolDef = {
  rpcMethod: "catalog.delete",
  mcpName: "catalog_delete",
  description:
    "按 id 删字段目录。返回 {ok}。⚠️ 配置级删除——删了该检测类型就没有字段对照了，慎用。",
  inputSchema: {
    id: z.string().describe("字段目录 id"),
  },
};

export const allCatalogTools: readonly ToolDef[] = [
  catalogList,
  catalogGet,
  catalogSave,
  catalogDelete,
];
