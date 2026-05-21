/**
 * leeb_hardness 右侧 RightPanel「调参」tab：输出路径 + 默认测量角度。
 * 运行按钮 + 结果显示在 Page 顶部 / 底部（保持和 plot_curves 一致：主操作在主区）。
 */
import { useCallback } from "react";
import { save as saveDialog } from "@tauri-apps/plugin-dialog";

import { Field, Picker, ResetBtn } from "../_shared/forms";
import { useLeeb } from "./controller";

export function LeebHardnessSettingsForm() {
  const c = useLeeb();

  const pickOutput = useCallback(async () => {
    const sel = await saveDialog({
      title: "保存结果 Excel 为",
      defaultPath: c.defaultOutput || undefined,
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
    });
    if (typeof sel === "string") c.setOutputPath(sel);
  }, [c]);

  return (
    <div className="flex flex-col h-full text-xs overflow-auto p-4 space-y-4">
      <Field label="输出 Excel 路径" hint="留空 = <输入同级>/<stem>_结果.xlsx">
        <Picker
          value={c.outputPath || c.defaultOutput}
          onPick={pickOutput}
          placeholder="（选 Excel 后自动）"
          muted={!c.outputPath}
          extra={
            c.outputPath ? <ResetBtn onClick={() => c.setOutputPath("")} /> : undefined
          }
        />
      </Field>

      <Field label="默认测量角度（度）" hint="构件未指定角度时用此值；常用 0 / 90 / 180">
        <input
          type="number"
          value={c.angle}
          onChange={(e) => c.setAngle(parseFloat(e.target.value || "0"))}
          className="w-32 bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
        />
      </Field>

      <div className="pt-2 text-[11px] text-vscode-text-faint">
        选好 Excel 后点工具页顶部「开始计算」即可；结果会显示在工具页底部。
      </div>
    </div>
  );
}
