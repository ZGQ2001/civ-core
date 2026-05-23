/**
 * data_processing 状态控制中心。整合「读 Excel → 走某种检测算法 → 写结果 Excel」流程。
 *
 * calcType: 计算类型 dropdown 切换；当前 leeb / anchor，run() 内按 calcType 分支调对应 RPC。
 *
 * preview 走 leeb.preview_excel 通用读 Excel 前 N 行（headers/rows/total/sheets）；
 * 这个方法和 calcType 无关，未来可改成 io.preview_xlsx 之类的中性命名，暂沿用。
 *
 * anchor 独有：
 *   - 选完 Excel + 切到 anchor 时自动调 anchor.list_batches 拉批次清单
 *   - 用户在 SettingsForm 按批次填工程参数 (P/Lf/La/A/E)
 *   - generateTemplate() 调 anchor.generate_template 写空白模板让用户下载填
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
} from "react";

import { rpc } from "../../lib/rpc";
import { logLine, useShell } from "../../lib/shell";
import type {
  AnchorParams,
  AnchorStandard,
  CalcType,
  CellValue,
  PreviewRes,
  RunRes,
} from "./types";
import { ANCHOR_DEFAULT_BATCH_COL, DEFAULT_ANCHOR_PARAMS } from "./types";

const TOOL_ID = "data_processing";
/** 本工具可接收的文件扩展名（文件树双击时由 useShell 自动灌进来）。 */
const ACCEPTED_EXTS = new Set([".xlsx", ".xls"]);

const PREVIEW_DEBOUNCE_MS = 300;
const PREVIEW_MAX_ROWS = 50;

interface State {
  calcType: CalcType;

  // 用户参数（通用）
  excelPath: string;
  sheet: string;
  headerRow: number;
  angle: number;             // leeb 默认测量角度
  outputPath: string;

  // 表格预览
  sheets: string[];
  previewHeaders: string[];
  previewRows: Record<string, CellValue>[];
  previewTotalRows: number;
  previewShownRows: number;
  previewLoading: boolean;
  previewError: string | null;

  // 运行
  running: boolean;
  result: RunRes | null;
  runError: string | null;

  // anchor 专属
  anchorStandard: AnchorStandard;
  anchorBatchIdColumn: string;
  anchorBatchIds: string[];
  anchorBatchesLoading: boolean;
  anchorBatchesError: string | null;
  anchorParamsByBatch: Record<string, AnchorParams>;
}

interface Actions {
  setCalcType: (t: CalcType) => void;
  setExcelPath: (p: string) => void;
  setSheet: (s: string) => void;
  setHeaderRow: (n: number) => void;
  setAngle: (n: number) => void;
  setOutputPath: (s: string) => void;
  run: () => Promise<RunRes | null>;

  // anchor
  setAnchorStandard: (s: AnchorStandard) => void;
  setAnchorBatchIdColumn: (s: string) => void;
  setAnchorParamsForBatch: (batchId: string, params: AnchorParams) => void;
  setAnchorParamsForAllBatches: (params: AnchorParams) => void;
  generateAnchorTemplate: (outputPath: string) => Promise<string | null>;
}

/** 模板生成结果（按钮下方反馈用）。 */
export type TemplateStatus =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; path: string }
  | { kind: "error"; message: string };

type Ctx = State & Actions & {
  defaultOutput: string;
  anchorTemplateStatus: TemplateStatus;
};

const DataProcessingContext = createContext<Ctx | null>(null);

export function useDataProcessing(): Ctx {
  const v = useContext(DataProcessingContext);
  if (!v) throw new Error("useDataProcessing must be used within <DataProcessingProvider>");
  return v;
}

export function DataProcessingProvider({ children }: { children: React.ReactNode }) {
  const shell = useShell();
  const [calcType, setCalcTypeRaw] = useState<CalcType>("leeb");

  const [excelPath, setExcelPathRaw] = useState("");
  const [sheet, setSheet] = useState("");
  const [headerRow, setHeaderRow] = useState(1);
  const [angle, setAngle] = useState(0);
  const [outputPath, setOutputPath] = useState("");

  const [sheets, setSheets] = useState<string[]>([]);
  const [previewHeaders, setPreviewHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<Record<string, CellValue>[]>([]);
  const [previewTotalRows, setPreviewTotalRows] = useState(0);
  const [previewShownRows, setPreviewShownRows] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunRes | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // anchor 专属 state
  const [anchorStandard, setAnchorStandard] = useState<AnchorStandard>("GB 50086-2015");
  const [anchorBatchIdColumn, setAnchorBatchIdColumn] = useState(ANCHOR_DEFAULT_BATCH_COL);
  const [anchorBatchIds, setAnchorBatchIds] = useState<string[]>([]);
  const [anchorBatchesLoading, setAnchorBatchesLoading] = useState(false);
  const [anchorBatchesError, setAnchorBatchesError] = useState<string | null>(null);
  const [anchorParamsByBatch, setAnchorParamsByBatch] =
    useState<Record<string, AnchorParams>>({});
  const [anchorTemplateStatus, setAnchorTemplateStatus] =
    useState<TemplateStatus>({ kind: "idle" });

  // 切 Excel → 清掉旧预览 + 清 sheet 选择 + 清结果 + 清批次
  const setExcelPath = useCallback((p: string) => {
    setExcelPathRaw(p);
    setSheet("");
    setSheets([]);
    setPreviewHeaders([]);
    setPreviewRows([]);
    setPreviewError(null);
    setResult(null);
    setRunError(null);
    setAnchorBatchIds([]);
    setAnchorBatchesError(null);
    setAnchorParamsByBatch({});
  }, []);

  const setCalcType = useCallback((t: CalcType) => {
    setCalcTypeRaw(t);
    setResult(null);
    setRunError(null);
  }, []);

  // 默认输出：<excel 同级>/<stem>_<类型>_结果.xlsx
  const defaultOutput = useMemo(() => {
    if (!excelPath) return "";
    const sep = excelPath.includes("\\") ? "\\" : "/";
    const idx = excelPath.lastIndexOf(sep);
    const dir = idx > 0 ? excelPath.slice(0, idx) : "";
    const file = idx > 0 ? excelPath.slice(idx + 1) : excelPath;
    const stem = file.replace(/\.[^.]+$/, "");
    const tag = calcType === "anchor" ? "锚杆" : "里氏";
    return `${dir}${sep}${stem}_${tag}_结果.xlsx`;
  }, [excelPath, calcType]);

  // ── 预览（debounce）─────────────────────────────────────
  const debounceRef = useRef<number | null>(null);
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (!excelPath) {
      // excelPath 清空 → 关掉残留的 loading
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPreviewLoading(false);
      return;
    }
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      const myId = ++reqIdRef.current;
      setPreviewLoading(true);
      setPreviewError(null);
      rpc<PreviewRes>("leeb.preview_excel", {
        path: excelPath,
        sheet: sheet || null,
        header_row: headerRow,
        max_rows: PREVIEW_MAX_ROWS,
      })
        .then((r) => {
          if (myId !== reqIdRef.current) return;
          setSheets(r.sheets);
          setPreviewHeaders(r.headers);
          setPreviewRows(r.rows);
          setPreviewTotalRows(r.total_rows);
          setPreviewShownRows(r.shown_rows);
          if (r.sheet && r.sheet !== sheet) setSheet(r.sheet);
        })
        .catch((e) => {
          if (myId !== reqIdRef.current) return;
          setPreviewError(String(e));
          setPreviewHeaders([]);
          setPreviewRows([]);
          setPreviewTotalRows(0);
          setPreviewShownRows(0);
        })
        .finally(() => {
          if (myId === reqIdRef.current) setPreviewLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current);
    };
  }, [excelPath, sheet, headerRow]);

  // ── anchor 批次清单（calcType=anchor 时按 excelPath/sheet/列名 变化拉）──
  const batchReqIdRef = useRef(0);
  useEffect(() => {
    if (calcType !== "anchor" || !excelPath) return;
    const myId = ++batchReqIdRef.current;
    // 拉批次清单前先翻 loading flag — 异步 IO 的标准前置
    /* eslint-disable react-hooks/set-state-in-effect */
    setAnchorBatchesLoading(true);
    setAnchorBatchesError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    rpc<{ batches: string[] }>("anchor.list_batches", {
      input_xlsx: excelPath,
      sheet: sheet || null,
      batch_id_column: anchorBatchIdColumn,
    })
      .then((r) => {
        if (myId !== batchReqIdRef.current) return;
        setAnchorBatchIds(r.batches);
        // 为新批次填默认参数；保留已填的
        setAnchorParamsByBatch((prev) => {
          const next: Record<string, AnchorParams> = {};
          for (const b of r.batches) {
            next[b] = prev[b] ?? { ...DEFAULT_ANCHOR_PARAMS };
          }
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
  }, [calcType, excelPath, sheet, anchorBatchIdColumn]);

  const setAnchorParamsForBatch = useCallback(
    (batchId: string, params: AnchorParams) => {
      setAnchorParamsByBatch((prev) => ({ ...prev, [batchId]: params }));
    }, []);

  const setAnchorParamsForAllBatches = useCallback((params: AnchorParams) => {
    setAnchorParamsByBatch((prev) => {
      const next: Record<string, AnchorParams> = {};
      for (const b of Object.keys(prev)) next[b] = { ...params };
      return next;
    });
  }, []);

  const generateAnchorTemplate = useCallback(
    async (savePath: string): Promise<string | null> => {
      setAnchorTemplateStatus({ kind: "running" });
      shell.appendOutput(logLine(`[锚杆] 生成模板 → ${savePath}`));
      try {
        const r = await rpc<{ ok: boolean; path: string }>("anchor.generate_template", {
          output_xlsx: savePath,
          standard: anchorStandard,
        });
        setAnchorTemplateStatus({ kind: "ok", path: r.path });
        shell.appendOutput(logLine(`[锚杆] 模板已生成: ${r.path}`));
        return r.path;
      } catch (e) {
        const message = String(e);
        console.error("anchor.generate_template 失败:", e);
        setAnchorTemplateStatus({ kind: "error", message });
        shell.appendOutput(logLine(`[锚杆] 生成模板失败: ${message}`));
        return null;
      }
    }, [anchorStandard, shell]);

  const run = useCallback(async (): Promise<RunRes | null> => {
    if (!excelPath || running) return null;
    setRunning(true);
    setRunError(null);
    setResult(null);
    const label = calcType === "anchor" ? "锚杆" : "里氏";
    shell.appendOutput(logLine(`[${label}] 开始计算: ${excelPath}`));
    try {
      if (calcType === "leeb") {
        const params: Record<string, unknown> = {
          input_xlsx: excelPath,
          angle_degrees: angle,
        };
        if (outputPath.trim()) params.output_xlsx = outputPath.trim();

        const res = await rpc<{
          batches: number;
          components: number;
          output: string;
          report_table_data: Array<{
            sheet_name: string;
            components: Array<{
              name: string;
              thickness_mm: number;
              test_areas_raw: number[][];
              comp_fb_min_avg: number;
            }>;
            batch_fb_char_avg: number;
          }>;
        }>("leeb.run", params);

        if (res.report_table_data && res.report_table_data.length > 0) {
          await rpc("xlsx.write_leeb_report_table", {
            output_path: res.output,
            batches: res.report_table_data,
          });
        }

        const display: RunRes = {
          calcType: "leeb",
          output: res.output,
          summary: `${res.batches} 批 / ${res.components} 构件`,
        };
        setResult(display);
        shell.appendOutput(logLine(`[里氏] 完成: ${display.summary} → ${display.output}`));
        return display;
      }

      // anchor
      const params: Record<string, unknown> = {
        input_xlsx: excelPath,
        standard: anchorStandard,
        batch_id_column: anchorBatchIdColumn,
        params_by_batch: anchorParamsByBatch,
      };
      if (sheet) params.sheet = sheet;
      if (outputPath.trim()) params.output_xlsx = outputPath.trim();

      const res = await rpc<{
        batches: number;
        anchors_total: number;
        anchors_qualified: number;
        output: string;
      }>("anchor.run", params);

      const display: RunRes = {
        calcType: "anchor",
        output: res.output,
        summary: `${res.batches} 批 / ${res.anchors_qualified}/${res.anchors_total} 合格`,
      };
      setResult(display);
      shell.appendOutput(logLine(`[锚杆] 完成: ${display.summary} → ${display.output}`));
      return display;
    } catch (e) {
      const message = String(e);
      setRunError(message);
      shell.appendOutput(logLine(`[${label}] 失败: ${message}`));
      return null;
    } finally {
      setRunning(false);
    }
  }, [
    excelPath, sheet, outputPath, angle, running, calcType,
    anchorStandard, anchorBatchIdColumn, anchorParamsByBatch, shell,
  ]);

  // ── 文件树双击 .xlsx/.xls 联动：自动设为 excelPath ──
  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf(".");
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : "";
    if (!ACCEPTED_EXTS.has(ext)) return;
    // 同 key 在依赖里变化 → effect 重跑；同 path 也会触发（因 key 每次 ++）
    // 外部事件（文件树双击）→ 必须在 effect 里把 path 灌进 state
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExcelPath(f.path);
    shell.appendOutput(logLine(`[数据处理] 已接收文件: ${f.path}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  const ctx: Ctx = useMemo(
    () => ({
      calcType,
      excelPath, sheet, headerRow, angle, outputPath,
      sheets, previewHeaders, previewRows, previewTotalRows, previewShownRows,
      previewLoading, previewError,
      running, result, runError,
      defaultOutput,
      anchorStandard, anchorBatchIdColumn, anchorBatchIds,
      anchorBatchesLoading, anchorBatchesError, anchorParamsByBatch,
      anchorTemplateStatus,
      setCalcType, setExcelPath, setSheet, setHeaderRow, setAngle, setOutputPath,
      run,
      setAnchorStandard, setAnchorBatchIdColumn,
      setAnchorParamsForBatch, setAnchorParamsForAllBatches,
      generateAnchorTemplate,
    }),
    [
      calcType,
      excelPath, sheet, headerRow, angle, outputPath,
      sheets, previewHeaders, previewRows, previewTotalRows, previewShownRows,
      previewLoading, previewError,
      running, result, runError,
      defaultOutput,
      anchorStandard, anchorBatchIdColumn, anchorBatchIds,
      anchorBatchesLoading, anchorBatchesError, anchorParamsByBatch,
      anchorTemplateStatus,
      setExcelPath, setCalcType, run,
      setAnchorParamsForBatch, setAnchorParamsForAllBatches, generateAnchorTemplate,
    ],
  );

  return <DataProcessingContext.Provider value={ctx}>{children}</DataProcessingContext.Provider>;
}
