/**
 * leeb_hardness 状态控制中心。和 plot_curves controller 同构：
 *   - 全状态 lift 到 Provider（Page 在主区 / SettingsForm 在右侧 RightPanel 共用同一份）
 *   - excelPath/sheet/headerRow 任一改 → 300ms debounce 调 leeb.preview_excel 拉前 N 行表格
 *   - run() 同步阻塞，结果存 result/runError；Page 顶部按钮触发
 *
 * 设计选择：sheet 列表也走 preview_excel 一并返（省一次 RPC）；用户改 sheet 时再次调
 * preview_excel 用新 sheet 重读 rows —— sheets 字段每次返一样的全列表，幂等。
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
import type { CellValue, PreviewRes, RunRes } from "./types";

const PREVIEW_DEBOUNCE_MS = 300;
const PREVIEW_MAX_ROWS = 50;

interface State {
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
  setExcelPath: (p: string) => void;
  setSheet: (s: string) => void;
  setHeaderRow: (n: number) => void;
  setAngle: (n: number) => void;
  setOutputPath: (s: string) => void;
  run: () => Promise<RunRes | null>;
}

type Ctx = State & Actions & { defaultOutput: string };

const LeebContext = createContext<Ctx | null>(null);

export function useLeeb(): Ctx {
  const v = useContext(LeebContext);
  if (!v) throw new Error("useLeeb must be used within <LeebHardnessProvider>");
  return v;
}

export function LeebHardnessProvider({ children }: { children: React.ReactNode }) {
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
      const params: Record<string, unknown> = {
        input_xlsx: excelPath,
        angle_degrees: angle,
      };
      if (outputPath.trim()) params.output_xlsx = outputPath.trim();
      const res = await rpc<RunRes>("leeb.run", params);
      setResult(res);
      return res;
    } catch (e) {
      setRunError(String(e));
      return null;
    } finally {
      setRunning(false);
    }
  }, [excelPath, outputPath, angle, running]);

  const ctx: Ctx = useMemo(
    () => ({
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
      setExcelPath,
      setSheet,
      setHeaderRow,
      setAngle,
      setOutputPath,
      run,
    }),
    [
      excelPath, sheet, headerRow, angle, outputPath,
      sheets, previewHeaders, previewRows, previewTotalRows, previewShownRows,
      previewLoading, previewError,
      running, result, runError,
      defaultOutput, setExcelPath, run,
    ],
  );

  return <LeebContext.Provider value={ctx}>{children}</LeebContext.Provider>;
}
