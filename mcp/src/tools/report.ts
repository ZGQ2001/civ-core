/**
 * report.* —— 通用占位符渲染（独立于具体计算）。
 *
 * 跟 anchor_run 的 word_template_path 路径不一样：那个是「锚杆专用」并自动注入
 * 每根锚杆的计算结果；本 tool 是纯字段替换，给 agent 一份 docx + 一个 {key:value}
 * 字典就能出文档。适合非装配线场景（用户自己准备数据出报告）。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const reportRenderPlaceholder: ToolDef = {
  rpcMethod: "report.render_placeholder",
  mcpName: "report_render_placeholder",
  description:
    "把 docx 模板里的 `{{key}}` 占位符按 values 字典渲染，写到 output_path。" +
    "返回 {output_path, replaced, unknown_keys}。" +
    "\n\n跟 anchor_run 的 Word 路径区别：本 tool 不跑计算、不嵌图片、不处理 [[marker]]" +
    "重复区域——纯字段替换。给 agent 一份模板 + 一份字段值就行。" +
    "\n\nagent 建议：调本 tool 前先 template_fields 拿 catalog 字段清单，确认 values 的 key 命中目录。",
  inputSchema: {
    docx_path: z.string().describe("Word 模板绝对路径（含 `{{key}}` 占位符）"),
    output_path: z.string().describe("输出 docx 绝对路径"),
    catalog_id: z.string().describe("字段目录 id（决定 key 别名/格式化规则）"),
    values: z
      .record(
        z.string(),
        z.union([z.string(), z.number(), z.boolean(), z.null()]),
      )
      .describe(
        "{key: value} 字段值字典。key 可以是 catalog 的 key、name 或 alias 任一。",
      ),
  },
};

export const allReportTools: readonly ToolDef[] = [reportRenderPlaceholder];
