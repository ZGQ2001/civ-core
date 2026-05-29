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
import { anchorRunResultSchema } from '../../lib/rpcSchemas';
import { logLine, useShell } from '../../lib/shell';
import {
  ANCHOR_DEFAULT_BATCH_COL,
  DEFAULT_ANCHOR_PARAMS,
  type AnchorParams,
  type AnchorStandard,
} from '../data_processing/types';
import type { ValidateResult } from '../template_helper/types';
import type { ReportRunRes, ReportUserInputs } from './types';
import { DEFAULT_CATALOG_ID } from './types';

/** 报告按锚杆展开必需的重复锚点 —— 与 C# ReportGenerator.DefaultPerRowStartMarker 对齐。 */
const REQUIRED_PER_ROW_MARKER = '[[每根锚杆]]';

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
  /**
   * 检测项目（catalog id）—— 决定字段定义、预设过滤范围、未来 calc 分发。
   * 用户从下拉切换；不同检测项目（锚杆 / 钻芯 / 回弹）字段定义完全独立。
   * 当前只有 anchor 一种 calc 真正落地；切到其他 catalog 仅影响 UI 字段渲染，
   * 跑报告时仍走 anchor.run（直到钻芯/回弹切 C#）。
   */
  catalogId: string;
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

  // 模板体检 —— 选完 Word 模板自动跑 template.validate（复用模板助手同一 RPC），
  // 在「生成」之前就把缺锚点 / 层级错 / 未识别占位符摆出来，不等生成失败才发现。
  templateCheck: ValidateResult | null;
  templateChecking: boolean;
  templateCheckError: string | null;
}

interface Actions {
  // 输入
  setExcelPath: (p: string) => void;
  setDataSource: (s: ReportDataSource) => void;
  setReportName: (n: string) => void;
  setCatalogId: (id: string) => void;
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
  // 数据处理快照（仅「一键导入」探针 + 导入用）走 ShellContext，不再直接 useDataProcessing。
  // → report 不依赖 DataProcessingProvider 的嵌套顺序，可独立挂载/测试（见 frontend/CLAUDE.md 工具间耦合原则）。
  const dpSnapshot = shell.dataProcessingSnapshot;

  // ── 输入 state（独立 own） ──
  const [excelPath, setExcelPathRaw] = useState('');
  const [dataSource, setDataSource] = useState<ReportDataSource>('raw');
  const [reportName, setReportName] = useState('');
  const [catalogId, setCatalogId] = useState<string>(DEFAULT_CATALOG_ID);
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

  // ── 模板体检 state ──
  const [templateCheck, setTemplateCheck] = useState<ValidateResult | null>(
    null,
  );
  const [templateChecking, setTemplateChecking] = useState(false);
  const [templateCheckError, setTemplateCheckError] = useState<string | null>(
    null,
  );

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

  // ── 自动体检模板（选/换 Word 模板 或 切检测项目时跑 template.validate）──
  // 复用模板助手同一 RPC（上下游共用一份校验逻辑），把问题前置到「生成」之前。
  const templateCheckReqRef = useRef(0);
  useEffect(() => {
    const path = wordTemplatePath.trim();
    if (!path) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setTemplateCheck(null);
      setTemplateChecking(false);
      setTemplateCheckError(null);
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }
    const myId = ++templateCheckReqRef.current;

    setTemplateChecking(true);
    setTemplateCheckError(null);

    rpc<ValidateResult>('template.validate', {
      docx_path: path,
      catalog_id: catalogId,
    })
      .then((r) => {
        if (myId !== templateCheckReqRef.current) return;
        setTemplateCheck(r);
      })
      .catch((e) => {
        if (myId !== templateCheckReqRef.current) return;
        setTemplateCheck(null);
        setTemplateCheckError(String(e));
      })
      .finally(() => {
        if (myId === templateCheckReqRef.current) setTemplateChecking(false);
      });
  }, [wordTemplatePath, catalogId]);

  // ── 探针：数据处理上游是否有可导入的 state ──
  const upstream: UpstreamProbe = useMemo(() => {
    if (!dpSnapshot) {
      return {
        available: false,
        excelPath: '',
        batchCount: 0,
        paramsFilledBatchCount: 0,
        reason: '数据处理还没产生可导入数据',
      };
    }
    const batchIds = dpSnapshot.anchorBatchIds;
    const filled = batchIds.filter(
      (b) => !!dpSnapshot.anchorParamsByBatch[b],
    ).length;
    let reason: string | null = null;
    if (dpSnapshot.calcType !== 'anchor')
      reason = '数据处理 calcType 不是 anchor';
    else if (!dpSnapshot.excelPath) reason = '数据处理还没选 Excel';
    else if (batchIds.length === 0) reason = '数据处理还没读到批次';
    return {
      available: reason === null,
      excelPath: dpSnapshot.excelPath,
      batchCount: batchIds.length,
      paramsFilledBatchCount: filled,
      reason,
    };
  }, [dpSnapshot]);

  const importFromDataProcessing = useCallback(() => {
    if (!upstream.available || !dpSnapshot) {
      shell.appendOutput(
        logLine(`[报告] 无法从数据处理导入：${upstream.reason}`),
      );
      return;
    }
    // 一键导入默认走「结果数据」路径——数据处理已经算过一遍，没必要再算一次；
    // 解决用户反馈 #2+#7「从数据处理导入应该是结果数据」+「报告填充不应再生成结果 xlsx」。
    // 拿不到 outputPath 时退化回原始（兜底，不该常态触发）。
    const importSource: ReportDataSource =
      dpSnapshot.outputPath && dpSnapshot.outputPath.trim() ? 'result' : 'raw';
    const importPath =
      importSource === 'result' && dpSnapshot.outputPath
        ? dpSnapshot.outputPath
        : dpSnapshot.excelPath;

    // 注意 setExcelPath 内部会清旧批次缓存，所以下面 set 参数要在 set Excel 之后
    setExcelPath(importPath);
    setDataSource(importSource);
    setSheet(dpSnapshot.sheet);
    setAnchorStandard(dpSnapshot.anchorStandard);
    setAnchorBatchIdColumn(dpSnapshot.anchorBatchIdColumn);
    // 不直接复制 batchIds —— 让本地 effect 再调一次 list_batches，结果以当前 Excel 为准
    setAnchorParamsByBatch({ ...dpSnapshot.anchorParamsByBatch });
    shell.appendOutput(
      logLine(
        `[报告] 已从数据处理导入: ${importPath}（${upstream.batchCount} 批，参数已填 ${upstream.paramsFilledBatchCount}/${upstream.batchCount}，数据来源=${importSource === 'result' ? '结果 xlsx' : '原始 xlsx'}）`,
      ),
    );
  }, [upstream, dpSnapshot, shell, setExcelPath]);

  // ── 就绪态 ──
  // dataSource=result 时不再要求填批次参数（结果 xlsx 隐藏 metadata 已带工程参数）；
  // 也不阻塞 anchor.list_batches 失败的情况，因为 result 路径不依赖批次列名。
  const readiness: Readiness = useMemo(() => {
    if (!excelPath) return { ready: false, reason: '请选输入 Excel' };
    if (dataSource === 'raw') {
      if (anchorBatchesLoading)
        return { ready: false, reason: '正在加载批次…' };
      if (anchorBatchesError)
        return { ready: false, reason: `读批次失败：${anchorBatchesError}` };
      if (anchorBatchIds.length === 0)
        return {
          ready: false,
          reason: 'Excel 里没读到任何批次（检查批次列名）',
        };
      const missing = anchorBatchIds.filter((b) => !anchorParamsByBatch[b]);
      if (missing.length > 0)
        return {
          ready: false,
          reason: `还有 ${missing.length}/${anchorBatchIds.length} 批次未填工程参数`,
        };
    }
    if (!wordTemplatePath.trim())
      return {
        ready: false,
        reason: '请选 Word 模板（带 {{占位符}} + [[每根锚杆]] 锚点）',
      };
    // 模板体检：已确认模板缺 [[每根锚杆]] 重复锚点 → 报告必然无法按锚杆展开，前置拦截。
    // （生成始终走 anchor 路径、必需此锚点；体检还在跑 / 失败时 fail-open，交后端兜底报错）
    if (
      templateCheck &&
      !templateCheck.markers.some(
        (m) => m.type === 'open' && m.text === REQUIRED_PER_ROW_MARKER,
      )
    )
      return {
        ready: false,
        reason:
          '模板缺 [[每根锚杆]] 重复锚点 —— 报告无法按锚杆展开（见下方「模板体检」，可一键复制锚点段）',
      };
    return { ready: true, reason: null };
  }, [
    excelPath,
    dataSource,
    anchorBatchesLoading,
    anchorBatchesError,
    anchorBatchIds,
    anchorParamsByBatch,
    wordTemplatePath,
    templateCheck,
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

      // dataSource 分支：
      //   raw    → 走 anchor.run（完整链路：读原始 → 算 → 写结果 xlsx → 出 Word）
      //   result → 走 report.run_from_result（读结果 xlsx 直接出 Word，不重算 / 不写新 xlsx）
      // 解决用户反馈 #2+#7「报告填充不应再重算 / 应消费结果文件」。
      const method =
        dataSource === 'result' ? 'report.run_from_result' : 'anchor.run';

      const params: Record<string, unknown> = {
        standard: anchorStandard,
        word_template_path: wordTemplatePath.trim(),
        user_inputs: userInputsTrimmed,
      };
      if (dataSource === 'result') {
        params.result_xlsx = excelPath;
      } else {
        params.input_xlsx = excelPath;
        params.batch_id_column = anchorBatchIdColumn;
        params.params_by_batch = anchorParamsByBatch;
        if (sheet) params.sheet = sheet;
      }
      if (outputDir.trim()) params.word_output_dir = outputDir.trim();
      if (curveImageDir.trim()) params.curve_image_dir = curveImageDir.trim();
      if (reportName.trim()) params.report_name = reportName.trim();
      if (Object.keys(batchUserInputs).length > 0)
        params.batch_user_inputs = batchUserInputs;

      const res = await rpc(method, params, anchorRunResultSchema);

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
    dataSource,
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
      catalogId,
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
      templateCheck,
      templateChecking,
      templateCheckError,
      upstream,
      readiness,
      setExcelPath,
      setDataSource,
      setReportName,
      setCatalogId,
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
      catalogId,
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
      templateCheck,
      templateChecking,
      templateCheckError,
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
