/**
 * template.* —— 字段目录查询 + docx 模板占位符校验。
 *
 * template.fields 查字段清单；template.validate 体检一份 docx 模板：占位符是否都能
 * 命中字段、有没有未识别的、哪些字段没用上、重复标记 marker 嵌套是否合法。
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

export const templateValidate: ToolDef = {
  rpcMethod: "template.validate",
  mcpName: "template_validate",
  description:
    "体检一份 Word 模板（docx）的占位符。扫 `{{字段}}` 占位符 + `[[标记]]...[[/标记]]` 重复标记，" +
    "对照指定字段目录给出：matched（命中字段）/ unrecognized（写了但没对应字段，多半拼错）/ " +
    "unused（目录里有但模板没用）/ markers（嵌套结构）/ hints（层级放错位置等可操作提示）/ summary。" +
    "\n\nagent 用法：用户给了甲方模板、或自己改了模板后，先 validate 一遍确认占位符都对得上，再喂给 anchor_run 的 word_template_path。",
  inputSchema: {
    docx_path: z.string().describe("Word 模板 docx 绝对路径"),
    catalog_id: z
      .string()
      .describe("对照的字段目录 id（如 'anchor'）；决定哪些占位符算「识别」"),
  },
};

export const allTemplateTools: readonly ToolDef[] = [
  templateFields,
  templateValidate,
];
