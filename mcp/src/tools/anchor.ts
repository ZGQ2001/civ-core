/**
 * anchor.* —— 锚杆抗拔（GB 50086-2015）装配线核心 3 tool。
 *
 * 典型用户流（agent 视角）：
 *   1. anchor_generate_template 出空白输入模板（首次用）
 *   2. （用户/agent 把数据填进 Excel）
 *   3. anchor_list_batches 拿到批次 ID 清单
 *   4. anchor_run 跑全流程；可选 word_template_path 同时出 Word 报告
 *
 * 入参 schema 跟 dotnet/civ-doc/Handlers/AnchorHandlers.cs 一一对照。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const anchorGenerateTemplate: ToolDef = {
  rpcMethod: "anchor.generate_template",
  mcpName: "anchor_generate_template",
  description:
    "生成空白锚杆抗拔输入 Excel 模板（按指定规范的列定义）。" +
    "返回 {ok, path}。用户拿模板填数据后用 anchor_run。",
  inputSchema: {
    output_xlsx: z
      .string()
      .describe("输出 xlsx 绝对路径（所在目录必须已存在；同名文件会被覆盖）"),
    standard: z
      .string()
      .optional()
      .describe("规范版本，目前仅支持 'GB 50086-2015'（缺省即此值）"),
  },
};

export const anchorListBatches: ToolDef = {
  rpcMethod: "anchor.list_batches",
  mcpName: "anchor_list_batches",
  description:
    "读输入 Excel 返回所有批次 ID。返回 {batches: string[]}。" +
    "anchor_run 之前调一次，用结果为每个批次准备 params_by_batch。",
  inputSchema: {
    input_xlsx: z.string().describe("锚杆数据 Excel 绝对路径"),
    sheet: z
      .string()
      .optional()
      .describe("sheet 名（缺省取第一个 sheet）"),
    batch_id_column: z
      .string()
      .optional()
      .describe("批次列列名，缺省 '批次'"),
  },
};

/**
 * 每批工程参数 schema：P / Lf / La / A / E 5 字段全必填，按 AnchorParams.Create
 * 的入参签名定义（dotnet/civ-doc/Calc/Anchor/AnchorParams.cs）。
 */
const anchorParamsSchema = z.object({
  P: z.number().describe("轴向拉力设计值（N）"),
  Lf: z.number().describe("自由段长度（mm）"),
  La: z.number().describe("锚固段长度（mm）"),
  A: z.number().describe("杆体截面积（mm²）"),
  E: z.number().describe("弹性模量（MPa）"),
});

export const anchorRun: ToolDef = {
  rpcMethod: "anchor.run",
  mcpName: "anchor_run",
  description:
    "运行锚杆抗拔（GB 50086-2015）全流程：读 Excel + 按批次套工程参数 + 算 + 写「<批>-数据分析」sheet。" +
    "返回 {batches, anchors_total, anchors_qualified, output}。" +
    "\n\n可选 word_template_path 触发 Word 报告。三层模板嵌套：外层 `[[检测项目]]...[[/检测项目]]`" +
    "（检测项目级，可放 {{检测项目}}）→ 中层 `[[批次]]...[[/批次]]`（批次级，可放 {{批次}} {{灌浆日期}}）→" +
    "内层 `[[每根锚杆]]...[[/每根锚杆]]`（构件级，会按每根锚杆克隆一次）。后端按命中的最外层 marker " +
    "决定走单层 / 两层 / 三层路径，向后兼容旧模板。" +
    "`{{img:曲线图}}` 占位符配合 curve_image_dir 自动按 anchor_id 匹配 PNG 嵌入。" +
    "\n\n典型流程：先 anchor_list_batches 拿批次清单 → 为每批填 params_by_batch → 调本 tool。",
  inputSchema: {
    input_xlsx: z.string().describe("锚杆数据 Excel 绝对路径"),
    params_by_batch: z
      .record(z.string(), anchorParamsSchema)
      .describe(
        "{ batchId: {P,Lf,La,A,E} }。每个批次的工程参数全必填。" +
          "batchId 必须覆盖 anchor_list_batches 返回的所有 batch_id（缺谁报错）。",
      ),
    output_xlsx: z
      .string()
      .optional()
      .describe(
        "输出 xlsx 绝对路径。缺省时在 input 同目录写 '<原名>_锚杆_结果.xlsx'",
      ),
    standard: z
      .string()
      .optional()
      .describe("规范版本，默认 'GB 50086-2015'"),
    sheet: z.string().optional().describe("输入 Excel 的 sheet 名"),
    batch_id_column: z
      .string()
      .optional()
      .describe("批次列列名，缺省 '批次'"),
    word_template_path: z
      .string()
      .optional()
      .describe(
        "Word 模板 docx 绝对路径。给了就出 Word 报告，留空只出 Excel。",
      ),
    word_output_dir: z
      .string()
      .optional()
      .describe(
        "Word 报告输出目录。缺省在 input 同目录新建 '<原名>_Word报告/'",
      ),
    curve_image_dir: z
      .string()
      .optional()
      .describe(
        "曲线图目录。`{{img:曲线图}}` 占位符按 anchor_id 拼 PNG 路径自动嵌入。" +
          "目录里 PNG 文件名应与 anchor_id 一致（如 'AG-01.png'）。",
      ),
    user_inputs: z
      .record(z.string(), z.string())
      .optional()
      .describe(
        "项目级用户输入（{key: value}）—— 注入 Word 占位符 `{{xxx}}`。" +
          "例：{委托单位: '甲方公司', 工程名称: 'xxx 项目'}。",
      ),
    batch_user_inputs: z
      .record(z.string(), z.record(z.string(), z.string()))
      .optional()
      .describe(
        "批次级用户输入（{batchId: {key: value}}）—— 模板含 `[[批次]]...[[/批次]]` 时按批次注入。" +
          "目前唯一支持的字段：grouting_date（灌浆日期）。例：" +
          "{'B1': {grouting_date: '2026-05-01'}, 'B2': {grouting_date: '2026-05-03'}}",
      ),
  },
};

export const allAnchorTools: readonly ToolDef[] = [
  anchorGenerateTemplate,
  anchorListBatches,
  anchorRun,
];
