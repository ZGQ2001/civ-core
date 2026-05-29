/**
 * plot_curves.* —— matplotlib 出曲线图（Python sidecar，唯一保留的 Python 路径）。
 *
 * Phase 1 暴露 6 个：list_presets / list_sheets / list_headers / preflight / run / render_preview。
 * 预设 CRUD（save/delete/rename/copy）留待 Phase 2——更偏「人维护预设」，agent 暂用不上。
 *
 * 注意：所有方法走 Python sidecar（SidecarRouter 前缀路由自动）。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const plotCurvesListPresets: ToolDef = {
  rpcMethod: "plot_curves.list_presets",
  mcpName: "plot_curves_list_presets",
  description:
    "列出所有可用绘图预设（system + user 合并去重）。" +
    "返回 {presets: [name], default, details: {name: data}, sources: {name: 'system'|'user'}}。" +
    "agent 决定调 plot_curves_run 前用本 tool 查 preset 名。",
};

export const plotCurvesListSheets: ToolDef = {
  rpcMethod: "plot_curves.list_sheets",
  mcpName: "plot_curves_list_sheets",
  description:
    "列举 Excel 全部 sheet 名（给 agent 在多 sheet 文件里挑一个）。返回 {sheets: [str]}。",
  inputSchema: {
    excel_path: z.string().describe("Excel 文件绝对路径"),
  },
};

export const plotCurvesListHeaders: ToolDef = {
  rpcMethod: "plot_curves.list_headers",
  mcpName: "plot_curves_list_headers",
  description:
    "列举指定 sheet 表头行的列名。返回 {headers: [str]}。" +
    "agent 用法：拿来跟预设要求的列名做比对，缺哪列马上反馈用户。",
  inputSchema: {
    excel_path: z.string().describe("Excel 文件绝对路径"),
    sheet: z.string().optional().describe("sheet 名（缺省第一个）"),
    header_row: z
      .number()
      .int()
      .optional()
      .describe("表头所在行（1-based），缺省 1"),
  },
};

export const plotCurvesPreflight: ToolDef = {
  rpcMethod: "plot_curves.preflight",
  mcpName: "plot_curves_preflight",
  description:
    "跑前预检：读 Excel 表头 + 检查预设要求的列名是否全匹配。" +
    "返回 {ok: bool, message: string}。" +
    "建议在 plot_curves_run 之前先调一次——预检不过就别浪费时间跑全量。",
  inputSchema: {
    excel_path: z.string().describe("数据 Excel 绝对路径"),
    preset: z.string().describe("预设名（用 plot_curves_list_presets 查）"),
    sheet: z.string().optional().describe("sheet 名（缺省第一个）"),
    header_row: z
      .number()
      .int()
      .optional()
      .describe("表头所在行（1-based），缺省 1"),
  },
};

export const plotCurvesRun: ToolDef = {
  rpcMethod: "plot_curves.run",
  mcpName: "plot_curves_run",
  description:
    "按预设批量出曲线图。" +
    "返回 {written: [path], failed: [{path,error}], summary, output_dir}。" +
    "\n\n输出文件名由预设的 filename_template 决定。装配线下游用法：output_dir 传给 " +
    "anchor_run 的 curve_image_dir，让 `{{img:曲线图}}` 自动按 anchor_id 嵌入 Word。",
  inputSchema: {
    excel_path: z.string().describe("数据 Excel 绝对路径"),
    preset: z.string().describe("预设名"),
    output_dir: z
      .string()
      .optional()
      .describe("输出目录。缺省 '<excel同目录>/曲线图/'"),
    sheet: z.string().optional().describe("sheet 名"),
    header_row: z
      .number()
      .int()
      .optional()
      .describe("表头行（1-based），缺省 1"),
    preset_override: z
      .record(z.string(), z.unknown())
      .optional()
      .describe(
        "完全覆盖预设字典（编辑后的预设 JSON）。缺省用预设库里的原始预设。",
      ),
    output_format: z
      .enum(["svg", "png", "jpg", "jpeg"])
      .optional()
      .describe("临时覆盖 filename_template 的后缀；不写回预设文件。"),
    filename_prefix: z
      .string()
      .optional()
      .describe(
        "拼在每张图文件名最前的字面前缀（不参与 {id} 替换）。多批次出图时按 sheet 调本 tool，" +
          "各传 '<批次>_'（如 '2025.05.17_'）避免不同批相同标识列值互相覆盖；" +
          "报告侧 anchor_run 会按 '<批次>_<anchor_id>' 优先查找曲线图。",
      ),
  },
};

export const plotCurvesRenderPreview: ToolDef = {
  rpcMethod: "plot_curves.render_preview",
  mcpName: "plot_curves_render_preview",
  description:
    "实时预览：用 preset_dict + Excel 第 row_index 行数据渲染单张 PNG，返 base64。" +
    "返回 {png_base64, mime: 'image/png', row_id, title, total_rows}。" +
    "agent 想给用户秀一眼调参效果时用；不写文件。",
  inputSchema: {
    preset_dict: z
      .record(z.string(), z.unknown())
      .describe("预设字典（完整 plot_curves 预设结构）"),
    excel_path: z.string().describe("数据 Excel 绝对路径"),
    sheet: z.string().optional().describe("sheet 名"),
    header_row: z.number().int().optional().describe("表头行（1-based），缺省 1"),
    row_index: z
      .number()
      .int()
      .optional()
      .describe("第几行数据（0-based），越界自动回退到末尾，缺省 0"),
  },
};

export const allPlotCurvesTools: readonly ToolDef[] = [
  plotCurvesListPresets,
  plotCurvesListSheets,
  plotCurvesListHeaders,
  plotCurvesPreflight,
  plotCurvesRun,
  plotCurvesRenderPreview,
];
