/**
 * pdf_tools.* —— PDF 合并 / 拆分 / 检视（C# sidecar，PDFsharp 原子写）。
 *
 * 入参 schema 跟 dotnet/civ-doc/Handlers/PdfToolsHandlers.cs 一一对照。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const pdfToolsMerge: ToolDef = {
  rpcMethod: "pdf_tools.merge",
  mcpName: "pdf_tools_merge",
  description:
    "按 inputs 顺序合并多个 PDF 成一个。返回 {output, count}。" +
    "原子写——中途失败不会留半截文件。",
  inputSchema: {
    inputs: z
      .array(z.string())
      .describe("待合并的 PDF 绝对路径数组（按数组顺序拼接）"),
    output: z.string().describe("输出 PDF 绝对路径（所在目录须已存在）"),
  },
};

export const pdfToolsSplitPerPage: ToolDef = {
  rpcMethod: "pdf_tools.split_per_page",
  mcpName: "pdf_tools_split_per_page",
  description:
    "把一个 PDF 按页拆成多个单页 PDF。返回 {written: [path], count}。",
  inputSchema: {
    input: z.string().describe("源 PDF 绝对路径"),
    output_dir: z.string().describe("输出目录绝对路径"),
    name_template: z
      .string()
      .optional()
      .describe(
        "文件名模板，缺省 '{stem}_p{n}.pdf'（{stem}=源文件名去扩展，{n}=零填充页码）",
      ),
  },
};

export const pdfToolsSplitByRanges: ToolDef = {
  rpcMethod: "pdf_tools.split_by_ranges",
  mcpName: "pdf_tools_split_by_ranges",
  description:
    "把一个 PDF 按页码范围表达式拆分。返回 {written: [path], count}。",
  inputSchema: {
    input: z.string().describe("源 PDF 绝对路径"),
    output_dir: z.string().describe("输出目录绝对路径"),
    expr: z
      .string()
      .describe("范围表达式，逗号分隔、连字符表区间，如 '1-3,5,7-9'（1-based）"),
    name_template: z
      .string()
      .optional()
      .describe(
        "文件名模板，缺省 '{stem}_{start}-{end}.pdf'（{start}/{end}=该段起止页）",
      ),
  },
};

export const pdfToolsInspect: ToolDef = {
  rpcMethod: "pdf_tools.inspect",
  mcpName: "pdf_tools_inspect",
  description:
    "检视一批 PDF 的页数和大小。返回 {files: [{path, size_kb, pages?, error?}], total_pages}。" +
    "单个文件失败（不存在/损坏）只在该项标 error，不影响整体。",
  inputSchema: {
    paths: z.array(z.string()).describe("待检视的 PDF 绝对路径数组"),
  },
};

export const allPdfToolsTools: readonly ToolDef[] = [
  pdfToolsMerge,
  pdfToolsSplitPerPage,
  pdfToolsSplitByRanges,
  pdfToolsInspect,
];
