/**
 * word2pdf 状态控制中心。和 pdf_tools 同思路：inputs[] 变 → 200ms debounce 拉 inspect。
 * run() 走 COM 单进程串行；结果区分 written / failed。
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
import type { ConvertRes, DocxFileInfo, InspectRes } from './types';

const INSPECT_DEBOUNCE_MS = 200;

interface State {
  inputs: string[];
  outDir: string;

  previewInfos: DocxFileInfo[];
  previewLoading: boolean;
  previewError: string | null;

  running: boolean;
  result: ConvertRes | null;
  runError: string | null;
}

interface Actions {
  addInputs: (paths: string[]) => void;
  removeAt: (i: number) => void;
  clearInputs: () => void;
  setOutDir: (p: string) => void;
  run: () => Promise<RunOutcome>;
}

/// run() 返回值：成功 / 失败 / 无操作（前置校验不过或 running 中）。
/// Page handleRun 拿这个快照而不是读 ctx state —— state 异步更新，
/// await 后读 c.result / c.runError 永远是上一次的旧值。
export type RunOutcome =
  | { kind: 'ok'; res: ConvertRes }
  | { kind: 'error'; message: string }
  | null;

type Ctx = State & Actions;

const Word2PdfContext = createContext<Ctx | null>(null);

export function useWord2Pdf(): Ctx {
  const v = useContext(Word2PdfContext);
  if (!v) throw new Error('useWord2Pdf must be used within <Word2PdfProvider>');
  return v;
}

export function Word2PdfProvider({ children }: { children: React.ReactNode }) {
  const [inputs, setInputs] = useState<string[]>([]);
  const [outDir, setOutDir] = useState('');

  const [previewInfos, setPreviewInfos] = useState<DocxFileInfo[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ConvertRes | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const addInputs = useCallback((paths: string[]) => {
    setInputs((prev) => [...prev, ...paths]);
    setResult(null);
    setRunError(null);
  }, []);
  const removeAt = useCallback((i: number) => {
    setInputs((prev) => prev.filter((_, j) => j !== i));
  }, []);
  const clearInputs = useCallback(() => {
    setInputs([]);
    setPreviewInfos([]);
    setResult(null);
    setRunError(null);
  }, []);

  // ── inspect（debounce）─────────────────────────────────
  const debounceRef = useRef<number | null>(null);
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (inputs.length === 0) {
      // 输入清空 → 同步清掉旧预览。这是与 inputs 关联的派生状态重置，
      // 移到 action 里会让 removeAt/clearInputs 重复逻辑，留在 effect 更内聚
      /* eslint-disable react-hooks/set-state-in-effect */
      setPreviewInfos([]);
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
      rpc<InspectRes>('word2pdf.inspect', { paths: inputs })
        .then((r) => {
          if (myId !== reqIdRef.current) return;
          setPreviewInfos(r.files);
        })
        .catch((e) => {
          if (myId !== reqIdRef.current) return;
          setPreviewError(String(e));
          setPreviewInfos([]);
        })
        .finally(() => {
          if (myId === reqIdRef.current) setPreviewLoading(false);
        });
    }, INSPECT_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current !== null)
        window.clearTimeout(debounceRef.current);
    };
  }, [inputs]);

  const run = useCallback(async (): Promise<RunOutcome> => {
    if (running || inputs.length === 0 || !outDir.trim()) return null;
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      const res = await rpc<ConvertRes>('word2pdf.convert', {
        inputs,
        output_dir: outDir.trim(),
      });
      setResult(res);
      return { kind: 'ok', res };
    } catch (e) {
      const message = String(e);
      setRunError(message);
      return { kind: 'error', message };
    } finally {
      setRunning(false);
    }
  }, [running, inputs, outDir]);

  const ctx: Ctx = useMemo(
    () => ({
      inputs,
      outDir,
      previewInfos,
      previewLoading,
      previewError,
      running,
      result,
      runError,
      addInputs,
      removeAt,
      clearInputs,
      setOutDir,
      run,
    }),
    [
      inputs,
      outDir,
      previewInfos,
      previewLoading,
      previewError,
      running,
      result,
      runError,
      addInputs,
      removeAt,
      clearInputs,
      run,
    ],
  );

  return (
    <Word2PdfContext.Provider value={ctx}>{children}</Word2PdfContext.Provider>
  );
}
