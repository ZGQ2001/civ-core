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
    "含可见「批次信息」sheet（批次/P/Lf/La/A/E/灌浆日期）——按批次工程参数 + 灌浆日期填这里，" +
    "anchor_run 会自动读取，无需再传 params_by_batch。" +
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

export const anchorReadBatchInfo: ToolDef = {
  rpcMethod: "anchor.read_batch_info",
  mcpName: "anchor_read_batch_info",
  description:
    "读输入 Excel 的「批次信息」sheet → 各批工程参数 + 灌浆日期。" +
    "返回 {batches: [{batch_id, params: {P,Lf,La,A,E}|null, grouting_date}]}。" +
    "sheet 缺失（别人给的旧 Excel）返回空列表。" +
    "用于在 anchor_run 之前确认 xlsx 里已填好参数（params=null 表示该批还没填）。",
  inputSchema: {
    input_xlsx: z.string().describe("锚杆数据 Excel 绝对路径"),
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
    "\n\n可选 word_template_path 触发 Word 报告（薄壳 + 占位符，不再用 marker/「锚杆专用模板」）：" +
    "要放表处写一段 `{{表格:锚杆}}`，程序按规范建逐根 表2.4（单根→「表{节号}」/多根→「表{节号}-1…」，" +
    "节号由 section_no 定、缺省 2.4）插在该处；表内 `{{img:曲线图}}` 配 curve_image_dir 按 anchor_id 嵌图；" +
    "项目信息写 {{委托单位}} 等 {{}} 占位符、由 user_inputs/batch_user_inputs 填（各批灌浆日期出现在本批锚杆表）。" +
    "\n\n典型流程：先 anchor_list_batches 拿批次清单 → 为每批填 params_by_batch → 调本 tool。",
  inputSchema: {
    input_xlsx: z.string().describe("锚杆数据 Excel 绝对路径"),
    params_by_batch: z
      .record(z.string(), anchorParamsSchema)
      .optional()
      .describe(
        "{ batchId: {P,Lf,La,A,E} }。可选 —— 不传则从输入 xlsx 的「批次信息」sheet 读。" +
          "传了的批次以传入值为准（覆盖 sheet）；最终每个 batch_id 都得有参数（GUI 或 sheet），" +
          "否则报错。纯 agent 流推荐把参数写进「批次信息」sheet，这里不传。",
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
        "Word 薄壳模板 docx 绝对路径，含 {{表格:锚杆}} 数据表占位符 + 项目信息 {{}} 占位符。" +
          "给了就出 Word 报告，留空只出 Excel。",
      ),
    section_no: z
      .string()
      .optional()
      .describe("锚杆结果表节号；单根→「表{节号}」/多根→「表{节号}-1…」，缺省 2.4"),
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
        "批次级用户输入（{batchId: {key: value}}）—— 各批的值出现在本批锚杆表（如灌浆日期格）。" +
          "目前唯一支持的字段：grouting_date（灌浆日期）。例：" +
          "{'B1': {grouting_date: '2026-05-01'}, 'B2': {grouting_date: '2026-05-03'}}",
      ),
  },
};

export const allAnchorTools: readonly ToolDef[] = [
  anchorGenerateTemplate,
  anchorListBatches,
  anchorReadBatchInfo,
  anchorRun,
];
