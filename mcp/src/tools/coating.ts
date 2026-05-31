/**
 * coating.* —— 防火涂层厚度（GB 50205-2020 §13.4.3 涂层厚度验收）装配线 4 tool。
 *
 * 流程（构件清单驱动，用户/agent 几乎只填数字）：
 *   1. coating_generate_template 出「类型预设 + 构件清单」模板
 *   2. （填「构件清单」：一构件一行，构件位置/类型/长度或截面数/设计厚度）
 *   3. coating_expand_template 展开成「测点数据-<类型>」网格（国标薄/超薄为 5 测点×3 次）
 *   4. （在网格里填实测数字）
 *   5. coating_run 跑判定，每批出「<批>-数据分析」宽表
 *
 * 涂层类型按设计厚度自动分级（≥7厚/3~7薄/≤3超薄）。判定：厚型 ≥80%测点达标且最薄≥设计×0.85；
 * 膨胀型(薄/超薄) 构件均值 ≥ 设计×0.95（偏差−5%，加−200µm兜底）。
 * 入参 schema 跟 dotnet/civ-doc/Handlers/CoatingHandlers.cs 一一对照。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const coatingGenerateTemplate: ToolDef = {
  rpcMethod: "coating.generate_template",
  mcpName: "coating_generate_template",
  description:
    "生成防火涂层厚度输入模板（含「类型预设」预填梁/柱 + 「构件清单」）。" +
    "返回 {ok, path}。用户/agent 在「构件清单」一构件一行填好后，用 coating_expand_template 展开。",
  inputSchema: {
    output_xlsx: z
      .string()
      .describe("输出 xlsx 绝对路径（所在目录必须已存在；同名文件会被覆盖）"),
    standard: z
      .string()
      .optional()
      .describe("'GB 50205-2020'（国标，缺省）或 '北京地标'（每1m一截面）"),
  },
};

export const coatingExpandTemplate: ToolDef = {
  rpcMethod: "coating.expand_template",
  mcpName: "coating_expand_template",
  description:
    "读「构件清单」展开成「测点数据-<类型>」网格（每构件铺 N 行，测点列留空待填数字）。" +
    "布局按 标准×涂层类型：国标薄/超薄型→「测点数据-<类型>-膨胀型」5 测点×3 次（测点号1~5，列头 第一次/第二次/第三次）；" +
    "其余（国标厚型 / 地标任意）→面名网格，截面数按 ⌈长度/间距⌉（国标3m/北京地标1m）。" +
    "解析规则：构件类型空则从构件位置名识别（含「梁/柱」）；设计厚度空则用类型预设默认。" +
    "返回 {ok, path, members, total_sections, sheets}。output_xlsx 缺省=写回 input_xlsx。",
  inputSchema: {
    input_xlsx: z.string().describe("含「类型预设」+「构件清单」的 Excel 绝对路径"),
    output_xlsx: z
      .string()
      .optional()
      .describe("输出 xlsx 绝对路径，缺省写回 input_xlsx（新增/覆盖「测点数据」表）"),
    standard: z
      .string()
      .optional()
      .describe("'GB 50205-2020'（间距3m，缺省）或 '北京地标'（间距1m）——决定截面数"),
  },
};

export const coatingListBatches: ToolDef = {
  rpcMethod: "coating.list_batches",
  mcpName: "coating_list_batches",
  description:
    "读「测点数据」返回所有批次 ID。返回 {batches: string[]}。" +
    "批次列缺失时返回单元素默认批。信息性，coating_run 不依赖它。",
  inputSchema: {
    input_xlsx: z.string().describe("已展开（含「测点数据」表）的 Excel 绝对路径"),
    sheet: z.string().optional().describe("sheet 名（缺省取所有「测点数据」开头的表）"),
    batch_id_column: z.string().optional().describe("批次列列名，缺省 '批次'"),
  },
};

export const coatingRun: ToolDef = {
  rpcMethod: "coating.run",
  mcpName: "coating_run",
  description:
    "运行防火涂层厚度验收：读「测点数据」宽表 + 按构件聚合判定 + 写「<批>-数据分析」宽表 sheet。" +
    "判定（GB 50205 §13.4.3）：厚型 ≥80% 测点 ≥ 设计厚度 且 最薄处 ≥ 设计×85%；" +
    "膨胀型(薄/超薄) 构件均值 ≥ 设计×95%（偏差−5%，加−200µm兜底）。" +
    "返回 {batches, members_total, members_qualified, members_pending, output}（梁柱已全判，pending=0）。" +
    "前置：先 coating_expand_template 展开并填好测点数字。",
  inputSchema: {
    input_xlsx: z.string().describe("已展开且填好数字的 Excel 绝对路径"),
    output_xlsx: z
      .string()
      .optional()
      .describe("输出 xlsx 绝对路径。缺省在 input 同目录写 '<原名>_防火涂层_结果.xlsx'"),
    standard: z
      .string()
      .optional()
      .describe("'GB 50205-2020'（缺省）或 '北京地标'"),
    sheet: z.string().optional().describe("输入 Excel 的 sheet 名（缺省读所有「测点数据」表）"),
    batch_id_column: z.string().optional().describe("批次列列名，缺省 '批次'"),
  },
};

export const allCoatingTools: readonly ToolDef[] = [
  coatingGenerateTemplate,
  coatingExpandTemplate,
  coatingListBatches,
  coatingRun,
];
