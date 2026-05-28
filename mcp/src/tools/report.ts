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

export const reportRunFromResult: ToolDef = {
  rpcMethod: "report.run_from_result",
  mcpName: "report_run_from_result",
  description:
    "用已经算好的结果 xlsx 直接出 Word 报告——不重新跑 AnchorCalculator，省事且避免" +
    "用户重复输入工程参数（P/Lf/La/A/E 等从结果 xlsx 的隐藏 metadata sheet 自动读）。" +
    "\n\n输入 result_xlsx 必须由 anchor_run 产出（含 `_批次参数` 隐藏 sheet）。" +
    "旧版本生成的结果 xlsx 不带 metadata，会返清晰错误提示重新跑装配线。" +
    "\n\n模板探测同 anchor_run：单层 / [[批次]] / [[检测项目]]>[[批次]]>[[每根锚杆]] 三种嵌套自动分发。" +
    "\n\n返回 {batches, anchors_total, anchors_qualified, output, word_outputs," +
    "word_unknown_keys, word_missing_images}—— 字段与 anchor_run 对齐方便 agent 一致处理。",
  inputSchema: {
    result_xlsx: z
      .string()
      .describe("anchor_run 已产出的结果 xlsx 绝对路径（含每批数据分析 sheet + _批次参数 sheet）"),
    word_template_path: z
      .string()
      .describe("Word 模板绝对路径，带 {{占位符}} 和 [[每根锚杆]] / [[批次]] marker"),
    standard: z
      .string()
      .optional()
      .describe("规范代号；默认 GB 50086-2015"),
    word_output_dir: z
      .string()
      .optional()
      .describe("Word 输出目录；留空 = 结果 xlsx 同级 <stem>_Word报告/"),
    curve_image_dir: z
      .string()
      .optional()
      .describe("plot_curves 出图目录；留空 = {{img:曲线图}} 留原文并报 missing"),
    report_name: z
      .string()
      .optional()
      .describe("报告文件名；自动补 .docx 后缀；留空 = 默认「锚杆抗拔报告.docx」"),
    user_inputs: z
      .record(z.string(), z.string())
      .optional()
      .describe("报告级 + 检测项目级 user_inputs；可直接喂 report_preset_get 的返回值"),
    batch_user_inputs: z
      .record(z.string(), z.record(z.string(), z.string()))
      .optional()
      .describe("批次级 user_inputs：{batchId: {key: value}}，目前只用 grouting_date"),
  },
};

export const allReportTools: readonly ToolDef[] = [
  reportRenderPlaceholder,
  reportRunFromResult,
];
