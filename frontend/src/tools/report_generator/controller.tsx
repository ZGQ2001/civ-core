/**
 * report_generator 状态控制中心 —— 装配线「报告填充」环节。
 *
 * 设计原则（用户拍板「方案 A：完全独立」）：
 *   1. **独立 own 全套 state**：excelPath / sheet / 规范 / 批次列 / 各批次参数 / Word 模板 /
 *      输出目录 / user_inputs —— 全部由本 controller 自己维护，不再耦合数据处理 controller。
 *   2. **可选导入**：提供 importFromDataProcessing() action，让用户一键把数据处理已填的
 *      excelPath/参数等复制过来。日常工作流（数据处理→报告填充）一次点击即可，
 *      独立工作流（拿别人 Excel 出报告）则跳过这一步直接自己填。
 *   3. **自带 list_batches**：选完 Excel 自动调 anchor.list_batches 拉批次清单，
 *      跟数据处理逻辑一样，但状态在本 controller 内 own，互不影响。
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
import { useDataProcessing } from '../data_processing/controller';
import {
  ANCHOR_DEFAULT_BATCH_COL,
  DEFAULT_ANCHOR_PARAMS,
  type AnchorParams,
  type AnchorStandard,
} from '../data_processing/types';
import type { ReportRunRes, ReportUserInputs } from './types';

/// 批次级 user_input map 的 RPC wire 类型：{ [batchId]: { [key]: value } }
/// 目前唯一批次级 key 是 grouting_date（见 types.ts BATCH_DIM_KEYS），未来加字段在此扩展。
type BatchUserInputsWire = Record<string, Record<string, string>>;

const TOOL_ID = 'report_generator';
const XLSX_EXTS = new Set(['.xlsx', '.xls']);
const DOCX_EXTS = new Set(['.docx']);

/**
 * 数据来源 —— 决定走哪条 RPC 路径：
 *   - "raw"     : 输入是原始检测数据 Excel；调 anchor.run（读 + 算 + 写结果 xlsx + 出 Word）
 *   - "result"  : 输入是数据处理已经出的结果 Excel；调 report.run_from_result
 *                 （读结果直接出 Word，不再重算、不再写新 xlsx）
 * 一键从数据处理导入时默认走 result，避免重复计算。
 */
export type ReportDataSource = 'raw' | 'result';

interface State {
  // 输入（自己 own，可独立填或一键从数据处理导入）
  excelPath: string;
  dataSource: ReportDataSource;
  /** 报告名称 —— 影响输出文件名；留空 = 默认「锚杆抗拔报告.docx」。 */
  reportName: string;
  sheet: string;
  anchorStandard: AnchorStandard;
  anchorBatchIdColumn: string;
  anchorBatchIds: string[];
  anchorBatchesLoading: boolean;
  anchorBatchesError: string | null;
  anchorParamsByBatch: Record<string, AnchorParams>;

  // 本工具自己 own
  wordTemplatePath: string;
  outputDir: string;
  /**
   * 占位图（曲线图）目录 —— 注：实际存储在 ShellContext 上跨工具共享；
   * 这里只是 expose 给 Ctx 消费者方便用。详见 lib/shell.ts curveImageDir。
   */
  curveImageDir: string;
  userInputs: ReportUserInputs;
  /// 批次级 user_input：按 batchId 存。当前仅 grouting_date。
  /// 跟着 anchorBatchIds 同步：新批次进来补空 string，旧批次离开就清掉。
  groutingDateByBatch: Record<string, string>;

  // 运行
  running: boolean;
  lastResult: ReportRunRes | null;
  runError: string | null;
}

interface Actions {
  // 输入
  setExcelPath: (p: string) => void;
  setDataSource: (s: ReportDataSource) => void;
  setReportName: (n: string) => void;
  setSheet: (s: string) => void;
  setAnchorStandard: (s: AnchorStandard) => void;
  setAnchorBatchIdColumn: (s: string) => void;
  setAnchorParamsForBatch: (batchId: string, params: AnchorParams) => void;
  setAnchorParamsForAllBatches: (params: AnchorParams) => void;

  // Word
  setWordTemplatePath: (p: string) => void;
  setOutputDir: (p: string) => void;
  setCurveImageDir: (p: string) => void;
  setUserInput: (key: string, value: string) => void;
  /** 整批替换 user_inputs —— 从报告预设载入时用；保留已填的非预设字段。 */
  loadUserInputs: (values: ReportUserInputs) => void;
  resetUserInputs: () => void;
  setGroutingDateForBatch: (batchId: string, value: string) => void;
  setGroutingDateForAllBatches: (value: string) => void;

  // 一键导入数据处理当前 state（excelPath / sheet / 规范 / 批次列 / 各批次参数）
  importFromDataProcessing: () => void;

  run: () => Promise<ReportRunRes | null>;
}

/** 数据处理上游是否有可导入 state（用来高亮"一键导入"按钮）。 */
interface UpstreamProbe {
  available: boolean;
  excelPath: string;
  batchCount: number;
  paramsFilledBatchCount: number;
  reason: string | null;
}

/** 报告生成能否开跑的就绪态 + 阻断理由（不就绪时按钮 disable + 显示 reason）。 */
interface Readiness {
  ready: boolean;
  reason: string | null;
}

type Ctx = State &
  Actions & {
    upstream: UpstreamProbe;
    readiness: Readiness;
  };

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
  // 仅用于 importFromDataProcessing()——日常 state 不依赖 dp
  const dp = useDataProcessing();

  // ── 输入 state（独立 own） ──
  const [excelPath, setExcelPathRaw] = useState('');
  const [dataSource, setDataSource] = useState<ReportDataSource>('raw');
  const [reportName, setReportName] = useState('');
  const [sheet, setSheet] = useState('');
  const [anchorStandard, setAnchorStandard] =
    useState<AnchorStandard>('GB 50086-2015');
  const [anchorBatchIdColumn, setAnchorBatchIdColumn] = useState(
    ANCHOR_DEFAULT_BATCH_COL,
  );
  const [anchorBatchIds, setAnchorBatchIds] = useState<string[]>([]);
  const [anchorBatchesLoading, setAnchorBatchesLoading] = useState(false);
  const [anchorBatchesError, setAnchorBatchesError] = useState<string | null>(
    null,
  );
  const [anchorParamsByBatch, setAnchorParamsByBatch] = useState<
    Record<string, AnchorParams>
  >({});

  // ── Word state ──
  const [wordTemplatePath, setWordTemplatePath] = useState('');
  const [outputDir, setOutputDir] = useState('');
  // plot_curves 出图目录 —— 走 ShellContext 跨工具共享（[[报告填充]] 嵌图 / [[模板助手]] 预校验
  // 用同一份），留空 = 不嵌图（模板里 {{img:曲线图}} 留原文 + 报 missingImages）
  const curveImageDir = shell.curveImageDir;
  const setCurveImageDir = shell.setCurveImageDir;
  const [userInputs, setUserInputs] = useState<ReportUserInputs>({});
  const [groutingDateByBatch, setGroutingDateByBatch] = useState<
    Record<string, string>
  >({});

  // ── 运行 state ──
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<ReportRunRes | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // 切 Excel → 清掉批次缓存（防串味）
  const setExcelPath = useCallback((p: string) => {
    setExcelPathRaw(p);
    setSheet('');
    setAnchorBatchIds([]);
    setAnchorBatchesError(null);
    setAnchorParamsByBatch({});
    setGroutingDateByBatch({});
    setLastResult(null);
    setRunError(null);
  }, []);

  const setAnchorParamsForBatch = useCallback(
    (batchId: string, params: AnchorParams) => {
      setAnchorParamsByBatch((prev) => ({ ...prev, [batchId]: params }));
    },
    [],
  );

  const setAnchorParamsForAllBatches = useCallback((params: AnchorParams) => {
    setAnchorParamsByBatch((prev) => {
      const next: Record<string, AnchorParams> = {};
      for (const b of Object.keys(prev)) next[b] = { ...params };
      return next;
    });
  }, []);

  const setUserInput = useCallback((key: string, value: string) => {
    setUserInputs((prev) => ({ ...prev, [key]: value }));
  }, []);

  /// 从预设载入：合并到当前 state（保留预设没覆盖的字段，符合「不自动清空用户输入」原则）。
  const loadUserInputs = useCallback((values: ReportUserInputs) => {
    setUserInputs((prev) => ({ ...prev, ...values }));
  }, []);

  /// 「全部清空」—— 用户主动点才清，避免误清；保留 key=空字符串方便 UI 受控。
  const resetUserInputs = useCallback(() => {
    setUserInputs({});
  }, []);

  const setGroutingDateForBatch = useCallback(
    (batchId: string, value: string) => {
      setGroutingDateByBatch((prev) => ({ ...prev, [batchId]: value }));
    },
    [],
  );

  // 「填默认」按钮：把同一日期写给所有当前已知批次（仅覆盖已存在 key）
  const setGroutingDateForAllBatches = useCallback((value: string) => {
    setGroutingDateByBatch((prev) => {
      const next: Record<string, string> = {};
      for (const b of Object.keys(prev)) next[b] = value;
      return next;
    });
  }, []);

  // ── 自动拉批次清单（excelPath/sheet/batchCol 变化时）──
  const batchReqIdRef = useRef(0);
  useEffect(() => {
    if (!excelPath) return;
    const myId = ++batchReqIdRef.current;
    /* eslint-disable react-hooks/set-state-in-effect */
    setAnchorBatchesLoading(true);
    setAnchorBatchesError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    rpc<{ batches: string[] }>('anchor.list_batches', {
      input_xlsx: excelPath,
      sheet: sheet || null,
      batch_id_column: anchorBatchIdColumn,
    })
      .then((r) => {
        if (myId !== batchReqIdRef.current) return;
        setAnchorBatchIds(r.batches);
        // 新批次补默认参数；保留已填的
        setAnchorParamsByBatch((prev) => {
          const next: Record<string, AnchorParams> = {};
          for (const b of r.batches) {
            next[b] = prev[b] ?? { ...DEFAULT_ANCHOR_PARAMS };
          }
          return next;
        });
        // 灌浆日期：新批次进来补空 string；旧批次（同 batchId）保留已填值。
        // 旧批次（这次 Excel 没出现的）直接被丢弃（构造 next 时不带过来），符合预期。
        setGroutingDateByBatch((prev) => {
          const next: Record<string, string> = {};
          for (const b of r.batches) next[b] = prev[b] ?? '';
          return next;
        });
      })
      .catch((e) => {
        if (myId !== batchReqIdRef.current) return;
        setAnchorBatchesError(String(e));
        setAnchorBatchIds([]);
      })
      .finally(() => {
        if (myId === batchReqIdRef.current) setAnchorBatchesLoading(false);
      });
  }, [excelPath, sheet, anchorBatchIdColumn]);

  // ── 探针：数据处理上游是否有可导入的 state ──
  const upstream: UpstreamProbe = useMemo(() => {
    const batchIds = dp.anchorBatchIds;
    const filled = batchIds.filter((b) => !!dp.anchorParamsByBatch[b]).length;
    let reason: string | null = null;
    if (dp.calcType !== 'anchor') reason = '数据处理 calcType 不是 anchor';
    else if (!dp.excelPath) reason = '数据处理还没选 Excel';
    else if (batchIds.length === 0) reason = '数据处理还没读到批次';
    return {
      available: reason === null,
      excelPath: dp.excelPath,
      batchCount: batchIds.length,
      paramsFilledBatchCount: filled,
      reason,
    };
  }, [dp.calcType, dp.excelPath, dp.anchorBatchIds, dp.anchorParamsByBatch]);

  const importFromDataProcessing = useCallback(() => {
    if (!upstream.available) {
      shell.appendOutput(
        logLine(`[报告] 无法从数据处理导入：${upstream.reason}`),
      );
      return;
    }
    // 一键导入默认走「结果数据」路径——数据处理已经算过一遍，没必要再算一次；
    // 解决用户反馈 #2+#7「从数据处理导入应该是结果数据」+「报告填充不应再生成结果 xlsx」。
    // 拿不到 outputPath 时退化回原始（兜底，不该常态触发）。
    const importSource: ReportDataSource =
      dp.outputPath && dp.outputPath.trim() ? 'result' : 'raw';
    const importPath =
      importSource === 'result' && dp.outputPath ? dp.outputPath : dp.excelPath;

    // 注意 setExcelPath 内部会清旧批次缓存，所以下面 set 参数要在 set Excel 之后
    setExcelPath(importPath);
    setDataSource(importSource);
    setSheet(dp.sheet);
    setAnchorStandard(dp.anchorStandard);
    setAnchorBatchIdColumn(dp.anchorBatchIdColumn);
    // 不直接复制 batchIds —— 让本地 effect 再调一次 list_batches，结果以 dp 当前 Excel 为准
    setAnchorParamsByBatch({ ...dp.anchorParamsByBatch });
    shell.appendOutput(
      logLine(
        `[报告] 已从数据处理导入: ${importPath}（${upstream.batchCount} 批，参数已填 ${upstream.paramsFilledBatchCount}/${upstream.batchCount}，数据来源=${importSource === 'result' ? '结果 xlsx' : '原始 xlsx'}）`,
      ),
    );
  }, [upstream, dp, shell, setExcelPath]);

  // ── 就绪态 ──
  const readiness: Readiness = useMemo(() => {
    if (!excelPath) return { ready: false, reason: '请选输入 Excel' };
    if (anchorBatchesLoading) return { ready: false, reason: '正在加载批次…' };
    if (anchorBatchesError)
      return { ready: false, reason: `读批次失败：${anchorBatchesError}` };
    if (anchorBatchIds.length === 0)
      return { ready: false, reason: 'Excel 里没读到任何批次（检查批次列名）' };
    const missing = anchorBatchIds.filter((b) => !anchorParamsByBatch[b]);
    if (missing.length > 0)
      return {
        ready: false,
        reason: `还有 ${missing.length}/${anchorBatchIds.length} 批次未填工程参数`,
      };
    if (!wordTemplatePath.trim())
      return {
        ready: false,
        reason: '请选 Word 模板（带 {{占位符}} + [[每根锚杆]] 锚点）',
      };
    return { ready: true, reason: null };
  }, [
    excelPath,
    anchorBatchesLoading,
    anchorBatchesError,
    anchorBatchIds,
    anchorParamsByBatch,
    wordTemplatePath,
  ]);

  // ── run ──
  const run = useCallback(async (): Promise<ReportRunRes | null> => {
    if (!readiness.ready || running) {
      if (!readiness.ready)
        shell.appendOutput(logLine(`[报告] 不能生成：${readiness.reason}`));
      return null;
    }
    setRunning(true);
    setRunError(null);
    setLastResult(null);
    shell.appendOutput(
      logLine(`[报告] 开始生成: ${excelPath} + ${wordTemplatePath}`),
    );
    try {
      // 清掉空字符串字段
      const userInputsTrimmed: Record<string, string> = {};
      for (const [k, v] of Object.entries(userInputs)) {
        if (v && v.trim()) userInputsTrimmed[k] = v;
      }

      // 批次级 user_inputs：只把有填的批次打包发过去（空值跳过，后端按缺省处理）
      const batchUserInputs: BatchUserInputsWire = {};
      for (const b of anchorBatchIds) {
        const v = (groutingDateByBatch[b] ?? '').trim();
        if (v) batchUserInputs[b] = { grouting_date: v };
      }

      const params: Record<string, unknown> = {
        input_xlsx: excelPath,
        standard: anchorStandard,
        batch_id_column: anchorBatchIdColumn,
        params_by_batch: anchorParamsByBatch,
        word_template_path: wordTemplatePath.trim(),
        user_inputs: userInputsTrimmed,
      };
      if (sheet) params.sheet = sheet;
      if (outputDir.trim()) params.word_output_dir = outputDir.trim();
      if (curveImageDir.trim()) params.curve_image_dir = curveImageDir.trim();
      if (reportName.trim()) params.report_name = reportName.trim();
      if (Object.keys(batchUserInputs).length > 0)
        params.batch_user_inputs = batchUserInputs;

      const res = await rpc<{
        batches: number;
        anchors_total: number;
        anchors_qualified: number;
        output: string;
        word_outputs?: string[];
        word_unknown_keys?: string[];
        word_missing_images?: string[];
      }>('anchor.run', params);

      if (!res.word_outputs || res.word_outputs.length === 0) {
        throw new Error('后端没返回 word_outputs —— 模板替换可能跳过了');
      }
      const wordOut = res.word_outputs[0];
      const display: ReportRunRes = {
        output: wordOut,
        rowsRendered: res.anchors_total,
        unknownKeys: res.word_unknown_keys ?? [],
        missingImages: res.word_missing_images ?? [],
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
    readiness,
    running,
    excelPath,
    sheet,
    anchorStandard,
    anchorBatchIdColumn,
    anchorBatchIds,
    anchorParamsByBatch,
    groutingDateByBatch,
    wordTemplatePath,
    outputDir,
    curveImageDir,
    userInputs,
    reportName,
    shell,
  ]);

  // ── 文件树双击：.xlsx 设输入；.docx 设 Word 模板 ──
  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (XLSX_EXTS.has(ext)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExcelPath(f.path);
      shell.appendOutput(logLine(`[报告] 已接收输入 Excel: ${f.path}`));
    } else if (DOCX_EXTS.has(ext)) {
      setWordTemplatePath(f.path);
      shell.appendOutput(logLine(`[报告] 已接收 Word 模板: ${f.path}`));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  const ctx: Ctx = useMemo(
    () => ({
      excelPath,
      dataSource,
      reportName,
      sheet,
      anchorStandard,
      anchorBatchIdColumn,
      anchorBatchIds,
      anchorBatchesLoading,
      anchorBatchesError,
      anchorParamsByBatch,
      wordTemplatePath,
      outputDir,
      curveImageDir,
      userInputs,
      groutingDateByBatch,
      running,
      lastResult,
      runError,
      upstream,
      readiness,
      setExcelPath,
      setDataSource,
      setReportName,
      setSheet,
      setAnchorStandard,
      setAnchorBatchIdColumn,
      setAnchorParamsForBatch,
      setAnchorParamsForAllBatches,
      setWordTemplatePath,
      setOutputDir,
      setCurveImageDir,
      setUserInput,
      loadUserInputs,
      resetUserInputs,
      setGroutingDateForBatch,
      setGroutingDateForAllBatches,
      importFromDataProcessing,
      run,
    }),
    [
      excelPath,
      dataSource,
      reportName,
      sheet,
      anchorStandard,
      anchorBatchIdColumn,
      anchorBatchIds,
      anchorBatchesLoading,
      anchorBatchesError,
      anchorParamsByBatch,
      wordTemplatePath,
      outputDir,
      curveImageDir,
      setCurveImageDir,
      userInputs,
      groutingDateByBatch,
      running,
      lastResult,
      runError,
      upstream,
      readiness,
      setExcelPath,
      setAnchorParamsForBatch,
      setAnchorParamsForAllBatches,
      setUserInput,
      loadUserInputs,
      resetUserInputs,
      setGroutingDateForBatch,
      setGroutingDateForAllBatches,
      importFromDataProcessing,
      run,
    ],
  );

  return (
    <ReportGeneratorContext.Provider value={ctx}>
      {children}
    </ReportGeneratorContext.Provider>
  );
}
