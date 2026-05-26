/**
 * report_generator 状态控制中心 —— 装配线「报告填充」环节。
 *
 * 设计要点：
 *   1. **复用上游数据**：从 useDataProcessing() 拿 excelPath / sheet / standard /
 *      batchCol / params —— 用户在数据处理已填的工程参数不再重填一次。
 *   2. **本工具自己 own 的**：Word 模板路径、输出目录、24 个项目级 user_input。
 *   3. **run() 调 anchor.run**：把上游 state + 本工具 state 拼成完整参数，
 *      让 anchor.run 同时出 Excel + Word 报告（带 word_template_path）。
 *      Excel 会被覆写到同样路径——通常跟数据处理的输出一致，等价于"重算一遍 + 出 Word"。
 *
 * 流程图：
 *   ┌─── data_processing ──────────────┐
 *   │  excelPath / params / batches    │ ──┐
 *   └──────────────────────────────────┘   │
 *                                          ▼
 *   ┌─── report_generator ─────────────┐
 *   │  + wordTemplatePath              │
 *   │  + outputDir                     │ ─→ anchor.run + word_template_path ─→ docx
 *   │  + 24 个 user_inputs             │
 *   └──────────────────────────────────┘
 */
/* eslint-disable react-refresh/only-export-components -- hook 与 Provider 同文件共存，是工具页范式（见 frontend/CLAUDE.md） */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { rpc } from '../../lib/rpc';
import { logLine, useShell } from '../../lib/shell';
import { useDataProcessing } from '../data_processing/controller';
import type { ReportRunRes, ReportUserInputs } from './types';
import { DEFAULT_REPORT_USER_INPUTS } from './types';

const TOOL_ID = 'report_generator';
const ACCEPTED_EXTS = new Set(['.docx']);

interface State {
  wordTemplatePath: string;
  outputDir: string;
  userInputs: ReportUserInputs;
  running: boolean;
  lastResult: ReportRunRes | null;
  runError: string | null;
}

interface Actions {
  setWordTemplatePath: (p: string) => void;
  setOutputDir: (p: string) => void;
  setUserInput: (key: keyof ReportUserInputs, value: string) => void;
  resetUserInputs: () => void;
  run: () => Promise<ReportRunRes | null>;
}

interface UpstreamSummary {
  excelPath: string;
  sheet: string;
  standard: string;
  batchCol: string;
  batchCount: number;
  paramsFilledBatchCount: number;
  ready: boolean;
  blockReason: string | null;
}

type Ctx = State & Actions & { upstream: UpstreamSummary };

const ReportGeneratorContext = createContext<Ctx | null>(null);

export function useReportGenerator(): Ctx {
  const v = useContext(ReportGeneratorContext);
  if (!v)
    throw new Error(
      'useReportGenerator must be used within <ReportGeneratorProvider>',
    );
  return v;
}

export function ReportGeneratorProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const shell = useShell();
  const dp = useDataProcessing();

  const [wordTemplatePath, setWordTemplatePath] = useState('');
  const [outputDir, setOutputDir] = useState('');
  const [userInputs, setUserInputs] = useState<ReportUserInputs>({
    ...DEFAULT_REPORT_USER_INPUTS,
  });
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<ReportRunRes | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const setUserInput = useCallback(
    (key: keyof ReportUserInputs, value: string) => {
      setUserInputs((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const resetUserInputs = useCallback(() => {
    setUserInputs({ ...DEFAULT_REPORT_USER_INPUTS });
  }, []);

  /** 从上游 data_processing 汇总「能否生成报告」的状态。任何 block 必须给清晰理由。 */
  const upstream: UpstreamSummary = useMemo(() => {
    const excelPath = dp.excelPath;
    const batchIds = dp.anchorBatchIds;
    const filled = batchIds.filter((b) => !!dp.anchorParamsByBatch[b]).length;
    let blockReason: string | null = null;
    if (dp.calcType !== 'anchor') {
      blockReason = '当前数据处理的 calcType 不是 anchor —— 只支持锚杆抗拔报告生成';
    } else if (!excelPath) {
      blockReason = '上游数据处理还没选输入 Excel';
    } else if (dp.anchorBatchesLoading) {
      blockReason = '上游正在读批次清单…';
    } else if (dp.anchorBatchesError) {
      blockReason = `上游读批次失败：${dp.anchorBatchesError}`;
    } else if (batchIds.length === 0) {
      blockReason = '上游 Excel 里没读到任何批次';
    } else if (filled < batchIds.length) {
      blockReason = `上游还有 ${batchIds.length - filled} / ${batchIds.length} 批次未填工程参数`;
    } else if (!wordTemplatePath.trim()) {
      blockReason = '请先选 Word 模板（.docx 带 {{占位符}} + [[每根锚杆]] 锚点）';
    }
    return {
      excelPath,
      sheet: dp.sheet,
      standard: dp.anchorStandard,
      batchCol: dp.anchorBatchIdColumn,
      batchCount: batchIds.length,
      paramsFilledBatchCount: filled,
      ready: blockReason === null,
      blockReason,
    };
  }, [
    dp.excelPath,
    dp.sheet,
    dp.anchorBatchIds,
    dp.anchorBatchesLoading,
    dp.anchorBatchesError,
    dp.anchorParamsByBatch,
    dp.anchorStandard,
    dp.anchorBatchIdColumn,
    dp.calcType,
    wordTemplatePath,
  ]);

  const run = useCallback(async (): Promise<ReportRunRes | null> => {
    if (!upstream.ready || running) {
      if (!upstream.ready)
        shell.appendOutput(logLine(`[报告] 不能生成：${upstream.blockReason}`));
      return null;
    }

    setRunning(true);
    setRunError(null);
    setLastResult(null);
    shell.appendOutput(
      logLine(`[报告] 开始生成: ${upstream.excelPath} + ${wordTemplatePath}`),
    );

    try {
      // 清掉空字符串字段（避免给后端发一堆空 user_input；catalog 命中后空值会显示为空）
      const userInputsTrimmed: Record<string, string> = {};
      for (const [k, v] of Object.entries(userInputs)) {
        if (v && v.trim()) userInputsTrimmed[k] = v;
      }

      const params: Record<string, unknown> = {
        input_xlsx: upstream.excelPath,
        standard: upstream.standard,
        batch_id_column: upstream.batchCol,
        params_by_batch: dp.anchorParamsByBatch,
        word_template_path: wordTemplatePath.trim(),
        user_inputs: userInputsTrimmed,
      };
      if (upstream.sheet) params.sheet = upstream.sheet;
      if (outputDir.trim()) params.word_output_dir = outputDir.trim();

      const res = await rpc<{
        batches: number;
        anchors_total: number;
        anchors_qualified: number;
        output: string;
        word_outputs?: string[];
      }>('anchor.run', params);

      if (!res.word_outputs || res.word_outputs.length === 0) {
        throw new Error('后端没返回 word_outputs —— 模板替换可能跳过了');
      }
      const wordOut = res.word_outputs[0];
      // 当前 anchor.run 没回 unknownKeys / rowsRendered；先用 anchors_total 当 rowsRendered
      const display: ReportRunRes = {
        output: wordOut,
        rowsRendered: res.anchors_total,
        unknownKeys: [],
      };
      setLastResult(display);
      shell.appendOutput(
        logLine(`[报告] 完成: ${display.rowsRendered} 根 → ${wordOut}`),
      );
      shell.notifyFilesChanged();
      return display;
    } catch (e) {
      const message = String(e);
      setRunError(message);
      shell.appendOutput(logLine(`[报告] 失败: ${message}`));
      return null;
    } finally {
      setRunning(false);
    }
  }, [
    upstream,
    running,
    userInputs,
    dp.anchorParamsByBatch,
    wordTemplatePath,
    outputDir,
    shell,
  ]);

  // ── 文件树双击 .docx 联动：自动设为 Word 模板路径 ──
  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (!ACCEPTED_EXTS.has(ext)) return;
    // 外部事件（文件树双击）→ 必须在 effect 里把 path 灌进 state
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setWordTemplatePath(f.path);
    shell.appendOutput(logLine(`[报告] 已接收 Word 模板: ${f.path}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  const ctx: Ctx = useMemo(
    () => ({
      wordTemplatePath,
      outputDir,
      userInputs,
      running,
      lastResult,
      runError,
      upstream,
      setWordTemplatePath,
      setOutputDir,
      setUserInput,
      resetUserInputs,
      run,
    }),
    [
      wordTemplatePath,
      outputDir,
      userInputs,
      running,
      lastResult,
      runError,
      upstream,
      setUserInput,
      resetUserInputs,
      run,
    ],
  );

  return (
    <ReportGeneratorContext.Provider value={ctx}>
      {children}
    </ReportGeneratorContext.Provider>
  );
}
