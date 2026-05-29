/* eslint-disable react-refresh/only-export-components -- hook 与 Provider 同文件共存，是工具页范式 */
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
  CatalogField,
  CatalogSummary,
  FieldCatalog,
  ValidateResult,
} from './types';
import { LEVEL_LABEL } from './types';

const UNUSED_PREVIEW_LIMIT = 5;

const TOOL_ID = 'template_helper';
const ACCEPTED_EXTS = new Set(['.docx']);

interface State {
  catalogs: CatalogSummary[];
  catalogsLoading: boolean;
  activeCatalogId: string | null;
  activeCatalog: FieldCatalog | null;
  catalogLoading: boolean;
  dirty: boolean;
  saving: boolean;

  docxPath: string;
  validating: boolean;
  /** 最近一次「验证」的结构化结果 —— 页内体检面板渲染用；选新模板/换目录时清空。 */
  lastValidation: ValidateResult | null;

  copiedKey: string | null;
  editingFieldKey: string | null;
}

interface Actions {
  refreshCatalogs: () => Promise<void>;
  selectCatalog: (id: string) => Promise<void>;
  setDocxPath: (p: string) => void;
  validate: () => Promise<ValidateResult | null>;
  /** 收起页内体检面板（不影响日志已输出的内容）。 */
  dismissValidation: () => void;
  copyPlaceholder: (text: string, key: string) => void;

  addField: (field: CatalogField) => void;
  updateField: (oldKey: string, field: CatalogField) => void;
  removeField: (key: string) => void;
  saveCatalog: () => Promise<boolean>;
  setEditingFieldKey: (key: string | null) => void;

  createCatalog: (id: string, label: string) => Promise<boolean>;
  copyCatalog: (newId: string, newLabel: string) => Promise<boolean>;
  deleteCatalog: () => Promise<boolean>;
  renameCatalog: (label: string) => void;
}

type Ctx = State & Actions;

const TemplateHelperContext = createContext<Ctx | null>(null);

export function useTemplateHelper(): Ctx {
  const v = useContext(TemplateHelperContext);
  if (!v)
    throw new Error(
      'useTemplateHelper must be used within <TemplateHelperProvider>',
    );
  return v;
}

export function TemplateHelperProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const shell = useShell();

  const [catalogs, setCatalogs] = useState<CatalogSummary[]>([]);
  const [catalogsLoading, setCatalogsLoading] = useState(false);
  const [activeCatalogId, setActiveCatalogId] = useState<string | null>(null);
  const [activeCatalog, setActiveCatalog] = useState<FieldCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const [docxPath, setDocxPathRaw] = useState('');
  const [validating, setValidating] = useState(false);
  const [lastValidation, setLastValidation] = useState<ValidateResult | null>(
    null,
  );

  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [editingFieldKey, setEditingFieldKey] = useState<string | null>(null);

  // 换模板 → 旧体检结果作废（避免拿 A 模板的结果误导 B 模板）。
  const setDocxPath = useCallback((p: string) => {
    setDocxPathRaw(p);
    setLastValidation(null);
  }, []);

  const dismissValidation = useCallback(() => setLastValidation(null), []);

  const refreshCatalogs = useCallback(async () => {
    setCatalogsLoading(true);
    try {
      const res = await rpc<{ catalogs: CatalogSummary[] }>('catalog.list');
      setCatalogs(res.catalogs);
      if (res.catalogs.length > 0 && !activeCatalogId) {
        setActiveCatalogId(res.catalogs[0].id);
      }
    } catch (e) {
      shell.appendOutput(logLine(`[模板助手] 加载字段目录失败: ${String(e)}`));
    } finally {
      setCatalogsLoading(false);
    }
  }, [activeCatalogId, shell]);

  const selectCatalog = useCallback(
    async (id: string) => {
      setActiveCatalogId(id);
      setCatalogLoading(true);
      setDirty(false);
      setEditingFieldKey(null);
      setLastValidation(null); // 换目录 → 旧体检结果作废
      try {
        const res = await rpc<{ catalog: FieldCatalog }>('catalog.get', {
          id,
        });
        setActiveCatalog(res.catalog);
      } catch (e) {
        shell.appendOutput(
          logLine(`[模板助手] 加载字段目录失败: ${String(e)}`),
        );
        setActiveCatalog(null);
      } finally {
        setCatalogLoading(false);
      }
    },
    [shell],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshCatalogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeCatalogId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      selectCatalog(activeCatalogId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCatalogId]);

  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (!ACCEPTED_EXTS.has(ext)) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDocxPath(f.path);
    shell.appendOutput(logLine(`[模板助手] 已接收模板文件: ${f.path}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  const validate = useCallback(async (): Promise<ValidateResult | null> => {
    if (!docxPath || !activeCatalogId) return null;
    setValidating(true);
    try {
      const res = await rpc<ValidateResult>('template.validate', {
        docx_path: docxPath,
        catalog_id: activeCatalogId,
      });
      setLastValidation(res); // 结构化结果存进 state，页内体检面板渲染
      const s = res.summary;
      shell.appendOutput(
        logLine(
          `[模板助手] 验证完成: ${s.matched_count} 匹配 / ${s.unrecognized_count} 未识别 / ${s.unused_count} 未使用 / ${s.hint_count} 提示`,
        ),
      );
      for (const h of res.hints) {
        const tag = h.severity === 'error' ? '错误' : '警告';
        shell.appendOutput(
          logLine(`[模板助手]   [${tag}] ${h.message} @ ${h.location}`),
        );
      }
      for (const u of res.unrecognized) {
        shell.appendOutput(
          logLine(
            `[模板助手]   未识别占位符: ${u.placeholder} @ ${u.location}`,
          ),
        );
      }
      const unusedShown = res.unused.slice(0, UNUSED_PREVIEW_LIMIT);
      for (const u of unusedShown) {
        const lvl = LEVEL_LABEL[u.level] ?? u.level;
        shell.appendOutput(
          logLine(`[模板助手]   未使用字段: ${u.name}（${lvl}）`),
        );
      }
      if (res.unused.length > UNUSED_PREVIEW_LIMIT) {
        shell.appendOutput(
          logLine(
            `[模板助手]   …另外 ${res.unused.length - UNUSED_PREVIEW_LIMIT} 个未使用字段（略）`,
          ),
        );
      }
      return res;
    } catch (e) {
      const msg = String(e);
      shell.appendOutput(logLine(`[模板助手] 验证失败: ${msg}`));
      return null;
    } finally {
      setValidating(false);
    }
  }, [docxPath, activeCatalogId, shell]);

  const copyPlaceholder = useCallback((text: string, key: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedKey(key);
    setTimeout(
      () => setCopiedKey((prev) => (prev === key ? null : prev)),
      1500,
    );
  }, []);

  // ── Field CRUD ──

  const addField = useCallback((field: CatalogField) => {
    setActiveCatalog((prev) => {
      if (!prev) return prev;
      if (prev.fields.some((f) => f.key === field.key)) return prev;
      return { ...prev, fields: [...prev.fields, field] };
    });
    setDirty(true);
  }, []);

  const updateField = useCallback((oldKey: string, field: CatalogField) => {
    setActiveCatalog((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        fields: prev.fields.map((f) => (f.key === oldKey ? field : f)),
      };
    });
    setDirty(true);
  }, []);

  const removeField = useCallback((key: string) => {
    setActiveCatalog((prev) => {
      if (!prev) return prev;
      return { ...prev, fields: prev.fields.filter((f) => f.key !== key) };
    });
    setDirty(true);
    setEditingFieldKey((prev) => (prev === key ? null : prev));
  }, []);

  const renameCatalog = useCallback((label: string) => {
    setActiveCatalog((prev) => (prev ? { ...prev, label } : prev));
    setDirty(true);
  }, []);

  const saveCatalog = useCallback(async (): Promise<boolean> => {
    if (!activeCatalog) return false;
    setSaving(true);
    try {
      await rpc('catalog.save', { catalog: activeCatalog });
      setDirty(false);
      shell.appendOutput(
        logLine(`[模板助手] 已保存字段目录: ${activeCatalog.label}`),
      );
      refreshCatalogs();
      return true;
    } catch (e) {
      shell.appendOutput(logLine(`[模板助手] 保存失败: ${String(e)}`));
      return false;
    } finally {
      setSaving(false);
    }
  }, [activeCatalog, shell, refreshCatalogs]);

  // ── Catalog management ──

  const createCatalog = useCallback(
    async (id: string, label: string): Promise<boolean> => {
      const catalog: FieldCatalog = { id, label, fields: [] };
      try {
        await rpc('catalog.save', { catalog });
        shell.appendOutput(logLine(`[模板助手] 已创建字段目录: ${label}`));
        await refreshCatalogs();
        setActiveCatalogId(id);
        return true;
      } catch (e) {
        shell.appendOutput(logLine(`[模板助手] 创建失败: ${String(e)}`));
        return false;
      }
    },
    [shell, refreshCatalogs],
  );

  const copyCatalog = useCallback(
    async (newId: string, newLabel: string): Promise<boolean> => {
      if (!activeCatalog) return false;
      const catalog: FieldCatalog = {
        ...activeCatalog,
        id: newId,
        label: newLabel,
      };
      try {
        await rpc('catalog.save', { catalog });
        shell.appendOutput(
          logLine(
            `[模板助手] 已复制字段目录: ${activeCatalog.label} → ${newLabel}`,
          ),
        );
        await refreshCatalogs();
        setActiveCatalogId(newId);
        return true;
      } catch (e) {
        shell.appendOutput(logLine(`[模板助手] 复制失败: ${String(e)}`));
        return false;
      }
    },
    [activeCatalog, shell, refreshCatalogs],
  );

  const deleteCatalog = useCallback(async (): Promise<boolean> => {
    if (!activeCatalogId) return false;
    try {
      await rpc('catalog.delete', { id: activeCatalogId });
      shell.appendOutput(
        logLine(`[模板助手] 已删除字段目录: ${activeCatalogId}`),
      );
      setActiveCatalog(null);
      setActiveCatalogId(null);
      setDirty(false);
      await refreshCatalogs();
      return true;
    } catch (e) {
      shell.appendOutput(logLine(`[模板助手] 删除失败: ${String(e)}`));
      return false;
    }
  }, [activeCatalogId, shell, refreshCatalogs]);

  const ctx: Ctx = useMemo(
    () => ({
      catalogs,
      catalogsLoading,
      activeCatalogId,
      activeCatalog,
      catalogLoading,
      dirty,
      saving,
      docxPath,
      validating,
      lastValidation,
      copiedKey,
      editingFieldKey,
      refreshCatalogs,
      selectCatalog,
      setDocxPath,
      validate,
      dismissValidation,
      copyPlaceholder,
      addField,
      updateField,
      removeField,
      saveCatalog,
      setEditingFieldKey,
      createCatalog,
      copyCatalog,
      deleteCatalog,
      renameCatalog,
    }),
    [
      catalogs,
      catalogsLoading,
      activeCatalogId,
      activeCatalog,
      catalogLoading,
      dirty,
      saving,
      docxPath,
      validating,
      lastValidation,
      copiedKey,
      editingFieldKey,
      refreshCatalogs,
      selectCatalog,
      setDocxPath,
      validate,
      dismissValidation,
      copyPlaceholder,
      addField,
      updateField,
      removeField,
      saveCatalog,
      createCatalog,
      copyCatalog,
      deleteCatalog,
      renameCatalog,
    ],
  );

  return (
    <TemplateHelperContext.Provider value={ctx}>
      {children}
    </TemplateHelperContext.Provider>
  );
}
