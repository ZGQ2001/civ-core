/**
 * coating.* —— 防火涂层厚度（GB 50205-2020 §13.4.3 厚涂型验收）装配线 3 tool。
 *
 * 典型用户流（agent 视角）：
 *   1. coating_generate_template 出空白长表模板（首次用）
 *   2. （用户/agent 把测点数据填进 Excel，每行一测点）
 *   3. coating_list_batches 拿批次清单（信息性，可跳过）
 *   4. coating_run 跑判定，每批出「<批>-数据分析」宽表 sheet
 *
 * 与 anchor 的差异：设计厚度在输入 Excel「设计厚度」列里（按构件），不需要按批次填工程参数。
 * 入参 schema 跟 dotnet/civ-doc/Handlers/CoatingHandlers.cs 一一对照。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const coatingGenerateTemplate: ToolDef = {
  rpcMethod: "coating.generate_template",
  mcpName: "coating_generate_template",
  description:
    "生成空白防火涂层厚度输入 Excel 模板（长表：每行一个测点）。" +
    "列：批次 / 构件位置 / 构件类型 / 设计厚度 / 截面号 / 测点位置 / 实测厚度，含钢梁(3面)+钢柱(4面)样例。" +
    "单位统一 mm。返回 {ok, path}。用户拿模板填数据后用 coating_run。",
  inputSchema: {
    output_xlsx: z
      .string()
      .describe("输出 xlsx 绝对路径（所在目录必须已存在；同名文件会被覆盖）"),
    standard: z
      .string()
      .optional()
      .describe("规范版本，目前仅支持 'GB 50205-2020'（缺省即此值）"),
  },
};

export const coatingListBatches: ToolDef = {
  rpcMethod: "coating.list_batches",
  mcpName: "coating_list_batches",
  description:
    "读输入 Excel 返回所有批次 ID。返回 {batches: string[]}。" +
    "「批次」列缺失时返回单元素默认批（不分批）。信息性，coating_run 不依赖它。",
  inputSchema: {
    input_xlsx: z.string().describe("防火涂层数据 Excel 绝对路径"),
    sheet: z.string().optional().describe("sheet 名（缺省取第一个 sheet）"),
    batch_id_column: z
      .string()
      .optional()
      .describe("批次列列名，缺省 '批次'"),
  },
};

export const coatingRun: ToolDef = {
  rpcMethod: "coating.run",
  mcpName: "coating_run",
  description:
    "运行防火涂层厚度厚涂型验收（GB 50205-2020 §13.4.3）：读长表 Excel + 按构件聚合判定 + 写「<批>-数据分析」宽表 sheet。" +
    "判定（按构件）：≥80% 测点 ≥ 设计厚度，且最薄处 ≥ 设计 × 85%，两者都满足为合格。" +
    "设计厚度在 Excel「设计厚度」列里按构件填——不需要像 anchor 那样传 params_by_batch。" +
    "返回 {batches, members_total, members_qualified, output}。",
  inputSchema: {
    input_xlsx: z.string().describe("防火涂层数据 Excel 绝对路径（长表，每行一测点）"),
    output_xlsx: z
      .string()
      .optional()
      .describe(
        "输出 xlsx 绝对路径。缺省时在 input 同目录写 '<原名>_防火涂层_结果.xlsx'",
      ),
    standard: z
      .string()
      .optional()
      .describe("规范版本，默认 'GB 50205-2020'"),
    sheet: z.string().optional().describe("输入 Excel 的 sheet 名"),
    batch_id_column: z
      .string()
      .optional()
      .describe("批次列列名，缺省 '批次'（无此列则所有构件归入单批）"),
  },
};

export const allCoatingTools: readonly ToolDef[] = [
  coatingGenerateTemplate,
  coatingListBatches,
  coatingRun,
];
