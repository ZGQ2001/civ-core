/**
 * data_processing 状态控制中心。整合"读 Excel → 走某种检测算法 → 写结果 Excel"流程。
 *
 * calcType: 计算类型 dropdown 切换；当前只有 "leeb"（里氏硬度），未来加钻芯/回弹等。
 *   - 每种 calcType 的 RPC 方法和参数集不一样，但「读 Excel + 预览 + 跑」这套
 *     状态是通用的；run() 内按 calcType 分支调对应 RPC。
 *
 * preview 走 leeb.preview_excel 通用读 Excel 前 N 行（headers/rows/total/sheets）；
 * 这个方法和 calcType 无关，未来可改成 io.preview_xlsx 之类的中性命名，暂沿用。
 *
 * 设计选择：sheet 列表也走 preview_excel 一并返（省一次 RPC）；用户改 sheet 时再次调
 * preview_excel 用新 sheet 重读 rows —— sheets 字段每次返一样的全列表，幂等。
 *
 * 未来 T5.5 后 leeb 的 Excel 读取切 C# OpenXML（合并单元格解析更靠谱），
 * preview_excel + leeb.run 都会迁过去，前端结构不需要改动 —— Provider 这层不感知。
 */
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
import type { CalcType, CellValue, PreviewRes, RunRes } from "./types";

const PREVIEW_DEBOUNCE_MS = 300;
const PREVIEW_MAX_ROWS = 50;

interface State {
  calcType: CalcType;

  // 用户参数
  excelPath: string;
  sheet: string;
  headerRow: number;
  angle: number;
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
}

interface Actions {
  setCalcType: (t: CalcType) => void;
  setExcelPath: (p: string) => void;
  setSheet: (s: string) => void;
  setHeaderRow: (n: number) => void;
  setAngle: (n: number) => void;
  setOutputPath: (s: string) => void;
  run: () => Promise<RunRes | null>;
}

type Ctx = State & Actions & { defaultOutput: string };

const DataProcessingContext = createContext<Ctx | null>(null);

export function useDataProcessing(): Ctx {
  const v = useContext(DataProcessingContext);
  if (!v) throw new Error("useDataProcessing must be used within <DataProcessingProvider>");
  return v;
}

export function DataProcessingProvider({ children }: { children: React.ReactNode }) {
  const [calcType, setCalcType] = useState<CalcType>("leeb");

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

  // 切换 Excel → 清掉旧预览 + 清 sheet 选择 + 清结果
  const setExcelPath = useCallback((p: string) => {
    setExcelPathRaw(p);
    setSheet("");
    setSheets([]);
    setPreviewHeaders([]);
    setPreviewRows([]);
    setPreviewError(null);
    setResult(null);
    setRunError(null);
  }, []);

  // 默认输出：<excel 同级>/<stem>_结果.xlsx；用户选了 outputPath 就用用户的
  const defaultOutput = useMemo(() => {
    if (!excelPath) return "";
    const sep = excelPath.includes("\\") ? "\\" : "/";
    const idx = excelPath.lastIndexOf(sep);
    const dir = idx > 0 ? excelPath.slice(0, idx) : "";
    const file = idx > 0 ? excelPath.slice(idx + 1) : excelPath;
    const stem = file.replace(/\.[^.]+$/, "");
    return `${dir}${sep}${stem}_结果.xlsx`;
  }, [excelPath]);

  // ── 预览（debounce）─────────────────────────────────────
  const debounceRef = useRef<number | null>(null);
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (!excelPath) {
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
          // 过期回包覆盖最新（旧请求晚到时丢弃）
          if (myId !== reqIdRef.current) return;
          setSheets(r.sheets);
          setPreviewHeaders(r.headers);
          setPreviewRows(r.rows);
          setPreviewTotalRows(r.total_rows);
          setPreviewShownRows(r.shown_rows);
          // 后端返回 actual sheet：传了不存在的 sheet 时它会回退到第一个；UI 同步
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

  const run = useCallback(async (): Promise<RunRes | null> => {
    if (!excelPath || running) return null;
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      // 当前 calcType 只支持 leeb；未来在这里加 switch 分支
      const params: Record<string, unknown> = {
        input_xlsx: excelPath,
        angle_degrees: angle,
      };
      if (outputPath.trim()) params.output_xlsx = outputPath.trim();

      // ── 第 1 步：Python leeb.run 算 + 写「过程数据」sheet ──
      // 后端把「报告插入表」交给 C# 写，所以这里也返回 report_table_data
      const res = await rpc<RunRes & {
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

      // ── 第 2 步：C# sidecar 写精致「报告插入表」sheet（合并/字体/边框/列宽）──
      if (res.report_table_data && res.report_table_data.length > 0) {
        await rpc("xlsx.write_leeb_report_table", {
          output_path: res.output,
          batches: res.report_table_data,
        });
      }

      // UI 只关心 batches/components/output，不展示 report_table_data
      const display: RunRes = {
        batches: res.batches,
        components: res.components,
        output: res.output,
      };
      setResult(display);
      return display;
    } catch (e) {
      setRunError(String(e));
      return null;
    } finally {
      setRunning(false);
    }
  }, [excelPath, outputPath, angle, running]);

  const ctx: Ctx = useMemo(
    () => ({
      calcType,
      excelPath,
      sheet,
      headerRow,
      angle,
      outputPath,
      sheets,
      previewHeaders,
      previewRows,
      previewTotalRows,
      previewShownRows,
      previewLoading,
      previewError,
      running,
      result,
      runError,
      defaultOutput,
      setCalcType,
      setExcelPath,
      setSheet,
      setHeaderRow,
      setAngle,
      setOutputPath,
      run,
    }),
    [
      calcType,
      excelPath, sheet, headerRow, angle, outputPath,
      sheets, previewHeaders, previewRows, previewTotalRows, previewShownRows,
      previewLoading, previewError,
      running, result, runError,
      defaultOutput, setExcelPath, run,
    ],
  );

  return <DataProcessingContext.Provider value={ctx}>{children}</DataProcessingContext.Provider>;
}
