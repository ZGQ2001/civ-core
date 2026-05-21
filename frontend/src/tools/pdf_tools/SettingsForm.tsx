/**
 * pdf_tools 右侧 RightPanel「调参」tab：按 mode 切对应参数。
 *   - merge: 输出 PDF 路径
 *   - split_per_page: 输出目录 + 文件名模板
 *   - split_by_ranges: 输出目录 + 文件名模板 + 页号范围表达式
 */
import { useCallback } from "react";
import { open as openDialog, save as saveDialog } from "@tauri-apps/plugin-dialog";

import { Field, Picker } from "../_shared/forms";
import { usePdfTools } from "./controller";

export function PdfToolsSettingsForm() {
  const c = usePdfTools();

  const pickMergeOutput = useCallback(async () => {
    const sel = await saveDialog({
      title: "保存合并 PDF 为",
      defaultPath: "合并.pdf",
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (typeof sel === "string") c.setMergeOutput(sel);
  }, [c]);

  const pickSplitOutDir = useCallback(async () => {
    const sel = await openDialog({ title: "选择输出目录", directory: true });
    if (typeof sel === "string") c.setSplitOutDir(sel);
  }, [c]);

  return (
    <div className="flex flex-col h-full text-xs overflow-auto p-4 space-y-4">
      {c.mode === "merge" && (
        <Field label="输出 PDF 路径" hint="按上方文件顺序合并到此文件">
          <Picker value={c.mergeOutput} onPick={pickMergeOutput} placeholder="尚未选择" />
        </Field>
      )}

      {c.mode !== "merge" && (
        <>
          <Field label="输出目录">
            <Picker value={c.splitOutDir} onPick={pickSplitOutDir} placeholder="尚未选择" />
          </Field>

          {c.mode === "split_by_ranges" && (
            <Field
              label="页号范围表达式"
              hint='例如 "1-3,5,7-9"：拆出 3 个文件分别覆盖这些页'
            >
              <input
                type="text"
                value={c.splitExpr}
                onChange={(e) => c.setSplitExpr(e.target.value)}
                placeholder="1-3,5,7-9"
                className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
              />
            </Field>
          )}

          <Field
            label="输出文件名模板"
            hint={
              c.mode === "split_per_page"
                ? "占位：{stem}=源文件名 {n}=页号（自动补零）"
                : "占位：{stem}=源文件名 {start} {end}=该段起止页号"
            }
          >
            <input
              type="text"
              value={c.splitTemplate}
              onChange={(e) => c.setSplitTemplate(e.target.value)}
              placeholder={c.defaultTemplate}
              className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
            />
          </Field>
        </>
      )}

      <div className="pt-2 text-[11px] text-vscode-text-faint">
        选好文件后点工具页顶部「开始{c.mode === "merge" ? "合并" : "拆分"}」即可。
      </div>
    </div>
  );
}
