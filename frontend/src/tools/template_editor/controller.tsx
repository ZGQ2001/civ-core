/**
 * template_editor 状态控制中心 —— Phase 2 完整态。
 *
 * 状态分层（解耦）：
 *  - 静态：templates (已保存列表) / fields (字段清单)
 *  - 当前模板：currentName / sourceDocxPath / parsed / displayName / repeat
 *  - 编辑态：bindings / selectedCell
 *
 * actions 不掺 UI；UI 文件不写 RPC。
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
import type {
  CellBinding,
  FieldDef,
  ParsedTable,
  RepeatStrategy,
  TemplateConfig,
  TemplateLoadRes,
  TemplateMeta,
} from './types';

const TOOL_ID = 'template_editor';
const ACCEPTED_EXTS = new Set(['.docx']);
const DEFAULT_PROJECT_TYPE = 'anchor';

/** bindings 用 "{row}-{col}" 字符串 key 存（React state 友好；保存时转 array）。 */
export type BindingMap = Record<string, CellBinding>;
export const cellKey = (row: number, col: number) => `${row}-${col}`;

interface State {
  templates: TemplateMeta[];
  templatesLoading: boolean;
  templatesError: string | null;

  projectType: string;
  fields: FieldDef[];
  fieldsLoading: boolean;
  fieldsError: string | null;

  // 当前编辑的模板
  currentName: string | null;
  sourceDocxPath: string;
  parsed: ParsedTable | null;
  parseLoading: boolean;
  parseError: string | null;

  displayName: string;
  repeat: RepeatStrategy;

  bindings: BindingMap;
  selectedCell: { row: number; col: number } | null;

  saving: boolean;
  saveError: string | null;
}

interface Actions {
  setSourceDocxPath: (p: string) => void;
  setProjectType: (t: string) => void;
  setDisplayName: (s: string) => void;
  setRepeat: (r: RepeatStrategy) => void;

  selectCell: (row: number, col: number) => void;
  clearSelectedCell: () => void;
  bindFieldToSelected: (fieldKey: string) => void;
  unbindCell: (row: number, col: number) => void;
  setBindingFormat: (row: number, col: number, format: string | null) => void;

  saveTemplate: (name: string) => Promise<boolean>;
  loadTemplate: (name: string) => Promise<boolean>;
  deleteTemplate: (name: string) => Promise<boolean>;
  startNewTemplate: () => void;

  reloadTemplates: () => Promise<void>;
  reloadFields: () => Promise<void>;
}

type Ctx = State & Actions;

const TemplateEditorContext = createContext<Ctx | null>(null);

export function useTemplateEditor(): Ctx {
  const v = useContext(TemplateEditorContext);
  if (!v)
    throw new Error(
      'useTemplateEditor must be used within <TemplateEditorProvider>',
    );
  return v;
}

export function TemplateEditorProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const shell = useShell();

  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  const [projectType, setProjectType] = useState<string>(DEFAULT_PROJECT_TYPE);
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [fieldsLoading, setFieldsLoading] = useState(false);
  const [fieldsError, setFieldsError] = useState<string | null>(null);

  const [currentName, setCurrentName] = useState<string | null>(null);
  const [sourceDocxPath, setSourceDocxPath] = useState<string>('');
  const [parsed, setParsed] = useState<ParsedTable | null>(null);
  const [parseLoading, setParseLoading] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState('');
  const [repeat, setRepeat] = useState<RepeatStrategy>('per_row');

  const [bindings, setBindings] = useState<BindingMap>({});
  const [selectedCell, setSelectedCell] = useState<{
    row: number;
    col: number;
  } | null>(null);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // ── 列表 + 字段清单 ────────────────────────────────────
  const reloadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    setTemplatesError(null);
    try {
      const r = await rpc<{ templates: TemplateMeta[] }>('template.list');
      setTemplates(r.templates);
    } catch (e) {
      setTemplatesError(String(e));
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  const reloadFields = useCallback(async () => {
    setFieldsLoading(true);
    setFieldsError(null);
    try {
      const r = await rpc<{ fields: FieldDef[] }>('template.fields', {
        project_type: projectType,
      });
      setFields(r.fields);
    } catch (e) {
      setFieldsError(String(e));
      setFields([]);
    } finally {
      setFieldsLoading(false);
    }
  }, [projectType]);

  useEffect(() => {
    // 启动期拉模板列表；setState 在 reloadTemplates 内异步完成
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reloadTemplates();
  }, [reloadTemplates]);
  useEffect(() => {
    // 启动期 + projectType 变化时重拉字段清单
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reloadFields();
  }, [reloadFields]);

  // ── 选 docx → 解析 ──────────────────────────────────────
  useEffect(() => {
    if (!sourceDocxPath) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setParsed(null);
      setParseError(null);
      setParseLoading(false);
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }
    let cancelled = false;
    setParseLoading(true);
    setParseError(null);
    rpc<ParsedTable>('template.parse', { docx_path: sourceDocxPath })
      .then((r) => {
        if (cancelled) return;
        setParsed(r);
      })
      .catch((e) => {
        if (cancelled) return;
        setParseError(String(e));
        setParsed(null);
      })
      .finally(() => {
        if (!cancelled) setParseLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceDocxPath]);

  // ── 文件树双击 .docx ────────────────────────────────────
  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (!ACCEPTED_EXTS.has(ext)) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSourceDocxPath(f.path);
    shell.appendOutput(logLine(`[模板编辑] 已接收文件: ${f.path}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  // ── 编辑态 actions ──────────────────────────────────────
  const selectCell = useCallback(
    (row: number, col: number) => setSelectedCell({ row, col }),
    [],
  );
  const clearSelectedCell = useCallback(() => setSelectedCell(null), []);

  const bindFieldToSelected = useCallback(
    (fieldKey: string) => {
      if (!selectedCell) return;
      const { row, col } = selectedCell;
      setBindings((prev) => {
        // 该字段已绑到别格 → 移除旧绑定（保证 fieldKey 唯一）
        const next: BindingMap = {};
        for (const [k, b] of Object.entries(prev))
          if (b.field_key !== fieldKey) next[k] = b;
        next[cellKey(row, col)] = {
          row,
          col,
          field_key: fieldKey,
          format: null,
        };
        return next;
      });
    },
    [selectedCell],
  );

  const unbindCell = useCallback((row: number, col: number) => {
    setBindings((prev) => {
      const next = { ...prev };
      delete next[cellKey(row, col)];
      return next;
    });
  }, []);

  const setBindingFormat = useCallback(
    (row: number, col: number, format: string | null) => {
      const k = cellKey(row, col);
      setBindings((prev) => {
        const cur = prev[k];
        if (!cur) return prev;
        return { ...prev, [k]: { ...cur, format } };
      });
    },
    [],
  );

  // ── 模板 CRUD ──────────────────────────────────────────
  const startNewTemplate = useCallback(() => {
    setCurrentName(null);
    setSourceDocxPath('');
    setDisplayName('');
    setRepeat('per_row');
    setBindings({});
    setSelectedCell(null);
    setSaveError(null);
  }, []);

  const saveTemplate = useCallback(
    async (name: string): Promise<boolean> => {
      if (!parsed || !sourceDocxPath) {
        setSaveError('请先选 Word 模板并完成解析');
        return false;
      }
      setSaving(true);
      setSaveError(null);
      try {
        const config: TemplateConfig = {
          version: 1,
          project_type: projectType,
          display_name: displayName.trim() || name,
          table_signature: parsed.table_signature,
          repeat,
          bindings: Object.values(bindings).sort(
            (a, b) => a.row - b.row || a.col - b.col,
          ),
        };
        await rpc('template.save', {
          name,
          source_docx_path: sourceDocxPath,
          config,
        });
        setCurrentName(name);
        shell.appendOutput(logLine(`[模板编辑] 已保存：${name}`));
        await reloadTemplates();
        return true;
      } catch (e) {
        setSaveError(String(e));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [
      parsed,
      sourceDocxPath,
      projectType,
      displayName,
      repeat,
      bindings,
      reloadTemplates,
      shell,
    ],
  );

  const loadTemplate = useCallback(
    async (name: string): Promise<boolean> => {
      setSaveError(null);
      try {
        const r = await rpc<TemplateLoadRes>('template.load', { name });
        setCurrentName(name);
        setSourceDocxPath(r.source_docx_path);
        setParsed(r.parsed);
        setParseError(null);
        setDisplayName(r.config.display_name);
        setRepeat(r.config.repeat);
        setProjectType(r.config.project_type);
        const map: BindingMap = {};
        for (const b of r.config.bindings) map[cellKey(b.row, b.col)] = b;
        setBindings(map);
        setSelectedCell(null);
        shell.appendOutput(logLine(`[模板编辑] 已加载：${name}`));
        return true;
      } catch (e) {
        setSaveError(`加载失败：${String(e)}`);
        return false;
      }
    },
    [shell],
  );

  const deleteTemplate = useCallback(
    async (name: string): Promise<boolean> => {
      try {
        await rpc('template.delete', { name });
        if (currentName === name) startNewTemplate();
        await reloadTemplates();
        shell.appendOutput(logLine(`[模板编辑] 已删除：${name}`));
        return true;
      } catch (e) {
        setSaveError(`删除失败：${String(e)}`);
        return false;
      }
    },
    [currentName, startNewTemplate, reloadTemplates, shell],
  );

  const ctx: Ctx = useMemo(
    () => ({
      templates,
      templatesLoading,
      templatesError,
      projectType,
      fields,
      fieldsLoading,
      fieldsError,
      currentName,
      sourceDocxPath,
      parsed,
      parseLoading,
      parseError,
      displayName,
      repeat,
      bindings,
      selectedCell,
      saving,
      saveError,
      setSourceDocxPath,
      setProjectType,
      setDisplayName,
      setRepeat,
      selectCell,
      clearSelectedCell,
      bindFieldToSelected,
      unbindCell,
      setBindingFormat,
      saveTemplate,
      loadTemplate,
      deleteTemplate,
      startNewTemplate,
      reloadTemplates,
      reloadFields,
    }),
    [
      templates,
      templatesLoading,
      templatesError,
      projectType,
      fields,
      fieldsLoading,
      fieldsError,
      currentName,
      sourceDocxPath,
      parsed,
      parseLoading,
      parseError,
      displayName,
      repeat,
      bindings,
      selectedCell,
      saving,
      saveError,
      selectCell,
      clearSelectedCell,
      bindFieldToSelected,
      unbindCell,
      setBindingFormat,
      saveTemplate,
      loadTemplate,
      deleteTemplate,
      startNewTemplate,
      reloadTemplates,
      reloadFields,
    ],
  );

  return (
    <TemplateEditorContext.Provider value={ctx}>
      {children}
    </TemplateEditorContext.Provider>
  );
}
