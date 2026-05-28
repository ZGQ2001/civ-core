/**
 * report_preset.* —— 报告填充 user_inputs 预设 CRUD。
 *
 * agent 用法：用户跨报告复用「委托单位 + 仪器 + 检测人员」这套元信息，
 * 把它存成预设，下次出同类报告一键载入。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const reportPresetList: ToolDef = {
  rpcMethod: "report_preset.list",
  mcpName: "report_preset_list",
  description:
    "列报告预设。可按 catalog_id 过滤（建议传，避免给锚杆报告拉钻芯预设）。" +
    "返回 {presets: [{id, label, catalog_id, updated_at, field_count}]}，按 updated_at 倒序。",
  inputSchema: {
    catalog_id: z
      .string()
      .optional()
      .describe("字段目录 id 过滤；不传则列全部"),
  },
};

export const reportPresetGet: ToolDef = {
  rpcMethod: "report_preset.get",
  mcpName: "report_preset_get",
  description:
    "读单个预设的完整内容。返回 {preset: {id, label, catalog_id, user_inputs, updated_at}}。" +
    "user_inputs 直接喂给 anchor_run 的 user_inputs 参数即可。",
  inputSchema: {
    id: z.string().describe("预设 id"),
  },
};

export const reportPresetSave: ToolDef = {
  rpcMethod: "report_preset.save",
  mcpName: "report_preset_save",
  description:
    "新建或覆盖预设（按 id 主键）。" +
    "返回 {ok, id, updated_at}（带 server 端写入时间）。" +
    "\n\nuser_inputs 建议只放 catalog 里 level=report/detection_item 的 user_input 字段；" +
    "level=batch / level=component 的字段每次不同，不该入预设。",
  inputSchema: {
    preset: z
      .object({
        id: z
          .string()
          .describe("预设 id（英文小写下划线，例：xx_env_standard）"),
        label: z.string().describe("显示名（中文）"),
        catalog_id: z.string().describe("绑定的字段目录 id"),
        user_inputs: z
          .record(z.string(), z.string())
          .describe("字段值 map（key 来自 catalog 的 field.key）"),
      })
      .describe("预设完整内容；server 会自动补 updated_at"),
  },
};

export const reportPresetDelete: ToolDef = {
  rpcMethod: "report_preset.delete",
  mcpName: "report_preset_delete",
  description: "按 id 删预设。返回 {ok}。",
  inputSchema: {
    id: z.string().describe("预设 id"),
  },
};

export const reportPresetRename: ToolDef = {
  rpcMethod: "report_preset.rename",
  mcpName: "report_preset_rename",
  description: "改预设的 label（不动 id / user_inputs）。返回 {ok}。",
  inputSchema: {
    id: z.string().describe("预设 id"),
    label: z.string().describe("新显示名"),
  },
};

export const allReportPresetTools: readonly ToolDef[] = [
  reportPresetList,
  reportPresetGet,
  reportPresetSave,
  reportPresetDelete,
  reportPresetRename,
];
