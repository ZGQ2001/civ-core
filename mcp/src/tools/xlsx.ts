/**
 * xlsx.* —— Excel 重资产场景（ClosedXML 写精致排版）。
 *
 * 目前唯一方法 write_leeb_report_table 跟 leeb_run 配对使用：
 * leeb_run 算完返 report_table_data，本 tool 把它转写成报告插入 sheet。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

/** 单个构件：3 测区 × 9 次读数 + 该构件代表强度。schema 跟 LeebReportBatch 一一对照。 */
const leebComponentSchema = z.object({
  name: z.string().describe("构件名（如「地上一层1/A×（4~1/4）轴钢梁」）"),
  thickness_mm: z.number().describe("构件厚度（mm）"),
  test_areas_raw: z
    .array(z.array(z.number()))
    .describe("测区原始读数：array of arrays（如 3 测区 × 9 次冲击）"),
  comp_fb_min_avg: z.number().describe("该构件代表强度（MPa）"),
});

const leebBatchSchema = z.object({
  sheet_name: z.string().describe("批次 sheet 名（如「检测批1-报告插入表」）"),
  components: z.array(leebComponentSchema).describe("该批所有构件"),
  batch_fb_char_avg: z.number().describe("批代表强度（MPa）"),
});

export const xlsxWriteLeebReportTable: ToolDef = {
  rpcMethod: "xlsx.write_leeb_report_table",
  mcpName: "xlsx_write_leeb_report_table",
  description:
    "把里氏硬度的「报告插入表」追加到指定 xlsx（每批 1 sheet；同名 sheet 覆盖）。" +
    "返回 {ok, sheets_written}。" +
    "\n\n典型场景：拿 leeb_run 返回的 report_table_data 直接当 batches 参数传入。",
  inputSchema: {
    output_path: z
      .string()
      .describe(
        "输出 xlsx 绝对路径。文件存在则追加 sheet，不存在则新建。",
      ),
    batches: z
      .array(leebBatchSchema)
      .describe("批次数据（一般直接传 leeb_run 返回的 report_table_data）"),
  },
};

export const allXlsxTools: readonly ToolDef[] = [xlsxWriteLeebReportTable];
