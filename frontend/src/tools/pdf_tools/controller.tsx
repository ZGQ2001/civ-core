/**
 * pdf_tools 状态控制中心：三个 mode（合并 / 按页拆 / 按范围拆）共享 state。
 *
 * 切 mode 不清 state — 用户可能在 merge / split 间来回切换，保留各自输入。
 * preview（每个 PDF 的页数 + 大小）：
 *   - merge: 用 mergeInputs 拉 inspect → previewInfos（多个）
 *   - split_*: 用 splitInput 拉 inspect → previewInfos（单个数组）
 *
 * 设计选择：previewInfos 始终是数组，split 模式数组长度 1。让 Page 渲染统一。
 */
/* eslint-disable react-refresh/only-export-components -- hook 与 Provider 同文件共存，是工具页范式（见 frontend/CLAUDE.md） */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { rpc } from '../../lib/rpc';
import { logLine, useShell } from '../../lib/shell';
import type {
  InspectRes,
  MergeRes,
  Mode,
  PdfFileInfo,
  SplitRes,
} from './types';

const TOOL_ID = 'pdf_tools';
const ACCEPTED_EXTS = new Set(['.pdf']);

const INSPECT_DEBOUNCE_MS = 200;

interface State {
  mode: Mode;

  // merge 专用
  mergeInputs: string[];
  mergeOutput: string;
  mergeResult: MergeRes | null;

  // split_per_page / split_by_ranges 共用
  splitInput: string;
  splitOutDir: string;
  splitTemplate: string;
  splitExpr: string;
  splitResult: SplitRes | null;

  // 通用预览
  previewInfos: PdfFileInfo[];
  previewTotalPages: number;
  previewLoading: boolean;
  previewError: string | null;

  // 运行
  running: boolean;
  runError: string | null;
}

interface Actions {
  setMode: (m: Mode) => void;

  addMergeInputs: (paths: string[]) => void;
  removeMergeAt: (i: number) => void;
  moveMergeUp: (i: number) => void;
  moveMergeDown: (i: number) => void;
  setMergeOutput: (p: string) => void;

  setSplitInput: (p: string) => void;
  setSplitOutDir: (p: string) => void;
  setSplitTemplate: (s: string) => void;
  setSplitExpr: (s: string) => void;

  run: () => Promise<RunOutcome>;
}

/// run() 返回值：mode 不同结果类型不同，让 Page handleRun 拿快照而不是读
/// ctx state（state 更新异步，await 后读 c.mergeResult 永远是旧值）。
export type RunOutcome =
  | { kind: 'merge'; res: MergeRes }
  | { kind: 'split'; res: SplitRes }
  | { kind: 'error'; message: string }
  | null;

type Ctx = State & Actions & { defaultTemplate: string };

const DEFAULT_TEMPLATE: Record<Mode, string> = {
  merge: '', // merge 不用 template
  split_per_page: '{stem}_p{n}.pdf',
  split_by_ranges: '{stem}_{start}-{end}.pdf',
};

const PdfToolsContext = createContext<Ctx | null>(null);

export function usePdfTools(): Ctx {
  const v = useContext(PdfToolsContext);
  if (!v) throw new Error('usePdfTools must be used within <PdfToolsProvider>');
  return v;
}

export function PdfToolsProvider({ children }: { children: React.ReactNode }) {
  const shell = useShell();
  const [mode, setModeRaw] = useState<Mode>('merge');
  // 文件树双击 effect 里读 mode 不能用闭包（deps 只有 activatedFile.key），用 ref
  const modeRef = useRef<Mode>('merge');
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  const [mergeInputs, setMergeInputs] = useState<string[]>([]);
  const [mergeOutput, setMergeOutput] = useState('');
  const [mergeResult, setMergeResult] = useState<MergeRes | null>(null);

  const [splitInput, setSplitInputRaw] = useState('');
  const [splitOutDir, setSplitOutDir] = useState('');
  const [splitTemplate, setSplitTemplate] = useState<string>(
    DEFAULT_TEMPLATE.split_per_page,
  );
  const [splitExpr, setSplitExpr] = useState('');
  const [splitResult, setSplitResult] = useState<SplitRes | null>(null);

  const [previewInfos, setPreviewInfos] = useState<PdfFileInfo[]>([]);
  const [previewTotalPages, setPreviewTotalPages] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // 切 mode 时清结果 + 切默认模板（如果用户没改过的话简单逻辑：直接覆盖）
  const setMode = useCallback((m: Mode) => {
    setModeRaw(m);
    setMergeResult(null);
    setSplitResult(null);
    setRunError(null);
    if (m !== 'merge') {
      setSplitTemplate(DEFAULT_TEMPLATE[m]);
    }
  }, []);

  const addMergeInputs = useCallback((paths: string[]) => {
    setMergeInputs((prev) => [...prev, ...paths]);
  }, []);
  const removeMergeAt = useCallback(
    (i: number) => setMergeInputs((prev) => prev.filter((_, j) => j !== i)),
    [],
  );
  const moveMergeUp = useCallback(
    (i: number) =>
      setMergeInputs((prev) => {
        if (i === 0) return prev;
        const next = [...prev];
        [next[i - 1], next[i]] = [next[i], next[i - 1]];
        return next;
      }),
    [],
  );
  const moveMergeDown = useCallback(
    (i: number) =>
      setMergeInputs((prev) => {
        if (i === prev.length - 1) return prev;
        const next = [...prev];
        [next[i + 1], next[i]] = [next[i], next[i + 1]];
        return next;
      }),
    [],
  );

  const setSplitInput = useCallback((p: string) => {
    setSplitInputRaw(p);
    setSplitResult(null);
    setRunError(null);
  }, []);

  // 当前 mode 关注的 path 列表（用于 inspect）
  const inspectTargets = useMemo<string[]>(() => {
    if (mode === 'merge') return mergeInputs;
    return splitInput ? [splitInput] : [];
  }, [mode, mergeInputs, splitInput]);

  // ── 拉 inspect（debounce）─────────────────────────────────
  const debounceRef = useRef<number | null>(null);
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (inspectTargets.length === 0) {
      // 输入清空 → 同步清掉旧预览。与 inspectTargets 派生绑定，留 effect 内
      /* eslint-disable react-hooks/set-state-in-effect */
      setPreviewInfos([]);
      setPreviewTotalPages(0);
      setPreviewError(null);
      setPreviewLoading(false);
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      const myId = ++reqIdRef.current;
      setPreviewLoading(true);
      setPreviewError(null);
      rpc<InspectRes>('pdf_tools.inspect', { paths: inspectTargets })
        .then((r) => {
          if (myId !== reqIdRef.current) return;
          setPreviewInfos(r.files);
          setPreviewTotalPages(r.total_pages);
        })
        .catch((e) => {
          if (myId !== reqIdRef.current) return;
          setPreviewError(String(e));
          setPreviewInfos([]);
          setPreviewTotalPages(0);
        })
        .finally(() => {
          if (myId === reqIdRef.current) setPreviewLoading(false);
        });
    }, INSPECT_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current !== null)
        window.clearTimeout(debounceRef.current);
    };
  }, [inspectTargets]);

  // ── 文件树双击 .pdf 联动：merge 追加（去重），split 覆盖 ──
  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (!ACCEPTED_EXTS.has(ext)) return;
    // 外部事件灌 state — 必须留在 effect 里

    if (modeRef.current === 'merge') {
      setMergeInputs((prev) =>
        prev.includes(f.path) ? prev : [...prev, f.path],
      );
      shell.appendOutput(logLine(`[PDF 工具] 已接收文件: ${f.path}`));
    } else {
      setSplitInputRaw(f.path);
      setSplitResult(null);
      setRunError(null);
      shell.appendOutput(logLine(`[PDF 工具] 已接收文件: ${f.path}`));
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  const run = useCallback(async (): Promise<RunOutcome> => {
    if (running) return null;
    setRunning(true);
    setRunError(null);
    setMergeResult(null);
    setSplitResult(null);
    try {
      if (mode === 'merge') {
        if (mergeInputs.length === 0 || !mergeOutput.trim()) {
          throw new Error('缺少输入或输出路径');
        }
        const res = await rpc<MergeRes>('pdf_tools.merge', {
          inputs: mergeInputs,
          output: mergeOutput.trim(),
        });
        setMergeResult(res);
        return { kind: 'merge', res };
      } else {
        if (!splitInput || !splitOutDir.trim()) {
          throw new Error('缺少输入文件或输出目录');
        }
        if (mode === 'split_by_ranges' && !splitExpr.trim()) {
          throw new Error('缺少页号范围表达式（例如 "1-3,5,7-9"）');
        }
        const params: Record<string, unknown> = {
          input: splitInput,
          output_dir: splitOutDir.trim(),
          name_template: splitTemplate.trim() || DEFAULT_TEMPLATE[mode],
        };
        if (mode === 'split_by_ranges') params.expr = splitExpr.trim();
        const res = await rpc<SplitRes>(`pdf_tools.${mode}`, params);
        setSplitResult(res);
        return { kind: 'split', res };
      }
    } catch (e) {
      const message = String(e);
      setRunError(message);
      return { kind: 'error', message };
    } finally {
      setRunning(false);
    }
  }, [
    mode,
    running,
    mergeInputs,
    mergeOutput,
    splitInput,
    splitOutDir,
    splitTemplate,
    splitExpr,
  ]);

  const defaultTemplate = mode === 'merge' ? '' : DEFAULT_TEMPLATE[mode];

  const ctx: Ctx = useMemo(
    () => ({
      mode,
      mergeInputs,
      mergeOutput,
      mergeResult,
      splitInput,
      splitOutDir,
      splitTemplate,
      splitExpr,
      splitResult,
      previewInfos,
      previewTotalPages,
      previewLoading,
      previewError,
      running,
      runError,
      defaultTemplate,
      setMode,
      addMergeInputs,
      removeMergeAt,
      moveMergeUp,
      moveMergeDown,
      setMergeOutput,
      setSplitInput,
      setSplitOutDir,
      setSplitTemplate,
      setSplitExpr,
      run,
    }),
    [
      mode,
      mergeInputs,
      mergeOutput,
      mergeResult,
      splitInput,
      splitOutDir,
      splitTemplate,
      splitExpr,
      splitResult,
      previewInfos,
      previewTotalPages,
      previewLoading,
      previewError,
      running,
      runError,
      defaultTemplate,
      setMode,
      addMergeInputs,
      removeMergeAt,
      moveMergeUp,
      moveMergeDown,
      setSplitInput,
      run,
    ],
  );

  return (
    <PdfToolsContext.Provider value={ctx}>{children}</PdfToolsContext.Provider>
  );
}
