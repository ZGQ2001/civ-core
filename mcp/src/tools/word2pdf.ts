/**
 * word2pdf.* —— Word(docx) → PDF 批量转换 + docx 体量检视。
 *
 * 入参 schema 跟 dotnet/civ-doc/Handlers/Word2PdfHandlers.cs 一一对照。
 * 平台说明：convert 仅 Windows（走 Word/WPS COM 保排版精度，非 Windows 抛
 * PlatformNotSupported）；inspect 跨平台（OpenXML SDK 读 docProps）。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const word2pdfConvert: ToolDef = {
  rpcMethod: "word2pdf.convert",
  mcpName: "word2pdf_convert",
  description:
    "批量把 docx 转 PDF。返回 {written: [path], failed: [{path, error}], total}。" +
    "\n\n⚠️ 仅 Windows——走 Word/WPS COM 保 100% 排版还原（检测报告对甲方模板精度要求高，" +
    "不用 LibreOffice 这类会掉 ~5% 精度的降级方案）。非 Windows 调用会报 PlatformNotSupported。" +
    "装配线下游用法：anchor_run 出的 Word 报告交付前转 PDF。",
  inputSchema: {
    inputs: z.array(z.string()).describe("待转换的 docx 绝对路径数组"),
    output_dir: z.string().describe("PDF 输出目录绝对路径"),
  },
};

export const word2pdfInspect: ToolDef = {
  rpcMethod: "word2pdf.inspect",
  mcpName: "word2pdf_inspect",
  description:
    "检视一批 docx 的大小 / 段落数 / 页数。返回 {files: [{path, size_kb?, paragraphs?, pages?, error?}]}。" +
    "跨平台（OpenXML SDK）。注：pages 取自 docProps，仅在 Word 保存过的 docx 里有；" +
    "程序新生成未经 Word 打开的 docx 可能没有该字段。",
  inputSchema: {
    paths: z.array(z.string()).describe("待检视的 docx 绝对路径数组"),
  },
};

export const allWord2PdfTools: readonly ToolDef[] = [
  word2pdfConvert,
  word2pdfInspect,
];
