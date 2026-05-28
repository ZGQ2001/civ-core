import { describe, expect, it } from "vitest";
import { SidecarRouter } from "../src/router.js";

describe("SidecarRouter.isPythonMethod", () => {
  it("把 ping / version / plot_curves.* 路由到 Python", () => {
    expect(SidecarRouter.isPythonMethod("ping")).toBe(true);
    expect(SidecarRouter.isPythonMethod("version")).toBe(true);
    expect(SidecarRouter.isPythonMethod("plot_curves.run")).toBe(true);
    expect(SidecarRouter.isPythonMethod("plot_curves.list_presets")).toBe(true);
    expect(SidecarRouter.isPythonMethod("plot_curves.render_preview")).toBe(true);
  });

  it("其余全部默认到 C#（含 T5.7 切过去的 workspace/files/pdf_tools/word2pdf）", () => {
    // 装配线
    expect(SidecarRouter.isPythonMethod("anchor.run")).toBe(false);
    expect(SidecarRouter.isPythonMethod("anchor.list_batches")).toBe(false);
    expect(SidecarRouter.isPythonMethod("anchor.generate_template")).toBe(false);
    expect(SidecarRouter.isPythonMethod("leeb.run")).toBe(false);
    expect(SidecarRouter.isPythonMethod("leeb.preview_excel")).toBe(false);
    expect(SidecarRouter.isPythonMethod("xlsx.write_leeb_report_table")).toBe(false);
    expect(SidecarRouter.isPythonMethod("template.fields")).toBe(false);
    expect(SidecarRouter.isPythonMethod("report.render_placeholder")).toBe(false);

    // 工作区上下文 + 文件操作（T5.7 全切 C#）
    expect(SidecarRouter.isPythonMethod("workspace.last")).toBe(false);
    expect(SidecarRouter.isPythonMethod("workspace.create_standard")).toBe(false);
    expect(SidecarRouter.isPythonMethod("files.list_dir")).toBe(false);
    expect(SidecarRouter.isPythonMethod("files.delete")).toBe(false);
    expect(SidecarRouter.isPythonMethod("pdf_tools.merge")).toBe(false);
    expect(SidecarRouter.isPythonMethod("pdf_tools.inspect")).toBe(false);
    expect(SidecarRouter.isPythonMethod("word2pdf.convert")).toBe(false);
    expect(SidecarRouter.isPythonMethod("word2pdf.inspect")).toBe(false);
    expect(SidecarRouter.isPythonMethod("doc.ping")).toBe(false);
    expect(SidecarRouter.isPythonMethod("doc.version")).toBe(false);

    // 未来扩展（不用改路由）
    expect(SidecarRouter.isPythonMethod("calc.core_drilling.run")).toBe(false);
    expect(SidecarRouter.isPythonMethod("calc.rebound.run")).toBe(false);
  });

  it("`plot_curves`（无 .）不算 plot_curves 前缀", () => {
    // 防御 startsWith 误伤——前缀必须严格带 `.`
    expect(SidecarRouter.isPythonMethod("plot_curves")).toBe(false);
  });
});
