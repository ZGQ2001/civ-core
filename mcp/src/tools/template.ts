/**
 * template.* —— 字段目录查询（给 agent / 用户配 user_inputs 时参考）。
 *
 * Phase 1 仅暴露 template.fields；template.validate（docx 占位符校验）留待 Phase 2，
 * 因为它面向「人 review 模板」场景，agent 自己很少直接用。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const templateFields: ToolDef = {
  rpcMethod: "template.fields",
  mcpName: "template_fields",
  description:
    "查指定字段目录下的全部字段定义。" +
    "返回 {fields: [{key, name, group, level, source, value_type, default_format, aliases}]}。" +
    "\n\nagent 用法：调用 anchor_run / report_render_placeholder 等需要 user_inputs 的 tool 前，" +
    "先用这个查清楚字段 key/中文名/别名/单位，避免猜测。" +
    "\n\n常见 catalog_id：`anchor`（锚杆抗拔）。完整列表后续在文档同步。",
  inputSchema: {
    catalog_id: z.string().describe("字段目录 id（如 'anchor'）"),
  },
};

export const allTemplateTools: readonly ToolDef[] = [templateFields];
