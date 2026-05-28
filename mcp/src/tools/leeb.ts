/**
 * leeb.* —— 里氏硬度装配线（GB/T 17394 + JGJ/T 23）。
 *
 * 流程跟 anchor 类似但更简单：preview_excel 看一眼数据 → run 算硬度
 * + 返 report_table_data（不写文件）→ 调 xlsx_write_leeb_report_table
 * 把表写到 Excel。装配线被拆成两步是因为 Python 端先写「过程数据」，
 * C# 端追加「报告插入表」，两边协作走同一 xlsx 文件（见 XlsxHandlers）。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const leebRun: ToolDef = {
  rpcMethod: "leeb.run",
  mcpName: "leeb_run",
  description:
    "运行里氏硬度全流程：读 Excel → 套规范 → 算硬度。" +
    "返回 {batches, components, output, report_table_data}。" +
    "注意：本 tool 只算数据不写报告 xlsx——拿到 report_table_data 后调 " +
    "xlsx_write_leeb_report_table 写正式报告插入表。",
  inputSchema: {
    input_xlsx: z.string().describe("里氏硬度数据 Excel 绝对路径"),
    output_xlsx: z
      .string()
      .optional()
      .describe(
        "输出 xlsx 路径（缺省 '<input同目录>/<原名>_里氏_结果.xlsx'）。仅决定 output 字段。",
      ),
    angle_degrees: z
      .number()
      .optional()
      .describe("默认冲击角度（度），缺省 0.0。每构件可在 Excel 里另填覆盖。"),
  },
};

export const leebPreviewExcel: ToolDef = {
  rpcMethod: "leeb.preview_excel",
  mcpName: "leeb_preview_excel",
  description:
    "Excel 前 N 行预览：列出 sheets、表头、若干数据行 + 合并单元格信息。" +
    "agent 想快速看清一份未知 Excel 结构时用。返回 " +
    "{sheets, sheet, headers, rows, total_rows, shown_rows, merges}。",
  inputSchema: {
    path: z.string().describe("Excel 文件绝对路径"),
    sheet: z.string().optional().describe("sheet 名（缺省第一个）"),
    header_row: z
      .number()
      .int()
      .optional()
      .describe("表头所在行（1-based），缺省 1"),
    max_rows: z
      .number()
      .int()
      .optional()
      .describe("最多返回多少行数据，缺省 50"),
  },
};

export const allLeebTools: readonly ToolDef[] = [leebRun, leebPreviewExcel];
