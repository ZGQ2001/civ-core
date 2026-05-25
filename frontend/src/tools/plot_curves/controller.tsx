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
import type { PlotPreset, PreviewRes, RunRes } from './types';

const TOOL_ID = 'plot_curves';
const ACCEPTED_EXTS = new Set(['.xlsx', '.xls']);

const PREVIEW_DEBOUNCE_MS = 300;

type PresetSource = 'system' | 'user';

interface State {
  // 静态预设库
  presets: string[];
  presetDetails: Record<string, PlotPreset>;
  presetSources: Record<string, PresetSource>;
  presetLoadError: string | null;

  // 当前 Excel 的 sheet 列表（选 Excel 后自动拉）
  sheets: string[];
  sheetsLoading: boolean;
  sheetsError: string | null;

  // 当前 sheet + headerRow 下的列名（excel/sheet/headerRow 任一变化都自动拉）
  // 独立于 previewRowData：预览失败/未渲染时也能拿到表头给下拉用
  excelHeaders: string[];
  headersLoading: boolean;
  headersError: string | null;

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

export type RunOutcome =
  | { kind: 'ok'; res: RunRes; preset: string; excelPath: string }
  | { kind: 'error'; message: string }
  | null;

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
  run: () => Promise<RunOutcome>;
  // CRUD（操作完会自动 refresh 预设列表）
  savePreset: (name: string, data: PlotPreset) => Promise<void>;
  deletePreset: (name: string) => Promise<void>;
  renamePreset: (oldName: string, newName: string) => Promise<void>;
  copyPreset: (sourceName: string, newName: string) => Promise<void>;
  reloadPresets: () => Promise<void>;
}

type Ctx = State &
  Actions & {
    edited: boolean;
    effectivePreset: PlotPreset | null;
    currentSource: PresetSource | null;
  };

const PlotCurvesContext = createContext<Ctx | null>(null);

export function usePlotCurves(): Ctx {
  const v = useContext(PlotCurvesContext);
  if (!v)
    throw new Error('usePlotCurves must be used within <PlotCurvesProvider>');
  return v;
}

export function PlotCurvesProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const shell = useShell();
  const [presets, setPresets] = useState<string[]>([]);
  const [presetDetails, setPresetDetails] = useState<
    Record<string, PlotPreset>
  >({});
  const [presetSources, setPresetSources] = useState<
    Record<string, PresetSource>
  >({});
  const [presetLoadError, setPresetLoadError] = useState<string | null>(null);

  const [sheets, setSheets] = useState<string[]>([]);
  const [sheetsLoading, setSheetsLoading] = useState(false);
  const [sheetsError, setSheetsError] = useState<string | null>(null);

  const [excelHeaders, setExcelHeaders] = useState<string[]>([]);
  const [headersLoading, setHeadersLoading] = useState(false);
  const [headersError, setHeadersError] = useState<string | null>(null);

  const [preset, setPreset] = useState<string>('');
  const [excelPath, setExcelPath] = useState<string>('');
  const [sheet, setSheet] = useState<string>('');
  const [headerRow, setHeaderRow] = useState<number>(1);
  const [outputDir, setOutputDir] = useState<string>('');
  const [rowIndex, setRowIndex] = useState<number>(0);

  const [workingPreset, setWorkingPreset] = useState<PlotPreset | null>(null);

  const [previewPng, setPreviewPng] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewTotal, setPreviewTotal] = useState(0);
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewRowId, setPreviewRowId] = useState('');
  const [previewRowData, setPreviewRowData] = useState<
    Record<string, string | number | boolean | null>
  >({});

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunRes | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // 拉预设（启动 + CRUD 操作后调用）
  const reloadPresets = useCallback(async () => {
    try {
      const r = await rpc<{
        presets: string[];
        default: string | null;
        details: Record<string, PlotPreset>;
        sources: Record<string, PresetSource>;
      }>('plot_curves.list_presets');
      setPresets(r.presets);
      setPresetDetails(r.details);
      setPresetSources(r.sources);
      setPresetLoadError(null);
      // 当前选中的预设如果没了 → 退回 default
      setPreset((cur) =>
        cur && r.presets.includes(cur) ? cur : (r.default ?? ''),
      );
    } catch (e) {
      setPresetLoadError(String(e));
    }
  }, []);

  useEffect(() => {
    // 启动期拉预设。setState 在 reloadPresets 内异步完成
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reloadPresets();
  }, [reloadPresets]);

  // 切换预设 → 丢编辑、重置行号
  useEffect(() => {
    // preset 变 → 关联派生状态重置；move 到 setPreset action 会漏掉外部 setPreset 路径
    /* eslint-disable react-hooks/set-state-in-effect */
    setWorkingPreset(null);
    setRowIndex(0);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [preset]);

  // 切换 Excel → 拉 sheets 列表；自动选第一个；重置 row index
  useEffect(() => {
    if (!excelPath) {
      // excelPath 清空 → 同步清掉 sheets
      /* eslint-disable react-hooks/set-state-in-effect */
      setSheets([]);
      setSheetsError(null);
      setSheet('');
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }
    let cancelled = false;
    setSheetsLoading(true);
    setSheetsError(null);
    rpc<{ sheets: string[] }>('plot_curves.list_sheets', {
      excel_path: excelPath,
    })
      .then((r) => {
        if (cancelled) return;
        setSheets(r.sheets);
        // 当前选中 sheet 不在新文件里 → 退回第一个；空文件 → 清空
        setSheet((cur) => (r.sheets.includes(cur) ? cur : (r.sheets[0] ?? '')));
        setRowIndex(0);
      })
      .catch((e) => {
        if (cancelled) return;
        setSheetsError(String(e));
        setSheets([]);
        setSheet('');
      })
      .finally(() => {
        if (!cancelled) setSheetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [excelPath]);

  // 拉当前 sheet + headerRow 下的表头列名（独立于预览渲染）
  // 没选 Excel / 没选 sheet → 清空；其它情况 race-guard 后异步拉
  useEffect(() => {
    if (!excelPath || !sheet) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setExcelHeaders([]);
      setHeadersError(null);
      setHeadersLoading(false);
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }
    let cancelled = false;
    setHeadersLoading(true);
    setHeadersError(null);
    rpc<{ headers: string[] }>('plot_curves.list_headers', {
      excel_path: excelPath,
      sheet,
      header_row: headerRow,
    })
      .then((r) => {
        if (cancelled) return;
        setExcelHeaders(r.headers);
      })
      .catch((e) => {
        if (cancelled) return;
        setHeadersError(String(e));
        setExcelHeaders([]);
      })
      .finally(() => {
        if (!cancelled) setHeadersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [excelPath, sheet, headerRow]);

  const effectivePreset: PlotPreset | null =
    workingPreset ?? presetDetails[preset] ?? null;
  const edited = workingPreset !== null;
  const currentSource: PresetSource | null = preset
    ? (presetSources[preset] ?? null)
    : null;

  // CRUD —— 调完后 reload 确保前端拿到最新预设列表 + sources
  const savePreset = useCallback(
    async (name: string, data: PlotPreset) => {
      await rpc('plot_curves.save_preset', { name, data });
      await reloadPresets();
      // 切到刚保存的，清掉 working override
      setPreset(name);
      setWorkingPreset(null);
    },
    [reloadPresets],
  );

  const deletePreset = useCallback(
    async (name: string) => {
      await rpc('plot_curves.delete_preset', { name });
      await reloadPresets();
    },
    [reloadPresets],
  );

  const renamePreset = useCallback(
    async (oldName: string, newName: string) => {
      await rpc('plot_curves.rename_preset', {
        old_name: oldName,
        new_name: newName,
      });
      await reloadPresets();
      // 切到新名
      setPreset(newName);
    },
    [reloadPresets],
  );

  const copyPreset = useCallback(
    async (sourceName: string, newName: string) => {
      await rpc('plot_curves.copy_preset', {
        source_name: sourceName,
        new_name: newName,
      });
      await reloadPresets();
      setPreset(newName);
    },
    [reloadPresets],
  );

  const patchPreset: Actions['patchPreset'] = useCallback(
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
      // 关联输入清空 → 同步清旧预览
      /* eslint-disable react-hooks/set-state-in-effect */
      setPreviewPng(null);
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
      rpc<PreviewRes>('plot_curves.render_preview', {
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
      if (debounceRef.current !== null)
        window.clearTimeout(debounceRef.current);
    };
  }, [effectivePreset, excelPath, sheet, headerRow, rowIndex]);

  // ── 文件树双击 .xlsx/.xls 联动：自动设为 excelPath ──
  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (!ACCEPTED_EXTS.has(ext)) return;
    // 同 key 在依赖里变化 → effect 重跑；同 path 也会触发（因 key 每次 ++）
    // 外部事件（文件树双击）→ 必须在 effect 里把 path 灌进 state
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExcelPath(f.path);
    shell.appendOutput(logLine(`[绘曲线图] 已接收文件: ${f.path}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  // ── 运行（同步阻塞，结果走 result）─────────────────────
  const run = useCallback(async (): Promise<RunOutcome> => {
    if (!excelPath || !preset || running) return null;
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
      const res = await rpc<RunRes>('plot_curves.run', params);
      setResult(res);
      shell.notifyFilesChanged();
      return { kind: 'ok', res, preset, excelPath };
    } catch (e) {
      const message = String(e);
      setRunError(message);
      return { kind: 'error', message };
    } finally {
      setRunning(false);
    }
  }, [excelPath, preset, sheet, headerRow, outputDir, workingPreset, running, shell]);

  const ctx: Ctx = useMemo(
    () => ({
      presets,
      presetDetails,
      presetSources,
      presetLoadError,
      sheets,
      sheetsLoading,
      sheetsError,
      excelHeaders,
      headersLoading,
      headersError,
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
      currentSource,
      setPreset,
      setExcelPath,
      setSheet,
      setHeaderRow,
      setOutputDir,
      setRowIndex,
      patchPreset,
      resetPreset,
      run,
      savePreset,
      deletePreset,
      renamePreset,
      copyPreset,
      reloadPresets,
    }),
    [
      presets,
      presetDetails,
      presetSources,
      presetLoadError,
      sheets,
      sheetsLoading,
      sheetsError,
      excelHeaders,
      headersLoading,
      headersError,
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
      currentSource,
      patchPreset,
      resetPreset,
      run,
      savePreset,
      deletePreset,
      renamePreset,
      copyPreset,
      reloadPresets,
    ],
  );

  return (
    <PlotCurvesContext.Provider value={ctx}>
      {children}
    </PlotCurvesContext.Provider>
  );
}
