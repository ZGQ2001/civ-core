/**
 * Word → PDF 工具页。
 * 选多个 .docx → 选输出目录 → 跑（底层走 COM/WPS 单进程批量）→ 显示 written/failed。
 */
import { useCallback, useState } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { rpc } from "../lib/rpc";
import { Field, Picker, RunBtn } from "./LeebHardnessTool";

interface ConvertRes {
  written: string[];
  failed: { path: string; error: string }[];
  total: number;
}

interface Props {
  appendOutput?: (text: string) => void;
}

export function Word2PdfTool({ appendOutput }: Props = {}) {
  const [inputs, setInputs] = useState<string[]>([]);
  const [outDir, setOutDir] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ConvertRes | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addDocs = useCallback(async () => {
    const sel = await openDialog({
      title: "选择 Word 文件（可多选）",
      multiple: true,
      filters: [{ name: "Word", extensions: ["docx", "doc"] }],
    });
    if (Array.isArray(sel)) setInputs((prev) => [...prev, ...sel]);
    else if (typeof sel === "string") setInputs((prev) => [...prev, sel]);
  }, []);

  const removeAt = (i: number) => setInputs((prev) => prev.filter((_, j) => j !== i));

  const pickOutDir = useCallback(async () => {
    const sel = await openDialog({ title: "选择输出目录", directory: true });
    if (typeof sel === "string") setOutDir(sel);
  }, []);

  const canRun = inputs.length >= 1 && !!outDir && !running;

  const handleRun = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await rpc<ConvertRes>("word2pdf.convert", {
        inputs,
        output_dir: outDir,
      });
      setResult(res);
      appendOutput?.(
        `[${new Date().toLocaleTimeString()}] word2pdf: 成功 ${res.written.length} / 失败 ${res.failed.length} (共 ${res.total})`,
      );
    } catch (e) {
      setError(String(e));
      appendOutput?.(`[${new Date().toLocaleTimeString()}] word2pdf 失败: ${String(e)}`);
    } finally {
      setRunning(false);
    }
  }, [canRun, inputs, outDir, appendOutput]);

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="px-6 pt-5 pb-3 border-b border-vscode-border">
        <h1 className="text-lg font-medium text-vscode-text flex items-center gap-2">
          <i className="codicon codicon-file-binary !text-[18px]" />
          Word → PDF 批量转换
        </h1>
        <p className="mt-1 text-xs text-vscode-text-dim">
          走 COM 单进程跑完所有文件（要求安装 Microsoft Word 或 WPS）。
        </p>
      </div>

      <div className="px-6 py-4 space-y-4 max-w-3xl">
        <Field label={`Word 文件列表（${inputs.length} 个）`}>
          <div className="space-y-1">
            {inputs.map((p, i) => (
              <div
                key={`${p}_${i}`}
                className="flex items-center gap-1 bg-vscode-input border border-vscode-border rounded-[2px] px-2 py-1 text-xs"
              >
                <span className="w-5 text-vscode-text-dim text-right">{i + 1}.</span>
                <span className="flex-1 truncate" title={p}>{p}</span>
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  title="移除"
                  className="h-5 w-5 flex items-center justify-center rounded text-vscode-text-dim hover:bg-vscode-hover hover:text-white"
                >
                  <i className="codicon codicon-close !text-[12px]" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={addDocs}
              className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1"
            >
              <i className="codicon codicon-add !text-[12px]" /> 添加 Word…
            </button>
          </div>
        </Field>

        <Field label="输出目录">
          <Picker value={outDir} onPick={pickOutDir} placeholder="尚未选择" />
        </Field>

        <div className="pt-2">
          <RunBtn running={running} disabled={!canRun} onClick={handleRun}>
            {running ? "正在转换…" : "开始转换"}
          </RunBtn>
        </div>
      </div>

      {(result || error) && (
        <div className="px-6 py-4 border-t border-vscode-border max-w-3xl space-y-3">
          {error && (
            <div className="text-xs text-red-400 whitespace-pre-wrap">
              <i className="codicon codicon-error !text-[14px] mr-1" />
              {error}
            </div>
          )}
          {result && (
            <>
              <div className="flex items-center gap-2 text-sm">
                <i
                  className={`codicon !text-[16px] ${
                    result.failed.length === 0
                      ? "codicon-pass text-green-400"
                      : "codicon-warning text-yellow-400"
                  }`}
                />
                <span className={result.failed.length === 0 ? "text-green-400" : "text-yellow-400"}>
                  {result.failed.length === 0 ? "全部成功" : "部分失败"}
                </span>
                <span className="text-vscode-text-dim text-xs">
                  成功 {result.written.length} / 失败 {result.failed.length} / 共 {result.total}
                </span>
              </div>
              {result.written.length > 0 && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-vscode-text-dim hover:text-white">
                    成功 {result.written.length} 个
                  </summary>
                  <ul className="mt-1 ml-4 space-y-0.5">
                    {result.written.map((p) => (
                      <li key={p}>
                        <button
                          type="button"
                          onClick={() => openPath(p).catch(console.error)}
                          className="text-vscode-focus hover:underline truncate text-left"
                        >
                          {p.split(/[\\/]/).pop()}
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {result.failed.length > 0 && (
                <details className="text-xs" open>
                  <summary className="cursor-pointer text-red-400">
                    失败 {result.failed.length} 个
                  </summary>
                  <ul className="mt-1 ml-4 space-y-1">
                    {result.failed.map((f) => (
                      <li key={f.path} className="text-vscode-text-dim">
                        <div className="truncate" title={f.path}>{f.path.split(/[\\/]/).pop()}</div>
                        <div className="text-red-400 ml-2">{f.error}</div>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
