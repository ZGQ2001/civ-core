/**
 * plot_curves 状态控制中心：lift state 到 App 顶层（Provider），让
 * 工具页主区（上）和底部 Panel 的 SettingsForm（下）共享同一份数据。
 *
 * 设计要点：
 *  - 所有 state + actions 集中在 usePlotCurves hook
 *  - workingPreset = 用户改过的预设（form 编辑直接 mutate 它）；
 *    null 时退化为 presetDetails[preset]（原版）
 *  - debounce：workingPreset/excelPath/sheet/headerRow/rowIndex 任一变 →
 *    300ms 后调 render_preview 拉新预览图；快速键入不卡 IO
 *  - run() 时若 workingPreset 非 null 就作为 preset_override 传后端
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { rpc } from "../../lib/rpc";
import type { PlotPreset, PreviewRes, RunRes } from "./types";

const PREVIEW_DEBOUNCE_MS = 300;

interface State {
  // 静态预设库
  presets: string[];
  presetDetails: Record<string, PlotPreset>;
  presetLoadError: string | null;

  // 用户选择
  preset: string;
  excelPath: string;
  sheet: string;
  headerRow: number;
  outputDir: string;
  rowIndex: number;

  // 编辑后的预设：null=用原版
  workingPreset: PlotPreset | null;

  // 预览
  previewPng: string | null;
  previewError: string | null;
  previewLoading: boolean;
  previewTotal: number;
  previewTitle: string;
  previewRowId: string;
  previewRowData: Record<string, string | number | boolean | null>;

  // 运行
  running: boolean;
  result: RunRes | null;
  runError: string | null;
}

interface Actions {
  setPreset: (name: string) => void;
  setExcelPath: (p: string) => void;
  setSheet: (s: string) => void;
  setHeaderRow: (n: number) => void;
  setOutputDir: (s: string) => void;
  setRowIndex: (n: number) => void;
  /** form 编辑：传 updater 改 workingPreset（若 null 先初始化为当前预设的深拷贝） */
  patchPreset: (updater: (p: PlotPreset) => PlotPreset) => void;
  resetPreset: () => void;
  run: () => Promise<void>;
}

type Ctx = State & Actions & { edited: boolean; effectivePreset: PlotPreset | null };

const PlotCurvesContext = createContext<Ctx | null>(null);

export function usePlotCurves(): Ctx {
  const v = useContext(PlotCurvesContext);
  if (!v) throw new Error("usePlotCurves must be used within <PlotCurvesProvider>");
  return v;
}

export function PlotCurvesProvider({ children }: { children: React.ReactNode }) {
  const [presets, setPresets] = useState<string[]>([]);
  const [presetDetails, setPresetDetails] = useState<Record<string, PlotPreset>>({});
  const [presetLoadError, setPresetLoadError] = useState<string | null>(null);

  const [preset, setPreset] = useState<string>("");
  const [excelPath, setExcelPath] = useState<string>("");
  const [sheet, setSheet] = useState<string>("");
  const [headerRow, setHeaderRow] = useState<number>(1);
  const [outputDir, setOutputDir] = useState<string>("");
  const [rowIndex, setRowIndex] = useState<number>(0);

  const [workingPreset, setWorkingPreset] = useState<PlotPreset | null>(null);

  const [previewPng, setPreviewPng] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewTotal, setPreviewTotal] = useState(0);
  const [previewTitle, setPreviewTitle] = useState("");
  const [previewRowId, setPreviewRowId] = useState("");
  const [previewRowData, setPreviewRowData] = useState<
    Record<string, string | number | boolean | null>
  >({});

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunRes | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // 启动拉预设
  useEffect(() => {
    (async () => {
      try {
        const r = await rpc<{
          presets: string[];
          default: string | null;
          details: Record<string, PlotPreset>;
        }>("plot_curves.list_presets");
        setPresets(r.presets);
        setPresetDetails(r.details);
        if (r.default) setPreset(r.default);
      } catch (e) {
        setPresetLoadError(String(e));
      }
    })();
  }, []);

  // 切换预设 → 丢编辑、重置行号
  useEffect(() => {
    setWorkingPreset(null);
    setRowIndex(0);
  }, [preset]);

  const effectivePreset: PlotPreset | null = workingPreset ?? presetDetails[preset] ?? null;
  const edited = workingPreset !== null;

  const patchPreset: Actions["patchPreset"] = useCallback(
    (updater) => {
      const base = workingPreset ?? presetDetails[preset];
      if (!base) return;
      // 深拷贝避免 mutate presetDetails 原值
      const cloned = JSON.parse(JSON.stringify(base)) as PlotPreset;
      setWorkingPreset(updater(cloned));
    },
    [workingPreset, presetDetails, preset],
  );

  const resetPreset = useCallback(() => setWorkingPreset(null), []);

  // ── 预览（debounce）─────────────────────────────────────
  const debounceRef = useRef<number | null>(null);
  const reqIdRef = useRef(0);

  useEffect(() => {
    // 没选 Excel / 没预设 → 跳过预览
    if (!excelPath || !effectivePreset) {
      setPreviewPng(null);
      setPreviewError(null);
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
      rpc<PreviewRes>("plot_curves.render_preview", {
        preset_dict: effectivePreset,
        excel_path: excelPath,
        sheet: sheet.trim() || null,
        header_row: headerRow,
        row_index: rowIndex,
      })
        .then((r) => {
          // 防过期回包覆盖最新（旧请求晚到时丢弃）
          if (myId !== reqIdRef.current) return;
          setPreviewPng(r.png_base64);
          setPreviewTotal(r.total_rows);
          setPreviewTitle(r.title);
          setPreviewRowId(r.row_id);
          setPreviewRowData(r.row_data ?? {});
        })
        .catch((e) => {
          if (myId !== reqIdRef.current) return;
          setPreviewError(String(e));
          setPreviewPng(null);
        })
        .finally(() => {
          if (myId === reqIdRef.current) setPreviewLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current);
    };
  }, [effectivePreset, excelPath, sheet, headerRow, rowIndex]);

  // ── 运行（同步阻塞，结果走 result）─────────────────────
  const run = useCallback(async () => {
    if (!excelPath || !preset || running) return;
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      const params: Record<string, unknown> = {
        excel_path: excelPath,
        preset,
        header_row: headerRow,
      };
      if (sheet.trim()) params.sheet = sheet.trim();
      if (outputDir.trim()) params.output_dir = outputDir.trim();
      if (workingPreset) params.preset_override = workingPreset;
      const res = await rpc<RunRes>("plot_curves.run", params);
      setResult(res);
    } catch (e) {
      setRunError(String(e));
    } finally {
      setRunning(false);
    }
  }, [excelPath, preset, sheet, headerRow, outputDir, workingPreset, running]);

  const ctx: Ctx = useMemo(
    () => ({
      presets,
      presetDetails,
      presetLoadError,
      preset,
      excelPath,
      sheet,
      headerRow,
      outputDir,
      rowIndex,
      workingPreset,
      previewPng,
      previewError,
      previewLoading,
      previewTotal,
      previewTitle,
      previewRowId,
      previewRowData,
      running,
      result,
      runError,
      edited,
      effectivePreset,
      setPreset,
      setExcelPath,
      setSheet,
      setHeaderRow,
      setOutputDir,
      setRowIndex,
      patchPreset,
      resetPreset,
      run,
    }),
    [
      presets, presetDetails, presetLoadError,
      preset, excelPath, sheet, headerRow, outputDir, rowIndex,
      workingPreset, previewPng, previewError, previewLoading,
      previewTotal, previewTitle, previewRowId, previewRowData,
      running, result, runError, edited, effectivePreset,
      patchPreset, resetPreset, run,
    ],
  );

  return <PlotCurvesContext.Provider value={ctx}>{children}</PlotCurvesContext.Provider>;
}
