/**
 * PDF 工具页：合并 / 按页拆 / 按范围拆。
 * 三个 Tab 切换不同操作；都走 pdf_tools.* RPC。
 */
import { useCallback, useState } from "react";
import { open as openDialog, save as saveDialog } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../lib/cn";
import { rpc } from "../lib/rpc";
import { Field, Picker, RunBtn } from "./_shared/forms";

type Mode = "merge" | "split_per_page" | "split_by_ranges";

interface Props {
  appendOutput?: (text: string) => void;
}

export function PdfToolsTool({ appendOutput }: Props = {}) {
  const [mode, setMode] = useState<Mode>("merge");

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="px-6 pt-5 pb-3 border-b border-vscode-border">
        <h1 className="text-lg font-medium text-vscode-text flex items-center gap-2">
          <i className="codicon codicon-file-pdf !text-[18px]" />
          PDF 工具
        </h1>
        <div className="mt-3 flex gap-1">
          <ModeTab label="合并" active={mode === "merge"} onClick={() => setMode("merge")} />
          <ModeTab
            label="按页拆分"
            active={mode === "split_per_page"}
            onClick={() => setMode("split_per_page")}
          />
          <ModeTab
            label="按范围拆分"
            active={mode === "split_by_ranges"}
            onClick={() => setMode("split_by_ranges")}
          />
        </div>
      </div>
      <div className="px-6 py-4 max-w-3xl">
        {mode === "merge" && <MergePane appendOutput={appendOutput} />}
        {mode === "split_per_page" && <SplitPerPagePane appendOutput={appendOutput} />}
        {mode === "split_by_ranges" && <SplitByRangesPane appendOutput={appendOutput} />}
      </div>
    </div>
  );
}

function ModeTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-3 py-1 text-xs rounded-[2px] border",
        active
          ? "bg-vscode-selected border-vscode-focus text-white"
          : "bg-transparent border-vscode-border text-vscode-text-dim hover:text-white hover:bg-vscode-hover",
      )}
    >
      {label}
    </button>
  );
}

// ── 合并 ──────────────────────────────────────────────
function MergePane({ appendOutput }: { appendOutput?: (s: string) => void }) {
  const [inputs, setInputs] = useState<string[]>([]);
  const [output, setOutput] = useState("");
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addPdfs = useCallback(async () => {
    const sel = await openDialog({
      title: "选择要合并的 PDF（可多选）",
      multiple: true,
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (Array.isArray(sel)) setInputs((prev) => [...prev, ...sel]);
    else if (typeof sel === "string") setInputs((prev) => [...prev, sel]);
  }, []);

  const removeAt = (i: number) => setInputs((prev) => prev.filter((_, j) => j !== i));
  const moveUp = (i: number) =>
    setInputs((prev) => {
      if (i === 0) return prev;
      const next = [...prev];
      [next[i - 1], next[i]] = [next[i], next[i - 1]];
      return next;
    });
  const moveDown = (i: number) =>
    setInputs((prev) => {
      if (i === prev.length - 1) return prev;
      const next = [...prev];
      [next[i + 1], next[i]] = [next[i], next[i + 1]];
      return next;
    });

  const pickOutput = useCallback(async () => {
    const sel = await saveDialog({
      title: "保存合并 PDF 为",
      defaultPath: "合并.pdf",
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (typeof sel === "string") setOutput(sel);
  }, []);

  const canRun = inputs.length >= 1 && !!output && !running;
  const handleRun = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    setDone(null);
    try {
      const res = await rpc<{ output: string; count: number }>("pdf_tools.merge", {
        inputs,
        output,
      });
      setDone(res.output);
      appendOutput?.(
        `[${new Date().toLocaleTimeString()}] pdf merge: ${res.count} 个 → ${res.output}`,
      );
    } catch (e) {
      setError(String(e));
      appendOutput?.(`[${new Date().toLocaleTimeString()}] pdf merge 失败: ${String(e)}`);
    } finally {
      setRunning(false);
    }
  }, [canRun, inputs, output, appendOutput]);

  return (
    <div className="space-y-4">
      <Field label={`输入 PDF 列表（${inputs.length} 个，按顺序合并）`}>
        <div className="space-y-1">
          {inputs.map((p, i) => (
            <div
              key={`${p}_${i}`}
              className="flex items-center gap-1 bg-vscode-input border border-vscode-border rounded-[2px] px-2 py-1 text-xs"
            >
              <span className="w-5 text-vscode-text-dim text-right">{i + 1}.</span>
              <span className="flex-1 truncate" title={p}>{p}</span>
              <IconBtn icon="chevron-up" onClick={() => moveUp(i)} title="上移" />
              <IconBtn icon="chevron-down" onClick={() => moveDown(i)} title="下移" />
              <IconBtn icon="close" onClick={() => removeAt(i)} title="移除" />
            </div>
          ))}
          <button
            type="button"
            onClick={addPdfs}
            className="px-2 py-1 text-xs bg-[#2d2d2d] hover:bg-[#3a3a3a] border border-vscode-border rounded-[2px] flex items-center gap-1"
          >
            <i className="codicon codicon-add !text-[12px]" /> 添加 PDF…
          </button>
        </div>
      </Field>
      <Field label="输出 PDF">
        <Picker value={output} onPick={pickOutput} placeholder="尚未选择" />
      </Field>
      <div className="pt-2">
        <RunBtn running={running} disabled={!canRun} onClick={handleRun}>
          {running ? "正在合并…" : "开始合并"}
        </RunBtn>
      </div>
      {error && <ErrorBox text={error} />}
      {done && <DoneBox label="合并完成" path={done} />}
    </div>
  );
}

// ── 按页拆 ────────────────────────────────────────────
function SplitPerPagePane({ appendOutput }: { appendOutput?: (s: string) => void }) {
  return (
    <SplitPaneBase
      title="把每页拆成单独 PDF"
      method="pdf_tools.split_per_page"
      defaultTemplate="{stem}_p{n}.pdf"
      templateHint="占位：{stem}=源文件名 {n}=页号（自动补零）"
      logLabel="split_per_page"
      appendOutput={appendOutput}
    />
  );
}

// ── 按范围拆 ──────────────────────────────────────────
function SplitByRangesPane({ appendOutput }: { appendOutput?: (s: string) => void }) {
  return (
    <SplitPaneBase
      title="按范围拆"
      method="pdf_tools.split_by_ranges"
      defaultTemplate="{stem}_{start}-{end}.pdf"
      templateHint="占位：{stem}=源文件名 {start} {end}=该段起止页号"
      logLabel="split_by_ranges"
      withExpr
      appendOutput={appendOutput}
    />
  );
}

function SplitPaneBase({
  title,
  method,
  defaultTemplate,
  templateHint,
  logLabel,
  withExpr,
  appendOutput,
}: {
  title: string;
  method: string;
  defaultTemplate: string;
  templateHint: string;
  logLabel: string;
  withExpr?: boolean;
  appendOutput?: (s: string) => void;
}) {
  const [input, setInput] = useState("");
  const [outDir, setOutDir] = useState("");
  const [template, setTemplate] = useState(defaultTemplate);
  const [expr, setExpr] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ written: string[]; count: number } | null>(null);

  const pickInput = useCallback(async () => {
    const sel = await openDialog({
      title: "选择 PDF",
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (typeof sel === "string") setInput(sel);
  }, []);

  const pickOutDir = useCallback(async () => {
    const sel = await openDialog({ title: "选择输出目录", directory: true });
    if (typeof sel === "string") setOutDir(sel);
  }, []);

  const canRun = !!input && !!outDir && (!withExpr || !!expr.trim()) && !running;

  const handleRun = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    setDone(null);
    try {
      const params: Record<string, unknown> = {
        input,
        output_dir: outDir,
        name_template: template,
      };
      if (withExpr) params.expr = expr.trim();
      const res = await rpc<{ written: string[]; count: number }>(method, params);
      setDone(res);
      appendOutput?.(
        `[${new Date().toLocaleTimeString()}] pdf ${logLabel}: ${res.count} 个 → ${outDir}`,
      );
    } catch (e) {
      setError(String(e));
      appendOutput?.(`[${new Date().toLocaleTimeString()}] pdf ${logLabel} 失败: ${String(e)}`);
    } finally {
      setRunning(false);
    }
  }, [canRun, input, outDir, template, expr, withExpr, method, logLabel, appendOutput]);

  return (
    <div className="space-y-4">
      <div className="text-xs text-vscode-text-dim">{title}</div>
      <Field label="输入 PDF">
        <Picker value={input} onPick={pickInput} placeholder="尚未选择" />
      </Field>
      <Field label="输出目录">
        <Picker value={outDir} onPick={pickOutDir} placeholder="尚未选择" />
      </Field>
      {withExpr && (
        <Field
          label="页号范围表达式"
          hint='例如 "1-3,5,7-9"：拆出 3 个文件分别覆盖这些页'
        >
          <input
            type="text"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
            placeholder="1-3,5,7-9"
            className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
          />
        </Field>
      )}
      <Field label="输出文件名模板" hint={templateHint}>
        <input
          type="text"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          className="w-full bg-vscode-input border border-vscode-border px-2 py-1 text-xs text-vscode-text rounded-[2px]"
        />
      </Field>
      <div className="pt-2">
        <RunBtn running={running} disabled={!canRun} onClick={handleRun}>
          {running ? "正在拆分…" : "开始拆分"}
        </RunBtn>
      </div>
      {error && <ErrorBox text={error} />}
      {done && (
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2 text-sm text-green-400">
            <i className="codicon codicon-pass !text-[16px]" />
            拆出 {done.count} 个文件
          </div>
          <details>
            <summary className="cursor-pointer text-vscode-text-dim hover:text-white">
              查看清单
            </summary>
            <ul className="mt-1 ml-4 space-y-0.5">
              {done.written.map((p) => (
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
        </div>
      )}
    </div>
  );
}

// ── 共用小组件 ────────────────────────────────────────
function IconBtn({
  icon,
  onClick,
  title,
}: {
  icon: string;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="h-5 w-5 flex items-center justify-center rounded text-vscode-text-dim hover:bg-vscode-hover hover:text-white"
    >
      <i className={`codicon codicon-${icon} !text-[12px]`} />
    </button>
  );
}

function ErrorBox({ text }: { text: string }) {
  return (
    <div className="text-xs text-red-400 whitespace-pre-wrap">
      <i className="codicon codicon-error !text-[14px] mr-1" />
      {text}
    </div>
  );
}

function DoneBox({ label, path }: { label: string; path: string }) {
  return (
    <div className="text-xs flex items-center gap-2">
      <i className="codicon codicon-pass !text-[14px] text-green-400" />
      <span className="text-green-400">{label}：</span>
      <button
        type="button"
        onClick={() => openPath(path).catch(console.error)}
        className="text-vscode-focus hover:underline truncate"
      >
        {path}
      </button>
    </div>
  );
}
